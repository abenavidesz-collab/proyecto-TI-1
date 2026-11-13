"""
Simulador de NanyBoard en la computadora.
Publica los mismos mensajes MQTT que el peluche para poder construir y
probar la app Flutter sin tener la IdeaBoard conectada.

Uso:
    pip install paho-mqtt
    python simulador.py            # usa DEVICE_ID = nanyboard-grupo1
Teclas (Enter después de cada una):
    g = alerta de gas   l = llanto   c = caída   t = calor   n = volver a normal
"""
import json
import random
import sys
import threading
import time

import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"
DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "nanyboard-grupo1"
BASE = f"nanyboard/{DEVICE_ID}"

estado = "NORMAL"
inicio_estado = time.time()
TECLAS = {"g": "ALERTA_CRITICA_GAS", "l": "ALERTA_LLANTO", "c": "ALERTA_CAIDA",
          "t": "ADVERTENCIA_CLIMA", "n": "NORMAL"}


def lecturas():
    return {
        "gas": 45000 if estado == "ALERTA_CRITICA_GAS" else random.randint(8000, 12000),
        "temp": 30.5 if estado == "ADVERTENCIA_CLIMA" else round(random.uniform(22, 25), 1),
        "humedad": round(random.uniform(55, 65), 1),
        "luz": random.randint(10, 400),
        "movimiento": 30.0 if estado == "ALERTA_CAIDA" else round(random.uniform(9.6, 10.0), 2),
        "ruido": 20000 if estado == "ALERTA_LLANTO" else random.randint(500, 3000),
        "estado": estado,
    }


def al_conectar(cliente, *_):
    cliente.subscribe(f"{BASE}/comando")
    cliente.publish(f"{BASE}/estado", "online", retain=True)
    print("Conectado. Tópico base:", BASE)


def al_mensaje(cliente, _u, msg):
    print(">> Comando recibido desde la app:", msg.payload.decode())


def cambiar(nuevo, cliente):
    global estado, inicio_estado
    if nuevo == estado:
        return
    if estado != "NORMAL":
        cliente.publish(f"{BASE}/evento", json.dumps(
            {"tipo": estado, "fase": "fin", "duracion_s": round(time.time() - inicio_estado)}))
    estado, inicio_estado = nuevo, time.time()
    if nuevo != "NORMAL":
        cliente.publish(f"{BASE}/evento", json.dumps(
            {"tipo": nuevo, "fase": "inicio", "lecturas": lecturas()}))
    print("Estado ->", estado)


def teclado(cliente):
    for linea in sys.stdin:
        tecla = linea.strip().lower()
        if tecla in TECLAS:
            cambiar(TECLAS[tecla], cliente)


cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{DEVICE_ID}-sim")
cliente.will_set(f"{BASE}/estado", "offline", retain=True)
cliente.on_connect = al_conectar
cliente.on_message = al_mensaje
cliente.connect(BROKER, 1883, 30)
cliente.loop_start()
threading.Thread(target=teclado, args=(cliente,), daemon=True).start()

while True:
    cliente.publish(f"{BASE}/telemetria", json.dumps(lecturas()))
    time.sleep(5)
