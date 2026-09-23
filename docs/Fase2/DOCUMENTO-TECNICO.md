# Documento Tecnico - PORTUS Fase 2

Universidad de San Carlos de Guatemala  
Facultad de Ingenieria  
Escuela de Ciencias y Sistemas  
Arquitectura de Computadoras y Ensambladores 2  

---

## 1. Proposito y Alcance Implementado

La Fase 2 de PORTUS transforma una maqueta fisica autonoma (Fase 1) en una terminal portuaria conectada y gobernable a distancia mediante un computador de placa unica (Raspberry Pi 3). La plataforma resuelve la falta de coordinacion entre los cinco actores que intervienen en una operacion portuaria real inspirada en Puerto Quetzal: Terminal, Naviera, Agente Aduanero, Autoridad Fiscalizadora (SAT) y Transportista.

El alcance implementado cubre:
1. Enlace de comunicacion serial bidireccional delimitado con CRC16-CCITT y numero de secuencia continuo entre el Arduino Mega 2560 y la Raspberry Pi 3.
2. Intermediario de mensajeria MQTT (Mosquitto / amqtt) bajo el espacio de topicos estricto `portus/evt/*` y `portus/cmd/*`.
3. Servidor web HTTP en Flask con transmision de eventos en tiempo real mediante Server-Sent Events (SSE) sin polling a la base de datos (latencia verificada menor a 2 segundos).
4. Persistencia relacional en SQLite con modelo completo de turnos, manifiestos, declaraciones, citas, inventario de patio, alarmas y telemetria.
5. Control de acceso y matriz de permisos por rol aplicada obligatoriamente en backend para los 5 roles (`TERMINAL`, `NAVIERA`, `AGENTE`, `AUTORIDAD`, `TRANSPORTISTA`).
6. Interfaz del rol TERMINAL con sus ocho pestañas obligatorias (Operacion con sinoptico en vivo, Turnos con linea de tiempo al segundo, Retenciones, Patio, Grua, Alarmas, Citas, Reportes).
7. Cadena documental completa: declaracion de manifiesto por Naviera, declaracion de mercancia y solicitud de levante por Agente, y otorgamiento de levante con canal selectivo verde/rojo por Autoridad.
8. Parqueo de retencion de 3 plazas administradas de forma logica sobre el ramal fisico existente, evaluando las seis causas (RT01 a RT06) y ejecutando las tres resoluciones (`Aclarar`, `Corregir`, `Rechazar`).
9. Catalogo de alarmas AL01 a AL14 con distincion entre activas e historicas, reconocimiento individual para severidad Alta/Critica y masivo para Baja/Media.
10. Calculo de las 8 metricas de operacion sobre cualquier rango de corrida con exportacion a CSV.
11. Servicio conversacional de mensajeria para el Transportista con los 7 comandos obligatorios, codigos de vinculacion temporales a 60 minutos y las 9 notificaciones automaticas.

---

## 2. Arquitectura General del Sistema

El sistema opera bajo una distribucion jerarquica de responsabilidades:

```
+-------------------------------------------------------------------------+
|                         CAPA DE APLICACION WEB                          |
|  [TERMINAL] (8 pestanas)  [NAVIERA] (2 pestanas)  [AGENTE] (2 pestanas) |
|  [AUTORIDAD] (3 pestanas)                         [TRANSPORTISTA] (CLI) |
+-------------------------------------------------------------------------+
                                    |
                           (HTTP / SSE / JSON)
                                    v
+-------------------------------------------------------------------------+
|                     SERVIDOR CENTRAL (Raspberry Pi 3)                   |
|  - Aplicacion Flask (app.py)                                            |
|  - Matriz de permisos en backend (auth.py)                              |
|  - Maquina de estados del turno (turn_manager.py)                       |
|  - Administrador de retenciones (retention_manager.py)                  |
|  - Administrador de alarmas (alarm_manager.py)                          |
|  - Calculo de metricas (metrics.py)                                     |
|  - Base de datos SQLite (database.py)                                   |
+-------------------------------------------------------------------------+
          |                                            ^
  (portus/cmd/solicitud)                        (portus/evt/*)
          v                                            |
+-------------------------------------------------------------------------+
|                  INTERMEDIARIO DE MENSAJERIA (MQTT)                     |
|  Broker Mosquitto local en puerto 1883                                  |
+-------------------------------------------------------------------------+
          ^                                            |
          +--------------------+-----------------------+
                               |
                   (Publicacion / Suscripcion)
                               v
+-------------------------------------------------------------------------+
|                  PUENTE SERIAL-MQTT (serial_bridge.py)                  |
|  - Empaqueta y valida tramas con CRC16 y secuencia                      |
|  - Supervisa latido de 5s y genera alarma AL01 si se pierde enlace      |
+-------------------------------------------------------------------------+
                               |
               (Cable USB /dev/ttyACM0, 115200 baud)
                               v
+-------------------------------------------------------------------------+
|                CONTROLADOR DE MAQUETA (Arduino Mega 2560)               |
|  - Muestreo HX711 sincronizado con Timer2                               |
|  - Control de motores paso a paso 28BYJ-48 (ULN2003)                    |
|  - Enclavamientos de seguridad de la grua                               |
|  - Paro de emergencia fisico (INT5 pin 18)                              |
|  - Servos de talanquera y aguja desviadora                              |
+-------------------------------------------------------------------------+
```

