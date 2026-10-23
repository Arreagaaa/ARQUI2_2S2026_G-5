"""Estacion ambiental para Raspberry Pi 3.

Cableado propuesto: DHT22 en GPIO4, salida digital YL-83 en GPIO17,
LDR en divisor resistivo hacia A0 del ADS1115 por I2C. Este proceso es independiente del
servidor web y publica exclusivamente lecturas reales por MQTT.
"""
import argparse
import json
import logging
import math
import signal
import time
from pathlib import Path
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("portus.estacion")


def light_percentage(voltage, dark_voltage, bright_voltage):
    """Luz relativa 0-100 para LDR hacia 3.3 V y resistencia hacia GND."""
    if not math.isfinite(voltage) or not 0 <= voltage <= 3.35:
        raise RuntimeError("Voltaje LDR fuera de rango; revisar divisor y ADS1115")
    if not 0 <= dark_voltage < bright_voltage <= 3.3:
        raise ValueError("Calibracion LDR invalida")
    return round(min(100.0, max(0.0, 100.0 * (voltage - dark_voltage) / (bright_voltage - dark_voltage))), 1)


class Sensors:
    def __init__(self, rain_pin=17, dht_pin=4, ads1115_address=0x48, ldr_channel=0):
        import board
        import adafruit_dht
        import RPi.GPIO as GPIO
        from adafruit_ads1x15 import ADS1115, AnalogIn, ads1x15
        self.gpio = GPIO
        self.gpio.setmode(GPIO.BCM)
        self.gpio.setup(rain_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.rain_pin = rain_pin
        self.dht = adafruit_dht.DHT22(getattr(board, f"D{dht_pin}"), use_pulseio=False)
        self.i2c = board.I2C()
        self.ads = ADS1115(self.i2c, gain=1, address=ads1115_address)
        self.ldr = AnalogIn(self.ads, (ads1x15.Pin.A0, ads1x15.Pin.A1,
                                       ads1x15.Pin.A2, ads1x15.Pin.A3)[ldr_channel])

    def read(self, dark_voltage, bright_voltage):
        light = light_percentage(self.ldr.voltage, dark_voltage, bright_voltage)
        temperature = self.dht.temperature
        humidity = self.dht.humidity
        if temperature is None or humidity is None:
            raise RuntimeError("DHT22 no entrego temperatura y humedad")
        return {"temperatura": round(float(temperature), 1),
                "humedad": round(float(humidity), 1),
                "lluvia": self.gpio.input(self.rain_pin) == self.gpio.LOW,
                "luz": light,
                "timestamp": datetime.now(timezone.utc).isoformat(), "origen": "raspberry-pi-3"}

    def close(self):
        self.dht.exit()
        self.i2c.deinit()
        self.gpio.cleanup(self.rain_pin)


def run(args):
    saved = Path(__file__).with_name("station_settings.json")
    if saved.exists():
        settings = json.loads(saved.read_text(encoding="utf-8"))
        args.read_seconds = int(settings.get("SegundosLecturaEstacion", args.read_seconds))
        args.heartbeat_seconds = int(settings.get("SegundosLatidoEstacion", args.heartbeat_seconds))
    sensors = Sensors(args.rain_pin, args.dht_pin, args.ads1115_address, args.ldr_channel)
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
    reading_healthy = False
    try:
        while running:
            stamp = time.monotonic()
            if stamp >= next_read:
                next_read = stamp + args.read_seconds
                try:
                    value = sensors.read(args.ldr_dark_voltage, args.ldr_bright_voltage)
                    reading_healthy = True
                    if online:
                        client.publish("portus/estacion/lectura", json.dumps(value), qos=1)
                    else:
                        log.warning("Lectura local sin enlace MQTT: %s", value)
                except (RuntimeError, OSError) as exc:
                    reading_healthy = False
                    log.warning("Lectura fallida; se reintentara: %s", exc)
            if stamp >= next_beat:
                next_beat = stamp + args.heartbeat_seconds
                if online:
                    client.publish("portus/estacion/estado", json.dumps({"estado": "OPERATIVA" if reading_healthy else "FALLO_LECTURA", "timestamp": datetime.now(timezone.utc).isoformat()}), qos=1)
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
    parser.add_argument("--ads1115-address", type=lambda x: int(x, 0), default=0x48)
    parser.add_argument("--ldr-channel", type=int, default=0)
    parser.add_argument("--ldr-dark-voltage", type=float, default=0.0)
    parser.add_argument("--ldr-bright-voltage", type=float, default=3.3)
    parser.add_argument("--read-seconds", type=int, default=5)
    parser.add_argument("--heartbeat-seconds", type=int, default=10)
    options = parser.parse_args()
    if (options.ads1115_address not in range(0x48, 0x4c) or options.ldr_channel not in range(4)
            or not 0 <= options.ldr_dark_voltage < options.ldr_bright_voltage <= 3.3
            or not 2 <= options.read_seconds <= 60 or not 5 <= options.heartbeat_seconds <= 60):
        parser.error("Parametros fuera de rango")
    logging.basicConfig(level=logging.INFO)
    run(options)
