import json
import os

from conftest import (T0, compactacion, escribir_jsonl, fijar_creacion, notificacion, prompt_usuario,
                      resultado_fondo, sl, texto_asistente, texto_final, tool_result, tool_use)


# ── leer_cola ──────────────────────────────────────────────────────────
def test_cola_lee_las_ultimas_lineas_y_descarta_la_cortada(tmp_path):
    ruta = tmp_path / "t.jsonl"
    ruta.write_text("".join(json.dumps({"n": i, "relleno": "x" * 100}) + "\n" for i in range(2000)), encoding="utf-8")
    cola = sl.leer_cola(str(ruta), maximo=4096)
    assert cola and cola[-1]["n"] == 1999
    assert all("n" in o for o in cola)  # ninguna línea a medias
    assert len(cola) < 60


def test_cola_tolera_ultima_linea_truncada(tmp_path):
    ruta = tmp_path / "t.jsonl"
    ruta.write_text(json.dumps({"n": 1}) + "\n" + '{"n": 2, "corta', encoding="utf-8")
    assert [o["n"] for o in sl.leer_cola(str(ruta))] == [1]


def test_cola_de_archivo_inexistente_es_vacia(tmp_path):
    assert sl.leer_cola(str(tmp_path / "no.jsonl")) == []


def test_cola_agranda_la_ventana_si_una_linea_grande_corta_la_chica(tmp_path):
    # Línea real > 64 KB (402 casos medidos, máx 1,09 MB): con la ventana chica queda cortada y se
    # descarta entera, perdiendo también las entradas anteriores (el Read pendiente).
    ruta = tmp_path / "grande.jsonl"
    resultado_grande = tool_result("r1", T0 + 3)
    resultado_grande["message"]["content"][0]["content"] = "x" * 100_000
    entradas = [
        tool_use("ag1", "Agent", {"subagent_type": "Explore", "description": "Revisar"}, T0),
        resultado_fondo("ag1", T0 + 1, "a9e7b17fbc69cc405"),
        tool_use("r1", "Read", {"file_path": "a.py"}, T0 + 2),
        resultado_grande,
    ]
    escribir_jsonl(ruta, entradas)
    cola = sl.leer_cola(str(ruta))
    assert len(cola) == 4
    a = sl.analizar(cola)
    assert sl.pose_de_analisis(a, T0 + 10) == (sl.PENSANDO, "", None)


def test_cola_no_reintenta_si_la_ventana_chica_ya_alcanza(tmp_path, monkeypatch):
    ruta = tmp_path / "chico.jsonl"
    escribir_jsonl(ruta, [tool_use(f"t{i}", "Read", {"file_path": f"a{i}.py"}, T0 + i) for i in range(3)])
    llamadas = []
    original = sl._leer_ventana

    def contador(ruta_, maximo):
        llamadas.append(maximo)
        return original(ruta_, maximo)
    monkeypatch.setattr(sl, "_leer_ventana", contador)
    cola = sl.leer_cola(str(ruta))
    assert len(llamadas) == 1
    assert len(cola) == 3


# ── poses de Clawd ─────────────────────────────────────────────────────
def pose(entradas, ahora=T0 + 10):
    return sl.pose_de_analisis(sl.analizar(entradas), ahora)


def test_sin_entradas_esperando():
    assert pose([]) == (sl.ESPERANDO, "", None)


def test_tool_use_pendiente_elige_pose_y_leyenda():
    assert pose([tool_use("t1", "Read", {"file_path": "E:\\x\\statusline.py"}, T0)]) == (sl.LEYENDO, "statusline.py", "Read")
    assert pose([tool_use("t1", "Grep", {"pattern": "def main"}, T0)]) == (sl.LEYENDO, "def main", "Grep")
    assert pose([tool_use("t1", "Edit", {"file_path": "/a/b.py"}, T0)]) == (sl.ESCRIBIENDO, "b.py", "Edit")
    assert pose([tool_use("t1", "Bash", {"command": "ls", "description": "Listar"}, T0)]) == (sl.EJECUTANDO, "Listar", "Bash")
    assert pose([tool_use("t1", "Skill", {"skill": "writing-plans"}, T0)]) == (sl.EJECUTANDO, "writing-plans", "Skill")
    assert pose([tool_use("t1", "WebFetch", {"url": "https://docs.claude.com/x/y"}, T0)]) == (sl.NAVEGANDO, "docs.claude.com", "WebFetch")
    assert pose([tool_use("t1", "mcp__claude-in-chrome__navigate", {"url": "http://a.b/c"}, T0)]) == (sl.NAVEGANDO, "a.b", "mcp__claude-in-chrome__navigate")
    assert pose([tool_use("t1", "Rara", {"x": 1}, T0)]) == (sl.EJECUTANDO, "Rara", "Rara")


