---
documentclass: IEEEtran
classoption:
  - journal
  - twocolumn
title: >-
  Diseño, Simulación e Implementación de un Filtro Pasabanda en Tecnología
  de Guía de Onda Integrada en Sustrato (SIW) a 2.87 GHz
author: "\\vspace{-2em}"
date: 2026
abstract: |
  Se presenta el diseño, la simulación electromagnética y la preparación para
  fabricación de un filtro pasabanda de tercer orden en tecnología de guía de
  onda integrada en sustrato (SIW), centrado en 2.87 GHz (banda S), con
  respuesta de Chebyshev de 5 % de ancho de banda fraccional y 0.1 dB de rizado,
  sobre Rogers RO4350B de 0.76 mm. Una primera iteración analítica, verificada
  con openEMS y CST, reprodujo la banda pero no la adaptación: los puertos de
  openEMS no entregan un $S_{11}$ confiable. El trabajo pasó entonces a Palace,
  un solver de elementos finitos de código abierto con puertos modales,
  controlado desde una cadena de herramientas propia en Python. Se modeló el
  conector SMA real con un lanzador CPWG adaptado, se exploraron varias
  topologías (cavidad de modo dual N=2, geometrías alternativas y variantes
  N=4) y se reemplazó la optimización bayesiana global, que falla porque el
  ancho de banda del filtro ensamblado es discontinuo, por calibración de
  acoplamientos sobre estructuras pequeñas e inversión. El diseño fabricado
  (N=3, vías de 1.5 mm con paso de 3.0 mm) centra la banda en 2.876 GHz, con
  182 MHz de ancho de banda, pérdida de inserción de 1.70 dB y
  $|S_{11}| = -11.2$ dB en el peor punto de la banda. No alcanza la
  especificación de $-16$ dB, y un ajuste de matriz de acoplamiento explica por
  qué. La placa fue enviada a fabricar a JLCPCB; las mediciones se agregarán
  al recibirla.
bibliography: references.bib
csl: ieee-jestpe.csl
header-includes:
  - \usepackage[spanish]{babel}
  - \usepackage{graphicx}
  - \usepackage{amsmath}
  - \usepackage{placeins}
  - \IEEEoverridecommandlockouts
  - \IEEEspecialpapernotice{\includegraphics[width=2.8cm]{logo_UTN.pdf}}
  - |
    \makeatletter
    \AtBeginDocument{%
      \let\savedtitle\@title
      \def\@title{\savedtitle\\[4pt]{\normalsize\itshape Informe --- Medidas Electrónicas 2}}%
      \def\@author{%
        \parbox{\textwidth}{\centering
          Borello, Federico\IEEEauthorrefmark{1},\;
          Calvino, Franco\IEEEauthorrefmark{1},\;
          Pereyra, Nicolás\IEEEauthorrefmark{1}\\[2pt]
          {\small\IEEEauthorrefmark{1}Universidad Tecnológica Nacional --- Facultad Regional Buenos Aires}%
        }%
      }%
    }
    \makeatother
---

> **Cómo leer este informe (actualizado 2026-09-29).** Las Secciones II a VIII
> documentan la **primera iteración** (junio de 2026): diseño analítico con vías
> de 0.8 mm y paso de 1.5 mm, openEMS, CST y una primera optimización con
> Palace. Se conservan porque explican las decisiones posteriores. Desde la
> Sección IX se describe la evolución hasta el **diseño fabricado**: vías de
> 1.5 mm con paso de 3.0 mm, conector SMA real, calibración e inversión, y
> verificación final.


```{=latex}
\begin{IEEEkeywords}
banda S, filtro pasabanda, guía de onda integrada en sustrato, SIW,
cavidades resonantes, síntesis de Chebyshev, simulación electromagnética,
Palace, optimización bayesiana
\end{IEEEkeywords}
```

# Introducción

La tecnología de guía de onda integrada en sustrato (SIW, del inglés
*Substrate Integrated Waveguide*) permite implementar estructuras de guía de
onda rectangular sobre sustrato laminado de microondas, combinando el bajo
costo y la integrabilidad de los circuitos planos con el alto factor de calidad
y la capacidad de manejo de potencia de las guías de onda metálicas
[@deslandes2001integrated; @bozzi2011review]. Una guía SIW se forma confinando
el campo entre dos filas de vías metalizadas que conectan los planos de masa
superior e inferior, emulando las paredes laterales de una guía rectangular.

Los filtros pasabanda constituyen un bloque fundamental en cualquier cadena de
recepción o transmisión de radiofrecuencia. En este trabajo se diseña un filtro
SIW de tercer orden centrado en $f_0 = 2.87$ GHz, con una respuesta de
Chebyshev de ancho de banda fraccional $\text{FBW} = 5\%$ y rizado de 0.1 dB.
La Tabla \ref{tab:specs} resume las especificaciones de partida.

```{=latex}
\begin{table}[t]
\centering
\caption{Especificaciones del filtro}
\label{tab:specs}
\begin{tabular}{ll}
\hline
\textbf{Parámetro} & \textbf{Valor} \\
\hline
Frecuencia central $f_0$ & 2.87 GHz \\
Orden $N$ & 3 cavidades \\
Ancho de banda fraccional & 5 \% \\
Rizado (Chebyshev) & 0.1 dB \\
Sustrato & Rogers RO4350B \\
Espesor $h$ & 0.76 mm \\
Permitividad $\varepsilon_r$ & 3.66 \\
Tangente de pérdidas $\tan\delta$ & 0.0037 \\
Diámetro de vía $d$ & 0.8 mm (1ª iter.) / 1.5 mm (final) \\
Paso de vía $p$ & 1.5 mm (1ª iter.) / 3.0 mm (final) \\
\hline
\end{tabular}
\end{table}
```

# Síntesis del filtro

