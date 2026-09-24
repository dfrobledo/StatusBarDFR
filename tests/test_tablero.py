import time

from conftest import cuadro, golden, sl, verificar_tokens


def entrada(**kw):
    e = sl.Entrada(modelo="Opus 5", esfuerzo="xhigh", carpeta="StatusBarDFR", pr_numero=12, pr_estado="approved",
                   contexto_pct=41.4, cache_observada=True, cache_tibia=True, cache_aciertos=0.784, cache_fallos=0,
                   cinco_h=sl.Ventana(58, 1_800_010_000), siete_d=sl.Ventana(27, 1_800_300_000),
                   costo=4.2, lineas=(312, 18))
    for k, v in kw.items():
        setattr(e, k, v)
    return e


ACT = sl.Actividad(rama="master")


def hora(t):
    lt = time.localtime(t)
    return f"{lt.tm_hour:02d}:{lt.tm_min:02d}"


def dia(t):
    return ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"][time.localtime(t).tm_wday]


def plano(fila):
    return "".join(c for c, _ in fila)


def test_medidor_y_torta():
    assert [sl.token_medidor(p, 75, 90) for p in (0, 74.9, 75, 89.9, 90)] == \
        ["texto principal", "texto principal", "aviso", "aviso", "critico"]
    assert [sl.torta(p) for p in (0, 1, 12.5, 12.6, 50, 99, 100)] == ["○", "󰪞", "󰪞", "󰪟", "󰪡", "󰪥", "󰪥"]


def test_barra_de_contexto_con_marca():
    b = sl.barra_contexto(41.4, 80, 20, "texto principal")
    assert plano(b) == "████████░░░░░░░░┆░░░"
    assert b[16] == ("┆", "texto secundario") and b[0] == ("█", "texto principal") and b[8] == ("░", "apagado")
    assert plano(sl.barra_contexto(95, 80, 10, "critico")) == "████████┆█"
    assert plano(sl.barra_contexto(0, 80, 20, "texto principal")).count("█") == 0


def test_fila_identidad_completa():
    assert plano(sl.fila_identidad(entrada(), ACT, 0)) == "Opus 5 · 󰧑 xhigh   󰉋 StatusBarDFR   󰘬 master    #12"
    f = sl.fila_identidad(entrada(), ACT, 0)
    assert f[-1] == ("2", "bien")


def test_fila_identidad_sin_esfuerzo_ni_pr_ni_rama():
    assert plano(sl.fila_identidad(entrada(esfuerzo=None, pr_numero=None), sl.Actividad(), 0)) == "Opus 5   󰉋 StatusBarDFR"


def test_fila_identidad_worktree_gana_a_la_rama_y_mr():
    e = entrada(worktree="mi-feature", pr_es_mr=True, pr_estado="changes_requested")
    f = sl.fila_identidad(e, ACT, 0)
    assert plano(f).endswith("󰘬 mi-feature    !12") and f[-1][1] == "critico"


def test_fila_identidad_por_nivel():
    assert plano(sl.fila_identidad(entrada(), ACT, 2)) == "Opus 5   󰉋 StatusBarDFR   󰘬 master    #12"
    assert plano(sl.fila_identidad(entrada(), ACT, 3)) == "Opus 5   󰉋 StatusBarDFR"


def test_fila_contexto_completa_y_niveles():
    assert plano(sl.fila_contexto(entrada(), 0)) == "󰃥 ████████░░░░░░░░┆░░░  41%   󰆼  78%"
    assert plano(sl.fila_contexto(entrada(cache_fallos=2), 0)) == "󰃥 ████████░░░░░░░░┆░░░  41%   󰆼  78% · 2 fallos"
    assert plano(sl.fila_contexto(entrada(cache_fallos=2), 2)) == "󰃥 ████████░░░░░░░░┆░░░  41%   󰆼  78%"
    assert plano(sl.fila_contexto(entrada(), 3)) == "󰃥 ████░░░░┆░  41%   󰆼  78%"
    assert plano(sl.fila_contexto(entrada(), 4)) == "󰃥  41%   󰆼  78%"


def test_fila_contexto_colorea_barra_y_numero_juntos():
    f = sl.fila_contexto(entrada(contexto_pct=91, cache_observada=False), 0)
    assert f[2][1] == "critico" and f[-1][1] == "critico"  # primera celda llena y el "%"
    f = sl.fila_contexto(entrada(contexto_pct=76, cache_observada=False), 0)
    assert f[2][1] == "aviso" and f[-1][1] == "aviso"


