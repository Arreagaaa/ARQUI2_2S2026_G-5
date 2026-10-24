"""Reglas de Fase 3. No inicia hilos ni toca GPIO al importarse."""
import json
import re
from datetime import datetime, timezone

from .database import get_db_connection
from .telemetry import alarm_once
from ..mensajeria import notifier

PARAM_RANGES = {
    "SegundosLecturaEstacion": (2, 60), "SegundosLatidoEstacion": (5, 60),
    "MinutosSinLluviaReanudar": (1, 30), "UmbralLuzEncendido": (0, 95),
    "UmbralLuzApagado": (5, 100), "ConfianzaMinimaOCR": (30, 95),
    "IntentosOCR": (1, 5), "SegundosEsperaVerificacion": (5, 30),
    "SegundosConteoCola": (2, 30), "UmbralCola": (1, 10),
}
PLATE = re.compile(r"^C\d{3}[A-Z]{3}$")


def now():
    return datetime.now(timezone.utc).isoformat()


def params():
    conn = get_db_connection()
    try:
        return {r["nombre"]: r["valor"] for r in conn.execute("SELECT * FROM fase3_parametros")}
    finally:
        conn.close()


def set_params(values):
    current = params()
    for name, value in values.items():
        if name not in PARAM_RANGES or isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Parametro invalido: {name}")
        lo, hi = PARAM_RANGES[name]
        if value < lo or value > hi:
            raise ValueError(f"{name} fuera de rango {lo}..{hi}")
        if name not in ("UmbralLuzEncendido", "UmbralLuzApagado", "ConfianzaMinimaOCR") and int(value) != value:
            raise ValueError(f"{name} debe ser entero")
    current.update(values)
    if current["UmbralLuzApagado"] - current["UmbralLuzEncendido"] < 5:
        raise ValueError("UmbralLuzApagado debe superar UmbralLuzEncendido por al menos 5")
    conn = get_db_connection()
    try:
        for name, value in values.items():
            conn.execute("UPDATE fase3_parametros SET valor=? WHERE nombre=?", (value, name))
        conn.commit()
    finally:
        conn.close()
    return current


def state_get(key, default=None):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT valor FROM fase3_estado WHERE clave=?", (key,)).fetchone()
        return json.loads(row["valor"]) if row else default
    finally:
        conn.close()


def state_set(key, value):
    conn = get_db_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO fase3_estado VALUES (?,?)", (key, json.dumps(value)))
        conn.commit()
    finally:
        conn.close()


def audit(user, action, data):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO fase3_auditoria(timestamp,usuario,accion,datos) VALUES (?,?,?,?)",
                     (now(), user, action, json.dumps(data)))
        conn.commit()
    finally:
        conn.close()


def affected_transporters():
    """Turnos activos y citas de la franja actual o siguiente (15 min)."""
    conn = get_db_connection()
    try:
        users = {r[0] for r in conn.execute("SELECT DISTINCT transportista_id FROM turnos WHERE estado_actual NOT IN ('Cerrado','Anulado')")}
        # Las fechas y horas de cita se guardan como texto ISO en Fase 2.
        for row in conn.execute("SELECT DISTINCT transportista_id,fecha,hora_inicio FROM citas WHERE estado NOT IN ('CANCELADA','CANCELADO')"):
            try:
                from datetime import datetime, timedelta
                start = datetime.fromisoformat(f"{row['fecha']}T{row['hora_inicio']}").replace(tzinfo=datetime.now().astimezone().tzinfo)
                if -900 <= (start - datetime.now().astimezone()).total_seconds() <= 1800:
                    users.add(row["transportista_id"])
            except (ValueError, KeyError):
                continue
        return sorted(users)
    finally:
        conn.close()


def norm_plate(value):
    return re.sub(r"\s+", "", str(value or "")).upper()


def match_plate(read, candidates):
    """Coincidencia exacta o distancia Hamming 1, solo cuando es unica."""
    read = norm_plate(read)
    names = {norm_plate(p) for p in candidates}
    if read in names:
        return read
    close = [p for p in names if len(p) == len(read) and sum(a != b for a, b in zip(p, read)) == 1]
    return close[0] if len(close) == 1 else None


