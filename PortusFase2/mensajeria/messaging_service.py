"""
Servicio conversacional y de notificaciones para TRANSPORTISTA en PORTUS Fase 2.
Implementa los siete comandos obligatorios (/inicio, /vincular, /cita, /miscitas,
/estado, /misturnos, /ayuda), validacion de codigos de 6 caracteres con expiracion
a 60 minutos, y las nueve notificaciones automaticas con aislamiento estricto de datos.
"""

import time
import string
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from ..server.database import get_db_connection
from . import notifier

# Vida util de una seleccion de franja pendiente antes de descartarse.
PENDIENTE_TTL_SEG = 300
# Cantidad de franjas que se ofrecen al transportista en un solo paso.
FRANJAS_OFERTADAS = 4


def generate_binding_code(transportista_id: str, creado_por: str = "operador1") -> str:
    """
    Genera un codigo unico de vinculacion de 6 caracteres alfanumericos.
    Expira a los 60 minutos y solo puede usarse una vez.
    """
    chars = string.ascii_uppercase + string.digits
    codigo = "".join(random.choices(chars, k=6))

    conn = get_db_connection()
    now = datetime.now(timezone.utc)
    expira = (now + timedelta(minutes=60)).isoformat()

    conn.execute("""
    INSERT INTO vinculaciones_transportista (codigo, transportista_id, creado_por, expira_at, usado, created_at)
    VALUES (?, ?, ?, ?, 0, ?)
    """, (codigo, transportista_id, creado_por, expira, now.isoformat()))
    conn.commit()
    conn.close()

    return codigo


