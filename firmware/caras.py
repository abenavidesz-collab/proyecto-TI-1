# Íconos 5x5 para la matriz LED de la IdeaSense.
# Cada string es una fila (de arriba hacia abajo); "1" = LED encendido.

FELIZ = (
    "01010",
    "01010",
    "00000",
    "10001",
    "01110",
)

TRISTE = (
    "01010",
    "01010",
    "00000",
    "01110",
    "10001",
)

PELIGRO = (  # signo de exclamación
    "00100",
    "00100",
    "00100",
    "00000",
    "00100",
)

CLIMA = (  # termómetro
    "00100",
    "00100",
    "00100",
    "01110",
    "01110",
)

CAIDA = (  # flecha hacia abajo
    "00100",
    "00100",
    "10101",
    "01110",
    "00100",
)


def mostrar(matriz, icono):
    """Dibuja un ícono en la matriz HT16K33 de la IdeaSense."""
    matriz.fill(0)
    for y, fila in enumerate(icono):
        for x, celda in enumerate(fila):
            if celda == "1":
                matriz[x, y] = 1
    matriz.show()
