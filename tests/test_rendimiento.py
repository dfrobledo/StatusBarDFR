import json
import os
import statistics
import subprocess
import sys
import time

import pytest

from conftest import RAIZ, T0, escribir_jsonl, tool_result, tool_use
from test_entrada import COMPLETO


def armar(tmp_path):
    ruta = tmp_path / "grande.jsonl"
    bloque = []
    for i in range(40):
        bloque.append(tool_use(f"t{i}", "Read", {"file_path": f"archivo{i}.py"}, T0 - 1000 + i))
        r = tool_result(f"t{i}", T0 - 999 + i)
        r["message"]["content"][0]["content"] = "x" * 4000
        bloque.append(r)
    lineas = [json.dumps(o) for o in bloque]
    with open(ruta, "w", encoding="utf-8") as f:
        escrito = 0
        while escrito < 5 * 1024 * 1024:
            for ln in lineas:
                f.write(ln + "\n")
                escrito += len(ln) + 1
        for k in range(6):
            f.write(json.dumps(tool_use(f"ag{k}", "Agent", {"subagent_type": "Explore", "description": f"Amigo {k}"}, T0 - 20 + k)) + "\n")
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    for k in range(6):
        (sub / f"agent-{k}.meta.json").write_text(json.dumps({"agentType": "Explore", "toolUseId": f"ag{k}"}), encoding="utf-8")
        escribir_jsonl(sub / f"agent-{k}.jsonl", bloque[:20] + [tool_use(f"g{k}", "Grep", {"pattern": "pose"}, T0 - 2)])
    return json.dumps(dict(COMPLETO, transcript_path=str(ruta), session_id="s1")).encode()


# Cuántas veces se corre el script para estimar su piso. El umbral de abajo tiene ~5 ms de margen real, y
# el estimador (mínimo de N corridas de subproceso, menos el mínimo del intérprete) oscila ~8-10 ms cuando la
# máquina está cargada — por ejemplo con el resto de la suite corriendo antes. Con 5 corridas el test fallaba
# de manera intermitente SIN que el código hubiera cambiado: medido el 2026-09-17, el mismo binario daba
# 39-40 ms corrido solo y 48 ms dentro de la suite. Subir la muestra no afloja el invariante —el umbral sigue
# en 45— sino que acerca el estimador al piso que dice medir.
CORRIDAS = 11


@pytest.mark.rendimiento
def test_corrida_completa_bajo_100_ms(tmp_path):
    entrada = armar(tmp_path)
    entorno = {**os.environ, "COLUMNS": "202"}
    tiempos = []
    for _ in range(CORRIDAS):
        t = time.perf_counter()
        r = subprocess.run([sys.executable, str(RAIZ / "statusline.py")], input=entrada,
                            capture_output=True, timeout=10, env=entorno)
        tiempos.append((time.perf_counter() - t) * 1000)
        assert r.returncode == 0 and r.stderr == b""
        assert r.stdout.decode("utf-8").count("\n") == 3
        assert "Amigo" not in r.stdout.decode("utf-8")  # la descripción no se dibuja
    assert statistics.median(tiempos) < 100, f"mediana {statistics.median(tiempos):.0f} ms, corridas {tiempos}"

    base = []
    for _ in range(CORRIDAS):
        t = time.perf_counter()
        subprocess.run([sys.executable, "-c", "pass"], capture_output=True, timeout=10)
        base.append((time.perf_counter() - t) * 1000)
    # `propio` mide un piso, no una mediana: los dos lados de la resta usan el mínimo (el mejor caso, sin
    # ruido de scheduler ni de caché fría), tanto la corrida real como la base del intérprete. Restar la
    # mediana de la corrida real (ruidosa: una sola corrida lenta la infla) del mínimo del intérprete
    # (limpio) mezclaba magnitudes que no eran comparables y hacía que "propio" leyera de más sin que el
    # código hubiera cambiado. El total (assert de arriba) sí sigue midiéndose con mediana: ahí lo que
    # importa es la experiencia típica del usuario, no el piso del código.
    # Margen medido (no re-correr para actualizar esto: son cifras de una corrida ya hecha, no un umbral):
    # tiempo propio 39.4 / 40.6 / 39.5 ms a COLUMNS 202 / 140 / 100, piso del intérprete 26.8 ms, contra el
    # umbral de 45 ms — unos 6 ms de margen real, no los 45 del umbral.
    propio = min(tiempos) - min(base)
    assert propio < 45, (
        f"tiempo propio {propio:.0f} ms (mínimo corrida {min(tiempos):.0f} ms, "
        f"mediana total {statistics.median(tiempos):.0f} ms, mínimo intérprete {min(base):.0f} ms)"
    )
