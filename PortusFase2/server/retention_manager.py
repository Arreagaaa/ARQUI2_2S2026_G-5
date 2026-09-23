"""
Administrador logico del parqueo de retencion (3 plazas) para PORTUS Fase 2.
Maneja las causas RT01-RT06, asignacion de plazas 1-3, resoluciones Aclarar,
Corregir y Rechazar, y genera comandos de aguja y notificaciones al transportista.
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from .database import get_db_connection
from .turn_manager import transition_turn, add_timeline_event

CAUSAS_ROLES = {
    "RT01": "TERMINAL",   # Discrepancia peso ingreso
    "RT02": "TERMINAL",   # Discrepancia peso salida
    "RT03": "AUTORIDAD",  # Canal rojo
    "RT04": "TERMINAL",   # Fuera de ventana
    "RT05": "AUTORIDAD",  # Retencion documental
    "RT06": "TERMINAL"    # Manual operativa
}


def get_parking_occupancy() -> Dict[int, Optional[Dict[str, Any]]]:
    """
    Retorna el estado de las 3 plazas logicas del parqueo (1, 2, 3).
    """
    conn = get_db_connection()
    retenciones_activas = conn.execute("""
    SELECT r.*, t.codigo_turno, t.placa_vehiculo, t.transportista_id
    FROM retenciones r
    JOIN turnos t ON r.turno_id = t.id
    WHERE r.estado = 'ABIERTA'
    """).fetchall()
    conn.close()

    plazas = {1: None, 2: None, 3: None}
    for r in retenciones_activas:
        p_num = r["plaza_numero"]
        if p_num in plazas:
            plazas[p_num] = dict(r)
    return plazas


def assign_retention(
    turno_id: int,
    causa: str,
    estacion: str,
    peso_declarado_g: Optional[int] = None,
    peso_medido_g: Optional[int] = None,
    observacion: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Crea una retencion y asigna la plaza libre de menor indice (1..3).
    Si no hay plazas libres, retorna None (parqueo lleno -> dispara AL11).
    """
    plazas = get_parking_occupancy()
    plaza_asignada = None
    for p in [1, 2, 3]:
        if plazas[p] is None:
            plaza_asignada = p
            break

    if plaza_asignada is None:
        # Parqueo lleno
        return None

    conn = get_db_connection()
    turno = conn.execute("SELECT * FROM turnos WHERE id = ?", (turno_id,)).fetchone()
    if not turno:
        conn.close()
        return None

    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM retenciones")
    count = c.fetchone()["count"] + 1
    codigo = f"RET-{count:04d}"

    now = datetime.now(timezone.utc).isoformat()
    rol_facultado = CAUSAS_ROLES.get(causa, "TERMINAL")

    diff_abs = None
    diff_pct = None
    if peso_declarado_g is not None and peso_medido_g is not None:
        diff_abs = abs(peso_medido_g - peso_declarado_g)
        diff_pct = round((diff_abs / peso_declarado_g) * 100, 2) if peso_declarado_g > 0 else 0.0

    c.execute("""
    INSERT INTO retenciones (
        codigo_retencion, turno_id, vehiculo_placa, contenedor_id, causa,
        estacion, plaza_numero, tiempo_inicio, estado, peso_declarado_g,
        peso_medido_g, diferencia_abs_g, diferencia_pct, rol_facultado, observacion
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ABIERTA', ?, ?, ?, ?, ?, ?)
    """, (
        codigo, turno_id, turno["placa_vehiculo"], turno["contenedor_id"], causa,
        estacion, plaza_asignada, now, peso_declarado_g, peso_medido_g,
        diff_abs, diff_pct, rol_facultado, observacion
    ))

    retencion_id = c.lastrowid
    conn.commit()
    conn.close()

    # Transicionar turno a 'Retenido'
    transition_turn(
        turno_id,
        "Retenido",
        estacion="PARQUEO",
        origen="servidor",
        detalle=f"Vehiculo enviado a parqueo de retencion plaza {plaza_asignada} por causa {causa}",
        valores={
            "retencion_codigo": codigo,
            "plaza": plaza_asignada,
            "causa": causa,
            "peso_declarado": peso_declarado_g,
            "peso_medido": peso_medido_g
        }
    )

    return {
        "id": retencion_id,
        "codigo": codigo,
        "plaza": plaza_asignada,
        "causa": causa,
        "turno_id": turno_id
    }