El punto de partida es el prototipo pasabajos de Chebyshev, cuyos valores
normalizados $g_i$ se obtienen por recursión [@hong2001microstrip]. Para
$N = 3$ y rizado de 0.1 dB resultan $g_1 = g_3 = 1.0316$, $g_2 = 1.1474$ y
$g_4 = 1.0$.

A partir de estos valores se calculan los coeficientes de acoplamiento entre
cavidades adyacentes y el factor de calidad externo de los puertos de entrada
y salida:

$$ k_{i,i+1} = \frac{\text{FBW}}{\sqrt{g_i \, g_{i+1}}}, \qquad
   Q_e = \frac{g_0 \, g_1}{\text{FBW}}. $$

Con $\text{FBW} = 0.05$ se obtienen $k_{12} = k_{23} = 0.0460$ y
$Q_e = 20.63$. Estos parámetros son independientes de la frecuencia y de la
implementación física, y constituyen el objetivo que debe reproducir la
geometría SIW.

Conviene destacar que, al ser el rizado de solo 0.1 dB, la banda de paso de
$|S_{21}|$ aparenta ser de máxima planicidad: una variación de 0.1 dB resulta
visualmente imperceptible en escala logarítmica. El carácter equirizado
(Chebyshev) se manifiesta en cambio en $|S_{11}|$, que presenta exactamente
$N = 3$ ceros de reflexión con picos de igual nivel ($\approx -15.5$ dB), firma
inequívoca de una respuesta de Chebyshev y no de Butterworth.

# Diseño geométrico

El ancho equivalente de la guía SIW se elige para que la frecuencia de corte
del modo fundamental TE10 quede en $f_c \approx 0.7\,f_0$, operando así cerca
de $1.4\,f_c$ donde la guía es monomodo y de bajas pérdidas:

$$ a_{\text{eff}} = \frac{c}{2 \, f_c \, \sqrt{\varepsilon_r}}. $$

La separación física entre filas de vías se corrige según la fórmula de
Cassivi--Wu [@cassivi2002dispersion]:

$$ a_{\text{siw}} = a_{\text{eff}} + \frac{d^2}{0.95 \, p}. $$

La longitud de cada cavidad se obtiene de la condición de resonancia del modo
TE101:

$$ f_{101} = \frac{c}{2\sqrt{\varepsilon_r}}
   \sqrt{\left(\frac{1}{a_{\text{eff}}}\right)^2 +
         \left(\frac{1}{L}\right)^2}. $$

Las reglas de diseño de las vías ($0.5 \le p/d \le 2.5$ y $d < \lambda_g/5$)
se verifican para evitar fugas por radiación entre vías. La Tabla
\ref{tab:dim} resume las dimensiones resultantes; la Fig. \ref{fig:layout}
muestra la vista superior del layout.

```{=latex}
\begin{table}[t]
\centering
\caption{Dimensiones físicas del filtro}
\label{tab:dim}
\begin{tabular}{ll}
\hline
\textbf{Dimensión} & \textbf{Valor} \\
\hline
Ancho equivalente $a_{\text{eff}}$ & 39.00 mm \\
Separación de vías $a_{\text{siw}}$ & 39.45 mm \\
Longitud de cavidad $L_{\text{cav}}$ & 38.23 mm \\
Ancho de iris $w_{12} = w_{23}$ & 13.66 mm \\
Ancho de microstrip 50 $\Omega$ & 1.664 mm \\
\hline
\end{tabular}
\end{table}
```

