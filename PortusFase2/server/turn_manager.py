"""
Maquina de estados de los turnos de operacion para PORTUS Fase 2.
Controla los 10 estados exactos y registra cada transicion en la linea de tiempo.
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from .database import get_db_connection

ESTADOS_VALIDOS = {
    "Programado": ["EnGarita", "Anulado"],
    "EnGarita": ["EnPesajeEntrada", "Retenido", "Anulado"],
    "EnPesajeEntrada": ["EnRuta", "Retenido", "Anulado"],
    "EnRuta": ["EnTransferencia", "Anulado"],
    "EnTransferencia": ["EnPesajeSalida", "EnTransferencia", "Anulado"],
    "EnPesajeSalida": ["EnSalida", "Retenido", "Anulado"],
    "EnSalida": ["Cerrado", "Retenido"],
    "Retenido": ["EnGarita", "EnPesajeEntrada", "EnRuta", "EnTransferencia", "EnPesajeSalida", "EnSalida", "Anulado"],
    "Cerrado": [],
    "Anulado": []
}


def add_timeline_event(turno_id: int, origen: str, descripcion: str, valores: Optional[Dict[str, Any]] = None):
    conn = get_db_connection()
    now = datetime.now(timezone.utc).isoformat()
    val_str = json.dumps(valores) if valores else None
    conn.execute("""
    INSERT INTO linea_tiempo_turno (turno_id, timestamp, origen, descripcion, valores_asociados)
    VALUES (?, ?, ?, ?, ?)
    """, (turno_id, now, origen, descripcion, val_str))
    conn.commit()
    conn.close()


def create_turn(
    placa: str,
    transportista_id: str,
    contenedor_id: str,
    tipo_operacion: str,
    manifiesto_id: Optional[str] = None,
    cita_id: Optional[int] = None,
    peso_declarado_g: Optional[int] = None
) -> Optional[int]:
    """
    Crea un turno cuando la garita autoriza el ingreso (Pasa a EnGarita).
    """
    conn = get_db_connection()
    now = datetime.now(timezone.utc).isoformat()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) as count FROM turnos")
    count = c.fetchone()["count"] + 1
    codigo = f"TRN-{count:04d}"

    c.execute("""
    INSERT INTO turnos (
        codigo_turno, placa_vehiculo, transportista_id, contenedor_id, manifiesto_id,
        cita_id, tipo_operacion, estado_actual, estacion_actual, peso_declarado_g,
        tiempo_inicio
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'EnGarita', 'GARITA', ?, ?)
    """, (codigo, placa, transportista_id, contenedor_id, manifiesto_id, cita_id, tipo_operacion, peso_declarado_g, now))

    turno_id = c.lastrowid
    conn.commit()
    conn.close()

    add_timeline_event(
        turno_id,
        "servidor",
        f"Turno creado e ingreso autorizado para vehiculo {placa}",
        {"codigo": codigo, "contenedor": contenedor_id, "tipo": tipo_operacion}
    )
    return turno_id


def transition_turn(turno_id: int, nuevo_estado: str, estacion: Optional[str] = None, origen: str = "servidor", detalle: str = "", valores: Optional[Dict[str, Any]] = None) -> bool:
    """
    Ejecuta una transicion de estado verificando la tabla de transiciones permitidas.
    """
    conn = get_db_connection()
    turno = conn.execute("SELECT * FROM turnos WHERE id = ?", (turno_id,)).fetchone()
    if not turno:
        conn.close()
        return False

    estado_actual = turno["estado_actual"]
    transiciones_posibles = ESTADOS_VALIDOS.get(estado_actual, [])

    if nuevo_estado not in transiciones_posibles and nuevo_estado != estado_actual:
        conn.close()
        return False

    now = datetime.now(timezone.utc).isoformat()
    estacion_nueva = estacion if estacion else turno["estacion_actual"]

    # Calcular tiempo total si finaliza
    tiempo_fin = None
    tiempo_total = turno["tiempo_total_seg"]
    if nuevo_estado in ("Cerrado", "Anulado"):
        tiempo_fin = now
        try:
            t_ini = datetime.fromisoformat(turno["tiempo_inicio"])
            t_now = datetime.fromisoformat(now)
            tiempo_total = int((t_now - t_ini).total_seconds())
        except Exception:
            tiempo_total = 0

    estado_previo = turno["estado_previo_retencion"]
    if nuevo_estado == "Retenido":
        estado_previo = estado_actual

    conn.execute("""
    UPDATE turnos
    SET estado_actual = ?, estacion_actual = ?, estado_previo_retencion = ?, tiempo_fin = ?, tiempo_total_seg = ?
    WHERE id = ?
    """, (nuevo_estado, estacion_nueva, estado_previo, tiempo_fin, tiempo_total, turno_id))
    conn.commit()
    conn.close()

    val_dict = valores or {}
    val_dict["de_estado"] = estado_actual
    val_dict["a_estado"] = nuevo_estado
    desc = detalle or f"Transicion de estado a {nuevo_estado}"

    add_timeline_event(turno_id, origen, desc, val_dict)
    return True


def get_active_turn_by_vehicle(placa: str):
    conn = get_db_connection()
    turno = conn.execute("""
    SELECT * FROM turnos
    WHERE placa_vehiculo = ? AND estado_actual NOT IN ('Cerrado', 'Anulado')
    ORDER BY id DESC LIMIT 1
    """, (placa,)).fetchone()
    conn.close()
    return dict(turno) if turno else None


def get_turn_timeline(turno_id: int):
    conn = get_db_connection()
    events = conn.execute("""
    SELECT * FROM linea_tiempo_turno
    WHERE turno_id = ?
    ORDER BY id ASC
    """, (turno_id,)).fetchall()
    conn.close()
    return [dict(e) for e in events]