### 2.1 Reparto entre Controlador y Servidor
Conforme a la Seccion 12 del enunciado, el reparto de funciones es riguroso:

| Funcion | Entorno de Ejecucion | Justificacion |
|---|---|---|
| Generacion de pulsos de motores | Arduino Mega 2560 | Tiempos criticos de paso a paso sin jitter del OS |
| Muestreo y filtrado de pesaje | Arduino Mega 2560 | Lectura sincrona de celdas A/B por Timer2 |
| Deteccion de meseta de pesaje | Arduino Mega 2560 | Evaluacion local determinista de estabilidad |
| Enclavamientos de seguridad de grua | Arduino Mega 2560 | Parada inmediata ante fin de carrera o perdida de marca |
| Altura de pila y confirmacion de agarre | Arduino Mega 2560 | Deteccion fisica local por contacto y LDR |
| Paro de emergencia | Arduino Mega 2560 | Interrupcion fisica por hardware (INT5 pin 18) |
| Cola de trabajos de grúa | Arduino Mega 2560 | Buffer local para continuar operacion si cae el servidor |
| Validacion de acceso en garita | Servidor (Pi 3) | Consulta de manifiesto, levante y cita en base de datos |
| Asignacion de posicion de patio | Servidor (Pi 3) | Inventario logico y politicas de almacenamiento |
| Asignacion de plaza de parqueo | Servidor (Pi 3) | Asignacion de menor indice (1..3) y causas RT01-RT06 |
| Resolucion de retenciones | Servidor (Pi 3) | Despacho de autorizaciones Aclarar, Corregir, Rechazar |
| Programacion de citas | Servidor (Pi 3) | Manejo de franjas de 15 minutos y limites de capacidad |
| Metricas y reportes | Servidor (Pi 3) | Agregacion estadistica e historial de operaciones |

---

## 3. Protocolo Serial Propio

Para garantizar integridad ante ruidos electromagneticos producidos por bobinas de motores y reles, se diseno un protocolo delimitado por caracteres imprimibles con CRC16-CCITT y numero de secuencia.

### 3.1 Estructura de la Trama
```
[SEQ:TIPO:CMD:CARGA:CRC]\n
```
- Delimitadores: corchete de apertura `[` y corchete de cierre `]` con terminador de linea `\n`.
- `SEQ`: Entero incremental (0 a 65535). Permite al receptor detectar perdidas de paquetes o desorden en el enlace.
- `TIPO`: Identificador de transaccion:
  - `CMD`: Comando emitido desde el servidor hacia el controlador.
  - `EVT`: Evento de estado o sensor emitido por el controlador hacia el servidor.
  - `ACK`: Confirmacion de aceptacion de comando emitida por el controlador.
  - `NAK`: Confirmacion de rechazo de comando emitida por el controlador con causa explicita.
  - `HB`: Latido periodico de enlace emitido cada 5 segundos.
- `CMD`: Nombre de la instruccion o evento (ej. `AbrirTalanquera`, `GaritaLectura`, `LatidoEstado`).
- `CARGA`: Parametros estructurados en pares `clave=valor` separados por punto y coma (ej. `uid=A1B2C3;peso=22500`).
- `CRC`: Verificacion de redundancia ciclica de 16 bits (CRC16-CCITT, polinomio 0x1021, valor inicial 0xFFFF), codificada en 4 caracteres hexadecimales en mayusculas. Se calcula sobre la cadena exacta `SEQ:TIPO:CMD:CARGA`.

### 3.2 Ejemplo de Trama Valida
Envio de orden de apertura de talanquera con secuencia 105:
```
[105:CMD:AbrirTalanquera:motivo=operador:26A0]\n
```
Respuesta afirmativa del controlador:
```
[105:ACK:AbrirTalanquera:estado=ABIERTA:8F12]\n
```
Respuesta de rechazo si habia un vehiculo presente:
```
[105:NAK:AbrirTalanquera:error=Vehiculo detectado bajo talanquera:D4E1]\n
```