![Vista superior del layout inicial (primera iteración) del filtro SIW: cavidades resonantes formadas por filas de vías, iris inductivos de acoplamiento y transiciones microstrip de entrada y salida. Dimensiones analíticas: $a_{\text{siw}} = 39.45$ mm, $L_{\text{cav}} = 38.23$ mm, $w_{12} = w_{23} = 13.66$ mm, $W_{\text{ms}} = 1.66$ mm.](layout_init.png){#fig:layout width=88%}

# Calibración electromagnética con openEMS

Las fórmulas cerradas para el ancho de iris en SIW son poco confiables, por lo
que el acoplamiento se extrae mediante simulación de onda completa con openEMS
[@liebig2013openems]. Se simula una estructura de dos cavidades acopladas por
un iris de ancho variable; del par de modos resonantes desdoblados $(f_1, f_2)$
se obtiene el coeficiente de acoplamiento:

$$ k = \frac{f_2^2 - f_1^2}{f_2^2 + f_1^2}. $$

Ajustando $w(k)$ se determina que el acoplamiento objetivo $k = 0.046$ se
consigue con un iris de $w = 13.66$ mm, valor notablemente mayor que la
estimación analítica inicial, lo que confirma la necesidad de la calibración.

## Verificación de la longitud de cavidad

La longitud de cavidad se verifica con simulación de onda completa. Conviene
distinguir dos modelos de excitación, ya que conducen a conclusiones diferentes:

- Un modelo de **puertos concentrados** (sondas de 50 $\Omega$ dentro de la
  cavidad) permite ubicar la resonancia de forma rápida y económica, pero no
  incluye la carga del alimentador real; resulta sesgado en frecuencia y su
  nivel absoluto de $|S_{21}|$ no es representativo.
- El modelo **físico**, con alimentación microstrip de 50 $\Omega$ adaptada
  mediante una transición cónica (taper) microstrip--SIW
  [@deslandes2006accurate], reproduce las condiciones de medición y es el que se
  toma como referencia.

Con el feed adaptado, openEMS y CST coinciden: la longitud analítica de
$L_{\text{cav}} = 38.23$ mm ubica el centro de la banda de paso en 2.82 GHz
(openEMS, $-3$ dB) / 2.905 GHz (pico) y 2.818 GHz (CST), todos a menos de
50 MHz del objetivo de 2.87 GHz. Es decir, el
cálculo analítico de la longitud de cavidad es adecuado y **no requiere
corrección apreciable**; acortar la cavidad desplazaría la banda por encima del
objetivo, como muestra la Tabla \ref{tab:sweep} y la Fig. \ref{fig:cmpall}.

```{=latex}
\begin{table}[t]
\centering
\caption{Barrido de $L_{\text{cav}}$ con feed microstrip adaptado (openEMS)}
\label{tab:sweep}
\begin{tabular}{cc}
\hline
$L_{\text{cav}}$ (mm) & $f_{\text{centro}}$ (GHz) \\
\hline
\textbf{38.23} & \textbf{2.905} \\
35.93 & 2.982 \\
33.64 & 3.077 \\
\hline
\end{tabular}
\end{table}
```

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.86\textwidth]{compare_all.png}
\caption{Barrido de la longitud de cavidad en openEMS con alimentación
microstrip adaptada (res.\ media), comparado con la respuesta objetivo de
síntesis y con la simulación de CST. La longitud analítica de 38.2 mm (curva en
banda) coincide con el objetivo, validando el diseño.}
\label{fig:cmpall}
\end{figure*}
```

Con el feed adaptado y la longitud analítica, openEMS reproduce una banda de
paso de tres polos con una pérdida de inserción de unos pocos decibelios,
comparable a la de CST, confirmando la validez del diseño tanto en frecuencia
como en forma de respuesta.

# Modelo 3D en CST Studio Suite 2021

A partir de las dimensiones se construye el modelo tridimensional
paramétrico en CST Studio Suite 2021 mediante una macro generada
automáticamente. El modelo está compuesto por sólidos nativos (sustrato,
planos de masa, vías metalizadas y transiciones microstrip), con todas las
dimensiones almacenadas como parámetros editables, de modo que el diseño puede
re-sintonizarse directamente en el entorno gráfico. Las Figs. \ref{fig:cst1},
\ref{fig:cst2} y \ref{fig:cst3} muestran distintas vistas del modelo.

La simulación de CST se realizó con la longitud de cavidad analítica
$L_{\text{cav}} = 38.23$ mm, el mismo valor validado por el barrido con feed
adaptado en openEMS.

![Vista superior del modelo 3D en CST ($a_{\text{siw}} = 39.45$ mm, $L_{\text{cav}} = 38.23$ mm, $W_{\text{ms}} = 1.66$ mm).](above.jpeg){#fig:cst1 width=88%}

![Vista en perspectiva del modelo 3D ($a_{\text{siw}} = 39.45$ mm, $L_{\text{cav}} = 38.23$ mm, $w_{12} = w_{23} = 13.66$ mm).](up.jpeg){#fig:cst2 width=88%}

![Vista lateral mostrando el espesor del sustrato ($h = 0.76$ mm) y los planos de masa ($L_{\text{cav}} = 38.23$ mm, $W_{\text{ms}} = 1.66$ mm).](height_and_plane.jpeg){#fig:cst3 width=88%}

# Resultados y comparación

La Fig. \ref{fig:compare} superpone la respuesta objetivo de síntesis con la
simulación de CST. Las Figs. \ref{fig:s11} y \ref{fig:s21} muestran los
parámetros $S_{11}$ y $S_{21}$ obtenidos en CST. La Tabla \ref{tab:res}
resume la comparación cuantitativa.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.86\textwidth]{compare.png}
\caption{Comparación de la respuesta objetivo de síntesis (líneas
discontinuas) con la simulación de CST (líneas continuas, $L_{\text{cav}} =
38.23$ mm, $w_{12} = w_{23} = 13.66$ mm, $W_{\text{ms}} = 1.66$ mm), para
$|S_{11}|$ (superior) y $|S_{21}|$ (inferior).}
\label{fig:compare}
\end{figure*}
```

```{=latex}
\begin{table}[t]
\centering
\caption{Comparación síntesis vs. simulación CST ($L_{\text{cav}} = 38.23$ mm analítico)}
\label{tab:res}
\begin{tabular}{lcc}
\hline
\textbf{Parámetro} & \textbf{Objetivo} & \textbf{CST} \\
\hline
Frecuencia central & 2.870 GHz & 2.818 GHz \\
Ancho de banda ($-3$ dB) & 143 MHz & 293 MHz \\
Pérdida de inserción & $\sim$0 dB & 3.65 dB \\
Pérdida de retorno & $>$16 dB & 1.02 dB \\
\hline
\end{tabular}
\end{table}
```

