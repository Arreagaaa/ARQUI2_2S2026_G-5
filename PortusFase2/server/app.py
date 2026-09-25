"""
Servidor web principal para PORTUS Fase 2.
Construido sobre Flask, con autenticacion por roles, matriz de permisos en backend,
distribucion de eventos en tiempo real via Server-Sent Events (SSE) sin polling,
y endpoints REST para la cadena documental y los comandos remotos.
"""

import os
import json
import uuid
import time
import queue
import logging
import threading
from datetime import datetime, timezone, timedelta

# Ruta absoluta al build de la SPA React (frontend/dist) para el modo produccion.
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

from flask import Flask, request, jsonify, session, redirect, url_for, Response, send_from_directory
import paho.mqtt.client as mqtt

from .database import get_db_connection, init_database
from .auth import authenticate_user, login_required, require_permission, PERMISOS_MATRIZ
from .turn_manager import create_turn, transition_turn, get_turn_timeline, add_timeline_event
from .retention_manager import (
    get_parking_occupancy, assign_retention, resolve_retention, CAUSAS_ROLES
)
from .alarm_manager import raise_alarm, acknowledge_alarm, acknowledge_all_low_medium, get_alarms
from .yard_crane_manager import (
    get_yard_inventory, update_yard_on_physical_confirmation, set_position_blocked,
    get_crane_history, record_crane_cycle
)
from .metrics import calculate_metrics, export_report_csv
from ..mensajeria.messaging_service import TransportistaMessagingService, generate_binding_code

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__, static_folder=None)
app.secret_key = "portus_secret_key_usac_arqui2_2026"

# Colas de transmision en tiempo real para clientes SSE conectados
event_queues = []
event_queues_lock = threading.Lock()

# Ultimo estado conocido de la maqueta y del enlace
terminal_state = {
    "modo": "NORMAL",
    "enlace": "CONECTADO",
    "ultimo_latido_timestamp": datetime.now(timezone.utc).isoformat(),
    "garita": {"estado": "Libre", "vehiculo": None},
    "talanquera": "Cerrada",
    "pesaje": {"estado": "Libre", "ultimo_valor_kg": 0.0, "resultado": "Valido"},
    "aguja": "Recta",
    "parqueo": {1: None, 2: None, 3: None},
    "transferencia": {"estado": "Libre", "vehiculo": None},
    "grua": {
        "estado": "En reposo",
        "posicion": 0,
        "trabajo_en_curso": None,
        "cola_pendientes": 0,
        "suspendida": False,
        "referenciada": True,
        "en_falla": False
    },
    "puerta_salida": "Cerrada",
    "zona_espera": {"cantidad_vehiculos": 0}
}

# Servicio de mensajeria
init_database()
msg_service = TransportistaMessagingService()

# Cliente MQTT del servidor
mqtt_client: mqtt.Client = None


def _refresh_parqueo_state():
    """
    Sincroniza terminal_state['parqueo'] con el retention manager (fuente real
    de las plazas ocupadas). Cada plaza ocupada expone vehiculo, turno, causa
    y tiempo de retencion transcurrido, tal como exige el sinoptico.
    """
    try:
        ocupacion = get_parking_occupancy()
        now = datetime.now(timezone.utc)
        parqueo = {}
        for plaza, ret in ocupacion.items():
            if ret is None:
                parqueo[plaza] = None
                continue
            retencion_min = 0
            try:
                t_ini = datetime.fromisoformat(ret["tiempo_inicio"])
                retencion_min = int((now - t_ini).total_seconds() / 60)
            except Exception:
                pass
            parqueo[plaza] = {
                "vehiculo": ret["placa_vehiculo"],
                "codigo_turno": ret["codigo_turno"],
                "codigo_retencion": ret["codigo_retencion"],
                "causa": ret["causa"],
                "tiempo_retencion_min": retencion_min
            }
        terminal_state["parqueo"] = parqueo
    except Exception as e:
        logging.error("No se pudo refrescar el estado del parqueo: %s", e)


def dispatch_event_to_sse(event_data: dict):
    with event_queues_lock:
        dead_queues = []
        for q in event_queues:
            try:
                q.put_nowait(event_data)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            if dq in event_queues:
                event_queues.remove(dq)


def on_mqtt_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8")
        data = json.loads(payload_str)
        topic = msg.topic
        datos = data.get("datos", {})

        now_str = datetime.now(timezone.utc).isoformat()
        terminal_state["ultimo_latido_timestamp"] = now_str

        # Actualizar estado interno segun el topico
        if topic == "portus/evt/estado":
            if data.get("tipo") == "EnlacePerdido":
                terminal_state["enlace"] = "DESCONECTADO"
            elif data.get("tipo") == "EnlaceRestablecido":
                terminal_state["enlace"] = "CONECTADO"
            else:
                terminal_state["enlace"] = "CONECTADO"
                terminal_state["modo"] = datos.get("modo", terminal_state["modo"])
                terminal_state["talanquera"] = datos.get("talanquera", terminal_state["talanquera"])
                terminal_state["aguja"] = datos.get("aguja", terminal_state["aguja"])
                terminal_state["grua"]["posicion"] = datos.get("grua_pos", terminal_state["grua"]["posicion"])
                terminal_state["grua"]["cola_pendientes"] = datos.get("cola_grua", terminal_state["grua"]["cola_pendientes"])
                terminal_state["grua"]["suspendida"] = (datos.get("grua_susp") == "SI")
                terminal_state["grua"]["referenciada"] = (datos.get("grua_ref") == "SI")
                terminal_state["grua"]["en_falla"] = (datos.get("grua_falla") == "SI")
                # El latido mantiene el parqueo del sinoptico alineado sin polling al navegador
                _refresh_parqueo_state()

        elif topic == "portus/evt/garita":
            tipo_ev = data.get("tipo")
            if tipo_ev == "GaritaIdentificacion":
                terminal_state["garita"]["estado"] = "Validando"
                terminal_state["garita"]["vehiculo"] = datos.get("uid")
            elif "RECHAZADO" in str(datos):
                terminal_state["garita"]["estado"] = "Rechazada"
            else:
                terminal_state["garita"]["estado"] = "Autorizada"

        elif topic == "portus/evt/pesaje":
            terminal_state["pesaje"]["estado"] = "Medicion valida"
            if "peso" in datos:
                try:
                    terminal_state["pesaje"]["ultimo_valor_kg"] = float(datos["peso"])
                except Exception:
                    pass

        elif topic == "portus/evt/aguja":
            terminal_state["aguja"] = datos.get("posicion", terminal_state["aguja"])

        elif topic == "portus/evt/grua":
            terminal_state["grua"]["estado"] = data.get("tipo", "Operando")

        elif topic == "portus/evt/alarma":
            cod = datos.get("codigo", "AL00")
            raise_alarm(cod, origen=data.get("origen", "controlador"), datos=datos)

        elif topic == "portus/cmd/respuesta":
            resultado = datos.get("resultado")
            cmd = datos.get("comando")
            if resultado == "NAK":
                # Alarma AL14 obligatoria si controlador rechaza comando
                raise_alarm("AL14", origen="controlador", datos={"comando": cmd, "error": datos.get("error")})

        # Notificar instantaneamente al navegador via SSE (sin polling)
        dispatch_event_to_sse({"topic": topic, "data": data, "state": terminal_state})

    except Exception as e:
        logging.error("Error procesando mensaje MQTT en server: %s", e)


