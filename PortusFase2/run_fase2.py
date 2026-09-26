"""
Script maestro de arranque unificado para PORTUS Fase 2.
Levanta en un solo comando:
  1. Broker MQTT (Mosquitto si esta disponible, o broker amqtt integrado)
  2. Inicializacion y migracion de base de datos SQLite con datos semilla
  3. Puente de comunicacion Serial-MQTT (hardware real o simulador de Arduino Mega)
  4. Servidor web Flask en http://localhost:5000 con soporte de SSE y WebSockets
"""

import sys
import os
import time
import socket
import argparse
import logging
import threading
import subprocess

# Asegurar que el directorio de la solucion este en sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Configure before importing app/database (which initializes SQLite).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass
mock_requested = "--mock" in sys.argv or os.environ.get("PORTUS_USE_MOCK", "false").lower() in ("true", "1", "yes")
os.environ.setdefault("PORTUS_DEMO_DATA", "true" if mock_requested else "false")
os.environ.setdefault("PORTUS_DB_PATH", os.path.join(os.path.dirname(__file__), "server", "portus_mock.db" if mock_requested else "portus_hardware.db"))

from PortusFase2.server.database import init_database
from PortusFase2.bridge.serial_bridge import SerialMQTTBridge
from PortusFase2.server.app import app, init_mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def start_embedded_mqtt_broker(port: int = 1883):
    """
    Si no hay un broker Mosquitto corriendo en el puerto 1883,
    inicia un broker amqtt ligero en segundo plano.
    """
    if is_port_in_use(port):
        logging.info("Broker MQTT detectado y activo en el puerto %d", port)
        return None

    logging.info("Iniciando broker MQTT amqtt integrado en el puerto %d...", port)
    broker_code = f"""
import asyncio
from amqtt.broker import Broker

config = {{
    'listeners': {{
        'default': {{
            'type': 'tcp',
            'bind': '0.0.0.0:{port}',
            'max_connections': 100
        }}
    }},
    'sys_interval': 0,
    'auth': {{
        'allow-anonymous': True
    }}
}}

async def start():
    broker = Broker(config)
    await broker.start()
    while True:
        await asyncio.sleep(1)

asyncio.run(start())
"""
    proc = subprocess.Popen([sys.executable, "-c", broker_code])
    # Esperar hasta 5 segundos a que abra el puerto
    for _ in range(10):
        time.sleep(0.5)
        if is_port_in_use(port):
            logging.info("Broker MQTT integrado listo en puerto %d", port)
            return proc

    logging.warning("El broker MQTT tardo en iniciar, continuando...")
    return proc


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def main():
    default_port = os.environ.get("PORTUS_SERIAL_PORT", "/dev/ttyACM0" if sys.platform.startswith("linux") else "COM3")
    default_baud = int(os.environ.get("PORTUS_SERIAL_BAUD", 115200))
    default_mock = os.environ.get("PORTUS_USE_MOCK", "false").lower() in ("true", "1", "yes")
    default_mqtt_port = int(os.environ.get("PORTUS_MQTT_PORT", 1883))
    default_web_port = int(os.environ.get("PORTUS_WEB_PORT", 5000))

    parser = argparse.ArgumentParser(description="PORTUS Fase 2 - Sistema Integrado de Control Portuario")
    parser.add_argument("--port", default=default_port, help="Puerto serial del Arduino Mega")
    parser.add_argument("--baud", type=int, default=default_baud, help="Baudrate serial (defecto 115200)")
    parser.add_argument("--mock", action="store_true", default=default_mock, help="Forzar modo simulador del Arduino Mega")
    parser.add_argument("--mqtt-port", type=int, default=default_mqtt_port, help="Puerto del broker MQTT (defecto 1883)")
    parser.add_argument("--web-port", type=int, default=default_web_port, help="Puerto del servidor web (defecto 5000)")
    args = parser.parse_args()

    print("=" * 65)
    print("      PORTUS - Fase 2: Terminal Portuaria Conectada")
    print("      Arquitectura de Computadoras y Ensambladores 2 - USAC")
    print("=" * 65)

    # 1. Base de datos
    logging.info("Paso 1: Inicializando base de datos SQLite y semillas...")
    logging.info("Base de datos: %s", os.environ["PORTUS_DB_PATH"])

    # 2. Broker MQTT
    logging.info("Paso 2: Verificando disponibilidad de intermediario MQTT...")
    broker_proc = start_embedded_mqtt_broker(args.mqtt_port)

    # 3. Puente Serial-MQTT
    logging.info("Paso 3: Iniciando puente Serial-MQTT (Puerto: %s, Mock: %s)...", args.port, args.mock)
    bridge = SerialMQTTBridge(
        port=args.port,
        baudrate=args.baud,
        mqtt_host="127.0.0.1",
        mqtt_port=args.mqtt_port,
        use_mock=args.mock
    )
    init_mqtt()
    bridge.start()



    # 5. Servidor Web
    print("-" * 65)
    print(f" Servidor disponible en: http://localhost:{args.web_port}")
    print(" Credenciales de prueba:")
    print("   Operador Terminal: operador1 / terminal123")
    print("   Naviera 1:         maersk    / maersk123")
    print("   Naviera 2:         msc       / msc123")
    print("   Agente Aduanero:   agente1   / agente123")
    print("   Autoridad SAT:     sat1      / sat123")
    print("   Transportista 1:   trans_rapido (Canal de mensajeria)")
    print("   Transportista 2:   trans_global (Canal de mensajeria)")
    print("-" * 65)

    try:
        app.run(host="0.0.0.0", port=args.web_port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\nDeteniendo servicios de PORTUS Fase 2...")
    finally:
        bridge.stop()
        if broker_proc:
            broker_proc.terminate()


if __name__ == "__main__":
    main()
