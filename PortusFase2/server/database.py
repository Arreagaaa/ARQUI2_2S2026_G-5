"""
Modelo de base de datos SQLite y migracion inicial para PORTUS Fase 2.
Gestiona usuarios, permisos, manifiestos, declaraciones, turnos, linea de tiempo,
retenciones, parqueo de 3 plazas, alarmas AL01-AL14, inventario de patio y citas.
"""

import sqlite3
import os
import json
import hashlib
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "portus_fase2.db")


def hash_password(password: str) -> str:
    # Hash seguro SHA-256 con salt fijo para la plataforma
    salt = "portus_usac_arqui2_2026"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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

    # 3. Catalogo de camiones
    camiones = [
        ("P001AAA", "trans_rapido", 6000, "A1B2C3D4"),
        ("P002BBB", "trans_rapido", 6200, "B2C3D4E5"),
        ("P003CCC", "trans_global", 5900, "C3D4E5F6"),
        ("P004DDD", "trans_global", 6100, "D4E5F6A1"),
    ]
    for placa, trans, tara, uid in camiones:
        c.execute("""
        INSERT OR IGNORE INTO catalogo_camiones (placa, transportista_id, tara_g, rfid_uid)
        VALUES (?, ?, ?, ?)
        """, (placa, trans, tara, uid))

    # 4. Inicializar posiciones de patio (2 posiciones, 2 niveles = 4 celdas)
    for pos in [0, 1]:
        for niv in [0, 1]:
            c.execute("""
            INSERT OR IGNORE INTO patio_posiciones (posicion, nivel, contenedor_id, naviera_id, peso_declarado_g, estado_autorizacion, bloqueada, ingreso_at, remociones)
            VALUES (?, ?, NULL, NULL, NULL, 'LIBRE', 0, NULL, 0)
            """, (pos, niv))

    # Posicion inicial para demostraciones: P0 N0 con un contenedor existente
    c.execute("""
    UPDATE patio_posiciones
    SET contenedor_id = 'MSKU1001', naviera_id = 'maersk', peso_declarado_g = 22000,
        estado_autorizacion = 'AUTORIZADO', ingreso_at = ?
    WHERE posicion = 0 AND nivel = 0 AND contenedor_id IS NULL
    """, (now,))

    conn.commit()


if __name__ == "__main__":
    init_database()
    print("Base de datos de PORTUS Fase 2 inicializada con exito.")
