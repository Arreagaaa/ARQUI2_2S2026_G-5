# Diagrama de Pines - PORTUS Fase 1

## Arduino Mega 2560 - Mapa de Conexiones

### Bus SPI (RFID MFRC522)

| Pin Mega | Funcion | Modulo RFID |
|---|---|---|
| 53 | SS | SDA |
| 52 | SCK | SCK |
| 51 | MOSI | MOSI |
| 50 | MISO | MISO |
| 10 | RST (no conectado) | RST fijo a 3.3V por hardware |
| 3.3V | Alimentacion | VCC (NO usar 5V) |
| GND | Tierra | GND |

**Nota importante:** el pin RST del modulo RC522 esta fijo a 3.3V por hardware en esta implementacion. `PIN_RFID_RST` en `Config.h` (pin 10) queda documentado pero sin uso. Si se conecta fisicamente el RST al pin 10, la libreria MFRC522 puede fallar al leer el registro de version del chip. Verificar comunicacion SPI con el sketch DumpInfo antes de continuar.

### Bus I2C (LCD 16x2)

| Pin Mega | Funcion | LCD |
|---|---|---|
| 20 | SDA | SDA |
| 21 | SCL | SCL |
| 5V | Alimentacion | VCC |
| GND | Tierra | GND |

Direccion I2C: 0x27

### Pesaje Dinamico (2x HX711)

| Pin Mega | Funcion | HX711 |
|---|---|---|
| 24 | SCK (compartido) | SCK (ambos modulos) |
| 22 | DOUT1 | DOUT (celda extremo A) |
| 23 | DOUT2 | DOUT (celda extremo B) |
| 5V | Alimentacion | VCC (ambos modulos) |
| GND | Tierra | GND (ambos modulos) |

**Nota:** ambos modulos HX711 comparten el pin de reloj (SCK). Las conversiones se leen de forma sincronizada con 24 pulsos compartidos, leyendo DOUT1 y DOUT2 en cada pulso para que ambas mediciones correspondan al mismo instante fisico.

### Grua - Motor de Traslacion (28BYJ-48 + ULN2003)

| Pin Mega | Funcion | Driver ULN2003 |
|---|---|---|
| 30 | IN1 | IN1 |
| 31 | IN2 | IN2 |
| 32 | IN3 | IN3 |
| 33 | IN4 | IN4 |
| 5V ext | Alimentacion motor | VCC (fuente externa) |
| GND | Tierra compartida | GND |

### Grua - Motor de Izaje (28BYJ-48 + ULN2003)

| Pin Mega | Funcion | Driver ULN2003 |
|---|---|---|
| 34 | IN1 | IN1 |
| 35 | IN2 | IN2 |
| 36 | IN3 | IN3 |
| 37 | IN4 | IN4 |
| 5V ext | Alimentacion motor | VCC (fuente externa) |
| GND | Tierra compartida | GND |

### Grua - Sensores y Electroiman

| Pin Mega | Funcion | Componente |
|---|---|---|
| 38 | INPUT_PULLUP | Sensor de contacto (fin de carrera cabezal) |
| A0 | Analogico | Sensor optico de marca de posicion |
| 39 | OUTPUT | Electroiman (via modulo de rele) |

**Nota sobre la marca optica:** la deteccion se hace con `analogRead()` y un umbral fijo de 512. Verificar el valor en reposo al iniciar el sistema (se imprime en el serial como `[GRUA] Marca optica en reposo (analogRead): XXXX`).

### Servomotores

| Pin Mega | Funcion | Componente |
|---|---|---|
| 5 | PWM | Servo talanquera (garita/salida compartida) |
| 7 | PWM | Servo aguja desviadora |

Valores angulares:
- Talanquera: 0 = cerrado, 90 = abierto
- Aguja: 0 = recta (transferencia), 90 = ramal (desvio)

### Semaforos (R/A/V)

| Pin Mega | Color | Estacion |
|---|---|---|
| 40 | Rojo | Garita |
| 41 | Ambar | Garita |
| 42 | Verde | Garita |
| 43 | Rojo | Zona transferencia |
| 44 | Ambar | Zona transferencia |
| 45 | Verde | Zona transferencia |

### Flechas Direccionales (Pesaje)

| Pin Mega | Color | Significado |
|---|---|---|
| 8 | Verde | Continuar a zona de transferencia |
| 9 | Ambar | Desviar al ramal (retencion) |

### Sensores Infrarrojos de Presencia

| Pin Mega | Ubicacion | Logica |
|---|---|---|
| 2 | Espera (antes de garita) | LOW = presencia |
| 3 | Plataforma de pesaje | LOW = presencia |
| 19 | Salida | LOW = presencia |
| 25 | Zona de transferencia | LOW = presencia |
| 26 | Ramal | LOW = presencia |

**Nota:** todos los sensores IR usan logica invertida. Se configuran como `INPUT` sin pull-up. Verificar que el valor leido cambie de HIGH a LOW cuando el camion se posiciona frente al sensor.

### Sensores LDR del Patio

| Pin Mega | Posicion | Nivel | Umbral |
|---|---|---|---|
| A8 | Posicion 0 | Nivel 0 (base) | 545 |
| A9 | Posicion 0 | Nivel 1 (segundo piso) | 356 |
| A10 | Posicion 1 | Nivel 0 (base) | 150 (provisional) |
| A11 | Posicion 1 | Nivel 1 (segundo piso) | 295 |

**Nota:** los LDR se leen con `analogRead()` directamente. No necesitan `pinMode` ni pull-up. Cada sensor tiene su propio umbral configurado en `UMBRAL_LDR_OSCURO` dentro de `Config.h`. El sensor P1N0 es poco confiable y esta deshabilitado por software.

### LEDs de Estado del Patio

| Pin Mega | Posicion |
|---|---|
| A12 | Posicion 0 |
| A13 | Posicion 1 |

Patron de parpadeo:
- Apagado = libre
- Fijo = ocupada
- Parpadeo lento (400ms) = reservada
- Parpadeo rapido (120ms) = bloqueada

### Paro de Emergencia

| Pin Mega | Funcion |
|---|---|
| 18 | INT5, INPUT_PULLUP, FALLING |

Boton momentaneo, normalmente cerrado. Cada pulsacion alterna el estado: la primera detiene todo, la segunda reanuda. Debounce de 250ms.

### Pantalla LCD

| Pin Mega | Funcion |
|---|---|
| 20 | SDA |
| 21 | SCL |

Direccion: 0x27, 16 columnas, 2 filas. Muestra el estado general del sistema.

## Resumen de Uso de Pines

| Rango de Pines | Uso |
|---|---|
| 2, 3, 5, 7, 8, 9, 10 | Sensores, servos, flechas |
| 18 | Paro de emergencia (INT5) |
| 19, 22, 23, 24, 25, 26 | Sensores IR y HX711 |
| 20, 21 | I2C (LCD) |
| 30-39 | Motores stepper, electroiman, sensor contacto |
| 40-45 | Semaforos |
| 50-53 | SPI (RFID) |
| A0 | Sensor optico de marca |
| A8-A13 | LDR patio y LEDs de estado |
