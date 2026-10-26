"""Galería visual: imprime con ANSI cada pose de Clawd, los amigos, las tareas de fondo, los colores del modelo, del
esfuerzo y del ritmo de los límites, y cada nivel de plegado.
Uso: python tools/vista.py [--nivel N] [--ancho N] [--seg S]. Sin argumentos imprime todo,
incluida una pasada por anchos representativos (--ancho compone uno solo, con el plegado elástico)."""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import statusline as sl  # noqa: E402

POSES = [sl.ESPERANDO, sl.DORMIDO, sl.PENSANDO, sl.LEYENDO, sl.ESCRIBIENDO, sl.EJECUTANDO, sl.NAVEGANDO,
         sl.DELEGANDO, sl.SOBRESALTO, sl.COMPACTANDO]


def entrada():
    return sl.Entrada(modelo="Opus 5", esfuerzo="xhigh", carpeta="StatusBarDFR", pr_numero=12, pr_estado="approved",
                      contexto_pct=76, cache_observada=True, cache_tibia=True, cache_aciertos=0.78, cache_fallos=1,
                      cinco_h=sl.Ventana(88, 1_800_010_000, esperado=70.0, fraccion=0.7),
                      siete_d=sl.Ventana(27, 1_800_300_000, esperado=40.0, fraccion=0.4),
                      costo=4.2, lineas=(312, 18))


def amigos():
    return [sl.Amigo("a1", "explore", "explore", pose=sl.LEYENDO, leyenda="pose", herramienta="Grep", nacido_hace=9, escritorio=0),
            sl.Amigo("a2", "general", "general", pose=sl.EJECUTANDO, leyenda="x", herramienta="Bash", nacido_hace=9, escritorio=1),
            sl.Amigo("a3", "plan", "plan", pose=sl.ESCRIBIENDO, leyenda="p.md", herramienta="Write", nacido_hace=9, escritorio=2),
            sl.Amigo("a4", "propio", "revisor", nacido_hace=1, escritorio=3),
            sl.Amigo("a5", "explore", "explore", pose=sl.NAVEGANDO, leyenda="docs", herramienta="WebFetch", nacido_hace=9, escritorio=4),
            sl.Amigo("a6", "general", "general", pose=sl.PENSANDO, leyenda="", nacido_hace=9, escritorio=5)]


def imprimir(grilla, titulo):
    print(f"\x1b[2m── {titulo} ──\x1b[0m")
    for fila in grilla:
        print(sl.pintar_fila(fila))
    print()


def imprimir_filas(filas, titulo):
    print(f"[2m── {titulo} ──[0m")
    for fila in filas:
        print(sl.pintar_fila(fila))
    print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--nivel", type=int)
    p.add_argument("--seg", type=int, default=0)
    p.add_argument("--ancho", type=int, help="compone a ese ancho de terminal (usa el plegado elástico)")
    a = p.parse_args()
    e = entrada()
    if a.nivel is None and a.ancho is None:
        for pose in POSES:
            act = sl.Actividad(pose=pose, leyenda="statusline.py", herramienta="Read", rama="master")
            imprimir(sl.componer(e, act, a.seg, 4), f"clawd {pose}")

        e_frio = sl.Entrada(modelo="Opus 5", esfuerzo="xhigh", carpeta="StatusBarDFR", pr_numero=12,
                             pr_estado="approved", contexto_pct=92, cache_observada=True, cache_tibia=False,
                             cache_aciertos=0.78, cache_fallos=1, cinco_h=sl.Ventana(96, 1_800_010_000),
                             siete_d=sl.Ventana(27, 1_800_300_000), costo=4.2, lineas=(312, 18))
        act_frio = sl.Actividad(pose=sl.PENSANDO, rama="master")
        imprimir(sl.componer(e_frio, act_frio, a.seg, 4), "humor frío y crítico")

        e_trunc = sl.Entrada(modelo="Opus 5", carpeta="una-carpeta-con-nombre-largo", contexto_pct=41)
        act_trunc = sl.Actividad(pose=sl.LEYENDO, leyenda="un_archivo_con_nombre_muy_largo.py", herramienta="Read",
                                  rama="feature/una-rama-con-nombre-larga",
                                  amigos=[sl.Amigo("t1", "propio", "revisor-de-codigo"[:7], pose=sl.LEYENDO,
                                                    leyenda="patron", herramienta="Grep", nacido_hace=9,
                                                    escritorio=0)])
        imprimir(sl.componer(e_trunc, act_trunc, a.seg, 0), "truncación")

        filas = [sl.fila_identidad(sl.Entrada(modelo=m, esfuerzo=n, carpeta="StatusBarDFR"), sl.Actividad(), 0)
                 for m in ("Opus 5.5", "Sonnet 5.5", "Haiku 5.5", "Fable 5.1") for n in sl.NIVELES_ESFUERZO]
        imprimir_filas(filas, "modelo y esfuerzo")

        ritmos = [(30, "por debajo"), (50, "en el margen"), (57, "levemente excedido"), (70, "muy excedido")]
        filas = [sl.fila_ventanas(sl.Entrada(cinco_h=sl.Ventana(p, None, esperado=50.0, fraccion=0.5)), 0)
                 + sl.texto(f"   {nombre}", "texto secundario") for p, nombre in ritmos]
        imprimir_filas(filas, "ritmo de los límites: uso real (esperado a esta hora)")

        act_tareas = sl.Actividad(pose=sl.ESPERANDO, rama="master", amigos=amigos()[:2], scripts=2, monitores=1)
        imprimir(sl.componer(e, act_tareas, a.seg, 0), "tareas de fondo: 2 scripts y 1 monitor")

    act = sl.Actividad(pose=sl.DELEGANDO, leyenda="··", herramienta="Agent", amigos=amigos(), rama="master")
    if a.ancho is not None:
        imprimir(sl.componer_que_entre(e, act, a.seg, a.ancho), f"ancho {a.ancho} (nivel {sl.elegir_nivel(a.ancho)})")
        return
    for nivel in ([a.nivel] if a.nivel is not None else range(-1, 5)):
        imprimir(sl.componer(e, act, a.seg, nivel), f"nivel {nivel} ({sl.ancho_escena(nivel)} col de escena)")
    if a.nivel is None:
        for ancho in (140, 164, 165, 202):
            imprimir(sl.componer_que_entre(e, act, a.seg, ancho), f"ancho {ancho} (nivel {sl.elegir_nivel(ancho)})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
