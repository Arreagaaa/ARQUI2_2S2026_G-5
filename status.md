# PORTUS Fase 2 - Estado del Proyecto

Fecha: 2026-09-22
Version: 1.0.0
Estado: En desarrollo activo

---

## 1. Resumen de Fase 1

La Fase 1 construyo el nucleo fisico y de control determinista de la terminal portuaria sobre un microcontrolador Arduino Mega 2560. El sistema implemento identificacion RFID, pesaje dinamico con dos celdas HX711, aguja desviadora hacia ramal, zona de transferencia asistida, grua de dos grados de libertad con motores paso a paso 28BYJ-48 y electroiman, patio apilable de dos niveles monitoreado con LDRs, salida controlada y paro de emergencia en pin 18. El control opera sin retardos bloqueantes mediante maquinas de estado y ticks del Timer2. Como unico detalle de hardware registrado, el sensor IR de transferencia (pin 25) presentaba lecturas bajas constantes atribuibles a cableado fisico en la maqueta.

---

## 2. Contexto de Fase 2

PORTUS Fase 2 integra la maqueta fisica con una plataforma digital completa ejecutada en un computador de placa unica (Raspberry Pi 3). El objetivo es gobernar remotamente la terminal, gestionar la cadena documental aduanera y comercial (manifiestos, declaraciones de mercancias, levante, canal verde/rojo), administrar logicamente un parqueo de retencion de 3 plazas para resolver discrepancias de peso o documentos, programar citas de transportistas y supervisar en tiempo real sin recarga periodica de base de datos.

### 2.1 Arquitectura del Sistema

```
[ Arduino Mega 2560 ]
        |
   (USB Serial /dev/ttyACM0 o COMx, 115200 baud, protocolo delimitado con CRC)
        v
[ Bridge Python (pySerial <-> MQTT paho) ]
        |
   (Broker MQTT Mosquitto / amqtt local, puerto 1883)
        +---> portus/evt/*   (Eventos del controlador y telemetria)
        +---> portus/cmd/*   (Comandos remotos y respuestas)
        v
[ Servidor Web Flask + SSE/WebSocket + SQLite ]
        |
   (HTTP/WebSocket - Red Local)
        v
[ Interfaces Web por Rol: TERMINAL, NAVIERA, AGENTE, AUTORIDAD ]
        +
[ Servicio de Mensajeria Transportista: Comandos CLI/Telegram + Notificaciones ]
```

### 2.2 Protocolo Serial
- Formato de trama: `[SEQ:TIPO:CMD:CARGA:CRC]\n`
- Delimitadores: corchetes `[` y `]`, terminador salto de linea `\n`.
- Secuencia: entero incremental 0-65535 para deteccion de paquetes perdidos.
- Verificacion: CRC16-CCITT en hexadecimal (4 caracteres).
- Confirmacion: todo comando emitido desde el servidor recibe ACK o NAK con causa explicita de rechazo evaluada por el controlador.

### 2.3 Espacio de Topicos MQTT (Prefijo portus Obligatorio)
- `portus/evt/garita`: eventos de identificacion, validacion y rechazos.
- `portus/evt/pesaje`: lecturas de entrada y salida, muestras y comparacion con tolerancia.
- `portus/evt/aguja`: estado fisico y logico de la aguja (recta, parqueo, liberacion).
- `portus/evt/transferencia`: alineacion de camion, inicio, aborto y fin de transferencia.
- `portus/evt/grua`: pasos del ciclo (reposo, izaje, traslado, deposito, referencia, fallas).
- `portus/evt/patio`: cambios de ocupacion por nivel y posicion con ID de contenedor.
- `portus/evt/salida`: verificacion y paso por puerta de salida.
- `portus/evt/alarma`: catalogo de alarmas AL01 a AL14 con severidad y datos.
- `portus/evt/estado`: latido periodico cada 5 segundos.
- `portus/cmd/solicitud`: comandos remotos despachados desde la plataforma.
- `portus/cmd/respuesta`: aceptacion o rechazo emitido por el controlador.

