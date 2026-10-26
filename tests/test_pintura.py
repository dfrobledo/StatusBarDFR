import subprocess
import sys

from conftest import RAIZ, sl, verificar_tokens


def test_texto_asigna_un_token_por_celda():
    fila = sl.texto("ab", "mascota")
    assert fila == [("a", "mascota"), ("b", "mascota")]


def test_poner_no_crece_la_fila():
    fila = sl.fila_vacia(4)
    sl.poner(fila, 2, "xyz", "texto principal")
    assert [c for c, _ in fila] == [" ", " ", "x", "y"]


def test_pintar_sin_ansi_es_el_texto_plano():
    fila = sl.texto("ab", "mascota") + sl.texto(" c", "piso")
    assert sl.pintar_fila(fila, ansi=False) == "ab c"


def test_pintar_con_ansi_emite_truecolor_y_reset():
    fila = sl.texto("ab", "mascota") + sl.texto("c", "piso")
    s = sl.pintar_fila(fila)
    assert s.startswith("\x1b[0m\x1b[38;2;215;119;87mab")
    assert "\x1b[38;2;58;58;58mc" in s
    assert s.endswith("\x1b[0m")
    assert s.count("\x1b[38;2") == 2, "un escape por cambio de token, no por celda"


def test_espacios_no_llevan_color():
    s = sl.pintar_fila(sl.texto("a b", "mascota"))
    assert s == "\x1b[0m\x1b[38;2;215;119;87ma b\x1b[0m"


def test_la_linea_pintada_empieza_y_termina_con_un_escape():
    """Los dos resets son lo que hace que el `trim()` por línea de Claude Code no pueda comerse ninguna
    columna: ESC no es whitespace para JS. Quitar cualquiera de los dos reabre el defecto."""
    s = sl.pintar_fila(sl.fila_vacia(5))
    assert s.startswith("\x1b[") and s.endswith("m")
    assert s.strip(" ") == s, "la línea pintada no puede empezar ni terminar en un espacio desnudo"


def test_unir_deja_un_hueco_fijo():
    escena = [sl.texto("E", "mascota")] * 3
    tablero = [sl.texto("T", "texto principal")] * 3
    g = sl.unir(escena, tablero, hueco=2)
    assert sl.a_texto(g) == ["E  T"] * 3
    verificar_tokens(g)


def test_ningun_hexadecimal_fuera_de_la_paleta():
    for tok, hexa in sl.PALETA.items():
        assert hexa.startswith("#") and len(hexa) == 7, tok
    assert set(sl.PALETA) == {
        "mascota", "amigo explore", "amigo general", "amigo plan", "amigo propio", "amigo desconocido",
        "lampara encendida", "lampara apagada", "frio", "texto principal", "texto secundario",
        "apagado", "piso", "bien", "aviso", "critico", "ritmo bajo",
        "modelo opus", "modelo sonnet", "modelo haiku", "modelo fable",
        *(f"esfuerzo {f}{n}" for f in ("opus ", "sonnet ", "haiku ", "fable ", "")
          for n in ("low", "medium", "high", "xhigh", "max"))}


def test_stdin_vacio_produce_la_linea_de_respaldo():
    r = subprocess.run([sys.executable, str(RAIZ / "statusline.py")], input=b"", capture_output=True, timeout=10)
    assert r.returncode == 0
    assert r.stderr == b""
    assert r.stdout.decode("utf-8").strip() != ""
    assert "Claude" in r.stdout.decode("utf-8")


def test_ancho_de_grilla_es_la_fila_mas_larga():
    g = sl.unir([sl.texto("abc", "piso")] * 3, [sl.texto("de", "piso"), sl.texto("d", "piso"), sl.texto("", "piso")])
    assert sl.ancho_de_grilla(g) == 3 + 2 + 2
    assert sl.ancho_de_grilla([[], [], []]) == 0
