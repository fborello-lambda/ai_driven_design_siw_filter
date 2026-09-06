---
title: "Guía para simular el filtro SIW en CST"
subtitle: "Cascade N=3, 2.87 GHz — pasos para correr la macro y verificar el modelo"
date: "2026-09-06"
lang: es
geometry: margin=2.5cm
papersize: a4
fontsize: 11pt
colorlinks: true
toc: true
toc-depth: 2
---

\newpage

# Qué es esto

Este paquete tiene todo lo necesario para simular en **CST Studio Suite**
el diseño que se va a fabricar: un filtro pasabanda SIW de orden 3
(cascada de 3 cavidades TE101), centrado en **2.87 GHz**, sobre
**Rogers RO4350B de 0.76 mm**, con conector **SMA edge-mount Taoglas
EMPCB.SMAFSTJ.B.HT** real.

El diseño ya fue optimizado y simulado con otro solver (Palace, FEM,
open-source) durante todo el proceso. Esta corrida en CST sirve como
**verificación independiente**, con un solver distinto, del mismo diseño.

Archivos en esta carpeta:

| Archivo | Qué es |
|---|---|
| `siw_cascade_N3.bas` | La macro VBA. Al ejecutarla en CST construye toda la geometría 3D. |
| `palace_cascade_N3_reference.s2p` | Los parámetros S que dio Palace para este mismo diseño, para comparar contra lo que dé CST (ver §6 — el archivo tiene **fase puesta en cero**, sirve solo para comparar magnitud en dB, no para nada que dependa de la fase). |
| `FAB_NOTES.md` | Notas de fabricación (sustrato, cobre, acabado) — no hace falta para simular, es referencia. |
| `img/` | Imágenes de referencia (esta guía), generadas directamente desde la herramienta de línea de comandos del proyecto — no son capturas de CST. |

## Cómo se ve la placa (vista de arriba, acotada)

Esta imagen sale de `siw layout` (no de CST): las tres cavidades, los dos
iris internos acoplando las cavidades, los acoplamientos externos de
entrada/salida (`w_ext`), la fila de vías de cada pared, y las tapers
microstrip-a-SIW en cada extremo (la zona en forma de flecha que se
ensancha desde la línea angosta hasta el ancho completo de la cavidad).

![Vista superior acotada del filtro cascade N=3. Las tapers grandes en
cada extremo son la transición microstrip-a-SIW; el lanzador CPWG (mucho
más chico) está fuera de este dibujo, pegado al conector.](img/board_top_dimensionado.png)

## Cómo se ve en 3D (el modelo que arma la macro)

![Vista 3D del sólido completo: sustrato, plano de tierra, fila de vías,
tapers y el conector SMA en cada extremo.](img/board_3d.png)

![Acercamiento al lanzador: el conector SMA, el gap CPWG angosto, y cómo
se ensancha hacia la taper grande que entra a la cavidad. Esta es
exactamente la zona que la macro debe reproducir en CST -- si en el
modelo de CST falta la pieza ancha después del microstrip, la pista no
llega a la cavidad.](img/board_3d_launch_closeup.png)

\newpage

# 1. Qué se necesita

- **CST Studio Suite 2021** (o una versión posterior compatible con VBA
  `AddToHistory`/`Brick`/`Cylinder` — el macro fue escrito y pensado para
  2021, pero el VBA de estas instrucciones es estable en versiones más
  nuevas también).
- El archivo `siw_cascade_N3.bas` de esta misma carpeta.
- Unos ~15-20 minutos: la macro tarda segundos en construir la geometría,
  pero la simulación en sí (paso 5) puede tardar bastante más según la PC
  (una malla fina 3D con un conector coaxial real no es trivial).

No hace falta ningún archivo de Python ni el resto de este repositorio —
la macro es autocontenida.

\newpage

# 2. Abrir CST y crear un proyecto nuevo

