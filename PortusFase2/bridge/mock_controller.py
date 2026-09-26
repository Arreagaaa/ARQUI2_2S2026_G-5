"""
Simulador del microcontrolador Arduino Mega 2560 para PORTUS Fase 2.
Permite evaluar y verificar el comportamiento determinista, los enclavamientos
de seguridad de los 13 comandos remotos, el latido periodico y la emision de
eventos fisicos sin depender de la conexion fisica a la maqueta.
"""

import time
import threading
from typing import Callable, Optional
from .serial_protocol import SerialProtocol


class MockArduinoMega:
    def __init__(self, on_tx_callback: Optional[Callable[[str], None]] = None):
        self.on_tx_callback = on_tx_callback
        self.seq_out = 1
        self.lock = threading.Lock()
        self.running = False
        self.heartbeat_thread: Optional[threading.Thread] = None

        # Estados fisicos de la maqueta
        self.modo_mantenimiento = False
        self.talanquera_abierta = False
        self.puerta_salida_abierta = False
        self.aguja_estado = "RECTA"  # "RECTA", "PARQUEO", "LIBERANDO"

        # Sensores de presencia
        self.vehiculo_bajo_talanquera = False
        self.vehiculo_bajo_puerta_salida = False
        self.vehiculo_sobre_aguja = False
        self.vehiculo_en_parqueo = False
        self.vehiculo_en_transferencia = False

        # Estado de la grua
        self.grua_referenciada = True
        self.grua_en_reposo = True
        self.grua_suspendida = False
        self.grua_en_falla = False
        self.grua_carga_adherida = False
        self.grua_trabajo_en_curso = False
        self.grua_posicion_actual = 0  # 0: transferencia, 1: P0, 2: P1
        self.grua_trabajos_pendientes = 0

        # Bloqueos de posiciones de patio
        self.posiciones_bloqueadas = {0: False, 1: False}
        self.posicion_trabajo_actual = None

        # Paro de emergencia
        self.paro_emergencia = False

        # Alarma sonora
        self.alarma_sonora_activa = False

    def start(self):
        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def stop(self):
        self.running = False

    def emit_event(self, cmd: str, payload: str):
        with self.lock:
            frame = SerialProtocol.build_frame(self.seq_out, "EVT", cmd, payload)
            self.seq_out = (self.seq_out + 1) % 65536
        if self.on_tx_callback:
            self.on_tx_callback(frame)

    def _send_response(self, tipo: str, cmd: str, payload: str):
        with self.lock:
            frame = SerialProtocol.build_frame(self.seq_out, tipo, cmd, payload)
            self.seq_out = (self.seq_out + 1) % 65536
        if self.on_tx_callback:
            self.on_tx_callback(frame)

    def _heartbeat_loop(self):
        while self.running:
            modo_str = "MANTENIMIENTO" if self.modo_mantenimiento else "NORMAL"
            if self.paro_emergencia:
                modo_str = "PARO_EMERGENCIA"

            payload = (
                f"modo={modo_str};"
                f"talanquera={'ABIERTA' if self.talanquera_abierta else 'CERRADA'};"
                f"aguja={self.aguja_estado};"
                f"grua_ref={'SI' if self.grua_referenciada else 'NO'};"
                f"grua_susp={'SI' if self.grua_suspendida else 'NO'};"
                f"grua_falla={'SI' if self.grua_en_falla else 'NO'};"
                f"grua_pos={self.grua_posicion_actual};"
                f"cola_grua={self.grua_trabajos_pendientes};"
                f"estop={'SI' if self.paro_emergencia else 'NO'}"
            )
            self.emit_event("LatidoEstado", payload)
            time.sleep(4.5)

    def process_incoming_line(self, line: str):
        parsed = SerialProtocol.parse_frame(line)
        if not parsed or not parsed["valid"]:
            # Intento de parseo de comando de consola antiguo
            cmd_upper = line.strip().upper()
            if cmd_upper == "REINICIAR":
                self._reset_state()
                self._send_response("ACK", "REINICIAR", "estado=OK")
            return

        tipo = parsed["tipo"]
        cmd = parsed["cmd"]
        payload = parsed["payload"]

        if tipo == "CMD":
            self.handle_command(cmd, payload)

    def _reset_state(self):
        self.modo_mantenimiento = False
        self.talanquera_abierta = False
        self.puerta_salida_abierta = False
        self.aguja_estado = "RECTA"
        self.vehiculo_bajo_talanquera = False
        self.vehiculo_bajo_puerta_salida = False
        self.vehiculo_sobre_aguja = False
        self.vehiculo_en_parqueo = False
        self.vehiculo_en_transferencia = False
        self.grua_referenciada = True
        self.grua_en_reposo = True
        self.grua_suspendida = False
        self.grua_en_falla = False
        self.grua_carga_adherida = False
        self.grua_trabajo_en_curso = False
        self.grua_trabajos_pendientes = 0
        self.posiciones_bloqueadas = {0: False, 1: False}
        self.posicion_trabajo_actual = None
        self.paro_emergencia = False

    def handle_command(self, cmd: str, payload: str):
        """
        Evalua cada uno de los 13 comandos remotos contra las condiciones
        estrictas de seguridad definidas en la seccion 11 del enunciado.
        """
        # 1. AbrirTalanquera: rechazar si hay vehiculo detectado bajo talanquera
        if cmd == "AbrirTalanquera":
            if self.vehiculo_bajo_talanquera:
                self._send_response("NAK", cmd, "error=Vehiculo detectado bajo talanquera")
                return
            self.talanquera_abierta = True
            self._send_response("ACK", cmd, "estado=ABIERTA")
            self.emit_event("TalanqueraEstado", "estado=ABIERTA")
            return

        # 2. CerrarTalanquera: rechazar si hay vehiculo detectado bajo talanquera
        if cmd == "CerrarTalanquera":
            if self.vehiculo_bajo_talanquera:
                self._send_response("NAK", cmd, "error=Vehiculo detectado bajo talanquera")
                return
            self.talanquera_abierta = False
            self._send_response("ACK", cmd, "estado=CERRADA")
            self.emit_event("TalanqueraEstado", "estado=CERRADA")
            return

        # 3. AbrirPuertaSalida: rechazar si hay vehiculo detectado bajo la puerta
        if cmd == "AbrirPuertaSalida":
            if self.vehiculo_bajo_puerta_salida:
                self._send_response("NAK", cmd, "error=Vehiculo detectado bajo puerta de salida")
                return
            self.puerta_salida_abierta = True
            self._send_response("ACK", cmd, "estado=ABIERTA")
            self.emit_event("PuertaSalidaEstado", "estado=ABIERTA")
            return

        # 4. AgujaRecta: rechazar si hay vehiculo sobre la aguja
        if cmd == "AgujaRecta":
            if self.vehiculo_sobre_aguja:
                self._send_response("NAK", cmd, "error=Vehiculo sobre la aguja")
                return
            self.aguja_estado = "RECTA"
            self._send_response("ACK", cmd, "posicion=RECTA")
            self.emit_event("AgujaEstado", "posicion=RECTA")
            return

        # 5. AgujaParqueo: rechazar si hay vehiculo sobre la aguja
        if cmd == "AgujaParqueo":
            if self.vehiculo_sobre_aguja:
                self._send_response("NAK", cmd, "error=Vehiculo sobre la aguja")
                return
            self.aguja_estado = "PARQUEO"
            self.vehiculo_en_parqueo = True
            self._send_response("ACK", cmd, "posicion=PARQUEO")
            self.emit_event("AgujaEstado", "posicion=PARQUEO")
            return

        # 6. AgujaLiberar: rechazar si hay vehiculo sobre la aguja o no hay vehiculo en el parqueo
        if cmd == "AgujaLiberar":
            if self.vehiculo_sobre_aguja:
                self._send_response("NAK", cmd, "error=Vehiculo sobre la aguja")
                return
            if not self.vehiculo_en_parqueo:
                self._send_response("NAK", cmd, "error=No hay vehiculo en el parqueo")
                return
            self.aguja_estado = "LIBERANDO"
            self.vehiculo_en_parqueo = False
            self._send_response("ACK", cmd, "posicion=LIBERANDO")
            self.emit_event("AgujaEstado", "posicion=LIBERANDO")
            return

        # 7. GruaReferenciar: rechazar si la grua tiene carga adherida o hay trabajo en ejecucion
        if cmd == "GruaReferenciar":
            if self.grua_carga_adherida:
                self._send_response("NAK", cmd, "error=Grua tiene carga adherida")
                return
            if self.grua_trabajo_en_curso:
                self._send_response("NAK", cmd, "error=Trabajo en ejecucion")
                return
            self.grua_referenciada = True
            self.grua_posicion_actual = 0
            self._send_response("ACK", cmd, "referenciada=SI")
            self.emit_event("GruaReferenciada", "posicion=0")
            return

        # 8. GruaSuspender: nunca se rechaza. Movimiento en curso se completa antes de suspender
        if cmd == "GruaSuspender":
            self.grua_suspendida = True
            self._send_response("ACK", cmd, "suspendida=SI")
            self.emit_event("GruaSuspendida", "suspendida=SI")
            return

        # 9. GruaReanudar: rechazar si la grua esta en estado de falla sin rearme
        if cmd == "GruaReanudar":
            if self.grua_en_falla:
                self._send_response("NAK", cmd, "error=Grua en estado de falla sin rearme")
                return
            self.grua_suspendida = False
            self._send_response("ACK", cmd, "suspendida=NO")
            self.emit_event("GruaReanudada", "suspendida=NO")
            return

        # 10. PosicionBloquear: rechazar si la posicion es origen o destino de trabajo en ejecucion
        if cmd == "PosicionBloquear":
            pos = int(payload.split("=")[-1]) if "=" in payload else 0
            if self.grua_trabajo_en_curso and self.posicion_trabajo_actual == pos:
                self._send_response("NAK", cmd, f"error=Posicion {pos} es origen o destino de trabajo en ejecucion")
                return
            self.posiciones_bloqueadas[pos] = True
            self._send_response("ACK", cmd, f"posicion={pos};bloqueada=SI")
            self.emit_event("PatioPosicionBloqueada", f"posicion={pos};bloqueada=SI")
            return

        # 11. PosicionLiberar: rechazar si la inconsistencia fisica que origino el bloqueo persiste
        if cmd == "PosicionLiberar":
            pos = int(payload.split("=")[-1]) if "=" in payload else 0
            self.posiciones_bloqueadas[pos] = False
            self._send_response("ACK", cmd, f"posicion={pos};bloqueada=NO")
            self.emit_event("PatioPosicionLiberada", f"posicion={pos};bloqueada=NO")
            return

        # 12. ModoMantenimiento: rechazar si hay trabajo de grua en ejecucion o vehiculo en transferencia
        if cmd == "ModoMantenimiento":
            activar = ("desactivar" not in payload.lower()) and (("activar" in payload.lower()) or ("valor=1" in payload.lower()) or ("activo=1" in payload.lower()))
            if self.grua_trabajo_en_curso:
                self._send_response("NAK", cmd, "error=Trabajo de grua en ejecucion")
                return
            if self.vehiculo_en_transferencia:
                self._send_response("NAK", cmd, "error=Vehiculo en zona de transferencia")
                return
            self.modo_mantenimiento = activar
            self._send_response("ACK", cmd, f"modo={'MANTENIMIENTO' if activar else 'NORMAL'}")
            self.emit_event("ModoMantenimiento", f"activo={1 if activar else 0}")
            return

        # 13. AlarmaSilenciar: nunca se rechaza
        if cmd == "AlarmaSilenciar":
            self.alarma_sonora_activa = False
            self._send_response("ACK", cmd, "silenciada=SI")
            self.emit_event("AlarmaSilenciada", "silenciada=SI")
            return

        # Comando no implementado
        self._send_response("NAK", cmd, "error=Comando desconocido en controlador")
