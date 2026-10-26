"""El censo de amigos: quién está en la oficina, desde cuándo y hasta cuándo.

Los tres bugs que este archivo fija como invariante se midieron el 2026-09-17 sobre sesiones reales
(219 transcripts de subagente, 28.989 huecos entre entradas, 217 `.meta.json`).
"""
from conftest import (T0, amigo, entrega, id_agente, notificacion, oficina, prompt_usuario, sl, texto_asistente,
                      texto_final, tool_result, tool_use)


def tool_result_gordo(id_, t):
    """Un resultado de 4 KB, del tamaño con el que se llena de verdad la ventana de `leer_cola`."""
    r = tool_result(id_, t)
    r["message"]["content"][0]["content"] = "x" * 4000
    return r


# ── censo: el despacho no es la fuente ─────────────────────────────────
def test_amigo_aparece_aunque_el_despacho_ya_no_este_en_la_ventana(tmp_path):
    """La causa dominante del bug: el `tool_use` del `Agent` se escribe UNA sola vez y queda atrás a medida
    que el transcript crece. En una sesión viva el despacho de un amigo que seguía trabajando estaba
    a 426 KB del final, 6,5 veces fuera de la ventana de 64 KB de `leer_cola`: la oficina se veía vacía con
    el amigo adentro. El censo tiene que salir de la carpeta `subagents`, que no depende de la ventana."""
    principal = [texto_asistente(T0 + 100), tool_use("t9", "Read", {"file_path": "a.py"}, T0 + 101)]
    ruta = oficina(tmp_path, principal, [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 105)],
                                               nace=T0, mtime=T0 + 105, descripcion="Buscar poses")])
    act = sl.leer_actividad(ruta, "s1", T0 + 110)
    assert len(act.amigos) == 1
    am = act.amigos[0]
    assert (am.tipo, am.nombre, am.descripcion) == ("explore", "explore", "Buscar poses")
    assert (am.pose, am.leyenda) == (sl.LEYENDO, "pose")


def test_el_nacimiento_sale_de_la_creacion_del_meta(tmp_path):
    """El `mtime` del `.meta.json` no sirve (se reescribe) y el timestamp del despacho tampoco: contra la
    creación real da desvíos de hasta +1065 s, porque un agente de fondo se encola y arranca cuando hay lugar."""
    ruta = oficina(tmp_path, [], [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "p"}, T0 + 50)],
                                        nace=T0, mtime=T0 + 50)])
    assert sl.leer_actividad(ruta, "s1", T0 + 60).amigos[0].nacido_hace == 60


def test_el_censo_no_abre_los_metas_de_los_amigos_viejos(tmp_path, monkeypatch):
    """Abrir los `.meta.json` de toda la carpeta cuesta 7,7 ms con 40 metas (medido), un sexto del presupuesto
    propio de 45 ms. Con la puerta por silencio baja a 0,68 ms porque sólo se abren los candidatos."""
    viejo = amigo("viejo", [tool_use("x", "Grep", {"pattern": "p"}, T0 - 5000)], nace=T0 - 5000, mtime=T0 - 5000,
                  agent_id="b" * 17)
    nuevo = amigo("ag1", [tool_use("x1", "Grep", {"pattern": "p"}, T0 + 50)], nace=T0, mtime=T0 + 50)
    ruta = oficina(tmp_path, [], [viejo, nuevo])
    abiertos = []
    original = sl.leer_meta

    def espia(ruta_meta):
        abiertos.append(ruta_meta)
        return original(ruta_meta)
    monkeypatch.setattr(sl, "leer_meta", espia)
    act = sl.leer_actividad(ruta, "s1", T0 + 60)
    assert [am.id for am in act.amigos] == ["ag1"]
    assert len(abiertos) == 1, f"se abrieron metas de más: {abiertos}"


