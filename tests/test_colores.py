"""Los colores de la oficina se distinguen entre sí, también con daltonismo.

Desde que el escritorio rotula el encargo y no el tipo, el color de la figura es lo único que dice qué clase de
agente es: tiene que leerse sin ayuda. La medida es la distancia en OKLab ×100, con la simulación de daltonismo de
Machado, Oliveira y Fernandes (2009) a severidad completa: los mismos umbrales que el validador del skill `dataviz`
(15 a simple vista, 8 con protanopía o deuteranopía).
"""
import itertools
import math

from conftest import sl

TIPOS = ["amigo explore", "amigo general", "amigo plan", "amigo propio"]
VECINOS = ["mascota", "amigo desconocido", "critico", "lampara encendida"]  # comparten la escena con los tipos
LETRAS = ["modelo opus", "modelo sonnet", "modelo haiku", "modelo fable"]  # al lado de la figura, pero se nombran solas

A_SIMPLE_VISTA, CON_DALTONISMO, CONTRA_LETRAS = 15.0, 8.0, 10.0

MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
}


def _lineal(hexa):
    c = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def _oklab(rgb):
    r, g, b = (min(1.0, max(0.0, x)) for x in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def distancia(x, y, vision=None):
    def ver(hexa):
        rgb = _lineal(hexa)
        if vision:
            rgb = [sum(f * c for f, c in zip(fila, rgb)) for fila in MACHADO[vision]]
        return _oklab(rgb)
    return 100 * math.dist(ver(x), ver(y))


def test_la_medida_reproduce_al_validador():
    """Control: los dos números que el validador de `dataviz` dio para la paleta vieja."""
    assert round(distancia("#d55181", "#199e70", "deutan"), 1) == 1.6
    assert round(distancia("#D77757", "#c98500"), 1) == 8.1


def test_los_tipos_se_distinguen_entre_si_tambien_con_daltonismo():
    p = sl.PALETA
    for a, b in itertools.combinations(TIPOS, 2):
        assert distancia(p[a], p[b]) >= A_SIMPLE_VISTA, (a, b)
        peor = min(distancia(p[a], p[b], v) for v in MACHADO)
        assert peor >= CON_DALTONISMO, (a, b, round(peor, 1))


def test_ningun_tipo_se_confunde_con_clawd_ni_con_lo_que_lo_rodea():
    """El Plan ámbar a 8 de Clawd se leía como un Clawd chiquito."""
    p = sl.PALETA
    for a in TIPOS:
        for b in VECINOS:
            assert distancia(p[a], p[b]) >= A_SIMPLE_VISTA, (a, b, round(distancia(p[a], p[b]), 1))


def test_ningun_tipo_se_confunde_con_la_letra_de_un_modelo():
    """Rosa de los propios junto al rosa de Haiku: la letra se nombra sola, así que alcanza con menos distancia."""
    p = sl.PALETA
    for a in TIPOS:
        for b in LETRAS:
            assert distancia(p[a], p[b]) >= CONTRA_LETRAS, (a, b, round(distancia(p[a], p[b]), 1))