### 2.4 Stack Tecnologico
- Servidor web: Python Flask con soporte de SSE / WebSockets para entrega en tiempo real de eventos MQTT al navegador (latencia menor a 2 segundos sin polling).
- Base de datos: SQLite con esquema relacional para persistencia local.
- Intermediario MQTT: Eclipse Mosquitto (nativo en Linux/Raspberry Pi) y fallback compatible amqtt (Python) para desarrollo multiplataforma.
- Enlace serial: Python pySerial con hilo dedicado de lectura/escritura no bloqueante.
- Canal de mensajeria: Servicio conversacional modular con soporte de consola/HTTP y bot de Telegram.

---

## 3. Referencia del Firmware Arduino Mega 2560

### 3.1 Sensores (Entradas)

| Pin | Nombre | Tipo | Logica | Funcion |
|-----|--------|------|--------|---------|
| 2 | PIN_IR_ESPERA | Digital | LOW = presencia | Garita de espera |
| 3 | PIN_IR_PESAJE | Digital | LOW = presencia | Plataforma de pesaje |
| 25 | PIN_IR_TRANSFERENCIA | Digital | LOW = presencia | Zona de transferencia |
| 26 | PIN_IR_RAMAL | Digital | LOW = presencia | Entrada al ramal/parqueo |
| 19 | PIN_IR_SALIDA | Digital | LOW = presencia | Puerta de salida |
| 38 | PIN_FC_CONTACTO | Digital | LOW = contacto | Fin de carrera vertical grua |
| A0 | PIN_MARCA_OPTICA | Analogico/Digital | LOW = marca | Marca de posicion riel grua |
| 18 | PIN_PARO_EMERGENCIA | Digital (INT5) | LOW = activo | Paro de emergencia fisico |
| 22 | PIN_HX711_DOUT1 | Digital | Datos | Celda de carga extremo A |
| 23 | PIN_HX711_DOUT2 | Digital | Datos | Celda de carga extremo B |
| 24 | PIN_HX711_SCK | Salida digital | Reloj | Reloj compartido celdas |
| 50 | MISO (SPI) | Digital | Bus SPI | Lector RFID RC522 |
| 51 | MOSI (SPI) | Digital | Bus SPI | Lector RFID RC522 |
| 52 | SCK (SPI) | Digital | Bus SPI | Lector RFID RC522 |
| 53 | PIN_RFID_SS | Digital | Salida | Slave Select RFID RC522 |
| 10 | PIN_RFID_RST | Digital | Salida | Reset RFID RC522 |
| A8 | LDR Posicion 0 Nivel 0 | Analogico | Lectura LDR | Presencia contenedor P0 N0 |
| A9 | LDR Posicion 0 Nivel 1 | Analogico | Lectura LDR | Presencia contenedor P0 N1 |
| A10 | LDR Posicion 1 Nivel 0 | Analogico | Lectura LDR | Presencia contenedor P1 N0 |
| A11 | LDR Posicion 1 Nivel 1 | Analogico | Lectura LDR | Presencia contenedor P1 N1 |

### 3.2 Actuadores (Salidas)

| Pin | Nombre | Tipo | Funcion |
|-----|--------|------|---------|
| 5 | PIN_SERVO_TALANQUERA | Servo PWM | Apertura y cierre de garita (0=cerrado, 90=abierto) |
| 7 | PIN_SERVO_AGUJA | Servo PWM | Aguja desviadora (0=recta, 90=ramal) |
| 8 | PIN_FLECHA_VERDE | Digital | Indicador aceptado hacia transferencia |
| 9 | PIN_FLECHA_AMBAR | Digital | Indicador retenido hacia ramal |
| 30-33 | PIN_TRANS_IN1..4 | Digital | Driver ULN2003 motor traslacion horizontal |
| 34-37 | PIN_IZAJE_IN1..4 | Digital | Driver ULN2003 motor izaje vertical |
| 39 | PIN_ELECTROIMAN | Digital | Rele de activacion de electroiman |
| 40-42 | PIN_SEM_GARITA_R/A/V | Digital | Semaforo garita |
| 43-45 | PIN_SEM_TRANSF_R/A/V | Digital | Semaforo transferencia |
| A12-A13| YARD_LED_PIN[0..1] | Digital | LEDs indicadores de posicion de patio |
| 20 (SDA)| I2C SDA | I2C | Pantalla LCD 16x2 (Direccion 0x27) |
| 21 (SCL)| I2C SCL | I2C | Pantalla LCD 16x2 (Direccion 0x27) |

