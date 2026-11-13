# =============================================================
#  NanyBoard - Firmware de la IdeaBoard + IdeaSense Explorer
#  CircuitPython. Copiar a la raíz de la unidad CIRCUITPY.
#
#  Flujo: leer sensores -> evaluar alertas -> salidas locales
#         (matriz, LED RGB, buzzer) -> publicar por MQTT a la app.
# =============================================================
import time
import json
import os
import math

import board
import analogio
import pwmio
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT

from ideaboard import IdeaBoard
from ideasense import IdeaSense
import caras

# -------------------------------------------------------------
# 1. CONFIGURACIÓN
# -------------------------------------------------------------
DEVICE_ID = os.getenv("DEVICE_ID", "nanyboard-demo")
BROKER = os.getenv("MQTT_BROKER", "broker.hivemq.com")
PUERTO = int(os.getenv("MQTT_PORT", 1883))

# Tópicos MQTT (la app usa exactamente los mismos)
T_TELEMETRIA = "nanyboard/%s/telemetria" % DEVICE_ID   # cada 5 s
T_EVENTO = "nanyboard/%s/evento" % DEVICE_ID           # inicio/fin de alertas
T_COMANDO = "nanyboard/%s/comando" % DEVICE_ID         # app -> peluche
T_ESTADO = "nanyboard/%s/estado" % DEVICE_ID           # online/offline (retenido)

# Umbrales. OJO: el MQ-2 y el micrófono dan valores CRUDOS (0-65535),
# no ppm ni dB. Hay que calibrarlos midiendo en la habitación real.
UMBRAL_GAS = 30000        # crudo; calibrar con aire limpio vs. encendedor sin llama
UMBRAL_RUIDO = 12000      # amplitud pico a pico; calibrar con llanto grabado
SEG_RUIDO_SOSTENIDO = 2   # segundos de ruido continuo antes de alertar "llanto"
TEMP_MAX = 28.0
TEMP_MIN = 18.0
CAIDA_LIBRE = 3.0         # m/s^2: magnitud baja = el peluche va cayendo
GOLPE_FUERTE = 25.0       # m/s^2: magnitud alta = impacto o sacudida

PERIODO_LOOP = 0.2        # 200 ms, como en el pseudocódigo
PERIODO_TELEMETRIA = 5.0  # 5 s

# Pines de los sensores EXTERNOS. Verificar nombres con:
#   import board; print(dir(board))
# Con Wi-Fi activo, el ESP32 solo puede leer analógico en ADC1 (GPIO 32-39).
# Si un pin no existe o el sensor no está conectado, se deja en None y se omite.
PIN_GAS = getattr(board, "IO32", None)
PIN_MIC = getattr(board, "IO35", None)
PIN_BUZZER = getattr(board, "IO26", None)

# -------------------------------------------------------------
# 2. INICIALIZACIÓN DE HARDWARE
# -------------------------------------------------------------
ib = IdeaBoard()     # LED RGB y pines de la IdeaBoard
idea = IdeaSense()   # matriz 5x5, botones, temp/humedad, luz, acelerómetro
idea.matrix.brightness(0.3)

sensor_gas = analogio.AnalogIn(PIN_GAS) if PIN_GAS else None
sensor_mic = analogio.AnalogIn(PIN_MIC) if PIN_MIC else None
buzzer = (pwmio.PWMOut(PIN_BUZZER, frequency=440, duty_cycle=0,
                       variable_frequency=True) if PIN_BUZZER else None)

VERDE, AMARILLO, ROJO, AZUL = (0, 255, 0), (255, 160, 0), (255, 0, 0), (0, 0, 255)


# -------------------------------------------------------------
# 3. LECTURA DE SENSORES
# -------------------------------------------------------------
def leer_gas():
    return sensor_gas.value if sensor_gas else 0


def leer_ruido(muestras=60):
    """Amplitud pico a pico del micrófono: más alto = más ruido."""
    if not sensor_mic:
        return 0
    minimo, maximo = 65535, 0
    for _ in range(muestras):
        v = sensor_mic.value
        minimo = min(minimo, v)
        maximo = max(maximo, v)
    return maximo - minimo


def leer_movimiento():
    """Devuelve la magnitud de la aceleración en m/s^2 (~9.8 en reposo)."""
    ax, ay, az = idea.accel
    return math.sqrt(ax * ax + ay * ay + az * az)


