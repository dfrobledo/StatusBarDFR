from conftest import cuadro, golden, sl, verificar_tokens


def act(pose, leyenda="", herramienta=None, amigos=()):
    return sl.Actividad(pose=pose, leyenda=leyenda, herramienta=herramienta, amigos=list(amigos))


def entrada(**kw):
    e = sl.Entrada()
    for k, v in kw.items():
        setattr(e, k, v)
    return e


# ── humor ──────────────────────────────────────────────────────────────
def test_humor_por_umbrales():
    assert sl.humor_de(entrada()) == sl.Humor(0, None, None)
    assert sl.humor_de(entrada(contexto_pct=75, cache_observada=True, cache_tibia=True)) == sl.Humor(1, "tibio", None)
    assert sl.humor_de(entrada(contexto_pct=90, cache_observada=True, cache_tibia=False)) == sl.Humor(2, "frio", None)
    assert sl.humor_de(entrada(cinco_h=sl.Ventana(85, None))).reloj == "aviso"
    assert sl.humor_de(entrada(cinco_h=sl.Ventana(95, None))).reloj == "critico"
    assert sl.humor_de(entrada(cinco_h=sl.Ventana(84.9, None))).reloj is None


# ── escritorio de Clawd ────────────────────────────────────────────────
def test_clawd_mide_3x22_y_solo_usa_tokens():
    g = sl.escritorio_clawd(act(sl.ESPERANDO), sl.Humor(), 0)
    verificar_tokens(g)
    assert [len(f) for f in g] == [22, 22, 22]


def test_clawd_leyendo_read():
    g = sl.escritorio_clawd(act(sl.LEYENDO, "statusline.py", "Read"), sl.Humor(cafe="tibio"), 0)
    assert cuadro(g) == "\n".join([
        " ╭──◉◉─╮  statusline.p",
        " ╰─┬─┬─╯ ▕󰈙▏󰅶",
        "━━━┻━┻━━━━━━━━━━━━━━━━",
    ])
    assert g[1][10] == ("󰈙", "texto principal") and g[1][12] == ("󰅶", "mascota")
    assert g[2][3] == ("┻", "mascota") and g[2][4] == ("━", "piso")


def test_clawd_esperando_parpadea_en_el_cuarto_cuadro():
    ojos = [cuadro(sl.escritorio_clawd(act(sl.ESPERANDO), sl.Humor(), s)).split("\n")[0] for s in range(5)]
    assert ojos[0] == " ╭─◉─◉─╮" and ojos[2] == ojos[0] and ojos[3] == " ╭─────╮" and ojos[4] == ojos[0]


def test_clawd_pensando_cuenta_puntos():
    filas = [cuadro(sl.escritorio_clawd(act(sl.PENSANDO), sl.Humor(), s)).split("\n")[0] for s in range(3)]
    assert filas == [" ╭─◉◉──╮  ·", " ╭─◉◉──╮  ··", " ╭─◉◉──╮  ···"]


def test_clawd_ejecutando_gira_la_tableta():
    tabs = [sl.escritorio_clawd(act(sl.EJECUTANDO, "Correr tests", "Bash"), sl.Humor(), s)[1][10][0] for s in range(8)]
    assert "".join(tabs) == "⠋⠙⠹⠸⠼⠴⠦⠧"


def test_clawd_escribiendo_salta():
    patas = [cuadro(sl.escritorio_clawd(act(sl.ESCRIBIENDO, "a.py", "Edit"), sl.Humor(), s)).split("\n")[2] for s in range(2)]
    assert patas[0].startswith("━━┻━━━┻━") and patas[1].startswith("━━━┻━┻━━")


def test_clawd_dormido_agachado_con_zzz():
    g = sl.escritorio_clawd(act(sl.DORMIDO), sl.Humor(), 0)
    assert cuadro(g).split("\n") == [" ╭─────╮󰒲", " ╰─────╯", "━━━┻━┻━━━━━━━━━━━━━━━━"]
    assert g[0][8] == ("󰒲", "texto secundario")


def test_clawd_sobresalto_alerta_en_critico():
    g = sl.escritorio_clawd(act(sl.SOBRESALTO), sl.Humor(), 0)
    assert cuadro(g).split("\n")[0] == " ╭─◎─◎─╮"
    assert g[1][10] == ("󰀦", "critico")