### 3.3 Puertos Seriales del Arduino Mega
- `Serial` (Pines 0 RX0, 1 TX0): Conectado al chip USB a serial del Arduino. Usado en Fase 1 a 115200 baud para consola y diagnostico. Se utiliza para la conexion USB directa con la Raspberry Pi sin requerir cableado adicional.
- `Serial1` (Pines 19 RX1, 18 TX1): No disponible como UART porque los pines 18 y 19 estan ocupados como GPIO para PIN_PARO_EMERGENCIA (18) y PIN_IR_SALIDA (19).
- `Serial2` (Pines 17 RX2, 16 TX2): Libre de uso.
- `Serial3` (Pines 15 RX3, 14 TX3): Libre de uso.

### 3.4 Recursos de Temporizadores y Concurrencia
- `Timer2`: Configurado en Weighing.cpp para tick base de 100 microsegundos compartido con Crane.cpp.
- `Timer1, Timer3, Timer4, Timer5`: Reservados por la libreria `Servo.h` en Arduino Mega.
- Baudrate de enlace serial: 115200 baudios.

---

## 4. Plan de Trabajo e Implementacion

1. Protocolo serial bidireccional delimitado con CRC16 y secuencia (`PortusFase2/bridge/serial_protocol.py`).
2. Simulador de controlador y maqueta para validacion de los 15 escenarios y pruebas sin hardware (`PortusFase2/bridge/mock_controller.py`).
3. Puente de comunicacion Serial-MQTT (`PortusFase2/bridge/serial_bridge.py`) con publicacion en `portus/evt/*`, atencion a `portus/cmd/*` y latido cada 5 segundos con deteccion de enlace perdido (AL01 tras 3 periodos sin latido).
4. Base de datos relacional SQLite (`PortusFase2/server/database.py`) con modelo completo de usuarios, roles, permisos, manifiestos, declaraciones, turnos, retenciones, alarmas, patio, grua, telemetria y citas.
5. Capa de autenticacion y matriz de permisos aplicada estrictamente en backend (`PortusFase2/server/auth.py`).
6. Maquina de estados del turno con los 10 estados exactos del enunciado (`PortusFase2/server/turn_manager.py`).
7. Administrador logico del parqueo de retencion (3 plazas, causas RT01 a RT06, resoluciones Aclarar, Corregir, Rechazar con efecto fisico y notificaciones).
8. Servidor Web Flask con arquitectura de distribucion en tiempo real sin polling (`PortusFase2/server/app.py`).
9. Interfaz completa del rol TERMINAL: sinoptico en vivo (SVG/Canvas dinamico), bandeja de turnos con linea de tiempo, bandeja de retenciones, inventario de patio, control e historial de grua, panel de alarmas activas/historicas con reconocimiento, citas y reportes de corrida con las 8 metricas.
10. Interfaces web para roles NAVIERA, AGENTE y AUTORIDAD con la cadena documental completa y aislamiento de datos por naviera.
11. Servicio de mensajeria del TRANSPORTISTA con los 7 comandos obligatorios y las 9 notificaciones automaticas.
12. Script maestro de inicio unificado (`PortusFase2/run_fase2.py`) e instrucciones claras de despliegue.

---

## 5. Progreso del Proyecto