def test_la_ultima_herramienta_pendiente_manda():
    e = [tool_use("t1", "Read", {"file_path": "a.py"}, T0), tool_use("t2", "Bash", {"description": "Correr"}, T0 + 1)]
    assert pose(e)[0] == sl.EJECUTANDO


def test_solo_agent_pendiente_es_delegando():
    e = [tool_use("t1", "Agent", {"subagent_type": "Explore", "description": "Buscar"}, T0)]
    assert pose(e) == (sl.DELEGANDO, "··", "Agent")


def test_agent_pendiente_mas_herramienta_propia_muestra_la_herramienta():
    e = [tool_use("t1", "Agent", {"description": "Buscar"}, T0), tool_use("t2", "Read", {"file_path": "a.py"}, T0 + 1)]
    assert pose(e)[0] == sl.LEYENDO


def test_error_reciente_es_sobresalto_aunque_haya_herramienta_nueva():
    e = [tool_use("t1", "Bash", {"description": "Falla"}, T0), tool_result("t1", T0 + 1, error=True),
         tool_use("t2", "Read", {"file_path": "a.py"}, T0 + 2)]
    assert pose(e, ahora=T0 + 3.5)[0] == sl.SOBRESALTO
    assert pose(e, ahora=T0 + 4.5)[0] == sl.LEYENDO


def test_resultado_sin_respuesta_es_pensando():
    e = [tool_use("t1", "Read", {"file_path": "a.py"}, T0), tool_result("t1", T0 + 1)]
    assert pose(e) == (sl.PENSANDO, "", None)


def test_prompt_humano_es_pensando_y_limpia_pendientes():
    e = [tool_use("t1", "Bash", {"description": "Largo"}, T0), prompt_usuario(T0 + 5)]
    assert pose(e)[0] == sl.PENSANDO


def test_respuesta_terminada_es_esperando_y_luego_dormido():
    e = [texto_asistente(T0)]
    assert pose(e, ahora=T0 + 60)[0] == sl.ESPERANDO
    assert pose(e, ahora=T0 + 301)[0] == sl.DORMIDO


def test_entradas_meta_y_marcadores_se_ignoran():
    e = [texto_asistente(T0), {"type": "user", "isMeta": True, "timestamp": "2027-01-01T00:00:00Z",
                              "message": {"role": "user", "content": "x"}},
         {"type": "last-prompt", "lastPrompt": "x"}, {"type": "system", "subtype": "turn_duration"}]
    assert pose(e, ahora=T0 + 1)[0] == sl.ESPERANDO


def test_rama_sale_de_la_ultima_linea_que_la_trae():
    a = sl.analizar([texto_asistente(T0), {"type": "system", "subtype": "turn_duration", "gitBranch": "feat/x"}])
    assert a.rama == "feat/x"


# ── compactación ───────────────────────────────────────────────────────
def test_compactacion_por_marca_del_sistema_dura_dos_segundos():
    a = sl.analizar([texto_asistente(T0), compactacion(T0 + 5)])
    assert sl.hay_compactacion(a, T0 + 6.5, 200_000)
    assert not sl.hay_compactacion(a, T0 + 7.5, 200_000)


def test_compactacion_por_caida_de_contexto():
    a = sl.analizar([texto_asistente(T0, msg="m1", contexto=150_000), texto_asistente(T0 + 5, msg="m2", contexto=40_000)])
    assert sl.hay_compactacion(a, T0 + 6, 200_000)
    assert not sl.hay_compactacion(a, T0 + 8, 200_000)


def test_caida_chica_no_es_compactacion():
    a = sl.analizar([texto_asistente(T0, msg="m1", contexto=100_000), texto_asistente(T0 + 5, msg="m2", contexto=60_000)])
    assert not sl.hay_compactacion(a, T0 + 6, 200_000)


# ── escritorios ────────────────────────────────────────────────────────
def test_escritorios_primero_libre_y_se_conservan():
    d = [("a", 0.0, None), ("b", 1.0, 5.0), ("c", 2.0, None), ("d", 9.0, None)]
    asig = sl.asignar_escritorios(d)
    assert asig == {"a": 0, "b": 1, "c": 2, "d": 1}  # d toma el de b, libre desde 5+2


