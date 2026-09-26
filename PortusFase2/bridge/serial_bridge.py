"""
Puente de comunicacion bidireccional Serial <-> MQTT para PORTUS Fase 2.
Traduce eventos seriales del controlador Arduino Mega a mensajes en los topicos
portus/evt/* y comandos de la plataforma en portus/cmd/solicitud a tramas seriales.
Supervisa el latido cada 5 segundos y dispara AL01 si se pierden 3 periodos consecutivos.
"""

import sys
import time
import json
import uuid
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

try:
    import serial
except ImportError:
    serial = None

import paho.mqtt.client as mqtt
from .serial_protocol import SerialProtocol
from .legacy_telemetry import LegacyTelemetry
from .mock_controller import MockArduinoMega

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class SerialMQTTBridge:
    def __init__(
        self,
        port: str = "COM3",
        baudrate: int = 115200,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        use_mock: bool = False
    ):
        self.port = port
        self.baudrate = baudrate
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.use_mock = use_mock

        self.serial_conn = None
        self.mock_controller: Optional[MockArduinoMega] = None
        self.mqtt_client: Optional[mqtt.Client] = None

        self.running = False
        self.seq_out = 1
        self.last_heartbeat_time = time.time()
        self.link_lost = False
        self.lock = threading.Lock()
        self.legacy = LegacyTelemetry()
        self.protocol = "mock" if use_mock else "fase1"

    def start(self):
        self.running = True
        self._init_mqtt()

        if self.use_mock:
            self._init_mock()
        else:
            if serial is None:
                raise RuntimeError("Instale pyserial para usar el Arduino real")
            # A physical connection failure must never silently simulate hardware.
            self._open_serial()
            threading.Thread(target=self._serial_read_loop, daemon=True).start()
            threading.Thread(target=self._query_loop, daemon=True).start()

        # Hilo de supervision de enlace (deteccion AL01 tras 15 segundos sin latido)
        threading.Thread(target=self._watchdog_loop, daemon=True).start()

    def _init_mock(self):
        logging.info("Iniciando controlador simulado de Arduino Mega")
        self.mock_controller = MockArduinoMega(on_tx_callback=self._handle_controller_line)
        self.mock_controller.start()

    def _init_mqtt(self):
        self.mqtt_client = mqtt.Client(client_id=f"portus_bridge_{uuid.uuid4().hex[:6]}")
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        try:
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()
            logging.info("Conectado al broker MQTT en %s:%d", self.mqtt_host, self.mqtt_port)
        except Exception as e:
            logging.error("Error al conectar con broker MQTT (%s:%d): %s", self.mqtt_host, self.mqtt_port, e)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info("Suscrito a portus/cmd/solicitud")
            client.subscribe("portus/cmd/solicitud")
        else:
            logging.warning("Fallo conexion MQTT rc=%d", rc)

    def _on_mqtt_message(self, client, userdata, msg):
        """
        Recibe comandos remotos emitidos desde la plataforma web y los retransmite al controlador.
        """
        if msg.topic == "portus/cmd/solicitud":
            try:
                payload_str = msg.payload.decode("utf-8")
                data = json.loads(payload_str)
                cmd = data.get("comando") or data.get("cmd")
                parametros = data.get("parametros", {})

                # Construir string de parametros para el protocolo serial
                param_str = ";".join([f"{k}={v}" for k, v in parametros.items()])
                self.send_command_to_controller(cmd, param_str)
            except Exception as e:
                logging.error("Error procesando mensaje MQTT en portus/cmd/solicitud: %s", e)

    def send_command_to_controller(self, cmd: str, payload_str: str = ""):
        if not self.use_mock:
            self.publish_event("portus/cmd/respuesta", "RechazoComando", {
                "resultado": "NAK", "comando": cmd,
                "error": "El firmware Fase1 instalado solo permite supervision; opere el control local."})
            return
        with self.lock:
            frame = SerialProtocol.build_frame(self.seq_out, "CMD", cmd, payload_str)
            self.seq_out = (self.seq_out + 1) % 65536

        logging.info("Enviando comando al controlador: %s", frame.strip())
        if self.mock_controller:
            self.mock_controller.process_incoming_line(frame)
        elif self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(frame.encode("utf-8"))
            except Exception as e:
                logging.error("Error escribiendo en puerto serial: %s", e)

    def _open_serial(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=0.1)
            logging.info("Serial real %s a %d baud (sin simulacion)", self.port, self.baudrate)
        except Exception as exc:
            self.serial_conn = None
            logging.error("Serial no disponible: %s. Se reintentara; NO se usara mock.", exc)

    def _query_loop(self):
        # Commands already supported by Fase1, all read-only. Also works with
        # the older sketch without heartbeat. Never TARA/REARME/REINICIAR.
        while self.running:
            time.sleep(2)
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    with self.lock:
                        self.serial_conn.write(b"ESTADO\nPATIO\nGRUA\n")
                except Exception as exc:
                    logging.warning("Consulta serial: %s", exc)

    def _serial_read_loop(self):
        buf = b""
        while self.running:
            if not self.serial_conn:
                time.sleep(2)
                self._open_serial()
                buf = b""
                continue
            try:
                chunk = self.serial_conn.read(self.serial_conn.in_waiting or 1)
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    self._handle_controller_line(raw.decode("utf-8", errors="replace"))
                if len(buf) > 8192:
                    buf = b""
            except Exception as exc:
                logging.error("Lectura serial: %s", exc)
                self.serial_conn.close()
                self.serial_conn = None

    def _handle_controller_line(self, line: str):
        """
        Procesa una linea recibida del controlador (fisico o simulado)
        y la publica en el espacio de topicos portus/evt/* o portus/cmd/respuesta.
        """
        legacy_event = self.legacy.feed(line)
        parsed = SerialProtocol.parse_frame(line)
        if not parsed:
            return

        if not legacy_event and not parsed["valid"]:
            return
        self.last_heartbeat_time = time.time()
        if self.link_lost:
            self.link_lost = False
            logging.info("Enlace con el controlador restablecido")
            self.publish_event("portus/evt/estado", "EnlaceRestablecido", {"estado": "CONECTADO"})

        if legacy_event:
            kind, values = legacy_event
            if kind not in ("SnapshotInicio", "SnapshotParte", "SnapshotIncompleto"):
                topic = next((name for word, name in (
                    ("Pesaje", "pesaje"), ("Salida", "salida"),
                    ("Grua", "grua"), ("Patio", "patio"),
                    ("Paro", "alarma")) if word in kind), "estado")
                self.publish_event("portus/evt/" + topic, kind, values)
            return

        tipo = parsed["tipo"]
        cmd = parsed["cmd"]
        payload_raw = parsed["payload"]

        # Parsear payload key=value
        datos = {}
        if payload_raw:
            for item in payload_raw.split(";"):
                if "=" in item:
                    k, v = item.split("=", 1)
                    datos[k.strip()] = v.strip()
                else:
                    datos["info"] = item.strip()

        # Enrutamiento segun especificacion de topicos
        if tipo in ("ACK", "NAK"):
            topic = "portus/cmd/respuesta"
            event_type = "AceptacionComando" if tipo == "ACK" else "RechazoComando"
            datos["resultado"] = tipo
            datos["comando"] = cmd
        elif tipo == "HB" or cmd == "LatidoEstado":
            topic = "portus/evt/estado"
            event_type = "Latido"
        elif "Garita" in cmd:
            topic = "portus/evt/garita"
            event_type = cmd
        elif "Pesaje" in cmd:
            topic = "portus/evt/pesaje"
            event_type = cmd
        elif "Aguja" in cmd:
            topic = "portus/evt/aguja"
            event_type = cmd
        elif "Transferencia" in cmd:
            topic = "portus/evt/transferencia"
            event_type = cmd
        elif "Grua" in cmd:
            topic = "portus/evt/grua"
            event_type = cmd
        elif "Patio" in cmd:
            topic = "portus/evt/patio"
            event_type = cmd
        elif "Salida" in cmd:
            topic = "portus/evt/salida"
            event_type = cmd
        elif "Alarma" in cmd or "ParoEmergencia" in cmd:
            topic = "portus/evt/alarma"
            event_type = cmd
        else:
            topic = "portus/evt/estado"
            event_type = cmd

        self.publish_event(topic, event_type, datos)

    def publish_event(self, topic: str, tipo_evento: str, datos: dict):
        """
        Publica con el formato obligatorio cerrado de la seccion 10.2:
        - id: identificador unico
        - timestamp: marca de tiempo ISO 8601
        - origen: "controlador"
        - tipo: tipo de evento
        - datos: diccionario con los campos propios del evento
        """
        now_str = datetime.now(timezone.utc).isoformat()
        mensaje = {
            "id": str(uuid.uuid4()),
            "timestamp": now_str,
            "origen": "controlador",
            "protocolo": self.protocol,
            "tipo": tipo_evento,
            "datos": datos
        }

        if self.mqtt_client:
            try:
                self.mqtt_client.publish(topic, json.dumps(mensaje), qos=1)
            except Exception as e:
                logging.error("Error al publicar en MQTT %s: %s", topic, e)

    def _watchdog_loop(self):
        """
        Monitorea el latido periodico (maximo 5 segundos).
        Si deja de recibirse por 3 periodos consecutivos (15 segundos),
        declara enlace perdido y genera la alarma AL01.
        """
        while self.running:
            time.sleep(2.0)
            elapsed = time.time() - self.last_heartbeat_time
            if elapsed > 15.0 and not self.link_lost:
                self.link_lost = True
                logging.warning("ALERTA: Enlace con el controlador perdido (%0.1f s sin latido). Generando AL01.", elapsed)
                self.publish_event(
                    "portus/evt/alarma",
                    "AlarmaGenerada",
                    {
                        "codigo": "AL01",
                        "severidad": "Critica",
                        "descripcion": "Enlace con el controlador perdido",
                        "origen": "servidor",
                        "tiempo_transcurrido": round(elapsed, 1)
                    }
                )
                self.publish_event(
                    "portus/evt/estado",
                    "EnlacePerdido",
                    {"estado": "DESCONECTADO", "ultimo_latido": elapsed}
                )

    def stop(self):
        self.running = False
        if self.mock_controller:
            self.mock_controller.stop()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()


if __name__ == "__main__":
    bridge = SerialMQTTBridge(use_mock=True)
    bridge.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()
