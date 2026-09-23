"""
Administrador del catalogo de alarmas AL01 a AL14 para PORTUS Fase 2.
Mantiene listas de alarmas activas e historicas y atiende reconocimiento
manual (individual para criticas/altas, masivo para bajas/medias).
"""

import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from .database import get_db_connection

CATALOGO_ALARMAS = {
    "AL01": ("Critica", "Enlace con el controlador perdido"),
    "AL02": ("Critica", "Paro de emergencia accionado"),
    "AL03": ("Critica", "Perdida de referencia de posicion de la grua"),
    "AL04": ("Critica", "Perdida de carga durante el traslado"),
    "AL05": ("Alta", "Agarre de contenedor no confirmado"),
    "AL06": ("Alta", "Trabajo de grua abortado"),
    "AL07": ("Alta", "Inconsistencia entre altura fisica e inventario"),
    "AL08": ("Alta", "Movimiento del vehiculo durante la transferencia"),
    "AL09": ("Media", "Pesaje fuera de tolerancia"),
    "AL10": ("Media", "Vehiculo incorrecto en la salida"),
    "AL11": ("Media", "Parqueo de retencion lleno"),
    "AL12": ("Media", "Retencion que supera treinta minutos"),
    "AL13": ("Baja", "Permanencia de contenedor superior a dos horas"),
    "AL14": ("Baja", "Comando remoto rechazado por el controlador"),
}


def raise_alarm(codigo: str, origen: str = "controlador", datos: Optional[Dict[str, Any]] = None) -> int:
    """
    Registra una alarma en el sistema como activa (reconocida=0).
    """
    cat_info = CATALOGO_ALARMAS.get(codigo, ("Media", "Alarma no especificada"))
    severidad, desc_default = cat_info

    descripcion = desc_default
    if datos and "descripcion" in datos:
        descripcion = datos["descripcion"]

    conn = get_db_connection()
    now = datetime.now(timezone.utc).isoformat()
    datos_str = json.dumps(datos) if datos else None

    c = conn.cursor()
    c.execute("""
    INSERT INTO alarmas (codigo, severidad, descripcion, origen, datos_asociados, reconocida, timestamp)
    VALUES (?, ?, ?, ?, ?, 0, ?)
    """, (codigo, severidad, descripcion, origen, datos_str, now))

    alarm_id = c.lastrowid
    conn.commit()
    conn.close()
    return alarm_id


def acknowledge_alarm(alarm_id: int, usuario: str, comentario: Optional[str] = None) -> bool:
    """
    Reconoce individualmente una alarma activa.
    """
    conn = get_db_connection()
    now = datetime.now(timezone.utc).isoformat()
    c = conn.cursor()
    c.execute("""
    UPDATE alarmas
    SET reconocida = 1, reconocida_por = ?, reconocida_en = ?, comentario_reconocimiento = ?
    WHERE id = ? AND reconocida = 0
    """, (usuario, now, comentario, alarm_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def acknowledge_all_low_medium(usuario: str, comentario: Optional[str] = "Reconocimiento masivo") -> int:
    """
    Reconoce en bloque todas las alarmas activas de severidad Baja y Media.
    No afecta a alarmas Criticas ni Altas, que deben reconocerse una a una.
    """
    conn = get_db_connection()
    now = datetime.now(timezone.utc).isoformat()
    c = conn.cursor()
    c.execute("""
    UPDATE alarmas
    SET reconocida = 1, reconocida_por = ?, reconocida_en = ?, comentario_reconocimiento = ?
    WHERE reconocida = 0 AND severidad IN ('Baja', 'Media')
    """, (usuario, now, comentario))
    count = c.rowcount
    conn.commit()
    conn.close()
    return count


def get_alarms(severidad: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retorna listas separadas de alarmas activas e historicas (ya reconocidas).
    """
    conn = get_db_connection()
    query_act = "SELECT * FROM alarmas WHERE reconocida = 0"
    query_hist = "SELECT * FROM alarmas WHERE reconocida = 1"
    params_act = []
    params_hist = []

    if severidad:
        query_act += " AND severidad = ?"
        query_hist += " AND severidad = ?"
        params_act.append(severidad)
        params_hist.append(severidad)

    query_act += " ORDER BY id DESC"
    query_hist += " ORDER BY id DESC LIMIT 100"

    activas = [dict(r) for r in conn.execute(query_act, params_act).fetchall()]
    historicas = [dict(r) for r in conn.execute(query_hist, params_hist).fetchall()]
    conn.close()

    return {
        "activas": activas,
        "historicas": historicas
    }
