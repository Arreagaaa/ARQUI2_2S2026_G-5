"""Projection of observed Fase1 state. Never issues physical commands.

Firmware observations may skip intermediate states between two snapshots;
they are reconciled directly, not rejected by the administrative workflow.
Unknown positions, distances and container identities remain unknown.
"""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from .database import get_db_connection
from .alarm_manager import raise_alarm

CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'hardware_catalog.json').read_text(encoding='utf-8'))
CRANE_STATES = [
    'Inactiva', 'Referenciando', 'Confirmando referencia', 'Moviendo a origen',
    'Descendiendo a contacto', 'Verificando altura', 'Confirmando agarre',
    'Elevando carga', 'Esperando liberar marca', 'Trasladando a destino',
    'Descendiendo deposito', 'Confirmando colocacion', 'Retrayendo',
    'Actualizando inventario', 'Trabajo completado', 'Detenida / falla',
]
STATIONS = {0: ('Programado', 'SIN_ESTACION'), 1: ('Programado', 'ESPERA'),
            2: ('EnGarita', 'GARITA'), 3: ('EnPesajeEntrada', 'PESAJE'),
            4: ('Retenido', 'RAMAL'), 5: ('EnTransferencia', 'TRANSFERENCIA'),
            6: ('EnPesajeSalida', 'SALIDA'), 7: ('Cerrado', 'SALIDA')}


def initial_state():
    state = {
        'modo': 'DESCONOCIDO', 'enlace': 'DESCONECTADO', 'ultimo_latido_timestamp': '',
        'protocolo': 'fase1', 'fuente': 'SIN_DATOS', 'sincronizado': False,
        'garita': {'estado': 'Sin confirmar', 'vehiculo': None}, 'talanquera': 'Sin confirmar',
        'pesaje': {'estado': 'Sin confirmar', 'ultimo_valor_kg': None, 'resultado': 'Sin confirmar'},
        'aguja': 'Sin confirmar', 'parqueo': {},
        'transferencia': {'estado': 'Sin confirmar', 'vehiculo': None},
        'grua': {'estado': 'Sin confirmar', 'posicion': None, 'trabajo_en_curso': None,
                 'cola_pendientes': None, 'suspendida': False, 'referenciada': None, 'en_falla': False},
        'puerta_salida': 'Sin confirmar', 'zona_espera': {'cantidad_vehiculos': None},
        'vehiculos_dentro': None, 'patio_fisico': {}, 'paro_emergencia': False,
    }
    conn = get_db_connection()
    row = conn.execute('SELECT state FROM controller_state WHERE id=1').fetchone()
    conn.close()
    if row:
        state.update(json.loads(row['state']))
        state.update(enlace='DESCONECTADO', sincronizado=False)
    return state


def alarm_once(code, datos=None):
    conn = get_db_connection()
    exists = conn.execute('SELECT 1 FROM alarmas WHERE codigo=? AND reconocida=0', (code,)).fetchone()
    conn.close()
    if not exists:
        raise_alarm(code, datos=datos)


def _active(conn, plate=None):
    query = "SELECT * FROM turnos WHERE hardware_key IS NOT NULL AND estado_actual NOT IN ('Cerrado','Anulado')"
    return conn.execute(query + (' AND placa_vehiculo=?' if plate else '') + ' ORDER BY id', (plate,) if plate else ()).fetchall()


def _timeline(conn, tid, timestamp, text, values=None):
    conn.execute("INSERT INTO linea_tiempo_turno(turno_id,timestamp,origen,descripcion,valores_asociados) VALUES (?,?,'controlador',?,?)",
                 (tid, timestamp, text, json.dumps(values or {})))


