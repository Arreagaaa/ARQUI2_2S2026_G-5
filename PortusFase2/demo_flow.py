"""Prueba de respaldo del controlador SIMULADO; nunca abre el puerto serial."""

from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PortusFase2.bridge.mock_controller import MockArduinoMega
from PortusFase2.bridge.serial_protocol import SerialProtocol


def main() -> int:
    responses = []
    controller = MockArduinoMega(on_tx_callback=responses.append)
    sequence = 1

    def command(name: str, payload: str = "", expected: str = "ACK") -> None:
        nonlocal sequence
        responses.clear()
        controller.process_incoming_line(
            SerialProtocol.build_frame(sequence, "CMD", name, payload)
        )
        sequence += 1
        parsed = [SerialProtocol.parse_frame(line) for line in responses]
        result = next((item for item in parsed if item and item["cmd"] == name
                       and item["tipo"] in ("ACK", "NAK")), None)
        if not result or result["tipo"] != expected:
            raise RuntimeError(f"{name}: se esperaba {expected}; recibido {result}")
        print(f"{name}: {result['tipo']} {result['payload']}")

    print("MODO SIMULADO: no se accionan grua, iman, servos ni sensores fisicos.")
    command("AbrirTalanquera")
    controller.vehiculo_bajo_talanquera = True
    command("CerrarTalanquera", expected="NAK")
    controller.vehiculo_bajo_talanquera = False
    command("CerrarTalanquera")
    command("AgujaParqueo")
    command("AgujaLiberar")
    command("AgujaRecta")
    command("GruaReferenciar")
    command("GruaSuspender")
    command("GruaReanudar")
    controller.vehiculo_en_transferencia = True
    command("ModoMantenimiento", "activar=1", expected="NAK")
    controller.vehiculo_en_transferencia = False
    command("ModoMantenimiento", "activar=1")
    command("ModoMantenimiento", "desactivar=1")
    with tempfile.TemporaryDirectory(prefix="portus-demo-flow-") as directory:
        os.environ["PORTUS_DB_PATH"] = str(Path(directory) / "flow.db")
        os.environ["PORTUS_DEMO_DATA"] = "false"
        from PortusFase2.server.database import init_database, get_db_connection
        from PortusFase2.server.turn_manager import create_turn, transition_turn
        from PortusFase2.server.yard_crane_manager import record_crane_cycle

        init_database()
        turn_id = create_turn("P001AAA", "trans_rapido", "CT-001", "DEPOSITO")
        path = [
            ("EnPesajeEntrada", "PESAJE"), ("EnRuta", "RUTA"),
            ("EnTransferencia", "TRANSFERENCIA"),
            ("EnPesajeSalida", "PESAJE"), ("EnSalida", "SALIDA"),
            ("Cerrado", "SALIDA"),
        ]
        for state, station in path:
            if not transition_turn(turn_id, state, estacion=station,
                                   detalle="SIMULACION: transicion de demostracion"):
                raise RuntimeError(f"Transicion simulada fallida: {state}")
            print(f"Turno simulado -> {state}")
        record_crane_cycle(turn_id, "DESCARGA_CAMION_A_PATIO", 0, 1,
                           19.4, 850.0)
        conn = get_db_connection()
        try:
            final = conn.execute("SELECT estado_actual FROM turnos WHERE id=?", (turn_id,)).fetchone()[0]
            cycles = conn.execute("SELECT COUNT(*) FROM grua_ciclos WHERE turno_id=?", (turn_id,)).fetchone()[0]
            if final != "Cerrado" or cycles != 1:
                raise RuntimeError("El flujo simulado no cerro correctamente")
        finally:
            conn.close()
    print("Prueba simulada de aceptaciones y rechazos: OK")
    print("Movimiento de grua e iman: no probado por este simulador.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