def init_mqtt():
    global mqtt_client
    mqtt_client = mqtt.Client(client_id=f"portus_server_{uuid.uuid4().hex[:6]}")
    mqtt_client.on_connect = lambda c, u, f, rc: c.subscribe("portus/#") if rc == 0 else None
    mqtt_client.on_message = on_mqtt_message
    try:
        mqtt_client.connect("localhost", 1883, keepalive=60)
        mqtt_client.loop_start()
        logging.info("Servidor web conectado a MQTT en localhost:1883 (suscrito a portus/#)")
    except Exception as e:
        logging.warning("No se pudo conectar a MQTT en localhost:1883: %s", e)


# -------------------------------------------------------------
# RUTAS DE AUTENTICACION Y NAVEGACION
# -------------------------------------------------------------
def _servir_spa_si_existe():
    """Sirve el index de la SPA React si frontend/dist ya fue construido."""
    indice = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(indice):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return None


def _spa_no_construida():
    """Respuesta cuando no hay build de React (olvido de `pnpm build`)."""
    return (
        "Frontend React no construido. Ejecute: cd PortusFase2/frontend && pnpm install && pnpm build",
        503,
        {"Content-Type": "text/plain; charset=utf-8"},
    )


@app.route("/")
def index():
    spa = _servir_spa_si_existe()
    if spa is not None:
        return spa
    return _spa_no_construida()


@app.route("/login")
def login_page():
    spa = _servir_spa_si_existe()
    if spa is not None:
        return spa
    return _spa_no_construida()


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    user = authenticate_user(username, password)
    if not user:
        return jsonify({"error": "Credenciales invalidas. Verifique usuario y contraseña."}), 401

    if user["rol"] == "TRANSPORTISTA":
        return jsonify({"error": "El rol TRANSPORTISTA no tiene acceso a la aplicacion web. Debe operar desde el canal de mensajeria."}), 403

    session["user"] = user
    return jsonify({
        "success": True,
        "user": user,
        "redirect": url_for("index")
    })


@app.route("/api/logout", methods=["POST", "GET"])
def api_logout():
    session.clear()
    # La SPA React pide sesion JSON; las vistas Jinja2 antiguas conservan el redirect.
    if request.headers.get("Accept", "").find("application/json") >= 0 or request.is_json:
        return jsonify({"success": True})
    return redirect(url_for("login_page"))


@app.route("/api/me")
def api_me():
    """
    Devuelve el usuario en sesion para que la SPA React restaure su contexto
    tras recargar la pagina. Sin sesion valida responde user: null.
    """
    user = session.get("user")
    return jsonify({"user": user})


# -------------------------------------------------------------
# RUTAS DE NAVEGACION POR ROL (sirven la SPA; el control de rol
# de cada pestaña sigue vivo en la matriz de permisos de la API)
# -------------------------------------------------------------
@app.route("/terminal")
@login_required
def view_terminal():
    spa = _servir_spa_si_existe()
    if spa is not None:
        return spa
    return _spa_no_construida()


@app.route("/naviera")
@login_required
def view_naviera():
    spa = _servir_spa_si_existe()
    if spa is not None:
        return spa
    return _spa_no_construida()


@app.route("/agente")
@login_required
def view_agente():
    spa = _servir_spa_si_existe()
    if spa is not None:
        return spa
    return _spa_no_construida()


@app.route("/autoridad")
@login_required
def view_autoridad():
    spa = _servir_spa_si_existe()
    if spa is not None:
        return spa
    return _spa_no_construida()


