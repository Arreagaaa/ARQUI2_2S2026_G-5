"""Reglas de fase 3 sin camara ni sensores simulados como evidencia fisica."""
import os
import tempfile
import unittest
from unittest.mock import patch

from PortusFase2.server import database, fase3


class Fase3Logic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = database.DB_PATH
        database.DB_PATH = os.path.join(self.tmp.name, "portus.db")
        database.init_database()

    def tearDown(self):
        database.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_thresholds_and_plate_ambiguity(self):
        with self.assertRaises(ValueError):
            fase3.set_params({"UmbralLuzEncendido": 42, "UmbralLuzApagado": 45})
        self.assertEqual(fase3.match_plate("C123ABD", ["C123ABC"]), "C123ABC")
        self.assertIsNone(fase3.match_plate("C123ABD", ["C123ABC", "C123ABE"]))

    def test_rain_finishes_current_job_and_recovers_after_dry_interval(self):
        published = []
        runtime = fase3.Runtime(lambda topic, data: published.append((topic, data)), lambda *_: None)
        reading = {"temperatura": 27, "humedad": 70, "lluvia": True, "luz": 20}
        runtime.ingest("portus/estacion/lectura", reading)
        self.assertTrue(runtime.suspended_since)
        self.assertEqual(sum(d.get("comando") == "GruaSuspender" for _, d in published), 1)
        runtime.ingest("portus/estacion/lectura", reading)
        self.assertEqual(sum(d.get("comando") == "GruaSuspender" for _, d in published), 1)
        runtime.ingest("portus/estacion/lectura", {**reading, "lluvia": False, "luz": 50})
        self.assertTrue(runtime.dry_since)
        self.assertEqual(sum(d.get("comando") == "GruaReanudar" for _, d in published), 0)
        runtime.last_heartbeat = None
        self.assertTrue(runtime.suspended_since)

    def test_failed_reading_cannot_keep_station_online(self):
        published = []
        runtime = fase3.Runtime(lambda topic, data: published.append((topic, data)), lambda *_: None)
        runtime.ingest("portus/estacion/lectura", {"temperatura": 27, "humedad": 70, "lluvia": False, "luz": 20})
        self.assertTrue(runtime.station_online)
        runtime.ingest("portus/estacion/estado", {"estado": "FALLO_LECTURA"})
        self.assertFalse(runtime.station_online)
        self.assertEqual(runtime.snapshot()["lloviendo"], None)
        self.assertTrue(any(data.get("comando") == "IluminacionEncender" for _, data in published))

    def test_restricted_plate_has_priority_and_unknown_card_is_denied(self):
        conn = database.get_db_connection()
        try:
            conn.execute("INSERT INTO catalogo_camiones(placa,transportista_id,tara_g,rfid_uid,activo) VALUES (?,?,?,?,1)",
                         ("C123ABC", "trans_rapido", 100, "AABBCCDD"))
            conn.execute("INSERT INTO fase3_placas_restringidas(placa,motivo,usuario_alta,alta_at) VALUES (?,?,?,?)",
                         ("C123ABC", "Inspeccion aduanera", "sat1", fase3.now()))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(fase3.verify_plate("AABBCCDD", "C123ABC", 95)["resultado"], "PLACA RESTRINGIDA")
        self.assertEqual(fase3.verify_plate("00000000", "C123ABC", 95)["resultado"], "ACCESO DENEGADO")

    def test_late_ocr_result_cannot_answer_another_vehicle_access(self):
        from PortusFase2.server import app as app_module

        conn = database.get_db_connection()
        try:
            conn.execute("INSERT INTO catalogo_camiones(placa,transportista_id,tara_g,rfid_uid,activo) VALUES (?,?,?,?,1)",
                         ("C123ABC", "trans_rapido", 100, "AABBCCDD"))
            conn.execute("INSERT INTO catalogo_camiones(placa,transportista_id,tara_g,rfid_uid,activo) VALUES (?,?,?,?,1)",
                         ("C456DEF", "trans_rapido", 100, "11223344"))
            pending = conn.execute("INSERT INTO fase3_accesos(timestamp,rfid_uid,resultado) VALUES (?,?,?)",
                                   (fase3.now(), "11223344", "LEYENDO PLACA")).lastrowid
            conn.commit()
        finally:
            conn.close()

        old_gate = app_module.fase3_runtime.gate_enabled
        old_pending = app_module.fase3_runtime.pending_access_id
        old_since = app_module.fase3_runtime.pending_since
        app_module.fase3_runtime.gate_enabled = True
        app_module.fase3_runtime.pending_access_id = pending
        app_module.fase3_runtime.pending_since = 1.0
        try:
            with patch.object(app_module.fase3_runtime, "command") as command:
                app_module._fase3_record_plate({"uid": "AABBCCDD", "intentos": [
                    {"placa": "C123ABC", "confianza": 95, "foto": ""}]})
                command.assert_not_called()
            self.assertEqual(app_module.fase3_runtime.pending_access_id, pending)
            conn = database.get_db_connection()
            try:
                row = conn.execute("SELECT resultado,rfid_uid FROM fase3_accesos WHERE id=?", (pending,)).fetchone()
                self.assertEqual((row["resultado"], row["rfid_uid"]), ("LEYENDO PLACA", "11223344"))
            finally:
                conn.close()
        finally:
            app_module.fase3_runtime.gate_enabled = old_gate
            app_module.fase3_runtime.pending_access_id = old_pending
            app_module.fase3_runtime.pending_since = old_since

    def test_old_manual_decision_cannot_answer_current_access(self):
        from PortusFase2.server import app as app_module

        conn = database.get_db_connection()
        try:
            old_id = conn.execute("INSERT INTO fase3_accesos(timestamp,rfid_uid,resultado) VALUES (?,?,?)",
                                  (fase3.now(), "AABBCCDD", "VERIFICACION MANUAL")).lastrowid
            current_id = conn.execute("INSERT INTO fase3_accesos(timestamp,rfid_uid,resultado) VALUES (?,?,?)",
                                      (fase3.now(), "11223344", "MODO DEGRADADO")).lastrowid
            conn.commit()
        finally:
            conn.close()
        old_gate = app_module.fase3_runtime.gate_enabled
        old_pending = app_module.fase3_runtime.pending_access_id
        app_module.fase3_runtime.gate_enabled = True
        app_module.fase3_runtime.pending_access_id = current_id
        try:
            client = app_module.app.test_client()
            with client.session_transaction() as session:
                session["user"] = {"username": "operador", "rol": "TERMINAL"}
            with patch.object(app_module.fase3_runtime, "command") as command:
                response = client.post(f"/api/fase3/accesos/{old_id}/decision",
                                       json={"decision": "CONFIRMAR", "motivo": "Revision manual completa"})
                self.assertEqual(response.status_code, 409)
                command.assert_not_called()
                response = client.post(f"/api/fase3/accesos/{current_id}/decision",
                                       json={"decision": "CONFIRMAR", "motivo": "Revision manual completa"})
                self.assertEqual(response.status_code, 200)
                command.assert_called_once_with("GaritaResultado", resultado="AUTORIZAR", placa="")
            conn = database.get_db_connection()
            try:
                self.assertEqual(conn.execute("SELECT resultado FROM fase3_accesos WHERE id=?", (old_id,)).fetchone()[0],
                                 "VERIFICACION MANUAL")
            finally:
                conn.close()
        finally:
            app_module.fase3_runtime.gate_enabled = old_gate
            app_module.fase3_runtime.pending_access_id = old_pending


if __name__ == "__main__":
    unittest.main()
