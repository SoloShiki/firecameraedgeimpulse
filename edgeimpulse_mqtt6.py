#!/usr/bin/env python3
# edgeimpulse_mqtt.py
# Raspberry Pi 4: publica detección de fuego filtrada + heartbeat cada 1s
# Después de 5 detecciones consecutivas, ignora nuevas detecciones por 60 segundos

import subprocess
import threading
import json
import time
import paho.mqtt.client as mqtt
import sys
import os

# ---------- CONFIGURACIÓN ----------
BROKER_IP = "192.168.1.86"
BROKER_PORT = 1883
MQTT_TOPIC = "alerta/fuego"
RPI_ID = "RPI_1"
runner_path = '/usr/bin/edge-impulse-linux-runner'
model_path = 'model.eim'
DESIRED_LABEL = "fire"
THRESHOLD = 0.90
HEARTBEAT_INTERVAL = 1     # manda OK cada 1 segundo
REQUIRED_CONSECUTIVE = 5
IGNORE_DURATION = 60        # segundos que se ignoran nuevas detecciones
# -----------------------------------

# Verificar existencia del modelo
if not os.path.exists(model_path):
    print(f"[emisor] ERROR: El archivo de modelo '{model_path}' no existe.")
    sys.exit(1)

# Configurar MQTT
client = mqtt.Client()
try:
    client.connect(BROKER_IP, BROKER_PORT, 60)
except Exception as e:
    print("[emisor] ERROR: No pude conectar al broker MQTT:", e)
    sys.exit(1)

client.loop_start()

# Variables de estado
consecutive_fire = 0
fire_active = False
ignore_further_detections = False  # ignora detecciones por un tiempo

def reset_ignore_flag():
    global ignore_further_detections, fire_active, consecutive_fire
    ignore_further_detections = False
    fire_active = False
    consecutive_fire = 0
    print("[emisor] 🔵 Ignorar detecciones finalizado. Listo para detectar de nuevo.")

def publish_fire_with_coords(box):
    x = box.get('x', 0)
    y = box.get('y', 0)
    width = box.get('width', 0)
    height = box.get('height', 0)
    center_x = x + width / 2
    center_y = y + height / 2

    payload = {
        "rpi_id": RPI_ID,
        "label": box.get('label', 'fire'),
        "confidence": box.get('value', 0.0),
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "center_x": center_x,
        "center_y": center_y
    }

    try:
        client.publish(MQTT_TOPIC, json.dumps(payload))
        print(f"[emisor] 🚨 FIRE enviado: {payload}")
    except Exception as e:
        print("[emisor] Error publicando MQTT:", e)

def publish_heartbeat():
    while True:
        if not fire_active:
            payload = {
                "rpi_id": RPI_ID,
                "label": "none",
                "status": "OK"
            }
            try:
                client.publish(MQTT_TOPIC, json.dumps(payload))
                print(f"[emisor] Mensaje HEARTBEAT enviado: {payload}")
            except Exception as e:
                print("[emisor] Error publicando heartbeat:", e)
        time.sleep(HEARTBEAT_INTERVAL)

# Lanza el runner de Edge Impulse con modelo específico
try:
    proc = subprocess.Popen(
        [runner_path, '--model-file', model_path, '--clean', '--camera', '/dev/video0'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    print("[emisor] Runner lanzado con modelo model.eim.")
except Exception as e:
    print("[emisor] No se pudo lanzar edge-impulse-linux-runner:", e)
    sys.exit(1)

def read_loop():
    global consecutive_fire, fire_active, ignore_further_detections
    for line in proc.stdout:
        line = line.strip()
        if not line or ignore_further_detections:
            continue
        print("[runner]", line)

        if 'boundingBoxes' in line:
            try:
                json_start = line.find('[')
                boxes = json.loads(line[json_start:])

                fire_in_this_frame = False
                for box in boxes:
                    label = box.get('label', '')
                    value = box.get('value', 0.0)
                    if label == DESIRED_LABEL and value >= THRESHOLD:
                        fire_in_this_frame = True
                        last_box = box
                        print(f"[emisor] Detectado {label} con confianza {value:.2f}")

                if fire_in_this_frame:
                    consecutive_fire += 1
                    print(f"[emisor] Fuegos consecutivos: {consecutive_fire}")

                    if consecutive_fire >= REQUIRED_CONSECUTIVE and not fire_active:
                        fire_active = True
                        ignore_further_detections = True
                        publish_fire_with_coords(last_box)
                        print(f"[emisor] 🚀 Fuego confirmado. Ignorando detecciones por {IGNORE_DURATION} segundos.")

                        # Lanzar temporizador para reiniciar después de IGNORE_DURATION segundos
                        t = threading.Timer(IGNORE_DURATION, reset_ignore_flag)
                        t.start()

            except Exception as e:
                print("[emisor] Error analizando boundingBoxes:", e)

# Iniciar hilos
reader = threading.Thread(target=read_loop, daemon=True)
reader.start()

heartbeat_thread = threading.Thread(target=publish_heartbeat, daemon=True)
heartbeat_thread.start()

# Monitor básico
try:
    while True:
        time.sleep(1)
        if proc.poll() is not None:
            print("[emisor] El runner se cerró.")
            break
except KeyboardInterrupt:
    print("[emisor] Interrumpido por usuario.")
finally:
    try:
        proc.kill()
    except:
        pass
    client.loop_stop()
    client.disconnect()
