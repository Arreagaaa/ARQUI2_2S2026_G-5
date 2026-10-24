# PORTUS — Guía de montaje e integración de la fase 3

Esta guía organiza las conexiones y pruebas para quien arma la maqueta. Describe lo que el código **espera**; la revisión eléctrica con los componentes reales determina el esquema final. El [documento técnico](DOCUMENTO-TECNICO.md) explica las reglas y mensajes; la [bitácora](BITACORA-Y-EVIDENCIAS.md) registra lo observado.

## 1. Antes de conectar

1. Confirmar en la maqueta el [mapa de fase 2](../Fase2/MAPA-PINES-Y-HARDWARE.md), el [diagrama de fase 1](../Fase1/DIAGRAMA-PINES.md) y `PortusFase1_INO/PortusFase1/Config.h`.
2. Verificar con multímetro que Mega 46 y 47 estén libres; no mover los cables existentes sin actualizar el mapa.
3. Registrar modelo, tensión, corriente y polaridad de cada módulo de sensor, relé, MOSFET, baliza y fuente. La Raspberry trabaja a 3.3 V: **no introducir 5 V en sus GPIO**.
4. Dibujar el circuito final con alimentación, tierras, resistencias y etapas de potencia. Guardar archivo editable e imagen en la bitácora. La tabla siguiente no reemplaza el diagrama eléctrico.
5. No alimentar la tira LED desde el pin 46. Usar fuente y etapa de potencia. En la maqueta probada, el relé de iluminación se activa con LOW; el firmware lo configura mediante `RELE_F3_ILUMINACION_ACTIVO_BAJO`.

## 2. Pines y conexiones nuevas

| Equipo | Señal de código | Conexión prevista | Confirmación requerida |
|---|---|---|---|
| Mega 2560 | `PIN_F3_ILUMINACION` | Digital 46 a entrada de MOSFET o relé | Libre, polaridad y corriente de la etapa. |
| Mega 2560 | `PIN_F3_BALIZA` | Digital 47 a driver de baliza ámbar | Libre, resistencia o transistor según carga. |
| Raspberry Pi 3 | DHT22 `--dht-pin 4` | BCM GPIO4, pin físico 7 | Alimentación y pull-up del módulo. |
| Raspberry Pi 3 | YL-83 `--rain-pin 17` | Salida digital a BCM GPIO17, pin físico 11 | Nivel máximo 3.3 V; LOW significa lluvia. |
| Raspberry Pi 3 | ADS1115 `--ads1115-address 0x48` | VDD 3.3 V, GND, SDA BCM2/pin 3, SCL BCM3/pin 5; ADDR a GND | Verificar dirección con `i2cdetect -y 1`; entrada A0 nunca mayor que VDD. |
| Raspberry Pi 3 | LDR `--ldr-channel 0` | 3.3 V → LDR → nodo A0 del ADS1115 → resistencia fija 10 kΩ → GND | Medir A0 en oscuridad y luz; mayor voltaje debe significar más luz. |
| Teléfono–Pi | Cámara web USB | Cable USB de datos al puerto USB-A de la Pi | Debe aparecer como `/dev/video*`, no solo cargar. |
| Mega–Pi | Serial existente | USB al Mega, normalmente `/dev/ttyACM0`, 115200 | No se usan pines UART 0/1 adicionales. |

BCM y posición física del encabezado son numeraciones distintas. La estación se monta con carcasa ventilada y sensor de lluvia inclinado; la fuente y el aislamiento definitivos se documentan después de seleccionar los módulos.

