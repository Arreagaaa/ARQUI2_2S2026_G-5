# Fase 3: revisión de software y conexiones para integración

Estado revisado el 22 de octubre de 2026. Este reporte describe el código actual
para Arduino Mega 2560 y Raspberry Pi 3. La validación de pines y de sensores
sobre la maqueta sigue siendo indispensable antes de la presentación.

## Qué se agregó al código

- `PortusFase1_INO/PortusFase1/Fase3Control.cpp` y `.h`: iluminación,
  baliza, suspensión por clima, captura y respuesta de garita por comandos
  seriales `F3`. El parpadeo y la detección de pérdida de enlace usan `millis()`.
- El sketch original incorporó llamadas a `fase3_init()` y `fase3_update()`.
  La grúa termina el trabajo en curso antes de dejar de tomar trabajos al
  recibir suspensión por clima. Garita, pesaje y salida conservan su control
  local anterior. El modo de verificación por placa arranca desactivado y se
  habilita desde Operación cuando la cámara está operativa.
- `PortusFase3/estacion_pi.py`: la Raspberry lee DHT22, salida digital del
  comparador de lluvia YL-83 y BH1750; publica lectura y latido por MQTT.
- `PortusFase3/vision_pi.py`: la Raspberry lee la cámara del teléfono como
  dispositivo USB de video, hace OCR por evento RFID y conteo periódico de la
  fila. El dispositivo, las regiones de interés y el modelo se configuran en
  `vision_config.json`.
- El servidor de Fase 2 recibió reglas de clima, iluminación, acceso por
  RFID y placa, alarmas, retenciones, parámetros, auditoría, fotos y nuevos
  endpoints. El frontend recibió páginas de Accesos, Placas restringidas y
  parámetros de Fase 3. Telegram recibió `/clima` y avisos nuevos.
- El puente serial conserva el rechazo de comandos remotos de movimiento de
  Fase 2 en hardware real. Solo transmite los comandos `F3` permitidos.

## Conexiones nuevas para el ingeniero

| Equipo | Señal del código | Conexión prevista | Comprobación física |
|---|---|---|---|
| Mega 2560 | `PIN_F3_ILUMINACION` | Pin digital 46 hacia entrada de MOSFET o relé de la iluminación | El pin entrega una señal lógica; la tira LED usa fuente y etapa de potencia propias. Confirmar polaridad del módulo. |
| Mega 2560 | `PIN_F3_BALIZA` | Pin digital 47 hacia baliza ámbar | Usar resistencia y, si el consumo lo exige, transistor de manejo. Confirmar polaridad. |
| Raspberry Pi 3 | DHT22 `--dht-pin 4` | BCM GPIO4, pin físico 7 | Revisar alimentación y resistencia de pull-up del módulo utilizado. |
| Raspberry Pi 3 | YL-83 digital `--rain-pin 17` | BCM GPIO17, pin físico 11 | La salida digital del comparador debe ser compatible con 3.3 V; no ingresar 5 V al GPIO. El código interpreta LOW como lluvia. |
| Raspberry Pi 3 | BH1750 `--bh1750-address 0x23` | I2C 1: SDA BCM2/pin físico 3 y SCL BCM3/pin físico 5 | Habilitar I2C, compartir GND y verificar la dirección del módulo con `i2cdetect -y 1`. |
| Raspberry Pi 3 | Cámara del teléfono | Cable USB de datos a un puerto USB-A de la Pi | El teléfono debe exponer modo Cámara web/UVC y aparecer como `/dev/video*`; configurar la ruta real en `vision_config.json`. |
| Mega ↔ Pi | Serial existente | USB del Mega hacia la Raspberry; por defecto `/dev/ttyACM0`, 115200 baudios | No se agrega UART ni se cambian los pines 0/1. |

Las referencias BCM y el número físico del encabezado son sistemas distintos.
La Raspberry usa señales GPIO de 3.3 V. El esquema de alimentación y la
capacidad de corriente deben validarse con los módulos reales.
Referencia de numeración y niveles GPIO:
https://www.raspberrypi.com/documentation/computers/raspberry-pi.html