1. Abrir **CST Studio Suite**.
2. **File → New and Recent → New Template...**
3. Elegir **MW & RF & Optical → Circuits & Components → General → Full
   Wave (S-Parameter) Time Domain** (cualquier plantilla "en blanco" de
   alta frecuencia sirve — la macro define todo desde cero: unidades,
   sustrato, geometría, malla y solver. Si no aparece esa plantilla
   exacta, un proyecto "Microwave & RF" en blanco también funciona).
4. Guardar el proyecto donde sea cómodo (por ejemplo
   `siw_cascade_N3.cst`).

\newpage

# 3. Importar y ejecutar la macro

Esto es lo que reemplaza a dibujar la geometría a mano — la macro hace
**todo**: parámetros, sustrato, vías, iris, el conector SMA real y los
puertos.

## 3.0 Antes de correr nada: verificar que el archivo es la versión corregida

Este `siw_cascade_N3.bas` tiene corregidos **dos** errores reales, ambos
detectados a partir de una corrida real en CST que dio un resultado roto
(S1,1 pegado a 0 dB en toda la banda, ver §7.2 — no un problema de Palace
ni del diseño, sino de cómo se armaba este archivo):

1. **2026-09-05**: al conector SMA le faltaba el cilindro metálico que lo
   blinda por afuera del dieléctrico.
2. **2026-09-06**: la pared inferior del dominio de simulación estaba
   declarada `electric` (un plano de tierra extra) en vez de `open`. El
   plano de tierra real de la placa ya es un sólido PEC aparte (correcto);
   esta pared de más quedaba, por el tamaño automático del dominio,
   pegada al conector SMA -- una plancha de tierra ficticia del tamaño de
   toda la placa, sin ningún equivalente en el modelo de Palace, justo
   debajo del lanzador.

**Antes de ejecutar la macro**, abrir el archivo `.bas` con un editor de
texto (Bloc de notas alcanza) y buscar (Ctrl+F):

- `sma_in_shield` → debe **aparecer**.
- `.Zmin "open"` → debe **aparecer**. Si en cambio aparece
  `.Zmin "electric"`, es la versión vieja.

Si cualquiera de las dos búsquedas falla, es una versión vieja — usar el
archivo que viene en este mismo paquete, no uno descargado antes.

1. En el menú superior: **Macros → Macro Editor...** (o el ícono de
   macros, según la versión).
2. En el editor de macros: **File → Open Macro File...**
3. Seleccionar `siw_cascade_N3.bas` de esta carpeta.
4. Con el archivo abierto en el editor, presionar **F5** (o
   **Macros → Run Macro**).
5. Al terminar debería aparecer un cuadro de diálogo:
   *"SIW filter built: 124 solids. Check the modeler tree, then run the
   Time Domain solver."*
6. Cerrar el cuadro de diálogo y mirar el árbol del modelador
   (**Navigation Tree → Components**): debería verse la geometría
   completa — el sustrato, el plano de tierra, las vías (dos filas
   densas formando las cavidades), las tapers de microstrip a SIW, y en
   cada extremo el conector SMA (un cilindro de PTFE con su pin dorado
   adentro, sobresaliendo del borde de la placa).

Comparar contra las imágenes del §"Cómo se ve la placa" más arriba —
en particular, verificar que **después de la pista angosta del microstrip
haya una pieza ancha en forma de embudo antes de llegar a la cavidad**
(la taper microstrip-a-SIW). Esa pieza es grande y fácil de ver en el
árbol del modelador (se llama `taper_in`/`taper_out`); si falta, la pista
queda cortada y no llega a la cavidad — la simulación no va a andar aunque
CST no muestre ningún error al construir la geometría.

**Si algo de esto no aparece** (falta la taper grande, faltan vías, el
conector no se ve, o al conector le falta el cilindro metálico que envuelve
al dieléctrico PTFE por fuera), lo más probable es que el archivo `.bas`
esté desactualizado — pedir que se regenere desde el repositorio antes de
seguir. El archivo de esta carpeta ya tiene corregidos varios errores que
existieron en versiones anteriores de esta macro: dos de unidades (que
dibujaban el conector y las vías del lanzador 1000 veces más grandes o más
lejos de lo correcto); uno donde faltaba la taper grande, dejando la pista
sin conexión a la cavidad; uno donde al conector coaxial le faltaba el
blindaje metálico exterior (`sma_in_shield`/`sma_out_shield`); y uno en la
pared inferior del dominio de simulación (`.Zmin`, ver §3.0 y §7.2).