def test_clawd_compactando():
    g = sl.escritorio_clawd(act(sl.COMPACTANDO), sl.Humor(), 0)
    assert cuadro(g).split("\n")[:2] == [" ╭─◉─◉─╮✦ compactando", " ╰─────╯ ▕󰃢▏"]
    assert g[0][8] == ("✦", "lampara encendida")


def test_clawd_humor_completo():
    g = sl.escritorio_clawd(act(sl.NAVEGANDO, "docs.claude.com", "WebFetch"), sl.Humor(2, "frio", "critico"), 0)
    assert cuadro(g).split("\n")[:2] == [" ╭──◉◉─╮󰖌󰖌docs.claude.", " ╰─┬─┬─╯ ▕󰖟▏󰛊 󰔟"]
    assert g[0][8] == ("󰖌", "frio") and g[1][12] == ("󰛊", "frio") and g[1][14] == ("󰔟", "critico")


def test_clawd_delegando_y_grep():
    assert cuadro(sl.escritorio_clawd(act(sl.DELEGANDO, "··", "Agent"), sl.Humor(), 0)).split("\n")[0] == " ╭──◉◉─╮  ··"
    g = sl.escritorio_clawd(act(sl.LEYENDO, "def main", "Grep"), sl.Humor(), 0)
    assert g[1][10] == ("󰍉", "texto principal")


def test_dorados_de_todas_las_poses():
    for pose in (sl.ESPERANDO, sl.DORMIDO, sl.PENSANDO, sl.LEYENDO, sl.ESCRIBIENDO, sl.EJECUTANDO,
                 sl.NAVEGANDO, sl.DELEGANDO, sl.SOBRESALTO, sl.COMPACTANDO):
        golden(f"clawd_{pose}", sl.escritorio_clawd(act(pose, "leyenda", "Read"), sl.Humor(1, "tibio", "aviso"), 1))


# ── escritorios de amigos ──────────────────────────────────────────────
def amigo(id_="ag1", tipo="explore", nombre="explore", pose=sl.LEYENDO, leyenda="pose", herr="Grep",
          nacido=10.0, terminado=None, escritorio=0):
    return sl.Amigo(id=id_, tipo=tipo, nombre=nombre, pose=pose, leyenda=leyenda, herramienta=herr,
                    nacido_hace=nacido, terminado_hace=terminado, escritorio=escritorio)


def test_amigo_vacio_lampara_apagada_y_poste():
    g = sl.escritorio_amigo(None, 0, 13, con_leyenda=True)
    assert cuadro(g).split("\n") == ["", "         󰥟", "━━━━━━━━━┻━━━"]
    assert g[1][9] == ("󰥟", "lampara apagada") and g[2][9] == ("┻", "apagado")
    verificar_tokens(g)


def test_amigo_ocupado_con_leyenda():
    am = amigo()
    s = sum(map(ord, am.id))  # fase 0 de su parpadeo
    g = sl.escritorio_amigo(am, -s, 13, con_leyenda=True)
    assert cuadro(g).split("\n") == ["╭─◉◉╮ explore", "╰┬─┬╯▕󰍉▏ 󰥟", "━┻━┻━━━━━┻━━━"]
    assert g[0][0] == ("╭", "amigo explore") and g[1][9] == ("󰥟", "lampara encendida")
    assert g[2][1] == ("┻", "amigo explore")


def test_amigo_sin_leyenda_en_10_columnas():
    g = sl.escritorio_amigo(amigo(), 0, 10, con_leyenda=False)
    assert [len(f) for f in g] == [10, 10, 10]
    assert cuadro(g).split("\n")[0].startswith("╭") and "explore" not in cuadro(g)


def test_amigo_ancho_muestra_nombre_y_leyenda():
    g = sl.escritorio_amigo(amigo(nombre="explore", leyenda="pose"), 0, 20, con_leyenda=True)
    assert [len(f) for f in g] == [20, 20, 20]
    assert cuadro(g).split("\n")[0][6:] == "explore pose"


def test_amigo_en_el_ancho_base_trunca_a_siete_como_hoy():
    g = sl.escritorio_amigo(amigo(nombre="explore", leyenda="pose"), 0, 13, con_leyenda=True)
    assert cuadro(g).split("\n")[0][6:] == "explore"
    corto = sl.escritorio_amigo(amigo(nombre="plan", leyenda="pose"), 0, 13, con_leyenda=True)
    assert cuadro(corto).split("\n")[0][6:] == "plan po"  # una sola regla: se trunca, no se corta en palabra


