import json
import os
import re
import subprocess
import sys

from conftest import (RAIZ, T0, anchos_de_filas, escribir_jsonl, fijar_creacion, golden, sl, tool_use,
                      verificar_tokens)
from test_entrada import COMPLETO


def test_niveles_por_ancho():
    anchos = (202, 165, 164, 140, 139, 120, 119, 100, 99, 85, 84, 0)
    assert [sl.elegir_nivel(a) for a in anchos] == [-1, -1, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_peldano_menos_uno_mide_cien_columnas_de_escena():
    assert sl.ancho_escena(-1) == 22 + 6 * 13 == 100
    assert sl.repartir_sobrante(165, -1, 63) == (13, 2)      # justo en el peldaño: no sobra nada
    assert sl.repartir_sobrante(202, -1, 63) == (19, 3)      # 37 de sobrante: 6 a cada escritorio, 1 al hueco


# El tablero del nivel 0 mide 63 columnas con el contenido de referencia; los casos de abajo lo
# usan como ancho de tablero fijo para que la aritmética del reparto se lea sin depender del contenido.
def test_repartir_sobrante_sin_nada_que_repartir():
    assert sl.repartir_sobrante(139, 0, 63) == (13, 2)      # 74 + 2 + 63 = 139 justo
    assert sl.repartir_sobrante(100, 0, 63) == (13, 2)      # no entra: el hueco nunca baja de 2


def test_repartir_sobrante_ensancha_escritorios_y_el_resto_va_al_hueco():
    # 150 - 139 = 11 de sobrante entre 4 escritorios: 2 a cada uno (escena 82) y los 3 que sobran al hueco.
    assert sl.repartir_sobrante(150, 0, 63) == (15, 5)


def test_repartir_sobrante_respeta_el_tope_de_20():
    # 240/nivel 0 es un par sintético: desde que existe el peldaño -1, elegir_nivel(240) ya no elige el
    # nivel 0. Se conserva porque sigue siendo aritmética pura y válida, pero no es un ancho que la
    # producción vaya a pedirle a repartir_sobrante con ese nivel.
    assert sl.repartir_sobrante(240, 0, 63) == (20, 75)     # 22 + 4*20 = 102; 240 - 102 - 63 = 75
    # El tope, en los dos peldaños donde realmente se dispara en producción:
    # nivel -1 a 240 (el que elegir_nivel(240) elige de verdad): escena 22+6*13=100, sobrante
    # 240-(100+2+63)=75, 75//6=12 topa en 20-13=7 -> escritorio 20, hueco 240-(22+6*20)-63=35.
    assert sl.repartir_sobrante(240, -1, 63) == (20, 35)
    # nivel 3 desde una base de 10: escena 22+2*10=42, sobrante 99-(42+2+32)=23, 23//2=11 topa en
    # 20-10=10 -> escritorio 20, hueco 99-(22+2*20)-32=5.
    assert sl.repartir_sobrante(99, 3, 32) == (20, 5)


def test_repartir_sobrante_sin_escritorios_manda_todo_al_hueco():
    assert sl.repartir_sobrante(100, 4, 23) == (0, 55)      # nivel 4: sólo Clawd (22) y el tablero


def test_repartir_sobrante_no_deja_columnas_muertas():
    for ancho in range(139, 241):
        ancho_escritorio, hueco = sl.repartir_sobrante(ancho, 0, 63)
        assert sl.ancho_escena(0) - 4 * 13 + 4 * ancho_escritorio + hueco + 63 == ancho


def test_nivel_sube_si_la_grilla_no_entra_en_el_ancho(tmp_path):
    # feat/statusline suma 9 columnas y +1312 -118 otras 3: a 140-150 columnas la línea 1 se pasa del
    # ancho medido con "master" (139). componer_que_entre debe seguir bajando de nivel hasta entrar.
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, [tool_use("t1", "Read", {"file_path": "spec.md"}, T0 - 5)])
    d = dict(COMPLETO, transcript_path=str(ruta), session_id="s1",
             worktree={"name": "feature/una-rama-con-nombre-realmente-largo"},
             cost=dict(COMPLETO["cost"], total_lines_added=1312, total_lines_removed=118))
    e = sl.leer_entrada(json.dumps(d).encode("utf-8"))
    act = sl.leer_actividad(e.transcript_path, e.session_id, T0)

    grilla_0 = sl.componer(e, act, int(T0), 0)
    assert max(len(l) for l in sl.a_texto(grilla_0)) > 140  # confirma que el nivel 0 desborda

    grilla = sl.componer_que_entre(e, act, int(T0), 140)
    assert max(len(l) for l in sl.a_texto(grilla)) <= 140
    assert grilla != grilla_0

    grilla_200 = sl.componer_que_entre(e, act, int(T0), 200)
    assert sl.ancho_de_grilla(grilla_200) == 200
    assert grilla_200 != grilla_0                  # a 200 se dibuja el peldaño -1, no el nivel 0


