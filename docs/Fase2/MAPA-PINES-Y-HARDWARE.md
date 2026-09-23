# Mapa de Pines, Conexiones y Hardware - PORTUS Fase 2

Este documento detalla la distribucion fisica de conexiones de la terminal portuaria, especificando el rol del computador de placa unica (Raspberry Pi 3), el uso de sus interfaces, y el mapeo completo de pines del microcontrolador (Arduino Mega 2560).

---

## 1. Rol de la Raspberry Pi 3 y uso de sus Interfaces

### 1.1 Rol de la Raspberry Pi 3
La Raspberry Pi 3 actua exclusivamente como computador de placa unica (SBC) para ejecutar la plataforma central:
- Broker de mensajeria MQTT (Mosquitto local en puerto 1883).
- Puente de comunicacion bidireccional Serial-MQTT (`serial_bridge.py`).
- Servidor web HTTP y motor de eventos en tiempo real SSE (`app.py`).
- Base de datos relacional SQLite (`portus_fase2.db`).
- Servicio conversacional de atencion a transportistas (`messaging_service.py`).

### 1.2 Que GPIOs se usan en la Raspberry Pi
**Ningun pin del header GPIO de 40 pines de la Raspberry Pi se utiliza para controlar motores ni leer sensores de la maqueta.**

La conexion entre la Raspberry Pi 3 y el Arduino Mega 2560 se realiza **exclusivamente por cable USB** (USB Tipo A en la Pi hacia USB Tipo B en el Arduino Mega):

```
+------------------------+                        +------------------------+
|    Raspberry Pi 3      |                        |    Arduino Mega 2560   |
|                        |       Cable USB        |                        |
|  [Puerto USB Tipo A]   |========================|  [Puerto USB Tipo B]   |
|  (/dev/ttyACM0 o USB0) |   115200 baudios, 8N1  |  (Chip serial ATmega16U2)|
+------------------------+                        +------------------------+
```

### 1.3 Justificacion Tecnica
1. **Regla de enclavamiento determinista (Seccion 12 del enunciado):** La generacion de pulsos para los motores paso a paso (ULN2003), el muestreo sincrono de las celdas HX711 por Timer2, los servos y la atencion inmediata del paro de emergencia (pin 18) deben permanecer en el microcontrolador. Un sistema donde la Pi manipule motores o lea el pesaje directamente por sus GPIOs queda descalificado segun la rubrica.
2. **Aislamiento electrico y de ruido:** Los motores 28BYJ-48 generan picos inductivos que son absorbidos por la fuente de 5V externa y los drivers ULN2003 conectados al Mega. Llevar esas lineas a los pines de 3.3V no tolerantes a 5V de la Raspberry Pi pondria en riesgo la placa.
3. **Identificacion del enlace en Linux:** Al conectar el Mega a la Pi, el dispositivo aparece en el sistema operativo como `/dev/ttyACM0` (o `/dev/ttyUSB0` si se usa clon con chip CH340). La velocidad configurada es de 115200 baudios.

---

## 2. Mapa de Conexiones del Arduino Mega 2560

Toda la instrumentacion fisica de la maqueta se encuentra conectada al Arduino Mega.

### 2.1 Sensores de Presencia e Infrarrojos (Entradas Digitales)

| Pin Mega | Nombre en Codigo | Tipo | Logica | Ubicacion / Estacion |
|---|---|---|---|---|
| Pin 2 | `PIN_IR_ESPERA` | IR Digital | LOW = Presencia | Garita / Zona de espera |
| Pin 3 | `PIN_IR_PESAJE` | IR Digital | LOW = Presencia | Plataforma de pesaje dinamico |
| Pin 25 | `PIN_IR_TRANSFERENCIA` | IR Digital | LOW = Presencia | Zona de transferencia (bahia camion) |
| Pin 26 | `PIN_IR_RAMAL` | IR Digital | LOW = Presencia | Entrada al ramal (parqueo de retencion) |
| Pin 19 | `PIN_IR_SALIDA` | IR Digital | LOW = Presencia | Punto de verificacion de salida |