def test_amigo_sin_leyenda_no_deja_espacio_colgando():
    g = sl.escritorio_amigo(amigo(nombre="plan", leyenda=""), 0, 20, con_leyenda=True)
    # "plan" ocupa las columnas 6-9 (TEXTO_EN_ESCRITORIO=6); la celda siguiente
    # debe seguir siendo el relleno de fila_vacia, no un espacio escrito por poner()
    assert g[0][sl.TEXTO_EN_ESCRITORIO + len("plan")] == (" ", "apagado")


def test_amigo_nace_y_se_va_con_chispas():
    g = sl.escritorio_amigo(amigo(nacido=1.0), 0, 13, True)
    assert cuadro(g).split("\n")[:2] == ["", "  ✦      󰥟"]
    g = sl.escritorio_amigo(amigo(terminado=1.5), 0, 13, True)
    assert cuadro(g).split("\n")[:2] == ["", "  ✧      󰥟"]
    assert g[1][2] == ("✧", "lampara encendida")


def test_amigo_desbordado_muestra_mas_n():
    g = sl.escritorio_amigo(None, 0, 13, True, extra=3)
    assert cuadro(g).split("\n")[:2] == ["+3", "         󰥟"]
    assert g[1][9][1] == "lampara encendida"


def test_amigos_parpadean_desfasados():
    a, b = amigo(id_="aaaa", pose=sl.ESPERANDO), amigo(id_="aaab", pose=sl.ESPERANDO)
    ojos = lambda am, s: cuadro(sl.escritorio_amigo(am, s, 10, False)).split("\n")[0]
    assert [ojos(a, s) for s in range(4)] != [ojos(b, s) for s in range(4)]


def test_amigo_escribiendo_salta():
    am = amigo(pose=sl.ESCRIBIENDO, herr="Edit")
    s = sum(map(ord, am.id))
    patas = [cuadro(sl.escritorio_amigo(am, k - s, 10, False)).split("\n")[1][:5] for k in range(2)]
    assert patas == ["╰┬─┬╯", "╰─┬─╯"]


def test_colores_por_tipo():
    for tipo in ("explore", "general", "plan", "propio", "desconocido"):
        g = sl.escritorio_amigo(amigo(tipo=tipo), 0, 10, False)
        assert g[0][0][1] == f"amigo {tipo}"


# ── composición ────────────────────────────────────────────────────────
def test_ancho_de_escena_por_nivel():
    assert [sl.ancho_escena(n) for n in range(5)] == [74, 62, 52, 42, 22]


def test_ancho_de_escena_con_escritorio_ensanchado():
    assert sl.ancho_escena(0, 20) == 22 + 4 * 20
    assert sl.ancho_escena(0, 13) == sl.ancho_escena(0)


def test_escena_dibuja_escritorios_del_ancho_pedido():
    a = act(sl.DELEGANDO, "··", "Agent", amigos=[amigo(escritorio=0)])
    g = sl.dibujar_escena(a, sl.Humor(), 0, 0, 20)
    verificar_tokens(g)
    assert [len(f) for f in g] == [22 + 4 * 20] * 3
    assert g[1][22 + 9][1] == "lampara encendida"      # la lámpara sigue en la columna 9 del escritorio
    assert g[1][22 + 20 + 9][1] == "lampara apagada"   # el segundo escritorio arranca 20 columnas después


def test_escena_nivel_0_con_dos_amigos():
    a = act(sl.DELEGANDO, "··", "Agent", amigos=[amigo(escritorio=0), amigo(id_="ag2", tipo="plan", nombre="plan", escritorio=1)])
    g = sl.dibujar_escena(a, sl.Humor(cafe="tibio"), 0, 0)
    verificar_tokens(g)
    assert [len(f) for f in g] == [74] * 3
    assert g[2][22 + 9] == ("┻", "apagado") and g[2][22 + 13 + 9] == ("┻", "apagado")
    assert g[1][22 + 13 * 2 + 9][1] == "lampara apagada" and g[1][22 + 13 * 3 + 9][1] == "lampara apagada"
    golden("escena_n0_dos_amigos", g)


def test_escena_nivel_4_solo_clawd():
    g = sl.dibujar_escena(act(sl.ESPERANDO, amigos=[amigo()]), sl.Humor(), 0, 4)
    assert [len(f) for f in g] == [22] * 3