def verify_plate(uid, read, confidence):
    """Solo decide el resultado; la apertura fisica depende del controlador."""
    conn = get_db_connection()
    try:
        truck = conn.execute("SELECT * FROM catalogo_camiones WHERE UPPER(rfid_uid)=? AND activo=1", (str(uid).upper(),)).fetchone()
        if not truck:
            return {"resultado": "ACCESO DENEGADO", "placa_esperada": None}
        expected = norm_plate(truck["placa"])
        restricted = [r[0] for r in conn.execute("SELECT placa FROM fase3_placas_restringidas WHERE baja_at IS NULL")]
        registered = [r[0] for r in conn.execute("SELECT placa FROM catalogo_camiones WHERE activo=1")]
        threshold = params()["ConfianzaMinimaOCR"]
        found = match_plate(read, registered + restricted) if confidence is not None and confidence >= threshold else None
        if found is None:
            result = "VERIFICACION MANUAL"
        elif found in {norm_plate(p) for p in restricted}:
            result = "PLACA RESTRINGIDA"
        elif found == expected:
            result = "PLACA VERIFICADA"
        else:
            result = "PLACA NO COINCIDE"
        return {"resultado": result, "placa_esperada": expected, "placa_leida": norm_plate(read),
                "placa_identificada": found, "transportista_id": truck["transportista_id"]}
    finally:
        conn.close()