*Nota sobre Pin 25:* En Fase 1 presentaba lecturas bajas constantes por falso contacto. Mantener conexion firme a 5V y GND comun.

### 2.2 Pesaje Dinamico - 2x Celdas de Carga con HX711

| Pin Mega | Nombre en Codigo | Tipo | Modulo HX711 |
|---|---|---|---|
| Pin 24 | `PIN_HX711_SCK` | Salida digital | Reloj COMPARTIDO por ambas celdas |
| Pin 22 | `PIN_HX711_DOUT1` | Entrada digital | Datos Celda Extremo A |
| Pin 23 | `PIN_HX711_DOUT2` | Entrada digital | Datos Celda Extremo B |

*Nota:* Compartir SCK permite muestreo simultaneo en un solo ciclo de 24 pulsos gobernado por Timer2 (100 us de tick base).

### 2.3 Actuadores y Servomotores (Salidas PWM / Digitales)

| Pin Mega | Nombre en Codigo | Tipo | Descripcion / Movimiento |
|---|---|---|---|
| Pin 5 | `PIN_SERVO_TALANQUERA` | Servo PWM | Garita de acceso (0 deg = cerrada, 90 deg = abierta) |
| Pin 7 | `PIN_SERVO_AGUJA` | Servo PWM | Aguja desviadora (0 deg = recta, 90 deg = parqueo) |
| Pin 8 | `PIN_FLECHA_VERDE` | Salida digital | Indicador luminoso: pase hacia transferencia |
| Pin 9 | `PIN_FLECHA_AMBAR` | Salida digital | Indicador luminoso: desvio al parqueo |
| Pin 39 | `PIN_ELECTROIMAN` | Salida digital | Rele de activacion de electroiman del cabezal |

*Nota sobre la Aguja Desviadora:* En Fase 2 se reutiliza la aguja para atender el parqueo de retencion:
- Posicion Recta (0 grados): Camion continua hacia transferencia.
- Posicion Parqueo (90 grados): Camion retenido entra al ramal.
- Posicion Liberando: La aguja permite el retorno del camion del parqueo al carril principal tras resolverse la retencion.

### 2.4 Motores Paso a Paso de la Grua (28BYJ-48 + Drivers ULN2003)

| Pin Mega | Nombre en Codigo | Funcion | Driver ULN2003 | Alimentacion |
|---|---|---|---|---|
| Pin 30 | `PIN_TRANS_IN1` | Fase A | Traslacion horizontal IN1 | 5V Externa |
| Pin 31 | `PIN_TRANS_IN2` | Fase B | Traslacion horizontal IN2 | 5V Externa |
| Pin 32 | `PIN_TRANS_IN3` | Fase C | Traslacion horizontal IN3 | 5V Externa |
| Pin 33 | `PIN_TRANS_IN4` | Fase D | Traslacion horizontal IN4 | 5V Externa |
| Pin 34 | `PIN_IZAJE_IN1` | Fase A | Izaje vertical cabezal IN1 | 5V Externa |
| Pin 35 | `PIN_IZAJE_IN2` | Fase B | Izaje vertical cabezal IN2 | 5V Externa |
| Pin 36 | `PIN_IZAJE_IN3` | Fase C | Izaje vertical cabezal IN3 | 5V Externa |
| Pin 37 | `PIN_IZAJE_IN4` | Fase D | Izaje vertical cabezal IN4 | 5V Externa |

*Importante:* El GND de la fuente externa de 5V debe unirse al GND del Arduino Mega para compartir referencia comun de disparo.

### 2.5 Sensores de la Grua y Seguridad

| Pin Mega | Nombre en Codigo | Tipo | Componente / Logica |
|---|---|---|---|
| Pin 38 | `PIN_FC_CONTACTO` | Entrada digital (PULLUP) | Fin de carrera contacto cabezal (LOW = contacto) |
| Pin A0 | `PIN_MARCA_OPTICA` | Entrada analogica | Sensor optico de marcas en el riel de traslacion |
| Pin 18 | `PIN_PARO_EMERGENCIA` | Interrupcion INT5 | Boton hongo NC de paro fisico (LOW = disparo) |

