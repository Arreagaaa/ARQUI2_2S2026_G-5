"""
Bot de Telegram del canal de mensajeria del TRANSPORTISTA (PORTUS Fase 2).

Puente thin entre la API de Telegram y TransportistaMessagingService, que es
quien implementa los siete comandos obligatorios. Se usa long polling (getUpdates)
en un hilo daemon: no requiere webhook, no requiere IP publica y no interfiere
con el servidor web ni con el puente serial.

Solo se arranca si existe TELEGRAM_BOT_TOKEN en el entorno. Sin token el
sistema conserva el endpoint /api/mensajeria/simulador para pruebas.
"""

import os
import time
import logging
import threading
from typing import Any, Dict, Optional

import requests

API_BASE = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_TIMEOUT_SEG = 30          # long polling del lado de Telegram
HTTP_TIMEOUT_SEG = 35              # siempre mayor que el anterior
LARGO_MAXIMO_MENSAJE = 4096
LARGO_BLOQUE = 3800                # margen para el encabezado de formato

_lock = threading.Lock()
_activo = False
_offset = 0


def token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def disponible() -> bool:
    """True si hay token configurado y el canal puede operar."""
    return bool(token())


def _api(method: str, params: Optional[Dict[str, Any]] = None, http: str = "get") -> Optional[Dict[str, Any]]:
    """Llamada sincronica a la API de Telegram. Devuelve None si falla."""
    if not disponible():
        return None
    url = API_BASE.format(token=token(), method=method)
    try:
        if http == "post":
            resp = requests.post(url, params=params, timeout=HTTP_TIMEOUT_SEG)
        else:
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT_SEG)
        datos = resp.json()
        if not datos.get("ok"):
            logging.warning("Telegram %s respondio error: %s", method, datos.get("description"))
            return None
        return datos
    except Exception as exc:
        logging.warning("No se pudo llamar a Telegram %s: %s", method, exc)
        return None


def send_message(chat_id: str, texto: str) -> bool:
    """
    Envia un mensaje al chat indicado, partido en bloques de menos de 4096
    caracteres. Devuelve True solo si Telegram confirmo el envio.
    """
    if not chat_id or not texto:
        return False

    fragmentos = []
    resto = str(texto)
    while len(resto) > LARGO_BLOQUE:
        corte = resto.rfind("\n", 0, LARGO_BLOQUE)
        if corte <= 0:
            corte = LARGO_BLOQUE
        fragmentos.append(resto[:corte])
        resto = resto[corte:].lstrip("\n")
    fragmentos.append(resto)

    enviado = True
    for i, bloque in enumerate(fragmentos):
        if i:
            time.sleep(0.15)  # cortesia con el limite de mensajes por segundo
        datos = _api("sendMessage", {"chat_id": chat_id, "text": bloque}, http="post")
        if datos is None:
            enviado = False
    return enviado


def start(msg_service) -> bool:
    """
    Arranca el bucle de polling una sola vez. Recibe la instancia de
    TransportistaMessagingService para no crear dependencias circulares.
    Idempotente: llamarlo varias veces no duplica hilos.
    """
    global _activo
    if not disponible():
        logging.info("Bot de Telegram no iniciado: TELEGRAM_BOT_TOKEN vacio (modo simulador).")
        return False
    with _lock:
        if _activo:
            return True
        _activo = True
    threading.Thread(target=_loop, args=(msg_service,), name="portus-telegram", daemon=True).start()
    logging.info("Bot de Telegram iniciado (long polling).")
    return True


def _loop(msg_service) -> None:
    global _offset
    logging.info("Bot de Telegram escuchando mensajes...")
    while True:
        try:
            datos = _api("getUpdates", {
                "offset": _offset,
                "timeout": TELEGRAM_TIMEOUT_SEG,
                "allowed_updates": '["message"]',
            })
            if datos is None:
                # Sin conexion o token invalido: se reintenta sin tumbar el hilo.
                time.sleep(5)
                continue

            for update in datos.get("result", []):
                # El offset se avanza antes de responder: una caida intermedia
                # nunca provoca un bucle infinito del mismo update.
                _offset = update.get("update_id", 0) + 1
                mensaje = update.get("message") or update.get("edited_message") or {}
                chat_id = str((mensaje.get("chat") or {}).get("id", "")).strip()
                texto = (mensaje.get("text") or "").strip()
                if not chat_id:
                    continue
                if not texto:
                    _responder(chat_id, "Mensaje no reconocido. Escriba /ayuda para ver la lista de comandos.")
                    continue
                _responder(chat_id, _procesar(msg_service, chat_id, texto))
        except Exception:
            logging.exception("Error en el bucle del bot de Telegram")
            time.sleep(3)


def _procesar(msg_service, chat_id: str, texto: str) -> str:
    """Traduce el mensaje entrante y delega en el servicio de mensajeria."""
    normalizado = texto
    partes = texto.split()
    if partes and partes[0].lower().startswith("/start"):
        normalizado = "/inicio"
    try:
        return msg_service.process_message(chat_id, normalizado)
    except Exception:
        logging.exception("Error procesando mensaje de Telegram")
        return (
            "El servicio no pudo procesar su mensaje. "
            "Intente de nuevo o escriba /ayuda para ver la lista de comandos."
        )


def _responder(chat_id: str, texto: str) -> None:
    """Nunca lanza excepciones: el servicio jamas debe quedar sin respuesta."""
    try:
        if not send_message(chat_id, texto):
            logging.warning("Respuesta no entregada al chat %s", chat_id)
    except Exception:
        logging.exception("Error respondiendo al chat %s", chat_id)
