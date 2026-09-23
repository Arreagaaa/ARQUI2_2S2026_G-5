"""
Control de autenticacion, sesiones y verificacion de matriz de permisos
estricta en servidor para PORTUS Fase 2.
"""

from functools import wraps
from flask import session, jsonify, request, redirect, url_for
from .database import get_db_connection, hash_password

# Matriz formal de permisos segun Seccion 2.3 del enunciado
# Columnas: TERMINAL, NAVIERA, AGENTE, AUTORIDAD, TRANSPORTISTA
PERMISOS_MATRIZ = {
    "crear_manifiesto": ["NAVIERA"],
    "ver_manifiesto_completo": ["TERMINAL", "NAVIERA", "AGENTE", "AUTORIDAD"],
    "presentar_declaracion": ["AGENTE"],
    "otorgar_retener_levante": ["AUTORIDAD"],
    "asignar_canal_selectivo": ["AUTORIDAD"],
    "solicitar_cita": ["TRANSPORTISTA"],
    "ver_agenda_completa_citas": ["TERMINAL"],
    "ver_sinoptico": ["TERMINAL"],
    "emitir_comandos_remotos": ["TERMINAL"],
    "reconocer_alarmas": ["TERMINAL"],
    "resolver_retencion_operativa": ["TERMINAL"],
    "resolver_retencion_aduanera": ["AUTORIDAD"],
    "corregir_peso_manifiesto": ["TERMINAL"],
    "consultar_ubicacion_contenedor": ["TERMINAL", "NAVIERA", "AGENTE", "AUTORIDAD", "TRANSPORTISTA"],
    "generar_reporte_corrida": ["TERMINAL"],
    "generar_codigo_vinculacion": ["TERMINAL"]
}


def authenticate_user(username: str, password: str):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT id, username, password_hash, nombre_completo, rol FROM usuarios WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()

    if not user:
        return None

    pwd_hash = hash_password(password)
    if user["password_hash"] == pwd_hash:
        return {
            "id": user["id"],
            "username": user["username"],
            "nombre_completo": user["nombre_completo"],
            "rol": user["rol"]
        }
    return None


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "No autenticado. Inicie sesion primero."}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


def require_permission(action: str):
    """
    Decorador que valida la matriz de permisos en backend.
    Si el rol del usuario en sesion no tiene permiso para la accion,
    devuelve un error HTTP 403 con mensaje explicito.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user" not in session:
                return jsonify({"error": "Sesion no valida"}), 401

            user_role = session["user"]["rol"]
            allowed_roles = PERMISOS_MATRIZ.get(action, [])

            if user_role not in allowed_roles:
                return jsonify({
                    "error": f"Accion '{action}' denegada para el rol '{user_role}'. Permiso insuficiente."
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator
