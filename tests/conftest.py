"""Helpers compartidos. Reloj fijo T0; todos los tests derivan sus instantes de ahí."""
import ctypes
import json
import os
import re
import pathlib
import sys
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import statusline as sl  # noqa: E402

DORADOS = RAIZ / "tests" / "dorados"
T0 = 1_800_000_000.0  # 2027-01-15 08:00:00 UTC, un instante cualquiera pero fijo


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def tool_use(id_, nombre, entrada, t, msg="msg_1", contexto=50_000):
    return {"type": "assistant", "timestamp": iso(t), "gitBranch": "master",
            "message": {"id": msg, "role": "assistant",
                        "content": [{"type": "tool_use", "id": id_, "name": nombre, "input": entrada}],
                        "usage": {"input_tokens": 2, "cache_creation_input_tokens": 100,
                                  "cache_read_input_tokens": contexto - 102}}}


def tool_result(id_, t, error=False):
    return {"type": "user", "timestamp": iso(t),
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": id_,
                                                     "content": "ok", "is_error": error}]}}


def texto_asistente(t, msg="msg_2", contexto=60_000):
    return {"type": "assistant", "timestamp": iso(t), "gitBranch": "master",
            "message": {"id": msg, "role": "assistant", "content": [{"type": "text", "text": "listo"}],
                        "usage": {"input_tokens": contexto, "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0}}}


def prompt_usuario(t):
    return {"type": "user", "timestamp": iso(t), "message": {"role": "user", "content": "hola"}}


def resultado_fondo(id_, t, agent_id):
    """tool_result inmediato de un Agent lanzado en segundo plano (forma real de Claude Code 2.1.274)."""
    r = tool_result(id_, t)
    r["message"]["content"][0]["content"] = [{"type": "text", "text":
        f"Async agent launched successfully. (This tool result is internal metadata ...)\nagentId: {agent_id} (internal ID - do not mention to user...)\noutput_file: C:\\x\\{agent_id}.output"}]
    return r


def texto_final(t, msg="msg_f"):
    """Última entrada de un subagente terminado: bloque text con stop_reason end_turn."""
    e = texto_asistente(t, msg=msg)
    e["message"]["stop_reason"] = "end_turn"
    return e


def compactacion(t):
    return {"type": "system", "subtype": "compact_boundary", "timestamp": iso(t),
            "content": "Conversation compacted", "compactMetadata": {"trigger": "auto", "preTokens": 150_000}}


def escribir_jsonl(ruta, entradas):
    ruta.write_text("".join(json.dumps(e) + "\n" for e in entradas), encoding="utf-8")


def fijar_creacion(ruta, t: float) -> None:
    """Fija la fecha de CREACIÓN del archivo (`st_birthtime`/`st_ctime` en Windows), que `os.utime` no toca.
    El nacimiento de un subagente sale de ahí: el mtime del .meta.json se reescribe y contra el timestamp del
    despacho da desvíos de hasta +1065 s (medido el 2026-09-17 sobre 217 metas reales)."""
    k = ctypes.windll.kernel32
    h = k.CreateFileW(str(ruta), 0x100, 0, None, 3, 0x80, None)  # FILE_WRITE_ATTRIBUTES, OPEN_EXISTING
    if h == -1:
        raise OSError(f"no se pudo abrir {ruta}")
    ft = ctypes.c_ulonglong(int((t + 11_644_473_600) * 10_000_000))  # FILETIME: 100 ns desde 1601
    ok = k.SetFileTime(h, ctypes.byref(ft), None, None)
    k.CloseHandle(h)
    if not ok:
        raise OSError(f"no se pudo fijar la creación de {ruta}")


def id_agente(tid):
    """El agentId que le toca a un amigo de `oficina()`: es el nombre de su archivo (`agent-<agentId>.jsonl`)
    y también el `<task-id>` de sus notificaciones."""
    return ("a" + str(tid).rjust(16, "0"))[:17]


def notificacion(tool_use_id, t, agent_id=None, estado="completed", tipo="queue-operation"):
    """`<task-notification>` tal como la escribe Claude Code 2.1.274 (forma medida sobre transcripts reales).
    Llega por duplicado: como `queue-operation` (enqueue y después remove) y como `attachment`.
    El `<task-id>` es el agentId y es lo ESTABLE; el `<tool-use-id>` es el del mensaje que provocó esta
    parada, así que cambia en cada reanudación y no sirve de llave."""
    if agent_id is None:
        agent_id = id_agente(tool_use_id)
    xml = "\n".join([
        "<task-notification>",
        f"<task-id>{agent_id}</task-id>",
        f"<tool-use-id>{tool_use_id}</tool-use-id>",
        f"<output-file>C:\\x\\{agent_id}.output</output-file>",
        f"<status>{estado}</status>",
        '<summary>Agent "x" finished</summary>',
        "<note>A task-notification fires each time this agent stops with no live background children of its own. "
        "The user can send it another message and resume it, so the same task-id may notify more than once.</note>",
        "</task-notification>",
    ])
    if tipo == "queue-operation":
        return {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t), "content": xml}
    return {"type": "attachment", "timestamp": iso(t), "uuid": "u1",
            "attachment": {"type": "queued_command", "prompt": xml, "commandMode": "task-notification",
                           "timestamp": iso(t)}}


def entrega(id_, t):
    """Cómo termina un subagente desde Claude Code 2.1.310 (109 de 111 medidos el 2026-10-25): no con un `end_turn`
    sino con una llamada a `SubagentHandback` y su resultado. Devuelve las dos entradas."""
    uso = tool_use(id_, "SubagentHandback", {"report": "listo"}, t, msg="msg_h")
    uso["message"]["stop_reason"] = "tool_use"
    r = tool_result(id_, t + 0.1)
    r["message"]["content"][0]["content"] = [{"type": "text", "text": '{"success":true,"message":"Report delivered"}'}]
    return [uso, r]


def arranque_tarea(task_id, t, monitor=False, timeout_ms=1_800_000, persistente=False):
    """El `tool_result` con el que nace una tarea de fondo (forma real de 2.1.310): un Bash con `run_in_background`
    trae `backgroundTaskId`; un Monitor trae `taskId`, `timeoutMs` y `persistent`."""
    r = tool_result("u_" + task_id, t)
    if monitor:
        r["toolUseResult"] = {"taskId": task_id, "timeoutMs": timeout_ms, "persistent": persistente}
        r["message"]["content"][0]["content"] = f"Monitor started (task {task_id}, expires in 30m ...)"
    else:
        r["toolUseResult"] = {"stdout": "", "stderr": "", "interrupted": False, "backgroundTaskId": task_id}
        r["message"]["content"][0]["content"] = f"Command running in background with ID: {task_id}."
    return r


def aviso_tarea(task_id, t, estado="completed", monitor=False):
    """`<task-notification>` de una tarea de fondo. Con `estado=None` es un evento de Monitor, que no trae status."""
    if estado is None:
        cuerpo = [f'<summary>Monitor event: "x"</summary>', "<event>linea</event>"]
    else:
        que = "Monitor" if monitor else "Background command"
        cuerpo = [f"<status>{estado}</status>", f'<summary>{que} "x" {estado}</summary>']
    xml = "\n".join(["<task-notification>", f"<task-id>{task_id}</task-id>", *cuerpo, "</task-notification>"])
    return {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t), "content": xml}


def amigo(tid, entradas, nace, mtime, agent_id=None, tipo="Explore", descripcion="Revisar", fondo=True, modelo="opus"):
    """Un subagente de la carpeta `subagents`: su .meta.json y su .jsonl. `modelo=None` lo deja sin campo `model`."""
    return dict(tid=tid, entradas=entradas, nace=nace, mtime=mtime, tipo=tipo, descripcion=descripcion,
                fondo=fondo, agent_id=agent_id or id_agente(tid), modelo=modelo)


def oficina(tmp_path, principal=(), amigos=()):
    """Sesión completa en disco: transcript principal + `s1/subagents` con un .meta.json y un .jsonl por amigo,
    con su creación y su mtime puestos a mano. Devuelve la ruta del principal."""
    ruta = tmp_path / "s1.jsonl"
    escribir_jsonl(ruta, list(principal))
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    for am in amigos:
        meta = {"agentType": am["tipo"], "description": am["descripcion"], "toolUseId": am["tid"],
                "spawnDepth": 1}
        if am["modelo"] is not None:
            meta["model"] = am["modelo"]
        if am["fondo"]:
            meta["requestShape"] = "background"
            meta["requestNonInteractive"] = True
        m = sub / f"agent-{am['agent_id']}.meta.json"
        m.write_text(json.dumps(meta), encoding="utf-8")
        fijar_creacion(m, am["nace"])
        if am["entradas"] is not None:
            f = sub / f"agent-{am['agent_id']}.jsonl"
            escribir_jsonl(f, am["entradas"])
            os.utime(f, (am["mtime"], am["mtime"]))
    return str(ruta)


# WhiteSpace de JavaScript: lo que recorta String.prototype.trim. ESC no está en la lista, y de ahí
# que el `\x1b[0m` con el que cierra pintar_fila alcance para proteger el final de la línea.
ESPACIOS_JS = " \t\n\r\v\f\u00a0\ufeff"
SIN_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def como_lo_ve_claude_code(salida: str) -> list[str]:
    """La status line no se muestra tal como sale del script: Claude Code 2.1.274 (`dcn`) hace
    `stdout.trim().split(nl).flatMap(U => U.trim() || []).join(nl)`, o sea le recorta los espacios a
    CADA línea y DESCARTA las que queden vacías. Cualquier invariante sobre lo que se ve en pantalla
    se mide acá, después del trim, y no sobre la salida del script."""
    lineas = salida.strip(ESPACIOS_JS).split("\n")
    return [t for t in (linea.strip(ESPACIOS_JS) for linea in lineas) if t]


def columna_de_la_tinta(linea: str) -> int:
    """En qué columna arranca lo que se ve, sin contar los escapes ANSI (no ocupan celda)."""
    plana = SIN_ANSI.sub("", linea)
    return len(plana) - len(plana.lstrip(" "))


def verificar_tokens(grilla):
    assert len(grilla) == 3
    for fila in grilla:
        for car, tok in fila:
            assert tok in sl.PALETA, (car, tok)
            assert len(car) == 1, car


def cuadro(grilla) -> str:
    return "\n".join(linea.rstrip() for linea in sl.a_texto(grilla))


def anchos_de_filas(grilla) -> list[int]:
    """El ancho de CADA fila, sin rstrip y sin max: el vocabulario que le falta a la suite para hablar
    del borde derecho. `cuadro()` recorta y `ancho_de_grilla` toma el máximo, así que ninguno de los dos
    puede ver que una fila quedó corta."""
    return [len(f) for f in grilla]


def golden(nombre: str, grilla) -> None:
    """Compara con tests/dorados/<nombre>.txt; con ACTUALIZAR_DORADOS=1 lo (re)escribe."""
    verificar_tokens(grilla)
    ruta = DORADOS / f"{nombre}.txt"
    actual = cuadro(grilla)
    if os.environ.get("ACTUALIZAR_DORADOS"):
        DORADOS.mkdir(exist_ok=True)
        ruta.write_text(actual + "\n", encoding="utf-8")
    assert ruta.exists(), f"falta el dorado {ruta}; correr con ACTUALIZAR_DORADOS=1 y revisarlo a ojo"
    esperado = ruta.read_text(encoding="utf-8").rstrip("\n")
    assert actual == esperado, f"\n--- esperado\n{esperado}\n--- actual\n{actual}"
