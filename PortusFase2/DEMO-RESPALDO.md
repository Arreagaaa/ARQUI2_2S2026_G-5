# Respaldo de demostracion

Los scripts de esta carpeta generan y prueban datos **simulados**. No mueven la
maqueta ni convierten observaciones simuladas en evidencia de sensores reales.

## Prueba de flujo del controlador simulado

Desde la raiz del repositorio, con el entorno Python activo:

```bash
python3 PortusFase2/demo_flow.py
```

Comprueba ACK/NAK de talanquera, aguja, grua y mantenimiento. El simulador
actual no reproduce el movimiento fisico de la grua ni del electroiman.

## Base separada para el dashboard

```bash
python3 PortusFase2/prepare_demo_db.py
```

Para abrir esa base en la Raspberry, detener primero el servidor de hardware:

```bash
PORTUS_DB_PATH="$HOME/ARQUI2_2S2026_G-5/PortusFase2/server/portus_demo.db" \
PORTUS_DEMO_DATA=true python3 PortusFase2/run_fase2.py --mock
```

El frontend local sigue en `http://localhost:5173` con `PORTUS_API` apuntando a
la Raspberry. Al volver a las pruebas fisicas, detener el mock y arrancar el
servidor con `PORTUS_USE_MOCK=false` y `/dev/ttyACM0`. La base real
`portus_hardware.db` no se toca.