def resolve_retention(
    retencion_id: int,
    resolucion: str,
    usuario: str,
    rol_usuario: str,
    motivo_rechazo: Optional[str] = None,
    observacion: Optional[str] = None
) -> Dict[str, Any]:
    """
    Aplica una de las tres resoluciones: ACLARAR, CORREGIR o RECHAZAR.
    Verifica estrictamente los permisos por causa y rol.
    """
    resolucion = resolucion.upper()
    if resolucion not in ("ACLARAR", "CORREGIR", "RECHAZAR"):
        return {"success": False, "error": "Tipo de resolucion invalido"}

    conn = get_db_connection()
    ret = conn.execute("SELECT * FROM retenciones WHERE id = ?", (retencion_id,)).fetchone()
    if not ret:
        conn.close()
        return {"success": False, "error": "Retencion no encontrada"}

    if ret["estado"] == "RESUELTA":
        conn.close()
        return {"success": False, "error": "La retencion ya ha sido resuelta previamente"}

    causa = ret["causa"]
    rol_facultado = ret["rol_facultado"]

    # 1. Regla de permisos por causa y rol
    if rol_usuario != rol_facultado:
        conn.close()
        return {"success": False, "error": f"El rol '{rol_usuario}' no esta facultado para resolver la causa {causa} (requiere {rol_facultado})"}

    if resolucion == "CORREGIR" and rol_usuario != "TERMINAL":
        conn.close()
        return {"success": False, "error": "La resolucion 'Corregir' es potestad exclusiva del rol TERMINAL"}

    # 2. Rechazar exige motivo obligatorio
    if resolucion == "RECHAZAR" and (not motivo_rechazo or not motivo_rechazo.strip()):
        conn.close()
        return {"success": False, "error": "La resolucion 'Rechazar' exige un motivo obligatorio"}

    now = datetime.now(timezone.utc).isoformat()
    t_ret_seg = 0
    try:
        t_ini = datetime.fromisoformat(ret["tiempo_inicio"])
        t_now = datetime.fromisoformat(now)
        t_ret_seg = int((t_now - t_ini).total_seconds())
    except Exception:
        pass

    turno = conn.execute("SELECT * FROM turnos WHERE id = ?", (ret["turno_id"],)).fetchone()

    # Si la resolucion es CORREGIR, actualizar el manifiesto conservando el historial
    if resolucion == "CORREGIR" and turno and turno["manifiesto_id"]:
        manif = conn.execute("SELECT * FROM manifiestos WHERE id = ?", (turno["manifiesto_id"],)).fetchone()
        if manif:
            try:
                historial = json.loads(manif["historial_pesos"] or "[]")
            except Exception:
                historial = []
            historial.append({
                "fecha": now,
                "peso_anterior_g": manif["peso_declarado_g"],
                "peso_nuevo_g": ret["peso_medido_g"],
                "corregido_por": usuario
            })
            conn.execute("""
            UPDATE manifiestos
            SET peso_declarado_g = ?, historial_pesos = ?, updated_at = ?
            WHERE id = ?
            """, (ret["peso_medido_g"], json.dumps(historial), now, manif["id"]))

    # Actualizar estado de la retencion
    conn.execute("""
    UPDATE retenciones
    SET estado = 'RESUELTA', tiempo_resolucion = ?, tiempo_retencion_seg = ?,
        tipo_resolucion = ?, motivo_rechazo = ?, observacion = ?, resuelto_por = ?
    WHERE id = ?
    """, (now, t_ret_seg, resolucion, motivo_rechazo, observacion, usuario, retencion_id))
    conn.commit()
    conn.close()

    # Transicionar el turno segun la resolucion
    turno_id = ret["turno_id"]
    if resolucion == "RECHAZAR":
        transition_turn(
            turno_id,
            "Anulado",
            estacion="SALIDA",
            origen="usuario",
            detalle=f"Turno anulado por rechazo de retencion {ret['codigo_retencion']}: {motivo_rechazo}",
            valores={"resolucion": "RECHAZAR", "motivo": motivo_rechazo}
        )
    else:
        # Aclarar o Corregir: devuelve al estado previo o a EnRuta / EnSalida
        estado_previo = turno["estado_previo_retencion"] if turno else None
        if not estado_previo or estado_previo == "Retenido":
            estado_previo = "EnRuta" if ret["estacion"] != "SALIDA" else "EnSalida"

        transition_turn(
            turno_id,
            estado_previo,
            estacion="RUTA" if estado_previo == "EnRuta" else "SALIDA",
            origen="usuario",
            detalle=f"Retencion {ret['codigo_retencion']} resuelta mediante {resolucion}. Retornando a {estado_previo}.",
            valores={"resolucion": resolucion, "observacion": observacion}
        )

    return {
        "success": True,
        "retencion_id": retencion_id,
        "resolucion": resolucion,
        "plaza_liberada": ret["plaza_numero"],
        "turno_id": turno_id
    }
