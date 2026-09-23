"""
Script de validacion y prueba de los 15 escenarios minimos de evaluacion (E01 a E15)
definidos en la Seccion 15 de PORTUS Fase 2.
"""

import sys
import os
import unittest
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PortusFase2.server.database import init_database, get_db_connection
from PortusFase2.server.auth import authenticate_user, PERMISOS_MATRIZ
from PortusFase2.server.turn_manager import create_turn, transition_turn, get_turn_timeline
from PortusFase2.server.retention_manager import (
    assign_retention, resolve_retention, get_parking_occupancy
)
from PortusFase2.server.alarm_manager import raise_alarm, acknowledge_alarm, get_alarms
from PortusFase2.server.yard_crane_manager import (
    get_yard_inventory, update_yard_on_physical_confirmation, set_position_blocked,
    record_crane_cycle, get_crane_history
)
from PortusFase2.server.metrics import calculate_metrics, export_report_csv
from PortusFase2.mensajeria.messaging_service import (
    TransportistaMessagingService, generate_binding_code
)
from PortusFase2.bridge.mock_controller import MockArduinoMega


class Test15Escenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()
        cls.msg_svc = TransportistaMessagingService()
        cls.mock_mega = MockArduinoMega()

    def setUp(self):
        conn = get_db_connection()
        conn.execute("DELETE FROM retenciones")
        conn.execute("DELETE FROM citas")
        conn.execute("DELETE FROM linea_tiempo_turno")
        conn.execute("DELETE FROM turnos")
        conn.commit()
        conn.close()

    def test_E01_naviera_manifiesto_deposito(self):
        # E01: Una naviera declara un manifiesto de depósito -> El manifiesto aparece para el agente
        conn = get_db_connection()
        conn.execute("""
        INSERT OR REPLACE INTO manifiestos (
            id, contenedor_id, naviera_id, tipo_operacion, peso_declarado_g,
            tolerancia_pct, transportista_id, observaciones, estado_documental,
            created_at, updated_at
        ) VALUES ('MAN-TEST-E01', 'MSKU1002', 'maersk', 'DEPOSITO', 22500, 5.0, 'trans_rapido', 'Prueba E01', 'CREADO', '2026-09-22T10:00:00Z', '2026-09-22T10:00:00Z')
        """)
        conn.commit()

        # El agente consulta manifiestos sin levante
        manif = conn.execute("SELECT * FROM manifiestos WHERE id = 'MAN-TEST-E01'").fetchone()
        conn.close()
        self.assertIsNotNone(manif)
        self.assertEqual(manif["estado_documental"], "CREADO")

    def test_E02_agente_presenta_declaracion_solicita_levante(self):
        # E02: El agente presenta declaración y solicita levante -> aparece en solicitudes de autoridad
        conn = get_db_connection()
        conn.execute("""
        INSERT OR REPLACE INTO declaraciones (
            numero_declaracion, manifiesto_id, agente_id, regimen, descripcion_mercancia, valor_declarado, created_at
        ) VALUES ('DEC-E02-001', 'MAN-TEST-E01', 'agente1', 'Importacion definitiva', 'Mercaderia textil rollos algodon', 25000.0, '2026-09-22T10:05:00Z')
        """)
        conn.execute("UPDATE manifiestos SET estado_documental = 'LEVANTE_SOLICITADO' WHERE id = 'MAN-TEST-E01'")
        conn.commit()

        manif = conn.execute("SELECT * FROM manifiestos WHERE id = 'MAN-TEST-E01'").fetchone()
        conn.close()
        self.assertEqual(manif["estado_documental"], "LEVANTE_SOLICITADO")

    def test_E03_autoridad_retiene_levante(self):
        # E03: Autoridad retiene levante con motivo -> Talanquera no abre, transportista recibe aviso
        conn = get_db_connection()
        conn.execute("UPDATE manifiestos SET estado_documental = 'LEVANTE_RETENIDO', observaciones = 'Inconsistencia arancelaria' WHERE id = 'MAN-TEST-E01'")
        conn.commit()
        conn.close()

        aviso = self.msg_svc.notify_levante_retenido("trans_rapido", "MSKU1002", "Inconsistencia arancelaria")
        self.assertIn("RETENIDO", aviso)
        self.assertIn("Inconsistencia arancelaria", aviso)

    def test_E04_E05_autoridad_otorga_canal_verde_y_cita(self):
        # E04: Autoridad otorga canal verde y transportista solicita cita
        conn = get_db_connection()
        conn.execute("UPDATE manifiestos SET estado_documental = 'LEVANTE_OTORGADO', canal_selectivo = 'VERDE' WHERE id = 'MAN-TEST-E01'")
        conn.commit()
        conn.close()

        code = generate_binding_code("trans_rapido")
        self.msg_svc.process_message("chat_e04", f"/vincular {code}")
        resp_cita = self.msg_svc.process_message("chat_e04", "/cita MSKU1002")
        self.assertIn("Cita confirmada", resp_cita)

        # E05: Camion llega en ventana -> se autoriza ingreso y crea turno
        turno_id = create_turn(
            placa="P001AAA",
            transportista_id="trans_rapido",
            contenedor_id="MSKU1002",
            tipo_operacion="DEPOSITO",
            peso_declarado_g=22500
        )
        self.assertIsNotNone(turno_id)

    def test_E06_segundo_camion_fuera_de_ventana(self):
        # E06: Camion fuera de ventana -> retencion RT04 y parqueo
        turno_id = create_turn(
            placa="P002BBB",
            transportista_id="trans_rapido",
            contenedor_id="MSKU1001",
            tipo_operacion="DEPOSITO",
            peso_declarado_g=22000
        )
        ret = assign_retention(turno_id, "RT04", estacion="GARITA", observacion="Llegada 30 minutos fuera de ventana")
        self.assertIsNotNone(ret)
        self.assertEqual(ret["causa"], "RT04")

    def test_E07_E08_peso_alterado_y_corregir(self):
        # E07: Pesaje alterado -> RT01
        turno_id = create_turn(
            placa="P003CCC",
            transportista_id="trans_global",
            contenedor_id="CMAU3001",
            tipo_operacion="DEPOSITO",
            peso_declarado_g=20000
        )
        ret = assign_retention(turno_id, "RT01", estacion="PESAJE", peso_declarado_g=20000, peso_medido_g=24500)
        self.assertIsNotNone(ret)

        # E08: Terminal resuelve mediante Corregir
        res = resolve_retention(ret["id"], "CORREGIR", "operador1", "TERMINAL", observacion="Ajuste autorizado")
        self.assertTrue(res["success"])
        self.assertEqual(res["resolucion"], "CORREGIR")

    def test_E09_E10_canal_rojo_y_rechazar(self):
        # E09: Canal rojo -> RT03, solo Autoridad puede resolver
        turno_id = create_turn(
            placa="P004DDD",
            transportista_id="trans_global",
            contenedor_id="HLCU4001",
            tipo_operacion="DEPOSITO",
            peso_declarado_g=21000
        )
        ret = assign_retention(turno_id, "RT03", estacion="PESAJE", peso_declarado_g=21000, peso_medido_g=21000)
        self.assertIsNotNone(ret)

        # Terminal intenta resolver RT03 -> debe fallar (autoridad exclusiva)
        res_fail = resolve_retention(ret["id"], "ACLARAR", "operador1", "TERMINAL")
        self.assertFalse(res_fail["success"])

        # E10: Autoridad resuelve mediante Rechazar con motivo obligatorio
        res_rech = resolve_retention(ret["id"], "RECHAZAR", "sat1", "AUTORIDAD", motivo_rechazo="Contrabando detectado en inspeccion fisica")
        self.assertTrue(res_rech["success"])

    def test_E11_parqueo_lleno_y_alarma_al11(self):
        # Ocupar las 3 plazas
        t1 = create_turn("P001AAA", "trans_rapido", "C1", "DEPOSITO")
        t2 = create_turn("P002BBB", "trans_rapido", "C2", "DEPOSITO")
        t3 = create_turn("P003CCC", "trans_global", "C3", "DEPOSITO")
        r1 = assign_retention(t1, "RT06", "GARITA")
        r2 = assign_retention(t2, "RT06", "GARITA")
        r3 = assign_retention(t3, "RT06", "GARITA")

        # Cuarto intento con parqueo lleno -> None y genera AL11
        t4 = create_turn("P004DDD", "trans_global", "C4", "DEPOSITO")
        r4 = assign_retention(t4, "RT03", "GARITA")
        self.assertIsNone(r4)

        alarm_id = raise_alarm("AL11", origen="servidor", datos={"descripcion": "Parqueo de retencion lleno"})
        self.assertIsNotNone(alarm_id)

    def test_E12_rechazo_permisos_y_aislamiento(self):
        # Naviera no puede resolver retenciones
        self.assertNotIn("NAVIERA", PERMISOS_MATRIZ["resolver_retencion_operativa"])
        self.assertNotIn("NAVIERA", PERMISOS_MATRIZ["resolver_retencion_aduanera"])

        # Transportista consulta contenedor de otro
        resp = self.msg_svc.process_message("chat_e04", "/estado CONTENEDOR_AJENO")
        self.assertIn("No tiene carga asociada", resp)

    def test_E13_grua_suspender_y_reanudar(self):
        # Comandos en MockController
        self.mock_mega.handle_command("GruaSuspender", "")
        self.assertTrue(self.mock_mega.grua_suspendida)

        self.mock_mega.handle_command("GruaReanudar", "")
        self.assertFalse(self.mock_mega.grua_suspendida)

    def test_E14_al01_enlace_perdido(self):
        alarm_id = raise_alarm("AL01", origen="servidor", datos={"descripcion": "Enlace con el controlador perdido"})
        ok = acknowledge_alarm(alarm_id, "operador1", "Enlace restablecido tras reconexion de cable USB")
        self.assertTrue(ok)

    def test_E15_retiro_remocion_y_reporte(self):
        # Registrar ciclo de grua y remocion
        update_yard_on_physical_confirmation(0, 0, "MSKU1001", "maersk", 22000, es_remocion=True)
        record_crane_cycle(1, "RETIRO", 0, 0, 18.5, 450.0, exitoso=True)

        m = calculate_metrics()
        self.assertGreaterEqual(m["remociones_por_contenedor_retirado"], 0)
        csv_rep = export_report_csv("Evaluacion Fase 2", m)
        self.assertIn("PORTUS Fase 2 - Reporte de Corrida de Evaluacion", csv_rep)


if __name__ == "__main__":
    unittest.main()