| Modulo / Requisito | Estado | Observaciones / Comando de prueba |
|-------------------|--------|-----------------------------------|
| Revision de firmware Fase 1 y definicion de pines/puertos | Completado | Documentado en esta especificacion |
| Protocolo serial estructurado con CRC16 | Completado | `python PortusFase2/bridge/serial_protocol.py` |
| Simulador de controlador Arduino Mega | Completado | `python PortusFase2/bridge/mock_controller.py` |
| Puente Serial-MQTT bidireccional | Completado | `python PortusFase2/bridge/serial_bridge.py` |
| Base de datos SQLite y semillas de los 6 usuarios minimos | Completado | `python PortusFase2/server/database.py` |
| Autenticacion y matriz de permisos en backend | Completado | Verificado con matriz de 5 roles |
| Maquina de estados de turno (10 estados) | Completado | Gestion de transiciones y pesaje |
| Parqueo de retencion (3 plazas, RT01-RT06, 3 resoluciones) | Completado | Evaluacion de roles autorizados |
| Pestaña Operacion (Sinoptico en vivo por suscripcion) | Completado | Actualizacion en tiempo real < 2s |
| Pestaña Turnos y linea de tiempo detallada | Completado | Historial completo de eventos |
| Pestaña Retenciones | Completado | Acciones Aclarar, Corregir, Rechazar |
| Pestaña Patio e inventario | Completado | Niveles, permanencia y bloqueos |
| Pestaña Grua y metricas de ciclo | Completado | Cola, historial de fallas y exportacion |
| Pestaña Alarmas (AL01-AL14 con reconocimiento manual) | Completado | Filtros y reconocimiento individual/masivo |
| Interfaces NAVIERA, AGENTE, AUTORIDAD | Completado | Cadena de levante y selectivo rojo/verde |
| Pestaña Citas y agenda en franjas de 15 min | Completado | Validacion de franjas y ventanas |
| Pestaña Reportes con 8 metricas y exportacion CSV | Completado | Calculo de indicadores de corrida |
| Canal de mensajeria de Transportista (7 comandos, 9 avisos) | Completado | `python PortusFase2/mensajeria/messaging_service.py` |
| Documento Tecnico y Especificacion de Fase 2 | Completado | `docs/Fase2/DOCUMENTO-TECNICO.md` |
| Mapa de Pines, Hardware y Conexiones | Completado | `docs/Fase2/MAPA-PINES-Y-HARDWARE.md` |
| Manual de Despliegue y Guia de 15 Escenarios | Completado | `docs/Fase2/MANUAL-DESPLIEGUE-Y-PRUEBAS.md` |
| Script maestro de arranque unificado | Completado | `python PortusFase2/run_fase2.py` |

---

## 6. Decisiones de Diseno y Justificacion

1. **Uso del puerto Serial USB principal (115200 baud):**
   El Arduino Mega tiene conectados los pines 18 y 19 al paro de emergencia y al sensor IR de salida, lo cual inhabilita el uso de `Serial1`. El puerto `Serial` USB es el unico que no requiere cableado fisico adicional hacia la Raspberry Pi 3.

2. **Protocolo serial encapsulado con CRC16-CCITT:**
   Para evitar corrupcion de tramas en presencia de ruido electromagnetico de motores ULN2003 y celdas de carga, se eligio delimitacion por caracteres `[` y `]` junto a un CRC16 computado sobre la carga util, con un numero de secuencia continuo para detectar paquetes perdidos en el puente.

3. **Adaptacion bidireccional en el Bridge Serial-MQTT:**
   Para cumplir la Regla 1 (no alterar el firmware ya calificado de Fase 1), el puente en Python reconoce tanto las tramas formadas por el protocolo estructurado de Fase 2 como las salidas impresas por la consola de Fase 1, traduciendolas a los topicos obligatorios `portus/evt/*`. Esto permite conectar la maqueta original sin reprogramar el microcontrolador si no se desea, o bien activar la extension estructurada.

4. **Entrega al navegador mediante Server-Sent Events (SSE) / WebSocket conectado a MQTT:**
   El enunciado prohibe expresamente el polling a la base de datos para actualizar el sinoptico y exige latencia menor a 2 segundos. El servidor Flask se suscribe al broker MQTT y retransmite inmediatamente cada evento recibido hacia los clientes web conectados, garantizando consumo reactivo y bandera de desconexion visible con marca de tiempo.

5. **Parqueo logico de 3 plazas reutilizando la aguja desviadora:**
   El ramal fisico de Fase 1 se reutiliza como parqueo de retencion. La logica de asignacion asigna la plaza libre de menor indice (1, 2 o 3) y comanda la aguja hacia `AgujaParqueo`. Al resolver mediante Aclarar o Corregir, se comanda `AgujaLiberar` y el vehiculo regresa al carril principal.

6. **Aislamiento estricto de datos:**
   Las navieras unicamente pueden ver y operar sus propios manifiestos y contenedores. Los transportistas solo pueden consultar la carga que tienen asignada. Cualquier intento de consulta no autorizada es bloqueado en la capa de aplicacion y base de datos, retornando error explicito.
