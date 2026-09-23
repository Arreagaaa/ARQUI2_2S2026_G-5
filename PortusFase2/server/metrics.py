"""
Calculo de las ocho metricas de operacion obligatorias para la pestaña Reportes
segun seccion 13 de la especificacion de PORTUS Fase 2.
"""

import io
import csv
from datetime import datetime
from typing import Optional, Dict, Any
from .database import get_db_connection


def calculate_metrics(inicio_iso: Optional[str] = None, fin_iso: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db_connection()

    filtro_turnos = "WHERE estado_actual = 'Cerrado'"
    filtro_turnos_gen = "WHERE 1=1"
    filtro_grua = "WHERE 1=1"
    filtro_ret = "WHERE 1=1"
    filtro_citas = "WHERE 1=1"
    params_turnos = []
    params_turnos_gen = []
    params_grua = []
    params_ret = []
    params_citas = []

    if inicio_iso:
        filtro_turnos += " AND tiempo_inicio >= ?"
        filtro_turnos_gen += " AND tiempo_inicio >= ?"
        filtro_grua += " AND timestamp >= ?"
        filtro_ret += " AND tiempo_inicio >= ?"
        filtro_citas += " AND fecha >= ?"
        params_turnos.append(inicio_iso)
        params_turnos_gen.append(inicio_iso)
        params_grua.append(inicio_iso)
        params_ret.append(inicio_iso)
        params_citas.append(inicio_iso[:10])

    if fin_iso:
        filtro_turnos += " AND tiempo_inicio <= ?"
        filtro_turnos_gen += " AND tiempo_inicio <= ?"
        filtro_grua += " AND timestamp <= ?"
        filtro_ret += " AND tiempo_inicio <= ?"
        filtro_citas += " AND fecha <= ?"
        params_turnos.append(fin_iso)
        params_turnos_gen.append(fin_iso)
        params_grua.append(fin_iso)
        params_ret.append(fin_iso)
        params_citas.append(fin_iso[:10])

    # 1. Turnos cerrados y retiros
    turnos_cerrados = conn.execute(f"SELECT COUNT(*) as c FROM turnos {filtro_turnos}", params_turnos).fetchone()["c"]
    retiros_completados = conn.execute(
        f"SELECT COUNT(*) as c FROM turnos {filtro_turnos} AND tipo_operacion = 'RETIRO'",
        params_turnos
    ).fetchone()["c"]

    # Remociones registradas en el patio
    total_remociones = conn.execute("SELECT SUM(remociones) as s FROM patio_posiciones").fetchone()["s"] or 0
    remociones_por_retiro = round(total_remociones / retiros_completados, 2) if retiros_completados > 0 else 0.0

    # 2. Ciclos de grua
    total_ciclos = conn.execute(f"SELECT COUNT(*) as c FROM grua_ciclos {filtro_grua}", params_grua).fetchone()["c"]
    ciclos_por_operacion = round(total_ciclos / turnos_cerrados, 2) if turnos_cerrados > 0 else 0.0

    # 3. Distancia total recorrida
    distancia_mm = conn.execute(
        f"SELECT SUM(distancia_recorrida_mm) as s FROM grua_ciclos {filtro_grua}",
        params_grua
    ).fetchone()["s"] or 0.0
    distancia_m = round(distancia_mm / 1000.0, 2)

    # 4. Tiempo promedio de camion en terminal (turnos cerrados)
    tiempo_camion_prom_seg = conn.execute(
        f"SELECT AVG(tiempo_total_seg) as a FROM turnos {filtro_turnos}",
        params_turnos
    ).fetchone()["a"] or 0.0

    # 5. Tiempo promedio de retencion
    tiempo_ret_prom_seg = conn.execute(
        f"SELECT AVG(tiempo_retencion_seg) as a FROM retenciones {filtro_ret} AND estado = 'RESUELTA'",
        params_ret
    ).fetchone()["a"] or 0.0

    # 6. Longitud maxima de fila de espera
    # Calculada en base a max turnos en Garita / EnPesaje simultaneos
    max_espera_row = conn.execute(
        f"SELECT COUNT(*) as c FROM turnos {filtro_turnos_gen} AND estado_actual IN ('Programado', 'EnGarita')",
        params_turnos_gen
    ).fetchone()
    max_espera = max_espera_row["c"] if max_espera_row else 0

    # 7. Porcentaje de citas cumplidas en ventana
    total_citas = conn.execute(f"SELECT COUNT(*) as c FROM citas {filtro_citas}", params_citas).fetchone()["c"]
    citas_cumplidas = conn.execute(
        f"SELECT COUNT(*) as c FROM citas {filtro_citas} AND cumplida_en_ventana = 1",
        params_citas
    ).fetchone()["c"]
    pct_citas = round((citas_cumplidas / total_citas) * 100.0, 1) if total_citas > 0 else 0.0

    # 8. Retenciones por causa y por resolucion
    filas_ret = conn.execute(f"""
    SELECT causa, COALESCE(tipo_resolucion, 'PENDIENTE') as resolucion, COUNT(*) as cantidad
    FROM retenciones {filtro_ret}
    GROUP BY causa, tipo_resolucion
    """, params_ret).fetchall()

    retenciones_desglose = [dict(r) for r in filas_ret]
    conn.close()

    return {
        "remociones_por_contenedor_retirado": remociones_por_retiro,
        "ciclos_grua_por_operacion": ciclos_por_operacion,
        "distancia_total_grua_m": distancia_m,
        "tiempo_promedio_camion_seg": round(tiempo_camion_prom_seg, 1),
        "tiempo_promedio_camion_min": round(tiempo_camion_prom_seg / 60.0, 1),
        "tiempo_promedio_retencion_seg": round(tiempo_ret_prom_seg, 1),
        "tiempo_promedio_retencion_min": round(tiempo_ret_prom_seg / 60.0, 1),
        "longitud_maxima_fila_espera": max_espera,
        "porcentaje_citas_cumplidas_ventana": pct_citas,
        "retenciones_desglose": retenciones_desglose,
        "resumen_conteos": {
            "turnos_cerrados": turnos_cerrados,
            "retiros_completados": retiros_completados,
            "total_ciclos_grua": total_ciclos,
            "total_citas": total_citas,
            "citas_en_ventana": citas_cumplidas
        }
    }


def export_report_csv(etiqueta: str, metricas: Dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["PORTUS Fase 2 - Reporte de Corrida de Evaluacion"])
    writer.writerow(["Etiqueta de corrida", etiqueta])
    writer.writerow(["Fecha de generacion", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])
    writer.writerow(["Metrica", "Valor", "Unidad"])
    writer.writerow(["Remociones por contenedor retirado", metricas["remociones_por_contenedor_retirado"], "remociones/retiro"])
    writer.writerow(["Ciclos de grua por operacion completada", metricas["ciclos_grua_por_operacion"], "ciclos/turno"])
    writer.writerow(["Distancia total recorrida por la grua", metricas["distancia_total_grua_m"], "metros"])
    writer.writerow(["Tiempo promedio de camion en la terminal", metricas["tiempo_promedio_camion_seg"], "segundos"])
    writer.writerow(["Tiempo promedio de retencion", metricas["tiempo_promedio_retencion_seg"], "segundos"])
    writer.writerow(["Longitud maxima de la fila de espera", metricas["longitud_maxima_fila_espera"], "vehiculos"])
    writer.writerow(["Porcentaje de citas cumplidas en ventana", f"{metricas['porcentaje_citas_cumplidas_ventana']}%", "porcentaje"])
    writer.writerow([])
    writer.writerow(["Desglose de Retenciones por Causa y Resolucion"])
    writer.writerow(["Causa", "Resolucion", "Cantidad"])
    for d in metricas["retenciones_desglose"]:
        writer.writerow([d["causa"], d["resolucion"], d["cantidad"]])

    return output.getvalue()
