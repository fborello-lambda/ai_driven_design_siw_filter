# SIW Bandpass Filter — 2.87 GHz

A 3-cavity substrate integrated waveguide (SIW) bandpass filter on Rogers
RO4350B. This repository designs it in Python, simulates it with Palace
(FEM), and exports the files needed to manufacture it.

## Where things stand

The board was made by JLCPCB (Rogers RO4350B, ENIG, about USD 120) and
**measured on 2026-10-14**. It works as a filter but does not meet the
specification: the match is worse than simulated and the loss higher.

|                          | Target    | Simulated (Palace) | Measured (VNA, soldered) |
|--------------------------|-----------|--------------------|--------------------------|
| Centre frequency         | 2.87 GHz  | 2.876 GHz          | 2.894 GHz                |
| −3 dB bandwidth          | 143.5 MHz | 182 MHz            | 171 MHz                  |
| Peak insertion loss      | —         | 1.7 dB             | 2.0–2.4 dB               |
| Worst in-band S11        | −16 dB    | −11.2 dB           | −5 dB (best dip −17 dB)  |
| First spurious passband  | —         | 4.61 GHz, −3.8 dB  | 4.68 GHz, −4.4 dB        |

The measured range is the instrument calibration (2.4 dB) and an independent
software recalibration of the raw data (2.0 dB); `siw measure` reproduces both.
Board size is 165.8 × 45.8 mm.

## Key files

- **Measurements:** [`measurements/2026-10-14_vna/`](measurements/2026-10-14_vna/)
  (VNA `.s2p` files, raw standards, photos) and the tables in the papers.
- **Order the board:** [`docs/final_check/fab/`](docs/final_check/fab/)
  holds the gerbers, drill files and fab notes.
- **Is it ready?** [`docs/final_check/REPORT.md`](docs/final_check/REPORT.md)
  gives the verdict and what to write in the JLCPCB order notes.
- **The paper (English, the whole project):**
  [`docs/paper/ai_driven_rf_design.md`](docs/paper/ai_driven_rf_design.md).
- **Simulate in CST:** [`docs/cst_guide/`](docs/cst_guide/) (in Spanish).
- **University report (Spanish):**
  [`docs/paper/Anteproyecto_Filtro_SIW_287GHz.md`](docs/paper/Anteproyecto_Filtro_SIW_287GHz.md).

## Does the connector matter?

Yes. The filter was tuned with the SMA connector in place. Removing it and
feeding the board directly by microstrip or CPWG costs about 5 dB of return
loss. See [`docs/launch_comparison/`](docs/launch_comparison/) for 3D views
and S-parameters.

![Launch comparison](docs/launch_comparison/sparams.png)

## Specs

- **Substrate:** Rogers RO4350B, 0.76 mm thick, εr 3.66
- **Vias:** 1.5 mm diameter, 3.0 mm pitch
- **Connector:** Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA
- **Response:** Chebyshev, 3rd order, 0.1 dB ripple

## Quick start

```bash
uv sync      # install
siw          # fast pipeline: synthesis → geometry → layout → CST macro → measurement check
siw --list   # show every stage and subcommand
```

The EM simulations need [Palace](https://awslabs.github.io/palace/). It is
found through `$PALACE_BIN`, your `$PATH`, or `~/opt/palace/bin/palace`.

## Checking a measurement

```bash
siw measure            # software calibration + comparison with spec, Palace and CST
siw measure --paper    # also refresh the tables and figures in docs/paper/
```

`siw measure` recalibrates the raw VNA files (open, short, match and thru
saved with the measurement), checks the result against the instrument's own
calibration, and prints the comparison table. Its defaults are the committed
dataset and the fabricated design, so it runs with no arguments.

## Rebuilding the fabricated board

```bash
P=l_cav1=33.939,l_cav2=35.503,w_iris=14.416,w_ext=13.96,l_taper=15.738,w_ms=1.6636

siw kicad --topology cascade --N 3 --params $P --launch cpwg   # KiCad + gerbers → output/kicad/
siw cst   --topology cascade --N 3 --params $P --launch cpwg   # CST macro → output/bas/
```

## Designing a new filter

```bash
siw calibrate --what both --N 3   # measure the coupling curves (cached)
siw synth-design --N 3            # turn them into a design and check it
```

`siw --help` lists the other commands: optimisation, sweeps, scans and
comparison plots.

## Repository layout

```
src/siwfilter/   Python package and the `siw` command
golden/          validated designs and their simulated S-parameters
docs/            status, fab package, reports, figures
output/          generated files (not committed)
```
