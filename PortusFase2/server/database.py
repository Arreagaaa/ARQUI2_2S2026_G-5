"""
Modelo de base de datos SQLite y migracion inicial para PORTUS Fase 2.
Gestiona usuarios, permisos, manifiestos, declaraciones, turnos, linea de tiempo,
retenciones, parqueo de 3 plazas, alarmas AL01-AL14, inventario de patio y citas.
"""

import sqlite3
import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get("PORTUS_DB_PATH", os.path.join(os.path.dirname(__file__), "portus_fase2.db"))


def hash_password(password: str) -> str:
    # Hash seguro SHA-256 con salt fijo para la plataforma
    salt = "portus_usac_arqui2_2026"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL permite lecturas concurrentes mientras un hilo escribe (servidor multihilo)
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_database():
    conn = get_db_connection()
    c = conn.cursor()

    # 1. Tabla de Usuarios
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nombre_completo TEXT NOT NULL,
        rol TEXT NOT NULL CHECK (rol IN ('TERMINAL', 'NAVIERA', 'AGENTE', 'AUTORIDAD', 'TRANSPORTISTA')),
        created_at TEXT NOT NULL
    );
    """)

    # 2. Catalogo de Contenedores y Camiones de la maqueta
    c.execute("""
    CREATE TABLE IF NOT EXISTS catalogo_contenedores (
        id TEXT PRIMARY KEY,
        tipo TEXT NOT NULL,
        tara_g INTEGER NOT NULL DEFAULT 4000
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS catalogo_camiones (
        placa TEXT PRIMARY KEY,
        transportista_id TEXT NOT NULL,
        tara_g INTEGER NOT NULL DEFAULT 6000,
        rfid_uid TEXT UNIQUE
    );
    """)

    # 3. Manifiestos
    c.execute("""
    CREATE TABLE IF NOT EXISTS manifiestos (
        id TEXT PRIMARY KEY,
        contenedor_id TEXT NOT NULL,
        naviera_id TEXT NOT NULL,
        tipo_operacion TEXT NOT NULL CHECK (tipo_operacion IN ('DEPOSITO', 'RETIRO')),
        peso_declarado_g INTEGER NOT NULL,
        tolerancia_pct REAL NOT NULL DEFAULT 5.0,
        transportista_id TEXT NOT NULL,
        observaciones TEXT,
        estado_documental TEXT NOT NULL DEFAULT 'CREADO',
        canal_selectivo TEXT CHECK (canal_selectivo IN ('VERDE', 'ROJO')),
        historial_pesos TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (contenedor_id) REFERENCES catalogo_contenedores (id),
        FOREIGN KEY (naviera_id) REFERENCES usuarios (username)
    );
    """)

    # 4. Declaraciones de mercancias
    c.execute("""
    CREATE TABLE IF NOT EXISTS declaraciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_declaracion TEXT UNIQUE NOT NULL,
        manifiesto_id TEXT NOT NULL,
        agente_id TEXT NOT NULL,
        regimen TEXT NOT NULL CHECK (regimen IN ('Importacion definitiva', 'Deposito temporal')),
        descripcion_mercancia TEXT NOT NULL,
        valor_declarado REAL NOT NULL,
        observaciones TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (manifiesto_id) REFERENCES manifiestos (id),
        FOREIGN KEY (agente_id) REFERENCES usuarios (username)
    );
    """)

    # 5. Citas y franjas de transportistas
    c.execute("""
    CREATE TABLE IF NOT EXISTS citas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transportista_id TEXT NOT NULL,
        contenedor_id TEXT NOT NULL,
        manifiesto_id TEXT NOT NULL,
        fecha TEXT NOT NULL,
        hora_inicio TEXT NOT NULL,
        hora_fin TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'PROGRAMADA' CHECK (estado IN ('PROGRAMADA', 'CUMPLIDA', 'VENCIDA', 'CANCELADA')),
        cumplida_en_ventana INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (transportista_id) REFERENCES usuarios (username),
        FOREIGN KEY (manifiesto_id) REFERENCES manifiestos (id)
    );
    """)

    # 6. Turnos de operacion (10 estados exactos)
    c.execute("""
    CREATE TABLE IF NOT EXISTS turnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_turno TEXT UNIQUE NOT NULL,
        placa_vehiculo TEXT NOT NULL,
        transportista_id TEXT NOT NULL,
        contenedor_id TEXT NOT NULL,
        manifiesto_id TEXT,
        cita_id INTEGER,
        tipo_operacion TEXT NOT NULL CHECK (tipo_operacion IN ('DEPOSITO', 'RETIRO')),
        estado_actual TEXT NOT NULL DEFAULT 'Programado' CHECK (
            estado_actual IN (
                'Programado', 'EnGarita', 'EnPesajeEntrada', 'EnRuta',
                'EnTransferencia', 'EnPesajeSalida', 'EnSalida',
                'Retenido', 'Cerrado', 'Anulado'
            )
        ),
        estado_previo_retencion TEXT,
        estacion_actual TEXT NOT NULL DEFAULT 'GARITA',
        peso_declarado_g INTEGER,
        peso_medido_entrada_g INTEGER,
        peso_medido_salida_g INTEGER,
        posicion_patio_asignada INTEGER,
        nivel_patio_asignado INTEGER,
        tiempo_inicio TEXT NOT NULL,
        tiempo_fin TEXT,
        tiempo_total_seg INTEGER DEFAULT 0,
        FOREIGN KEY (transportista_id) REFERENCES usuarios (username)
    );
    """)

    # 7. Linea de tiempo por turno
    c.execute("""
    CREATE TABLE IF NOT EXISTS linea_tiempo_turno (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turno_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        origen TEXT NOT NULL CHECK (origen IN ('controlador', 'servidor', 'usuario')),
        descripcion TEXT NOT NULL,
        valores_asociados TEXT,
        FOREIGN KEY (turno_id) REFERENCES turnos (id) ON DELETE CASCADE
    );
    """)

    # 8. Parqueo de retencion y registro de retenciones
    c.execute("""
    CREATE TABLE IF NOT EXISTS retenciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_retencion TEXT UNIQUE NOT NULL,
        turno_id INTEGER NOT NULL,
        vehiculo_placa TEXT NOT NULL,
        contenedor_id TEXT NOT NULL,
        causa TEXT NOT NULL CHECK (causa IN ('RT01', 'RT02', 'RT03', 'RT04', 'RT05', 'RT06')),
        estacion TEXT NOT NULL,
        plaza_numero INTEGER NOT NULL CHECK (plaza_numero BETWEEN 1 AND 3),
        tiempo_inicio TEXT NOT NULL,
        tiempo_resolucion TEXT,
        tiempo_retencion_seg INTEGER DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'ABIERTA' CHECK (estado IN ('ABIERTA', 'RESUELTA')),
        peso_declarado_g INTEGER,
        peso_medido_g INTEGER,
        diferencia_abs_g INTEGER,
        diferencia_pct REAL,
        rol_facultado TEXT NOT NULL,
        tipo_resolucion TEXT CHECK (tipo_resolucion IN ('ACLARAR', 'CORREGIR', 'RECHAZAR')),
        motivo_rechazo TEXT,
        observacion TEXT,
        resuelto_por TEXT,
        FOREIGN KEY (turno_id) REFERENCES turnos (id)
    );
    """)

    # 9. Alarmas (AL01 a AL14)
    c.execute("""
    CREATE TABLE IF NOT EXISTS alarmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL,
        severidad TEXT NOT NULL CHECK (severidad IN ('Critica', 'Alta', 'Media', 'Baja')),
        descripcion TEXT NOT NULL,
        origen TEXT NOT NULL,
        datos_asociados TEXT,
        reconocida INTEGER NOT NULL DEFAULT 0,
        reconocida_por TEXT,
        reconocida_en TEXT,
        comentario_reconocimiento TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    # 10. Inventario de patio
    c.execute("""
    CREATE TABLE IF NOT EXISTS patio_posiciones (
        posicion INTEGER NOT NULL,
        nivel INTEGER NOT NULL,
        contenedor_id TEXT,
        naviera_id TEXT,
        peso_declarado_g INTEGER,
        estado_autorizacion TEXT DEFAULT 'AUTORIZADO',
        bloqueada INTEGER NOT NULL DEFAULT 0,
        ingreso_at TEXT,
        remociones INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (posicion, nivel)
    );
    """)

    # 11. Historial de ciclos de grua
    c.execute("""
    CREATE TABLE IF NOT EXISTS grua_ciclos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turno_id INTEGER,
        tipo_trabajo TEXT NOT NULL,
        posicion_origen INTEGER NOT NULL,
        posicion_destino INTEGER NOT NULL,
        tiempo_ciclo_seg REAL NOT NULL,
        distancia_recorrida_mm REAL NOT NULL,
        exitoso INTEGER NOT NULL DEFAULT 1,
        evento_falla TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    # 12. Codigos de vinculacion de transportistas
    c.execute("""
    CREATE TABLE IF NOT EXISTS vinculaciones_transportista (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE NOT NULL,
        transportista_id TEXT NOT NULL,
        creado_por TEXT NOT NULL,
        expira_at TEXT NOT NULL,
        usado INTEGER NOT NULL DEFAULT 0,
        chat_id TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 13. Franjas de la agenda bloqueadas por el operador (impiden asignacion de nuevas citas)
    c.execute("""
    CREATE TABLE IF NOT EXISTS franjas_bloqueadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        hora_inicio TEXT NOT NULL,
        hora_fin TEXT NOT NULL,
        creado_por TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (fecha, hora_inicio)
    );
    """)

    c.execute("CREATE TABLE IF NOT EXISTS schema_metadata (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS controller_events (id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, tipo TEXT NOT NULL, datos TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS controller_state (id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL)")
    columns = {r[1] for r in c.execute("PRAGMA table_info(turnos)")}
    for name, definition in (("hardware_key", "TEXT"), ("naviera_id", "TEXT"), ("retenido_fisico", "INTEGER DEFAULT 0")):
        if name not in columns:
            c.execute(f"ALTER TABLE turnos ADD COLUMN {name} {definition}")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS hardware_turn_key ON turnos(hardware_key)")
    conn.commit()
    seed_initial_data(conn)
    conn.close()


def seed_initial_data(conn):
    c = conn.cursor()

    # 1. Usuarios minimos exigidos
    now = datetime.now(timezone.utc).isoformat()
    usuarios_base = [
        ("operador1", "terminal123", "Operador Principal Terminal", "TERMINAL"),
        ("maersk", "maersk123", "Maersk Line Guatemala", "NAVIERA"),
        ("msc", "msc123", "Mediterranean Shipping Company", "NAVIERA"),
        ("agente1", "agente123", "Agencia Aduanera del Pacifico", "AGENTE"),
        ("sat1", "sat123", "Superintendencia de Administracion Tributaria", "AUTORIDAD"),
        ("trans_rapido", "trans123", "Transportes Rapidos del Sur", "TRANSPORTISTA"),
        ("trans_global", "global123", "Logistica Global de Carga", "TRANSPORTISTA"),
    ]

    for username, pwd, nombre, rol in usuarios_base:
        pwd_h = hash_password(pwd)
        c.execute("""
        INSERT OR IGNORE INTO usuarios (username, password_hash, nombre_completo, rol, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (username, pwd_h, nombre, rol, now))

    # 2. Catalogo de contenedores
    contenedores = [
        ("MSKU1001", "DRY20", 4000),
        ("MSKU1002", "DRY20", 4000),
        ("MSCU2001", "DRY20", 4000),
        ("MSCU2002", "DRY20", 4000),
        ("CMAU3001", "DRY20", 4000),
        ("HLCU4001", "DRY20", 4000),
    ]
    for cid, tipo, tara in contenedores:
        c.execute("INSERT OR IGNORE INTO catalogo_contenedores (id, tipo, tara_g) VALUES (?, ?, ?)", (cid, tipo, tara))

    for cid in range(1, 11):
        c.execute("INSERT OR IGNORE INTO catalogo_contenedores VALUES (?, 'MAQUETA', 0)", (f"CT-{cid:03d}",))

    # 3. Catalogo de camiones (con UIDs reales de hardware leidos por el RC522)
    camiones = [
        ("P001AAA", "trans_rapido", 120, "39BB16B3"),
        ("P002BBB", "trans_rapido", 2240, "D9D87BD3"),
        ("P003CCC", "trans_global", 2340, "55667788"),
        ("P004DDD", "trans_global", 6100, "D4E5F6A1"),
    ]
    for placa, trans, tara, uid in camiones:
        c.execute("""
        INSERT OR IGNORE INTO catalogo_camiones (placa, transportista_id, tara_g, rfid_uid)
        VALUES (?, ?, ?, ?)
        """, (placa, trans, tara, uid))
        # Actualizar UID si ya existia con el valor anterior
        c.execute("UPDATE catalogo_camiones SET rfid_uid = ? WHERE placa = ?", (uid, placa))

    # 4. Inicializar posiciones de patio (2 posiciones, 2 niveles = 4 celdas)
    for pos in [0, 1]:
        for niv in [0, 1]:
            c.execute("""
            INSERT OR IGNORE INTO patio_posiciones (posicion, nivel, contenedor_id, naviera_id, peso_declarado_g, estado_autorizacion, bloqueada, ingreso_at, remociones)
            VALUES (?, ?, NULL, NULL, NULL, 'LIBRE', 0, NULL, 0)
            """, (pos, niv))

    if os.environ.get("PORTUS_DEMO_DATA", "false").lower() not in ("true", "1", "yes"):
        conn.commit()
        return
    if c.execute("SELECT 1 FROM schema_metadata WHERE key='demo_seeded'").fetchone():
        conn.commit()
        return
    c.execute("INSERT INTO schema_metadata VALUES ('demo_seeded', '1')")

    # Posicion inicial para demostraciones: P0 N0 con un contenedor existente
    c.execute("""
    UPDATE patio_posiciones
    SET contenedor_id = 'MSKU1001', naviera_id = 'maersk', peso_declarado_g = 22000,
        estado_autorizacion = 'AUTORIZADO', ingreso_at = ?
    WHERE posicion = 0 AND nivel = 0 AND (contenedor_id IS NULL OR contenedor_id = 'MSKU1001')
    """, (now,))

    # 5. Manifiestos de demostracion para validar cadena documental y roles
    manifiestos_demo = [
        ("MAN-0001", "MSKU1001", "maersk", "DEPOSITO", 22000, 5.0, "trans_rapido", "Carga inicial en patio", "LEVANTE_OTORGADO", "VERDE", now, now),
        ("MAN-0002", "MSKU1002", "maersk", "DEPOSITO", 25000, 5.0, "trans_rapido", "Importacion maquinaria", "LEVANTE_OTORGADO", "VERDE", now, now),
        ("MAN-0003", "MSCU2001", "msc", "RETIRO", 20000, 5.0, "trans_global", "Retiro materia prima", "LEVANTE_SOLICITADO", None, now, now),
        ("MAN-0004", "MSCU2002", "msc", "DEPOSITO", 24000, 5.0, "trans_global", "Insumos hospitalarios", "DECLARADO", None, now, now),
        ("MAN-0005", "CMAU3001", "maersk", "DEPOSITO", 21000, 5.0, "trans_rapido", "Pendiente declaracion", "CREADO", None, now, now),
    ]
    for mid, cid, nid, top, pdec, tol, tid, obs, est, can, cat, uat in manifiestos_demo:
        c.execute("""
        INSERT OR IGNORE INTO manifiestos (
            id, contenedor_id, naviera_id, tipo_operacion, peso_declarado_g,
            tolerancia_pct, transportista_id, observaciones, estado_documental,
            canal_selectivo, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mid, cid, nid, top, pdec, tol, tid, obs, est, can, cat, uat))

    # 6. Declaraciones de mercancias de demostracion
    declaraciones_demo = [
        ("DEC-2026-0001", "MAN-0001", "agente1", "Importacion definitiva", "Componentes de computo y servidores", 52000.0, now),
        ("DEC-2026-0002", "MAN-0002", "agente1", "Importacion definitiva", "Repuestos industriales de precision", 38000.0, now),
        ("DEC-2026-0003", "MAN-0003", "agente1", "Importacion definitiva", "Materia prima textil para confeccion", 29500.0, now),
        ("DEC-2026-0004", "MAN-0004", "agente1", "Deposito temporal", "Equipos electronicos de medicion", 41000.0, now),
    ]
    for ndecl, mid, aid, reg, desc, val, cat in declaraciones_demo:
        c.execute("""
        INSERT OR IGNORE INTO declaraciones (
            numero_declaracion, manifiesto_id, agente_id, regimen,
            descripcion_mercancia, valor_declarado, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ndecl, mid, aid, reg, desc, val, cat))

    # 7. Citas para la agenda del dia actual
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    citas_demo = [
        ("trans_rapido", "MSKU1002", "MAN-0002", fecha_hoy, "10:00", "10:15", "PROGRAMADA", 0, now),
        ("trans_global", "MSCU2001", "MAN-0003", fecha_hoy, "11:30", "11:45", "PROGRAMADA", 0, now),
    ]
    for tid, cid, mid, fec, hini, hfin, est, cv, cat in citas_demo:
        c.execute("""
        INSERT OR IGNORE INTO citas (
            transportista_id, contenedor_id, manifiesto_id, fecha, hora_inicio, hora_fin,
            estado, cumplida_en_ventana, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tid, cid, mid, fec, hini, hfin, est, cv, cat))

    # 8. Turno historico completado y metricas de corrida
    t_ant_ini = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    t_ant_fin = (datetime.now(timezone.utc) - timedelta(hours=3, minutes=56)).isoformat()
    c.execute("""
    INSERT OR IGNORE INTO turnos (
        codigo_turno, placa_vehiculo, transportista_id, contenedor_id, manifiesto_id,
        tipo_operacion, estado_actual, estacion_actual, peso_declarado_g,
        peso_medido_entrada_g, peso_medido_salida_g, posicion_patio_asignada, nivel_patio_asignado,
        tiempo_inicio, tiempo_fin, tiempo_total_seg
    ) VALUES ('TRN-0001', 'P001AAA', 'trans_rapido', 'MSKU1001', 'MAN-0001',
              'DEPOSITO', 'Cerrado', 'SALIDA', 22000, 28000, 6000, 0, 0,
              ?, ?, 240)
    """, (t_ant_ini, t_ant_fin))

    t_row = c.execute("SELECT id FROM turnos WHERE codigo_turno = 'TRN-0001'").fetchone()
    if t_row:
        t_id = t_row["id"]
        c.execute("DELETE FROM linea_tiempo_turno WHERE turno_id = ?", (t_id,))
        c.execute("""
        INSERT INTO linea_tiempo_turno (turno_id, timestamp, origen, descripcion, valores_asociados)
        VALUES (?, ?, 'servidor', 'Ingreso autorizado e inicio de turno TRN-0001', '{"placa":"P001AAA","contenedor":"MSKU1001"}')
        """, (t_id, t_ant_ini))
        c.execute("""
        INSERT INTO linea_tiempo_turno (turno_id, timestamp, origen, descripcion, valores_asociados)
        VALUES (?, ?, 'controlador', 'Lectura de bascula de entrada: 28.0 kg', '{"peso_kg":28.0}')
        """, (t_id, t_ant_ini))
        c.execute("""
        INSERT INTO linea_tiempo_turno (turno_id, timestamp, origen, descripcion, valores_asociados)
        VALUES (?, ?, 'servidor', 'Operacion completada y salida de terminal', '{"estado":"Cerrado"}')
        """, (t_id, t_ant_fin))

        # 9. Ciclos historicos de grua vinculados al turno
        c.execute("DELETE FROM grua_ciclos WHERE turno_id = ?", (t_id,))
        c.execute("""
        INSERT INTO grua_ciclos (
            turno_id, tipo_trabajo, posicion_origen, posicion_destino,
            tiempo_ciclo_seg, distancia_recorrida_mm, exitoso, timestamp
        ) VALUES (?, 'DESCARGA_CAMION_A_PATIO', 0, 1, 19.4, 850.0, 1, ?)
        """, (t_id, t_ant_ini))
        c.execute("""
        INSERT INTO grua_ciclos (
            turno_id, tipo_trabajo, posicion_origen, posicion_destino,
            tiempo_ciclo_seg, distancia_recorrida_mm, exitoso, timestamp
        ) VALUES (?, 'REPOSICION_PATIO', 1, 1, 14.2, 400.0, 1, ?)
        """, (t_id, t_ant_ini))

    conn.commit()


if __name__ == "__main__":
    init_database()
    print("Base de datos de PORTUS Fase 2 inicializada con exito.")