El divisor LDR con resistencia fija es el mismo tipo de conexión que se usa en los LDR del patio, pero este sensor nuevo se lee en la Pi mediante ADS1115. La [guía oficial de fotoceldas de Adafruit](https://learn.adafruit.com/photocells/circuitpython) describe el divisor con 10 kΩ; la [guía del ADC](https://learn.adafruit.com/raspberry-pi-analog-to-digital-converters/ads1015-slash-ads1115) muestra la conexión I2C a la Pi. Alimentar el ADS1115 a 3.3 V y mantener A0 dentro de esa tensión.

## 3. Conexiones anteriores que se conservan

| Subsistema | Pines Mega 2560 |
|---|---|
| RFID RC522 SPI | SS 53; SCK 52, MOSI 51, MISO 50; RST definido en 10, documentado como fijo a 3.3 V en el montaje anterior. |
| HX711 doble | DOUT 22 y 23; SCK compartido 24. |
| Servos | Talanquera compartida ingreso/salida 5; aguja 7. |
| Presencia IR | Espera 2; pesaje 3; salida 19; transferencia 25; ramal 26. |
| Grúa | Traslación 30–33; izaje 34–37; contacto 38; electroimán por relé 39; marca óptica A0. |
| Señalización | Flechas 8 y 9; semáforo garita 40–42; transferencia 43–45. |
| LCD y seguridad | LCD I2C SDA 20/SCL 21; paro de emergencia 18. |
| Patio | LDR A8–A11; indicadores A12–A13. |

## 4. Preparación de software

1. Abrir `PortusFase1_INO/PortusFase1/PortusFase1.ino` **con todos los `.cpp` y `.h` de su carpeta**. Compilar para Mega 2560, registrar versión de Arduino IDE, librerías y memoria usada; cargar solo tras confirmar pines.
2. Conservar la instalación existente de `PortusFase2` y Mosquitto. Configurar puerto serial real y ejecutar el puente y servidor según el [manual de fase 2](../Fase2/MANUAL-DESPLIEGUE-Y-PRUEBAS.md). El doble factor queda apagado inicialmente.
3. Para la estación ambiental instalar `pip install --no-cache-dir -r PortusFase3/requirements-station.txt`. Este archivo evita descargar PyTorch y CUDA, que no se usan para el LDR, DHT22 ni lluvia. La visión se prepara por separado con `requirements-pi.txt`, `tesseract-ocr` y `v4l-utils` cuando se vaya a probar la cámara. Habilitar I2C con `raspi-config` y verificar el ADS1115 en `0x48` con `i2cdetect -y 1`.
4. Medir el voltaje de A0 con el LDR cubierto y bien iluminado. El arranque real en la Raspberry inicia la estación automáticamente con la calibración de campo 0.001 V (oscuro) y 0.252 V (claro). Si cambia el divisor, definir `PORTUS_LDR_DARK_VOLTAGE` y `PORTUS_LDR_BRIGHT_VOLTAGE` al iniciar `run_fase2.py`. La salida `luz` es porcentaje relativo, **no lux**. Calibrar también la polaridad del YL-83. La configuración de periodos se guarda en `PortusFase3/station_settings.json`.
5. Activar el modo **Cámara web** en un teléfono compatible. Verificar `ls /dev/video*` y `v4l2-ctl --list-devices`; ajustar `camera_device`, `plate_roi` y `queue_roi` en `PortusFase3/vision_config.json`. Instalar el peso público `yolov8n.pt` y ejecutar `python PortusFase3/vision_pi.py`.

## 5. Orden de pruebas de banco

| Paso | Prueba | Resultado que se debe registrar |
|---|---|---|
| A | Fases 1 y 2 con doble factor apagado y pines 46/47 desconectados. | RFID, talanquera, pesaje, grúa, patio, salida y web continúan. |
| B | Lecturas reales de DHT22, YL-83 y LDR por ADS1115. | Voltajes oscuro/claro, porcentaje 0–100, polaridad de lluvia, frecuencia y reconexión MQTT. |
| C | Luces y baliza con sus etapas de potencia. | Encendido/apagado, histéresis y parpadeo sin bloquear grúa. |
| D | Suspensión con lluvia durante un trabajo; secado. | Trabajo termina; no inicia otro; reanuda tras periodo configurado. |
| E | Cámara USB fija y regiones de interés calibradas. | Foto legible, veinte intentos OCR, conteo con 0–3 vehículos. |
| F | Doble factor activo y fallas inducidas. | Coincidencia, rechazo, RT07/RT08, decisión manual, cámara desconectada, reinicios. |
| G | Corrida continua E01–E13. | Resultado y evidencia de cada escenario en la bitácora. |

El teléfono necesita un modo UVC habilitado por su fabricante; conectarlo por USB no garantiza que entregue video. La Raspberry Pi 3 puede tardar en YOLO y OCR: medir la latencia real antes de la demostración. Las fotos de ejecución se guardan en `PortusFase3/fotos/` y no están versionadas.

## 6. Registro de aceptación física

Para cada prueba anotar fecha, responsable, versión del código, cableado real, resultado esperado, resultado observado, captura/foto/video y corrección si falló. Usar la [bitácora y matriz E01–E13](BITACORA-Y-EVIDENCIAS.md). No marcar una prueba como aprobada por una lectura MQTT inyectada o por la suite de software: el enunciado exige sensores y cámara reales durante la evaluación.