def test_no_queda_una_columna_muerta_a_ningun_ancho(tmp_path):
    """La propiedad que persigue el proyecto, como test de rango: cubre los anchos que no son peldaños,
    que es donde vive el elástico. Arranca en 47 (el ancho del nivel 4, el layout más plegado que existe);
    por debajo no hay nada que repartir y la línea desborda, que es el comportamiento de hoy.

    `ancho_de_grilla` es un `max`, así que la primera aserción sólo fija que la fila MÁS ANCHA llega al borde
    derecho; la segunda, que las tres llegan (el tablero llegó a dejar hasta 16 columnas de desparejo, a 202
    columnas 190/186/202, hasta que el último bloque de cada fila se corrió al borde). Lo que NO prueba es que
    ANCHO_ESCRITORIO_MAX esté bien puesto: la identidad de conservación que arma `repartir_sobrante` vale
    por construcción para cualquier ancho de escritorio, tope incluido o no; lo que protege el valor
    exacto del tope son las aserciones numéricas de `test_repartir_sobrante_respeta_el_tope_de_20`, no
    este test de rango."""
    crudo = sesion(tmp_path)
    for con_ritmo in (False, True):
        e = sl.leer_entrada(crudo)
        if con_ritmo:
            _con_ritmo(e)
        act = sl.leer_actividad(e.transcript_path, e.session_id, T0, e.contexto_total)
        for ancho in range(47, 241):
            g = sl.componer_que_entre(e, act, int(T0), ancho)
            assert sl.ancho_de_grilla(g) == ancho, f"a {ancho} columnas la grilla mide {sl.ancho_de_grilla(g)}"
            anchos = anchos_de_filas(g)
            assert len(set(anchos)) == 1, f"a {ancho} columnas las filas no llegan parejas al borde: {anchos}"


def _con_ritmo(e):
    """Lo que pasa en vivo: correr() le pone el esperado a cada ventana con reinicio. Reinicios a mitad de ventana."""
    e.cinco_h = sl.Ventana(58, T0 + 2.5 * 3600)
    e.siete_d = sl.Ventana(27, T0 + 3.5 * 86400)
    sl.poner_ritmo(e.cinco_h, sl.DURACION_5H, T0)
    sl.poner_ritmo(e.siete_d, sl.DURACION_7D, T0)


def test_el_ritmo_esperado_no_baja_de_peldano(tmp_path):
    """El esperado suma 12 columnas a la fila de las ventanas, que era la más ancha (63 de 63 a 165): sin mudar el
    costo y las líneas a otras filas, a 165 y a 140 la oficina perdía escritorios y leyendas. A cada peldaño el
    tablero con ritmo, cache con fallos y costo de 5 cifras tiene que entrar en lo que le deja la escena."""
    e = sl.leer_entrada(sesion(tmp_path))
    _con_ritmo(e)
    # Líneas de 3 cifras: con 4 («+1234 −567») ya se pasaba antes del ritmo y el elástico baja de peldaño.
    e.cache_fallos, e.costo, e.lineas = 12, 123.4, (312, 18)
    act = sl.Actividad(rama="master")
    for minimo, nivel in sl.NIVELES[:-1]:
        lugar = minimo - sl.ancho_escena(nivel) - sl.HUECO_MIN
        filas = [len(f) for f in sl.dibujar_tablero(e, act, nivel)]
        assert max(filas) <= lugar, f"nivel {nivel}: filas {filas}, lugar {lugar}"