def test_escritorio_no_se_libera_durante_la_gracia():
    asig = sl.asignar_escritorios([("a", 0.0, 5.0), ("b", 6.0, None)])
    assert asig == {"a": 0, "b": 1}


# ── leer_actividad de punta a punta ────────────────────────────────────
def armar_sesion(tmp_path, principal, amigos=(), nace=T0, escrito=T0 + 3):
    """amigos: lista de (tool_use_id, agentType, entradas_del_amigo). Las fechas de los archivos son parte
    del dato: el censo saca el nacimiento de la creación del .meta.json y el silencio del mtime del .jsonl."""
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, principal)
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    for i, (tid, tipo, entradas) in enumerate(amigos):
        meta = sub / f"agent-{i:017x}.meta.json"
        meta.write_text(json.dumps({"agentType": tipo, "toolUseId": tid}), encoding="utf-8")
        fijar_creacion(meta, nace)
        jsonl = sub / f"agent-{i:017x}.jsonl"
        escribir_jsonl(jsonl, entradas)
        os.utime(jsonl, (escrito, escrito))
    return str(ruta)


def test_actividad_con_amigo_vivo_lee_su_transcript(tmp_path):
    principal = [tool_use("ag1", "Agent", {"subagent_type": "Explore", "description": "Buscar poses"}, T0)]
    amigo = [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 3)]
    ruta = armar_sesion(tmp_path, principal, [("ag1", "Explore", amigo)])
    act = sl.leer_actividad(ruta, "s1", T0 + 10)
    assert act.pose == sl.DELEGANDO
    assert len(act.amigos) == 1
    am = act.amigos[0]
    assert (am.tipo, am.nombre, am.descripcion, am.escritorio) == ("explore", "explore", "Buscar poses", 0)
    assert (am.pose, am.leyenda, am.herramienta) == (sl.LEYENDO, "pose", "Grep")
    assert am.nacido_hace == 10 and am.terminado_hace is None


def test_tipo_del_amigo_sale_del_meta_si_falta_en_el_input(tmp_path):
    principal = [tool_use("ag1", "Agent", {"description": "Auditar"}, T0)]
    ruta = armar_sesion(tmp_path, principal, [("ag1", "general-purpose", [])])
    am = sl.leer_actividad(ruta, "s1", T0 + 5).amigos[0]
    assert (am.tipo, am.nombre, am.pose) == ("general", "general", sl.PENSANDO)


def test_amigo_sin_meta_es_pensando_y_desconocido(tmp_path):
    ruta = armar_sesion(tmp_path, [tool_use("ag9", "Agent", {"description": "x"}, T0)])
    am = sl.leer_actividad(ruta, "s1", T0 + 5).amigos[0]
    assert (am.tipo, am.nombre, am.pose) == ("desconocido", "?", sl.PENSANDO)


def test_amigo_terminado_se_va_a_los_dos_segundos(tmp_path):
    principal = [tool_use("ag1", "Agent", {"subagent_type": "Plan"}, T0), tool_result("ag1", T0 + 20)]
    ruta = armar_sesion(tmp_path, principal)
    assert sl.leer_actividad(ruta, "s1", T0 + 21).amigos[0].terminado_hace == 1
    assert sl.leer_actividad(ruta, "s1", T0 + 23).amigos == []


def test_clases_de_amigo():
    assert [sl.clase_amigo(t) for t in ("Explore", "general-purpose", "claude", "Plan", "mi-agente", None)] == \
        ["explore", "general", "general", "plan", "propio", "desconocido"]
    assert [sl.nombre_amigo(t) for t in ("Explore", "general-purpose", "claude-code-guide", None)] == \
        ["explore", "general", "claude-", "?"]


def test_actividad_sin_ruta_es_esperando():
    act = sl.leer_actividad(None, None, T0)
    assert act.pose == sl.ESPERANDO and act.amigos == []


# ── amigos de fondo ───────────────────────────────────────────────────
def test_agent_de_fondo_no_termina_con_su_tool_result():
    a = sl.analizar([tool_use("ag1", "Agent", {"description": "Revisar"}, T0), resultado_fondo("ag1", T0 + 2, "a9e7b17fbc69cc405")])
    assert a.despachos[0][2] is None and a.despachos[0][4] == "a9e7b17fbc69cc405"
    assert sl.pose_de_analisis(a, T0 + 10)[0] == sl.PENSANDO  # el tool_result llegó, Clawd piensa