def leer_todo():
    return {
        "gas": leer_gas(),
        "temp": round(idea.temp, 1),
        "humedad": round(idea.humid, 1),
        "luz": idea.light,
        "movimiento": round(leer_movimiento(), 2),
        "ruido": leer_ruido(),
    }


# -------------------------------------------------------------
# 4. BUZZER NO BLOQUEANTE (alarma y canción de cuna)
# -------------------------------------------------------------
# Notas (frecuencia Hz, duración s). 0 = silencio.
CANCION_CUNA = [(392, .4), (392, .4), (440, .8), (392, .8), (523, .8), (494, 1.2),
                (0, .3), (392, .4), (392, .4), (440, .8), (392, .8), (587, .8), (523, 1.2)]
ALARMA = [(2000, .25), (0, .15)]


class Sonido:
    def __init__(self):
        self.notas = []
        self.i = 0
        self.fin_nota = 0
        self.repetir = False

    def tocar(self, notas, repetir=False):
        self.notas, self.i, self.repetir, self.fin_nota = notas, 0, repetir, 0

    def detener(self):
        self.notas = []
        if buzzer:
            buzzer.duty_cycle = 0

    def actualizar(self):
        if not buzzer or not self.notas or time.monotonic() < self.fin_nota:
            return
        if self.i >= len(self.notas):
            if not self.repetir:
                self.detener()
                return
            self.i = 0
        freq, dur = self.notas[self.i]
        if freq:
            buzzer.frequency = freq
            buzzer.duty_cycle = 32768  # 50 %
        else:
            buzzer.duty_cycle = 0
        self.fin_nota = time.monotonic() + dur
        self.i += 1

    @property
    def sonando(self):
        return bool(self.notas)


sonido = Sonido()

# -------------------------------------------------------------
# 5. MQTT (Wi-Fi + comunicación con la app)
# -------------------------------------------------------------
mqtt = None


def al_recibir(cliente, topico, mensaje):
    """Comandos que manda la app: 'cuna', 'silenciar', 'detener_cuna', 'ping'."""
    print("Comando:", mensaje)
    if mensaje == "cuna":
        sonido.tocar(CANCION_CUNA)
    elif mensaje in ("silenciar", "detener_cuna"):
        silenciar()
    elif mensaje == "ping":
        publicar(T_TELEMETRIA, dict(leer_todo(), estado=estado_actual))


def conectar():
    global mqtt
    if not wifi.radio.connected:
        print("Conectando a Wi-Fi...")
        wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"),
                           os.getenv("CIRCUITPY_WIFI_PASSWORD"))
        print("IP:", wifi.radio.ipv4_address)
    pool = socketpool.SocketPool(wifi.radio)
    mqtt = MQTT.MQTT(broker=BROKER, port=PUERTO, socket_pool=pool,
                     client_id=DEVICE_ID, keep_alive=30, socket_timeout=0.05)
    # Si el peluche se apaga o pierde conexión, el broker avisa a la app.
    mqtt.will_set(T_ESTADO, "offline", retain=True)
    mqtt.on_message = al_recibir
    mqtt.connect()
    mqtt.subscribe(T_COMANDO)
    mqtt.publish(T_ESTADO, "online", retain=True)
    print("MQTT conectado a", BROKER)


def publicar(topico, datos):
    try:
        if mqtt:
            mqtt.publish(topico, json.dumps(datos))
    except Exception as e:
        print("Error publicando:", e)


# -------------------------------------------------------------
# 6. LÓGICA DE ALERTAS
# -------------------------------------------------------------
NORMAL = "NORMAL"
GAS = "ALERTA_CRITICA_GAS"
CAIDA = "ALERTA_CAIDA"
LLANTO = "ALERTA_LLANTO"
CLIMA = "ADVERTENCIA_CLIMA"
PANICO = "ALERTA_PANICO"

estado_actual = NORMAL
inicio_estado = time.monotonic()
silenciado = False
ruido_desde = None
panico_hasta = 0
caida_hasta = 0   # una caída se mantiene 5 s para no "parpadear" entre estados