## Conexiones existentes que el código conserva

| Subsistema | Pines Mega 2560 |
|---|---|
| RFID RC522 SPI | SS 53; SCK 52, MOSI 51, MISO 50; RST definido en 10 pero fijo a 3.3 V en el montaje documentado |
| HX711 doble | DOUT 22 y 23; SCK compartido 24 |
| Servos | Talanquera compartida de ingreso/salida 5; aguja 7 |
| Presencia IR | Espera 2; pesaje 3; salida 19; transferencia 25; ramal 26 |
| Grúa | Traslación 30–33; izaje 34–37; contacto 38; electroimán por relé 39; marca óptica A0 |
| Señalización | Flechas 8 y 9; semáforo garita 40–42; semáforo transferencia 43–45 |
| LCD y seguridad | LCD I2C SDA 20/SCL 21; paro de emergencia 18 |
| Patio | LDR A8–A11; indicadores A12–A13 |

Estos pines se tomaron de `Config.h` y del mapa de hardware de Fase 2. Los
pines 46 y 47 no aparecen ocupados en ese mapa, pero hay que verificar la
maqueta física antes de soldar o conectar.

## Correcciones realizadas durante esta revisión

1. En `Fase3Control.cpp`, el Mega ahora enciende la iluminación si no recibe
   ningún comando `F3` durante los primeros 15 segundos tras arrancar. Antes,
   la protección por pérdida de enlace solo funcionaba después del primer
   comando.
2. En `server/app.py`, el resultado OCR solo responde al acceso pendiente si
   coincide el UID RFID. Un resultado retrasado de otro vehículo queda
   registrado, pero ya no puede autorizar el acceso actual.

## Comprobaciones de software ejecutadas

- Compilación de sintaxis Python (`compileall`): correcta.
- Build de frontend (`pnpm build`): correcto.
- Pruebas de lógica Fase 3 y telemetría de hardware: 10/10 correctas,
  incluida la prueba de OCR tardío frente a otro UID pendiente.
- Validación de escenarios de Fase 2: 12/12 correctas.
- Suite completa de Python: 27 pruebas ejecutadas, 22 correctas, 4 fallos y
  1 error en `test_api_gaps.py`. Esas cinco pruebas esperan órdenes remotas de
  ingreso/resolución que el modo de hardware real de Fase 2 rechaza con 409;
  son incompatibles con el comportamiento aprobado de control local y no se
  modificaron para esta fase.
- `git diff --check`: sin errores de espacio. Las advertencias de CRLF son
  de conversión de fin de línea.

No se pudo compilar el sketch en esta máquina porque no está instalado
`arduino-cli` ni el compilador AVR. La carga al Mega y la validación de
memoria del firmware quedan para el equipo con Arduino IDE.

## Pruebas de integración pendientes antes del push final

1. Confirmar con el ingeniero que los pines 46 y 47 están libres y que los
   módulos de potencia responden a HIGH como espera el código.
2. Probar en la Pi lecturas reales de temperatura, humedad, lluvia y luz;
   calibrar `--max-lux` y la polaridad del comparador YL-83.
3. Confirmar que el teléfono aparece como cámara UVC en la Pi, fijar el
   soporte y calibrar `plate_roi` y `queue_roi` con la imagen real.
4. Probar OCR sobre al menos 20 capturas y conteo con 0, 1, 2 y 3 camiones.
5. Activar el modo de dos factores solo después de comprobar el flujo de
   garita; verificar apertura correcta, rechazo, RT07/RT08 y confirmación
   manual. El sensor de proximidad y el servo existentes siguen operando.
6. Ejecutar E01–E13 sobre la maqueta y revisar sus efectos en sinóptico,
   alarmas, Telegram y auditoría. Incluir una operación de depósito y retiro
   para comprobar continuidad de Fases 1 y 2.

El código está listo para una revisión y pruebas de banco; todavía no hay
evidencia de que todos los escenarios funcionen a la primera en el hardware.
