# =============================================================
#  NanyBoard - PRUEBA DE ENTRADAS (Avance 2, Sala de Experimentos)
#  Uso: copiar este contenido como code.py en la IdeaBoard
#  (o ejecutarlo desde IdeaCode) y mirar la consola serial.
#  Imprime cada 0,5 s todas las lecturas para llenar la tabla
#  de pruebas E1-E12 del documento.
# =============================================================
import time
import math
import board
import analogio
from ideasense import IdeaSense

idea = IdeaSense()

# Sensores externos (mismos pines que code.py). Si un pin no existe,
# se muestra "--" en vez de detener el programa.
def abrir_analogico(nombre):
    pin = getattr(board, nombre, None)
    return analogio.AnalogIn(pin) if pin else None

gas = abrir_analogico("IO32")
mic = abrir_analogico("IO35")

print("Pines disponibles en esta placa:")
print([p for p in dir(board) if not p.startswith("_")])
print()

# Para calibrar: se guardan el mínimo y el máximo vistos de gas y ruido
gas_min, gas_max = 65535, 0
ruido_max = 0


def amplitud_mic(muestras=60):
    if not mic:
        return None
    lo, hi = 65535, 0
    for _ in range(muestras):
        v = mic.value
        lo, hi = min(lo, v), max(hi, v)
    return hi - lo


while True:
    ax, ay, az = idea.accel
    magnitud = math.sqrt(ax * ax + ay * ay + az * az)

    g = gas.value if gas else None
    r = amplitud_mic()
    if g is not None:
        gas_min, gas_max = min(gas_min, g), max(gas_max, g)
    if r is not None:
        ruido_max = max(ruido_max, r)

    print("Temp: %.1f C | Hum: %.1f %% | Luz: %d | Accel: %.2f m/s2 | Gas: %s (min %s / max %s) | Ruido: %s (max %s)" % (
        idea.temp, idea.humid, idea.light, magnitud,
        g if g is not None else "--", gas_min if gas else "--", gas_max if gas else "--",
        r if r is not None else "--", ruido_max if mic else "--"))

    evento = idea.events.get()
    if evento and evento.pressed:
        print(">>> Botón", "ABC"[evento.key_number], "presionado")

    time.sleep(0.5)