# -------------------------------------------------------------
# EVENT STREAMING (SSE) - SIN POLLING (REQUISITO ESTRICTO)
# -------------------------------------------------------------
@app.route("/api/stream/events")
@login_required
def sse_events():
    def event_generator():
        q = queue.Queue(maxsize=100)
        with event_queues_lock:
            event_queues.append(q)

        # Enviar estado inicial completo de inmediato (con parqueo sincronizado)
        _refresh_parqueo_state()
        init_payload = json.dumps({"topic": "portus/init", "state": terminal_state})
        yield f"data: {init_payload}\n\n"

        try:
            while True:
                try:
                    event = q.get(timeout=10.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Keepalive SSE cada 10 segundos
                    yield ": keepalive\n\n"
        finally:
            with event_queues_lock:
                if q in event_queues:
                    event_queues.remove(q)

    return Response(event_generator(), mimetype="text/event-stream")


# -------------------------------------------------------------
# API: COMANDOS REMOTOS (ROL TERMINAL)
# -------------------------------------------------------------
@app.route("/api/cmd/remote", methods=["POST"])
@login_required
@require_permission("emitir_comandos_remotos")
def execute_remote_command():
    data = request.get_json() or {}
    comando = data.get("comando")
    parametros = data.get("parametros", {})

    if not comando:
        return jsonify({"error": "Comando no especificado"}), 400

    # Publicar comando a portus/cmd/solicitud
    msg_id = str(uuid.uuid4())
    msg_out = {
        "id": msg_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "origen": "servidor",
        "tipo": "SolicitudComando",
        "comando": comando,
        "parametros": parametros,
        "usuario": session["user"]["username"]
    }

    if mqtt_client:
        mqtt_client.publish("portus/cmd/solicitud", json.dumps(msg_out), qos=1)

    return jsonify({"success": True, "message": f"Comando '{comando}' despachado al controlador"})


# -------------------------------------------------------------
# API: MANIFIESTOS (NAVIERA / TERMINAL / AGENTE / AUTORIDAD)
# -------------------------------------------------------------
@app.route("/api/manifiestos", methods=["GET"])
@login_required
@require_permission("ver_manifiesto_completo")
def list_manifiestos():
    user = session["user"]
    conn = get_db_connection()

    if user["rol"] == "NAVIERA":
        # Aislamiento estricto: solo sus propios manifiestos
        rows = conn.execute("""
        SELECT * FROM manifiestos WHERE naviera_id = ? ORDER BY id DESC
        """, (user["username"],)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM manifiestos ORDER BY id DESC").fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/manifiestos", methods=["POST"])
@login_required
@require_permission("crear_manifiesto")
def create_manifiesto():
    data = request.get_json() or {}
    user = session["user"]

    contenedor_id = data.get("contenedor_id", "").strip().upper()
    tipo_operacion = data.get("tipo_operacion")
    peso_declarado = data.get("peso_declarado")
    tolerancia = data.get("tolerancia", 5.0)
    transportista_id = data.get("transportista_id")
    observaciones = data.get("observaciones", "")

    # Validaciones obligatorias
    if not contenedor_id or not tipo_operacion or peso_declarado is None or not transportista_id:
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    try:
        peso_declarado = int(peso_declarado)
        if peso_declarado <= 0:
            return jsonify({"error": "El peso declarado debe ser mayor que cero"}), 400
    except ValueError:
        return jsonify({"error": "Peso declarado invalido"}), 400

    try:
        tolerancia = float(tolerancia)
    except ValueError:
        tolerancia = 5.0

    conn = get_db_connection()
    # 1. Validar que exista en catalogo
    cat = conn.execute("SELECT id FROM catalogo_contenedores WHERE id = ?", (contenedor_id,)).fetchone()
    if not cat:
        conn.close()
        return jsonify({"error": f"El contenedor '{contenedor_id}' no existe en el catalogo oficial de la maqueta"}), 400

    # 2. Regla: Un contenedor no podra tener dos manifiestos pendientes al mismo tiempo
    pendiente = conn.execute("""
    SELECT id FROM manifiestos
    WHERE contenedor_id = ? AND estado_documental NOT IN ('CERRADO', 'ANULADO')
    """, (contenedor_id,)).fetchone()
    if pendiente:
        conn.close()
        return jsonify({"error": f"El contenedor '{contenedor_id}' ya posee un manifiesto activo ({pendiente['id']})"}), 400

    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM manifiestos")
    count = c.fetchone()["count"] + 1
    manif_id = f"MAN-{count:04d}"

    now = datetime.now(timezone.utc).isoformat()
    c.execute("""
    INSERT INTO manifiestos (
        id, contenedor_id, naviera_id, tipo_operacion, peso_declarado_g,
        tolerancia_pct, transportista_id, observaciones, estado_documental,
        created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CREADO', ?, ?)
    """, (manif_id, contenedor_id, user["username"], tipo_operacion, peso_declarado, tolerancia, transportista_id, observaciones, now, now))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "id": manif_id, "message": "Manifiesto declarado exitosamente"})


