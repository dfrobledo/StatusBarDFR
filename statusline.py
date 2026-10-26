#!/usr/bin/env python3
"""StatusBarDFR: status line "Oficina" para Claude Code.

Python 3.12, biblioteca estándar, un solo archivo, sin estado en disco.
Secciones: PALETA · PINTURA · ENTRADA · TRANSCRIPT · ESCENA · TABLERO · PLEGADO · MAIN.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════ PALETA
# Única tabla de colores del archivo. Cada celda pide un token; nunca un hexadecimal suelto.
PALETA: dict[str, str] = {
    "mascota": "#D77757",
    # Desde que el escritorio rotula el encargo, el color es lo único que dice el tipo: se distinguen entre sí también
    # con daltonismo, y de Clawd y de las letras de modelo (tests/test_colores.py). El ámbar de Plan se leía como un
    # Clawd chiquito, y el verde y el rosa de antes eran el mismo color para un deuteranope.
    "amigo explore": "#3d56f1",
    "amigo general": "#17a66a",
    "amigo plan": "#b8ac24",
    "amigo propio": "#ad36a2",
    "amigo desconocido": "#9A9A9A",
    "lampara encendida": "#F2E394",
    "lampara apagada": "#4A4A4A",
    "frio": "#7FB7D9",
    "texto principal": "#D4D4D4",
    "texto secundario": "#9A9A9A",
    "apagado": "#5C5C5C",
    "piso": "#3A3A3A",
    "bien": "#0ca30c",
    "aviso": "#fab219",
    "critico": "#d03b3b",
    "ritmo bajo": "#4c8fe8",
    # Anthropic no le asigna color a cada modelo (la paleta de marca tiene un solo acento naranja, que es el de Clawd):
    # tonos propios, lejos de los del ritmo. En el tablero va uno solo; en la oficina, la letra de cada amigo.
    "modelo opus": "#b48ef0",
    "modelo sonnet": "#3ec6d6",
    "modelo haiku": "#f08cb8",
    "modelo fable": "#e8975a",
}
# El esfuerzo lleva el color de su modelo, más intenso cuanto más alto: `max` es el color del modelo tal cual y los
# de abajo se lo mezclan con un gris claro, que baja la saturación sin mover el tono. Se generan una sola vez para que
# PALETA siga siendo la única tabla de colores: "esfuerzo <familia> <nivel>", y "esfuerzo <nivel>" para un modelo
# sin familia conocida, sobre el texto principal.
NIVELES_ESFUERZO = ("low", "medium", "high", "xhigh", "max")
_PROPORCION_DEL_MODELO = (0.30, 0.48, 0.66, 0.83, 1.0)
_GRIS_PALIDO = "#e6e6e6"


def _mezcla(hexa: str, otro: str, t: float) -> str:
    """t partes de hexa y (1 - t) de otro, canal por canal."""
    canales = (round(int(hexa[i:i + 2], 16) * t + int(otro[i:i + 2], 16) * (1 - t)) for i in (1, 3, 5))
    return "#" + "".join(f"{c:02x}" for c in canales)


for _base in [t for t in PALETA if t.startswith("modelo ")] + ["texto principal"]:
    _prefijo = "esfuerzo " + (_base[len("modelo "):] + " " if _base.startswith("modelo ") else "")
    for _nivel, _t in zip(NIVELES_ESFUERZO, _PROPORCION_DEL_MODELO):
        PALETA[_prefijo + _nivel] = _mezcla(PALETA[_base], _GRIS_PALIDO, _t)

Celda = tuple[str, str]  # (carácter, token)
Fila = list[Celda]
Grilla = list[Fila]  # siempre 3 filas


def texto(s: str, token: str) -> Fila:
    return [(c, token) for c in s]


def fila_vacia(ancho: int) -> Fila:
    return [(" ", "apagado")] * ancho


def poner(fila: Fila, col: int, s: str, token: str) -> None:
    """Escribe s desde col; lo que no entra se corta (nunca crece la fila)."""
    for i, c in enumerate(s):
        if 0 <= col + i < len(fila):
            fila[col + i] = (c, token)


# ══════════════════════════════════════════════════════════════════ PINTURA
def _ansi(hexa: str) -> str:
    r, g, b = int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16)
    return f"\x1b[38;2;{r};{g};{b}m"


def pintar_fila(fila: Fila, ansi: bool = True) -> str:
    if not ansi:
        return "".join(c for c, _ in fila)
    # Arranca y termina con un reset. El de atrás es higiene de color; el de adelante existe porque
    # Claude Code le hace `trim()` a cada línea antes de mostrarla (ver tests/test_consumidor.py): sin
    # él, una fila que empiece con espacio —las dos de la mascota— pierde esa columna y la escena se
    # corre respecto del piso, que empieza con tinta. ESC no es whitespace para el trim de JS, así que
    # un escape adelante protege la fila entera igual que el de atrás protege el relleno de la derecha.
    partes: list[str] = ["\x1b[0m"]
    actual = None
    for car, token in fila:
        if car != " " and token != actual:
            partes.append(_ansi(PALETA[token]))
            actual = token
        partes.append(car)
    partes.append("\x1b[0m")
    return "".join(partes)


HUECO_MIN = 2  # columnas mínimas entre la escena y el tablero (el valor histórico)


def unir(escena: Grilla, tablero: Grilla, hueco: int = HUECO_MIN) -> Grilla:
    return [e + fila_vacia(hueco) + t for e, t in zip(escena, tablero)]


def a_texto(grilla: Grilla) -> list[str]:
    return [pintar_fila(f, ansi=False) for f in grilla]


def ancho_de_grilla(grilla: Grilla) -> int:
    """Cada celda es un carácter, así que el largo de la fila es su ancho en columnas: no hace falta pintarla."""
    return max((len(f) for f in grilla), default=0)


# ══════════════════════════════════════════════════════════════════ ENTRADA
_REQUERIDO = object()  # marca de campo sin default, para _Registro


class _Registro:
    """Sustituto liviano de `@dataclass`: importar `dataclasses` arrastra `inspect`/`ast`/`dis`/`tokenize`
    (~36 ms medidos con `-X importtime`) sólo para generar `__init__`/`__eq__`/`__repr__`. `_campos` declara
    (nombre, default) en el orden del constructor; acepta posicionales y nombrados como un dataclass.
    Default `_REQUERIDO` = obligatorio; `list`/`dict` = contenedor nuevo por instancia; cualquier otro valor
    (None, "", 0, False, una constante) se copia tal cual porque es inmutable."""
    _campos: tuple[tuple[str, object], ...] = ()

    def __init__(self, *args, **kwargs):
        nombres = [n for n, _ in self._campos]
        if len(args) > len(nombres):
            raise TypeError(f"{type(self).__name__} acepta {len(nombres)} argumentos")
        for (n, _d), v in zip(self._campos, args):
            setattr(self, n, v)
        for n, d in self._campos[len(args):]:
            if n in kwargs:
                setattr(self, n, kwargs.pop(n))
            elif d is _REQUERIDO:
                raise TypeError(f"falta {n}")
            elif d is list:
                setattr(self, n, [])
            elif d is dict:
                setattr(self, n, {})
            else:
                setattr(self, n, d)
        if kwargs:
            raise TypeError(f"argumentos desconocidos: {sorted(kwargs)}")

    def __eq__(self, otro):
        return type(otro) is type(self) and all(getattr(self, n) == getattr(otro, n) for n, _ in self._campos)

    def __repr__(self):
        campos = ", ".join(f"{n}={getattr(self, n)!r}" for n, _ in self._campos)
        return f"{type(self).__name__}({campos})"


class Ventana(_Registro):
    """pct: float; reinicio: float | None (epoch segundos); esperado: float | None (el % que tocaría llevar a esta
    hora); fraccion: float | None (la parte de la ventana ya transcurrida, 0-1). Los dos últimos los pone poner_ritmo."""
    _campos = (("pct", _REQUERIDO), ("reinicio", _REQUERIDO), ("esperado", None), ("fraccion", None))


class Entrada(_Registro):
    _campos = (
        ("modelo", "Claude"),               # str
        ("esfuerzo", None),                 # str | None
        ("carpeta", "?"),                   # str
        ("worktree", None),                 # str | None
        ("pr_numero", None),                # int | None
        ("pr_estado", None),                # str | None
        ("pr_es_mr", False),                # bool
        ("contexto_pct", None),             # float | None
        ("contexto_total", 200_000),        # int
        ("cache_observada", False),         # bool
        ("cache_tibia", False),             # bool
        ("cache_aciertos", None),           # float | None
        ("cache_fallos", 0),                # int
        ("cinco_h", None),                  # Ventana | None
        ("siete_d", None),                  # Ventana | None
        ("costo", None),                    # float | None
        ("lineas", None),                   # tuple[int, int] | None
        ("transcript_path", None),          # str | None
        ("session_id", None),               # str | None
        ("valida", True),                   # bool: False si stdin no era un objeto JSON
    )


def _num(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _ventana(d) -> Ventana | None:
    if not isinstance(d, dict):
        return None
    pct = _num(d.get("used_percentage"))
    if pct is None:
        return None
    return Ventana(pct, _num(d.get("resets_at")))


def leer_entrada(crudo: bytes | str) -> Entrada:
    """Normaliza el JSON de stdin. Nunca lanza: lo que falte o esté mal queda en su default."""
    e = Entrada()
    try:
        d = json.loads(crudo)
    except Exception:
        e.valida = False
        return e
    if not isinstance(d, dict):
        e.valida = False
        return e

    def g(*ruta):
        v = d
        for k in ruta:
            if not isinstance(v, dict):
                return None
            v = v.get(k)
        return v

    try:
        e.modelo = str(g("model", "display_name") or "Claude")
        e.esfuerzo = g("effort", "level") or None
        proyecto = g("workspace", "project_dir") or g("cwd")
        if proyecto:
            e.carpeta = os.path.basename(str(proyecto).rstrip("\\/")) or str(proyecto)
        e.worktree = g("worktree", "name") or g("workspace", "git_worktree") or None
        pr = _num(g("pr", "number"))
        if pr is not None:
            e.pr_numero = int(pr)
            e.pr_estado = g("pr", "review_state") or None
            e.pr_es_mr = g("pr", "kind") == "mr"
        e.contexto_pct = _num(g("context_window", "used_percentage"))
        total = _num(g("context_window", "context_window_size"))
        if total and total > 0:
            e.contexto_total = int(total)
        e.cache_observada = bool(g("prompt_cache", "caching_observed"))
        e.cache_tibia = bool(g("prompt_cache", "warm"))
        e.cache_aciertos = _num(g("prompt_cache", "hit_ratio"))
        e.cache_fallos = int(_num(g("prompt_cache", "misses"), 0))
        e.cinco_h = _ventana(g("rate_limits", "five_hour"))
        e.siete_d = _ventana(g("rate_limits", "seven_day"))
        e.costo = _num(g("cost", "total_cost_usd"))
        mas, menos = _num(g("cost", "total_lines_added")), _num(g("cost", "total_lines_removed"))
        if mas is not None or menos is not None:
            e.lineas = (int(mas or 0), int(menos or 0))
        e.transcript_path = g("transcript_path") or None
        e.session_id = g("session_id") or None
    except Exception:
        pass
    return e


# ═══════════════════════════════════════════════════════════════ TRANSCRIPT
ESPERANDO, DORMIDO, PENSANDO, LEYENDO, ESCRIBIENDO = "esperando", "dormido", "pensando", "leyendo", "escribiendo"
EJECUTANDO, NAVEGANDO, DELEGANDO, SOBRESALTO, COMPACTANDO = "ejecutando", "navegando", "delegando", "sobresalto", "compactando"

POSE_POR_HERRAMIENTA = {
    "Read": LEYENDO, "Grep": LEYENDO, "Glob": LEYENDO,
    "Edit": ESCRIBIENDO, "Write": ESCRIBIENDO, "NotebookEdit": ESCRIBIENDO,
    "Bash": EJECUTANDO, "PowerShell": EJECUTANDO,
    "WebFetch": NAVEGANDO, "WebSearch": NAVEGANDO,
    "Agent": DELEGANDO,
}
PREFIJO_NAVEGADOR = "mcp__claude-in-chrome__"
SEGUNDOS_SOBRESALTO = 3.0
SEGUNDOS_DORMIDO = 300.0
SEGUNDOS_TRANSICION = 2.0  # ✦ al nacer, ✧ al irse, y duración de "compactando"
# Silencio tras el cual un subagente se da por terminado, cuando no llegó su notificación. Medido el
# 2026-09-17 sobre 219 subagentes reales (28.989 huecos entre entradas): el peor hueco de un agente que
# seguía trabajando es de 1105,2 s, así que 300 s daba por muertos a 6 agentes vivos y 1200 s a ninguno.
# No sube más porque el escritorio queda tomado todo ese tiempo si el amigo se fue de verdad.
SEGUNDOS_MUDO = 1200.0
CAIDA_COMPACTACION = 0.30  # fracción de la ventana


def pose_de(nombre: str) -> str:
    if nombre.startswith(PREFIJO_NAVEGADOR):
        return NAVEGANDO
    return POSE_POR_HERRAMIENTA.get(nombre, EJECUTANDO)


def leyenda_de(nombre: str, entrada: dict) -> str:
    if nombre in ("Read", "Edit", "Write", "NotebookEdit"):
        return os.path.basename(str(entrada.get("file_path") or entrada.get("notebook_path") or "").rstrip("\\/"))
    if nombre in ("Grep", "Glob"):
        return str(entrada.get("pattern") or "")
    if nombre in ("Bash", "PowerShell"):
        return str(entrada.get("description") or "")
    if nombre == "Skill":
        return str(entrada.get("skill") or "")
    if nombre == "WebFetch" or nombre.startswith(PREFIJO_NAVEGADOR):
        url = str(entrada.get("url") or "")
        return url.split("//", 1)[-1].split("/", 1)[0]
    if nombre == "WebSearch":
        return str(entrada.get("query") or "")
    return nombre


class Amigo(_Registro):
    _campos = (
        ("id", _REQUERIDO),                 # str
        ("tipo", _REQUERIDO),               # str: sufijo del token: explore | general | plan | propio | desconocido
        ("nombre", _REQUERIDO),             # str: leyenda de hasta 7 caracteres
        ("descripcion", ""),                # str
        ("modelo", ""),                     # str: alias del meta (opus | sonnet | ...) o el de la sesión si hereda
        ("pose", PENSANDO),                 # str
        ("leyenda", ""),                    # str
        ("herramienta", None),              # str | None
        ("nacido_hace", 0.0),               # float
        ("terminado_hace", None),           # float | None
        ("escritorio", 0),                  # int
    )


class Actividad(_Registro):
    _campos = (
        ("pose", ESPERANDO),                # str
        ("leyenda", ""),                    # str
        ("herramienta", None),              # str | None
        ("amigos", list),                   # list[Amigo], nueva por instancia
        ("rama", None),                     # str | None
        ("scripts", 0),                     # int: Bash de fondo vivos
        ("monitores", 0),                   # int: Monitor vivos
    )


class Analisis(_Registro):
    """Hechos crudos de una cola de transcript, sin reloj. La pose se decide aparte con `ahora`."""
    _campos = (
        ("pendientes", dict),               # dict[str, tuple[str, dict, float]]: id -> (nombre, input, ts)
        ("ultimo", "nada"),                 # str: asistente | resultado | usuario | nada
        ("ultimo_ts", 0.0),                 # float
        ("error_ts", None),                 # float | None
        ("compactacion_ts", None),          # float | None
        ("contextos", list),                # list[tuple[float, int]]: (ts, tokens de entrada) por mensaje
        ("rama", None),                     # str | None
        ("despachos", list),                # list[list]: [id, nace, termina|None, input, fondo|None] de cada Agent
    )


def _ts(o: dict) -> float:
    s = o.get("timestamp")
    if not isinstance(s, str):
        return 0.0
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


VENTANAS_COLA = (65_536, 262_144, 1_048_576)
MINIMO_ENTRADAS = 8


def _leer_ventana(ruta: str, maximo: int) -> tuple[list[dict], bool]:
    """Últimos `maximo` bytes del JSONL como objetos. Descarta la primera línea (cortada) y la última si está a
    medias. Devuelve además `quedo_corto` = había contenido antes del inicio de esta ventana."""
    try:
        with open(ruta, "rb") as f:
            f.seek(0, os.SEEK_END)
            largo = f.tell()
            inicio = max(0, largo - maximo)
            f.seek(inicio)
            datos = f.read()
    except OSError:
        return [], False
    lineas = datos.split(b"\n")
    if inicio > 0:
        lineas = lineas[1:]
    salida: list[dict] = []
    for ln in lineas:
        if not ln.strip():
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if isinstance(o, dict):
            salida.append(o)
    return salida, inicio > 0


def leer_cola(ruta: str, maximo: int | None = None) -> list[dict]:
    """Últimas entradas del JSONL. Una línea real puede superar los 64 KB (402 casos medidos, máx 1,09 MB), así que
    si la ventana chica trae menos de MINIMO_ENTRADAS se agranda (256 KB, 1 MB). `maximo` fija una sola ventana
    (tests)."""
    ventanas = (maximo,) if maximo else VENTANAS_COLA
    salida: list[dict] = []
    for ventana in ventanas:
        salida, quedo_corto = _leer_ventana(ruta, ventana)
        if len(salida) >= MINIMO_ENTRADAS or not quedo_corto:
            break
    return salida


def analizar(entradas: list[dict]) -> Analisis:
    a = Analisis()
    vistos: set = set()
    for o in entradas:
        t = o.get("type")
        ts = _ts(o)
        if o.get("gitBranch"):
            a.rama = str(o["gitBranch"])
        if t == "system":
            if o.get("subtype") == "compact_boundary":
                a.compactacion_ts = ts
            continue
        msg = o.get("message") if isinstance(o.get("message"), dict) else {}
        if t == "assistant":
            uso = msg.get("usage") or {}
            mid = msg.get("id")
            if uso and mid not in vistos:
                vistos.add(mid)
                total = sum(int(uso.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                a.contextos.append((ts, total))
            for b in msg.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    nombre, entrada = str(b.get("name") or ""), b.get("input") if isinstance(b.get("input"), dict) else {}
                    a.pendientes[str(b.get("id") or "")] = (nombre, entrada, ts)
                    if nombre == "Agent":
                        a.despachos.append([str(b.get("id") or ""), ts, None, entrada, None])
            a.ultimo, a.ultimo_ts = "asistente", ts
        elif t == "user":
            if o.get("isMeta"):
                continue
            cont = msg.get("content")
            resultados = [b for b in cont if isinstance(b, dict) and b.get("type") == "tool_result"] if isinstance(cont, list) else []
            if resultados:
                for b in resultados:
                    tid = str(b.get("tool_use_id") or "")
                    a.pendientes.pop(tid, None)
                    if b.get("is_error"):
                        a.error_ts = ts
                    for d in a.despachos:
                        if d[0] == tid and d[2] is None:
                            contenido = b.get("content")
                            if isinstance(contenido, str):
                                texto = contenido
                            elif isinstance(contenido, list):
                                texto = "".join(str(x.get("text") or "") for x in contenido
                                                 if isinstance(x, dict) and x.get("type") == "text")
                            else:
                                texto = ""
                            m = re.search(r"agentId:\s*([0-9a-f]{8,})", texto)
                            if m:
                                d[4] = m.group(1)
                            else:
                                d[2] = ts
                a.ultimo = "resultado"
            else:
                # Prompt humano nuevo: lo que estaba en curso fue interrumpido (Esc) o ya terminó.
                # Un amigo de fondo (d[4]) no se da por terminado: su fin lo decide su propio archivo.
                # Una herramienta abortada no deja rastro de su fin: sin esta limpieza quedaría
                # "en curso" para siempre.
                a.pendientes.clear()
                for d in a.despachos:
                    if d[2] is None and d[4] is None:
                        d[2] = ts
                a.ultimo = "usuario"
            a.ultimo_ts = ts
    return a


def pose_de_analisis(a: Analisis, ahora: float) -> tuple[str, str, str | None]:
    """(pose, leyenda, herramienta) por prioridad: sobresalto, compactación, herramienta en curso, reposo."""
    # El sobresalto tiene prioridad sobre la herramienta en curso durante sus 3 s, no al revés: "luego
    # vuelve al anterior" sólo tiene sentido si el sobresalto interrumpe.
    if a.error_ts is not None and 0 <= ahora - a.error_ts < SEGUNDOS_SOBRESALTO:
        return SOBRESALTO, "", None
    propias = [(n, i) for n, i, _ in a.pendientes.values() if n != "Agent"]
    if propias:
        nombre, entrada = propias[-1]
        return pose_de(nombre), leyenda_de(nombre, entrada), nombre
    if a.pendientes:
        return DELEGANDO, "··", "Agent"
    if a.ultimo in ("resultado", "usuario"):
        return PENSANDO, "", None
    if a.ultimo == "asistente" and ahora - a.ultimo_ts > SEGUNDOS_DORMIDO:
        return DORMIDO, "", None
    return ESPERANDO, "", None


def hay_compactacion(a: Analisis, ahora: float, contexto_total: int) -> bool:
    if a.compactacion_ts is not None and 0 <= ahora - a.compactacion_ts < SEGUNDOS_TRANSICION:
        return True
    if len(a.contextos) >= 2:
        (_, antes), (ts, despues) = a.contextos[-2], a.contextos[-1]
        if 0 <= ahora - ts < SEGUNDOS_TRANSICION and antes - despues > CAIDA_COMPACTACION * contexto_total:
            return True
    return False


def asignar_escritorios(despachos: list[tuple[str, float, float | None]], gracia: float = SEGUNDOS_TRANSICION) -> dict[str, int]:
    """Reproduce los despachos en orden: cada amigo toma el primer escritorio libre al nacer y lo
    conserva hasta `gracia` segundos después de terminar. Puro y determinista: no hace falta estado."""
    libre_desde: dict[int, float] = {}
    asignacion: dict[str, int] = {}
    for id_, nace, termina in despachos:
        n = 0
        while libre_desde.get(n, 0.0) > nace:
            n += 1
        asignacion[id_] = n
        libre_desde[n] = float("inf") if termina is None else termina + gracia
    return asignacion


def clase_amigo(tipo: str | None) -> str:
    if not tipo:
        return "desconocido"
    if tipo == "Explore":
        return "explore"
    if tipo in ("general-purpose", "claude"):
        return "general"
    if tipo == "Plan":
        return "plan"
    return "propio"


def nombre_amigo(tipo: str | None) -> str:
    if not tipo:
        return "?"
    if tipo == "general-purpose":
        return "general"
    return tipo.lower()[:7]


class Despacho(_Registro):
    """Un subagente censado: lo que se sabe de él antes de abrir su transcript."""
    _campos = (
        ("id", _REQUERIDO),         # str: toolUseId del despacho, con el que lo nombra el meta
        ("nace", _REQUERIDO),       # float
        ("agente", None),           # str | None: agentId; el nombre de su archivo y su <task-id>
        ("ruta", None),             # str | None: su JSONL, si ya existe
        ("tipo", None),             # str | None: agentType
        ("descripcion", ""),        # str
        ("modelo", ""),             # str: `model` del meta o del despacho; "inherit" o vacío = el de la sesión
        ("escrito", None),          # float | None: mtime de su JSONL; fiel al último timestamp de adentro
        ("termina", None),          # float | None
    )


def leer_meta(ruta: str) -> dict | None:
    """El .meta.json de un subagente. None si no se puede leer o no trae toolUseId."""
    try:
        with open(ruta, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) and m.get("toolUseId") else None


def censar_amigos(carpeta: str, ahora: float) -> list[Despacho]:
    """Quiénes hay en la oficina, según la carpeta `subagents` y NO según el transcript principal.

    El `tool_use` del despacho se escribe una sola vez y se va quedando atrás: en una sesión real de 2 MB el
    despacho de un amigo que seguía trabajando estaba a 426 KB del final, 6,5 veces fuera de la ventana de
    `leer_cola`, y la oficina se veía vacía con el amigo adentro. La carpeta no depende de la ventana.

    Abrir todos los .meta.json cuesta 7,7 ms con 40 metas (un sexto del presupuesto propio), así que primero
    se filtra por el mtime que `os.scandir` ya trae: 0,68 ms, 2 candidatos de 40 en las sesiones medidas.
    El nacimiento sale de la CREACIÓN del meta: su mtime se reescribe, y el timestamp del despacho se desvía
    hasta +1065 s porque un agente de fondo se encola y arranca cuando hay lugar."""
    try:
        entradas = list(os.scandir(carpeta))
    except OSError:
        return []
    escrito: dict[str, float] = {}
    metas: list[tuple[str, os.DirEntry]] = []
    for e in entradas:
        if e.name.endswith(".jsonl"):
            try:
                escrito[e.name[: -len(".jsonl")]] = e.stat().st_mtime
            except OSError:
                continue
        elif e.name.endswith(".meta.json"):
            metas.append((e.name[: -len(".meta.json")], e))
    salida: list[Despacho] = []
    for base, e in metas:
        mtime = escrito.get(base)
        try:
            st = e.stat()
        except OSError:
            continue
        nace = getattr(st, "st_birthtime", st.st_ctime)  # en Windows las dos son la creación
        # Un amigo del futuro pasaría la puerta de abajo por izquierda, porque la resta le da negativa. En
        # producción no hay archivos del futuro, pero sí al reproducir un instante pasado para medir el fix.
        if nace > ahora:
            continue
        if ahora - (nace if mtime is None else mtime) > SEGUNDOS_MUDO:
            continue  # mudo hace rato: no se abre siquiera
        m = leer_meta(e.path)
        if m is None:
            continue
        salida.append(Despacho(id=str(m["toolUseId"]), nace=nace, tipo=m.get("agentType"),
                               descripcion=str(m.get("description") or ""), modelo=str(m.get("model") or ""),
                               escrito=mtime,
                               agente=base[len("agent-"):] if base.startswith("agent-") else base,
                               ruta=None if mtime is None else os.path.join(carpeta, base + ".jsonl")))
    salida.sort(key=lambda d: d.nace)
    return salida


# La llave de una notificación es el `<task-id>`, que es el agentId (el nombre del archivo del subagente), y
# NO el `<tool-use-id>`: cada mensaje que el coordinador le manda al agente con `SendMessage` es un `tool_use`
# nuevo, así que la notificación trae el id del mensaje que provocó ESA parada, no el del despacho —que es el
# que guarda el `.meta.json`—. Buscando por tool-use-id sólo se ve la primera parada de cada amigo; medido en
# vivo el 2026-09-17, eso dejaba 2 escritorios encendidos de 3 con un solo agente trabajando.
RE_NOTIFICACION_ID = re.compile(r"<task-id>([^<]+)</task-id>")
RE_NOTIFICACION_ESTADO = re.compile(r"<status>([^<]+)</status>")


def _texto_de_notificacion(o: dict) -> str:
    """El XML de una <task-notification>, que llega por duplicado: como `queue-operation` (enqueue y después
    remove) y como `attachment` de tipo `queued_command`."""
    t = o.get("type")
    if t == "queue-operation":
        c = o.get("content")
    elif t == "attachment":
        c = (o.get("attachment") or {}).get("prompt")
    else:
        return ""
    return c if isinstance(c, str) and "<task-notification>" in c else ""


# Las notificaciones se buscan en su propia ventana, mucho más grande que la de `leer_cola`: la notificación
# llega en el instante en que el amigo para, pero el transcript le crece 483 KB por detrás (p90 medido sobre
# 511 notificaciones reales) en los SEGUNDOS_MUDO durante los que todavía hace falta. Con 64 KB sigue visible
# el 2%; con 1 MB, el 99%. Cuesta 0,93 ms porque son líneas chicas y el substring las filtra antes del JSON.
VENTANA_NOTIFICACIONES = 1_048_576
# Los tres estados con los que termina algo de fondo (medidos el 2026-10-25 en 2.1.310). Un agente que falla
# notifica `failed` («Agent terminated») y no vuelve a escribir; antes sólo `completed` apagaba el escritorio.
ESTADOS_FINALES = ("completed", "failed", "killed")
MARCAS_AVISO = (b"<task-notification>", b'"backgroundTaskId"', b'"timeoutMs"')
RE_TIMESTAMP = re.compile(rb'"timestamp":\s*"([^"]+)"')
# Para saber si un amigo está parado alcanza con su última entrada, que es un bloque de texto chico; si una
# línea gigante se comiera la ventana, `leer_cola` devuelve vacío y el amigo se queda, que es el lado seguro.
VENTANA_ULTIMA_ENTRADA = 65_536


class Avisos(_Registro):
    """Lo que el transcript principal dice de lo que corre de fondo, leído en una sola pasada de su cola."""
    _campos = (
        ("fines", dict),                    # dict[str, float]: agentId -> última notificación final
        ("fines_tareas", dict),             # dict[str, float]: taskId de script/monitor -> su notificación final
        ("arranques", dict),                # dict[str, tuple[str, float, float | None]]: taskId -> (tipo, ts, vence)
        ("con_eventos", dict),              # dict[str, float]: taskId de los monitores que emitieron eventos
        ("inicio", 0.0),                    # float: timestamp de la primera línea vista; 0 si se vio el archivo entero
    )


def _arranque(o: dict) -> tuple[str, str, float | None] | None:
    """(taskId, tipo, vence) si la entrada es el `tool_result` con el que nace una tarea de fondo."""
    r = o.get("toolUseResult") if o.get("type") == "user" else None
    if not isinstance(r, dict):
        return None
    if r.get("backgroundTaskId"):
        return str(r["backgroundTaskId"]), "script", None
    if r.get("taskId") and "timeoutMs" in r:
        ms = _num(r.get("timeoutMs"))
        return str(r["taskId"]), "monitor", None if r.get("persistent") or not ms else ms / 1000
    return None


def leer_avisos(ruta: str) -> Avisos:
    """Fines de amigos, arranques y fines de tareas de fondo, en la misma ventana de 1 MB. Sin el fin fino de un
    subagente su escritorio queda encendido hasta que el silencio lo apague: reproduciendo las sesiones reales daba
    2 a 3 escritorios de más por instante, con la oficina llena de amigos que ya se habían ido."""
    av = Avisos()
    try:
        with open(ruta, "rb") as f:
            f.seek(0, os.SEEK_END)
            inicio = max(0, f.tell() - VENTANA_NOTIFICACIONES)
            f.seek(inicio)
            datos = f.read()
    except OSError:
        return av
    lineas = datos.split(b"\n")
    if inicio > 0:
        lineas = lineas[1:]  # la primera quedó cortada
        for ln in lineas:
            m = RE_TIMESTAMP.search(ln)
            if m:
                av.inicio = _ts({"timestamp": m.group(1).decode("utf-8", "replace")}) or 1.0
                break
    for ln in lineas:
        if not any(marca in ln for marca in MARCAS_AVISO):
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(o, dict):
            continue
        ts = _ts(o)
        arr = _arranque(o)
        if arr is not None:
            id_, tipo, dura = arr
            av.arranques[id_] = (tipo, ts, None if dura is None else ts + dura)
            continue
        c = _texto_de_notificacion(o)
        m = RE_NOTIFICACION_ID.search(c) if c else None
        if not m:
            continue
        id_, estado = m.group(1), RE_NOTIFICACION_ESTADO.search(c)
        if estado is None:
            if "Monitor event" in c:
                av.con_eventos[id_] = ts
        elif estado.group(1) in ESTADOS_FINALES:
            destino = av.fines_tareas if RE_ID_TAREA.fullmatch(id_) else av.fines
            destino[id_] = max(destino.get(id_, 0.0), ts)
    return av


def notificaciones(ruta: str) -> dict[str, float]:
    """agentId -> instante de la última notificación final de un subagente."""
    return leer_avisos(ruta).fines


# ── tareas de fondo: scripts y monitores ───────────────────────────────
RE_ID_TAREA = re.compile(r"b[0-9a-z]{8}")  # los agentes son `a` + 16 hex: no entran
SEGUNDOS_GRACIA_MONITOR = 60.0  # el aviso de vencimiento llega con algo de atraso respecto del timeout declarado


def carpeta_tareas(ruta: str, session_id: str | None) -> str:
    """Donde Claude Code deja la salida de cada tarea: <temp>/claude/<proyecto>/<sesión>/tasks. El <proyecto> es el
    mismo nombre de carpeta que el del transcript (`E--AI-Claude-StatusBarDFR`)."""
    base = os.environ.get("CLAUDE_CODE_TMPDIR") or os.environ.get("TEMP") or os.environ.get("TMP") or ""
    return os.path.join(base, "claude", os.path.basename(os.path.dirname(ruta)), session_id or "", "tasks")


def censar_tareas(av: Avisos, carpeta: str, ahora: float) -> tuple[int, int]:
    """(scripts, monitores) vivos. El arranque se escribe una sola vez y se va quedando atrás, igual que el
    despacho de un amigo, así que la carpeta de salidas completa el censo: una salida escrita DENTRO de la ventana
    prueba que la tarea vivía entonces, y su fin, que viene después de su última escritura, estaría a la vista.

    Sólo cuentan las salidas que nacieron ANTES de la ventana: cada Bash, también el de primer plano, crea su
    `b*.output` mientras corre (medido el 2026-10-25) y lo borra al terminar. Una tarea de fondo nacida dentro de
    la ventana ya está en `arranques`; lo que nació adentro y no está ahí es un comando de primer plano."""
    vivas: dict[str, str] = {}
    for id_, (tipo, _ts_arr, vence) in av.arranques.items():
        if id_ in av.fines_tareas or (vence is not None and ahora > vence + SEGUNDOS_GRACIA_MONITOR):
            continue
        vivas[id_] = tipo
    if av.inicio > 0:  # si se vio el archivo entero, todo arranque está en `arranques`
        try:
            entradas = list(os.scandir(carpeta))
        except OSError:
            entradas = []
        for e in entradas:
            id_ = e.name[: -len(".output")] if e.name.endswith(".output") else ""
            if not RE_ID_TAREA.fullmatch(id_) or id_ in vivas or id_ in av.arranques or id_ in av.fines_tareas:
                continue
            try:
                st = e.stat()
            except OSError:
                continue
            nace = getattr(st, "st_birthtime", st.st_ctime)  # en Windows las dos son la creación
            if nace < av.inicio <= st.st_mtime:
                vivas[id_] = "monitor" if id_ in av.con_eventos else "script"
    tipos = list(vivas.values())
    return tipos.count("script"), tipos.count("monitor")


def leer_actividad(ruta: str | None, session_id: str | None, ahora: float, contexto_total: int = 200_000) -> Actividad:
    act = Actividad()
    if not ruta:
        return act
    entradas = leer_cola(ruta)
    a = analizar(entradas)
    act.pose, act.leyenda, act.herramienta = pose_de_analisis(a, ahora)
    act.rama = a.rama
    if hay_compactacion(a, ahora, contexto_total):
        act.pose, act.leyenda, act.herramienta = COMPACTANDO, "", None
    avisos = leer_avisos(ruta)
    act.scripts, act.monitores = censar_tareas(avisos, carpeta_tareas(ruta, session_id), ahora)
    dir_sub = os.path.join(os.path.dirname(ruta), session_id or "", "subagents")
    amigos = censar_amigos(dir_sub, ahora)
    _sumar_los_del_transcript(amigos, a.despachos, dir_sub)
    if not amigos:
        return act
    _poner_fines(amigos, a.despachos, avisos.fines, ahora)
    presentes = [d for d in amigos if d.termina is None or ahora - d.termina < SEGUNDOS_TRANSICION]
    if not presentes:
        return act
    asignacion = asignar_escritorios([(d.id, d.nace, d.termina) for d in amigos])
    # Sólo se abre el transcript del que va a entrar en la oficina: un fan-out real llega a 40 agentes vivos
    # a la vez, y abrir los 40 cuesta más que todo el presupuesto propio para dibujar 6.
    dibujados = max(ESCRITORIOS_POR_NIVEL.values())
    for d in presentes:
        am = Amigo(id=d.id, tipo=clase_amigo(d.tipo), nombre=nombre_amigo(d.tipo), descripcion=d.descripcion,
                   modelo=d.modelo, nacido_hace=ahora - d.nace, escritorio=asignacion[d.id],
                   terminado_hace=None if d.termina is None else ahora - d.termina)
        if d.termina is None and d.ruta and am.escritorio < dibujados:
            propias = leer_cola(d.ruta)
            if propias:  # sin líneas todavía sigue "pensando"
                am.pose, am.leyenda, am.herramienta = pose_de_analisis(analizar(propias), ahora)
        act.amigos.append(am)
    return act


def _sumar_los_del_transcript(amigos: list[Despacho], despachos: list[list], dir_sub: str) -> None:
    """Completa el censo con lo que sí se ve en el transcript principal: el amigo recién despachado, cuyo
    .meta.json puede no estar escrito todavía, y el `subagent_type`/`description` del propio despacho."""
    por_id = {d.id: d for d in amigos}
    for id_, nace, _termina, entrada, fondo in despachos:
        d = por_id.get(id_)
        if d is None:
            d = Despacho(id=id_, nace=nace)
            por_id[id_] = d
            amigos.append(d)
        d.tipo = entrada.get("subagent_type") or d.tipo
        d.descripcion = str(entrada.get("description") or "") or d.descripcion
        d.modelo = d.modelo or str(entrada.get("model") or "")  # el meta manda: es lo que de verdad corrió
        if d.ruta is None and fondo is not None:
            archivo = os.path.join(dir_sub, f"agent-{fondo}.jsonl")
            try:
                d.escrito = os.stat(archivo).st_mtime
            except OSError:
                continue  # todavía no existe: el amigo sigue "pensando"
            d.ruta = archivo
    amigos.sort(key=lambda d: d.nace)


def _esta_parado(ruta: str) -> bool:
    """True si la última entrada del subagente es una parada. Sólo vale el `stop_reason`: Claude Code escribe
    cada bloque como una línea, así que un `text` intermedio (stop_reason null) no lo es (1650 casos medidos).

    Por sí solo NO significa que el amigo terminó —70 de 218 agentes reales paran y siguen cuando el
    coordinador les manda otro mensaje—, pero sí que ahora mismo no está trabajando, y eso es justo lo que le
    falta a la notificación para ser concluyente."""
    entradas = leer_cola(ruta, maximo=VENTANA_ULTIMA_ENTRADA)
    if not entradas:
        return False
    u = entradas[-1]
    msg = u.get("message") if isinstance(u.get("message"), dict) else {}
    if u.get("type") == "assistant":
        return msg.get("stop_reason") in ("end_turn", "stop_sequence") or _es_entrega(msg)
    # Desde 2.1.310 el agente termina entregando su informe: la última entrada es el resultado de SubagentHandback.
    if u.get("type") == "user" and len(entradas) >= 2:
        previo = entradas[-2].get("message")
        return entradas[-2].get("type") == "assistant" and isinstance(previo, dict) and _es_entrega(previo)
    return False


def _es_entrega(msg: dict) -> bool:
    """True si el mensaje del asistente es la llamada a SubagentHandback con la que un subagente entrega el informe
    y termina (109 de 111 subagentes medidos en 2.1.310; los otros 2, con `end_turn`/`stop_sequence`)."""
    cont = msg.get("content")
    return isinstance(cont, list) and any(isinstance(b, dict) and b.get("type") == "tool_use"
                                          and b.get("name") == "SubagentHandback" for b in cont)


def _poner_fines(amigos: list[Despacho], despachos: list[list], fines: dict[str, float], ahora: float) -> None:
    """Cuándo se apaga cada escritorio. La notificación sola no alcanza (dice que el amigo paró, y puede ser
    reanudado) y el `end_turn` solo tampoco (70 de 218 agentes paran y siguen; y 59 de 219 no terminan nunca
    en `end_turn`). Juntos sí: notificó Y ahora mismo está parado. Como el tiempo entre una cosa y la otra no
    separa nada —de 165 escrituras posteriores a una notificación hay casos a 2 s, a 12 s y a 300 s—, lo que
    decide es el estado del archivo, no un margen."""
    del_transcript = {d[0]: d[2] for d in despachos if d[2] is not None}
    for d in amigos:
        fin = fines.get(d.agente)
        if fin is not None and d.ruta and _esta_parado(d.ruta):
            d.termina = max(fin, d.escrito or fin)
            continue
        fin = del_transcript.get(d.id)
        if fin is not None:
            d.termina = fin
            continue
        if d.escrito is not None and ahora - d.escrito > SEGUNDOS_MUDO:
            d.termina = d.escrito


# ═══════════════════════════════════════════════════════════════════ ESCENA
ANCHO_CLAWD = 22
# Clawd es una caja: sólo glifos de celda entera. Con bloques (▛ ▜ ▐ ▌) el ojo únicamente puede ser
# una muesca en la esquina de la celda, así que la cara queda pegada al borde de abajo de la cabeza
# y el dibujo se lee deforme; además las medias celdas corren la cabeza. El box-drawing empalma
# entre celdas por diseño y deja poner el ojo donde se quiera.
CABEZA = {  # 7 celdas desde idx 1; `─` en lugar del ojo es el párpado cerrado
    ESPERANDO: ["╭─◉─◉─╮", "╭─◉─◉─╮", "╭─◉─◉─╮", "╭─────╮"],
    DORMIDO: ["╭─────╮"],
    PENSANDO: ["╭─◉◉──╮"],
    SOBRESALTO: ["╭─◎─◎─╮"],
    COMPACTANDO: ["╭─◉─◉─╮"],
}
CABEZA_HERRAMIENTA = ["╭──◉◉─╮"]  # mira al otro lado que pensando: hacia la tableta
PATAS = {  # (cuerpo, pies), 7 celdas desde idx 1; el `┬` del cuerpo empalma con el `┻` del piso
    "parado": [("╰─┬─┬─╯", "  ┻ ┻  ")],
    "agachado": [("╰─────╯", "  ┻ ┻  ")],  # sentado: recoge las patas SIN mover los pies
    "salto": [("╰┬───┬╯", " ┻   ┻ "), ("╰─┬─┬─╯", "  ┻ ┻  ")],
}
PATAS_POR_POSE = {DORMIDO: "agachado", COMPACTANDO: "agachado", ESCRIBIENDO: "salto"}
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧"
ANCHO_LEYENDA_CLAWD = 11  # arranca en la columna 10 y deja libre la 21, la última: aire antes del primer amigo


class Humor(_Registro):
    _campos = (
        ("sudor", 0),                       # int
        ("cafe", None),                     # str | None
        ("reloj", None),                    # str | None
    )


def humor_de(e: Entrada) -> Humor:
    h = Humor()
    if e.contexto_pct is not None:
        h.sudor = 2 if e.contexto_pct >= 90 else 1 if e.contexto_pct >= 75 else 0
    if e.cache_observada:
        h.cafe = "tibio" if e.cache_tibia else "frio"
    if e.cinco_h is not None:
        h.reloj = "critico" if e.cinco_h.pct >= 95 else "aviso" if e.cinco_h.pct >= 85 else None
    return h


def glifo_tableta(pose: str, herramienta: str | None, seg: int) -> Celda | None:
    if pose == LEYENDO:
        return ("󰈙" if herramienta == "Read" else "󰍉", "texto principal")
    if pose == ESCRIBIENDO:
        return ("󰏫", "texto principal")
    if pose == EJECUTANDO:
        return (SPINNER[seg % len(SPINNER)], "texto principal")
    if pose == NAVEGANDO:
        return ("󰖟", "texto principal")
    if pose == SOBRESALTO:
        return ("󰀦", "critico")
    if pose == COMPACTANDO:
        return ("󰃢", "texto principal")
    return None


def _tableta(fila: Fila, col: int, celda: Celda | None) -> None:
    if celda is None:
        return
    fila[col] = ("▕", "texto secundario")
    fila[col + 1] = celda
    fila[col + 2] = ("▏", "texto secundario")


def leyenda_clawd(act: Actividad, seg: int) -> str:
    if act.pose == PENSANDO:
        return "·" * (seg % 3 + 1)
    if act.pose == DELEGANDO:
        return "··"
    if act.pose == COMPACTANDO:
        return "compactando"
    if act.pose in (ESPERANDO, DORMIDO, SOBRESALTO):
        return ""
    return act.leyenda[:ANCHO_LEYENDA_CLAWD]


def escritorio_clawd(act: Actividad, humor: Humor, seg: int) -> Grilla:
    cabeza = CABEZA.get(act.pose, CABEZA_HERRAMIENTA)
    f1 = fila_vacia(ANCHO_CLAWD)
    poner(f1, 1, cabeza[seg % len(cabeza)], "mascota")
    if act.pose == DORMIDO:
        f1[8] = ("󰒲", "texto secundario")
    elif act.pose == COMPACTANDO:
        f1[8] = ("✦", "lampara encendida")
    elif humor.sudor >= 1:
        f1[8] = ("󰖌", "frio")
        if humor.sudor >= 2:
            f1[9] = ("󰖌", "frio")
    poner(f1, 10, leyenda_clawd(act, seg), "texto principal")

    patas = PATAS[PATAS_POR_POSE.get(act.pose, "parado")]
    cuerpo, pies = patas[seg % len(patas)]

    f2 = fila_vacia(ANCHO_CLAWD)
    poner(f2, 1, cuerpo, "mascota")
    _tableta(f2, 9, glifo_tableta(act.pose, act.herramienta, seg))
    if humor.cafe == "tibio":
        f2[12] = ("󰅶", "mascota")
    elif humor.cafe == "frio":
        f2[12] = ("󰛊", "frio")
    if humor.reloj:
        f2[14] = ("󰔟", humor.reloj)

    f3 = texto("━" * ANCHO_CLAWD, "piso")
    for i, c in enumerate(pies):
        if c != " ":
            f3[1 + i] = (c, "mascota")
    return [f1, f2, f3]


ESCRITORIOS_POR_NIVEL = {-1: 6, 0: 4, 1: 4, 2: 3, 3: 2, 4: 0}
ANCHO_ESCRITORIO = {-1: 13, 0: 13, 1: 10, 2: 10, 3: 10, 4: 0}
ANCHO_ESCRITORIO_MAX = 20  # tope del ensanchado elástico: 14 columnas de texto (20 - 6) alcanzan para nombre y
# leyenda. El tope es el mismo en todos los niveles a propósito — el ancho del escritorio no es consciente
# del nivel —, aunque sólo nivel <= 0 dibuja leyenda (con_leyenda en escritorio_amigo): en 1, 2 y 3 ensanchar
# sólo separa las lámparas sobre piso vacío, así que el motivo de las 14 columnas no siempre aplica.
LAMPARA_EN = 9  # columna de la lámpara (fila 2) y del poste (fila 3) dentro del escritorio
CABEZA_AMIGO = {  # la misma caja que Clawd, en 5 celdas
    ESPERANDO: ["╭◉─◉╮", "╭◉─◉╮", "╭◉─◉╮", "╭───╮"],
    DORMIDO: ["╭───╮"],
    PENSANDO: ["╭◉◉─╮"],
    SOBRESALTO: ["╭◎─◎╮"],
    COMPACTANDO: ["╭◉─◉╮"],
}
CABEZA_AMIGO_HERRAMIENTA = ["╭─◉◉╮"]
PATAS_AMIGO = {  # (cuerpo, pies); el cuerpo va en la fila 2 y los pies en el piso del escritorio
    "parado": [("╰┬─┬╯", " ┻ ┻ ")],
    "salto": [("╰┬─┬╯", " ┻ ┻ "), ("╰─┬─╯", "  ┻  ")],
}
TEXTO_EN_ESCRITORIO = 6  # el texto del amigo arranca acá; la figura ocupa las columnas 0-4


def ancho_escena(nivel: int, ancho_escritorio: int | None = None) -> int:
    if ancho_escritorio is None:
        ancho_escritorio = ANCHO_ESCRITORIO[nivel]
    return ANCHO_CLAWD + ESCRITORIOS_POR_NIVEL[nivel] * ancho_escritorio


def escritorio_amigo(am: Amigo | None, seg: int, ancho: int, con_leyenda: bool, extra: int = 0) -> Grilla:
    f1, f2 = fila_vacia(ancho), fila_vacia(ancho)
    f3 = texto("━" * ancho, "piso")
    f3[LAMPARA_EN] = ("┻", "apagado")  # el tallo sube del piso a la lámpara, que está en la fila de arriba
    encendida = am is not None or extra > 0
    f2[LAMPARA_EN] = ("󰥟", "lampara encendida" if encendida else "lampara apagada")
    if extra > 0:
        poner(f1, 0, f"+{extra}", "texto principal")
        return [f1, f2, f3]
    if am is None:
        return [f1, f2, f3]
    if am.nacido_hace < SEGUNDOS_TRANSICION:
        f2[2] = ("✦", "lampara encendida")
        return [f1, f2, f3]
    if am.terminado_hace is not None:
        f2[2] = ("✧", "lampara encendida")
        return [f1, f2, f3]
    tok = f"amigo {am.tipo}"
    s = seg + sum(map(ord, am.id))  # desfase estable por amigo (hash() se aleatoriza por proceso)
    cabeza = CABEZA_AMIGO.get(am.pose, CABEZA_AMIGO_HERRAMIENTA)
    poner(f1, 0, cabeza[s % len(cabeza)], tok)
    if con_leyenda:
        # la letra de su modelo y su encargo; la última columna queda libre: sin ella el texto se pega a la
        # cabeza del escritorio vecino
        letra = letra_modelo(am.modelo)
        etiqueta = (letra + " " if letra else "") + (am.descripcion or am.nombre)
        poner(f1, TEXTO_EN_ESCRITORIO, etiqueta[:max(0, ancho - TEXTO_EN_ESCRITORIO - 1)], "texto principal")
        if letra and ancho - TEXTO_EN_ESCRITORIO - 1 > 0:
            f1[TEXTO_EN_ESCRITORIO] = (letra, token_modelo(am.modelo))
    patas = PATAS_AMIGO["salto" if am.pose == ESCRIBIENDO else "parado"]
    cuerpo, pies = patas[s % len(patas)]
    for i, c in enumerate(cuerpo):
        if c != " ":
            f2[i] = (c, tok)
    for i, c in enumerate(pies):
        if c != " ":
            f3[i] = (c, tok)
    _tableta(f2, 5, glifo_tableta(am.pose, am.herramienta, s))
    return [f1, f2, f3]


ICONO_SCRIPT = "󰆍"   # md-console U+F018D
ICONO_MONITOR = "󱎴"  # md-monitor_eye U+F13B4


def escritorio_tareas(scripts: int, monitores: int, seg: int, ancho: int) -> Grilla:
    """El escritorio de lo que corre de fondo sin ser un amigo: una pantalla en su pie, con la lámpara encendida.
    Arriba, un ícono por clase y un contador cuando hay más de una."""
    f1, f2 = fila_vacia(ancho), fila_vacia(ancho)
    f3 = texto("━" * ancho, "piso")
    partes = [icono + (str(n) if n > 1 else "") for icono, n in ((ICONO_SCRIPT, scripts), (ICONO_MONITOR, monitores)) if n]
    poner(f1, 0, " ".join(partes), "texto principal")
    _tableta(f2, 0, (SPINNER[seg % len(SPINNER)], "texto principal"))
    f3[1] = ("┻", "apagado")
    f2[LAMPARA_EN] = ("󰥟", "lampara encendida")
    f3[LAMPARA_EN] = ("┻", "apagado")
    return [f1, f2, f3]


def dibujar_escena(act: Actividad, humor: Humor, seg: int, nivel: int, ancho_escritorio: int | None = None) -> Grilla:
    g = escritorio_clawd(act, humor, seg)
    n = ESCRITORIOS_POR_NIVEL[nivel]
    ancho = ANCHO_ESCRITORIO[nivel] if ancho_escritorio is None else ancho_escritorio
    if n == 0:
        return g
    tareas = act.scripts > 0 or act.monitores > 0
    n_amigos = n - 1 if tareas else n  # las tareas toman el último escritorio y los amigos se aprietan
    por_escritorio = {am.escritorio: am for am in act.amigos}
    desbordados = sum(1 for am in act.amigos if am.escritorio >= n_amigos)
    for k in range(n_amigos):
        am, extra = por_escritorio.get(k), 0
        if k == n_amigos - 1 and desbordados:
            extra, am = desbordados + (1 if am else 0), None
        d = escritorio_amigo(am, seg, ancho, con_leyenda=(nivel <= 0), extra=extra)
        g = [gf + df for gf, df in zip(g, d)]
    if tareas:
        g = [gf + df for gf, df in zip(g, escritorio_tareas(act.scripts, act.monitores, seg, ancho))]
    return g


# ══════════════════════════════════════════════════════════════════ TABLERO
UMBRAL_AUTOCOMPACT_PCT = 84  # 200000 - min(32000, 20000) - 13000 = 167000 tokens = 83.5 % (umbral de autocompactación de Claude Code)
TORTAS = "󰪞󰪟󰪠󰪡󰪢󰪣󰪤󰪥"
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
SEPARADOR = "   "
ICONO_CACHE = "󱐋"  # md-lightning_bolt U+F140B: el disco (md-database) se leía como almacenamiento
ESTADO_PR = {"approved": "bien", "changes_requested": "critico", "pending": "aviso", "draft": "texto secundario"}


def token_medidor(pct: float, aviso: float, critico: float) -> str:
    return "critico" if pct >= critico else "aviso" if pct >= aviso else "texto principal"


def torta(pct: float) -> str:
    if pct <= 0:
        return "○"
    return TORTAS[min(len(TORTAS), max(1, math.ceil(pct / 12.5))) - 1]


def barra_contexto(pct: float, umbral: float, celdas: int, token: str) -> Fila:
    llenas = round(pct * celdas / 100)
    fila = [("█", token) if i < llenas else ("░", "apagado") for i in range(celdas)]
    fila[min(celdas - 1, int(umbral * celdas / 100))] = ("┆", "texto secundario")
    return fila


def _bloques(bloques: list[Fila | None]) -> Fila:
    fila: Fila = []
    for b in bloques:
        if not b:
            continue
        if fila:
            fila += texto(SEPARADOR, "apagado")
        fila += b
    return fila


def _pct(pct: float) -> str:
    return f"{round(pct):>3}%"


def _costo(c: float) -> str:
    """Siempre 5 caracteres: se bajan los decimales hasta que entre (2 → 1 → 0)."""
    s = f"{c:>5.0f}"
    for decimales in (2, 1, 0):
        s = f"{c:>5.{decimales}f}"
        if len(s) <= 5:
            return s
    return s[-5:]


FAMILIAS = ("opus", "sonnet", "haiku", "fable")


def token_modelo(modelo: str) -> str:
    m = modelo.lower()
    return next((f"modelo {f}" for f in FAMILIAS if f in m), "texto principal")


def letra_modelo(modelo: str) -> str:
    """La inicial de la familia («O» de Opus); vacía si no es una conocida."""
    m = modelo.lower()
    return next((f[0].upper() for f in FAMILIAS if f in m), "")


def heredar_modelo(act: Actividad, modelo_sesion: str) -> None:
    """Un amigo sin modelo propio (`inherit`, o sin `model` en el meta ni en el despacho) corre con el de la sesión."""
    for am in act.amigos:
        if not letra_modelo(am.modelo):
            am.modelo = modelo_sesion


def token_esfuerzo(esfuerzo: str, modelo: str = "") -> str:
    familia = token_modelo(modelo)
    familia = familia[len("modelo "):] + " " if familia.startswith("modelo ") else ""
    tok = f"esfuerzo {familia}{str(esfuerzo).lower()}"
    return tok if tok in PALETA else "texto principal"


def bloques_identidad(e: Entrada, act: Actividad, nivel: int) -> list[Fila | None]:
    modelo = texto(e.modelo, token_modelo(e.modelo))
    if e.esfuerzo and nivel <= 1:
        modelo += texto(" · 󰧑 ", "texto secundario") + texto(e.esfuerzo, token_esfuerzo(e.esfuerzo, e.modelo))
    carpeta = texto("󰉋 ", "texto secundario") + texto(e.carpeta, "texto principal")
    rama = pr = None
    if nivel <= 2:
        nombre = e.worktree or act.rama
        if nombre:
            rama = texto("󰘬 ", "texto secundario") + texto(nombre, "texto principal")
        if e.pr_numero is not None:
            pr = texto(" ", "texto secundario") + texto(("!" if e.pr_es_mr else "#") + str(e.pr_numero),
                                                         ESTADO_PR.get(e.pr_estado or "", "texto principal"))
    lineas = None  # lo que cambió esta sesión va con la identidad: la fila de las ventanas ya no tiene lugar
    if e.lineas is not None and nivel <= 0:
        lineas = (texto("+", "texto secundario") + texto(str(e.lineas[0]), "texto principal")
                  + texto(" −", "texto secundario") + texto(str(e.lineas[1]), "texto principal"))
    return [modelo, carpeta, rama, pr, lineas]


def fila_identidad(e: Entrada, act: Actividad, nivel: int) -> Fila:
    return _bloques(bloques_identidad(e, act, nivel))


def bloques_contexto(e: Entrada, nivel: int) -> list[Fila | None]:
    ctx = cache = None
    if e.contexto_pct is not None:
        tok = token_medidor(e.contexto_pct, 75, 90)
        ctx = texto("󰃥 ", "texto secundario")
        if nivel <= 3:
            ctx += barra_contexto(e.contexto_pct, UMBRAL_AUTOCOMPACT_PCT, 20 if nivel <= 2 else 10, tok) + texto(" ", "apagado")
        ctx += texto(_pct(e.contexto_pct), tok)
    if e.cache_observada and e.cache_aciertos is not None:
        cache = texto(ICONO_CACHE + " ", "texto secundario") + texto(_pct(e.cache_aciertos * 100), "texto principal")
        if e.cache_fallos > 0 and nivel <= 1:
            cache += texto(f" · {e.cache_fallos} fallos", "texto secundario")
    return [ctx, cache, _bloque_costo(e, nivel) if nivel <= NIVEL_MAX_ESPERADO else None]


def fila_contexto(e: Entrada, nivel: int) -> Fila:
    return _bloques(bloques_contexto(e, nivel))


DURACION_5H = 5 * 3600.0
DURACION_7D = 7 * 86400.0
# Márgenes del ritmo, como uso real sobre el esperado a esta hora (los «estrictos», elegidos el 2026-10-25).
RITMO_BAJO, RITMO_BIEN, RITMO_AVISO = 0.90, 1.05, 1.20
FRACCION_MINIMA_RITMO = 0.10  # antes, el esperado está tan cerca de cero que cualquier uso parece un exceso
# Hasta acá se escribe el esperado. La fila de las ventanas era la más ancha del tablero (63 de 63 columnas a 165) y
# el esperado le suma 12, así que en esos niveles el costo se muda a la fila del contexto y las líneas a la de la
# identidad; más plegado no hay lugar para el esperado y el costo vuelve a su fila, donde sobra.
NIVEL_MAX_ESPERADO = 0  # en el 1 la fila del contexto, con fallos de 2 cifras, se pasaba por una columna


def poner_ritmo(v: Ventana | None, duracion: float, ahora: float) -> None:
    """Cuánto tocaría llevar consumido a esta hora si el uso fuera parejo hasta el reinicio."""
    if v is None or v.reinicio is None:
        return
    fraccion = min(1.0, max(0.0, 1 - (v.reinicio - ahora) / duracion))
    v.fraccion, v.esperado = fraccion, fraccion * 100


def token_ritmo(pct: float, esperado: float, fraccion: float) -> str:
    if fraccion < FRACCION_MINIMA_RITMO:
        return "bien"
    r = pct / esperado
    return ("ritmo bajo" if r < RITMO_BAJO else "bien" if r <= RITMO_BIEN
            else "aviso" if r <= RITMO_AVISO else "critico")


# nombre distinto de _ventana (ENTRADA) para no pisarlo a nivel de módulo
def _ventana_fila(v: Ventana | None, etiqueta: str, nivel: int, con_dia: bool) -> Fila | None:
    if v is None:
        return None
    if v.esperado is None or v.fraccion is None:
        tok = token_medidor(v.pct, 70, 90)
    else:
        tok = token_ritmo(v.pct, v.esperado, v.fraccion)
    f = texto(torta(v.pct) + " ", tok) + texto(etiqueta + " ", "texto secundario") + texto(_pct(v.pct), tok)
    if v.esperado is not None and nivel <= NIVEL_MAX_ESPERADO:
        f += texto(f" ({round(v.esperado)}%)", "texto secundario")
    if v.reinicio is not None and nivel <= 1:
        try:
            lt = time.localtime(v.reinicio)
        except (OSError, OverflowError, ValueError):
            # un resets_at fuera de rango (p. ej. epoch en milisegundos) no debe tirar todo el tablero
            # al respaldo por un campo opcional: se omite sólo la parte "↻".
            return f
        hora = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
        if con_dia:
            cuando = DIAS[lt.tm_wday] + ("" if nivel == 1 else " " + hora)
        else:
            cuando = hora
        f += texto(" ↻ ", "texto secundario") + texto(cuando, "texto principal")
    return f


def bloques_ventanas(e: Entrada, nivel: int) -> list[Fila | None]:
    cinco = _ventana_fila(e.cinco_h, "5 h", nivel, con_dia=False)
    siete = _ventana_fila(e.siete_d, "7 d", nivel, con_dia=True)
    return [cinco, siete, _bloque_costo(e, nivel) if nivel > NIVEL_MAX_ESPERADO else None]


def fila_ventanas(e: Entrada, nivel: int) -> Fila:
    return _bloques(bloques_ventanas(e, nivel))


def _bloque_costo(e: Entrada, nivel: int) -> Fila | None:
    return texto("$" + _costo(e.costo), "texto principal") if e.costo is not None and nivel <= 3 else None


def _emparejar(filas: list[list[Fila | None]]) -> Grilla:
    """El último bloque de cada fila se corre hasta el borde de la más ancha, y el aire se junta justo antes de
    él: así el tablero tiene los dos bordes parejos sin mover nada más. Una fila de un solo bloque no tiene
    dónde juntar el aire y se queda a la izquierda."""
    naturales = [_bloques(f) for f in filas]
    borde = max((len(f) for f in naturales), default=0)
    grilla = []
    for bloques, natural in zip(filas, naturales):
        presentes = [b for b in bloques if b]
        if len(presentes) < 2:
            grilla.append(natural)
            continue
        ultimo = presentes[-1]
        grilla.append(natural[:-len(ultimo)] + fila_vacia(borde - len(natural)) + ultimo)
    return grilla


def dibujar_tablero(e: Entrada, act: Actividad, nivel: int) -> Grilla:
    return _emparejar([bloques_identidad(e, act, nivel), bloques_contexto(e, nivel), bloques_ventanas(e, nivel)])


# ══════════════════════════════════════════════════════════════════ PLEGADO
# Los peldaños de 170 y 200 que se habían esbozado eran para el rastro (B) y para Clawd caminando (C):
# cada proyecto declara el suyo cuando se diseñe, para no apartar espacio para contenido que no existe.
NIVELES = ((165, -1), (140, 0), (120, 1), (100, 2), (85, 3), (0, 4))


def elegir_nivel(ancho: int) -> int:
    for minimo, nivel in NIVELES:
        if ancho >= minimo:
            return nivel
    return 4


def repartir_sobrante(ancho: int, nivel: int, ancho_tablero: int) -> tuple[int, int]:
    """Reparte las columnas que sobran una vez elegido el nivel, por la lista de prioridad de la sección 3
    del diseño: primero ensancha los escritorios en partes iguales hasta ANCHO_ESCRITORIO_MAX, y el hueco
    entre escena y tablero se come el resto (incluido el resto de la división entera). El hueco va último
    a propósito: es el sumidero que garantiza cero columnas muertas a cualquier ancho. Aritmética pura.
    `ancho_tablero` se mide, no se declara: depende del contenido (la rama, el costo), no del nivel."""
    base, n = ANCHO_ESCRITORIO[nivel], ESCRITORIOS_POR_NIVEL[nivel]
    sobrante = ancho - (ancho_escena(nivel) + HUECO_MIN + ancho_tablero)
    extra = min(sobrante // n, ANCHO_ESCRITORIO_MAX - base) if sobrante > 0 and n else 0
    ancho_escritorio = base + extra
    return ancho_escritorio, max(HUECO_MIN, ancho - (ANCHO_CLAWD + n * ancho_escritorio) - ancho_tablero)


def _ancho_terminal() -> int | None:
    """En el hijo que lanza Claude Code sólo COLUMNS (que pone Claude Code) trae el
    ancho vivo; os.get_terminal_size falla con WinError 6 y CONOUT$ devuelve un valor fijo. shutil se
    evitó a propósito: su import arrastra bz2/lzma/zlib y cuesta decenas de ms."""
    try:
        columnas = int(os.environ.get("COLUMNS", ""))
    except ValueError:
        return None
    return columnas if columnas > 0 else None


MARGEN_UI = 2 * 2
"""Columnas que Claude Code se queda para sí: dibuja la status line dentro de un contenedor con
`paddingX` 2, y para sus propias filas calcula `rowWidth = ancho - 2*_se` con `var _se=2` (2.1.274).
`COLUMNS` trae el ancho de la terminal, no el pintable, así que hay que descontarlo a mano o la línea
se sale por la derecha a cualquier ancho de ventana y Ink la trunca con un `…`."""


def ancho_consola() -> int:
    """El ancho ÚTIL, que es lo que el layout necesita: la terminal menos lo que se queda la UI."""
    ancho = _ancho_terminal()
    if ancho:
        return max(1, ancho - MARGEN_UI)
    try:
        return max(1, int(os.environ.get("COLUMNS", "")) - MARGEN_UI)
    except ValueError:
        return 120 - MARGEN_UI


# ═════════════════════════════════════════════════════════════════════ MAIN
def respaldo(modelo: str, carpeta: str) -> Fila:
    return texto(f"{modelo}  ", "texto principal") + texto("󰉋 ", "texto secundario") + texto(carpeta, "texto principal")


def componer(e: Entrada, act: Actividad, seg: int, nivel: int,
             ancho_escritorio: int | None = None, hueco: int = HUECO_MIN) -> Grilla:
    return unir(dibujar_escena(act, humor_de(e), seg, nivel, ancho_escritorio),
                dibujar_tablero(e, act, nivel), hueco)


def componer_que_entre(e: Entrada, act: Actividad, seg: int, ancho: int) -> Grilla:
    """El nivel lo fija el ancho de la terminal (estable), nunca el contenido: a 1 fps un cambio de nivel
    por una rama más larga se lee como parpadeo. La variación de contenido la absorbe el elástico, y el
    bucle de abajo queda como red de seguridad contra el desborde (139 columnas medidas con "master"; una
    rama larga lo pasa de 140-150). Se compone acá en vez de llamar a componer() para dibujar el tablero
    una sola vez: su ancho medido es lo que come el hueco."""
    nivel = elegir_nivel(ancho)
    while True:
        tablero = dibujar_tablero(e, act, nivel)
        ancho_escritorio, hueco = repartir_sobrante(ancho, nivel, ancho_de_grilla(tablero))
        grilla = unir(dibujar_escena(act, humor_de(e), seg, nivel, ancho_escritorio), tablero, hueco)
        if nivel >= 4 or ancho_de_grilla(grilla) <= ancho:
            return grilla
        nivel += 1


def correr(crudo: bytes, ahora: float, ancho: int) -> str:
    e = Entrada()
    try:
        e = leer_entrada(crudo)
        if not e.valida:
            return pintar_fila(respaldo(e.modelo, e.carpeta))
        poner_ritmo(e.cinco_h, DURACION_5H, ahora)
        poner_ritmo(e.siete_d, DURACION_7D, ahora)
        act = leer_actividad(e.transcript_path, e.session_id, ahora, e.contexto_total)
        heredar_modelo(act, e.modelo)
        grilla = componer_que_entre(e, act, int(ahora), ancho)
        return "\n".join(pintar_fila(f) for f in grilla)
    except Exception:
        return pintar_fila(respaldo(e.modelo, e.carpeta))


def escribir(s: str) -> None:
    sys.stdout.buffer.write(s.encode("utf-8"))
    sys.stdout.buffer.flush()


def main() -> None:
    sys.stderr = open(os.devnull, "w")  # nunca ruido en stderr
    ahora = time.time()
    crudo = sys.stdin.buffer.read()
    escribir(correr(crudo, ahora, ancho_consola()) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            sys.stdout.buffer.write(b"Claude\n")
        except Exception:
            pass
