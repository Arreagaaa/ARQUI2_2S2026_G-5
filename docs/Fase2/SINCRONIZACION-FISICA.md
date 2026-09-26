# Sincronización de PORTUS con el firmware que corre en la maqueta

Esta versión usa el protocolo serial que emite Fase1. El bridge consulta
`ESTADO`, `PATIO` y `GRUA` cada dos segundos. Son comandos de lectura que ya
soporta el Mega. No hace falta cambiar el control de motores o sensores para
recibir el número de turnos activos, sus estaciones, los pesos, el estado de
paro y la ocupación general del patio. Las lecturas en vivo llegan además por
los mensajes seriales espontáneos.

El firmware ampliado en este repositorio añade líneas `@PORTUS` con detalle
de talanquera, aguja, identidad de cada celda y trabajo de grúa. Son solo
impresiones de supervisión. Hasta que se cargue al Mega, las vistas muestran
**Sin confirmar** o **Sin medición** donde Fase1 no emite la información;
no inventan identidades, posiciones ni distancias. El estado documental de
Fase2 tampoco se presenta como autorización física del Mega.

## Actualizar la Raspberry desde el paquete entregado

El archivo `PORTUS-sincronizacion-2026-09-26.zip` incluye el código y el
frontend ya construido. Desde Windows, en la raíz del repositorio:

```powershell
scp .\PORTUS-sincronizacion-2026-09-26.zip javier@192.168.0.13:~/
```

En la Raspberry, detener el proceso actual con `Ctrl+C` y ejecutar:

```bash
cd ~/ARQUI2_2S2026_G-5
python3 -m zipfile -e ~/PORTUS-sincronizacion-2026-09-26.zip .
source venv/bin/activate
PORTUS_USE_MOCK=false python3 PortusFase2/run_fase2.py --port /dev/ttyACM0
```

El dashboard actualizado queda en `http://IP_DE_LA_RASPBERRY:5000`.
Si se sigue usando Vite en `:5173`, reiniciar también `pnpm dev`; su proxy
debe apuntar a la Raspberry actualizada.

El arranque real usa `PortusFase2/server/portus_hardware.db`. El antiguo
`portus_fase2.db` queda intacto, con las citas y métricas de demostración
que ya contenía. La base nueva empieza sin operaciones ficticias. Los
usuarios y el catálogo base sí se crean una sola vez. Cada reinicio conserva
los registros observados.

`PortusFase2/hardware_catalog.json` relaciona los vehículos y contenedores
precargados del sketch con transportista y naviera. Revisar ese archivo si
se cambiaron los UID o la asignación de la maqueta.

No se debe interpretar `En vivo` como una confirmación de cada sensor. El
sinóptico muestra explícitamente fuente, última observación y valores que
el firmware realmente confirmó. Las órdenes remotas incompatibles con el
firmware Fase1 se rechazan; el control físico sigue en la maqueta.

## Validación

En una base temporal y modo simulación para las pruebas originales:

```bash
cd ~/ARQUI2_2S2026_G-5
source venv/bin/activate
python3 PortusFase2/tests/run_isolated.py
```

La prueba de regresión nueva reproduce el log MQTT real del 26 de septiembre:
dos vehículos, lecturas de 1.16 kg y 1.40 kg, fallas de grúa, cambios de
enlace, salidas y rechazos de RFID. También comprueba la lectura por roles,
aislamiento de navieras, CRC y actualización por estados físicos.
