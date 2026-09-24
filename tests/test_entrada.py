import json

from conftest import sl

COMPLETO = {
    "session_id": "abc", "transcript_path": "C:\\t\\abc.jsonl",
    "model": {"id": "claude-opus-5", "display_name": "Opus 5"},
    "effort": {"level": "xhigh"},
    "workspace": {"project_dir": "E:\\AI\\Claude\\StatusBarDFR", "current_dir": "E:\\AI\\Claude\\StatusBarDFR"},
    "pr": {"number": 12, "url": "u", "review_state": "approved"},
    "context_window": {"context_window_size": 200000, "used_percentage": 41.4},
    "prompt_cache": {"warm": True, "caching_observed": True, "hit_ratio": 0.784, "misses": 2},
    "rate_limits": {"five_hour": {"used_percentage": 58, "resets_at": 1800010000},
                    "seven_day": {"used_percentage": 27, "resets_at": 1800300000}},
    "cost": {"total_cost_usd": 4.2, "total_lines_added": 312, "total_lines_removed": 18},
}


def test_json_completo():
    e = sl.leer_entrada(json.dumps(COMPLETO))
    assert (e.modelo, e.esfuerzo, e.carpeta) == ("Opus 5", "xhigh", "StatusBarDFR")
    assert (e.pr_numero, e.pr_estado, e.pr_es_mr) == (12, "approved", False)
    assert (e.contexto_pct, e.contexto_total) == (41.4, 200000)
    assert (e.cache_observada, e.cache_tibia, e.cache_aciertos, e.cache_fallos) == (True, True, 0.784, 2)
    assert (e.cinco_h.pct, e.cinco_h.reinicio) == (58, 1800010000)
    assert (e.siete_d.pct, e.siete_d.reinicio) == (27, 1800300000)
    assert (e.costo, e.lineas) == (4.2, (312, 18))
    assert (e.transcript_path, e.session_id) == ("C:\\t\\abc.jsonl", "abc")


def test_json_vacio_da_defaults():
    e = sl.leer_entrada(b"{}")
    assert (e.modelo, e.esfuerzo, e.carpeta, e.worktree) == ("Claude", None, "?", None)
    assert e.contexto_pct is None and e.contexto_total == 200000
    assert e.cinco_h is None and e.siete_d is None and e.costo is None and e.lineas is None
    assert e.cache_observada is False and e.cache_aciertos is None


def test_json_invalido_no_lanza():
    e = sl.leer_entrada(b"{no es json")
    assert e.modelo == "Claude"


def test_valida_marca_el_json_inservible():
    assert sl.leer_entrada(b"{}").valida is True
    assert sl.leer_entrada(b"{no").valida is False
    assert sl.leer_entrada(b"[1,2]").valida is False


def test_json_que_no_es_objeto_no_lanza():
    assert sl.leer_entrada(b"[1,2]").modelo == "Claude"
    assert sl.leer_entrada(b"null").modelo == "Claude"


def test_worktree_y_mr():
    d = {"worktree": {"name": "mi-feature"}, "workspace": {"git_worktree": "otro"},
         "pr": {"number": 7, "kind": "mr"}}
    e = sl.leer_entrada(json.dumps(d))
    assert e.worktree == "mi-feature"
    assert (e.pr_numero, e.pr_es_mr, e.pr_estado) == (7, True, None)


def test_git_worktree_del_workspace_si_no_hay_bloque_worktree():
    e = sl.leer_entrada(json.dumps({"workspace": {"git_worktree": "otro"}}))
    assert e.worktree == "otro"


def test_carpeta_usa_cwd_si_no_hay_project_dir():
    e = sl.leer_entrada(json.dumps({"cwd": "/home/d/proyecto/"}))
    assert e.carpeta == "proyecto"


def test_usage_null_y_tipos_raros_no_lanzan():
    d = {"context_window": {"used_percentage": None, "current_usage": None, "context_window_size": "x"},
         "cost": {"total_cost_usd": "4"}, "rate_limits": {"five_hour": {"used_percentage": "58"}}}
    e = sl.leer_entrada(json.dumps(d))
    assert e.contexto_pct is None and e.contexto_total == 200000
    assert e.costo == 4.0
    assert e.cinco_h.pct == 58.0 and e.cinco_h.reinicio is None


def test_un_campo_malformado_no_arrastra_a_los_demas():
    d = {"pr": {"number": "no-es-numero"}, "cost": {"total_cost_usd": 1.5}, "session_id": "s9"}
    e = sl.leer_entrada(json.dumps(d))
    assert e.pr_numero is None
    assert e.costo == 1.5 and e.session_id == "s9"