![Parámetro $S_{11}$ simulado en CST ($L_{\text{cav}} = 38.23$ mm, $a_{\text{siw}} = 39.45$ mm, $w_{12} = w_{23} = 13.66$ mm, $W_{\text{ms}} = 1.66$ mm).](s11.jpeg){#fig:s11 width=88%}

![Parámetro $S_{21}$ simulado en CST ($L_{\text{cav}} = 38.23$ mm, $a_{\text{siw}} = 39.45$ mm, $w_{12} = w_{23} = 13.66$ mm, $W_{\text{ms}} = 1.66$ mm).](s21.jpeg){#fig:s21 width=88%}

La simulación de CST confirma una respuesta pasabanda con tres polos, en
concordancia con el orden $N = 3$ del diseño. La frecuencia central (2.818 GHz)
queda a unos 50 MHz del objetivo, dentro de la tolerancia esperable entre la
síntesis y la simulación de onda completa, y coincide con la predicción de
openEMS para la misma longitud de cavidad. El ancho de banda resulta más
amplio que el objetivo porque el acoplamiento externo $Q_e$, provisto por las
transiciones microstrip, aún no fue calibrado electromagnéticamente y se
encuentra sobreacoplado. La pérdida de inserción ($3.65$ dB en CST y unos pocos
decibelios en el modelo microstrip adaptado de openEMS) combina una leve
desadaptación residual con la pérdida dieléctrica propia del sustrato
($\tan\delta = 0.0037$); ambos simuladores coinciden en el orden de magnitud.

# Ajuste paramétrico y sintonización

El diseño de un filtro de cavidades acopladas admite dos grados de libertad de
sintonización prácticamente independientes, que se están explorando de forma
iterativa sobre el modelo paramétrico de CST.

## Frecuencia central y longitud de cavidad

La frecuencia central la fija la resonancia TE101 de cada cavidad, dominada por
la longitud $L_{\text{cav}}$. De la relación de resonancia se desprende que al
alargar la cavidad la frecuencia baja, y viceversa. El barrido con feed
adaptado de la Sección IV cuantifica esta sensibilidad: entre 33.64 mm y
38.23 mm la frecuencia central varía de 3.077 GHz a 2.905 GHz, es decir, una
pendiente de $\approx -37$ MHz/mm. Esta relación casi lineal permite centrar la
banda con un único ajuste de $L_{\text{cav}}$ sin alterar el resto del filtro.

## Ancho de banda y acoplamientos

El ancho de banda lo determina la intensidad de los acoplamientos, que escalan
con el ancho de banda fraccional: los acoplamientos internos cumplen
$k_{i,i+1} \propto \text{FBW}$ y el factor de calidad externo
$Q_e \propto 1/\text{FBW}$. En consecuencia existen dos perillas:

- Los **iris internos** ($w_{12}, w_{23}$): un iris más ancho aumenta $k$ y
  ensancha la banda; uno más angosto la estrecha.
- El **iris externo** de entrada/salida, que fija $Q_e$: una apertura más
  angosta debilita el acoplamiento al alimentador (aumenta $Q_e$) y estrecha la
  banda.

La simulación de CST arroja un ancho de banda de 293 MHz, aproximadamente el
doble del objetivo de 143 MHz, lo que indica que el acoplamiento externo está
sobreacoplado ($Q_e$ resulta cercano a la mitad del valor de síntesis). Para
corregirlo se introdujo en el modelo un iris inductivo de entrada/salida
parametrizable (apertura $w_{\text{ext}}$): una fila transversal de vías con un
hueco central ajustable que regula $Q_e$. Reduciendo $w_{\text{ext}}$ se
incrementa $Q_e$ y se estrecha la banda hacia el objetivo. Como regla de orden
de magnitud, para pasar de 293 MHz a 143 MHz se requiere aproximadamente la
mitad del acoplamiento interno y el doble de $Q_e$.

Se intentó calibrar $Q_e$ en openEMS por el método del retardo de grupo de
$S_{11}$, pero la limitación de fondo apareció antes: **los puertos de openEMS no
entregan un $S_{11}$ confiable** para esta estructura. El puerto concentrado
radia (se comporta como una fuente puntual, no como el modo distribuido de la
microstrip) y el puerto de microstrip (MSLPort) lanza bien el modo pero su
de-embedding del $S_{11}$ es inestable (se obtuvieron incluso $|S_{11}| > 1$, no
físico). En síntesis, openEMS es útil para el $S_{21}$ y el centro de la banda,
pero no para ajustar la adaptación. Por ello se cambió de herramienta para la
optimización.

# Optimización electromagnética con Palace

Para ajustar la adaptación se recurrió a **Palace**, un solver de elementos
finitos (FEM) de código abierto [@palace2023] que implementa **puertos modales
(wave ports)**: resuelve el modo 2D en la sección del puerto, igual que CST. A
diferencia de los puertos de openEMS, este enfoque es pasivo por construcción y
entrega un $S_{11}$ confiable. Como verificación previa, se simuló en Palace la
geometría de la primera iteración (sin $w_{\text{ext}}$) y se comparó con la
simulación de CST: ambas respuestas coinciden, validando a Palace como sustituto
fiel de CST para el lazo de optimización.

Una vez validado, se ejecutó una **optimización automática** (descenso por
coordenadas) sobre seis variables: las longitudes de cavidad, los iris internos
$w_{12}=w_{23}$, el iris externo $w_{\text{ext}}$ y el alimentador
($W_{\text{ms}}$, $L_{\text{taper}}$). La función objetivo penaliza la desviación
del centro respecto de 2.87 GHz y, sobre todo, el peor $|S_{11}|$ dentro de la
banda objetivo. De este proceso se desprende un resultado físico relevante: las
cavidades reales deben ser **más cortas** que el valor analítico
($\approx 34.4$ mm frente a 38.2 mm), porque los tapers de microstrip y los iris
externos cargan las cavidades y bajan su resonancia; el cálculo analítico, que
supone paredes ideales, no captura esa carga. La Tabla \ref{tab:opt} resume las
dimensiones finales optimizadas.

```{=latex}
\begin{table}[t]
\centering
\caption{Dimensiones finales optimizadas con Palace}
\label{tab:opt}
\begin{tabular}{lcc}
\hline
\textbf{Dimensión} & \textbf{1ra iter. (analítico)} & \textbf{Final (Palace)} \\
\hline
$L_{\text{cav}}$ & 38.23 mm & 34.40 mm \\
$w_{12} = w_{23}$ & 13.66 mm & 13.00 mm \\
$w_{\text{ext}}$ & sin iris & 16.00 mm \\
$W_{\text{ms}}$ & 1.66 mm & 2.26 mm \\
$L_{\text{taper}}$ & 15.46 mm & 15.46 mm \\
\hline
\end{tabular}
\end{table}
```

La Fig. \ref{fig:layoutopt} muestra el layout final optimizado; comparada con la
Fig. \ref{fig:layout} (primera iteración) se aprecian las cavidades más cortas y
el iris externo más cerrado.

![Vista superior del layout final optimizado con Palace: cavidades más cortas que la primera iteración y con el iris externo $w_{\text{ext}}$ que fija $Q_e$. Dimensiones: $a_{\text{siw}} = 39.45$ mm, $L_{\text{cav}} = 34.40$ mm, $w_{12} = w_{23} = 13.00$ mm, $w_{\text{ext}} = 16.00$ mm, $W_{\text{ms}} = 2.26$ mm.](layout_opt.png){#fig:layoutopt width=88%}

La Fig. \ref{fig:cmpfinal} compara, en una misma gráfica, la respuesta objetivo
de síntesis, la primera iteración de CST, la simulación de openEMS (ambas a
$L_{\text{cav}} = 38.23$ mm, sin $w_{\text{ext}}$) y el diseño final optimizado
con Palace. El diseño final centra la banda en 2.87 GHz y lleva la pérdida de
retorno en banda por debajo de $-16$ dB, frente a la fuerte desadaptación y el
sobre-ancho de la primera iteración.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.92\textwidth]{compare_final.png}
\caption{Comparación de $|S_{11}|$ (superior) y $|S_{21}|$ (inferior): objetivo
de síntesis; primera iteración de CST y openEMS, ambas con $L_{\text{cav}} =
38.23$ mm, $w_{12}=w_{23}=13.66$ mm y sin iris externo; y diseño final
optimizado con Palace ($L_{\text{cav}} = 34.4$ mm, $w_{12}=w_{23}=13.0$ mm,
$w_{\text{ext}} = 16.0$ mm, $W_{\text{ms}} = 2.26$ mm).}
\label{fig:cmpfinal}
\end{figure*}
```

## Discusión de la respuesta final

> **Corrección posterior (agosto de 2026).** Este resultado se obtuvo con un
> puerto modal colocado directamente sobre la microstrip, que se normaliza a la
> impedancia de la propia pista. Al reemplazarlo por un modelo 3D del conector
> SMA real (Sección X) se comprobó que el ancho optimizado $W_{	ext{ms}} =
> 2.26$ mm corresponde a una línea de $\approx 41~\Omega$, no de 50 $\Omega$: el
> optimizador había aprovechado un defecto del puerto. El ancho correcto de
> 50 $\Omega$ es 1.664 mm, y con el conector real este diseño mide
> $\approx -4.6$ dB. Los valores de esta sección son válidos solo para ese
> modelo de puerto.

El diseño final centra la banda en 2.87 GHz y consigue $|S_{11}| < -16$ dB. Su
ancho de banda de $-3$ dB es de $\approx 277$ MHz (FBW $\approx 9.7\%$), algo
mayor que el valor nominal de síntesis de 143 MHz (5\%). El ancho de banda **no
es un requisito estricto** en esta aplicación, y la diferencia es moderada; la
optimización privilegió deliberadamente el centrado y la adaptación en banda
($|S_{11}| < -16$ dB), que sí son los objetivos críticos. En otras palabras, se
aceptó una banda algo más ancha a cambio de una mejor adaptación, un compromiso
razonable. Conviene notar que el ancho lo gobiernan los acoplamientos y no la
longitud: para estrecharlo hacia el 5\% bastaría con **reducir en conjunto** el
iris interno $w_{12}=w_{23}$ (baja $k$) y el externo $w_{\text{ext}}$ (sube
$Q_e$), mientras que $L_{\text{cav}}$ solo recentra. Ese ajuste fino del ancho
queda disponible como refinamiento sin comprometer lo ya logrado.

Dos rasgos más de la respuesta merecen justificación. Primero, el $|S_{21}|$ no
alcanza 0 dB sino $\approx -1.5$ dB: es la pérdida de inserción, dominada por la
pérdida dieléctrica. Para un filtro angosto la estimación analítica es
$\text{IL} \approx 4.343\,\sum g_i / (Q_u\,\text{FBW}) \approx 1$ dB con
$Q_u \approx 270$ (factor de calidad descargado fijado por $\tan\delta = 0.0037$,
medido por análisis modal en Palace); el valor simulado es consistente. Segundo,
un barrido de banda ancha (0.5--6 GHz) revela una **banda espuria** en torno a
4.5 GHz: corresponde a los modos de orden superior de las cavidades
(TE$_{102}$/TE$_{201}$, a $\approx 1.5$--$1.7\,f_0$), fenómeno inherente a los
resonadores SIW [@bozzi2011review] y ajeno a la especificación a 2.87 GHz.

## Verificación en CST del diseño optimizado

El diseño final se exporta a CST Studio Suite 2021 mediante la macro paramétrica
generada automáticamente, de modo que la geometría optimizada se reconstruye con
un único paso. La Fig. \ref{fig:cstfinal} muestra la simulación de CST del diseño
optimizado (idénticas dimensiones: $L_{\text{cav}}=34.4$ mm, $w_{12}=w_{23}=13.0$ mm,
$w_{\text{ext}}=16.0$ mm) superpuesta con la respuesta de Palace y el objetivo de
síntesis.

La concordancia entre CST y Palace es muy buena, lo que valida toda la cadena de
diseño (síntesis $\rightarrow$ Palace $\rightarrow$ optimización). CST sitúa el
centro (criterio $-3$ dB) en **2.858 GHz** ($-12$ MHz respecto de 2.87 GHz), con un
$|S_{11}|$ de $-20.9$ dB en el centro de banda y una pérdida de inserción medida de
$|S_{21}| = -1.19$ dB en el pico. Este valor de inserción confirma cuantitativamente
el piso de pérdida estimado ($\approx 1$ dB, dominado por $\tan\delta = 0.0037$). El
$|S_{21}|$ de ambos solvers prácticamente se calca; la diferencia más visible está en
el $|S_{11}|$, donde CST presenta un único pozo profundo centrado mientras Palace
resuelve los dos pozos del Chebyshev de orden 3, una discrepancia atribuible a la
malla y al de-embedding del puerto, no al diseño. El ancho de banda de $-3$ dB en CST
es de 234 MHz, algo más angosto que en Palace (277 MHz) y en la dirección del
objetivo de síntesis.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.92\textwidth]{compare_cst_v2.png}
\caption{Verificación en CST del diseño optimizado ($L_{\text{cav}} = 34.4$ mm,
$w_{12}=w_{23}=13.0$ mm, $w_{\text{ext}} = 16.0$ mm, $W_{\text{ms}} = 2.26$ mm):
$|S_{11}|$ y $|S_{21}|$ de CST (rojo) superpuestos con la simulación de Palace
(\texttt{palace.s2p}, azul) y el objetivo de síntesis (\texttt{target.s2p}, punteado).
CST: centro $-3$ dB en 2.858 GHz, $|S_{11}|=-20.9$ dB y $|S_{21}|=-1.19$ dB en banda.}
\label{fig:cstfinal}
\end{figure*}
```

# Herramientas y método

## De openEMS a Palace

openEMS se abandonó por tres motivos:

- **Puertos.** Sus puertos no entregan un $S_{11}$ confiable para esta
  estructura (Sección VII), y la adaptación era justamente lo que faltaba
  ajustar.
- **Costo de cómputo.** El método FDTD representa las vías cilíndricas con una
  grilla escalonada que exige al menos tres celdas por diámetro en toda la
  placa. Además, el filtro resonante de alto $Q$ tarda en decaer. Cada
  corrida completa llevaba de minutos a decenas de minutos.
- **Sin solver de autovalores.** No tiene solver de modos propios para calibrar
  acoplamientos, que debían estimarse leyendo picos en barridos excitados.

Palace [@palace2023], basado en MFEM [@anderson2021mfem] y con mallas de gmsh
[@geuzaine2009gmsh], resolvió los tres problemas:

- la malla tetraédrica se ajusta a las vías;
- los puertos modales son pasivos por construcción;
- incluye un solver de autovalores;
- se controla íntegramente con archivos JSON.

## Cadena de herramientas en Python

Todo el flujo se implementó como un paquete de Python con una única
herramienta de línea de comandos (`siw`). Esa herramienta cubre síntesis,
layout, simulaciones de autovalores y excitadas, optimización bayesiana,
barridos, calibraciones y exportación a KiCad y CST. Los diseños validados se
guardan junto con sus parámetros S y el comando que los reproduce.

La optimización usa un proceso gaussiano (scikit-optimize
[@skopt; @jones1998efficient]). Evalúa con malla gruesa, confirma con malla
fina y descarta candidatos no resonantes antes de cada simulación completa.
Su función objetivo pasó por diez versiones.

## GPU y CPU

Para acelerar la búsqueda, el trabajo se trasladó a una estación con una GPU
NVIDIA GTX 1660 SUPER de 6 GB, con Palace compilado con soporte de GPU.

La GPU fue 1.24 veces más rápida que 4 procesos de CPU en el filtro de modo
dual, con parámetros S idénticos. Sin embargo, 6 GB limitan el modelo a unos
176 mil tetraedros. La cascada de 166 mm excede ese límite con cualquier malla
adecuada, y la verificación final (315 mil incógnitas, $\approx$5.5 GB) tampoco
entra en la GPU. Todas las corridas de producción terminaron ejecutándose en
CPU con 4 procesos MPI, en una máquina de 16 GB. Una máquina de 3.7 GB fue
insuficiente: cuatro intentos terminaron por falta de memoria. La memoria, y
no la velocidad de cálculo, fue siempre la restricción dominante.

# Conector SMA real y lanzador CPWG

Hasta este punto los puertos se ubicaban directamente sobre la microstrip. Al
modelar en 3D el conector de borde Taoglas EMPCB.SMAFSTJ.B.HT
[@taoglas_sma], con pin, dieléctrico de PTFE y blindaje, aparecieron dos
problemas:

1. El ancho de microstrip optimizado en junio (2.26 mm) resultó ser una línea
   de $\approx 41~\Omega$. El ancho correcto de 50 $\Omega$ es 1.664 mm
   [@hammerstad1980accurate].
2. Un pin de tamaño de cable (0.82 mm) es más grueso que la placa (0.76 mm) y
   cortocircuita el lanzador ($|S_{11}| \approx -0.2$ dB), como muestra la
   Fig. \ref{fig:sma}.

Se usó el pin real del conector (0.38 mm de radio). En el borde de la placa
se sintetizó un lanzador CPWG de 50 $\Omega$ dentro de la huella del conector
[@wadell1991transmission; @simons2001coplanar]: pista de 1.2 mm, ranura de
0.2512 mm y vías de costura a masa.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_sma_v1.png}
\caption{Primer modelo con conector real: el puerto ideal ocultaba una
alimentación de 41\,$\Omega$, y un pin de tamaño de cable cortocircuita el
lanzador.}
\label{fig:sma}
\end{figure}
```

# Exploración de topologías y longitudes

Con el objetivo de reducir el tamaño de la placa se exploraron varias
topologías (Figs. \ref{fig:layouts} y \ref{fig:designs}). Las vías pasaron a
1.5 mm de diámetro con paso de 3.0 mm. Tres búsquedas independientes, con tres
funciones objetivo distintas, confirmaron esa elección frente a vías de
0.8 mm.

**Longitudes de cavidad ensayadas.** La evolución de las longitudes fue la
siguiente:

- 38.23 mm: valor analítico.
- 35.93 y 33.64 mm: barrido en openEMS, con una pendiente de
  $\approx -37$ MHz/mm.
- $\approx$34.4 mm: primera optimización con Palace, que incluye la carga de
  los tapers.
- 34.24/35.50/34.24 mm: cavidades desiguales obtenidas por calibración e
  inversión.
- 33.94/35.50/33.94 mm: recorte final de las cavidades extremas. También se
  probó $-0.6$ mm, que ganó solo 0.07 dB y agregó 0.4 dB de pérdida en el
  borde de banda.

La sensibilidad medida en las cavidades extremas fue de $\approx$27 MHz/mm.

**Longitudes de placa.** Los candidatos y sus largos fueron:

- modo dual N=2: 119 mm;
- cascada N=3: 166 mm;
- cascada N=4: 211 mm;
- cascada de cuatro cavidades monomodo: 180--206 mm.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_layouts.png}
\caption{(a) Filtro de modo dual N=2 de una sola cavidad. (b) Cascada N=3
fabricada, con aperturas externas en rojo y las huellas CPWG/SMA en los
bordes.}
\label{fig:layouts}
\end{figure*}
```

## Filtro de modo dual N=2

Una única cavidad cuadrada ($a = 57.16$ mm) soporta el par degenerado
TE$_{102}$/TE$_{201}$. Una fila flotante de vías interna separa y acopla ese
par [@shen2009dualmode; @xu2014hexagonal], de modo que se obtienen dos polos
con una sola cavidad y la placa se reduce a 119 mm.

Con el lanzador CPWG real, su mejor respuesta es $f_c = 2.904$ GHz, 316.6 MHz
de ancho de banda, $-10.76$ dB de adaptación y 1.45 dB de pérdida de
inserción. Los barridos sobre el filtro ensamblado muestran que en esta
topología el ancho de banda y la adaptación se oponen en todos los
parámetros. Con $w_{\text{iris}} = 11$ mm la banda mide 145.6 MHz, pero la
adaptación cae a $-1.75$ dB. Un acoplamiento interno y uno externo no alcanzan
para ubicar dos polos y adaptarlos a la vez.

La cascada N=3 agrega un grado de libertad, a costa de 1.4 veces el largo, y
ganó la comparación directa. Otras tres cavidades únicas (esquina recortada,
circular con cruz y rómbica) no superaron al modo dual: su mejor $S_{11}$
estuvo entre $-6$ y $-9$ dB. La variante compacta N=4 con dos cavidades de modo
dual quedó cerrada: cinco mecanismos distintos más una búsqueda conjunta se
detuvieron en 2 de 4 polos.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_designs.png}
\caption{Mejor diseño de cada topología con el mismo lanzador CPWG + SMA
(Palace).}
\label{fig:designs}
\end{figure*}
```

# Calibración e inversión en lugar de búsqueda global

Aplicada al filtro ensamblado, la optimización bayesiana global nunca superó
$-5$ dB de adaptación en más de 60 evaluaciones. La causa es estructural. El
ancho de banda es **discontinuo** en la apertura externa: por debajo de un
umbral de acoplamiento solo el polo central supera $-3$ dB, y por encima los
tres polos se unen. En la cascada N=3 se midieron 16, 22, 36, 65 y luego
215 MHz, con el objetivo de 143.5 MHz dentro del salto. Un proceso gaussiano
supone una función suave, así que no puede modelar ese salto.

El método que funcionó mide cada acoplamiento en la estructura más pequeña que
lo contiene (Fig. \ref{fig:calib}):

- **Acoplamiento interno.** Dos cavidades cerradas, resueltas como problema de
  autovalores, dan $k = (f_2^2 - f_1^2)/(f_2^2 + f_1^2)$ en función de
  $w_{\text{iris}}$ [@hong2001microstrip].
- **Acoplamiento externo.** Una cavidad excitada por dos aperturas da el $Q$
  cargado, y de él se obtiene $Q_e = 2/(1/Q_L - 1/Q_u)$ con
  $Q_u = 1/\tan\delta = 270$.

Ambas curvas son suaves y se invierten en los valores de síntesis. Cada curva
convergió en unas tres simulaciones, y el acoplamiento interno quedó dentro
del 2 % del objetivo. La optimización bayesiana se conservó solo como pulido
local alrededor de ese resultado.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_calib.png}
\caption{(a), (b) Las magnitudes de calibración son suaves e invertibles.
(c) El ancho de banda del filtro ensamblado, que es lo que evalúa un
optimizador de caja negra, salta cuando los polos se unen.}
\label{fig:calib}
\end{figure*}
```

