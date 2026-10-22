"""Estacion ambiental para Raspberry Pi 3.

Cableado propuesto: DHT22 en GPIO4, salida digital YL-83 en GPIO17,
BH1750 en I2C bus 1 direccion 0x23. Este proceso es independiente del
servidor web y publica exclusivamente lecturas reales por MQTT.
"""
import argparse
import json
import logging
import signal
import time
from pathlib import Path
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("portus.estacion")


class Sensors:
    def __init__(self, rain_pin=17, dht_pin=4, bh1750_address=0x23):
        import board
        import adafruit_dht
        import RPi.GPIO as GPIO
        import smbus2
        self.gpio = GPIO
        self.gpio.setmode(GPIO.BCM)
        self.gpio.setup(rain_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.rain_pin = rain_pin
        self.dht = adafruit_dht.DHT22(getattr(board, f"D{dht_pin}"), use_pulseio=False)
        self.bus = smbus2.SMBus(1)
        self.address = bh1750_address

    def read(self, max_lux):
        # El BH1750 devuelve lux; se calibra el 100% con --max-lux.
        self.bus.write_byte(self.address, 0x10)
        time.sleep(0.18)
        data = self.bus.read_i2c_block_data(self.address, 0x10, 2)
        lux = ((data[0] << 8) | data[1]) / 1.2
        temperature = self.dht.temperature
        humidity = self.dht.humidity
        if temperature is None or humidity is None:
            raise RuntimeError("DHT22 no entrego temperatura y humedad")
        return {"temperatura": round(float(temperature), 1),
                "humedad": round(float(humidity), 1),
                "lluvia": self.gpio.input(self.rain_pin) == self.gpio.LOW,
                "luz": round(min(100.0, max(0.0, 100.0 * lux / max_lux)), 1),
                "timestamp": datetime.now(timezone.utc).isoformat(), "origen": "raspberry-pi-3"}

    def close(self):
        self.dht.exit()
        self.bus.close()
        self.gpio.cleanup(self.rain_pin)


def run(args):
    saved = Path(__file__).with_name("station_settings.json")
    if saved.exists():
        settings = json.loads(saved.read_text(encoding="utf-8"))
        args.read_seconds = int(settings.get("SegundosLecturaEstacion", args.read_seconds))
        args.heartbeat_seconds = int(settings.get("SegundosLatidoEstacion", args.heartbeat_seconds))
    sensors = Sensors(args.rain_pin, args.dht_pin, args.bh1750_address)
    client = mqtt.Client(client_id="portus_estacion_pi3")
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    online = False

    def connected(_client, _userdata, _flags, rc):
        nonlocal online
        online = rc == 0
        log.info("MQTT conectado=%s", online)
        if online:
            client.subscribe("portus/estacion/config")

    def disconnected(_client, _userdata, _rc):
        nonlocal online
        online = False

    client.on_connect = connected
    client.on_disconnect = disconnected
    def update_config(_client, _userdata, msg):
        try:
            values = json.loads(msg.payload.decode("utf-8"))
            reading = int(values.get("SegundosLecturaEstacion", args.read_seconds))
            heartbeat = int(values.get("SegundosLatidoEstacion", args.heartbeat_seconds))
            if not 2 <= reading <= 60 or not 5 <= heartbeat <= 60:
                raise ValueError("Periodo fuera de rango")
            args.read_seconds, args.heartbeat_seconds = reading, heartbeat
            temporary = saved.with_suffix(".tmp")
            temporary.write_text(json.dumps({"SegundosLecturaEstacion": reading,
                                             "SegundosLatidoEstacion": heartbeat}), encoding="utf-8")
            temporary.replace(saved)
        except (ValueError, OSError, TypeError) as exc:
            log.warning("Configuracion rechazada: %s", exc)
    client.on_message = update_config
    client.connect_async(args.host, args.port, keepalive=30)
    client.loop_start()
    running = True

    def stop(_sig, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    next_read = next_beat = 0.0
    try:
        while running:
            stamp = time.monotonic()
            if stamp >= next_read:
                next_read = stamp + args.read_seconds
                try:
                    value = sensors.read(args.max_lux)
                    if online:
                        client.publish("portus/estacion/lectura", json.dumps(value), qos=1)
                    else:
                        log.warning("Lectura local sin enlace MQTT: %s", value)
                except (RuntimeError, OSError) as exc:
                    log.warning("Lectura fallida; se reintentara: %s", exc)
            if stamp >= next_beat:
                next_beat = stamp + args.heartbeat_seconds
                if online:
                    client.publish("portus/estacion/estado", json.dumps({"estado": "OPERATIVA", "timestamp": datetime.now(timezone.utc).isoformat()}), qos=1)
            time.sleep(0.1)
    finally:
        client.loop_stop()
        client.disconnect()
        sensors.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lecturas reales de clima y luz en Raspberry Pi 3")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--rain-pin", type=int, default=17)
    parser.add_argument("--dht-pin", type=int, default=4)
    parser.add_argument("--bh1750-address", type=lambda x: int(x, 0), default=0x23)
    parser.add_argument("--max-lux", type=float, default=1000.0)
    parser.add_argument("--read-seconds", type=int, default=5)
    parser.add_argument("--heartbeat-seconds", type=int, default=10)
    options = parser.parse_args()
    if options.max_lux <= 0 or not 2 <= options.read_seconds <= 60 or not 5 <= options.heartbeat_seconds <= 60:
        parser.error("Parametros fuera de rango")
    logging.basicConfig(level=logging.INFO)
    run(options)