def test_agent_de_primer_plano_sigue_igual():
    a = sl.analizar([tool_use("ag1", "Agent", {"description": "x"}, T0), tool_result("ag1", T0 + 20)])
    assert a.despachos[0][2] == T0 + 20 and a.despachos[0][4] is None


def test_agent_de_fondo_sobrevive_a_un_prompt_nuevo():
    a = sl.analizar([tool_use("ag1", "Agent", {}, T0), resultado_fondo("ag1", T0 + 2, "abcdef0123456789a"), prompt_usuario(T0 + 30)])
    assert a.despachos[0][2] is None


def sesion_fondo(tmp_path, agent_id, entradas_amigo, mtime=None, principal_extra=()):
    principal = [tool_use("ag1", "Agent", {"subagent_type": "Explore", "description": "Revisar"}, T0),
                 resultado_fondo("ag1", T0 + 2, agent_id), *principal_extra]
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, principal)
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    if entradas_amigo is not None:
        meta = sub / f"agent-{agent_id}.meta.json"
        meta.write_text(json.dumps({"agentType": "Explore", "toolUseId": "ag1"}), encoding="utf-8")
        fijar_creacion(meta, T0)
        archivo = sub / f"agent-{agent_id}.jsonl"
        escribir_jsonl(archivo, entradas_amigo)
        if mtime is not None:
            os.utime(archivo, (mtime, mtime))
    return str(ruta)


def test_amigo_de_fondo_vivo_muestra_su_herramienta(tmp_path):
    ruta = sesion_fondo(tmp_path, "a9e7b17fbc69cc405", [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 5)], mtime=T0 + 5)
    act = sl.leer_actividad(ruta, "s1", T0 + 60)
    assert len(act.amigos) == 1
    am = act.amigos[0]
    assert (am.pose, am.leyenda, am.terminado_hace, am.escritorio) == (sl.LEYENDO, "pose", None, 0)


def test_amigo_de_fondo_sin_archivo_todavia_es_pensando(tmp_path):
    ruta = sesion_fondo(tmp_path, "a9e7b17fbc69cc405", None)
    am = sl.leer_actividad(ruta, "s1", T0 + 3).amigos[0]
    assert am.pose == sl.PENSANDO and am.terminado_hace is None


def test_amigo_de_fondo_pensando_sigue_vivo(tmp_path):
    ruta = sesion_fondo(tmp_path, "a9e7b17fbc69cc405", [tool_use("x1", "Read", {"file_path": "a.py"}, T0 + 5), tool_result("x1", T0 + 6)], mtime=T0 + 6)
    am = sl.leer_actividad(ruta, "s1", T0 + 60).amigos[0]
    assert am.pose == sl.PENSANDO and am.terminado_hace is None


def test_amigo_de_fondo_terminado_se_va_con_chispa(tmp_path):
    # El fin ya no lo declara el `end_turn` del propio subagente sino su <task-notification> (ver
    # test_amigos.py::test_end_turn_por_si_solo_no_mata_al_amigo, que mide por qué no alcanzaba).
    # Lo que este test sigue cuidando es la chispa: el escritorio no se apaga de golpe.
    fin = T0 + 100
    entradas = [tool_use("x1", "Read", {"file_path": "a.py"}, T0 + 5), tool_result("x1", T0 + 6), texto_final(fin)]
    # el <task-id> de la notificación es el agentId, o sea el nombre del archivo del subagente
    ruta = sesion_fondo(tmp_path, "a9e7b17fbc69cc405", entradas, mtime=fin,
                        principal_extra=[notificacion("ag1", fin, agent_id="a9e7b17fbc69cc405")])
    am = sl.leer_actividad(ruta, "s1", fin + 1).amigos[0]
    assert am.terminado_hace == 1
    assert sl.leer_actividad(ruta, "s1", fin + 5).amigos == []


def test_amigo_de_fondo_con_texto_intermedio_sigue_vivo(tmp_path):
    # Claude Code escribe cada bloque de texto como una línea propia: un `text` con stop_reason null
    # a media respuesta (medido: 1650 casos reales) no es el final del subagente.
    ruta = sesion_fondo(tmp_path, "a9e7b17fbc69cc405", [texto_asistente(T0 + 5)], mtime=T0 + 5)
    am = sl.leer_actividad(ruta, "s1", T0 + 10).amigos[0]
    assert am.terminado_hace is None
    assert am.pose == sl.ESPERANDO


