# PORTUS — Bitácora de cierre de la fase 3

**Estado al 26-10-2026:** fase terminada según confirmación del equipo responsable, incluida la integración física y la ejecución de los escenarios E01–E13. La verificación reproducible en este repositorio cubre 34 pruebas automatizadas y 12 escenarios de lógica. Los registros individuales de sensores, OCR, fotografías de la maqueta y mediciones de aceptación no fueron incorporados a Git; por ello no se publican valores cuantitativos que no puedan comprobarse aquí.

## 1. Desarrollo y comprobación registrada

| Fecha | Hito | Evidencia en el repositorio |
| --- | --- | --- |
| 22-10-2026 | Extensión `F3` del Mega, estación ambiental, visión en Pi, reglas web/MQTT, interfaz y mensajería. | Firmware, `PortusFase3/`, servidor y documentación técnica. |
| 22-10-2026 | Adaptación de la estación a GPIO de la Pi y cámara USB; sustitución del BH1750 por LDR con ADS1115. | `estacion_pi.py`, `vision_pi.py`, `vision_config.json` y guía de conexión. |
| 26-10-2026 | Verificación aislada del software de fases 2 y 3 con SQLite temporal. | `py -3.13 PortusFase2/tests/run_isolated.py`: **34 pruebas y 12 escenarios de lógica correctos**. |
| 26-10-2026 | Cierre del montaje y de las pruebas físicas comunicado por el equipo responsable. | Confirmación del equipo; las actas y capturas individuales no están versionadas. |

## 2. Escenarios de aceptación

El equipo confirmó la ejecución de los trece escenarios con la maqueta. Esta tabla consigna ese cierre; **no sustituye las mediciones ni las fotografías individuales**. Los tests automatizados verifican reglas de software y no certifican por sí solos el comportamiento físico.

| Código | Comprobación | Estado comunicado |
| --- | --- | --- |
| E01 | Estación y cuatro magnitudes en el sinóptico. | Realizado por el equipo |
| E02 | Lluvia durante un trabajo de grúa y aviso. | Realizado por el equipo |
| E03 | Bloqueo de reanudación manual mientras llueve. | Realizado por el equipo |
| E04 | Reanudación tras periodo seco. | Realizado por el equipo |
| E05 | Histéresis de la iluminación al cubrir y descubrir el LDR. | Realizado por el equipo |
| E06 | Desconexión de estación, alarma AL16 y respuesta segura. | Realizado por el equipo |
| E07 | RFID y placa correctos, ingreso y notificación. | Realizado por el equipo |
| E08 | Tarjeta de otro camión y retención RT07. | Realizado por el equipo |
| E09 | Placa restringida y retención RT08. | Realizado por el equipo |
| E10 | Placa ilegible y decisión manual. | Realizado por el equipo |
| E11 | Conteo de fila y alarma AL19. | Realizado por el equipo |
| E12 | Cámara desconectada y operación manual degradada. | Realizado por el equipo |
| E13 | Consulta `/clima` por mensajería. | Realizado por el equipo |

## 3. Evidencia disponible y alcance público

- El código de firmware, puente, servidor, frontend, estación y visión está versionado.
- Las pruebas de software son repetibles con el comando indicado arriba.
- Los archivos STL disponibles se enumeran en el [inventario 3D](INVENTARIO-FABRICACION-3D.md).
- La fotografía local de una placa mostrada en teléfono (`capturas/camara-20261024-164923.jpg`) está excluida de Git y no demuestra por sí sola la tasa de acierto OCR.
- Las fotografías generadas por visión en `PortusFase3/fotos/` se excluyen de Git. Tampoco hay un registro público de veinte lecturas OCR, de precisión del conteo, de voltajes de calibración o de latencias medidas. No se infieren cifras a partir de la confirmación de cierre.

La [guía de montaje](GUIA-MONTAJE-Y-PRUEBAS.md) conserva el procedimiento para reproducir la integración con otro equipo físico.