class Runtime:
    """Estado efimero protegido externamente por telemetry_lock del servidor."""
    def __init__(self, publish, broadcast):
        self.publish = publish
        self.broadcast = broadcast
        self.last_heartbeat = None
        self.last_reading_at = None
        self.last_reading = None
        self.station_online = False
        self.raining = False
        self.dry_since = None
        self.suspended_since = None
        self.mode = state_get("modo_iluminacion", "Automatico")
        self.lights = None
        self.queue_count = None
        self.camera_online = None
        self.last_camera_heartbeat = None
        self.gate_enabled = False
        self.pending_access_id = None
        self.pending_since = None

    def command(self, name, **arguments):
        self.publish("portus/cmd/solicitud", {"comando": name, "parametros": arguments,
                                             "origen": "fase3", "timestamp": now()})

    def snapshot(self):
        return {"estacion_operativa": self.station_online, "ultima_lectura": self.last_reading,
                "lloviendo": self.raining if self.station_online else None,
                "grua_suspendida_clima": self.suspended_since,
                "modo_iluminacion": self.mode, "iluminacion_encendida": self.lights,
                "cola": self.queue_count, "camara_operativa": self.camera_online,
                "doble_factor_activo": self.gate_enabled}

    def emit(self):
        snapshot = self.snapshot()
        state_set("clima_publico", snapshot)
        self.broadcast("portus/fase3/estado", snapshot)

    def set_light(self, enabled, force=False):
        if force or enabled != self.lights:
            self.command("IluminacionEncender" if enabled else "IluminacionApagar")
            self.lights = enabled
            self.publish("portus/evt/iluminacion", {"encendida": enabled, "modo": self.mode, "timestamp": now()})
            self.emit()

    def light_rule(self):
        if not self.station_online:
            self.set_light(True)
        elif self.mode == "Encendido forzado":
            self.set_light(True)
        elif self.mode == "Apagado forzado":
            self.set_light(False)
        elif self.last_reading:
            value = self.last_reading["luz"]
            limits = params()
            if value < limits["UmbralLuzEncendido"]:
                self.set_light(True)
            elif value > limits["UmbralLuzApagado"]:
                self.set_light(False)

    def set_mode(self, mode, user):
        if mode not in ("Automatico", "Encendido forzado", "Apagado forzado"):
            raise ValueError("Modo de iluminacion invalido")
        old = self.mode
        self.mode = mode
        state_set("modo_iluminacion", mode)
        audit(user, "modo_iluminacion", {"anterior": old, "nuevo": mode})
        self.light_rule()
        self.emit()

    def ingest(self, topic, data):
        stamp = datetime.now(timezone.utc)
        if topic == "portus/estacion/estado":
            self.last_heartbeat = stamp
            if data.get("estado") != "OPERATIVA":
                self.station_online = False
                alarm_once("AL16")
                self.light_rule()
            self.emit()
            return
        if topic == "portus/estacion/lectura":
            try:
                luz = float(data["luz"])
                temp = None if data.get("temperatura") is None else float(data["temperatura"])
                hum = None if data.get("humedad") is None else float(data["humedad"])
                rain = data["lluvia"]
                if not ((temp is None or -40 <= temp <= 85) and
                        (hum is None or 0 <= hum <= 100) and
                        0 <= luz <= 100 and isinstance(rain, bool)):
                    return
            except (KeyError, ValueError, TypeError):
                return
            self.last_heartbeat = stamp
            self.last_reading_at = stamp
            self.station_online = True
            self.last_reading = {"temperatura": temp, "humedad": hum, "luz": luz,
                                 "lluvia": rain, "timestamp": data.get("timestamp", now())}
            conn = get_db_connection()
            try:
                conn.execute("INSERT INTO fase3_lecturas(timestamp,temperatura,humedad,lluvia,luz,origen) VALUES (?,?,?,?,?,?)",
                             (now(), temp, hum, int(rain), luz, str(data.get("origen", "estacion"))))
                conn.commit()
            finally:
                conn.close()
            if rain and not self.raining:
                self.raining = True
                self.dry_since = None
                self.suspended_since = now()
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO fase3_suspensiones(inicio) VALUES (?)", (self.suspended_since,))
                    conn.commit()
                finally:
                    conn.close()
                self.command("GruaSuspender", motivo="Clima")
                self.publish("portus/evt/clima", {"evento": "suspension", "timestamp": self.suspended_since})
                alarm_once("AL17")
                state_set("transportistas_afectados", affected_transporters())
                audit("automatico", "suspension_lluvia", self.last_reading)
                for user in state_get("transportistas_afectados", []):
                    notifier.send(user, f"PORTUS: grua suspendida por lluvia desde {self.suspended_since}. Su operacion puede demorarse.")
            elif not rain and self.raining:
                self.raining = False
                self.dry_since = stamp
            elif rain:
                self.dry_since = None
            self.light_rule()
            self.emit()

    def tick(self):
        stamp = datetime.now(timezone.utc)
        if self.station_online:
            limits = params()
            heartbeat_stale = self.last_heartbeat and (stamp - self.last_heartbeat).total_seconds() >= 3 * limits["SegundosLatidoEstacion"]
            reading_stale = self.last_reading_at and (stamp - self.last_reading_at).total_seconds() >= 3 * limits["SegundosLecturaEstacion"]
            if heartbeat_stale or reading_stale:
                self.station_online = False
                alarm_once("AL16")
                self.light_rule()
                self.emit()
        if self.station_online and self.suspended_since and self.dry_since and not self.raining:
            if (stamp - self.dry_since).total_seconds() >= params()["MinutosSinLluviaReanudar"] * 60:
                started = self.suspended_since
                self.command("GruaReanudar", motivo="Clima")
                self.suspended_since = None
                conn = get_db_connection()
                try:
                    conn.execute("UPDATE fase3_suspensiones SET fin=? WHERE fin IS NULL", (now(),))
                    conn.commit()
                finally:
                    conn.close()
                self.dry_since = None
                self.publish("portus/evt/clima", {"evento": "reanudacion", "timestamp": now(), "inicio": started})
                audit("automatico", "reanudacion_lluvia", {"inicio": started})
                for user in state_get("transportistas_afectados", []):
                    notifier.send(user, f"PORTUS: grua reanudada a las {now()}. Suspension iniciada {started}.")
                self.emit()

    def set_queue(self, count, publish=True):
        self.queue_count = count
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO fase3_cola(timestamp,cantidad) VALUES (?,?)", (now(), count))
            conn.commit()
        finally:
            conn.close()
        if publish:
            self.publish("portus/vision/cola", {"cantidad": count, "timestamp": now()})
        if count >= params()["UmbralCola"]:
            alarm_once("AL19")
        else:
            conn = get_db_connection()
            try:
                conn.execute("""UPDATE alarmas SET reconocida=1,reconocida_por='automatico',
                    reconocida_en=?,comentario_reconocimiento='Congestion superada'
                    WHERE codigo='AL19' AND reconocida=0""", (now(),))
                conn.commit()
            finally:
                conn.close()
        self.emit()

    def set_camera(self, healthy, publish=True):
        if self.camera_online != healthy:
            self.camera_online = healthy
            if not healthy:
                alarm_once("AL18")
                self.queue_count = None
            if publish:
                self.publish("portus/vision/estado", {"operativa": healthy, "timestamp": now()})
            self.emit()
