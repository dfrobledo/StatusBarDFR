"""Lo que le pasa a la línea DESPUÉS de que el script la escribe.

Claude Code no muestra el stdout tal cual: le hace `trim()` a cada línea y descarta las vacías
(`como_lo_ve_claude_code`, en conftest). Ningún otro test de la suite ve esto, porque todos miden la
salida de `statusline.py` —que es correcta— y el defecto lo introduce el consumidor. Estos tests
miden la línea del lado de la pantalla.
"""
from conftest import columna_de_la_tinta, como_lo_ve_claude_code, sl

ANCHOS = (47, 100, 140, 144, 165, 202, 251)  # 144 y 251 son terminales reales medidas


def escena_poblada():
    e = sl.Entrada(modelo="Opus 5", carpeta="StatusBarDFR", contexto_pct=76, costo=4.2,
                   cinco_h=sl.Ventana(88, 1_800_010_000))
    amigos = [sl.Amigo("a1", "explore", "explore", pose=sl.LEYENDO, leyenda="pose", herramienta="Grep",
                       nacido_hace=9, escritorio=0),
              sl.Amigo("a2", "plan", "plan", pose=sl.ESCRIBIENDO, leyenda="p.md", herramienta="Write",
                       nacido_hace=9, escritorio=1)]
    act = sl.Actividad(pose=sl.DELEGANDO, leyenda="··", herramienta="Agent", amigos=amigos, rama="master")
    return e, act


def test_ninguna_linea_pierde_columnas_al_pasar_por_claude_code():
    """El trim del consumidor no puede alterar ni una columna de lo que el script dibujó."""
    e, act = escena_poblada()
    for ancho in ANCHOS:
        for seg in range(4):
            g = sl.componer_que_entre(e, act, seg, ancho)
            pintadas = [sl.pintar_fila(f) for f in g]
            assert como_lo_ve_claude_code("\n".join(pintadas)) == pintadas, (
                f"a {ancho} columnas (seg {seg}) el trim de Claude Code cambia la línea")


def test_los_pies_de_clawd_caen_sobre_el_piso():
    """El defecto tal como se ve en pantalla: las dos filas de la mascota empiezan con un espacio y el
    piso empieza con `━`, así que el trim corre la mascota una columna a la izquierda del piso y los
    pies quedan fuera de lugar. Se mide la columna donde arranca la tinta de cada fila, antes y después
    del consumidor: tienen que ser la misma."""
    e, act = escena_poblada()
    for ancho in ANCHOS:
        g = sl.componer_que_entre(e, act, 0, ancho)
        pintadas = [sl.pintar_fila(f) for f in g]
        vistas = como_lo_ve_claude_code("\n".join(pintadas))
        antes = [columna_de_la_tinta(p) for p in pintadas]
        despues = [columna_de_la_tinta(v) for v in vistas]
        assert antes == despues, f"a {ancho} columnas la escena se corre: {antes} → {despues}"


def test_la_grilla_entra_en_el_area_que_claude_code_pinta(monkeypatch):
    """`COLUMNS` trae el ancho de la TERMINAL, no el que la status line puede pintar: Claude Code la
    dibuja dentro de un contenedor con 2 columnas de padding por lado (`var _se=2` en 2.1.274, que usa
    para `rowWidth = ancho - 2*_se`). Medido en la barra real a 202 columnas: la sangría era de 2 y la
    fila del piso llegaba a 198 columnas de tinta, con el `…` de truncado de Ink al final. Componer al
    ancho de la terminal se sale siempre, a cualquier tamaño de ventana."""
    e, act = escena_poblada()
    for columnas in (100, 144, 202, 251):
        monkeypatch.setenv("COLUMNS", str(columnas))
        util = sl.ancho_consola()
        assert util == columnas - sl.MARGEN_UI, f"a {columnas} columnas el ancho útil debería ser {columnas - 4}"
        g = sl.componer_que_entre(e, act, 0, util)
        assert sl.ancho_de_grilla(g) <= util, f"a {columnas} columnas la grilla se sale del área pintable"


def test_una_fila_en_blanco_no_desarma_la_escena():
    """`flatMap(U => U.trim() || [])` DESCARTA las líneas que queden vacías, y las de abajo suben. Una
    fila de la escena que quede toda en blanco tiene que seguir ocupando su renglón."""
    grilla = [sl.fila_vacia(8), sl.texto("abcdefgh", "mascota"), sl.texto("━" * 8, "piso")]
    pintadas = [sl.pintar_fila(f) for f in grilla]
    assert len(como_lo_ve_claude_code("\n".join(pintadas))) == 3, "la fila en blanco se descartó"