def test_escena_desborde_en_el_ultimo_escritorio():
    amigos = [amigo(id_=f"a{i}", escritorio=i) for i in range(5)]
    g = sl.dibujar_escena(act(sl.DELEGANDO, amigos=amigos), sl.Humor(), 0, 2)  # 3 escritorios
    ultimo = 22 + 10 * 2
    assert "".join(c for c, _ in g[0][ultimo:ultimo + 2]) == "+3"  # 5 amigos, 2 con escritorio visible
    golden("escena_n2_desborde", g)


def test_escena_escritorio_libre_en_el_medio():
    amigos = [amigo(id_="a0", escritorio=0), amigo(id_="a2", escritorio=2)]
    g = sl.dibujar_escena(act(sl.DELEGANDO, amigos=amigos), sl.Humor(), 0, 1)
    assert g[1][22 + 10 + 9][1] == "lampara apagada"
    assert g[1][22 + 20 + 9][1] == "lampara encendida"


def test_dorados_de_niveles_de_escena():
    amigos = [amigo(escritorio=0, nacido=1.0), amigo(id_="ag2", tipo="general", nombre="general", pose=sl.EJECUTANDO,
                                                     leyenda="x", herr="Bash", escritorio=1)]
    for nivel in range(5):
        golden(f"escena_n{nivel}", sl.dibujar_escena(act(sl.LEYENDO, "spec.md", "Read", amigos), sl.Humor(1, "frio", None), 2, nivel))


# ── alineación de la caja ──────────────────────────────────────────────
# El personaje es una caja dibujada con glifos de celda entera: no hay medias celdas que
# corran la cabeza. El invariante pasa a ser la envolvente en columnas, que es más fuerte
# que el centro — dos piezas pueden compartir centro y tener anchos distintos.


def envolvente(s):
    llenas = [i for i, ch in enumerate(s) if ch != " "]
    return (min(llenas), max(llenas))


def piezas_de_clawd():
    return ([c for v in sl.CABEZA.values() for c in v] + list(sl.CABEZA_HERRAMIENTA)
            + [cuerpo for v in sl.PATAS.values() for cuerpo, _ in v])


def test_cabeza_y_cuerpo_de_clawd_comparten_envolvente():
    fuera = [p for p in piezas_de_clawd() if envolvente(p) != (0, 6)]
    assert fuera == [], f"envolventes {[(p, envolvente(p)) for p in fuera]}"


def test_cabeza_y_cuerpo_de_amigo_comparten_envolvente():
    piezas = ([c for v in sl.CABEZA_AMIGO.values() for c in v] + list(sl.CABEZA_AMIGO_HERRAMIENTA)
              + [cuerpo for v in sl.PATAS_AMIGO.values() for cuerpo, _ in v])
    fuera = [p for p in piezas if envolvente(p) != (0, 4)]
    assert fuera == [], f"envolventes {[(p, envolvente(p)) for p in fuera]}"


def test_solo_el_salto_mueve_los_pies():
    """Mover los pies es lo que dice 'me estoy moviendo'. Si una pose quieta los corre, el cambio
    de pose se ve como un respingo — y dormido termina con la misma silueta que escribiendo."""
    for tabla in (sl.PATAS, sl.PATAS_AMIGO):
        quieto = {i for i, c in enumerate(tabla["parado"][0][1]) if c == "┻"}
        for nombre, cuadros in tabla.items():
            if nombre == "salto":
                continue
            for _, pies in cuadros:
                apoyos = {i for i, c in enumerate(pies) if c == "┻"}
                assert apoyos == quieto, (nombre, pies, sorted(apoyos), sorted(quieto))


def test_cada_pata_apoya_en_un_pie():
    """Un `┬` del cuerpo sin `┻` debajo deja la pata colgando media celda sobre el piso."""
    for tabla in (sl.PATAS, sl.PATAS_AMIGO):
        for nombre, cuadros in tabla.items():
            for cuerpo, pies in cuadros:
                patas = {i for i, ch in enumerate(cuerpo) if ch == "┬"}
                apoyos = {i for i, ch in enumerate(pies) if ch == "┻"}
                assert patas <= apoyos, (nombre, cuerpo, pies, sorted(patas - apoyos))


def test_dorado_de_la_escena_del_peldano_nuevo():
    amigos = [amigo(id_=f"a{i}", escritorio=i, nombre=f"amigo{i}"[:7], leyenda="pose") for i in range(6)]
    g = sl.dibujar_escena(act(sl.DELEGANDO, "··", "Agent", amigos), sl.Humor(), 0, -1, 19)
    verificar_tokens(g)
    assert [len(f) for f in g] == [22 + 6 * 19] * 3
    golden("escena_nm1", g)