### 2.6 Lector RFID (Modulo RC522 en Bus SPI)

| Pin Mega | Linea SPI | Conector RC522 | Nivel Logico |
|---|---|---|---|
| Pin 53 | SS (Slave Select) | SDA | 3.3V |
| Pin 52 | SCK | SCK | 3.3V |
| Pin 51 | MOSI | MOSI | 3.3V |
| Pin 50 | MISO | MISO | 3.3V |
| Pin 10 | RST | RST (fijo a 3.3V por HW) | 3.3V |
| 3.3V | VCC | VCC | Alimentar de pin 3.3V del Mega |

### 2.7 Pantalla LCD de Garita (Bus I2C)

| Pin Mega | Linea I2C | Modulo LCD 16x2 | Direccion I2C |
|---|---|---|---|
| Pin 20 | SDA | SDA | 0x27 |
| Pin 21 | SCL | SCL | 0x27 |
| 5V / GND | VCC / GND | Alimentacion | -- |

### 2.8 Semaforos y Sensores LDR del Patio Lineal

| Pin Mega | Nombre | Tipo | Descripcion |
|---|---|---|---|
| Pin 40, 41, 42 | Sem_Garita_R/A/V | Salidas digitales | Luces roja, amarilla, verde garita |
| Pin 43, 44, 45 | Sem_Transf_R/A/V | Salidas digitales | Luces roja, amarilla, verde transferencia |
| Pin A8 | LDR P0 N0 | Entrada analogica | Presencia contenedor Posicion 0 Nivel 0 (Base) |
| Pin A9 | LDR P0 N1 | Entrada analogica | Presencia contenedor Posicion 0 Nivel 1 (Alto) |
| Pin A10 | LDR P1 N0 | Entrada analogica | Presencia contenedor Posicion 1 Nivel 0 (Base) |
| Pin A11 | LDR P1 N1 | Entrada analogica | Presencia contenedor Posicion 1 Nivel 1 (Alto) |
| Pin A12, A13 | YARD_LED_PIN[0..1] | Salidas digitales | Indicadores luminosos de posicion de patio |

---

## 3. Puertos Seriales UART en el Arduino Mega 2560

El microcontrolador cuenta con cuatro puertos seriales por hardware:

1. **`Serial` (Pines 0 RX0 y 1 TX0): EN USO PRINCIPAL**
   - Conectado directamente al conversor USB-Serial de la placa.
   - Es el canal utilizado para dialogar con la Raspberry Pi 3 a 115200 baudios sin cableado adicional.
2. **`Serial1` (Pines 19 RX1 y 18 TX1): NO DISPONIBLE COMO UART**
   - El pin 18 se utiliza como entrada de interrupcion externa (INT5) para el `PIN_PARO_EMERGENCIA`.
   - El pin 19 se utiliza como GPIO digital para el `PIN_IR_SALIDA`.
3. **`Serial2` (Pines 17 RX2 y 16 TX2): LIBRE**
   - Disponible como reserva para pruebas de banco con adaptadores USB-TTL externos.
4. **`Serial3` (Pines 15 RX3 y 14 TX3): LIBRE**
   - Disponible como reserva de hardware.

---

## 4. Parqueo de Retencion y Administracion Logica

El enunciado establece que las **tres plazas de parqueo no se instrumentan fisicamente con sensores independientes**. Se reutiliza el ramal fisico construido en Fase 1:
1. El vehiculo desviado por pesaje alterado (RT01), fuera de ventana (RT04) o canal rojo (RT03) ingresa al ramal mediante `AgujaParqueo` (pin 7 a 90 grados).
2. El software del servidor asigna la plaza libre de menor indice (Plaza 1, 2 o 3) y conoce la identidad exacta del vehiculo y su contenedor.
3. Al dictar la resolucion (`Aclarar` o `Corregir`), el servidor comanda `AgujaLiberar`, la aguja se reubica para permitir la salida y el vehiculo regresa al carril principal.
4. Si las 3 plazas se encuentran ocupadas, la garita rechaza inmediatamente cualquier nuevo ingreso que presente riesgo de retencion y dispara la alarma `AL11` (Parqueo de retencion lleno).
