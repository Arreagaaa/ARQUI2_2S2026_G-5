"""
Suite de pruebas de integracion automatizadas para PORTUS Fase 2.
Verifica:
  - Protocolo serial delimitado con CRC16
  - Autenticacion y matriz de permisos por rol
  - Maquina de estados del turno (10 estados)
  - Parqueo de retencion (3 plazas, RT01-RT06, resoluciones)
  - Calculo de las 8 metricas de operacion
  - Servicio de mensajeria del transportista
"""

import sys
import os
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PortusFase2.bridge.serial_protocol import SerialProtocol
from PortusFase2.server.database import init_database, get_db_connection
from PortusFase2.server.auth import authenticate_user, PERMISOS_MATRIZ
from PortusFase2.server.turn_manager import create_turn, transition_turn, get_turn_timeline
from PortusFase2.server.retention_manager import (
    assign_retention, resolve_retention, get_parking_occupancy
)
from PortusFase2.server.metrics import calculate_metrics
from PortusFase2.mensajeria.messaging_service import (
    TransportistaMessagingService, generate_binding_code
)


class TestPortusFase2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def setUp(self):
        conn = get_db_connection()
        conn.execute("DELETE FROM retenciones")
        conn.execute("DELETE FROM citas")
        conn.execute("DELETE FROM linea_tiempo_turno")
        conn.execute("DELETE FROM turnos")
        conn.execute("DELETE FROM vinculaciones_transportista")
        conn.commit()
        conn.close()

    def test_01_serial_protocol(self):
        # Generar trama
        frame = SerialProtocol.build_frame(42, "EVT", "GaritaIdentificacion", "uid=A1B2C3D4")
        self.assertTrue(frame.startswith("["))
        self.assertTrue(frame.endswith("]\n"))

        # Parsear trama valida
        parsed = SerialProtocol.parse_frame(frame)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["seq"], 42)
        self.assertEqual(parsed["tipo"], "EVT")
        self.assertEqual(parsed["cmd"], "GaritaIdentificacion")
        self.assertIn("uid=A1B2C3D4", parsed["payload"])

        # Trama corrompida
        corrupt_frame = frame.replace("A1B2", "XXXX")
        parsed_corrupt = SerialProtocol.parse_frame(corrupt_frame)
        self.assertFalse(parsed_corrupt["valid"])

    def test_02_authentication_and_roles(self):
        # Operador terminal
        user_term = authenticate_user("operador1", "terminal123")
        self.assertIsNotNone(user_term)
        self.assertEqual(user_term["rol"], "TERMINAL")

        # Naviera 1
        user_nav1 = authenticate_user("maersk", "maersk123")
        self.assertIsNotNone(user_nav1)
        self.assertEqual(user_nav1["rol"], "NAVIERA")

        # Clave erronea
        self.assertIsNone(authenticate_user("operador1", "clave_invalida"))

        # Validacion de permisos
        self.assertIn("TERMINAL", PERMISOS_MATRIZ["emitir_comandos_remotos"])
        self.assertNotIn("NAVIERA", PERMISOS_MATRIZ["emitir_comandos_remotos"])
        self.assertNotIn("AGENTE", PERMISOS_MATRIZ["emitir_comandos_remotos"])
        self.assertIn("NAVIERA", PERMISOS_MATRIZ["crear_manifiesto"])
        self.assertNotIn("TERMINAL", PERMISOS_MATRIZ["crear_manifiesto"])

    def test_03_turn_fsm_and_timeline(self):
        # Crear turno
        turno_id = create_turn(
            placa="P001AAA",
            transportista_id="trans_rapido",
            contenedor_id="MSKU1001",
            tipo_operacion="DEPOSITO",
            peso_declarado_g=22000
        )
        self.assertIsNotNone(turno_id)

        # Transicion EnGarita -> EnPesajeEntrada
        ok = transition_turn(turno_id, "EnPesajeEntrada", estacion="PESAJE")
        self.assertTrue(ok)

        # Transicion EnPesajeEntrada -> EnRuta
        ok = transition_turn(turno_id, "EnRuta", estacion="RUTA")
        self.assertTrue(ok)

        # Transicion invalida (ej. EnRuta a Cerrado sin pasar por transferencia)
        ok_invalido = transition_turn(turno_id, "Cerrado")
        self.assertFalse(ok_invalido)

        # Verificar linea de tiempo
        timeline = get_turn_timeline(turno_id)
        self.assertGreaterEqual(len(timeline), 3)

    def test_04_retention_and_3_slots(self):
        turno_id = create_turn(
            placa="P002BBB",
            transportista_id="trans_rapido",
            contenedor_id="MSKU1002",
            tipo_operacion="DEPOSITO",
            peso_declarado_g=24000
        )

        # Asignar retencion por peso alterado (RT01)
        ret = assign_retention(
            turno_id=turno_id,
            causa="RT01",
            estacion="PESAJE",
            peso_declarado_g=24000,
            peso_medido_g=28000
        )
        self.assertIsNotNone(ret)
        self.assertEqual(ret["plaza"], 1)

        # Resolver mediante CORREGIR (solo TERMINAL)
        res_fail = resolve_retention(
            retencion_id=ret["id"],
            resolucion="CORREGIR",
            usuario="agente1",
            rol_usuario="AGENTE"
        )
        self.assertFalse(res_fail["success"])  # Agente no puede corregir peso

        res_ok = resolve_retention(
            retencion_id=ret["id"],
            resolucion="CORREGIR",
            usuario="operador1",
            rol_usuario="TERMINAL",
            observacion="Peso verificado en bascula dinamica"
        )
        self.assertTrue(res_ok["success"])

    def test_05_messaging_service(self):
        svc = TransportistaMessagingService()

        # Generar codigo
        code = generate_binding_code("trans_rapido", "operador1")
        self.assertEqual(len(code), 6)

        # Comando no autenticado
        resp_unauth = svc.process_message("chat_99", "/misturnos")
        self.assertIn("Acceso no autorizado", resp_unauth)

        # Vincular cuenta
        resp_vinc = svc.process_message("chat_99", f"/vincular {code}")
        self.assertIn("Vinculacion exitosa", resp_vinc)

        # Comandos autenticados
        resp_turnos = svc.process_message("chat_99", "/misturnos")
        self.assertIn("operaciones activas", resp_turnos)

        resp_help = svc.process_message("chat_99", "/ayuda")
        self.assertIn("Lista de comandos", resp_help)

    def test_06_metrics_calculation(self):
        m = calculate_metrics()
        self.assertIn("remociones_por_contenedor_retirado", m)
        self.assertIn("ciclos_grua_por_operacion", m)
        self.assertIn("distancia_total_grua_m", m)
        self.assertIn("tiempo_promedio_camion_seg", m)
        self.assertIn("tiempo_promedio_retencion_seg", m)
        self.assertIn("longitud_maxima_fila_espera", m)
        self.assertIn("porcentaje_citas_cumplidas_ventana", m)
        self.assertIn("retenciones_desglose", m)


if __name__ == "__main__":
    unittest.main()