def test_fila_contexto_sin_datos():
    assert plano(sl.fila_contexto(sl.Entrada(), 0)) == ""
    assert plano(sl.fila_contexto(entrada(cache_observada=False), 0)) == "󰃥 ████████░░░░░░░░┆░░░  41%"
    assert plano(sl.fila_contexto(entrada(cache_aciertos=None), 0)) == "󰃥 ████████░░░░░░░░┆░░░  41%"


def test_fila_ventanas_completa():
    h5, h7, d7 = hora(1_800_010_000), hora(1_800_300_000), dia(1_800_300_000)
    assert plano(sl.fila_ventanas(entrada(), 0)) == f"󰪢 5 h  58% ↻ {h5}   󰪠 7 d  27% ↻ {d7} {h7}   $ 4.20   +312 −18"
    assert plano(sl.fila_ventanas(entrada(), 1)) == f"󰪢 5 h  58% ↻ {h5}   󰪠 7 d  27% ↻ {d7}   $ 4.20"
    assert plano(sl.fila_ventanas(entrada(), 2)) == "󰪢 5 h  58%   󰪠 7 d  27%   $ 4.20"
    assert plano(sl.fila_ventanas(entrada(), 4)) == "󰪢 5 h  58%   󰪠 7 d  27%"


def test_ventana_con_resets_at_invalido_omite_el_reloj(tmp_path):
    # time.localtime(1_800_000_000_000) (epoch en milisegundos) lanza OSError: un resets_at inválido no
    # debe tirar todo el tablero al respaldo, sólo omitir la parte "↻".
    f = sl.fila_ventanas(entrada(cinco_h=sl.Ventana(50, 1_800_000_000_000), siete_d=None, lineas=None, costo=None), 0)
    assert plano(f) == "󰪡 5 h  50%"
    assert "↻" not in plano(f)


def test_fila_ventanas_bloques_ausentes_y_colores():
    assert plano(sl.fila_ventanas(entrada(cinco_h=None, siete_d=None, lineas=None), 0)) == "$ 4.20"
    assert plano(sl.fila_ventanas(entrada(costo=12.5), 2)) == "󰪢 5 h  58%   󰪠 7 d  27%   $12.50"
    f = sl.fila_ventanas(entrada(cinco_h=sl.Ventana(72, None)), 2)
    assert f[0][1] == "aviso" and f[9][1] == "aviso" and f[3][1] == "texto secundario"


def test_costo_siempre_cinco_caracteres():
    assert [sl._costo(c) for c in (0.5, 4.2, 99.99, 123.4, 999.94, 1234.5)] == \
        [" 0.50", " 4.20", "99.99", "123.4", "999.9", " 1234"]
    assert all(len(sl._costo(c)) == 5 for c in (0, 9.999, 100, 12345))
    assert [sl._costo(c) for c in (99.995, 999.95, 99.994)] == ["100.0", " 1000", "99.99"]
    assert all(len(sl._costo(c)) == 5 for c in (0, 9.999, 99.995, 100, 999.95, 12345))


def test_dorados_del_tablero_por_nivel():
    for nivel in range(5):
        g = sl.dibujar_tablero(entrada(cinco_h=sl.Ventana(88, None), siete_d=sl.Ventana(27, None)), ACT, nivel)
        verificar_tokens(g)
        golden(f"tablero_n{nivel}", g)


def test_tablero_sin_naranja():
    for fila in sl.dibujar_tablero(entrada(), ACT, 0):
        assert all(tok != "mascota" for _, tok in fila)


def test_tablero_del_peldano_nuevo_es_el_del_nivel_cero():
    """El -1 sólo agranda la escena: el tablero ya estaba completo en el 0 y no debe perder el bloque de
    líneas por un `nivel == 0` que no dejaba entrar a los niveles negativos."""
    e = entrada()
    assert cuadro(sl.dibujar_tablero(e, ACT, -1)) == cuadro(sl.dibujar_tablero(e, ACT, 0))
    assert "312" in cuadro(sl.dibujar_tablero(e, ACT, -1))  # el bloque de líneas, que es el que se perdía
