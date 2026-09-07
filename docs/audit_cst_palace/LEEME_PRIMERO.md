# Prueba de CST — solver de frecuencia

Este paquete sirve para diagnosticar la discrepancia. **El diseño no está validado en CST.** La corrida recibida tiene S21 máximo de −60.7 dB y un comportamiento anómalo del puerto 2. No cambiar las cavidades todavía.

## Primero: coaxial recto

1. Crear un proyecto nuevo y ejecutar `00_coaxial_control.bas` desde el editor de macros. La macro construye solamente un coaxial recto de 12 mm y dos puertos; no es el filtro.
2. Seleccionar **Frequency Domain Solver**, malla tetraédrica. Confirmar que no quedó seleccionado el solver temporal por la plantilla o `ResetAll`.
3. Calcular/ver los modos de **ambos** puertos. Debe existir un TEM con campo eléctrico radial dentro del anillo de PTFE, sin frecuencia de corte y con impedancia de línea cercana a 50 Ω. No confundir impedancia de onda E/H con impedancia de línea V/I.
4. Si el modo seleccionado no es TEM, detener la simulación del filtro: revisar la selección de la cara/anillo, pin, blindaje y modo. Para inspección se pueden calcular varios modos; no excitar uno evanescente porque tenga índice 1.
5. Excitar todos los puertos para obtener la matriz completa. Desactivar la deducción de parámetros por simetría durante esta comprobación. Comparar primero las impedancias de línea y luego exportar S11/S21/S12/S22 con referencia común de 50 Ω.
6. El control debe tener transmisión cercana a 0 dB en toda la banda y poca reflexión. Como criterio de diagnóstico, buscar S21 >−0.1 dB y S11/S22 <−30 dB, estables al refinar la malla. La pérdida dieléctrica analítica a 2.87 GHz es apenas 0.0018 dB para este control con metal PEC.

No continuar con el filtro si el coaxial recto transmite −60 dB, tiene un puerto sin TEM o da parámetros que no corresponden a las excitaciones calculadas.

## Después: filtro

1. En otro proyecto nuevo ejecutar `01_filtro_geometria.bas`. Conserva las dimensiones actuales y el SMA cilíndrico **sin** el recorte plano. No contiene un bloque de configuración del solver temporal.
2. Seleccionar **Frequency Domain Solver**, malla tetraédrica, rango 2–3.6 GHz. Seleccionar explícitamente ambas excitaciones y desactivar simetrías automáticas de S para el diagnóstico.
3. Verificar nuevamente TEM e impedancia de línea próxima a 50 Ω en los dos puertos. El campo en el puerto 2 debe parecerse al del puerto 1, reflejado geométricamente.
4. Mallar el anillo coaxial, el pin y el gap CPWG de 0.2512 mm con resolución local suficiente. Como inicio, usar del orden de 0.08 mm o menos en el gap y 0.15 mm o menos en la sección coaxial; comprobar resultados tras otro refinamiento. Un número global de líneas por longitud de onda no garantiza resolver estos detalles.
5. Hacer primero puntos directos a 2.80, 2.87 y 2.94 GHz. Después barrer la banda con refinamiento adaptativo y comprobar estabilidad entre pasadas. Una curva interpolada de 1001 puntos no equivale a 1001 soluciones convergidas.
6. Exportar la matriz completa con magnitud **y fase**. Guardar también el informe de modos, impedancias, malla, convergencia y advertencias. Conservar el nombre de esta macro junto al resultado para identificar la geometría exacta.

Si persiste el fallo solo en el filtro, revisar especialmente la continuidad pin–pista, el blindaje–tierra y que exista la transición ancha entre microstrip y SIW. Luego comparar un modelo simplificado sin conectores, con sus propios puertos bien definidos, para separar transición y cavidades.

## Referencias incluidas

`palace_refined_ports_magnitude.csv` es la comparación más reciente con puertos refinados: IL mínima ≈2.01 dB, centro de banda ≈2.872 GHz, S11 peor muestreado ≈−10.56 dB. **Todavía tiene sensibilidad de malla/dominio**, por lo que no se exige coincidencia al dígito.

`palace_historical_magnitude.csv` es la referencia anterior, con puertos insuficientemente resueltos. `palace_previous_fine_magnitude.csv` conserva otra malla. Los tres archivos son magnitudes; el CSV `palace_refined_S11_S21_with_phase.csv` contiene las fases reales disponibles, solamente para excitación 1. No se inventó S12/S22 ni una fase cero para fabricar un Touchstone completo.

`cst_recibido_frequency.s2p` es el resultado recibido que se está diagnosticando, no un objetivo de diseño. `cst_chat_export.txt` conserva el resultado temporal pegado antes. `AUDITORIA.html` explica los hallazgos y sus límites; `comparison_cst_palace.png` muestra las curvas.

Las macros construyen geometría; **no fueron ejecutadas en CST en este entorno**. Si CST rechaza una instrucción, guardar el mensaje y la línea exacta. No sustituir una propiedad VBA por otra adivinada.
