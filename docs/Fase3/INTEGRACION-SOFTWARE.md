# PORTUS Fase 3: integración de software

## Diseño

La lógica nueva corre en procesos separados sobre Raspberry Pi 3 y se comunica
por MQTT con la plataforma de Fase 2. El Arduino Mega conserva sus flujos de
Fase 1. El firmware nuevo agrega GPIO 46 (conmutación de luces), GPIO 47
(baliza) y órdenes `F3` por el mismo USB serial. Los comandos remotos de
movimiento anteriores siguen rechazados por el puente con hardware real.

La lectura ambiental y la cámara se activan al ejecutar sus procesos. Si aún
no se instalan, la plataforma y la maqueta mantienen su operación anterior.
Los sensores ambientales van a la Raspberry, separados de los cables y estados
del Arduino. La alimentación física dependerá del montaje final. Esta es la
arquitectura de dos computadores aprobada para el grupo.
La Raspberry ejecuta toda la función asignada originalmente al ESP32: lectura
de DHT22, YL-83 y BH1750, publicación MQTT y lógica de clima e iluminación.
El teléfono aporta únicamente video USB; el OCR y el conteo corren en la Pi.

## Instalación en Raspberry Pi 3

1. Mantener el despliegue existente de `PortusFase2` y su broker MQTT.
2. Instalar `pip install -r PortusFase3/requirements-pi.txt` y
   `sudo apt install tesseract-ocr`.
3. Habilitar I2C con `raspi-config`. DHT22 usa GPIO4, salida digital del YL-83
   GPIO17, BH1750 el bus I2C 1 en dirección 0x23. Ajustar el comparador de
   lluvia y `--max-lux` con lecturas reales.
4. Desde la raíz ejecutar `python PortusFase3/estacion_pi.py --max-lux 1000`.
   El proceso sigue leyendo sin MQTT y se reconecta automáticamente.
5. Conectar un teléfono Android compatible por un cable USB de datos a un puerto
   USB-A de la Raspberry. En las preferencias USB del teléfono seleccionar
   **Cámara web**. Esta función depende del modelo y del sistema del teléfono;
   Android 14 QPR1 o posterior la admite cuando el fabricante la habilita.
   Comprobar en la Pi con `ls /dev/video*` y `v4l2-ctl --list-devices`
   (paquete `v4l-utils`). Elegir el dispositivo de captura de video, por ejemplo
   `/dev/video0`, en `camera_device` de `PortusFase3/vision_config.json`.
   Montar el teléfono fijo y calibrar `plate_roi` y `queue_roi` con su imagen.
   Preparar el peso público `yolov8n.pt` localmente y ejecutar
   `python PortusFase3/vision_pi.py` desde la raíz. Si el teléfono se desconecta,
   el proceso vuelve a abrir la cámara al reconectarlo; la garita RFID local
   continúa funcionando. Las fotos se escriben en `PortusFase3/fotos/`.

La Raspberry Pi 3 puede procesar los modelos lentamente. Medir la latencia real
antes de fijar `SegundosConteoCola` y de presentar el flujo de ingreso.

## Activación gradual

Cargar el sketch actualizado antes de cablear luces y baliza. Mantener 46/47
desconectados durante las primeras pruebas. La tira LED necesita MOSFET o relé
y fuente adecuada; no se alimenta directamente desde el pin del Mega. Confirmar
con el mapa físico que 46/47 estén libres.

El puente transmite solo `IluminacionEncender`, `IluminacionApagar`,
`GruaSuspender` y `GruaReanudar` con motivo Clima, y los comandos de captura.
Un `F3 PING` distingue inactividad de pérdida de enlace. Los parámetros se
guardan en SQLite y los umbrales de luz deben diferir al menos cinco unidades.
`/clima` devuelve la última lectura o informa que no está disponible.

## Estado pendiente de validación física

La cámara aún no está instalada: el OCR y el conteo no se han comprobado con
imágenes reales. Por defecto la garita física conserva su autorización RFID
local. Con cámara operativa y enlace confirmado, el operador puede activar
"Dos factores" en Operación; el Mega entonces espera la respuesta antes de
abrir. Un rechazo revierte el turno local y deja la talanquera cerrada; si
no llega respuesta, espera decisión manual sin abrir. Esta ruta requiere
prueba física completa antes de la presentación. La LCD inventariada es 16x2
y no puede mostrar cuatro líneas simultáneas.

Los escenarios E01-E13 requieren evidencia real individual. RT07 y RT08
activan la desviación de la aguja después del pesaje en el firmware actualizado
y generan la retención digital; aún faltan pruebas sobre la maqueta para
confirmar el recorrido hasta el parqueo de retención. Lecturas MQTT inyectadas
sirven para probar lógica, no como evidencia de sensores reales.
