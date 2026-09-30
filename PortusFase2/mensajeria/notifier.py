"""
Capa de salida del canal de mensajeria del TRANSPORTISTA.

Los avisos no se envian desde el hilo que los origina: se encolan y un hilo
emisor independiente los entrega. Asi, una caida de Internet o de la API de
Telegram nunca bloquea una peticion HTTP de Flask ni el hilo de telemetria MQTT,
que es el camino critico del sistema.

Si no existe TELEGRAM_BOT_TOKEN el sistema sigue funcionando igual que antes:
el aviso queda registrado en el log con el prefijo [SIN TELEGRAM].
"""

import os
import time
import queue
import logging
import threading
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from ..server.database import get_db_connection

TELEGRAM_API_TIMEOUT = 5
COLA_MAXIMA = 500
INTERVALO_RECORDATORIO_SEG = 60

_cola: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=COLA_MAXIMA)
_lock_emisor = threading.Lock()
_emisor_activo = False
_recordatorios_activos = False


def token_telegram() -> str:
    """Token del bot de Telegram. Vacio si el canal aun no esta configurado."""
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def start() -> bool:
    """Arranca el hilo emisor una sola vez. Idempotente."""
    global _emisor_activo
    with _lock_emisor:
        if _emisor_activo:
            return True
        _emisor_activo = True
    threading.Thread(target=_loop_emisor, name="portus-notifier", daemon=True).start()
    logging.info(
        "Notificador de transportistas iniciado (%s)",
        "Telegram conectado" if token_telegram() else "sin TELEGRAM_BOT_TOKEN: los avisos van al log",
    )
    return True


def start_reminders() -> bool:
    """Arranca el hilo de recordatorios de cita (1 hora antes). Idempotente."""
    global _recordatorios_activos
    with _lock_emisor:
        if _recordatorios_activos:
            return True
        _recordatorios_activos = True
    threading.Thread(target=_loop_recordatorios, name="portus-recordatorios", daemon=True).start()
    logging.info("Recordatorios de cita iniciados (cada %d s)", INTERVALO_RECORDATORIO_SEG)
    return True


def send(transportista_id: Optional[str], texto: Optional[str]) -> None:
    """
    Encola un aviso para el transportista indicado.
    Nunca bloquea y nunca lanza excepciones: el emisor hace el trabajo pesado.
    """
    if not transportista_id or not texto:
        return
    item = {"transportista_id": str(transportista_id), "texto": str(texto), "ts": time.time()}
    try:
        _cola.put_nowait(item)
    except queue.Full:
        # Cola llena: se descarta el aviso mas antiguo y se conserva el nuevo.
        try:
            _cola.get_nowait()
        except queue.Empty:
            pass
        try:
            _cola.put_nowait(item)
        except queue.Full:
            logging.warning("Cola de avisos llena; se descarta el aviso para %s", transportista_id)


def pending_count() -> int:
    """Avisos esperando entrega (util para pruebas y diagnostico)."""
    return _cola.qsize()


def resolver_chats(transportista_id: str) -> List[str]:
    """Devuelve los chat_id de Telegram vinculados y activos de un transportista."""
    conn = get_db_connection()
    try:
        filas = conn.execute(
            """
            SELECT chat_id FROM vinculaciones_transportista
            WHERE transportista_id = ? AND usado = 1 AND chat_id IS NOT NULL AND chat_id <> ''
            """,
            (str(transportista_id),),
        ).fetchall()
    finally:
        conn.close()
    return [str(f["chat_id"]) for f in filas]


def _loop_emisor() -> None:
    while True:
        try:
            item = _cola.get(timeout=1)
        except queue.Empty:
            continue
        except Exception:
            logging.exception("Error obteniendo un aviso de la cola")
            continue
        try:
            _entregar(item)
        except Exception:
            logging.exception("Error entregando un aviso de transportista")


def _entregar(item: Dict[str, Any]) -> None:
    transportista_id = item["transportista_id"]
    texto = item["texto"]
    chats = resolver_chats(transportista_id)

    if not chats:
        logging.info(
            "[SIN CANAL] Aviso para %s sin cuenta de mensajeria vinculada: %s",
            transportista_id, texto,
        )
        return

    if not token_telegram():
        for chat_id in chats:
            logging.info("[SIN TELEGRAM] chat=%s aviso=%s", chat_id, texto)
        return

    # Import perezoso: si el canal no esta disponible, el sistema sigue operando.
    try:
        from .telegram_bot import send_message
    except Exception:
        logging.exception("No se pudo cargar el canal de Telegram")
        return

    for chat_id in chats:
        if not send_message(chat_id, texto):
            logging.warning("No se pudo entregar el aviso a chat %s (transportista %s)", chat_id, transportista_id)


def _loop_recordatorios() -> None:
    while True:
        time.sleep(INTERVALO_RECORDATORIO_SEG)
        try:
            _procesar_recordatorios()
        except Exception:
            logging.exception("Error evaluando recordatorios de cita")


def _procesar_recordatorios() -> None:
    """
    Envia el recordatorio obligatorio cuando falta una hora o menos para la
    ventana asignada. Idempotente: cada cita se notifica una sola vez gracias
    a la columna citas.recordatorio_enviado.
    """
    conn = get_db_connection()
    try:
        hoy = date.today().isoformat()
        ahora = datetime.now()
        filas = conn.execute(
            """
            SELECT id, transportista_id, contenedor_id, fecha, hora_inicio, hora_fin
            FROM citas
            WHERE estado = 'PROGRAMADA' AND fecha = ? AND recordatorio_enviado = 0
            """,
            (hoy,),
        ).fetchall()

        pendientes = []
        for cita in filas:
            try:
                inicio = datetime.strptime(f"{cita['fecha']} {cita['hora_inicio']}", "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                continue
            restante_seg = (inicio - ahora).total_seconds()
            if restante_seg <= 0 or restante_seg > 3600:
                continue
            pendientes.append(cita)

        if not pendientes:
            return

        try:
            from .messaging_service import TransportistaMessagingService
            servicio = TransportistaMessagingService()
        except Exception:
            logging.exception("No se pudo construir el servicio de mensajeria para recordatorios")
            return

        for cita in pendientes:
            texto = servicio.notify_recordatorio_cita(
                cita["transportista_id"], cita["contenedor_id"],
                cita["hora_inicio"], cita["hora_fin"],
            )
            send(cita["transportista_id"], texto)
            conn.execute("UPDATE citas SET recordatorio_enviado = 1 WHERE id = ?", (cita["id"],))
        conn.commit()
        logging.info("Recordatorio(s) de cita encolado(s): %d", len(pendientes))
    finally:
        conn.close()
