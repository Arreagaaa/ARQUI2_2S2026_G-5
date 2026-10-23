# PORTUS — Bitácora y evidencias de la fase 3

**Estado:** pendiente de montaje y pruebas físicas. Este archivo distingue las verificaciones de software realizadas de las observaciones que todavía faltan. Adjuntar fotos, capturas y videos con fecha, responsable, código probado y referencia a la pieza o escenario; no sustituir evidencia real por simulaciones.

## 1. Registro de desarrollo

| Fecha | Cambio o decisión | Evidencia disponible | Pendiente |
|---|---|---|---|
| 22-10-2026 | Commit `a09347a`: extensión `F3` del Mega, estación y visión en Pi, reglas web/MQTT, interfaz y mensajería. | Código fuente y documentación del repositorio. | Compilar firmware y probar con hardware. |
| 22-10-2026 | Adaptación de la estación al GPIO de la Pi y teléfono como cámara USB, según el mensaje de autorización aportado al equipo. | `estacion_pi.py`, `vision_pi.py`, `vision_config.json`. | Confirmar fuente, carcasa, compatibilidad UVC y montaje. |
| 22-10-2026 | Corrección de decisión manual antigua, lecturas ambientales fallidas o vencidas y reinicio/pérdida del enlace de garita. | Pruebas aisladas: **29 pruebas y 12 escenarios correctos**; `compileall` y `git diff --check` correctos. | Repetir en maqueta; no hay compilación AVR ni mediciones físicas. |

**Incidencias nuevas:** registrar aquí síntoma, pasos para reproducir, causa comprobada, modificación y resultado de repetición. Evitar declarar resuelta una incidencia solo porque cambió el código.

| Fecha | Responsable | Síntoma y prueba | Causa comprobada | Corrección | Nueva evidencia |
|---|---|---|---|---|---|
| Pendiente | Pendiente | Pendiente | Pendiente | Pendiente | Pendiente |

## 2. Evidencia del montaje

| Elemento | Foto o archivo editable | Componentes, alimentación y medición | Estado |
|---|---|---|---|
| Diagrama eléctrico de estación | Pendiente | Fuente, DHT22, YL-83, BH1750, GPIO y GND | Pendiente |
| Diagrama eléctrico de iluminación y baliza | Pendiente | Fuente, MOSFET/relé, protecciones y polaridad | Pendiente |
| Estación terminada en carcasa | Pendiente | Ventilación y escurrimiento del sensor de lluvia | Pendiente |
| Teléfono y soporte fijo | Pendiente | Modelo, modo UVC, `/dev/video*`, distancia y ángulo | Pendiente |
| ROI de placa y fila sobre fotograma | Pendiente | Captura marcada y valores finales de `vision_config.json` | Pendiente |
| Mega, luces y baliza conectados | Pendiente | Pines 46/47, tensión y corriente observadas | Pendiente |

Guardar los archivos de evidencia bajo `docs/Fase3/evidencias/` cuando existan, con nombres como `2026-10-22_E07_ingreso-valido.jpg`. No crear fotos vacías ni resultados ficticios.

## 3. Versiones y mediciones de visión

| Dato | Valor medido |
|---|---|
| Modelo y versión del teléfono; modo UVC | Pendiente |
| Dispositivo de video y resolución real | Pendiente |
| Tesseract (`tesseract --version`) | Pendiente |
| Ultralytics (`python -c "import ultralytics; print(ultralytics.__version__)"`) | Pendiente |
| Origen exacto y SHA-256 de `yolov8n.pt` | Pendiente |
| Latencia OCR por ingreso, promedio y máximo | Pendiente |
| Latencia de conteo, promedio y máximo | Pendiente |

**Tasa de acierto de placas:** realizar al menos veinte capturas reales con la cámara fija. Por intento registrar UID, placa visible real, lectura OCR, confianza, iluminación, acierto y ruta de la fotografía. Calcular `aciertos / intentos × 100`; conservar también los fallos.

| Intento | Placa real | Lectura OCR | Confianza | Luz/condición | Acierto | Foto |
|---:|---|---|---:|---|---|---|
| 01–20 | Pendiente, una fila por captura | Pendiente | Pendiente | Pendiente | Pendiente | Pendiente |

**Conteo de fila:** fotografiar y medir cada condición con la misma ROI.

| Camiones reales | Conteo mostrado | Acierto | Captura | Observaciones |
|---:|---:|---|---|---|
| 0 | Pendiente | Pendiente | Pendiente | Pendiente |
| 1 | Pendiente | Pendiente | Pendiente | Pendiente |
| 2 | Pendiente | Pendiente | Pendiente | Pendiente |
| 3 | Pendiente | Pendiente | Pendiente | Pendiente |

## 4. Escenarios de aceptación E01–E13

Cada resultado está **pendiente** hasta ejecutarlo en la maqueta con sensores y cámara reales. Anotar la captura o video y el estado de web, Mega, Telegram y alarmas según corresponda.

| Código | Prueba breve | Resultado | Evidencia y observaciones |
|---|---|---|---|
| E01 | Encender estación; ver cuatro magnitudes en sinóptico. | Pendiente | Pendiente |
| E02 | Mojar sensor durante trabajo de grúa; suspensión y aviso. | Pendiente | Pendiente |
| E03 | Intentar reanudar manualmente mientras llueve. | Pendiente | Pendiente |
| E04 | Secar sensor; reanudación automática tras periodo. | Pendiente | Pendiente |
| E05 | Cubrir y descubrir sensor de luz; histéresis. | Pendiente | Pendiente |
| E06 | Desconectar estación; AL16, clima desconocido y luces encendidas. | Pendiente | Pendiente |
| E07 | RFID y placa correctos; apertura y foto al transportista. | Pendiente | Pendiente |
| E08 | Tarjeta de otro camión; RT07 y desvío tras pesaje. | Pendiente | Pendiente |
| E09 | Restringir placa; RT08 y resolución por autoridad. | Pendiente | Pendiente |
| E10 | Cubrir placa; intentos y confirmación manual con foto. | Pendiente | Pendiente |
| E11 | Alcanzar `UmbralCola`; conteo y AL19. | Pendiente | Pendiente |
| E12 | Desconectar cámara; AL18 e ingreso degradado manual. | Pendiente | Pendiente |
| E13 | Enviar `/clima`; recibir lectura y estado de grúa. | Pendiente | Pendiente |

Antes de la presentación, repetir E01–E13 de forma continua en ese orden y documentar también una operación completa de depósito y otra de retiro para confirmar la continuidad de fases 1 y 2.

## 5. Fabricación 3D y presentación

Registrar piezas y porcentaje en el [inventario de fabricación](INVENTARIO-FABRICACION-3D.md), con archivos editables y fotos reales. El guion y la presentación se incorporarán a `docs/Fase3/` cuando queden definitivos; todavía no son evidencia de funcionamiento físico.