\newpage

# 4. Verificar qué solver quedó configurado

La macro deja todo configurado, pero conviene revisarlo antes de correr
la simulación — es justamente lo que hay que confirmar.

## 4.1 Tipo de solver: Dominio del Tiempo (Time Domain)

1. **Home → Simulation → Setup Solver** (o el ícono con el nombre del
   solver, normalmente dice "Time Domain Solver").
2. Debería estar seleccionado el **Time Domain Solver** (también llamado
   "T-Solver" o "Transient Solver"), **no** el Frequency Domain Solver.
3. Esto es intencional: el T-Solver de CST hace **un único cálculo de
   banda ancha** (un pulso en el tiempo) y con la FFT obtiene S11/S21 en
   todo el rango de frecuencia de una sola corrida — no hace falta barrer
   frecuencia por frecuencia.

Esto se puede confirmar leyendo la macro misma: buscar (Ctrl+F en el
editor) la línea `.CalculationType "TD-S"` — la sigla **TD-S** es
justamente "Time Domain, S-parameters", la confirmación de que el solver
configurado es el de dominio del tiempo.

## 4.2 Parámetros del solver que trae la macro

En el mismo panel de configuración del solver debería verse:

| Parámetro | Valor que pone la macro | Significado |
|---|---|---|
| Rango de frecuencia | 2.0 – 3.6 GHz | `Solver.FrequencyRange` — la banda de interés alrededor de los 2.87 GHz |
| Método de malla | Hexahedral (PBA) | Perfect Boundary Approximation — la malla estándar de CST para geometrías curvas (los cilindros de las vías y el conector) |
| Líneas por longitud de onda | 25 | densidad de malla |
| Límite de estado estacionario | −40 dB | el solver corta la simulación en el tiempo cuando la energía cae 40 dB por debajo del pico — suficiente para S-parameters de un filtro |
| Puerto de excitación | Puerto 1, todos los modos | se excita desde el conector de entrada |

No hace falta tocar nada de esto — son los valores con los que se validó
el diseño. Si se quiere ver la banda espuria por encima de la banda de
paso (ya documentada y esperada, no es un error), se puede ampliar el
rango de frecuencia a algo como 0.5–8 GHz antes de correr.

\newpage

# 5. Correr la simulación

1. **Home → Simulation → Start Simulation** (o el botón con el ícono de
   "play" al lado del solver).
2. CST va a mallar la geometría (puede tardar uno o dos minutos: hay 118
   agujeros/cilindros más el conector coaxial) y después correr el
   Time Domain solver.
3. Tiempo total: depende mucho de la PC — puede ser de varios minutos a
   más de media hora en una notebook. Se puede seguir el progreso en la
   ventana de log que abre CST.
4. Al terminar, CST calcula automáticamente los parámetros S (no hace
   falta configurar nada adicional para esto).

\newpage

# 6. Ver los resultados y compararlos con Palace

1. En el árbol de navegación: **1D Results → S-Parameters**.
2. Debería aparecer **S1,1** y **S2,1** (dB) — estas son la pérdida de
   retorno y la pérdida de inserción del filtro.
3. Comparar contra el diseño esperado (medido con Palace):

| Magnitud | Palace (referencia) |
|---|---|
| Frecuencia central | 2.879 GHz |
| Pérdida de retorno (peor caso en banda) | −13.37 dB |
| Ancho de banda a −3 dB | 189 MHz |
| Pérdida de inserción | −1.85 dB (PEC) / −2.44 dB (cobre real) |

