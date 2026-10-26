"""Las tareas de fondo: scripts (`Bash` con `run_in_background`) y monitores (`Monitor`).

Formas medidas el 2026-10-25 sobre transcripts reales de Claude Code 2.1.310: el arranque es un `tool_result` con
`toolUseResult.backgroundTaskId` (script) o `toolUseResult.taskId` + `timeoutMs` (monitor); el fin, una
`<task-notification>` con `completed`, `failed` o `killed`; y cada evento de un monitor, una notificación sin status.
"""
import os

from conftest import T0, arranque_tarea, aviso_tarea, fijar_creacion, oficina, sl, tool_result, tool_use


def con_carpeta(tmp_path, monkeypatch, principal, salidas=(), amigos=()):
    """Una oficina más la carpeta de salidas de tareas donde la busca Claude Code: TEMP/claude/<proyecto>/<sesión>/tasks."""
    ruta = oficina(tmp_path, principal, amigos)
    temp = tmp_path / "temp"
    tareas = temp / "claude" / tmp_path.name / "s1" / "tasks"
    tareas.mkdir(parents=True)
    for nombre, nace, mtime in salidas:
        f = tareas / f"{nombre}.output"
        f.write_text("x", encoding="utf-8")
        fijar_creacion(f, nace)
        os.utime(f, (mtime, mtime))
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.delenv("CLAUDE_CODE_TMPDIR", raising=False)
    return ruta


def relleno(n, t):
    """Resultados de 4 KB: n de ellos empujan lo anterior fuera de la ventana de avisos si n*4 KB > 1 MB."""
    salida = []
    for i in range(n):
        r = tool_result(f"r{i}", t + i * 0.01)
        r["message"]["content"][0]["content"] = "x" * 4000
        salida.append(r)
    return salida


def cuenta(ruta, ahora):
    act = sl.leer_actividad(ruta, "s1", ahora)
    return act.scripts, act.monitores


# ── arranque y fin ─────────────────────────────────────────────────────
def test_un_script_de_fondo_cuenta_aunque_no_haya_amigos(tmp_path, monkeypatch):
    """El caso que motivó la feature: la oficina vacía y un script corriendo, sin nada que lo muestre."""
    ruta = con_carpeta(tmp_path, monkeypatch, [arranque_tarea("bscript01", T0)])
    act = sl.leer_actividad(ruta, "s1", T0 + 30)
    assert (act.scripts, act.monitores, act.amigos) == (1, 0, [])


def test_un_monitor_cuenta_como_monitor(tmp_path, monkeypatch):
    ruta = con_carpeta(tmp_path, monkeypatch, [arranque_tarea("bmonit001", T0, monitor=True)])
    assert cuenta(ruta, T0 + 30) == (0, 1)


def test_los_eventos_del_monitor_no_lo_terminan(tmp_path, monkeypatch):
    principal = [arranque_tarea("bmonit001", T0, monitor=True), aviso_tarea("bmonit001", T0 + 10, estado=None)]
    ruta = con_carpeta(tmp_path, monkeypatch, principal)
    assert cuenta(ruta, T0 + 30) == (0, 1)


def test_completed_failed_y_killed_terminan_la_tarea(tmp_path, monkeypatch):
    for i, estado in enumerate(("completed", "failed", "killed")):
        caso = tmp_path / estado
        caso.mkdir()
        principal = [arranque_tarea("bscript01", T0), arranque_tarea("bmonit001", T0, monitor=True),
                     aviso_tarea("bscript01", T0 + 10, estado), aviso_tarea("bmonit001", T0 + 11, estado, monitor=True)]
        ruta = con_carpeta(caso, monkeypatch, principal)
        assert cuenta(ruta, T0 + 30) == (0, 0), estado


def test_el_fin_de_una_tarea_no_apaga_a_otra(tmp_path, monkeypatch):
    principal = [arranque_tarea("bscript01", T0), arranque_tarea("bscript02", T0 + 1),
                 aviso_tarea("bscript01", T0 + 10)]
    ruta = con_carpeta(tmp_path, monkeypatch, principal)
    assert cuenta(ruta, T0 + 30) == (1, 0)


def test_el_monitor_no_persistente_vence_con_su_timeout(tmp_path, monkeypatch):
    """Si el aviso de vencimiento ya no está en la ventana, el timeout declarado al arrancar alcanza para soltarlo."""
    principal = [arranque_tarea("bmonit001", T0, monitor=True, timeout_ms=600_000),
                 arranque_tarea("bmonit002", T0, monitor=True, timeout_ms=600_000, persistente=True)]
    ruta = con_carpeta(tmp_path, monkeypatch, principal)
    assert cuenta(ruta, T0 + 590) == (0, 2)
    assert cuenta(ruta, T0 + 600 + sl.SEGUNDOS_GRACIA_MONITOR + 1) == (0, 1)