def test_dos_amigos_de_fondo_conservan_escritorio(tmp_path):
    principal = [tool_use("ag1", "Agent", {"subagent_type": "Explore"}, T0), resultado_fondo("ag1", T0 + 1, "aaaaaaaaaaaaaaaaa"),
                 tool_use("ag2", "Agent", {"subagent_type": "Plan"}, T0 + 10), resultado_fondo("ag2", T0 + 11, "bbbbbbbbbbbbbbbbb"),
                 notificacion("ag1", T0 + 50, agent_id="aaaaaaaaaaaaaaaaa")]
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, principal)
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    for aid, tid, entradas, mt in (("aaaaaaaaaaaaaaaaa", "ag1", [texto_final(T0 + 50)], T0 + 50),
                                   ("bbbbbbbbbbbbbbbbb", "ag2", [tool_use("y", "Bash", {"description": "Correr"}, T0 + 12)], T0 + 12)):
        meta = sub / f"agent-{aid}.meta.json"
        meta.write_text(json.dumps({"agentType": "x", "toolUseId": tid}), encoding="utf-8")
        fijar_creacion(meta, T0 if tid == "ag1" else T0 + 10)
        f = sub / f"agent-{aid}.jsonl"
        escribir_jsonl(f, entradas)
        os.utime(f, (mt, mt))
    act = sl.leer_actividad(str(ruta), "s1", T0 + 60)
    assert [(am.id, am.escritorio, am.pose) for am in act.amigos] == [("ag2", 1, sl.EJECUTANDO)]  # ag1 ya se fue; ag2 conserva el escritorio 1


def test_amigo_de_fondo_mudo_mas_alla_del_umbral_desaparece(tmp_path):
    # El umbral pasó de 5 min a SEGUNDOS_MUDO porque a los 5 min todavía hay agentes trabajando: el peor
    # hueco mid-trabajo medido sobre 219 subagentes reales es de 1105 s. La envolvente y los dos lados del
    # umbral están en test_amigos.py (amigo_mudo_seis_minutos / mudo_mas_alla_de_la_envolvente).
    caso1 = tmp_path / "caso1"
    caso1.mkdir()
    mudo = T0 - sl.SEGUNDOS_MUDO - 100
    ruta = sesion_fondo(caso1, "a9e7b17fbc69cc405", [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 5)], mtime=mudo)
    assert sl.leer_actividad(ruta, "s1", T0).amigos == []
    # Mudo pero dentro del umbral: sigue vivo y se lee su transcript como siempre.
    caso2 = tmp_path / "caso2"
    caso2.mkdir()
    ruta2 = sesion_fondo(caso2, "b9e7b17fbc69cc406", [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 5)], mtime=T0 - 100)
    am = sl.leer_actividad(ruta2, "s1", T0).amigos[0]
    assert am.pose == sl.LEYENDO


def test_amigo_de_fondo_sin_meta_usa_la_ruta_construida_con_el_agentId(tmp_path):
    principal = [tool_use("ag1", "Agent", {"subagent_type": "Explore", "description": "Revisar"}, T0),
                 resultado_fondo("ag1", T0 + 2, "cafecafecafecafe1")]
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, principal)
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)  # sin .meta.json: sólo el jsonl del subagente, nombrado con el agentId
    archivo = sub / "agent-cafecafecafecafe1.jsonl"
    escribir_jsonl(archivo, [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 5)])
    os.utime(archivo, (T0 + 5, T0 + 5))
    am = sl.leer_actividad(str(ruta), "s1", T0 + 10).amigos[0]
    assert (am.pose, am.leyenda, am.tipo) == (sl.LEYENDO, "pose", "explore")


# El costo del censo lo cuida ahora test_amigos.py::test_el_censo_no_abre_los_metas_de_los_amigos_viejos:
# `leer_metas` (abría todos los .meta.json de la carpeta) ya no existe, y la puerta por mtime la reemplaza.


def test_amigo_de_fondo_sin_meta_ni_subagent_type_es_desconocido(tmp_path):
    principal = [tool_use("ag1", "Agent", {"description": "Revisar"}, T0),
                 resultado_fondo("ag1", T0 + 2, "cafecafecafecafe2")]
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, principal)
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    archivo = sub / "agent-cafecafecafecafe2.jsonl"
    escribir_jsonl(archivo, [tool_use("x1", "Grep", {"pattern": "pose"}, T0 + 5)])
    os.utime(archivo, (T0 + 5, T0 + 5))
    am = sl.leer_actividad(str(ruta), "s1", T0 + 10).amigos[0]
    assert (am.tipo, am.nombre) == ("desconocido", "?")
