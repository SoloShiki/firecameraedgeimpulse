#!/usr/bin/env python3
# relay_mqtt_fire_only.py
# Escucha mensajes en un tópico, filtra por label "fire" y los reenvía a otro tópico

import paho.mqtt.client as mqtt
import json

# --- Configuración ---
MQTT_BROKER = "192.168.1.86"       # IP del broker MQTT
MQTT_PORT = 1883
SOURCE_TOPIC = "alerta/fuego"      # Tópico de entrada
DEST_TOPIC = "cigar/detect"        # Tópico de salida

# --- Lógica de conexión MQTT ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"🟢 Conectado al broker. Escuchando en: '{SOURCE_TOPIC}'")
        client.subscribe(SOURCE_TOPIC)
    else:
        print(f"❌ Falló la conexión. Código: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)

        if data.get("label") != "fire":
            return  # Ignorar mensajes que no sean de fuego

        print(f"[relay] 🔥 FUEGO detectado. Reenviando mensaje: {payload}")
        client.publish(DEST_TOPIC, json.dumps(data))
        print(f"[relay] Mensaje reenviado a '{DEST_TOPIC}'")

    except Exception as e:
        print(f"[relay] 🚨 Error procesando mensaje MQTT: {e}")

# --- Programa principal ---
if __name__ == "__main__":
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print("[relay] 📡 Iniciando relay MQTT...")
        client.loop_forever()
    except KeyboardInterrupt:
        print("[relay] ⛔ Relay detenido por usuario.")
        client.disconnect()
    except Exception as e:
        print(f"[relay] 🚨 Error al conectar o ejecutar: {e}")
