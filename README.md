# StatusBarDFR

Una status line para [Claude Code](https://claude.com/claude-code) que convierte la barra de abajo en una
pequeña oficina: Clawd, la mascota de Claude, trabaja en su escritorio imitando lo que Claude está haciendo,
y cada subagente que lanza aparece como un amigo en su propio escritorio; los scripts y monitores que corren de
fondo tienen el suyo. A la derecha, un tablero con todo lo que conviene tener a la vista: contexto, caché, costo y
límites de uso, con un color que dice si vas por debajo o por encima del ritmo.

![StatusBarDFR en la terminal de VS Code](docs/captura.png)

Son tres líneas en color verdadero, dibujadas con iconos de Nerd Font y actualizadas una vez por segundo.

## Qué muestra

### La escena

**Clawd** cambia de pose según lo que Claude esté haciendo:

| Pose | Cuándo |
|---|---|
| Leyendo | `Read`, `Grep`, `Glob` |
| Escribiendo | `Edit`, `Write`, `NotebookEdit` |
| Ejecutando | `Bash`, `PowerShell` |
| Navegando | `WebFetch`, `WebSearch` y el navegador |
| Delegando | mientras espera a sus subagentes |
| Pensando | mientras prepara la respuesta |
| Esperando | cuando el turno es tuyo |
| Dormido | tras 5 minutos esperándote |
| Sobresalto | 3 segundos después de un error de herramienta |
| Compactando | cuando se compacta el contexto |

Además, la escena refleja cómo va la sesión:
- **Sudor** cuando el contexto pasa del 75 % (y más al 90 %).
- **Un café** tibio o frío según la caché de prompt esté viva o se haya enfriado.
- **Un reloj de arena** en amarillo o rojo cuando la ventana de 5 horas pasa del 85 % o del 95 %.

**Los amigos** son los subagentes en curso. Cada uno ocupa un escritorio con su lámpara:

```
╭─◉◉╮ S Buscar el b
╰┬─┬╯▕󰍉▏ 󰥟
━┻━┻━━━━━┻━━━━━━━━━
```

- **El color de la figura** dice qué tipo de agente es:

  | Color | Tipo |
  |---|---|
  | azul índigo | `Explore` |
  | verde | `general-purpose` |
  | dorado oliva | `Plan` |
  | orquídea | cualquier otro: los agentes propios (`.claude/agents/`) y los de plugins |
  | gris | tipo desconocido |

  Los cuatro colores se distinguen entre sí también con daltonismo, y ninguno se confunde con Clawd.

- **La letra** es la inicial de su modelo, en el color de esa familia, el mismo que usa el tablero: `O` Opus
  (violeta), `S` Sonnet (turquesa), `H` Haiku (rosa claro), `F` Fable (cobre). Si el agente no pidió un modelo
  propio, lleva el de la sesión.
- **El texto** es el encargo con que se lo despachó, recortado al ancho del escritorio.
- **La tableta** muestra lo que hace en este momento: `󰍉` busca, `󰈙` lee, `󰏫` escribe, una ruedita ejecuta,
  `󰖟` navega, `󰃢` compacta y `󰀦`, en rojo, acaba de fallar una herramienta.
- **La lámpara** amarilla indica un escritorio ocupado, y gris uno libre. Una chispa `✦` anuncia al que llega y
  `✧` despide al que se va.

Cuando no hay escritorios para todos, el último muestra `+N`. Un amigo deja su escritorio apenas termina,
también si falló o lo cancelaron. La letra y el encargo sólo se ven en las terminales anchas; en las angostas
queda la figura con su color y su tableta.

**Las tareas de fondo** ocupan el último escritorio mientras haya alguna viva, aunque no quede ningún amigo:
una pantalla animada con `󰆍` para los scripts (`Bash` en segundo plano) y `󱎴` para los monitores (`Monitor`),
cada uno con su contador cuando hay más de uno.

### El tablero

- **Modelo y nivel de esfuerzo.** Cada familia tiene su color: Opus violeta, Sonnet turquesa, Haiku rosa y Fable
  cobre. El esfuerzo usa el mismo color, más intenso cuanto más alto: pálido en `low`, pleno en `max`.
- Carpeta, rama (o worktree), número de PR con su estado en color y líneas agregadas y quitadas.
- Barra de contexto con una marca `┆` donde Claude Code autocompacta, tasa de aciertos de la caché de prompt,
  cantidad de fallos y costo de la sesión en dólares.
- Uso de las ventanas de **5 horas** y **7 días**, con la hora a la que se reinicia cada una y, entre paréntesis,
  cuánto tocaría llevar consumido a esta hora si el uso fuera parejo hasta el reinicio: `58% (40%)`.

El porcentaje de cada ventana se pinta según el ritmo, es decir, el uso real dividido por el esperado:

| Color | Ritmo | Qué significa |
|---|---|---|
| Azul | menos del 90 % | vas por debajo |
| Verde | del 90 al 105 % | vas en el margen |
| Amarillo | del 105 al 120 % | vas levemente excedido |
| Rojo | más del 120 % | a este paso llegas al límite antes del reinicio |

Durante el primer 10 % de cada ventana se queda en verde: el esperado está tan cerca de cero que cualquier uso
parecería un exceso. El número esperado necesita lugar y solo aparece con 140 columnas o más; en terminales más
angostas queda el color.

### Se adapta al ancho

A medida que la terminal se angosta, la barra se pliega por niveles: primero achica los escritorios, luego
deja menos amigos a la vista y al final muestra solo el tablero. El nivel depende del ancho de la terminal, no
del contenido, así que la barra no parpadea cuando cambia la rama o el costo.

## Requisitos

- **Claude Code**. Probado con la 2.1.310; las versiones anteriores también funcionan.
- **Python 3**, sin paquetes adicionales: el script usa solo la biblioteca estándar. Probado con Python 3.12.
- **Una [Nerd Font](https://www.nerdfonts.com/)** configurada en la terminal. Sin ella, los iconos salen como
  cuadritos. Se recomienda la variante *Mono* (por ejemplo `JetBrainsMono Nerd Font Mono`), que dibuja cada
  icono en una sola celda.
- **Una terminal con color verdadero** (24 bits).

Probado en Windows 11 con la terminal integrada de VS Code. En macOS, Linux y otras terminales debería
funcionar, pero todavía no está probado.

## Instalación

1. Clona el repositorio en cualquier carpeta:

   ```sh
   git clone https://github.com/dfrobledo/StatusBarDFR.git
   ```

2. Agrega esto a `~/.claude/settings.json` (en Windows, `%USERPROFILE%\.claude\settings.json`), con las
   rutas de tu Python y de tu copia del script:

   ```json
   "statusLine": {
     "type": "command",
     "command": "python /ruta/a/StatusBarDFR/statusline.py",
     "refreshInterval": 1,
     "padding": 0
   }
   ```

   En Windows conviene usar la ruta completa al intérprete y barras normales, por ejemplo
   `"\"C:/Program Files/Python312/python.exe\" C:/herramientas/StatusBarDFR/statusline.py"`.
   `refreshInterval: 1` es lo que anima la escena una vez por segundo.

3. Abre una sesión nueva de Claude Code. La barra aparece abajo del cuadro de texto.

### Configuración recomendada para VS Code

```json
"terminal.integrated.fontFamily": "JetBrainsMono Nerd Font Mono",
"terminal.integrated.minimumContrastRatio": 1,
"terminal.integrated.gpuAcceleration": "on"
```

Con `minimumContrastRatio: 1`, VS Code respeta los colores tal cual en lugar de ajustarlos.

## Actualizar a una versión nueva

Si la instalaste con `git clone`, basta con traer los cambios en la carpeta del repositorio:

```sh
cd /ruta/a/StatusBarDFR
git pull
```

No hay que tocar `settings.json` ni reiniciar Claude Code: el script se ejecuta de nuevo cada segundo, así que la
versión nueva aparece sola en todas las sesiones abiertas.

- **Si cambiaste el script a mano**, guarda tus cambios antes con `git stash` y vuelve a aplicarlos después con
  `git stash pop`.
- **Si la descargaste como ZIP**, descarga la versión nueva desde la página de
  [releases](https://github.com/dfrobledo/StatusBarDFR/releases) y reemplaza los archivos **en la misma carpeta**,
  para que la ruta que tiene `settings.json` siga siendo válida.
- **Para saber qué versión tienes**: `git describe --tags`.
- **Para comprobar que quedó bien**: `python tools/vista.py` muestra las tareas de fondo, los colores del modelo y
  los del ritmo.

## Novedades

### 1.1.0

- **Los amigos se van cuando terminan.** Desde Claude Code 2.1.310 los subagentes terminan de otra forma, y la
  barra los dejaba sentados hasta 20 minutos después de haber terminado. También se van los que fallan o se
  cancelan.
- **Escritorio para las tareas de fondo:** scripts y monitores, con su contador.
- **Ritmo de los límites:** el uso esperado a esta hora junto a cada ventana y un color según el ritmo.
- **Colores para el modelo y el esfuerzo.**
- El costo pasó a la fila del contexto y las líneas cambiadas a la de identidad, para hacerle lugar al ritmo
  sin perder escritorios.

### 1.0.0

- Primera versión: Clawd, los amigos, el tablero y el plegado por ancho.

## Probarla sin Claude Code

`tools/vista.py` imprime una galería con todas las poses, los amigos y cada nivel de plegado:

```sh
python tools/vista.py              # todo
python tools/vista.py --ancho 120  # la barra compuesta para 120 columnas
```

Sirve para comprobar que la fuente y los colores se ven bien antes de configurarla.

## Si algo falla

La barra nunca rompe la sesión: si los datos que manda Claude Code no se pueden leer, muestra solo el modelo
y la carpeta, y si el script falla del todo, muestra `Claude`.

## Tests

```sh
python -m pip install pytest
python -m pytest
```

## Licencia

[MIT](LICENSE).