def evaluar(d):
    """Devuelve el estado según prioridad: gas > pánico > caída > llanto > clima."""
    global ruido_desde, caida_hasta
    ahora = time.monotonic()

    if d["gas"] > UMBRAL_GAS:
        return GAS
    if ahora < panico_hasta:
        return PANICO
    if d["movimiento"] < CAIDA_LIBRE or d["movimiento"] > GOLPE_FUERTE:
        caida_hasta = ahora + 5
    if ahora < caida_hasta:
        return CAIDA

    # Llanto = ruido alto SOSTENIDO (evita alertas por un golpe de puerta)
    if d["ruido"] > UMBRAL_RUIDO:
        ruido_desde = ruido_desde or ahora
        if ahora - ruido_desde >= SEG_RUIDO_SOSTENIDO:
            return LLANTO
    else:
        ruido_desde = None

    if d["temp"] > TEMP_MAX or d["temp"] < TEMP_MIN:
        return CLIMA
    return NORMAL


def aplicar_salidas(estado):
    """Matriz, LED RGB y buzzer según el estado (solo al cambiar de estado)."""
    if estado == GAS:
        ib.pixel = ROJO
        caras.mostrar(idea.matrix, caras.PELIGRO)
        if not silenciado:
            sonido.tocar(ALARMA, repetir=True)
    elif estado == PANICO:
        ib.pixel = ROJO
        caras.mostrar(idea.matrix, caras.PELIGRO)
    elif estado == CAIDA:
        ib.pixel = AMARILLO
        caras.mostrar(idea.matrix, caras.CAIDA)
    elif estado == LLANTO:
        ib.pixel = AMARILLO
        caras.mostrar(idea.matrix, caras.TRISTE)
        sonido.tocar(CANCION_CUNA)  # intenta calmar al bebé
    elif estado == CLIMA:
        ib.pixel = AMARILLO
        caras.mostrar(idea.matrix, caras.CLIMA)
    else:
        ib.pixel = VERDE
        caras.mostrar(idea.matrix, caras.FELIZ)
        if sonido.notas is ALARMA:
            sonido.detener()


def silenciar():
    global silenciado
    silenciado = True
    sonido.detener()
    ib.pixel = AZUL


def cambiar_estado(nuevo, d):
    """Registra fin del evento anterior e inicio del nuevo (para el historial)."""
    global estado_actual, inicio_estado, silenciado
    ahora = time.monotonic()
    if estado_actual != NORMAL:
        publicar(T_EVENTO, {"tipo": estado_actual, "fase": "fin",
                            "duracion_s": round(ahora - inicio_estado)})
    if nuevo != NORMAL:
        publicar(T_EVENTO, {"tipo": nuevo, "fase": "inicio", "lecturas": d})
        # TODO: pedir foto a la ESP32-CAM (otra placa) cuando nuevo == GAS
    else:
        silenciado = False
    estado_actual, inicio_estado = nuevo, ahora
    aplicar_salidas(nuevo)
    print("Estado ->", nuevo)


def revisar_botones():
    global panico_hasta
    evento = idea.events.get()
    if evento and evento.pressed:
        if evento.key_number == 0:      # Botón A: silenciar alarma local
            silenciar()
        elif evento.key_number == 1:    # Botón B: pánico manual (10 s)
            panico_hasta = time.monotonic() + 10


# -------------------------------------------------------------
# 7. CICLO PRINCIPAL
# -------------------------------------------------------------
aplicar_salidas(NORMAL)
try:
    conectar()
except Exception as e:
    print("Sin conexión, sigo en modo local:", e)

ultima_telemetria = 0
ultimo_reintento = time.monotonic()

while True:
    inicio = time.monotonic()

    datos = leer_todo()
    revisar_botones()

    nuevo = evaluar(datos)
    if nuevo != estado_actual:
        cambiar_estado(nuevo, datos)

    if inicio - ultima_telemetria >= PERIODO_TELEMETRIA:
        publicar(T_TELEMETRIA, dict(datos, estado=estado_actual))
        ultima_telemetria = inicio

    # Mantener MQTT vivo y recibir comandos; reconectar si se cae
    try:
        if mqtt:
            mqtt.loop(timeout=0.05)
    except Exception as e:
        print("MQTT caído:", e)
        mqtt = None
    if mqtt is None and inicio - ultimo_reintento > 15:
        ultimo_reintento = inicio
        try:
            conectar()
        except Exception as e:
            print("Reintento fallido:", e)

    sonido.actualizar()

    espera = PERIODO_LOOP - (time.monotonic() - inicio)
    if espera > 0:
        time.sleep(espera)