def test_un_amigo_que_todavia_no_nacio_no_ocupa_escritorio(tmp_path):
    """La puerta del censo compara contra `ahora`, y un archivo con fecha posterior la pasa "por izquierda"
    (la resta da negativa). En producción no hay archivos del futuro, pero sí al reproducir un instante
    pasado — que es como se mide el fix contra las sesiones reales."""
    ruta = oficina(tmp_path, [], [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "p"}, T0 + 500)],
                                        nace=T0 + 400, mtime=T0 + 500)])
    assert sl.leer_actividad(ruta, "s1", T0 + 10).amigos == []


def test_solo_se_abre_el_transcript_de_los_amigos_que_entran_en_la_oficina(tmp_path):
    """La oficina tiene 6 escritorios en su peldaño más ancho. Un fan-out real llega a 40 agentes vivos a la
    vez (medido en una sesión real): abrir los 40 transcripts cuesta más que todo el presupuesto propio,
    y 34 de esas lecturas no se dibujan en ningún lado."""
    amigos = [amigo(f"ag{i}", [tool_use(f"x{i}", "Grep", {"pattern": "p"}, T0 + 50)], nace=T0 + i,
                    mtime=T0 + 50, agent_id=f"{i:017d}") for i in range(12)]
    ruta = oficina(tmp_path, [], amigos)
    leidos = []
    original = sl.leer_cola

    def espia(ruta_, maximo=None):
        leidos.append(ruta_)
        return original(ruta_) if maximo is None else original(ruta_, maximo)
    monkeypatch_local = espia
    import unittest.mock as _mock
    with _mock.patch.object(sl, "leer_cola", monkeypatch_local):
        act = sl.leer_actividad(ruta, "s1", T0 + 60)
    de_amigos = [r for r in leidos if "subagents" in r]
    assert len(de_amigos) <= max(sl.ESCRITORIOS_POR_NIVEL.values()), f"se abrieron {len(de_amigos)} transcripts"
    assert len(act.amigos) == 12  # el modelo los conoce a todos; lo que se acota es a quién se le abre el archivo


# ── fin: silencio ──────────────────────────────────────────────────────
def test_amigo_mudo_seis_minutos_sigue_en_su_escritorio(tmp_path):
    """El corte de 5 min daba por muerto a un agente que seguía trabajando. Medido sobre 219 subagentes
    reales: el peor hueco mid-trabajo es de 1105 s, y un corte a los 300 s mata a 6 agentes vivos."""
    ruta = oficina(tmp_path, [], [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 60)],
                                        nace=T0, mtime=T0 + 60)])
    act = sl.leer_actividad(ruta, "s1", T0 + 420)
    assert len(act.amigos) == 1 and act.amigos[0].terminado_hace is None


def test_amigo_mudo_mas_alla_de_la_envolvente_libera_el_escritorio(tmp_path):
    """La cota de arriba: con SEGUNDOS_MUDO no muere ninguno de los 219 agentes medidos (envolvente 1105 s),
    pero el silencio tiene que terminar matando o un escritorio queda tomado para siempre."""
    ruta = oficina(tmp_path, [], [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 60)],
                                        nace=T0, mtime=T0 + 60)])
    ahora = T0 + 60 + sl.SEGUNDOS_MUDO + sl.SEGUNDOS_TRANSICION + 1
    assert sl.leer_actividad(ruta, "s1", ahora).amigos == []


def test_la_envolvente_medida_entra_en_el_umbral_de_silencio():
    """El umbral no es un número de gusto: 1105,2 s es el peor hueco mid-trabajo de los 219 agentes reales.
    La cota de abajo lo cubre; la de arriba impide que el escritorio quede tomado media hora."""
    assert sl.SEGUNDOS_MUDO > 1105.2
    assert sl.SEGUNDOS_MUDO <= 1800.0


# ── fin: la notificación ───────────────────────────────────────────────
def test_notificacion_completed_apaga_el_escritorio(tmp_path):
    """El fin fino: sin ella habría que esperar los SEGUNDOS_MUDO para liberar el escritorio."""
    principal = [notificacion("ag1", T0 + 61)]
    ruta = oficina(tmp_path, principal, [amigo("ag1", [texto_final(T0 + 60)], nace=T0, mtime=T0 + 60)])
    assert sl.leer_actividad(ruta, "s1", T0 + 62).amigos[0].terminado_hace == 1
    assert sl.leer_actividad(ruta, "s1", T0 + 64).amigos == []