Esto es lo que dio Palace para este mismo diseño (gráfico generado desde
la herramienta de línea de comandos, no es una captura de CST) — la forma
que debería tener el resultado de CST, aunque los números exactos no
coincidan al dígito por tratarse de dos solvers distintos:

![|S21| y |S11| medidos con Palace para este diseño. Banda verde =
banda de paso objetivo; línea punteada = objetivo de −16 dB. El diseño
real queda en torno a −13 a −15 dB, no en el objetivo -- esa diferencia
ya está identificada y aceptada, no es un error de la simulación (ver
§7 y `FAB_NOTES.md`).](img/resultado_esperado_s11_s21.png)

**Para superponer la curva de Palace directamente en el mismo gráfico de
CST:**

1. Click derecho sobre el gráfico de S-Parameters → **Import...** (o
   **1D Results → Import → Touchstone/Import Result**, según la versión).
2. Seleccionar `palace_cascade_N3_reference.s2p` (en esta misma carpeta).
3. Debería superponerse una curva más sobre el mismo gráfico.

**Importante sobre ese archivo `.s2p`**: la fase se puso en cero a
propósito porque los datos originales de Palace que se exportaron solo
tienen magnitud en dB, no fase. Sirve **exclusivamente** para comparar
visualmente las curvas de |S11| y |S21| en dB una al lado de la otra —
**no usarlo** para nada que dependa de la fase (retardo de grupo,
time-domain gating, etc.). Para eso habría que pedir el `.s2p` completo
con fase real.

No se espera que las dos curvas (CST y Palace) coincidan exactamente —
son dos solvers distintos (FEM en ambos casos, pero mallas y métodos
numéricos diferentes) — pero sí deberían tener la misma forma: la misma
cantidad de ceros de reflexión, el mismo ancho de banda aproximado, y la
frecuencia central dentro de un margen chico (unos pocos MHz).

\newpage

# 7. Verificación de que el modelo es fiel al diseño real

Esta sección es la respuesta directa a "¿el modelo de CST es lo más
parecido posible a la realidad?". Cada ítem se puede confirmar abriendo
la macro con un editor de texto y buscando el parámetro (todos están
declarados con `StoreParameter` cerca del principio del archivo).

| Elemento | Qué tiene la macro | Fuente del dato |
|---|---|---|
| Sustrato | RO4350B, eps_r = 3.66, tan_d = 0.0037, h = 0.76 mm | Hoja de datos Rogers (valor de **diseño**, no el de proceso 3.48 — ver nota abajo) |
| Cobre | 0.5 oz (0.0175 mm) | necesario para que la placa entre en el conector (ver FAB_NOTES.md) |
| Vías | Ø1.5 mm, paso 3.0 mm, 102 en total | tamaño confirmado por búsqueda EM, no arbitrario |
| Iris internos | `w_iris12`, `w_iris23` | calibrados por simulación EM (eigenmode), no una fórmula analítica |
| Acoplamiento externo | `w_ext` | mismo proceso de calibración |
| Conector | Taoglas EMPCB.SMAFSTJ.B.HT — pin de 0.38 mm de radio (0.76 mm de diámetro real de la hoja de datos), dieléctrico PTFE hasta 1.2639 mm, **blindaje metálico (PEC) envolviendo el PTFE** desde 1.2639 hasta 1.5639 mm, 6 mm de stub coaxial | Hoja de datos Taoglas (adjunta en el repositorio, `docs/sma_connector/`) |
| Lanzador CPWG | gap 0.2512 mm, ancho de pista 1.2 mm, 16 vías de "stitching" a tierra | resuelto para 50 Ω sobre este sustrato — **no** es el footprint recomendado por la hoja de datos del conector (que da 0.85 mm de pista), a propósito: ese ancho es el que da 50 Ω real en este sustrato |
| Puertos | **Coaxiales**, sobre la cara externa de cada stub SMA — no puertos de guía de onda sobre el microstrip | así es como se simuló el diseño real; un puerto de guía de onda sobre el microstrip mediría un problema distinto (una línea idealizada, no el conector real) |

