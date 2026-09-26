import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PortusFase2.server import database
from PortusFase2.server.telemetry import initial_state, process_event
from PortusFase2.bridge.serial_bridge import SerialMQTTBridge
from PortusFase2.bridge.serial_protocol import SerialProtocol


class HardwareTelemetryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, 'DB_PATH', str(Path(self.temp.name)/'hardware.db'))
        self.env_patch = patch.dict(os.environ, {'PORTUS_DEMO_DATA':'false'})
        self.db_patch.start()
        self.env_patch.start()
        database.init_database()
        self.state = initial_state()
        self.sequence = 0

    def tearDown(self):
        self.db_patch.stop()
        self.env_patch.stop()
        self.temp.cleanup()

    def emit(self, kind, data, topic='portus/evt/estado'):
        self.sequence += 1
        event = {'id':str(self.sequence), 'tipo':kind, 'datos':data,
                 'timestamp':f'2026-09-26T07:{self.sequence//60:02d}:{self.sequence%60:02d}+00:00'}
        process_event(self.state, event, topic)
        return event

    def rows(self, table):
        conn = database.get_db_connection()
        rows = [dict(r) for r in conn.execute('SELECT * FROM '+table)]
        conn.close()
        return rows

    def test_real_raspberry_run_closes_both_vehicles_without_creating_rejected_turns(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/raspberry_2026_09_26.json').read_text(encoding='utf-8'))
        for item in fixture:
            process_event(self.state, item['event'], item['topic'])
        turns = self.rows('turnos')
        self.assertEqual(len(turns), 2)
        self.assertEqual([t['estado_actual'] for t in turns], ['Cerrado','Cerrado'])
        self.assertEqual([t['contenedor_id'] for t in turns], ['CT-001','CT-002'])
        self.assertEqual([t['peso_medido_entrada_g'] for t in turns], [1160,1400])
        self.assertEqual(self.state['pesaje']['ultimo_valor_kg'], 1.4)
        self.assertEqual(self.state['garita']['estado'], 'Rechazada')
        self.assertEqual(self.state['talanquera'], 'Cerrada')
        self.assertEqual(len([a for a in self.rows('alarmas') if a['codigo']=='AL01']), 1)
        # Replay identical QoS1 messages: no additional turns or timeline entries.
        count = len(self.rows('linea_tiempo_turno'))
        for item in fixture:
            process_event(self.state, item['event'], item['topic'])
        self.assertEqual(len(self.rows('linea_tiempo_turno')), count)

    def test_snapshot_reconciles_concurrent_vehicles_and_emergency(self):
        bridge = SerialMQTTBridge()
        bridge.publish_event = lambda topic, kind, data: self.emit(kind, data, topic)
        for line in ['Turnos activos: 2',
                     'Turno 0 | Camion P001AAA | Estacion 5 | Retenido: NO | PesajeInicial: 1.16 | PesajeFinal: 0.00',
                     'Turno 1 | Camion P002BBB | Estacion 6 | Retenido: SI | PesajeInicial: 1.40 | PesajeFinal: 1.40',
                     '>>> PARO DE EMERGENCIA ACTIVO <<<', 'Ultima causa registrada: Boton de paro']:
            bridge._handle_controller_line(line)
        self.assertEqual(self.state['vehiculos_dentro'],2)
        self.assertEqual(self.state['modo'],'EMERGENCIA')
        self.assertEqual(self.state['transferencia']['vehiculo'],'P001AAA')
        self.assertEqual(len(self.rows('turnos')),2)
        bridge._handle_controller_line('Turnos activos: 0')
        # No end marker: incomplete snapshot must not erase vehicles.
        self.assertEqual(self.state['vehiculos_dentro'],2)
        bridge._handle_controller_line('Ultima causa registrada: Rearme')
        self.assertFalse(self.state['paro_emergencia'])
        self.assertEqual(self.state['vehiculos_dentro'],0)

    def test_crc_failure_does_not_update_heartbeat_or_publish(self):
        bridge = SerialMQTTBridge()
        published = []
        bridge.publish_event = lambda *args: published.append(args)
        bridge.last_heartbeat_time = 0
        bridge._handle_controller_line(SerialProtocol.build_frame(1,'EVT','PesajeLectura','peso=25').replace('25','99'))
        self.assertEqual(published,[])
        self.assertEqual(bridge.last_heartbeat_time,0)

    def test_restart_preserves_data_and_does_not_insert_demo_operations(self):
        self.emit('SnapshotFase1',{'cantidad':0,'turnos':[],'paro':False})
        database.init_database()
        database.init_database()
        for table in ('citas','grua_ciclos','turnos'):
            self.assertEqual(self.rows(table),[])
        restored = initial_state()
        self.assertEqual(restored['vehiculos_dentro'],0)
        self.assertEqual(restored['enlace'],'DESCONECTADO')

    def test_physical_detail_updates_yard_without_fabricating_authorization(self):
        bridge = SerialMQTTBridge()
        bridge.publish_event = lambda topic, kind, data: self.emit(kind,data,topic)
        bridge._handle_controller_line('@PORTUS PatioCelda;posicion=0;nivel=0;contenedor=CT-003;ocupada=1')
        cell = self.rows('patio_posiciones')[0]
        self.assertEqual(cell['contenedor_id'],'CT-003')
        self.assertEqual(cell['estado_autorizacion'],'SIN_DOCUMENTO')
        bridge._handle_controller_line('@PORTUS GruaDetalle;estado=9;posicion=1;cola=2;trabajo=3')
        self.assertEqual(self.state['grua']['estado'],'Trasladando a destino')
        self.assertEqual(self.state['grua']['cola_pendientes'],2)

    def test_all_roles_read_views_and_naviera_data_is_isolated(self):
        from PortusFase2.server import app as server
        server.terminal_state['protocolo'] = 'fase1'
        self.emit('SnapshotFase1', {'cantidad':1,'paro':False,'turnos':[
            {'turno_local':'0','placa':'P001AAA','estacion':'5','retenido':'NO','entrada_kg':'1.16','salida_kg':'0'}]})
        users = [('operador1','terminal123'),('maersk','maersk123'),('msc','msc123'),('agente1','agente123'),('sat1','sat123')]
        for user,password in users:
            client = server.app.test_client()
            self.assertEqual(client.post('/api/login',json={'username':user,'password':password}).status_code,200)
            for path in ('/api/manifiestos','/api/declaraciones','/api/patio','/api/turnos'):
                self.assertEqual(client.get(path).status_code,200,(user,path))
            self.assertEqual(client.get('/api/carga').status_code, 200)
            if user=='msc':
                self.assertEqual(client.get('/api/turnos').json,[])
                self.assertEqual(client.get('/api/carga').json,[])
                self.assertEqual(client.get('/api/turnos/1/timeline').status_code,404)
                stream=client.get('/api/stream/events',buffered=False)
                first=next(iter(stream.response)).decode()
                self.assertNotIn('P001AAA',first)
                self.assertNotIn('garita',first)
                stream.close()
            if user=='operador1':
                self.assertEqual(client.post('/api/cmd/remote',json={'comando':'AbrirTalanquera'}).status_code,409)
                for path in ('/api/retenciones','/api/grua/historial','/api/alarmas','/api/citas','/api/reportes/calcular'):
                    self.assertEqual(client.get(path).status_code,200,path)
            if user=='maersk':
                rows = client.get('/api/carga').json
                self.assertEqual(rows[0]['contenedor'], 'CT-001')
                self.assertEqual(rows[0]['estado'], 'EnTransferencia')
                self.assertEqual(client.post('/api/manifiestos',json={
                    'contenedor_id':'CT-003','tipo_operacion':'RETIRO',
                    'peso_declarado':65,'transportista_id':'trans_global'}).status_code,403)


if __name__ == '__main__':
    unittest.main()