def test_la_notificacion_se_lee_en_sus_dos_formas(tmp_path):
    """La misma notificación cae como `queue-operation` y como `attachment`; el proyecto no modelaba ninguna
    de las dos, así que `analizar` las ignoraba enteras."""
    def oficina_con(caso, principal):
        caso.mkdir()
        return oficina(caso, principal, [amigo("ag1", [texto_final(T0 + 60)], nace=T0, mtime=T0 + 60)])

    # Control: la MISMA oficina sin la notificación conserva al amigo. Sin esto la aserción de abajo la
    # cumple cualquier código que no muestre amigos nunca.
    sin = oficina_con(tmp_path / "control", [])
    assert [am.id for am in sl.leer_actividad(sin, "s1", T0 + 64).amigos] == ["ag1"]
    for i, tipo in enumerate(("queue-operation", "attachment")):
        ruta = oficina_con(tmp_path / f"caso{i}", [notificacion("ag1", T0 + 61, tipo=tipo)])
        assert sl.leer_actividad(ruta, "s1", T0 + 64).amigos == [], tipo


def test_la_notificacion_se_busca_mas_atras_que_la_ventana_de_leer_cola(tmp_path):
    """La notificación llega en el momento exacto en que el amigo para, pero se va de la ventana de 64 KB
    enseguida: medido sobre 511 notificaciones reales, a los SEGUNDOS_MUDO sólo el 2% sigue dentro de 64 KB.
    Sin buscarla más atrás, el escritorio queda encendido los 20 minutos del respaldo por silencio — que es
    justo lo que se vio al reproducir sesiones reales: 2 a 3 escritorios de más por instante.
    El transcript crece 483 KB (p90) en esos 1200 s, así que con 1 MB la notificación sigue estando."""
    relleno = [tool_result_gordo(f"r{i}", T0 + 62 + i) for i in range(30)]  # ~120 KB después de la notificación
    principal = [notificacion("ag1", T0 + 61), *relleno]
    ruta = oficina(tmp_path, principal, [amigo("ag1", [texto_final(T0 + 60)], nace=T0, mtime=T0 + 60)])
    assert len(sl.leer_cola(ruta)) < len(principal), "la notificación tiene que quedar FUERA de la ventana"
    assert sl.leer_actividad(ruta, "s1", T0 + 100).amigos == []


def test_la_notificacion_de_una_parada_posterior_no_trae_el_id_del_despacho(tmp_path):
    """El caso que se vio en vivo el 2026-09-17 en la ventana de RockAvionics: la oficina mostraba 3 amigos
    y Claude Code reportaba 1. Dos habían parado 15 min antes y su notificación estaba en el transcript, pero
    con OTRO `<tool-use-id>`: cada `SendMessage` al agente es un `tool_use` nuevo, y la notificación trae el
    id del mensaje que provocó ESA parada, no el del despacho, que es el que guarda el `.meta.json`.
    Buscando por tool-use-id sólo se ve la primera parada de cada amigo. La llave estable es el `<task-id>`,
    que es el agentId, que es el nombre del archivo del meta."""
    entradas = [texto_final(T0 + 60), prompt_usuario(T0 + 150), texto_final(T0 + 200, msg="msg_f2")]
    principal = [notificacion("otro-tool-use-id", T0 + 201, agent_id=id_agente("ag1"))]
    ruta = oficina(tmp_path, principal, [amigo("ag1", entradas, nace=T0, mtime=T0 + 200)])
    assert sl.leer_actividad(ruta, "s1", T0 + 205).amigos == []