# ── la carpeta de salidas: el arranque que ya no está en la ventana ───
def test_una_tarea_vieja_que_sigue_escribiendo_cuenta_por_su_salida(tmp_path, monkeypatch):
    """El arranque se escribe una sola vez y se va quedando atrás, igual que el despacho de un amigo. La salida
    escrita DENTRO de la ventana prueba que vivía hasta entonces, y su fin, que viene después, estaría a la vista."""
    principal = [arranque_tarea("bscript01", T0), *relleno(300, T0 + 10), aviso_tarea("bmonit001", T0 + 20, None)]
    ruta = con_carpeta(tmp_path, monkeypatch, principal, salidas=[("bscript01", T0, T0 + 15), ("bmonit001", T0, T0 + 20)])
    assert len(sl.leer_cola(ruta, maximo=sl.VENTANA_NOTIFICACIONES)) < len(principal), "el arranque tiene que quedar FUERA"
    assert cuenta(ruta, T0 + 30) == (1, 1)


def test_una_salida_quieta_desde_antes_de_la_ventana_no_cuenta(tmp_path, monkeypatch):
    """Su fin pudo haber pasado y quedado atrás también: sin pruebas de vida se da por terminada."""
    principal = [arranque_tarea("bscript01", T0), *relleno(300, T0 + 10)]
    ruta = con_carpeta(tmp_path, monkeypatch, principal, salidas=[("bscript01", T0, T0 + 1)])
    assert cuenta(ruta, T0 + 30) == (0, 0)


def test_un_comando_de_primer_plano_no_es_una_tarea(tmp_path, monkeypatch):
    """Cada Bash crea su `b*.output` mientras corre, también el de primer plano (lo que delató a la barra contando
    como script el comando con el que se la estaba mirando). Nació dentro de la ventana sin arranque de fondo."""
    principal = [*relleno(300, T0 + 10)]
    ruta = con_carpeta(tmp_path, monkeypatch, principal, salidas=[("bfrente01", T0 + 13, T0 + 14)])
    assert cuenta(ruta, T0 + 30) == (0, 0)


def test_con_el_transcript_entero_a_la_vista_la_carpeta_no_agrega_nada(tmp_path, monkeypatch):
    """Si la ventana cubre todo el archivo y el arranque no aparece, la salida es de otra cosa (o de antes)."""
    ruta = con_carpeta(tmp_path, monkeypatch, [tool_use("t1", "Read", {"file_path": "a"}, T0)],
                       salidas=[("bscript01", T0, T0 + 1)])
    assert cuenta(ruta, T0 + 30) == (0, 0)


def test_las_salidas_de_los_amigos_no_son_tareas(tmp_path, monkeypatch):
    """La misma carpeta guarda la salida de cada subagente (`a` + 16 hex): ésos ya tienen escritorio."""
    principal = [*relleno(300, T0 + 10)]
    ruta = con_carpeta(tmp_path, monkeypatch, principal, salidas=[("a0697adae65baee2c", T0, T0 + 12)])
    assert cuenta(ruta, T0 + 30) == (0, 0)


# ── el escritorio de las tareas ───────────────────────────────────────
def amigos_en(n):
    return [sl.Amigo(id=f"a{k}", tipo="explore", nombre="explore", nacido_hace=60.0, escritorio=k) for k in range(n)]


def test_el_escritorio_de_tareas_va_al_final_con_iconos_y_contador():
    act = sl.Actividad(scripts=2, monitores=1)
    g = sl.dibujar_escena(act, sl.Humor(), 0, 0)
    ultimo = [f[-sl.ANCHO_ESCRITORIO[0]:] for f in g]
    assert "".join(c for c, _ in ultimo[0]).rstrip() == f"{sl.ICONO_SCRIPT}2 {sl.ICONO_MONITOR}"
    assert ultimo[1][sl.LAMPARA_EN] == ("󰥟", "lampara encendida")
    assert len(g[0]) == sl.ancho_escena(0)


def test_sin_tareas_no_hay_escritorio_de_tareas():
    g = sl.dibujar_escena(sl.Actividad(), sl.Humor(), 0, 0)
    plano = "".join(c for f in g for c, _ in f)
    assert sl.ICONO_SCRIPT not in plano and sl.ICONO_MONITOR not in plano


def test_con_tareas_los_amigos_se_aprietan_un_escritorio():
    """Con 4 escritorios y tareas, los amigos tienen 3: el tercero y el cuarto amigo pasan al contador «+2»."""
    act = sl.Actividad(amigos=amigos_en(4), monitores=1)
    g = sl.dibujar_escena(act, sl.Humor(), 0, 0)
    ancho = sl.ANCHO_ESCRITORIO[0]
    tercero = "".join(c for c, _ in g[0][sl.ANCHO_CLAWD + 2 * ancho: sl.ANCHO_CLAWD + 3 * ancho]).rstrip()
    assert tercero == "+2"
    assert len(g[0]) == sl.ancho_escena(0)


def test_en_el_nivel_sin_escritorios_las_tareas_no_se_dibujan():
    g = sl.dibujar_escena(sl.Actividad(scripts=1), sl.Humor(), 0, 4)
    assert len(g[0]) == sl.ANCHO_CLAWD