class TransportistaMessagingService:
    def __init__(self):
        # Mapeo en memoria de chat_id -> transportista_id vinculado
        self.session_bindings: Dict[str, str] = {}
        # Solicitud de cita en curso: chat_id -> {contenedor, ts}.
        # Permite el flujo obligatorio de tres pasos: contenedor -> franja -> confirmacion.
        self.pending: Dict[str, Dict[str, Any]] = {}
        self._load_active_bindings()

    def _load_active_bindings(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT chat_id, transportista_id FROM vinculaciones_transportista WHERE usado = 1 AND chat_id IS NOT NULL").fetchall()
        conn.close()
        for r in rows:
            self.session_bindings[r["chat_id"]] = r["transportista_id"]

    def process_message(self, chat_id: str, text: str) -> str:
        """
        Punto de entrada para cualquier mensaje entrante desde el transportista.
        """
        cmd_raw = text.strip()
        if not cmd_raw:
            return "Por favor ingrese un comando. Escriba /inicio o /ayuda para ver las opciones."

        parts = cmd_raw.split()
        # En Telegram un comando puede llegar como /ayuda@MiBot (uso en grupos):
        # el sufijo se descarta para no romper el reconocimiento del comando.
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        # Comandos publicos sin necesidad de vinculacion previa
        if cmd == "/inicio":
            return (
                "Bienvenido a PORTUS - Terminal Portuaria Quetzal.\n"
                "Servicio oficial de atencion a transportistas.\n\n"
                "Comandos disponibles:\n"
                "/inicio - Presenta el servicio y lista comandos disponibles\n"
                "/vincular CODIGO - Asocia su cuenta mediante codigo de 6 caracteres\n"
                "/cita - Solicita una cita para retiro o deposito de carga\n"
                "/miscitas - Lista sus citas vigentes y su estado\n"
                "/estado CONTENEDOR - Consulta estado y ubicacion de su carga\n"
                "/misturnos - Consulta turnos y operaciones en curso\n"
                "/ayuda - Repite la lista de comandos disponibles"
            )

        if cmd == "/ayuda":
            return (
                "Lista de comandos de la Terminal PORTUS:\n"
                "/inicio - Presentacion y menu principal\n"
                "/vincular CODIGO - Vincular cuenta con codigo de 6 caracteres\n"
                "/cita - Programar una nueva cita de atencion\n"
                "/miscitas - Ver citas asignadas y ventanas de atencion\n"
                "/estado CONTENEDOR - Ver ubicacion y autorizacion de un contenedor\n"
                "/misturnos - Ver estado de sus vehiculos en la terminal\n"
                "/ayuda - Muestra esta ayuda"
            )

        if cmd == "/vincular":
            if not args:
                return "Debe proporcionar el codigo de 6 caracteres. Ejemplo: /vincular ABC123"
            codigo_ingresado = args[0].upper()
            return self._vincular_cuenta(chat_id, codigo_ingresado)

        # Para los demas comandos se requiere vinculacion previa
        transportista_id = self.session_bindings.get(chat_id)
        if not transportista_id:
            return (
                "Acceso no autorizado: Su cuenta no esta vinculada.\n"
                "Solicite un codigo de vinculacion al operador de terminal y use:\n"
                "/vincular CODIGO"
            )

        # Texto sin barra: solo se interpreta como eleccion de franja cuando
        # existe una solicitud de cita pendiente para este chat. En cualquier
        # otro caso se responde que el comando no fue reconocido y se ofrece /ayuda.
        if not cmd_raw.startswith("/"):
            pendiente = self.pending.get(chat_id)
            if pendiente and (time.time() - float(pendiente.get("ts", 0))) <= PENDIENTE_TTL_SEG:
                return self._cmd_cita(transportista_id, [pendiente["contenedor"], cmd_raw], chat_id)
            self.pending.pop(chat_id, None)
            return (
                f"Comando '{cmd_raw}' no reconocido.\n"
                "Escriba /ayuda para ver la lista de comandos validos."
            )

        # Comandos autenticados
        if cmd == "/cita":
            return self._cmd_cita(transportista_id, args, chat_id)
        elif cmd == "/miscitas":
            return self._cmd_miscitas(transportista_id)
        elif cmd == "/estado":
            if not args:
                return "Debe indicar el identificador del contenedor. Ejemplo: /estado MSKU1001"
            return self._cmd_estado(transportista_id, args[0].upper())
        elif cmd == "/misturnos":
            return self._cmd_misturnos(transportista_id)
        else:
            return (
                f"Comando '{cmd}' no reconocido.\n"
                "Escriba /ayuda para ver la lista de comandos validos."
            )

    def _vincular_cuenta(self, chat_id: str, codigo: str) -> str:
        conn = get_db_connection()
        now = datetime.now(timezone.utc).isoformat()
        vinc = conn.execute("""
        SELECT * FROM vinculaciones_transportista
        WHERE codigo = ? AND usado = 0
        """, (codigo,)).fetchone()

        if not vinc:
            conn.close()
            return "Codigo de vinculacion invalido o ya utilizado."

        if vinc["expira_at"] < now:
            conn.close()
            return "El codigo de vinculacion ha vencido. Solicite un nuevo codigo al operador."

        transportista_id = vinc["transportista_id"]
        user = conn.execute("SELECT nombre_completo FROM usuarios WHERE username = ?", (transportista_id,)).fetchone()
        nombre = user["nombre_completo"] if user else transportista_id

        conn.execute("""
        UPDATE vinculaciones_transportista
        SET usado = 1, chat_id = ?
        WHERE id = ?
        """, (chat_id, vinc["id"]))
        conn.commit()
        conn.close()

        self.session_bindings[chat_id] = transportista_id
        return f"Vinculacion exitosa: Cuenta vinculada al transportista '{nombre}'. Ya puede operar con /cita o /misturnos."

    def _cmd_cita(self, transportista_id: str, args: List[str], chat_id: Optional[str] = None) -> str:
        """
        Solicitud de cita en tres pasos obligatorios:
        1. /cita                -> lista los contenedores con levante y sin cita.
        2. /cita CONTENEDOR     -> ofrece las proximas franjas con capacidad.
        3. /cita CONTENEDOR HH:MM (o el chat indicando la hora) -> confirma la cita.
        """
        conn = get_db_connection()
        # Buscar contenedores asignados a este transportista con levante otorgado y sin cita vigente
        manifs = conn.execute("""
        SELECT m.id, m.contenedor_id, m.tipo_operacion, m.canal_selectivo
        FROM manifiestos m
        WHERE m.transportista_id = ? AND m.estado_documental = 'LEVANTE_OTORGADO'
        AND m.id NOT IN (
            SELECT manifiesto_id FROM citas WHERE estado IN ('PROGRAMADA', 'CUMPLIDA')
        )
        """, (transportista_id,)).fetchall()

        if not manifs:
            conn.close()
            if chat_id:
                self.pending.pop(chat_id, None)
            return "No tiene contenedores con levante aduanero otorgado pendientes de cita."

        # Paso 1: sin argumentos se listan las opciones disponibles
        if not args:
            lista = "\n".join([f"- {m['contenedor_id']} (Manifiesto {m['id']}, Tipo: {m['tipo_operacion']})" for m in manifs])
            if chat_id:
                self.pending.pop(chat_id, None)
            conn.close()
            return (
                "Contenedores autorizados disponibles para cita:\n"
                f"{lista}\n\n"
                "Para agendar, escriba: /cita CONTENEDOR\n"
                "Ejemplo: /cita " + manifs[0]["contenedor_id"]
            )

        cid = args[0].upper()
        manif_elegido = None
        for m in manifs:
            if m["contenedor_id"] == cid:
                manif_elegido = m
                break

        if not manif_elegido:
            conn.close()
            if chat_id:
                self.pending.pop(chat_id, None)
            return f"El contenedor {cid} no existe o no cuenta con levante aduanero otorgado para su cuenta."

        ahora = datetime.now()
        fecha_hoy = ahora.strftime("%Y-%m-%d")
        oferta = self._oferta_franjas(conn, fecha_hoy, ahora)

        if not oferta:
            conn.close()
            if chat_id:
                self.pending.pop(chat_id, None)
            return "No hay franjas de atencion disponibles en las proximas horas. Intente mas tarde."

        hora_elegida = args[1].strip() if len(args) > 1 else None

        # Paso 2: se ofrecen las franjas disponibles y se espera la eleccion
        if not hora_elegida:
            if chat_id:
                self.pending[chat_id] = {"contenedor": cid, "ts": time.time()}
            lineas = "\n".join(f"- {h_ini} a {h_fin}" for h_ini, h_fin in oferta)
            conn.close()
            return (
                f"Contenedor {cid}: proximas franjas con capacidad disponible:\n"
                f"{lineas}\n\n"
                f"Elija una escribiendo su hora de inicio, por ejemplo: {oferta[0][0]}\n"
                f"(o en un solo paso: /cita {cid} {oferta[0][0]})"
            )

        # Paso 3: la franja elegida debe seguir entre las ofrecidas y con capacidad
        disponibles = {h_ini: h_fin for h_ini, h_fin in oferta}
        if hora_elegida not in disponibles:
            conn.close()
            return (
                f"La franja {hora_elegida} no esta disponible.\n"
                "Escriba /cita para ver las franjas vigentes y elija una de ellas."
            )

        h_ini = hora_elegida
        h_fin = disponibles[h_ini]
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute("""
        INSERT INTO citas (transportista_id, contenedor_id, manifiesto_id, fecha, hora_inicio, hora_fin, estado, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'PROGRAMADA', ?)
        """, (transportista_id, cid, manif_elegido["id"], fecha_hoy, h_ini, h_fin, now_iso))
        conn.commit()
        conn.close()

        if chat_id:
            self.pending.pop(chat_id, None)

        # Notificacion automatica obligatoria: asignacion de cita
        notifier.send(
            transportista_id,
            self.notify_cita_asignada(transportista_id, cid, fecha_hoy, h_ini, h_fin),
        )

        return (
            f"Cita confirmada exitosamente.\n"
            f"Contenedor: {cid}\n"
            f"Fecha: {fecha_hoy}\n"
            f"Ventana de atencion: {h_ini} a {h_fin}\n"
            f"Tolerancia de presentacion: hasta 5 minutos despues de las {h_fin}."
        )

    def _oferta_franjas(self, conn, fecha: str, ahora: datetime, cantidad: int = FRANJAS_OFERTADAS) -> List[tuple]:
        """
        Proximas franjas de 15 minutos con capacidad disponible (menos de dos
        citas) y no bloqueadas por el operador. Se exploran las proximas 4 horas.
        """
        oferta: List[tuple] = []
        cursor = ahora.replace(minute=(ahora.minute // 15) * 15, second=0, microsecond=0) + timedelta(minutes=15)
        for _ in range(16):
            h_ini = cursor.strftime("%H:%M")
            h_fin = (cursor + timedelta(minutes=15)).strftime("%H:%M")
            if self._franja_disponible(conn, fecha, h_ini):
                oferta.append((h_ini, h_fin))
                if len(oferta) >= cantidad:
                    break
            cursor += timedelta(minutes=15)
        return oferta

    @staticmethod
    def _franja_disponible(conn, fecha: str, h_ini: str) -> bool:
        """Reglas de la agenda: capacidad maxima de dos y franja no bloqueada."""
        ocupadas = conn.execute("""
        SELECT COUNT(*) as c FROM citas
        WHERE fecha = ? AND hora_inicio = ? AND estado = 'PROGRAMADA'
        """, (fecha, h_ini)).fetchone()["c"]
        if ocupadas >= 2:
            return False
        bloqueada = conn.execute("""
        SELECT COUNT(*) as c FROM franjas_bloqueadas
        WHERE fecha = ? AND hora_inicio = ?
        """, (fecha, h_ini)).fetchone()["c"]
        return bloqueada == 0

    def _cmd_miscitas(self, transportista_id: str) -> str:
        conn = get_db_connection()
        citas = conn.execute("""
        SELECT * FROM citas
        WHERE transportista_id = ?
        ORDER BY id DESC LIMIT 10
        """, (transportista_id,)).fetchall()
        conn.close()

        if not citas:
            return "No tiene citas registradas."

        lineas = []
        for c in citas:
            lineas.append(
                f"- Contenedor: {c['contenedor_id']} | Fecha: {c['fecha']} | Ventana: {c['hora_inicio']}-{c['hora_fin']} | Estado: {c['estado']}"
            )
        return "Sus citas vigentes e historicas:\n" + "\n".join(lineas)

    def _cmd_estado(self, transportista_id: str, contenedor_id: str) -> str:
        conn = get_db_connection()
        # Verificar que el contenedor pertenezca al transportista
        manif = conn.execute("""
        SELECT * FROM manifiestos
        WHERE contenedor_id = ? AND transportista_id = ?
        ORDER BY id DESC LIMIT 1
        """, (contenedor_id, transportista_id)).fetchone()

        if not manif:
            conn.close()
            return f"No tiene carga asociada al identificador {contenedor_id}."

        patio = conn.execute("""
        SELECT * FROM patio_posiciones WHERE contenedor_id = ?
        """, (contenedor_id,)).fetchone()

        ubicacion = "Fuera de terminal"
        permanencia_str = "0h 0m"
        if patio:
            ubicacion = f"Patio Posicion {patio['posicion']}, Nivel {patio['nivel']}"
            if patio["ingreso_at"]:
                try:
                    t_ing = datetime.fromisoformat(patio["ingreso_at"])
                    diff_m = int((datetime.now(timezone.utc) - t_ing).total_seconds() / 60)
                    permanencia_str = f"{diff_m // 60}h {diff_m % 60}m"
                except Exception:
                    pass

        canal = manif["canal_selectivo"] or "Pendiente de asignacion"
        estado_doc = manif["estado_documental"]
        conn.close()

        return (
            f"Estado del contenedor {contenedor_id}:\n"
            f"Estado documental: {estado_doc}\n"
            f"Ubicacion actual: {ubicacion}\n"
            f"Permanencia en patio: {permanencia_str}\n"
            f"Canal aduanero: {canal}"
        )

    def _cmd_misturnos(self, transportista_id: str) -> str:
        conn = get_db_connection()
        turnos = conn.execute("""
        SELECT * FROM turnos
        WHERE transportista_id = ? AND estado_actual NOT IN ('Cerrado', 'Anulado')
        ORDER BY id DESC
        """, (transportista_id,)).fetchall()
        conn.close()

        if not turnos:
            return "No tiene turnos u operaciones activas en este momento."

        lineas = []
        for t in turnos:
            lineas.append(
                f"- Turno {t['codigo_turno']} | Vehiculo: {t['placa_vehiculo']} | Contenedor: {t['contenedor_id']} | "
                f"Operacion: {t['tipo_operacion']} | Estado: {t['estado_actual']} | Estacion: {t['estacion_actual']}"
            )
        return "Sus operaciones activas en la terminal:\n" + "\n".join(lineas)

    # -------------------------------------------------------------
    # Metodos para las 9 Notificaciones Automaticas Obligatorias
    # -------------------------------------------------------------
    def notify_levante_otorgado(self, transportista_id: str, contenedor: str, canal: str) -> str:
        advertencia = " ATENCION: Al tener canal rojo asignado, su vehiculo sera desviado a verificacion fisica en parqueo." if canal == "ROJO" else ""
        return f"[AVISO PORTUS] Levante aduanero otorgado para contenedor {contenedor}. Canal asignado: {canal}.{advertencia}"

    def notify_levante_retenido(self, transportista_id: str, contenedor: str, motivo: str) -> str:
        return f"[AVISO PORTUS] Levante aduanero RETENIDO para contenedor {contenedor}. Motivo: {motivo}."

    def notify_cita_asignada(self, transportista_id: str, contenedor: str, fecha: str, h_ini: str, h_fin: str) -> str:
        return f"[AVISO PORTUS] Cita asignada para contenedor {contenedor} el dia {fecha} en ventana de {h_ini} a {h_fin}."

    def notify_recordatorio_cita(self, transportista_id: str, contenedor: str, h_ini: str, h_fin: str) -> str:
        return f"[RECORDATORIO] Falta 1 hora para su ventana de atencion ({h_ini}-{h_fin}) para el contenedor {contenedor}."

    def notify_vehiculo_retenido(self, transportista_id: str, vehiculo: str, contenedor: str, causa: str, peso_dec: Optional[int] = None, peso_med: Optional[int] = None) -> str:
        det = ""
        if peso_dec is not None and peso_med is not None:
            det = f" (Peso declarado: {peso_dec}g, Peso medido: {peso_med}g, Diferencia: {abs(peso_med - peso_dec)}g)"
        return f"[ALERTA PORTUS] Vehiculo {vehiculo} con contenedor {contenedor} ha sido RETENIDO en parqueo. Causa: {causa}{det}."

    def notify_retencion_resuelta(self, transportista_id: str, vehiculo: str, contenedor: str, resolucion: str, nuevo_peso: Optional[int] = None, motivo: Optional[str] = None) -> str:
        det = ""
        if resolucion == "CORREGIR" and nuevo_peso:
            det = f" Nuevo peso oficial registrado: {nuevo_peso}g."
        elif resolucion == "RECHAZAR" and motivo:
            det = f" Motivo de rechazo: {motivo}."
        return f"[AVISO PORTUS] Retencion de vehiculo {vehiculo} ({contenedor}) resuelta mediante {resolucion}.{det}"

    def notify_cita_cancelada_reprogramada(self, transportista_id: str, contenedor: str, situacion: str, nueva_ventana: Optional[str] = None) -> str:
        det = f" Nueva ventana: {nueva_ventana}" if nueva_ventana else ""
        return f"[AVISO PORTUS] Su cita para el contenedor {contenedor} ha sido {situacion}.{det}"

    def notify_turno_cerrado(self, transportista_id: str, vehiculo: str, contenedor: str, tipo_op: str, tiempo_seg: int) -> str:
        minutos = tiempo_seg // 60
        return f"[AVISO PORTUS] Operacion completada. Turno CERRADO para vehiculo {vehiculo} ({contenedor}, {tipo_op}). Tiempo total en terminal: {minutos} minutos."

    def notify_turno_anulado(self, transportista_id: str, vehiculo: str, contenedor: str, causa: str) -> str:
        return f"[AVISO PORTUS] Turno ANULADO para vehiculo {vehiculo} ({contenedor}). Motivo: {causa}. Vehiculo autorizado para salir sin completar operacion."