**Nota sobre eps_r = 3.66 vs 3.48**: la hoja de datos de RO4350B trae dos
valores de constante dieléctrica. 3.48 es el valor de **especificación de
proceso** (medido con un método de laboratorio específico que subestima
el valor real por un hueco de aire en el aparato de medición). 3.66 es el
valor de **diseño** que el propio fabricante recomienda usar para calcular
líneas de microstrip/stripline. Todo este proyecto fue diseñado con 3.66 —
es el valor correcto para simular, no un error.

Todos los parámetros anteriores están fijados como `StoreParameter` al
principio de la macro, así que se pueden inspeccionar (y, si hace falta,
volver a calcular a mano) sin tener que correr nada.

## 7.1 ¿Tenemos la referencia de 50 Ω?

Sí, y se puede verificar sin correr CST, con la fórmula estándar de
impedancia característica de un coaxial:

$$Z_0 = \frac{60}{\sqrt{\varepsilon_r}} \ln\left(\frac{r_{out}}{r_{in}}\right)$$

Con los valores reales del conector (pin $r_{in}=0.38$ mm, PTFE hasta
$r_{out}=1.2639$ mm, $\varepsilon_r=2.08$):

$$Z_0 = \frac{60}{\sqrt{2.08}} \ln\left(\frac{1.2639}{0.38}\right) = 49.997\ \Omega$$

Es decir: el radio del PTFE (1.2639 mm) **no es un número cosmético** —
se calculó exactamente para que este coaxial dé 50 Ω, la misma cuenta que
ya está documentada en `topologies/launch.py`. Lo que arreglaba el error
del §3.0 (el blindaje faltante) no era esta cuenta -- ya estaba bien --
sino que sin un conductor metálico real envolviendo el PTFE, el puerto de
CST no tenía ninguna pared conductora contra la cual esa impedancia
pudiera referenciarse, y por eso el resultado salía roto (ver §7.2) aunque
el coaxial en sí ya estaba dimensionado en 50 Ω desde el principio.

## 7.2 Qué pasa si se corre con una versión vieja (referencia, no repetir)

Ya se probó: con una versión anterior de este `.bas` (no queda del todo
claro cuál de los dos errores del §3.0 tenía sin corregir), el resultado
en CST fue S1,1 pegado a 0 dB en **toda** la banda 2.0–3.6 GHz (mejor caso
apenas −0.37 dB) y S2,1 entre −30 y −95 dB — el puerto refleja casi toda
la potencia y el filtro real (que sí existe, calibrado y con la geometría
correcta) queda enterrado debajo de esa desadaptación. No indica ningún
problema con Palace ni con el diseño.

Se identificaron dos causas posibles, ambas explicadas en el §3.0:

1. **Falta de blindaje del coaxial** — confirmado por inspección directa
   del archivo que efectivamente se corrió: no tenía `sma_in_shield`.
2. **Pared inferior del dominio mal declarada** (`.Zmin "electric"` en vez
   de `"open"`) — encontrado después, por comparación directa contra la
   lógica de Palace (que no tiene ninguna pared PEC ahí), **no** corriendo
   CST. Es un diagnóstico bien fundamentado, pero no verificado con una
   corrida real todavía, porque este entorno no tiene CST instalado para
   probarlo directamente.

Por eso conviene una corrida nueva con el archivo actual (que corrige
ambas cosas) antes de asumir que el problema está resuelto del todo — si
el resultado sigue sin parecerse al de Palace, avisar con el archivo de
resultados igual que la vez anterior; eso es información real, no un paso
de más.

\newpage

# 8. Qué hacer con los resultados

1. Exportar S1,1 y S2,1: click derecho sobre el gráfico → **Export →
   ASCII (Touchstone)** o similar, según la versión de CST.
2. Guardar también una captura del árbol del modelador (para confirmar
   visualmente que la geometría se construyó completa).
3. Devolver ambas cosas junto con cualquier diferencia notable respecto a
   los valores de la tabla del §6.
