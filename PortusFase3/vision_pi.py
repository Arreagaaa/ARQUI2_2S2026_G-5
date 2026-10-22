"""Vision real en Raspberry Pi 3: OCR por evento y conteo YOLO periodico.

Requiere camara y modelos instalados. No fabrica lecturas al faltar hardware.
Las ROI son fracciones [x,y,w,h] del fotograma y se calibran en config.json.
"""
import argparse
import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import paho.mqtt.client as mqtt
import pytesseract

log = logging.getLogger("portus.vision")


def crop(frame, rect):
    height, width = frame.shape[:2]
    x, y, w, h = rect
    left, top = int(x * width), int(y * height)
    right, bottom = int((x + w) * width), int((y + h) * height)
    if left < 0 or top < 0 or right > width or bottom > height or right <= left or bottom <= top:
        raise ValueError("ROI fuera del fotograma")
    return frame[top:bottom, left:right]


class Vision:
    def __init__(self, config, client):
        self.cfg = config
        self.client = client
        self.source = config.get("camera_device", config.get("camera_index", 0))
        self.camera = None
        from ultralytics import YOLO
        self.detector = YOLO(config["coco_model"])
        self.jobs = queue.Queue(maxsize=10)
        self.lock = threading.Lock()
        self.online = False
        self.last_count = 0.0
        self.last_heartbeat = 0.0
        config["photo_dir"] = str(Path(config["photo_dir"]).resolve())
        Path(config["photo_dir"]).mkdir(parents=True, exist_ok=True)

    def open_camera(self):
        if self.camera is not None:
            self.camera.release()
        backend = cv2.CAP_V4L2 if isinstance(self.source, (int, str)) and (
            isinstance(self.source, int) or self.source.startswith("/dev/video")) else cv2.CAP_ANY
        self.camera = cv2.VideoCapture(self.source, backend)
        if not self.camera.isOpened():
            self.camera.release()
            self.camera = None
            raise RuntimeError(f"Camara USB no disponible: {self.source}")
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.cfg.get("camera_width", 640)))
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.cfg.get("camera_height", 480)))
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def publish(self, topic, data):
        self.client.publish(topic, json.dumps(data), qos=1)

    def frame(self):
        if self.camera is None or not self.camera.isOpened():
            self.open_camera()
        ok, image = self.camera.read()
        if not ok or image is None:
            self.camera.release()
            self.camera = None
            raise RuntimeError("Camara no entrega fotogramas")
        return image

    def plate(self, uid):
        # La iluminacion se ordena siempre, incluso en modo apagado forzado.
        self.publish("portus/cmd/solicitud", {"comando": "CapturaInicio", "parametros": {}})
        time.sleep(1)
        try:
            results = []
            for attempt in range(self.cfg["attempts"]):
                image = self.frame()
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                path = str(Path(self.cfg["photo_dir"]) / f"ingreso_{stamp}_{attempt + 1}.jpg")
                if not cv2.imwrite(path, image):
                    raise RuntimeError("No se pudo guardar fotografia")
                region = crop(image, self.cfg["plate_roi"])
                gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                # Tesseract es un motor OCR preentrenado; ROI fija autorizada
                # cuando el detector de placas no funciona en escala de maqueta.
                data = pytesseract.image_to_data(gray, config="--psm 7 -c tessedit_char_whitelist=C0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                                                 output_type=pytesseract.Output.DICT)
                words = [(text.strip(), conf) for text, conf in zip(data["text"], data["conf"])
                         if text.strip() and float(conf) >= 0]
                plate = "".join(text for text, _ in words).replace(" ", "").upper()
                confidence = sum(float(conf) for _, conf in words) / len(words) if words else 0.0
                result = {"uid": uid, "placa": plate, "confianza": round(confidence, 1),
                          "foto": path, "intento": attempt + 1, "timestamp": datetime.now(timezone.utc).isoformat()}
                results.append(result)
            self.publish("portus/vision/placa", {"uid": uid, "intentos": results,
                                                 "timestamp": datetime.now(timezone.utc).isoformat()})
        finally:
            self.publish("portus/cmd/solicitud", {"comando": "CapturaFin", "parametros": {}})

    def count(self):
        image = crop(self.frame(), self.cfg["queue_roi"])
        result = self.detector.predict(image, verbose=False, device="cpu", imgsz=320)[0]
        count = sum(1 for box in result.boxes if int(box.cls.item()) in (2, 5, 7))
        self.publish("portus/vision/cola", {"cantidad": count, "timestamp": datetime.now(timezone.utc).isoformat()})

    def loop(self):
        while True:
            if time.monotonic() - self.last_heartbeat >= 5:
                self.publish("portus/vision/estado", {"operativa": self.online,
                                                       "timestamp": datetime.now(timezone.utc).isoformat()})
                self.last_heartbeat = time.monotonic()
            uid = None
            try:
                with self.lock:
                    if not self.online:
                        self.open_camera()
                        self.frame()
                        self.online = True
                        self.publish("portus/vision/estado", {"operativa": True})
                    try:
                        uid = self.jobs.get_nowait()
                    except queue.Empty:
                        pass
                    if uid is not None:
                        self.plate(uid)
                    elif time.monotonic() - self.last_count >= self.cfg["count_seconds"]:
                        self.count()
                        self.last_count = time.monotonic()
                if not self.online:
                    self.online = True
                    self.publish("portus/vision/estado", {"operativa": True})
            except Exception as exc:
                log.warning("Vision fuera de servicio: %s", exc)
                if uid is not None:
                    try:
                        self.jobs.put_nowait(uid)
                    except queue.Full:
                        log.warning("Cola OCR llena tras fallo de camara")
                if self.online:
                    self.online = False
                    self.publish("portus/vision/estado", {"operativa": False, "error": str(exc)})
                time.sleep(2)
                if self.camera is not None:
                    self.camera.release()
                    self.camera = None
            time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).with_name("vision_config.json")))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    client = mqtt.Client(client_id="portus_vision_pi3")
    vision = Vision(config, client)

    def on_connect(c, _u, _f, rc):
        if rc == 0:
            c.subscribe("portus/evt/garita")
            c.subscribe("portus/vision/config")
            vision.publish("portus/vision/estado", {"operativa": vision.online})

    def on_message(_c, _u, msg):
        data = json.loads(msg.payload.decode("utf-8"))
        if msg.topic == "portus/vision/config":
            values = (("ConfianzaMinimaOCR", "confidence", 30, 95),
                      ("IntentosOCR", "attempts", 1, 5),
                      ("SegundosConteoCola", "count_seconds", 2, 30))
            for source, target, minimum, maximum in values:
                value = data.get(source)
                if isinstance(value, (int, float)) and minimum <= value <= maximum:
                    vision.cfg[target] = value
            return
        if data.get("tipo") == "GaritaRFID":
            uid = data.get("datos", {}).get("uid")
            if uid:
                try:
                    vision.jobs.put_nowait(uid)
                except queue.Full:
                    log.warning("Cola OCR llena")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.get("mqtt_host", "localhost"), int(config.get("mqtt_port", 1883)))
    client.loop_start()
    try:
        vision.loop()
    finally:
        client.loop_stop()
        if vision.camera is not None:
            vision.camera.release()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