def test_ancho_consola_cae_a_columns_y_a_un_respaldo(monkeypatch):
    """Todas las ramas devuelven el ancho ÚTIL, o sea ya con MARGEN_UI descontado (ver
    `test_la_grilla_entra_en_el_area_que_claude_code_pinta`)."""
    monkeypatch.setattr(sl, "_ancho_terminal", lambda: None)
    monkeypatch.setenv("COLUMNS", "101")
    assert sl.ancho_consola() == 101 - sl.MARGEN_UI
    monkeypatch.setenv("COLUMNS", "nada")
    assert sl.ancho_consola() == 120 - sl.MARGEN_UI
    monkeypatch.delenv("COLUMNS")
    assert sl.ancho_consola() == 120 - sl.MARGEN_UI
    monkeypatch.setenv("COLUMNS", "0")  # no puede devolver 0 ni negativo, aunque la línea desborde
    assert sl.ancho_consola() >= 1


def sesion(tmp_path):
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, [tool_use("ag1", "Agent", {"subagent_type": "Explore", "description": "Buscar"}, T0 - 30),
                          tool_use("t1", "Read", {"file_path": "spec.md"}, T0 - 5)])
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    meta = sub / "agent-a.meta.json"
    meta.write_text(json.dumps({"agentType": "Explore", "toolUseId": "ag1"}), encoding="utf-8")
    fijar_creacion(meta, T0 - 30)  # el censo lee el nacimiento de acá y el silencio del mtime de abajo:
    jsonl = sub / "agent-a.jsonl"  # con la hora real del disco el amigo quedaría mudo desde 2027
    escribir_jsonl(jsonl, [tool_use("x1", "Grep", {"pattern": "pose"}, T0 - 3)])
    os.utime(jsonl, (T0 - 3, T0 - 3))
    d = dict(COMPLETO, transcript_path=str(ruta), session_id="s1")
    return json.dumps(d).encode("utf-8")


def test_correr_produce_tres_lineas_con_ansi(tmp_path):
    salida = sl.correr(sesion(tmp_path), T0, 140)
    lineas = salida.split("\n")
    assert len(lineas) == 3 and all(l.endswith("\x1b[0m") for l in lineas)
    assert "\x1b[38;2;215;119;87m" in lineas[0]  # Clawd naranja
    assert "spec.md" in lineas[0] and "StatusBarDFR" in lineas[0]


def test_dorados_completos_por_nivel(tmp_path):
    """Llama a `componer` con el hueco por default y sin capa elástica: pinta el nivel tal cual la capa
    discreta lo arma, sin que `repartir_sobrante` ensanche nada. Legítimo para fijar la capa discreta
    sola, pero como la producción siempre pasa por `componer_que_entre`, estos dorados NO son "lo que se
    ve en pantalla" — para eso están los dorados por ancho de `test_dorados_por_ancho`."""
    crudo = sesion(tmp_path)
    e = sl.leer_entrada(crudo)
    act = sl.leer_actividad(e.transcript_path, e.session_id, T0, e.contexto_total)
    for nivel, ancho in ((0, 140), (1, 120), (2, 100), (3, 85), (4, 60)):
        g = sl.componer(e, act, int(T0), nivel)
        verificar_tokens(g)
        assert max(len(l) for l in sl.a_texto(g)) <= ancho, nivel
        golden(f"completo_n{nivel}", g)


def test_dorados_por_ancho(tmp_path):
    """Los dorados por nivel reciben el nivel ya elegido, así que el elástico no aparecería en ninguno.
    164 es un pelo por debajo del peldaño, 165 justo en él, y 202 es una terminal real medida."""
    crudo = sesion(tmp_path)
    e = sl.leer_entrada(crudo)
    act = sl.leer_actividad(e.transcript_path, e.session_id, T0, e.contexto_total)
    for ancho in (164, 165, 202):
        g = sl.componer_que_entre(e, act, int(T0), ancho)
        verificar_tokens(g)
        assert sl.ancho_de_grilla(g) == ancho
        golden(f"ancho_{ancho}", g)


def test_componer_acepta_escritorio_y_hueco_sin_cambiar_el_default(tmp_path):
    crudo = sesion(tmp_path)
    e = sl.leer_entrada(crudo)
    act = sl.leer_actividad(e.transcript_path, e.session_id, T0, e.contexto_total)
    base = sl.componer(e, act, int(T0), 0)
    assert sl.componer(e, act, int(T0), 0, 13, 2) == base
    ancho = sl.ancho_de_grilla(sl.componer(e, act, int(T0), 0, 20, 9))
    assert ancho == sl.ancho_de_grilla(base) + 4 * 7 + 7


