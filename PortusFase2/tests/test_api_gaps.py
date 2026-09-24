"""
Pruebas E2E de la API Flask para los puntos cerrados en la sesion final:
  - POST /api/turnos (validacion de levante, ventana de cita, RT04, parqueo lleno AL11)
  - Citas mutables: cancelar, reprogramar, bloquear/desbloquear franjas
  - Estado del parqueo expuesto en el stream SSE (terminal_state)
  - Matriz de permisos aplicada en servidor (rechazos 403 explicitos)
  - Servicio de mensajeria: /cita omite franjas bloqueadas
"""

import sys
import os
import unittest
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PortusFase2.server.database import init_database, get_db_connection
from PortusFase2.server import app as app_module
from PortusFase2.mensajeria.messaging_service import TransportistaMessagingService

CREDS = {
    "terminal": ("operador1", "terminal123"),
    "naviera": ("maersk", "maersk123"),
    "naviera2": ("msc", "msc123"),
    "agente": ("agente1", "agente123"),
    "autoridad": ("sat1", "sat123"),
}


def reset_operacion():
    conn = get_db_connection()
    for tabla in ("retenciones", "citas", "linea_tiempo_turno", "turnos",
                  "declaraciones", "manifiestos", "franjas_bloqueadas",
                  "alarmas", "vinculaciones_transportista"):
        conn.execute(f"DELETE FROM {tabla}")
    conn.commit()
    conn.close()


class TestApiGaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()
        app_module.app.testing = True

    def setUp(self):
        reset_operacion()
        self.cli = app_module.app.test_client()

    def _login(self, clave):
        u, p = CREDS[clave]
        r = self.cli.post("/api/login", json={"username": u, "password": p})
        self.assertEqual(r.status_code, 200, f"Fallo login {clave}: {r.get_json()}")
        return r.get_json()["user"]

    def _cadena_documental(self, contenedor="MSKU1001", transportista="trans_rapido"):
        """Manifiesto -> declaracion -> solicitud -> levante otorgado canal VERDE."""
        self.cli.post("/api/logout", json={})
        self._login("naviera")
        r = self.cli.post("/api/manifiestos", json={
            "contenedor_id": contenedor, "tipo_operacion": "DEPOSITO",
            "peso_declarado": 22000, "transportista_id": transportista})
        self.assertEqual(r.status_code, 200, r.get_json())
        manif_id = r.get_json()["id"]

        self.cli.post("/api/logout", json={})
        self._login("agente")
        r = self.cli.post("/api/declaraciones", json={
            "manifiesto_id": manif_id, "numero_declaracion": f"DEC-{manif_id}",
            "regimen": "Importacion definitiva",
            "descripcion_mercancia": "Contenedores de repuestos mecanicos",
            "valor_declarado": 15000.50})
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.cli.post("/api/declaraciones/solicitar-levante", json={"manifiesto_id": manif_id})
        self.assertEqual(r.status_code, 200, r.get_json())

        self.cli.post("/api/logout", json={})
        self._login("autoridad")
        r = self.cli.post("/api/autoridad/resolver-levante", json={
            "manifiesto_id": manif_id, "decision": "OTORGAR", "canal": "VERDE"})
        self.assertEqual(r.status_code, 200, r.get_json())

        self.cli.post("/api/logout", json={})
        self._login("terminal")
        return manif_id

    # ----------------------------------------------------------
    # POST /api/turnos
    # ----------------------------------------------------------
    def test_01_turno_rechazado_sin_levante(self):
        self.cli.post("/api/logout", json={})
        self._login("naviera")
        r = self.cli.post("/api/manifiestos", json={
            "contenedor_id": "MSKU1001", "tipo_operacion": "DEPOSITO",
            "peso_declarado": 22000, "transportista_id": "trans_rapido"})
        manif_id = r.get_json()["id"]

        self.cli.post("/api/logout", json={})
        self._login("terminal")
        r = self.cli.post("/api/turnos", json={"placa_vehiculo": "P001AAA", "manifiesto_id": manif_id})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["causa_rechazo"], "SIN_LEVANTE")

        # No se crea turno (regla de la maquina de estados)
        conn = get_db_connection()
        n = conn.execute("SELECT COUNT(*) as c FROM turnos").fetchone()["c"]
        conn.close()
        self.assertEqual(n, 0)

    def test_02_turno_dentro_de_ventana_cumple_cita(self):
        manif_id = self._cadena_documental()
        ahora = datetime.now()
        ini = (ahora - timedelta(minutes=5)).strftime("%H:%M")
        fin = (ahora + timedelta(minutes=10)).strftime("%H:%M")
        conn = get_db_connection()
        conn.execute("""INSERT INTO citas (transportista_id, contenedor_id, manifiesto_id, fecha,
                     hora_inicio, hora_fin, estado, created_at) VALUES (?,?,?,?,?,?, 'PROGRAMADA', ?)""",
                     ("trans_rapido", "MSKU1001", manif_id, ahora.strftime("%Y-%m-%d"), ini, fin, ahora.isoformat()))
        conn.commit(); conn.close()

        r = self.cli.post("/api/turnos", json={"placa_vehiculo": "P001AAA", "manifiesto_id": manif_id})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertNotIn("retencion", r.get_json())

        conn = get_db_connection()
        cita = conn.execute("SELECT * FROM citas").fetchone()
        conn.close()
        self.assertEqual(cita["estado"], "CUMPLIDA")
        self.assertEqual(cita["cumplida_en_ventana"], 1)

    def test_03_turno_fuera_de_ventana_genera_rt04(self):
        manif_id = self._cadena_documental()
        ayer = datetime.now() - timedelta(hours=6)
        conn = get_db_connection()
        conn.execute("""INSERT INTO citas (transportista_id, contenedor_id, manifiesto_id, fecha,
                     hora_inicio, hora_fin, estado, created_at) VALUES (?,?,?,?,?,?, 'PROGRAMADA', ?)""",
                     ("trans_rapido", "MSKU1001", manif_id, ayer.strftime("%Y-%m-%d"),
                      ayer.strftime("%H:%M"), (ayer + timedelta(minutes=15)).strftime("%H:%M"), ayer.isoformat()))
        conn.commit(); conn.close()

        r = self.cli.post("/api/turnos", json={"placa_vehiculo": "P001AAA", "manifiesto_id": manif_id})
        self.assertEqual(r.status_code, 200, r.get_json())
        data = r.get_json()
        self.assertIn("retencion", data)
        self.assertEqual(data["retencion"]["causa"], "RT04")
        self.assertEqual(data["retencion"]["plaza"], 1)

        # El parqueo del estado en tiempo real refleja la plaza ocupada (gap cerrado)
        self.assertIsNotNone(app_module.terminal_state["parqueo"][1])

        # El turno queda en estado Retenido
        conn = get_db_connection()
        turno = conn.execute("SELECT * FROM turnos").fetchone()
        conn.close()
        self.assertEqual(turno["estado_actual"], "Retenido")

    def test_04_parqueo_lleno_rechaza_ingreso_al11(self):
        # Ocupar las 3 plazas
        contenedores = ["MSKU1001", "MSKU1002", "MSCU2001"]
        placas = ["P001AAA", "P002BBB", "P003CCC"]
        trans = ["trans_rapido", "trans_rapido", "trans_global"]
        manif_ids = []
        for cont, plc, tr in zip(contenedores, placas, trans):
            mid = self._cadena_documental(contenedor=cont, transportista=tr)
            manif_ids.append(mid)
            r = self.cli.post("/api/turnos", json={"placa_vehiculo": plc, "manifiesto_id": mid})
            self.assertEqual(r.status_code, 200, r.get_json())  # sin cita -> RT04 -> ocupa plaza

        # Cuarto vehiculo, tambien con riesgo (sin cita) -> parqueo lleno
        mid4 = self._cadena_documental(contenedor="MSCU2002", transportista="trans_global")
        r = self.cli.post("/api/turnos", json={"placa_vehiculo": "P004DDD", "manifiesto_id": mid4})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["causa_rechazo"], "PARQUEO_LLENO")

        conn = get_db_connection()
        alarma = conn.execute("SELECT * FROM alarmas WHERE codigo = 'AL11'").fetchone()
        conn.close()
        self.assertIsNotNone(alarma)

    # ----------------------------------------------------------
    # Citas mutables (gap 1)
    # ----------------------------------------------------------
    def _crear_cita_en_franja(self, transportista="trans_rapido", contenedor="MSKU1001",
                              fecha=None, hora="10:00"):
        fecha = fecha or datetime.now().strftime("%Y-%m-%d")
        h_fin = (datetime.strptime(hora, "%H:%M") + timedelta(minutes=15)).strftime("%H:%M")
        now_iso = datetime.now().isoformat()
        conn = get_db_connection()
        # Manifiesto real por la llave foranea de citas
        n = conn.execute("SELECT COUNT(*) as c FROM manifiestos").fetchone()["c"] + 1
        manif_id = f"MAN-{n:04d}"
        conn.execute("""INSERT INTO manifiestos (id, contenedor_id, naviera_id, tipo_operacion,
                     peso_declarado_g, tolerancia_pct, transportista_id, estado_documental,
                     canal_selectivo, created_at, updated_at)
                     VALUES (?,?, 'maersk', 'DEPOSITO', 22000, 5.0, ?, 'LEVANTE_OTORGADO', 'VERDE', ?, ?)""",
                     (manif_id, contenedor, transportista, now_iso, now_iso))
        cur = conn.execute("""INSERT INTO citas (transportista_id, contenedor_id, manifiesto_id, fecha,
                     hora_inicio, hora_fin, estado, created_at) VALUES (?,?,?,?,?,?, 'PROGRAMADA', ?)""",
                     (transportista, contenedor, manif_id, fecha, hora, h_fin, now_iso))
        cid = cur.lastrowid
        conn.commit(); conn.close()
        return cid, fecha, hora

    def test_05_cancelar_cita(self):
        cid, _, _ = self._crear_cita_en_franja()
        self._login("terminal")
        r = self.cli.post(f"/api/citas/{cid}/cancelar", json={"motivo": "Reprogramacion interna"})
        self.assertEqual(r.status_code, 200, r.get_json())

        conn = get_db_connection()
        cita = conn.execute("SELECT estado FROM citas WHERE id = ?", (cid,)).fetchone()
        conn.close()
        self.assertEqual(cita["estado"], "CANCELADA")

        # No permite cancelar de nuevo
        r = self.cli.post(f"/api/citas/{cid}/cancelar", json={})
        self.assertEqual(r.status_code, 400)

    def test_06_reprogramar_cita_y_validaciones(self):
        cid, fecha, _ = self._crear_cita_en_franja(hora="10:00")
        self._login("terminal")

        # Reprogramacion valida a franja libre
        r = self.cli.post(f"/api/citas/{cid}/reprogramar", json={"fecha": fecha, "hora_inicio": "11:00"})
        self.assertEqual(r.status_code, 200, r.get_json())

        conn = get_db_connection()
        cita = conn.execute("SELECT * FROM citas WHERE id = ?", (cid,)).fetchone()
        conn.close()
        self.assertEqual(cita["hora_inicio"], "11:00")
        self.assertEqual(cita["hora_fin"], "11:15")

        # Llenar la franja 12:00 (capacidad 2) y comprobar rechazo de reprogramacion
        self._crear_cita_en_franja(contenedor="MSKU1002", hora="12:00")
        self._crear_cita_en_franja(contenedor="MSCU2001", transportista="trans_global", hora="12:00")
        r = self.cli.post(f"/api/citas/{cid}/reprogramar", json={"fecha": fecha, "hora_inicio": "12:00"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("llena", r.get_json()["error"])

        # Formato invalido
        r = self.cli.post(f"/api/citas/{cid}/reprogramar", json={"fecha": "ay", "hora_inicio": "--"})
        self.assertEqual(r.status_code, 400)

    def test_07_bloqueo_de_franja(self):
        self._login("terminal")
        fecha = datetime.now().strftime("%Y-%m-%d")

        r = self.cli.post("/api/citas/bloquear-franja", json={"fecha": fecha, "hora_inicio": "14:00"})
        self.assertEqual(r.status_code, 200, r.get_json())

        # Bloqueo doble -> error
        r = self.cli.post("/api/citas/bloquear-franja", json={"fecha": fecha, "hora_inicio": "14:00"})
        self.assertEqual(r.status_code, 400)

        # La franja bloqueada aparece en el listado
        r = self.cli.get(f"/api/citas/franjas-bloqueadas?fecha={fecha}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 1)

        # No se puede reprogramar hacia franja bloqueada
        cid, _, _ = self._crear_cita_en_franja(hora="10:00")
        r = self.cli.post(f"/api/citas/{cid}/reprogramar", json={"fecha": fecha, "hora_inicio": "14:00"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("bloqueada", r.get_json()["error"])

        # Desbloquear y verificar
        r = self.cli.post("/api/citas/desbloquear-franja", json={"fecha": fecha, "hora_inicio": "14:00"})
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.cli.get(f"/api/citas/franjas-bloqueadas?fecha={fecha}")
        self.assertEqual(len(r.get_json()), 0)

        r = self.cli.post("/api/citas/desbloquear-franja", json={"fecha": fecha, "hora_inicio": "14:00"})
        self.assertEqual(r.status_code, 400)

    def test_08_mensajeria_omite_franja_bloqueada(self):
        manif_id = self._cadena_documental()

        # Vincular transportista por servicio de mensajeria
        svc = TransportistaMessagingService()
        from PortusFase2.mensajeria.messaging_service import generate_binding_code
        code = generate_binding_code("trans_rapido", "operador1")
        resp = svc.process_message("chat_t1", f"/vincular {code}")
        self.assertIn("Vinculacion exitosa", resp)

        # Bloquear la franja inmediata siguiente (la primera que ofreceria /cita)
        ahora = datetime.now()
        franja = (ahora.replace(minute=(ahora.minute // 15) * 15, second=0, microsecond=0)
                  + timedelta(minutes=-(ahora.minute % 15) + 15))
        # Corregir calculo: proxima franja con inicio > ahora
        base = ahora.replace(second=0, microsecond=0)
        inicio = base + timedelta(minutes=(15 - base.minute % 15))
        h_ini = inicio.strftime("%H:%M")
        h_fin = (inicio + timedelta(minutes=15)).strftime("%H:%M")
        fecha = ahora.strftime("%Y-%m-%d")

        conn = get_db_connection()
        conn.execute("""INSERT INTO franjas_bloqueadas (fecha, hora_inicio, hora_fin, creado_por, created_at)
                     VALUES (?,?,?,?,?)""", (fecha, h_ini, h_fin, "operador1", datetime.now().isoformat()))
        conn.commit(); conn.close()

        resp = svc.process_message("chat_t1", "/cita MSKU1001")
        self.assertIn("Cita confirmada", resp)
        self.assertNotIn(h_ini, resp.split("Ventana de atencion:")[1][:6],
                         "El servicio ofrecio una franja bloqueada")

    # ----------------------------------------------------------
    # Matriz de permisos en servidor (E12)
    # ----------------------------------------------------------
    def test_09_permisos_rechazados_en_servidor(self):
        self._login("naviera")
        # NAVIERA intenta emitir comando remoto
        r = self.cli.post("/api/cmd/remote", json={"comando": "AbrirTalanquera"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())
        # NAVIERA intenta crear turno
        r = self.cli.post("/api/turnos", json={"placa_vehiculo": "P001AAA", "manifiesto_id": "MAN-0001"})
        self.assertEqual(r.status_code, 403)
        # NAVIERA intenta gestionar agenda completa
        r = self.cli.post("/api/citas/bloquear-franja", json={"fecha": "2026-09-23", "hora_inicio": "10:00"})
        self.assertEqual(r.status_code, 403)

        # TRANSPORTISTA no puede entrar a la web
        r = self.cli.post("/api/login", json={"username": "trans_rapido", "password": "trans123"})
        self.assertEqual(r.status_code, 403)

    def test_10_aislamiento_entre_navieras(self):
        self._login("naviera")
        r = self.cli.post("/api/manifiestos", json={
            "contenedor_id": "MSKU1001", "tipo_operacion": "DEPOSITO",
            "peso_declarado": 22000, "transportista_id": "trans_rapido"})
        self.assertEqual(r.status_code, 200)

        self.cli.post("/api/logout", json={})
        self._login("naviera2")
        r = self.cli.get("/api/manifiestos")
        ids = [m["contenedor_id"] for m in r.get_json()]
        self.assertNotIn("MSKU1001", ids, "MSC vio el manifiesto de Maersk")

    def test_11_resolucion_retencion_solo_rol_facultado(self):
        manif_id = self._cadena_documental()
        ayer = datetime.now() - timedelta(hours=6)
        conn = get_db_connection()
        conn.execute("""INSERT INTO citas (transportista_id, contenedor_id, manifiesto_id, fecha,
                     hora_inicio, hora_fin, estado, created_at) VALUES (?,?,?,?,?,?, 'PROGRAMADA', ?)""",
                     ("trans_rapido", "MSKU1001", manif_id, ayer.strftime("%Y-%m-%d"),
                      ayer.strftime("%H:%M"), (ayer + timedelta(minutes=15)).strftime("%H:%M"), ayer.isoformat()))
        conn.commit(); conn.close()

        r = self.cli.post("/api/turnos", json={"placa_vehiculo": "P001AAA", "manifiesto_id": manif_id})
        ret_id = r.get_json()["retencion"]["id"] if "id" in r.get_json().get("retencion", {}) else None

        conn = get_db_connection()
        ret = conn.execute("SELECT id FROM retenciones ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        rid = ret["id"]

        # AUTORIDAD intenta resolver una retencion operativa (RT04 es facultad de TERMINAL)
        self.cli.post("/api/logout", json={})
        self._login("autoridad")
        r = self.cli.post(f"/api/retenciones/{rid}/resolver", json={"resolucion": "ACLARAR"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("no esta facultado", r.get_json()["error"])

        # TERMINAL resuelve con Aclarar
        self.cli.post("/api/logout", json={})
        self._login("terminal")
        r = self.cli.post(f"/api/retenciones/{rid}/resolver", json={"resolucion": "ACLARAR", "observacion": "Verificado manual"})
        self.assertEqual(r.status_code, 200, r.get_json())

        # Doble resolucion rechazada
        r = self.cli.post(f"/api/retenciones/{rid}/resolver", json={"resolucion": "ACLARAR"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
