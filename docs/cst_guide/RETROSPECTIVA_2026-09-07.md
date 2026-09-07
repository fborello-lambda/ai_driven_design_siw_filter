# Retrospectiva: cómo se llegó a un Frequency Domain solver que funciona

Resumen conciso de la sesión CST del 6-7 de septiembre de 2026: qué estaba roto,
qué se probó, qué terminó arreglando el problema real. Contexto completo en
`docs/audit_cst_palace/AUDITORIA.md` y en el historial de `cst_export.py`.

## Resultado final

`siw cst ... --solver fd` (malla Tetrahedral + bloque `FDSolver`) + refinamiento
de malla local manual en el gap CPWG (~0.08mm) y el anillo coaxial (~0.15mm)
da un resultado que calca a Palace:

| | fc | BW (−3dB) | IL mínima | S11 mejor |
|---|---:|---:|---:|---:|
| CST FD (corregido) | 2.876 GHz | 129.6 MHz | −1.80 dB | −17.29 dB |
| Palace (referencia) | 2.875 GHz | 150.0 MHz | −1.85 dB | −34.07 dB* |

\* no convergida en malla, ver más abajo.

## Cronología de bugs (orden real, no el orden ideal)

| # | Síntoma | Causa | Arreglo |
|---|---|---|---|
| 1 | Time Domain: "calculation seems to be unstable" | Faltaba blindaje del conector SMA (contaminación de un agente de fondo) | Restaurado el shield PEC |
| 2 | Persistía la inestabilidad tras el fix 1 | `Zmin`/`Xmin`/`Xmax` como `"electric"` (tapas PEC) en vez de `"open"` — cortocircuitaba el dominio | Cambiados a `open` |
| 3 | "Dispersive materials not supported at open boundary... ymin ymax" | `YminSpace`/`YmaxSpace` en `0` desde el primer commit del archivo — el sustrato con pérdidas tocaba el borde abierto | `YminSpace/YmaxSpace = 2.0`, después `5.0` |
| 4 | Instabilidad más específica: "small mesh step touching the open boundary y_min, y_max" | `RatioLimit` subido a 100 permitía refinar demasiado cerca de la fila externa de vías, a solo 3mm del borde Y | `RatioLimit` moderado a 50, standoff Y ampliado a 5mm |
| 5 | `.StabilityFactor "0.8"` → CST: "No such property or method" | Propiedad VBA **adivinada**, nunca existió | Eliminada, no reemplazada por otra adivinanza. Lección: solo usar propiedades ya probadas en una corrida real |
| 6 | Hipótesis del "ground clip" del SMA (corte plano) | Se probó y **se descartó**: con el corte quitado, el mismo warning de inestabilidad seguía apareciendo | `flat_sma_ground` revertido a `False` |
| 7 | Time Domain: inestabilidad genérica **persiste hasta hoy**, nunca resuelta del todo | Probablemente múltiple/acumulativa, no una causa única | Parked — se migró a Frequency Domain, que sí funcionó |
| 8 | Frequency Domain, primer intento: S21 < −60dB en **toda** la banda (2-3.6GHz), sin transmisión útil | El macro dejaba configurado `Solver.Method "Hexahedral"` + `CalculationType "TD-S"` (exclusivo de Time Domain); al correr Frequency Domain manualmente, la malla PBA/hexaédrica no resuelve el gap CPWG (0.25mm) ni el anillo coaxial | Se agregó `--solver fd` a `siw cst`: cambia `Mesh.MeshType` a `"Tetrahedral"` y agrega un bloque `With FDSolver` |
| 9 | `.SParaSymmetry "False"` en el bloque `FDSolver` → CST: "No such property or method" | Esa propiedad existe en el objeto `Solver` (Time Domain), **no** en `FDSolver` — son objetos COM distintos, adivinar por analogía de nombre fue un error | Eliminada, no reemplazada. El resto del bloque (`.Reset`, `.SetMethod "Tetrahedral","General purpose"`, `.MeshAdaptionTet/Hex`, `.Stimulation "All","All"`) sí parseó bien |
| 10 | Preocupación: en la vista 3D del conector solo se ve un cilindro, no el pin central tocando la pista | **No es un bug** — pin/PTFE/blindaje son cilindros concéntricos con el mismo rango en X; el blindaje (más ancho) tapa visualmente a los otros dos. El resultado eléctrico (calca a Palace) confirma que el contacto pin-pista funciona | Ninguno — aclarado, no corregido |

## El fix que realmente importó

Después de arreglar los bugs de borde/malla de Time Domain (#1-6), la inestabilidad
de ese solver **nunca se resolvió del todo** (#7). El avance real vino de cambiar
de solver:

1. **Coaxial de control primero** (`00_coaxial_control_fd.bas`, tramo recto de
   12mm, sin filtro): validó que el solver de Frecuencia y los puertos coaxiales
   funcionan bien en esta instalación de CST — S21≈0dB, S11=−50dB. Esto descartó
   un problema genérico de puertos y localizó el problema en la malla del filtro.
2. **Mesh type → Tetrahedral** + bloque `FDSolver` mínimo (sin propiedades TD).
3. **Refinamiento de malla local manual** en el gap CPWG (~0.08mm) y el anillo
   coaxial (~0.15mm) — el paso que de verdad resolvió el −60dB, porque la malla
   tetraédrica global no alcanzaba a representar un gap de 0.25mm.

## Hallazgo colateral, no menor

La auditoría (`docs/audit_cst_palace/`) encontró que el S11=−13.37dB usado para
elegir cascade N=3 sobre dual-mode (`docs/PLAN.md`, `docs/STATE.md`) **no está
convergido en malla**: refinar la malla de Palace ya en el repo
(`output/data/mesh_convergence_cascade_N3.json`) lo empeora a −9.34dB. El S11
real de cascade N=3 probablemente ronda el −10.5/−17dB, no el −13.37dB citado.
Caveat ya agregado a ambos documentos.

## Regla que se repitió tres veces esta sesión

**Nunca reemplazar una propiedad VBA que CST rechaza por otra adivinada.**
Pasó con `.StabilityFactor` (bug #5) y con `.SParaSymmetry` en `FDSolver` (bug #9)
— las dos veces la única corrección válida fue eliminar la línea y, si hacía
falta, dejar ese ajuste para la GUI hasta poder confirmarlo con una corrida real.