---

## 4. Espacio de Topicos MQTT

Todos los eventos y comandos utilizan el prefijo obligatorio `portus`:

| Topico | Direccion | Tipo de Mensaje | Contenido |
|---|---|---|---|
| `portus/evt/garita` | Controlador -> Servidor | Evento | Lectura RFID, resultado de validacion, causas de rechazo |
| `portus/evt/pesaje` | Controlador -> Servidor | Evento | Peso medido, muestras en meseta, comparacion con tolerancia |
| `portus/evt/aguja` | Controlador -> Servidor | Evento | Estado fisico de la aguja (`RECTA`, `PARQUEO`, `LIBERANDO`) |
| `portus/evt/transferencia` | Controlador -> Servidor | Evento | Alineacion, inicio, fin o aborto de operacion en bahia |
| `portus/evt/grua` | Controlador -> Servidor | Evento | Posicion, estado de ciclo (reposo, izando, depositando, falla) |
| `portus/evt/patio` | Controlador -> Servidor | Evento | Cambio de ocupacion fisica por posicion y nivel |
| `portus/evt/salida` | Controlador -> Servidor | Evento | Paso del camion por el sensor de salida y verificacion |
| `portus/evt/alarma` | Controlador/Servidor | Alarma | Codigo AL01 a AL14, severidad y datos de diagnostico |
| `portus/evt/estado` | Controlador -> Servidor | Latido | Heartbeat periodico cada 5s con modo y telemetria general |
| `portus/cmd/solicitud` | Servidor -> Controlador | Comando | Solicitud remota despachada desde la interfaz web |
| `portus/cmd/respuesta` | Controlador -> Servidor | Confirmacion | Aceptacion (`ACK`) o rechazo (`NAK`) con motivo de enclavamiento |