def test_un_amigo_parado_sin_notificacion_conserva_el_escritorio(tmp_path):
    """El control del test de arriba: lo que apaga el escritorio es la notificación, no el `end_turn`. Un
    agente que paró y todavía no notificó (o cuya notificación ya no está) se queda hasta el silencio."""
    ruta = oficina(tmp_path, [], [amigo("ag1", [texto_final(T0 + 60)], nace=T0, mtime=T0 + 60)])
    assert [am.id for am in sl.leer_actividad(ruta, "s1", T0 + 205).amigos] == ["ag1"]


def test_una_notificacion_que_no_es_completed_no_mata(tmp_path):
    ruta = oficina(tmp_path, [notificacion("ag1", T0 + 61, estado="failed")],
                   [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "p"}, T0 + 60)], nace=T0, mtime=T0 + 60)])
    assert sl.leer_actividad(ruta, "s1", T0 + 64).amigos[0].terminado_hace is None


def test_el_amigo_reanudado_despues_de_la_notificacion_sigue_vivo(tmp_path):
    """La propia notificación lo avisa: "the same task-id may notify more than once". Dice que el agente PARÓ,
    no que murió — el coordinador puede mandarle otro mensaje. Si escribió después, sigue vivo."""
    principal = [notificacion("ag1", T0 + 61)]
    entradas = [texto_final(T0 + 60), prompt_usuario(T0 + 150),
                tool_use("x2", "Bash", {"description": "Compilar"}, T0 + 200)]
    ruta = oficina(tmp_path, principal, [amigo("ag1", entradas, nace=T0, mtime=T0 + 200)])
    am = sl.leer_actividad(ruta, "s1", T0 + 205).amigos[0]
    assert am.terminado_hace is None and am.pose == sl.EJECUTANDO


# ── fin: la entrega del informe (2.1.310) ──────────────────────────────
def test_la_entrega_del_informe_cuenta_como_parada(tmp_path):
    """El bug que se veía en vivo el 2026-10-25: desde Claude Code 2.1.310 los subagentes terminan con una llamada a
    `SubagentHandback` y su resultado, no con un `end_turn` (109 de 111 medidos). `_esta_parado` no lo reconocía,
    la notificación nunca apagaba el escritorio y el amigo se quedaba sentado los 20 minutos del respaldo."""
    principal = [notificacion("ag1", T0 + 61)]
    ruta = oficina(tmp_path, principal, [amigo("ag1", entrega("h1", T0 + 60), nace=T0, mtime=T0 + 60)])
    assert sl.leer_actividad(ruta, "s1", T0 + 64).amigos == []


def test_la_entrega_sin_notificacion_no_apaga(tmp_path):
    """El control de arriba: lo que apaga es la notificación; la entrega sola sólo dice que ahora mismo está parado."""
    ruta = oficina(tmp_path, [], [amigo("ag1", entrega("h1", T0 + 60), nace=T0, mtime=T0 + 60)])
    assert [am.id for am in sl.leer_actividad(ruta, "s1", T0 + 64).amigos] == ["ag1"]


def test_el_amigo_reanudado_despues_de_la_entrega_sigue_vivo(tmp_path):
    entradas = [*entrega("h1", T0 + 60), prompt_usuario(T0 + 150), tool_use("x2", "Grep", {"pattern": "p"}, T0 + 200)]
    ruta = oficina(tmp_path, [notificacion("ag1", T0 + 61)], [amigo("ag1", entradas, nace=T0, mtime=T0 + 200)])
    am = sl.leer_actividad(ruta, "s1", T0 + 205).amigos[0]
    assert am.terminado_hace is None and am.pose == sl.LEYENDO


def test_failed_y_killed_con_el_amigo_parado_apagan(tmp_path):
    """Un agente que falla («Agent terminated») notifica `failed` y su archivo termina en `stop_sequence`; medido
    el 2026-10-25, ninguno de los 7 escribió después. Antes sólo `completed` apagaba y éstos esperaban el silencio."""
    for estado in ("failed", "killed"):
        caso = tmp_path / estado
        caso.mkdir()
        ruta = oficina(caso, [notificacion("ag1", T0 + 61, estado=estado)],
                       [amigo("ag1", [texto_final(T0 + 60)], nace=T0, mtime=T0 + 60)])
        assert sl.leer_actividad(ruta, "s1", T0 + 64).amigos == [], estado