**Errores silenciosos.** Durante el desarrollo aparecieron numerosos defectos
de modelado. En la mayoría de los casos el defecto no generaba ningún error: la simulación convergía y el
gráfico parecía razonable, pero el número era incorrecto. Algunos ejemplos:

- anchos de iris cuantizados por la construcción de las vías
  (Fig. \ref{fig:quant});
- selección del par de modos equivocado, que daba $k$ 21 veces menor;
- caras de la malla sin condición de borde, que producían pérdidas menores que
  las de un modelo sin pérdidas;
- una macro de CST que dibujaba el lanzador 1000 veces más grande.

Cada caso dejó una verificación automática en el código. La regla más útil
fue comparar cada resultado con lo que la física permite.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_quantization.png}
\caption{Cuantización de las vías: filtrar una grilla fija hacía que distintos
anchos de iris produjeran la misma malla.}
\label{fig:quant}
\end{figure}
```

# Diseño fabricado y verificación

El diseño elegido es
$l_{\text{cav1}} = 33.939$, $l_{\text{cav2}} = 35.503$,
$w_{\text{iris}} = 14.416$, $w_{\text{ext}} = 13.96$,
$l_{\text{taper}} = 15.738$ y $W_{\text{ms}} = 1.6636$ mm, sobre una placa de
165.78 $\times$ 45.79 mm. La Tabla \ref{tab:fab} resume la simulación con
malla fina (2.5/0.45 mm, puertos coaxiales de 0.15 mm, 61 puntos).

```{=latex}
\begin{table}[t]
\centering
\caption{Diseño fabricado: simulación con malla fina frente a la especificación}
\label{tab:fab}
\begin{tabular}{lcc}
\hline
 & \textbf{Objetivo} & \textbf{Simulado}\\