### 4.1 Formato Estandar del Mensaje JSON Publicado
Todo mensaje en cualquier topico cumple con la siguiente firma estandar:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-09-22T14:30:00.123456+00:00",
  "origen": "controlador",
  "tipo": "GaritaIdentificacion",
  "datos": {
    "uid": "A1B2C3D4",
    "estacion": "GARITA"
  }
}
```

---

## 5. Modelo de Datos (SQLite)

El archivo `portus_fase2.db` almacena el estado completo de la terminal mediante 12 tablas relacionales normalizadas:
1. `usuarios`: Credenciales con hash SHA-256 y salt, asignacion de uno de los 5 roles.
2. `catalogo_contenedores`: Lista oficial de contenedores validos de la maqueta y su tara base.
3. `catalogo_camiones`: Registro de vehiculos, placa, RFID UID asociado y transportista propietario.
4. `manifiestos`: Declaraciones de Naviera con peso declarado, tolerancia, transportista, estado documental, canal aduanero e historial de modificaciones de peso.
5. `declaraciones`: Declaraciones de mercancias del Agente Aduanero (numero unico, regimen, descripcion con minimo 10 caracteres, valor declarado).
6. `citas`: Agenda en franjas de 15 minutos (maximo 2 citas por franja) y control de cumplimiento de ventana.
7. `turnos`: Ciclo de vida del camion con los 10 estados exactos, pesajes de entrada y salida, estacion actual y marcas de tiempo.
8. `linea_tiempo_turno`: Registro historico inmutable de cada evento por turno con precision de segundo, origen y valores asociados.
9. `retenciones`: Control de las 3 plazas de parqueo, causas RT01 a RT06, tiempos de espera, evidencias de peso, rol facultado y resolucion aplicada.
10. `alarmas`: Catalogo de alarmas AL01 a AL14 con estado de reconocimiento manual y comentarios.
11. `patio_posiciones`: Inventario por celda (posiciones 0 y 1, niveles 0 y 1), bloqueo administrativo y reloj de permanencia.
12. `grua_ciclos`: Registro estadistico de cada movimiento de grua (tiempo de ciclo, distancia en mm, tipo de trabajo y fallas).

---

## 6. Modelo de Usuarios, Roles y Matriz de Permisos

El sistema implementa 5 roles. Las restricciones se aplican en el servidor mediante el decorador `@require_permission(accion)`. Un intento de violar la matriz devuelve un error HTTP 403 con mensaje explicito:

| Accion | TERMINAL | NAVIERA | AGENTE | AUTORIDAD | TRANSPORTISTA |
|---|---|---|---|---|---|
| Crear manifiesto | NO | SI | NO | NO | NO |
| Ver manifiesto completo | SI | Solo propios | SI | SI | NO |
| Presentar declaracion y solicitar levante | NO | NO | SI | NO | NO |
| Otorgar o retener levante | NO | NO | NO | SI | NO |
| Asignar canal de selectivo | NO | NO | NO | SI | NO |
| Solicitar cita | NO | NO | NO | NO | SI |
| Ver agenda completa de citas | SI | NO | NO | NO | NO |
| Ver sinoptico de la terminal | SI | NO | NO | NO | NO |
| Emitir comandos remotos | SI | NO | NO | NO | NO |
| Reconocer alarmas | SI | NO | NO | NO | NO |
| Resolver retencion operativa (RT01, RT02, RT04, RT06) | SI | NO | NO | NO | NO |
| Resolver retencion aduanera (RT03, RT05) | NO | NO | NO | SI | NO |
| Corregir peso declarado en manifiesto | SI | NO | NO | NO | NO |
| Consultar ubicacion de un contenedor | SI | Solo propios | SI | SI | Solo propios |
| Generar reporte de corrida | SI | NO | NO | NO | NO |
| Generar codigo de vinculacion transportista | SI | NO | NO | NO | NO |

---

## 7. Parqueo de Retencion y Resoluciones

El ramal fisico de Fase 1 se administra logicamente como un parqueo de 3 plazas (1, 2 y 3):
- Al generarse una retencion, el sistema asigna la plaza libre de menor indice y emite `AgujaParqueo`.
- Si las 3 plazas estan ocupadas y se presenta un camion con riesgo de retencion (canal rojo o fuera de ventana), la garita rechaza el ingreso y genera `AL11` (Parqueo de retencion lleno).

### 7.1 Resoluciones Permitidas
1. `Aclarar`: Devuelve el turno a su estado previo sin alterar el manifiesto. Despacha `AgujaLiberar` y libera la plaza.
2. `Corregir`: Potestad exclusiva de `TERMINAL`. Sustituye el peso declarado del manifiesto por el peso real medido en bascula, guarda el valor previo en el historial del manifiesto, libera la plaza con `AgujaLiberar` y reanuda el turno.
3. `Rechazar`: Requiere motivo obligatorio. Libera la plaza con `AgujaLiberar`, pasa el turno a estado `Anulado` y autoriza la salida del vehiculo sin completar la operacion. El inventario fisico del patio conserva su estado real.

---

## 8. Calculo de las Ocho Metricas de Operacion

En la pestaña Reportes, el sistema calcula sobre el rango de fechas seleccionado:
1. `Remociones por contenedor retirado`: Total de movimientos de remocion divididos entre retiros completados.
2. `Ciclos de grua por operacion completada`: Total de ciclos de grua divididos entre turnos cerrados.
3. `Distancia total recorrida por la grua`: Suma de distancia en mm de traslacion convertida a metros.
4. `Tiempo promedio de camion en la terminal`: Promedio del tiempo transcurrido entre creacion y cierre de turnos cerrados.
5. `Tiempo promedio de retencion`: Promedio del tiempo transcurrido entre generacion de una retencion y su resolucion resuelta.
6. `Longitud maxima de la fila de espera`: Conteo maximo de vehiculos en espera / garita simultaneos.
7. `Porcentaje de citas cumplidas en ventana`: Citas dentro de ventana divididas entre total de citas del periodo.
8. `Retenciones por causa y por resolucion`: Desglose cuantitativo agrupado por causa (`RT01` a `RT06`) y tipo de resolucion (`Aclarar`, `Corregir`, `Rechazar`).

---

## 9. Comportamiento ante Perdida de Comunicacion

La Seccion 12.1 del enunciado exige autonomia y degradacion segura:
1. **Deteccion en el Servidor:** Si pasan 3 periodos consecutivos (15 segundos) sin recibir el latido del controlador, el puente serial declara enlace perdido, el sinoptico muestra un banner de alerta con la marca de tiempo del ultimo estado conocido, y se genera la alarma critica `AL01`.
2. **Autonomia en el Controlador:** Si el microcontrolador deja de comunicarse con el servidor:
   - Completa de forma segura el trabajo de grua en curso.
   - Atiende normalmente el paro de emergencia fisico (pin 18) y los enclavamientos.
   - Muestra en la pantalla LCD de garita el mensaje de operacion en modo degradado.
   - Rechaza nuevos accesos hasta que el enlace se restablezca.
   - Almacena localmente los eventos ocurridos.
3. **Reconciliacion:** Al reconectarse el cable USB, el puente detecta el restablecimiento, actualiza el banner del sinoptico a conectado y solicita el estado real del inventario para reconciliar cualquier movimiento pendiente.