# ── fin: end_turn ya no alcanza ────────────────────────────────────────
def test_end_turn_por_si_solo_no_mata_al_amigo(tmp_path):
    """70 de 218 agentes reales tienen un `end_turn` que no es el final: el coordinador les manda otro mensaje
    y siguen. Y por el otro lado 59 de 219 no terminan NUNCA en `end_turn`, así que tampoco era un fin
    completo. Un agente parado se ve dormido en su escritorio, que es lo que es, y no desaparecido."""
    ruta = oficina(tmp_path, [], [amigo("ag1", [texto_final(T0 + 60)], nace=T0, mtime=T0 + 60)])
    act = sl.leer_actividad(ruta, "s1", T0 + 400)
    assert len(act.amigos) == 1
    assert act.amigos[0].terminado_hace is None
    assert act.amigos[0].pose == sl.DORMIDO


# ── lo que ya funcionaba y no se rompe ─────────────────────────────────
def test_el_amigo_de_primer_plano_sigue_muriendo_con_su_tool_result(tmp_path):
    principal = [tool_use("ag1", "Agent", {"subagent_type": "Plan"}, T0), tool_result("ag1", T0 + 20)]
    ruta = oficina(tmp_path, principal, [amigo("ag1", [texto_final(T0 + 20)], nace=T0, mtime=T0 + 20,
                                               tipo="Plan", fondo=False)])
    assert sl.leer_actividad(ruta, "s1", T0 + 21).amigos[0].terminado_hace == 1
    assert sl.leer_actividad(ruta, "s1", T0 + 23).amigos == []


def test_dos_amigos_toman_escritorios_distintos_en_orden_de_nacimiento(tmp_path):
    amigos = [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "p"}, T0 + 50)], nace=T0, mtime=T0 + 50),
              amigo("ag2", [tool_use("x2", "Bash", {"description": "Correr"}, T0 + 50)], nace=T0 + 10,
                    mtime=T0 + 50, tipo="Plan", agent_id="c" * 17)]
    ruta = oficina(tmp_path, [], amigos)
    act = sl.leer_actividad(ruta, "s1", T0 + 60)
    assert [(am.id, am.escritorio, am.pose) for am in act.amigos] == \
        [("ag1", 0, sl.LEYENDO), ("ag2", 1, sl.EJECUTANDO)]


# ── el modelo de cada amigo ────────────────────────────────────────────
def test_el_modelo_sale_del_meta(tmp_path):
    ruta = oficina(tmp_path, [], [amigo("ag1", [tool_use("x1", "Grep", {"pattern": "p"}, T0 + 5)],
                                        nace=T0, mtime=T0 + 5, modelo="sonnet")])
    assert sl.leer_actividad(ruta, "s1", T0 + 10).amigos[0].modelo == "sonnet"


def test_sin_meta_el_modelo_sale_del_despacho(tmp_path):
    """El amigo recién despachado todavía no escribió su .meta.json: el `model` del propio `Agent` lo nombra."""
    principal = [tool_use("t1", "Agent", {"subagent_type": "Explore", "description": "Buscar", "model": "haiku"}, T0)]
    ruta = oficina(tmp_path, principal, [])
    assert sl.leer_actividad(ruta, "s1", T0 + 10).amigos[0].modelo == "haiku"


def test_el_que_hereda_toma_el_modelo_de_la_sesion():
    """`inherit` (3 de 607 metas medidos), un meta sin `model` o un despacho sin él: corre con el de la sesión."""
    act = sl.Actividad(amigos=[sl.Amigo("a", "explore", "explore", modelo=m) for m in ("inherit", "", "fable")])
    sl.heredar_modelo(act, "Opus 5.5")
    assert [am.modelo for am in act.amigos] == ["Opus 5.5", "Opus 5.5", "fable"]