@app.route("/api/manifiestos/<manif_id>/anular", methods=["POST"])
@login_required
@require_permission("crear_manifiesto")
def anular_manifiesto(manif_id):
    user = session["user"]
    conn = get_db_connection()
    manif = conn.execute("SELECT * FROM manifiestos WHERE id = ?", (manif_id,)).fetchone()

    if not manif:
        conn.close()
        return jsonify({"error": "Manifiesto no encontrado"}), 404

    if manif["naviera_id"] != user["username"]:
        conn.close()
        return jsonify({"error": "No puede anular manifiestos de otra naviera"}), 403

    # Verificar que no tenga turno asociado
    turno = conn.execute("SELECT id FROM turnos WHERE manifiesto_id = ?", (manif_id,)).fetchone()
    if turno:
        conn.close()
        return jsonify({"error": "No se puede anular un manifiesto que ya posee un turno asociado"}), 400

    conn.execute("UPDATE manifiestos SET estado_documental = 'ANULADO' WHERE id = ?", (manif_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Manifiesto anulado exitosamente"})


# -------------------------------------------------------------
# API: CATALOGOS PARA FORMULARIOS DE LA SPA
# -------------------------------------------------------------
@app.route("/api/transportistas")
@login_required
def list_transportistas():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT username, nombre_completo FROM usuarios WHERE rol = 'TRANSPORTISTA' ORDER BY username"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/catalogo/contenedores")
@login_required
def list_catalogo_contenedores():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, tipo, tara_g FROM catalogo_contenedores ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# -------------------------------------------------------------
# API: DECLARACIONES Y LEVANTE ADUANERO (AGENTE / AUTORIDAD)
# -------------------------------------------------------------
@app.route("/api/declaraciones", methods=["GET"])
@login_required
@require_permission("ver_manifiesto_completo")
def list_declaraciones():
    manifiesto_id = request.args.get("manifiesto_id")
    conn = get_db_connection()
    if manifiesto_id:
        rows = conn.execute(
            "SELECT * FROM declaraciones WHERE manifiesto_id = ? ORDER BY id DESC",
            (manifiesto_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM declaraciones ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/declaraciones", methods=["POST"])
@login_required
@require_permission("presentar_declaracion")
def create_declaracion():
    data = request.get_json() or {}
    user = session["user"]

    manifiesto_id = data.get("manifiesto_id")
    numero_declaracion = data.get("numero_declaracion", "").strip()
    regimen = data.get("regimen")
    descripcion_mercancia = data.get("descripcion_mercancia", "").strip()
    valor_declarado = data.get("valor_declarado")
    observaciones = data.get("observaciones", "")

    if not manifiesto_id or not numero_declaracion or not regimen or not descripcion_mercancia or valor_declarado is None:
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    if len(descripcion_mercancia) < 10:
        return jsonify({"error": "La descripcion de mercancia debe contener minimo 10 caracteres"}), 400

    try:
        valor_declarado = float(valor_declarado)
        if valor_declarado <= 0:
            return jsonify({"error": "El valor declarado debe ser mayor que cero"}), 400
    except ValueError:
        return jsonify({"error": "Valor declarado invalido"}), 400

    conn = get_db_connection()
    c = conn.cursor()

    try:
        now = datetime.now(timezone.utc).isoformat()
        c.execute("""
        INSERT INTO declaraciones (
            numero_declaracion, manifiesto_id, agente_id, regimen,
            descripcion_mercancia, valor_declarado, observaciones, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (numero_declaracion, manifiesto_id, user["username"], regimen, descripcion_mercancia, valor_declarado, observaciones, now))

        c.execute("""
        UPDATE manifiestos SET estado_documental = 'DECLARADO', updated_at = ? WHERE id = ?
        """, (now, manifiesto_id))

        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({"error": f"Error al registrar declaracion: {e}"}), 400

    conn.close()
    return jsonify({"success": True, "message": "Declaracion de mercancias presentada exitosamente"})


@app.route("/api/declaraciones/solicitar-levante", methods=["POST"])
@login_required
@require_permission("presentar_declaracion")
def solicitar_levante():
    data = request.get_json() or {}
    manifiesto_id = data.get("manifiesto_id")

    conn = get_db_connection()
    manif = conn.execute("SELECT * FROM manifiestos WHERE id = ?", (manifiesto_id,)).fetchone()
    if not manif:
        conn.close()
        return jsonify({"error": "Manifiesto no encontrado"}), 404

    if manif["estado_documental"] != "DECLARADO":
        conn.close()
        return jsonify({"error": "Solo se puede solicitar levante para manifiestos con declaracion presentada"}), 400

    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
    UPDATE manifiestos SET estado_documental = 'LEVANTE_SOLICITADO', updated_at = ? WHERE id = ?
    """, (now, manifiesto_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Solicitud de levante enviada a la Autoridad Aduanera"})


@app.route("/api/autoridad/resolver-levante", methods=["POST"])
@login_required
@require_permission("otorgar_retener_levante")
def resolver_levante():
    data = request.get_json() or {}
    manifiesto_id = data.get("manifiesto_id")
    decision = data.get("decision")  # 'OTORGAR' o 'RETENER'
    canal = data.get("canal")  # 'VERDE' o 'ROJO' (obligatorio si OTORGAR)
    motivo = data.get("motivo", "")

    if not manifiesto_id or decision not in ("OTORGAR", "RETENER"):
        return jsonify({"error": "Decision invalida"}), 400

    if decision == "OTORGAR" and canal not in ("VERDE", "ROJO"):
        return jsonify({"error": "Debe seleccionar canal VERDE o ROJO al otorgar levante"}), 400

    if decision == "RETENER" and not motivo:
        return jsonify({"error": "Debe registrar el motivo de la retencion del levante"}), 400

    conn = get_db_connection()
    manif = conn.execute("SELECT * FROM manifiestos WHERE id = ?", (manifiesto_id,)).fetchone()
    if not manif:
        conn.close()
        return jsonify({"error": "Manifiesto no encontrado"}), 404

    now = datetime.now(timezone.utc).isoformat()
    if decision == "OTORGAR":
        conn.execute("""
        UPDATE manifiestos
        SET estado_documental = 'LEVANTE_OTORGADO', canal_selectivo = ?, updated_at = ?
        WHERE id = ?
        """, (canal, now, manifiesto_id))
        conn.commit()
        conn.close()

        # Notificacion automatica obligatoria al transportista
        msg_service.notify_levante_otorgado(manif["transportista_id"], manif["contenedor_id"], canal)
        return jsonify({"success": True, "message": f"Levante otorgado con canal {canal}"})
    else:
        conn.execute("""
        UPDATE manifiestos
        SET estado_documental = 'LEVANTE_RETENIDO', observaciones = ?, updated_at = ?
        WHERE id = ?
        """, (f"Retenido por SAT: {motivo}", now, manifiesto_id))
        conn.commit()
        conn.close()

        # Notificacion automatica obligatoria
        msg_service.notify_levante_retenido(manif["transportista_id"], manif["contenedor_id"], motivo)
        return jsonify({"success": True, "message": "Levante retenido por Autoridad Aduanera"})


# -------------------------------------------------------------
# API: TURNOS Y OPERACION
# -------------------------------------------------------------
@app.route("/api/turnos", methods=["GET"])
@login_required
def list_turnos():
    conn = get_db_connection()
    estado = request.args.get("estado")
    tipo = request.args.get("tipo")
    busqueda = request.args.get("q")

    query = "SELECT * FROM turnos WHERE 1=1"
    params = []

    if estado:
        query += " AND estado_actual = ?"
        params.append(estado)
    if tipo:
        query += " AND tipo_operacion = ?"
        params.append(tipo)
    if busqueda:
        query += " AND (placa_vehiculo LIKE ? OR contenedor_id LIKE ? OR codigo_turno LIKE ?)"
        b_wild = f"%{busqueda}%"
        params.extend([b_wild, b_wild, b_wild])

    query += " ORDER BY id DESC LIMIT 100"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    turnos_list = []
    now = datetime.now(timezone.utc)
    for r in rows:
        item = dict(r)
        transcurrido_min = 0
        try:
            t_ini = datetime.fromisoformat(item["tiempo_inicio"])
            t_fin = datetime.fromisoformat(item["tiempo_fin"]) if item["tiempo_fin"] else now
            transcurrido_min = int((t_fin - t_ini).total_seconds() / 60)
        except Exception:
            pass
        item["tiempo_transcurrido_min"] = transcurrido_min
        turnos_list.append(item)

    return jsonify(turnos_list)


@app.route("/api/turnos/<int:turno_id>/timeline", methods=["GET"])
@login_required
def get_timeline(turno_id):
    timeline = get_turn_timeline(turno_id)
    return jsonify(timeline)


@app.route("/api/turnos/<int:turno_id>/retener-manual", methods=["POST"])
@login_required
@require_permission("resolver_retencion_operativa")
def retener_turno_manual(turno_id):
    data = request.get_json(silent=True) or {}
    observacion = data.get("observacion", "Retencion manual por operador")

    res = assign_retention(turno_id, "RT06", estacion="GARITA", observacion=observacion)
    if not res:
        raise_alarm("AL11", origen="servidor", datos={"descripcion": "Parqueo de retencion lleno"})
        return jsonify({"error": "Parqueo de retencion lleno (3 plazas ocupadas). No se puede enviar el vehiculo a retencion."}), 400

    # Emitir comando AgujaParqueo
    if mqtt_client:
        mqtt_client.publish("portus/cmd/solicitud", json.dumps({
            "comando": "AgujaParqueo", "parametros": {"plaza": res["plaza"]}
        }))

    # Notificacion automatica obligatoria al transportista dueño del turno
    conn = get_db_connection()
    turno = conn.execute("SELECT * FROM turnos WHERE id = ?", (turno_id,)).fetchone()
    conn.close()
    if turno:
        aviso = msg_service.notify_vehiculo_retenido(
            turno["transportista_id"], turno["placa_vehiculo"], turno["contenedor_id"], "RT06"
        )
        logging.info("Notificacion a transportista: %s", aviso)

    _refresh_parqueo_state()
    dispatch_event_to_sse({"topic": "portus/evt/retencion", "data": {"tipo": "RetencionCreada", "datos": res}})
    return jsonify({"success": True, "retencion": res, "message": f"Turno retenido en plaza {res['plaza']}"})


@app.route("/api/turnos/<int:turno_id>/anular", methods=["POST"])
@login_required
@require_permission("emitir_comandos_remotos")
def anular_turno(turno_id):
    ok = transition_turn(turno_id, "Anulado", estacion="SALIDA", origen="usuario", detalle="Turno anulado manualmente por operador")
    if not ok:
        return jsonify({"error": "No se puede anular el turno en su estado actual"}), 400

    conn = get_db_connection()
    turno = conn.execute("SELECT * FROM turnos WHERE id = ?", (turno_id,)).fetchone()
    conn.close()
    if turno:
        aviso = msg_service.notify_turno_anulado(
            turno["transportista_id"], turno["placa_vehiculo"], turno["contenedor_id"],
            "Anulacion manual por operador de terminal"
        )
        logging.info("Notificacion a transportista: %s", aviso)
    dispatch_event_to_sse({"topic": "portus/evt/turnos", "data": {"tipo": "TurnoAnulado", "datos": {"turno_id": turno_id}}})

    return jsonify({"success": True, "message": "Turno anulado"})


# -------------------------------------------------------------
# API: RETENCIONES Y PARQUEO (3 PLAZAS)
# -------------------------------------------------------------
@app.route("/api/retenciones", methods=["GET"])
@login_required
def list_retenciones():
    estado = request.args.get("estado")
    causa = request.args.get("causa")
    user_rol = session["user"]["rol"]

    conn = get_db_connection()
    query = """
    SELECT r.*, t.codigo_turno, t.placa_vehiculo, t.transportista_id
    FROM retenciones r
    JOIN turnos t ON r.turno_id = t.id
    WHERE 1=1
    """
    params = []

    if user_rol == "AUTORIDAD":
        # Autoridad solo ve retenciones de causa aduanera (RT03 y RT05)
        query += " AND r.causa IN ('RT03', 'RT05')"
    elif user_rol == "TERMINAL":
        pass  # Terminal ve todas en su pestaña de retenciones

    if estado:
        query += " AND r.estado = ?"
        params.append(estado)
    if causa:
        query += " AND r.causa = ?"
        params.append(causa)

    query += " ORDER BY r.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    now = datetime.now(timezone.utc)
    results = []
    for r in rows:
        item = dict(r)
        duracion_min = 0
        try:
            t_ini = datetime.fromisoformat(item["tiempo_inicio"])
            t_fin = datetime.fromisoformat(item["tiempo_resolucion"]) if item["tiempo_resolucion"] else now
            duracion_min = int((t_fin - t_ini).total_seconds() / 60)
        except Exception:
            pass
        item["tiempo_retencion_min"] = duracion_min
        results.append(item)

    return jsonify(results)


@app.route("/api/retenciones/<int:ret_id>/resolver", methods=["POST"])
@login_required
def resolve_retention_endpoint(ret_id):
    data = request.get_json() or {}
    resolucion = data.get("resolucion")  # 'ACLARAR', 'CORREGIR', 'RECHAZAR'
    motivo = data.get("motivo_rechazo")
    observacion = data.get("observacion")

    user = session["user"]
    res = resolve_retention(ret_id, resolucion, user["username"], user["rol"], motivo, observacion)

    if not res.get("success"):
        return jsonify({"error": res.get("error")}), 400

    # Comandar AgujaLiberar via MQTT al controlador
    if mqtt_client:
        mqtt_client.publish("portus/cmd/solicitud", json.dumps({
            "comando": "AgujaLiberar",
            "parametros": {"plaza": res["plaza_liberada"]}
        }))

    # Regla obligatoria: toda resolucion notifica al transportista propietario
    conn = get_db_connection()
    turno = conn.execute("SELECT * FROM turnos WHERE id = ?", (res["turno_id"],)).fetchone()
    ret = conn.execute("SELECT * FROM retenciones WHERE id = ?", (ret_id,)).fetchone()
    conn.close()
    if turno and ret:
        aviso = msg_service.notify_retencion_resuelta(
            turno["transportista_id"], turno["placa_vehiculo"], turno["contenedor_id"],
            resolucion,
            nuevo_peso=ret["peso_medido_g"] if resolucion == "CORREGIR" else None,
            motivo=motivo if resolucion == "RECHAZAR" else None
        )
        logging.info("Notificacion a transportista: %s", aviso)

    _refresh_parqueo_state()
    dispatch_event_to_sse({"topic": "portus/evt/retencion", "data": {"tipo": "RetencionResuelta", "datos": res}})
    return jsonify(res)


# -------------------------------------------------------------
# API: PATIO Y GRUA
# -------------------------------------------------------------
@app.route("/api/patio", methods=["GET"])
@login_required
def get_patio():
    inv = get_yard_inventory()
    return jsonify(inv)


@app.route("/api/patio/posicion/<int:pos>/bloquear", methods=["POST"])
@login_required
@require_permission("emitir_comandos_remotos")
def bloquear_posicion(pos):
    set_position_blocked(pos, True)
    if mqtt_client:
        mqtt_client.publish("portus/cmd/solicitud", json.dumps({
            "comando": "PosicionBloquear", "parametros": {"posicion": pos}
        }))
    return jsonify({"success": True, "message": f"Posicion {pos} bloqueada"})


@app.route("/api/patio/posicion/<int:pos>/liberar", methods=["POST"])
@login_required
@require_permission("emitir_comandos_remotos")
def liberar_posicion(pos):
    set_position_blocked(pos, False)
    if mqtt_client:
        mqtt_client.publish("portus/cmd/solicitud", json.dumps({
            "comando": "PosicionLiberar", "parametros": {"posicion": pos}
        }))
    return jsonify({"success": True, "message": f"Posicion {pos} liberada"})


@app.route("/api/grua/historial", methods=["GET"])
@login_required
def get_grua_history_api():
    limit = int(request.args.get("limit", 50))
    hist = get_crane_history(limit)
    return jsonify(hist)


# -------------------------------------------------------------
# API: ALARMAS (CATALOGO AL01-AL14)
# -------------------------------------------------------------
@app.route("/api/alarmas", methods=["GET"])
@login_required
def list_alarmas():
    sev = request.args.get("severidad")
    alarms = get_alarms(sev)
    return jsonify(alarms)


@app.route("/api/alarmas/<int:alarm_id>/reconocer", methods=["POST"])
@login_required
@require_permission("reconocer_alarmas")
def ack_alarm(alarm_id):
    data = request.get_json() or {}
    comentario = data.get("comentario")
    user = session["user"]["username"]
    ok = acknowledge_alarm(alarm_id, user, comentario)
    if not ok:
        return jsonify({"error": "La alarma no existe o ya fue reconocida"}), 400
    return jsonify({"success": True, "message": "Alarma reconocida"})


@app.route("/api/alarmas/reconocer-todas", methods=["POST"])
@login_required
@require_permission("reconocer_alarmas")
def ack_all_alarms():
    user = session["user"]["username"]
    count = acknowledge_all_low_medium(user)
    return jsonify({"success": True, "reconocidas": count, "message": f"{count} alarmas de severidad baja y media reconocidas"})


@app.route("/api/turnos", methods=["POST"])
@login_required
@require_permission("emitir_comandos_remotos")
def crear_turno_desde_plataforma():
    """
    Registra la presentacion de un vehiculo en la garita. Replica la validacion
    que realiza el servidor al recibir la identificacion del controlador:
    manifiesto con levante otorgado (efecto fisico obligatorio sobre la
    talanquera), vehiculo registrado y cumplimiento de la ventana de la cita.
    Un ingreso rechazado no crea turno (regla de la maquina de estados).
    """
    data = request.get_json() or {}
    placa = (data.get("placa_vehiculo") or "").strip().upper()
    manifiesto_id = (data.get("manifiesto_id") or "").strip().upper()

    if not placa or not manifiesto_id:
        return jsonify({"error": "Debe indicar la placa del vehiculo y el manifiesto"}), 400

    conn = get_db_connection()

    camion = conn.execute(
        "SELECT * FROM catalogo_camiones WHERE placa = ?", (placa,)
    ).fetchone()
    if not camion:
        conn.close()
        return jsonify({"error": f"Vehiculo '{placa}' no registrado en el catalogo. Ingreso rechazado."}), 400

    manif = conn.execute("SELECT * FROM manifiestos WHERE id = ?", (manifiesto_id,)).fetchone()
    if not manif:
        conn.close()
        return jsonify({"error": f"Manifiesto '{manifiesto_id}' no encontrado. Ingreso rechazado."}), 400

    if manif["estado_documental"] == "LEVANTE_RETENIDO":
        conn.close()
        return jsonify({
            "error": "La talanquera no se abre: el manifiesto tiene el levante RETENIDO por la Autoridad Aduanera.",
            "causa_rechazo": "LEVANTE_RETENIDO"
        }), 400

    if manif["estado_documental"] != "LEVANTE_OTORGADO":
        conn.close()
        return jsonify({
            "error": f"La talanquera no se abre: el manifiesto no tiene levante otorgado (estado: {manif['estado_documental']}).",
            "causa_rechazo": "SIN_LEVANTE"
        }), 400

    if camion["transportista_id"] != manif["transportista_id"]:
        conn.close()
        return jsonify({"error": "El vehiculo no pertenece al transportista asignado al manifiesto. Ingreso rechazado."}), 400

    turno_activo = conn.execute("""
    SELECT id FROM turnos
    WHERE placa_vehiculo = ? AND estado_actual NOT IN ('Cerrado', 'Anulado')
    """, (placa,)).fetchone()
    if turno_activo:
        conn.close()
        return jsonify({"error": f"El vehiculo {placa} ya tiene un turno activo dentro de la terminal."}), 400

    # Control de ventana: cita vigente del contenedor para hoy
    ahora = datetime.now()
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    cita = conn.execute("""
    SELECT * FROM citas
    WHERE contenedor_id = ? AND fecha = ? AND estado = 'PROGRAMADA'
    ORDER BY id DESC LIMIT 1
    """, (manif["contenedor_id"], fecha_hoy)).fetchone()

    fuera_de_ventana = True
    cita_id = None
    if cita:
        try:
            h_ini = datetime.strptime(f"{cita['fecha']} {cita['hora_inicio']}", "%Y-%m-%d %H:%M")
            h_fin = datetime.strptime(f"{cita['fecha']} {cita['hora_fin']}", "%Y-%m-%d %H:%M")
            limite = h_fin.timestamp() + 5 * 60  # 5 minutos de tolerancia
            fuera_de_ventana = not (h_ini.timestamp() <= ahora.timestamp() <= limite)
            cita_id = cita["id"]
        except Exception:
            fuera_de_ventana = True

    riesgo_retencion = fuera_de_ventana or manif["canal_selectivo"] == "ROJO"

    # E11: parqueo lleno y vehiculo con riesgo de retencion -> garita rechaza el ingreso
    if riesgo_retencion:
        plazas = get_parking_occupancy()
        if all(p is not None for p in plazas.values()):
            conn.close()
            raise_alarm("AL11", origen="servidor", datos={"descripcion": "Parqueo de retencion lleno: ingreso rechazado en garita"})
            return jsonify({
                "error": "Ingreso rechazado: parqueo de retencion lleno (3/3 plazas ocupadas) y el vehiculo presenta riesgo de retencion.",
                "causa_rechazo": "PARQUEO_LLENO"
            }), 400

    turno_id = create_turn(
        placa=placa,
        transportista_id=manif["transportista_id"],
        contenedor_id=manif["contenedor_id"],
        tipo_operacion=manif["tipo_operacion"],
        manifiesto_id=manif["id"],
        cita_id=cita_id,
        peso_declarado_g=manif["peso_declarado_g"]
    )

    respuesta = {
        "success": True,
        "turno_id": turno_id,
        "message": f"Turno creado. Talanquera abierta para el vehiculo {placa}."
    }

    if cita and not fuera_de_ventana:
        conn.execute(
            "UPDATE citas SET estado = 'CUMPLIDA', cumplida_en_ventana = 1 WHERE id = ?",
            (cita["id"],)
        )
        conn.commit()
    conn.close()

    # RT04: llegada fuera de la ventana asignada -> retencion y desvio al parqueo
    if fuera_de_ventana:
        res = assign_retention(
            turno_id=turno_id,
            causa="RT04",
            estacion="GARITA",
            observacion="Llegada fuera de la ventana asignada a la cita"
        )
        if res:
            if mqtt_client:
                mqtt_client.publish("portus/cmd/solicitud", json.dumps({
                    "comando": "AgujaParqueo", "parametros": {"plaza": res["plaza"]}
                }))
            aviso = msg_service.notify_vehiculo_retenido(
                manif["transportista_id"], placa, manif["contenedor_id"], "RT04"
            )
            logging.info("Notificacion a transportista: %s", aviso)
            _refresh_parqueo_state()
            dispatch_event_to_sse({"topic": "portus/evt/retencion", "data": {"tipo": "RetencionCreada", "datos": res}})
            respuesta["retencion"] = res
            respuesta["message"] = f"Vehiculo {placa} ingreso FUERA DE VENTANA. Retencion RT04 asignada a plaza {res['plaza']}."
        else:
            raise_alarm("AL11", origen="servidor", datos={"descripcion": "Parqueo de retencion lleno"})
            respuesta["advertencia"] = "Parqueo lleno: el vehiculo permanece en garita a la espera de plaza."

    terminal_state["garita"]["estado"] = "Autorizada"
    terminal_state["garita"]["vehiculo"] = placa
    dispatch_event_to_sse({"topic": "portus/evt/garita", "data": {"tipo": "TurnoCreado", "datos": {"placa": placa, "turno_id": turno_id}}})

    return jsonify(respuesta)


# -------------------------------------------------------------
# API: CITAS
# -------------------------------------------------------------
@app.route("/api/citas", methods=["GET"])
@login_required
def list_citas():
    conn = get_db_connection()
    fecha = request.args.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    citas = conn.execute("SELECT * FROM citas WHERE fecha = ? ORDER BY hora_inicio ASC", (fecha,)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in citas])


def _datos_cita(cita_id):
    conn = get_db_connection()
    cita = conn.execute("SELECT * FROM citas WHERE id = ?", (cita_id,)).fetchone()
    conn.close()
    return dict(cita) if cita else None


def _franja_ocupacion(fecha: str, hora_inicio: str, excluir_cita_id=None) -> int:
    conn = get_db_connection()
    if excluir_cita_id:
        row = conn.execute("""
        SELECT COUNT(*) as c FROM citas
        WHERE fecha = ? AND hora_inicio = ? AND estado = 'PROGRAMADA' AND id != ?
        """, (fecha, hora_inicio, excluir_cita_id)).fetchone()
    else:
        row = conn.execute("""
        SELECT COUNT(*) as c FROM citas
        WHERE fecha = ? AND hora_inicio = ? AND estado = 'PROGRAMADA'
        """, (fecha, hora_inicio)).fetchone()
    conn.close()
    return row["c"]


def _franja_bloqueada(fecha: str, hora_inicio: str) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id FROM franjas_bloqueadas WHERE fecha = ? AND hora_inicio = ?",
        (fecha, hora_inicio)
    ).fetchone()
    conn.close()
    return row is not None


def _hora_fin_de(hora_inicio: str) -> str:
    h_ini = datetime.strptime(hora_inicio, "%H:%M")
    return (h_ini + timedelta(minutes=15)).strftime("%H:%M")


@app.route("/api/citas/franjas-bloqueadas", methods=["GET"])
@login_required
@require_permission("ver_agenda_completa_citas")
def list_franjas_bloqueadas():
    conn = get_db_connection()
    fecha = request.args.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    rows = conn.execute(
        "SELECT * FROM franjas_bloqueadas WHERE fecha = ? ORDER BY hora_inicio ASC",
        (fecha,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/citas/<int:cita_id>/cancelar", methods=["POST"])
@login_required
@require_permission("ver_agenda_completa_citas")
def cancelar_cita(cita_id):
    data = request.get_json(silent=True) or {}
    motivo = data.get("motivo", "Cancelada por el operador de terminal")

    cita = _datos_cita(cita_id)
    if not cita:
        return jsonify({"error": "Cita no encontrada"}), 404
    if cita["estado"] != "PROGRAMADA":
        return jsonify({"error": "Solo puede cancelarse una cita en estado PROGRAMADA"}), 400

    conn = get_db_connection()
    conn.execute("UPDATE citas SET estado = 'CANCELADA' WHERE id = ?", (cita_id,))
    conn.commit()
    conn.close()

    aviso = msg_service.notify_cita_cancelada_reprogramada(
        cita["transportista_id"], cita["contenedor_id"], "cancelada"
    )
    logging.info("Notificacion a transportista: %s (motivo: %s)", aviso, motivo)

    dispatch_event_to_sse({"topic": "portus/evt/citas", "data": {"tipo": "CitaCancelada", "datos": {"cita_id": cita_id}}})
    return jsonify({"success": True, "message": f"Cita del contenedor {cita['contenedor_id']} cancelada y transportista notificado"})


@app.route("/api/citas/<int:cita_id>/reprogramar", methods=["POST"])
@login_required
@require_permission("ver_agenda_completa_citas")
def reprogramar_cita(cita_id):
    data = request.get_json() or {}
    fecha_nueva = (data.get("fecha") or "").strip()
    hora_nueva = (data.get("hora_inicio") or "").strip()

    if not fecha_nueva or not hora_nueva:
        return jsonify({"error": "Debe indicar la fecha y la hora de inicio de la franja nueva"}), 400

    try:
        datetime.strptime(fecha_nueva, "%Y-%m-%d")
        hora_fin_nueva = _hora_fin_de(hora_nueva)
    except (ValueError, TypeError):
        return jsonify({"error": "Formato invalido. Fecha AAAA-MM-DD y hora HH:MM"}), 400

    cita = _datos_cita(cita_id)
    if not cita:
        return jsonify({"error": "Cita no encontrada"}), 404
    if cita["estado"] != "PROGRAMADA":
        return jsonify({"error": "Solo puede reprogramarse una cita en estado PROGRAMADA"}), 400

    if _franja_bloqueada(fecha_nueva, hora_nueva):
        return jsonify({"error": f"La franja {fecha_nueva} {hora_nueva} esta bloqueada y no admite nuevas citas"}), 400

    if _franja_ocupacion(fecha_nueva, hora_nueva, excluir_cita_id=cita_id) >= 2:
        return jsonify({"error": f"La franja {fecha_nueva} {hora_nueva} esta llena (2/2 citas). Seleccione otra franja."}), 400

    conn = get_db_connection()
    conn.execute("""
    UPDATE citas SET fecha = ?, hora_inicio = ?, hora_fin = ?, cumplida_en_ventana = 0
    WHERE id = ?
    """, (fecha_nueva, hora_nueva, hora_fin_nueva, cita_id))
    conn.commit()
    conn.close()

    aviso = msg_service.notify_cita_cancelada_reprogramada(
        cita["transportista_id"], cita["contenedor_id"], "reprogramada",
        nueva_ventana=f"{fecha_nueva} de {hora_nueva} a {hora_fin_nueva}"
    )
    logging.info("Notificacion a transportista: %s", aviso)

    dispatch_event_to_sse({"topic": "portus/evt/citas", "data": {"tipo": "CitaReprogramada", "datos": {"cita_id": cita_id}}})
    return jsonify({"success": True, "message": f"Cita reprogramada a {fecha_nueva} {hora_nueva}-{hora_fin_nueva} y notificada al transportista"})


@app.route("/api/citas/bloquear-franja", methods=["POST"])
@login_required
@require_permission("ver_agenda_completa_citas")
def bloquear_franja():
    data = request.get_json() or {}
    fecha = (data.get("fecha") or "").strip()
    hora_inicio = (data.get("hora_inicio") or "").strip()

    if not fecha or not hora_inicio:
        return jsonify({"error": "Debe indicar fecha (AAAA-MM-DD) y hora de inicio (HH:MM) de la franja"}), 400

    try:
        datetime.strptime(fecha, "%Y-%m-%d")
        hora_fin = _hora_fin_de(hora_inicio)
    except (ValueError, TypeError):
        return jsonify({"error": "Formato invalido. Fecha AAAA-MM-DD y hora HH:MM"}), 400

    if _franja_bloqueada(fecha, hora_inicio):
        return jsonify({"error": "La franja ya se encuentra bloqueada"}), 400

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    conn.execute("""
    INSERT INTO franjas_bloqueadas (fecha, hora_inicio, hora_fin, creado_por, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (fecha, hora_inicio, hora_fin, session["user"]["username"], now))
    conn.commit()
    conn.close()

    dispatch_event_to_sse({"topic": "portus/evt/citas", "data": {"tipo": "FranjaBloqueada", "datos": {"fecha": fecha, "hora_inicio": hora_inicio}}})
    return jsonify({"success": True, "message": f"Franja {fecha} {hora_inicio}-{hora_fin} bloqueada: no admite nuevas citas"})


@app.route("/api/citas/desbloquear-franja", methods=["POST"])
@login_required
@require_permission("ver_agenda_completa_citas")
def desbloquear_franja():
    data = request.get_json() or {}
    fecha = (data.get("fecha") or "").strip()
    hora_inicio = (data.get("hora_inicio") or "").strip()

    conn = get_db_connection()
    cur = conn.execute(
        "DELETE FROM franjas_bloqueadas WHERE fecha = ? AND hora_inicio = ?",
        (fecha, hora_inicio)
    )
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        return jsonify({"error": "La franja no estaba bloqueada"}), 400

    dispatch_event_to_sse({"topic": "portus/evt/citas", "data": {"tipo": "FranjaDesbloqueada", "datos": {"fecha": fecha, "hora_inicio": hora_inicio}}})
    return jsonify({"success": True, "message": f"Franja {fecha} {hora_inicio} desbloqueada"})


# -------------------------------------------------------------
# API: REPORTES Y METRICAS DE CORRIDA
# -------------------------------------------------------------
@app.route("/api/reportes/calcular", methods=["GET"])
@login_required
@require_permission("generar_reporte_corrida")
def report_metrics():
    ini = request.args.get("inicio")
    fin = request.args.get("fin")
    metrics = calculate_metrics(ini, fin)
    return jsonify(metrics)


@app.route("/api/reportes/exportar-csv", methods=["POST"])
@login_required
@require_permission("generar_reporte_corrida")
def export_metrics_csv():
    data = request.get_json() or {}
    etiqueta = data.get("etiqueta", "Corrida de evaluacion")
    ini = data.get("inicio")
    fin = data.get("fin")

    metrics = calculate_metrics(ini, fin)
    csv_str = export_report_csv(etiqueta, metrics)

    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=reporte_{etiqueta.replace(' ', '_')}.csv"}
    )


# -------------------------------------------------------------
# API: VINCULACION DE TRANSPORTISTA
# -------------------------------------------------------------
@app.route("/api/transportista/generar-codigo", methods=["POST"])
@login_required
@require_permission("generar_codigo_vinculacion")
def gen_binding_code():
    data = request.get_json() or {}
    trans_id = data.get("transportista_id")
    if not trans_id:
        return jsonify({"error": "Debe especificar el transportista"}), 400

    codigo = generate_binding_code(trans_id, creado_por=session["user"]["username"])
    return jsonify({"success": True, "codigo": codigo, "expira_en_minutos": 60})


@app.route("/api/mensajeria/simulador", methods=["POST"])
def simular_comando_transportista():
    """
    Endpoint para probar interactivamente los 7 comandos del transportista
    desde un cliente web, consola o emulador de mensajeria.
    """
    data = request.get_json() or {}
    chat_id = data.get("chat_id", "sim_phone_01")
    texto = data.get("texto", "")

    respuesta = msg_service.process_message(chat_id, texto)
    return jsonify({"chat_id": chat_id, "respuesta": respuesta})


# -------------------------------------------------------------
# SERVICIO DE LA SPA REACT (modo produccion: frontend/dist)
# -------------------------------------------------------------
@app.route("/<path:ruta_spa>")
def servir_spa(ruta_spa):
    """
    En produccion la SPA se sirve desde frontend/dist. Las rutas /api/* ya
    fueron registradas con prioridad por Flask, asi que no se interceptan.
    En desarrollo (Vite en 5173 con proxy) esta ruta no se usa.
    """
    if ruta_spa.startswith("api/"):
        return jsonify({"error": "Recurso no encontrado"}), 404

    indice = os.path.join(FRONTEND_DIST, "index.html")
    if not os.path.isfile(indice):
        return _spa_no_construida()

    # Rutas del cliente como /terminal/operacion resuelven el index.html
    # salvo que el archivo exista fisicamente (assets de Vite).
    archivo = os.path.join(FRONTEND_DIST, ruta_spa)
    if os.path.isfile(archivo):
        return send_from_directory(FRONTEND_DIST, ruta_spa)
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    init_database()
    init_mqtt()
    app.run(host="0.0.0.0", port=5000, debug=False)