def _turn(conn, plate, timestamp, local=None):
    rows = _active(conn, plate)
    if rows:
        if local is not None and rows[0]['hardware_key'].startswith('None:'):
            conn.execute('UPDATE turnos SET hardware_key=? WHERE id=?', (str(local)+':'+rows[0]['hardware_key'].split(':',1)[1],rows[0]['id']))
        return rows[0]
    config = CATALOG.get(plate)
    if not config:
        return None  # Unknown vehicle cannot be attributed to another carrier.
    manifest = conn.execute("SELECT * FROM manifiestos WHERE contenedor_id=? AND tipo_operacion=? ORDER BY created_at DESC LIMIT 1",
                            (config['contenedor'], config['operacion'])).fetchone()
    next_id = conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM turnos').fetchone()[0]
    cursor = conn.execute('''INSERT INTO turnos(codigo_turno,placa_vehiculo,transportista_id,contenedor_id,
        manifiesto_id,tipo_operacion,estado_actual,estacion_actual,peso_declarado_g,tiempo_inicio,hardware_key,naviera_id)
        VALUES (?,?,?,?,?,?,'EnGarita','GARITA',?,?,?,?)''',
        (f'TRN-{next_id:04d}', plate, config['transportista'], config['contenedor'],
         manifest['id'] if manifest else None, config['operacion'], config['peso_declarado_g'], timestamp,
         f'{local}:{uuid.uuid4().hex}', manifest['naviera_id'] if manifest else config['naviera']))
    _timeline(conn, cursor.lastrowid, timestamp, 'Turno fisico observado en Fase1; no implica levante documental', {'local': local})
    return conn.execute('SELECT * FROM turnos WHERE id=?', (cursor.lastrowid,)).fetchone()


def _observe(conn, row, status, station, timestamp, detail):
    if row is None:
        return
    if row['estado_actual'] != status or row['estacion_actual'] != station:
        _timeline(conn, row['id'], timestamp, detail, {'de_estado': row['estado_actual'], 'a_estado': status})
    end = timestamp if status in ('Cerrado', 'Anulado') else None
    duration = max(0, int((datetime.fromisoformat(timestamp) - datetime.fromisoformat(row['tiempo_inicio'])).total_seconds())) if end else 0
    conn.execute('UPDATE turnos SET estado_actual=?,estacion_actual=?,tiempo_fin=?,tiempo_total_seg=? WHERE id=?',
                 (status, station, end, duration, row['id']))