def test_resets_at_invalido_no_cae_al_respaldo(tmp_path):
    d = dict(COMPLETO, rate_limits={"five_hour": {"used_percentage": 50, "resets_at": 1_800_000_000_000}})
    s = sl.correr(json.dumps(d).encode("utf-8"), T0, 140)
    assert s.count("\n") == 2  # 3 líneas: dibujó el tablero completo, no cayó al respaldo de una línea
    assert "5 h" in s and "50%" in s


def test_respaldo_ante_json_invalido():
    assert sl.correr(b"{no", T0, 140).startswith("\x1b[0m\x1b[38;2;212;212;212mClaude  ")


def test_respaldo_ante_fallo_interno(tmp_path, monkeypatch):
    def explota(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(sl, "dibujar_escena", explota)
    s = sl.correr(sesion(tmp_path), T0, 140)
    assert "Opus 5" in s and "StatusBarDFR" in s and "\n" not in s


def test_respaldo_si_la_entrada_explota(monkeypatch):
    def explota(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(sl, "leer_entrada", explota)
    s = sl.correr(b"{}", T0, 140)
    assert "Claude" in s and "\n" not in s


def test_ancho_terminal_lee_columns(monkeypatch):
    monkeypatch.setenv("COLUMNS", "164")
    assert sl._ancho_terminal() == 164
    monkeypatch.setenv("COLUMNS", "0")
    assert sl._ancho_terminal() is None


def correr_proceso(entrada: bytes, env_extra=None):
    env = dict(os.environ, **(env_extra or {}))
    return subprocess.run([sys.executable, str(RAIZ / "statusline.py")], input=entrada, capture_output=True, timeout=10, env=env)


def test_proceso_con_transcript_inexistente_dibuja_igual(tmp_path):
    d = dict(COMPLETO, transcript_path=str(tmp_path / "no.jsonl"), session_id="s1")
    r = correr_proceso(json.dumps(d).encode(), {"COLUMNS": "140"})
    assert r.returncode == 0 and r.stderr == b""
    assert r.stdout.decode("utf-8").count("\n") == 3 and "Opus 5" in r.stdout.decode("utf-8")


def test_proceso_con_transcript_truncado(tmp_path):
    ruta = tmp_path / "t.jsonl"
    ruta.write_bytes(json.dumps(tool_use("t1", "Read", {"file_path": "a.py"}, T0)).encode() + b'\n{"type": "user", "mess')
    d = dict(COMPLETO, transcript_path=str(ruta), session_id="s1")
    r = correr_proceso(json.dumps(d).encode(), {"COLUMNS": "140"})
    assert r.returncode == 0 and r.stderr == b"" and "a.py" in r.stdout.decode("utf-8")


def test_proceso_con_stdin_basura_no_falla():
    r = correr_proceso(b"\xff\xfe no es utf-8 ni json")
    assert r.returncode == 0 and r.stderr == b"" and b"Claude" in r.stdout


def test_dorados_con_ritmo_y_tareas(tmp_path):
    """Lo que se ve en vivo con una suscripción: el esperado de cada ventana, y un script y un monitor de fondo en el
    último escritorio. 164 y 165 son los dos lados del peldaño: el ritmo no puede bajar a nadie de peldaño."""
    e = sl.leer_entrada(sesion(tmp_path))
    _con_ritmo(e)
    act = sl.leer_actividad(e.transcript_path, e.session_id, T0, e.contexto_total)
    act.scripts, act.monitores = 1, 1
    for ancho in (164, 165, 202):
        g = sl.componer_que_entre(e, act, int(T0), ancho)
        verificar_tokens(g)
        assert sl.ancho_de_grilla(g) == ancho
        golden(f"ritmo_tareas_{ancho}", g)


def test_el_amigo_sin_modelo_propio_lleva_la_letra_del_de_la_sesion(tmp_path):
    """El meta del amigo no trae `model`: la corrida completa le pone el de la sesión antes de dibujar."""
    salida = sl.correr(sesion(tmp_path), T0, 165)
    primera = re.sub(r"\x1b\[[0-9;]*m", "", salida.split("\n")[0])
    assert "╭─◉◉╮ O " in primera, primera