\hline
Frecuencia central & 2.870 GHz & 2.876 GHz\\
Ancho de banda ($-3$ dB) & 143.5 MHz & 182.3 MHz\\
Peor $|S_{11}|$ en banda & $-16$ dB & $-11.15$ dB\\
Pérdida de inserción (pico / peor) & --- & 1.70 / 2.58 dB\\
Medido & \multicolumn{2}{c}{\emph{pendiente}}\\
\hline
\end{tabular}
\end{table}
```

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_final_trim.png}
\caption{Verificación final con malla fina: el recorte de $-0.3$ mm de las
cavidades extremas mejora el rizado interior de $-11.2$ a $-14.5$ dB.}
\label{fig:trim}
\end{figure}
```

**Por qué no alcanza $-16$ dB.** Un ajuste de matriz de acoplamiento con
pérdidas [@cameron2018microwave] indica lo siguiente:

- el acoplamiento externo está en el objetivo (+0.4 %);
- el acoplamiento interno está 4.8 % débil;
- las cavidades extremas resuenan 17 MHz por debajo.

El recorte corrige la mitad de ese desvío. El peor punto queda en el borde
superior de la banda (2.94 GHz). Terminar de corregirlo requiere mover
$w_{\text{ext}}$, $l_{\text{cav1}}$ y $w_{\text{iris}}$ de forma coordinada.

**Por qué la pérdida de inserción es alta.** En un filtro angosto,
$\text{IL} \approx 4.343\sum g_i/(\text{FBW}\,Q_u)$ [@hong2001microstrip], de
modo que la pérdida la fija el $Q$ descargado. Las simulaciones de Palace
tratan el metal como conductor perfecto, así que su $Q$ está limitado por el
dieléctrico: $Q_d = 1/\tan\delta = 270$. Los ajustes de matriz de
acoplamiento dieron entre 229 y 320, valores que rodean ese límite.

Con el ancho de banda simulado (6.3 %), $Q_u = 270$ predice 0.8 dB de
disipación, y la desadaptación de $-11$ dB agrega 0.35 dB. El resto, unos
0.5 dB, se atribuye a radiación en las secciones abiertas de microstrip, taper
y lanzador.

En la placa real el cobre reduce el $Q$: con 0.76 mm de espesor,
$Q_c \approx 540$ [@pozar2012microwave] y $Q_u \approx 180$, lo que suma unos
0.4 dB. Se espera entonces medir entre 2.2 y 2.3 dB, cerca del piso físico de
este laminado, este espesor y este ancho de banda. Un sustrato de menor
pérdida, como RT/duroid 5880 de 1.52 mm, lo reduciría a $\approx$0.5 dB.