def process_event(state, event, topic):
    kind, data = event.get('tipo', ''), event.get('datos', {})
    if kind == 'INFO':
        from ..bridge.legacy_telemetry import LegacyTelemetry
        decoded = LegacyTelemetry().feed(str(data.get('info', '')))
        if decoded:
            kind, data = decoded
    timestamp = event.get('timestamp') or datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    # MQTT QoS1 may redeliver. State and history must be idempotent.
    event_id = event.get('id') or str(uuid.uuid4())
    result = conn.execute('INSERT OR IGNORE INTO controller_events VALUES (?,?,?,?)',
                          (event_id, timestamp, kind, json.dumps(data)))
    if result.rowcount == 0:
        conn.close()
        return False
    conn.commit()
    try:
        state['protocolo'] = event.get('protocolo', state.get('protocolo', 'fase1'))
        state['fuente'] = 'SIMULADOR' if state['protocolo'] == 'mock' else 'HARDWARE'
        if kind == 'EnlacePerdido':
            state['enlace'] = 'DESCONECTADO'
            state['sincronizado'] = False
        elif kind != 'AlarmaGenerada' and topic.startswith('portus/evt/'):
            state['enlace'] = 'CONECTADO'
            state['ultimo_latido_timestamp'] = timestamp

        if kind == 'SnapshotFase1':
            state.update(sincronizado=True, vehiculos_dentro=int(data['cantidad']),
                         paro_emergencia=bool(data['paro']), modo='EMERGENCIA' if data['paro'] else 'NORMAL')
            seen = set()
            for item in data['turnos']:
                row = _turn(conn, item['placa'], timestamp, item['turno_local'])
                if row is None:
                    continue
                seen.add(row['id'])
                station = int(item['estacion'])
                status, label = STATIONS.get(station, ('Programado', 'DESCONOCIDA'))
                # Fase1's ramal flag is not an administrative parking retention.
                retained = item['retenido'] == 'SI'
                _observe(conn, row, status, label, timestamp, f'Estacion fisica confirmada: {label}')
                conn.execute('UPDATE turnos SET retenido_fisico=? WHERE id=?', (int(retained), row['id']))
                if not state.get('telemetria_detallada') and (station >= 5 or float(item['entrada_kg']) != 0):
                    conn.execute('UPDATE turnos SET peso_medido_entrada_g=? WHERE id=?', (round(float(item['entrada_kg'])*1000), row['id']))
                if not state.get('telemetria_detallada') and float(item['salida_kg']) != 0:
                    conn.execute('UPDATE turnos SET peso_medido_salida_g=? WHERE id=?', (round(float(item['salida_kg'])*1000), row['id']))
            for row in _active(conn):
                if row['id'] not in seen:
                    # Missing from a complete snapshot means no longer active,
                    # but does not prove a successful operation after a reset.
                    _observe(conn, row, 'Anulado', 'SIN_ACTIVIDAD', timestamp,
                             'Reconciliacion: ya no figura activo en el controlador; cierre no observado')
            active = _active(conn)
            if not state.get('telemetria_detallada'):
                state['zona_espera']['cantidad_vehiculos'] = None
            at_gate = next((r for r in active if r['estacion_actual']=='GARITA'), None)
            state['garita'] = {'estado': 'Autorizada' if at_gate else 'Libre', 'vehiculo': at_gate['placa_vehiculo'] if at_gate else None}
            at_transfer = next((r for r in active if r['estacion_actual']=='TRANSFERENCIA'), None)
            state['transferencia'] = {'estado': 'Ocupada' if at_transfer else 'Libre', 'vehiculo': at_transfer['placa_vehiculo'] if at_transfer else None}
            if not state.get('telemetria_detallada'):
                state['aguja'] = 'Ramal' if any(r['retenido_fisico'] for r in active) else 'Sin confirmar'
            conn.commit()
            if data['paro']:
                alarm_once('AL02')
        elif kind == 'EstacionesDetalle':
            state.update(talanquera=data['talanquera'], aguja=data['aguja'], telemetria_detallada=True)
            state['zona_espera']['cantidad_vehiculos'] = int(data['espera'])
            state['transferencia']['estado'] = 'Ocupada' if data['transferencia']=='1' else 'Libre'
            state['pesaje_placa'] = data.get('pesaje_placa')
            state['salida_placa'] = data.get('salida_placa')
        elif kind == 'TurnoDetalle':
            row = _turn(conn, data['placa'], timestamp)
            if row:
                conn.execute('UPDATE turnos SET contenedor_id=?, posicion_patio_asignada=? WHERE id=?',
                             (data['contenedor'], int(data['posicion']), row['id']))
                for side, field in (('entrada','peso_medido_entrada_g'),('salida','peso_medido_salida_g')):
                    if data.get(side+'_valida')=='1':
                        conn.execute(f'UPDATE turnos SET {field}=? WHERE id=?', (round(float(data[side+'_kg'])*1000),row['id']))
        elif kind == 'TurnoCerrado':
            rows = _active(conn, data['placa'])
            if rows:
                _observe(conn, rows[0], 'Cerrado', 'SALIDA', timestamp, 'Salida fisica confirmada por vehiculo')
        elif kind == 'GruaDetalle':
            code = int(data['estado'])
            state['grua'].update(estado=CRANE_STATES[code], posicion=int(data['posicion']),
                                 cola_pendientes=int(data['cola']), trabajo_en_curso=data['trabajo'] or None,
                                 en_falla=code==15)
        elif kind == 'GruaTrabajo':
            state['grua']['trabajo_en_curso'] = data['id'] if data['evento']=='INICIO' else None
            if data['evento'] in ('FIN','ERROR'):
                active = _active(conn)
                matching = [r for r in active if r['hardware_key'].split(':')[0]==str(data['turno_local'])]
                types = ['DESCARGA_CAMION_A_PATIO','CARGA_PATIO_A_CAMION','REPOSICION_PATIO']
                conn.execute("INSERT INTO grua_ciclos(turno_id,tipo_trabajo,posicion_origen,posicion_destino,tiempo_ciclo_seg,distancia_recorrida_mm,exitoso,evento_falla,timestamp) VALUES (?,?,?,?,?,0,?,?,?)",
                             (matching[0]['id'] if len(matching)==1 else None, types[int(data['tipo'])],
                              int(data['origen']),int(data['destino']),float(data['duracion_ms'])/1000,
                              int(data['evento']=='FIN'), 'Trabajo abortado' if data['evento']=='ERROR' else None,timestamp))
                state['distancia_grua_disponible'] = False
        elif kind == 'PatioCelda':
            pos, level = int(data['posicion']), int(data['nivel'])
            cid = data.get('contenedor') or None
            config = next((c for c in CATALOG.values() if c['contenedor']==cid), {})
            old = conn.execute('SELECT * FROM patio_posiciones WHERE posicion=? AND nivel=?', (pos,level)).fetchone()
            if old and old['contenedor_id'] != cid:
                previous = conn.execute('SELECT * FROM patio_posiciones WHERE contenedor_id=?', (cid,)).fetchone() if cid else None
                entered = previous['ingreso_at'] if previous else timestamp if cid else None
                conn.execute("UPDATE patio_posiciones SET contenedor_id=?,naviera_id=?,peso_declarado_g=?,estado_autorizacion=?,ingreso_at=? WHERE posicion=? AND nivel=?",
                             (cid, config.get('naviera'), config.get('peso_declarado_g'), 'SIN_DOCUMENTO' if cid else 'LIBRE', entered, pos, level))
        elif kind == 'GaritaIdentificacion':
            uid = str(data.get('uid','')).replace(' ', '').upper()
            truck = conn.execute('SELECT placa FROM catalogo_camiones WHERE rfid_uid=?', (uid,)).fetchone()
            state['garita'] = {'estado': 'Validando', 'vehiculo': truck['placa'] if truck else uid}
        elif kind == 'GaritaValidacion':
            rejected = data.get('resultado') == 'RECHAZADO'
            state['garita']['estado'] = 'Rechazada' if rejected else 'Autorizada'
            state['garita']['causa'] = data.get('causa')
            if rejected:
                state['talanquera'] = 'Cerrada'
        elif kind in ('PesajeEnVivo', 'PesajeLectura'):
            # Old MQTT logs contain detalle; new bridge supplies numeric peso.
            import re
            match = re.search(r'Peso leido:\s*([-\d.]+)', str(data.get('detalle','')))
            value = float(data['peso']) if 'peso' in data else float(match[1]) if match else None
            if value is not None:
                state['pesaje'].update(ultimo_valor_kg=value, estado='Midiendo' if kind=='PesajeEnVivo' else 'Medicion recibida', resultado='Segun controlador')
                if kind == 'PesajeLectura':
                    active = _active(conn)
                    candidates = [r for r in active if r['placa_vehiculo']==state.get('pesaje_placa')]
                    if not candidates:
                        candidates = [r for r in active if r['estacion_actual']=='PESAJE']
                    if not candidates:
                        candidates = [r for r in active if r['estacion_actual']=='SALIDA' and r['peso_medido_salida_g'] is None]
                    if not candidates and not active and state['garita'].get('vehiculo'):
                        row = _turn(conn, state['garita']['vehiculo'], timestamp)
                        candidates = [row] if row else []
                    if len(candidates) == 1:
                        row = candidates[0]
                        field = 'peso_medido_salida_g' if row['estacion_actual']=='SALIDA' else 'peso_medido_entrada_g'
                        conn.execute(f'UPDATE turnos SET {field}=? WHERE id=?', (round(value*1000), row['id']))
                        _timeline(conn, row['id'], timestamp, f'Pesaje observado: {value} kg', {'campo':field, 'peso_kg':value})
        elif kind == 'SalidaEstado':
            code = int(data['estado'])
            previous = state.get('salida_codigo')
            state['salida_codigo'] = code
            candidates = [r for r in _active(conn) if r['placa_vehiculo']==state.get('salida_placa')]
            if not candidates:
                candidates = [r for r in _active(conn) if r['estacion_actual']=='SALIDA']
            if not candidates and len(_active(conn)) == 1:
                candidates = _active(conn)
            row = candidates[0] if candidates else None
            if code == 0:
                state['puerta_salida'] = state['talanquera'] = 'Cerrada'
                if previous == 6 and row:
                    _observe(conn, row, 'Cerrado', 'SALIDA', timestamp, 'Salida fisica confirmada por Fase1')
            elif code == 6:
                state['puerta_salida'] = state['talanquera'] = 'Abierta'
                _observe(conn, row, 'EnSalida', 'SALIDA', timestamp, 'Salida autorizada localmente')
            elif code in (1,2,3,4,5,7):
                state['puerta_salida'] = 'Cerrada'
                _observe(conn, row, 'EnPesajeSalida' if code==1 else 'Retenido' if code==7 else 'EnSalida', 'SALIDA', timestamp, f'Estado salida Fase1: {code}')
        elif kind == 'GruaEstado':
            code = int(data['estado'])
            state['grua'].update(estado=CRANE_STATES[code] if code<len(CRANE_STATES) else f'Estado {code}', en_falla=code==15)
            if code == 15:
                conn.commit()
                alarm_once('AL06', {'descripcion':'Grua detenida: consultar causa local / paro'})
        elif kind == 'GruaReferencia':
            state['grua']['referenciada'] = data['referenciada']=='SI'
        elif kind == 'GruaLibre':
            if data['libre']=='SI' and not state['paro_emergencia']:
                state['grua']['estado'] = 'En reposo'
                state['grua']['en_falla'] = False
        elif kind == 'PatioEstado':
            # Console reports levels, not container IDs. Keep that distinction.
            state['patio_fisico'][str(data['posicion'])] = dict(data, timestamp=timestamp)
        elif kind == 'ParoEmergencia':
            active = str(data.get('activo')).lower() in ('true','1','si')
            state.update(paro_emergencia=active, modo='EMERGENCIA' if active else 'NORMAL')
            if active:
                conn.commit()
                alarm_once('AL02')
        elif kind == 'AlarmaGenerada':
            conn.commit()
            alarm_once(data.get('codigo','AL00'), data)
        elif kind == 'RechazoComando':
            conn.commit()
            alarm_once('AL14', data)
        elif kind in ('GruaSuspendida','GruaReanudada'):
            state['grua']['suspendida'] = kind=='GruaSuspendida'
        elif kind == 'GruaReferenciada':
            state['grua'].update(referenciada=True,posicion=int(data.get('posicion',0)))
        elif kind == 'TalanqueraEstado':
            state['talanquera'] = str(data.get('estado','')).capitalize()
        elif kind == 'PuertaSalidaEstado':
            state['puerta_salida'] = str(data.get('estado','')).capitalize()
        elif kind == 'AgujaEstado':
            state['aguja'] = str(data.get('posicion','')).capitalize()
        elif kind == 'ModoMantenimiento':
            state['modo'] = 'MANTENIMIENTO' if str(data.get('activo'))=='1' else 'NORMAL'
        elif kind == 'Latido':
            for source,target in (('grua_ref','referenciada'),('grua_susp','suspendida'),('grua_falla','en_falla')):
                if source in data:
                    state['grua'][target] = data[source]=='SI'
            for source,target in (('grua_pos','posicion'),('cola_grua','cola_pendientes')):
                if source in data:
                    state['grua'][target] = int(data[source])
            state['modo'] = data.get('modo', state['modo'])
            for key in ('talanquera','aguja'):
                if key in data:
                    state[key] = data[key]
        conn.execute('INSERT OR REPLACE INTO controller_state VALUES (1,?)', (json.dumps(state),))
        conn.commit()
        return True
    finally:
        conn.close()
