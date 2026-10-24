"""Crea una base AISLADA de demostracion; no modifica portus_hardware.db."""

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "PortusFase2" / "server" / "portus_demo.db")
    args = parser.parse_args()
    db = args.db.expanduser().resolve()
    hardware = (ROOT / "PortusFase2" / "server" / "portus_hardware.db").resolve()
    if db == hardware or db.name == "portus_hardware.db":
        parser.error("No se permite usar la base de hardware real.")
    if db.exists():
        parser.error(f"La base ya existe: {db}. Use otra ruta para una demostracion nueva.")
    db.parent.mkdir(parents=True, exist_ok=True)
    os.environ["PORTUS_DB_PATH"] = str(db)
    os.environ["PORTUS_DEMO_DATA"] = "true"

    from PortusFase2.server.database import init_database, get_db_connection
    init_database()
    conn = get_db_connection()
    try:
        conn.execute("""INSERT INTO fase3_lecturas
            (timestamp,temperatura,humedad,lluvia,luz,origen)
            VALUES (datetime('now'),27.2,68.0,0,72.0,'SIMULACION')""")
        conn.execute("""INSERT INTO fase3_cola(timestamp,cantidad)
            VALUES (datetime('now'),2)""")
        conn.execute("""INSERT INTO fase3_accesos
            (timestamp,rfid_uid,placa_leida,confianza,placa_esperada,resultado)
            VALUES (datetime('now'),'39BB16B3','P001AAA',92,'P001AAA',
            'PLACA VERIFICADA - SIMULACION')""")
        conn.execute("""INSERT INTO fase3_accesos
            (timestamp,rfid_uid,placa_leida,confianza,placa_esperada,resultado)
            VALUES (datetime('now'),'D9D87BD3','P999ZZZ',87,'P002BBB',
            'PLACA NO COINCIDE - SIMULACION')""")
        conn.execute("""INSERT INTO alarmas
            (codigo,severidad,descripcion,origen,timestamp)
            VALUES ('AL20','Media','DEMO SIMULADA: placa no coincide',
            'SIMULACION',datetime('now'))""")
        conn.execute("""INSERT INTO fase3_placas_restringidas
            (placa,motivo,usuario_alta,alta_at)
            VALUES ('C999ZZZ','DEMO SIMULADA: restriccion de prueba',
            'sat1',datetime('now'))""")
        conn.execute(
            "INSERT INTO fase3_auditoria(timestamp,usuario,accion,datos) "
            "VALUES (datetime('now'),'demo','datos_simulados',?)",
            ('{"origen":"SIMULACION","uso":"demostracion; no es lectura fisica"}',),
        )
        conn.commit()
        counts = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("usuarios", "manifiestos", "declaraciones", "citas", "turnos",
                               "grua_ciclos", "fase3_lecturas", "fase3_accesos", "alarmas")}
    finally:
        conn.close()
    print(f"Base de demostracion SIMULADA creada: {db}")
    print("Registros:", counts)
    print("Para verla, detenga el servidor real y ejecute en la Raspberry:")
    print(f"PORTUS_DB_PATH='{db}' PORTUS_DEMO_DATA=true python3 PortusFase2/run_fase2.py --mock")
    print("El dashboard mostrara modo simulado. No use esta base como evidencia de hardware real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
