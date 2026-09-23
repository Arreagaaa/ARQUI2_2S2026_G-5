"""
Administrador del patio de contenedores y la grua para PORTUS Fase 2.
Controla el inventario fisico por posicion y nivel, el reloj de permanencia,
la cola de trabajos, y registra los ciclos y tiempos de ejecucion de la grua.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from .database import get_db_connection


def get_yard_inventory() -> List[Dict[str, Any]]:
    """
    Retorna el estado de todas las celdas del patio con reloj de permanencia calculado.
    """
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT posicion, nivel, contenedor_id, naviera_id, peso_declarado_g,
           estado_autorizacion, bloqueada, ingreso_at, remociones
    FROM patio_posiciones
    ORDER BY posicion ASC, nivel ASC
    """).fetchall()
    conn.close()

    now = datetime.now(timezone.utc)
    inventory = []
    for r in rows:
        item = dict(r)
        permanencia_min = 0
        permanencia_str = "0h 0m"
        excesiva = False

        if item["ingreso_at"] and item["contenedor_id"]:
            try:
                t_ingreso = datetime.fromisoformat(item["ingreso_at"])
                permanencia_min = int((now - t_ingreso).total_seconds() / 60)
                horas = permanencia_min // 60
                minutos = permanencia_min % 60
                permanencia_str = f"{horas}h {minutos}m"
                if permanencia_min > 120:
                    excesiva = True
            except Exception:
                pass

        item["permanencia_min"] = permanencia_min
        item["permanencia_str"] = permanencia_str
        item["permanencia_excesiva"] = excesiva
        inventory.append(item)

    return inventory


def update_yard_on_physical_confirmation(posicion: int, nivel: int, contenedor_id: Optional[str], naviera_id: Optional[str] = None, peso_g: Optional[int] = None, es_remocion: bool = False):
    """
    Actualiza el inventario del patio UNICAMENTE tras la confirmacion fisica del controlador.
    """
    conn = get_db_connection()
    now = datetime.now(timezone.utc).isoformat() if contenedor_id else None

    if contenedor_id is None:
        # Se retiro contenedor
        conn.execute("""
        UPDATE patio_posiciones
        SET contenedor_id = NULL, naviera_id = NULL, peso_declarado_g = NULL,
            estado_autorizacion = 'LIBRE', ingreso_at = NULL
        WHERE posicion = ? AND nivel = ?
        """, (posicion, nivel))
    else:
        # Se deposito o removio
        remocion_inc = 1 if es_remocion else 0
        conn.execute("""
        UPDATE patio_posiciones
        SET contenedor_id = ?, naviera_id = ?, peso_declarado_g = ?,
            estado_autorizacion = 'AUTORIZADO', ingreso_at = COALESCE(ingreso_at, ?),
            remociones = remociones + ?
        WHERE posicion = ? AND nivel = ?
        """, (contenedor_id, naviera_id, peso_g, now, remocion_inc, posicion, nivel))

    conn.commit()
    conn.close()


def set_position_blocked(posicion: int, bloqueada: bool):
    conn = get_db_connection()
    conn.execute("""
    UPDATE patio_posiciones
    SET bloqueada = ?
    WHERE posicion = ?
    """, (1 if bloqueada else 0, posicion))
    conn.commit()
    conn.close()


def record_crane_cycle(
    turno_id: Optional[int],
    tipo_trabajo: str,
    posicion_origen: int,
    posicion_destino: int,
    tiempo_ciclo_seg: float,
    distancia_recorrida_mm: float,
    exitoso: bool = True,
    evento_falla: Optional[str] = None
):
    conn = get_db_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
    INSERT INTO grua_ciclos (
        turno_id, tipo_trabajo, posicion_origen, posicion_destino,
        tiempo_ciclo_seg, distancia_recorrida_mm, exitoso, evento_falla, timestamp
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        turno_id, tipo_trabajo, posicion_origen, posicion_destino,
        tiempo_ciclo_seg, distancia_recorrida_mm, 1 if exitoso else 0, evento_falla, now
    ))
    conn.commit()
    conn.close()


def get_crane_history(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute("""
    SELECT * FROM grua_ciclos
    ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