**Verificación cruzada con CST.** Con la macro generada automáticamente, el
solver de frecuencia de CST coincide con Palace en la frecuencia central
(2.876 frente a 2.875 GHz) y en la pérdida (1.80 frente a 1.85 dB). Llegar a
ese resultado requirió diez correcciones de la macro y de la configuración, y
un modelo de control con un tramo de coaxial recto. El solver temporal de CST
nunca quedó del todo estable.

**Efecto del conector.** Las Figs. \ref{fig:launch} y \ref{fig:renders} comparan tres alimentaciones
sobre la misma geometría:

- microstrip sin conector: $-6.3$ dB;
- CPWG sin conector: $-5.1$ dB;
- CPWG con SMA, la versión fabricada: $-11.2$ dB.

El filtro fue sintonizado con la reactancia del conector incluida, de modo que
el conector forma parte del diseño.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_launch_sparams.png}
\caption{Misma geometría con tres alimentaciones distintas. Quitar el SMA
empeora la adaptación en unos 5 dB.}
\label{fig:launch}
\end{figure}
```

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.9\textwidth]{figures/fig_launch_renders.png}
\caption{Modelos 3D (Palace) de las tres alimentaciones: placa completa y
detalle del lanzador de entrada. Verde: cobre; marrón: RO4350B; amarillo:
conector SMA.}
\label{fig:renders}
\end{figure*}
```

# Fabricación

La herramienta `siw kicad` genera la placa de KiCad, los gerbers, los archivos
de taladrado, un sólido STEP y 34 verificaciones automáticas. Entre ellas se
comparan la geometría dibujada con la mallada y las posiciones de las vías de
la macro de CST con las de la malla.

JLCPCB dispone de RO4350B de 0.76 mm, pero solo ofrece cobre exterior de
1 oz [@jlcpcb_caps]. El espesor terminado en las pistas del conector queda en
$\approx$0.84 mm, frente a una ranura de 0.81 $\pm$ 0.1 mm en el conector.
Es un ajuste marginal, que se resuelve raspando 15--20 $\mu$m de cobre bajo las
patas del conector. La ausencia de máscara antisoldante queda definida por los
gerbers y se aclara en las notas del pedido. La placa fue enviada a fabricar.

# Mediciones

*[Pendiente: las placas están en fabricación. Se medirán $|S_{11}|$, $|S_{21}|$
y el retardo de grupo con un analizador vectorial de redes, entre 2.5 y
3.3 GHz y entre 0.1 y 8 GHz. Se superpondrán con la simulación de Palace y con
la de CST, y se ajustará la matriz de acoplamiento a la medición.]*

# Conclusiones y trabajo futuro

La primera iteración (openEMS y CST) validó la síntesis y el centro de la
banda, pero no la adaptación. El paso a Palace, junto con el modelado del
conector real, corrigió un error que el puerto ideal ocultaba: la alimentación
de 41 $\Omega$.

Los cambios que más influyeron en el resultado fueron dos. El primero,
reemplazar la optimización bayesiana global por la calibración de los
acoplamientos en estructuras pequeñas seguida de inversión. El segundo,
verificar sistemáticamente cada resultado contra lo que la física permite.

El filtro N=3 fabricado centra la banda a 6 MHz del objetivo, con 1.7 dB de
pérdida, cerca del límite del laminado. No alcanza la especificación de
adaptación ni de ancho de banda, por causas que identifica el ajuste de
matriz de acoplamiento.

Como trabajo futuro quedan:

- medir las placas y comparar la medición con la simulación;
- aplicar la corrección coordinada de $w_{\text{ext}}$, $l_{\text{cav1}}$ y
  $w_{\text{iris}}$;
- evaluar un laminado de menor pérdida;
- suprimir la banda espuria de 5.8--6.8 GHz con un filtro pasabajos.

```{=latex}
\FloatBarrier
\clearpage
```

# Referencias

::: {#refs}
:::
