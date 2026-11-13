# =============================================================
#  NanyBoard - PRUEBA DE SALIDAS (Avance 2, Sala de Experimentos)
#  Uso: copiar como code.py junto con caras.py.
#  Recorre cada salida y anuncia en la consola qué debería verse
#  u oírse, para llenar la tabla de pruebas S1-S7 del documento.
# =============================================================
import time
import board
import pwmio
from ideaboard import IdeaBoard
from ideasense import IdeaSense
import caras

ib = IdeaBoard()
idea = IdeaSense()
idea.matrix.brightness(0.3)

pin_buzzer = getattr(board, "IO26", None)
buzzer = (pwmio.PWMOut(pin_buzzer, frequency=440, duty_cycle=0,
                       variable_frequency=True) if pin_buzzer else None)


def paso(nombre):
    print("\n==>", nombre)
    time.sleep(0.3)


def tono(freq, dur):
    if not buzzer:
        print("   (sin buzzer conectado)")
        time.sleep(dur)
        return
    buzzer.frequency = freq
    buzzer.duty_cycle = 32768
    time.sleep(dur)
    buzzer.duty_cycle = 0


while True:
    paso("S1 Matriz: carita FELIZ")
    caras.mostrar(idea.matrix, caras.FELIZ)
    time.sleep(2)

    paso("S2 Matriz: carita TRISTE")
    caras.mostrar(idea.matrix, caras.TRISTE)
    time.sleep(2)

    paso("S3 Matriz: íconos PELIGRO, CLIMA y CAIDA")
    for icono in (caras.PELIGRO, caras.CLIMA, caras.CAIDA):
        caras.mostrar(idea.matrix, icono)
        time.sleep(1.5)

    paso("S4 LED RGB: verde, amarillo, rojo, azul")
    for nombre, color in (("verde", (0, 255, 0)), ("amarillo", (255, 160, 0)),
                          ("rojo", (255, 0, 0)), ("azul", (0, 0, 255))):
        print("   ", nombre)
        ib.pixel = color
        time.sleep(1)
    ib.pixel = (0, 0, 0)

    paso("S5 Buzzer: tono de alarma (2000 Hz intermitente)")
    for _ in range(4):
        tono(2000, 0.25)
        time.sleep(0.15)

    paso("S6 Buzzer: canción de cuna")
    for f, d in [(392, .4), (392, .4), (440, .8), (392, .8), (523, .8), (494, 1.2)]:
        tono(f, d)

    paso("S7 Presione el botón A en los próximos 5 s (silenciar)")
    limite = time.monotonic() + 5
    while time.monotonic() < limite:
        ev = idea.events.get()
        if ev and ev.pressed and ev.key_number == 0:
            print("   Botón A detectado: OK")
            break
    else:
        print("   No se detectó el botón A")

    idea.matrix.fill(0)
    idea.matrix.show()
    print("\nCiclo de pruebas completo. Se repite en 3 s...")
    time.sleep(3)
