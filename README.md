# SIW Bandpass Filter — 2.87 GHz

A parametric **substrate integrated waveguide** (SIW) bandpass filter, from
Chebyshev synthesis through EM calibration (Palace FEM) to fabrication files
(KiCad/JLCPCB gerbers and a CST Studio macro).

| | |
|---|---|
| Centre frequency | 2.87 GHz |
| Target | 5 % FBW (143.5 MHz), 0.1 dB Chebyshev ripple, S11 ≤ −16 dB in band |
| Substrate | Rogers RO4350B, 0.76 mm (εr 3.66, tanδ 0.0037) |
| Vias | Ø 1.5 mm, 3.0 mm pitch |
| Connector | Taoglas EMPCB.SMAFSTJ.B.HT, CPWG launch |

## Status (2026-09-23)

**The board being fabricated is an inline 3-cavity cascade** with its end
cavities trimmed by −0.3 mm. It is a prototype and misses the return-loss and
bandwidth spec. The deviation is documented:

| | fine-mesh Palace | spec |
|---|---|---|
| fc | 2.876 GHz | 2.87 GHz |
| −3 dB bandwidth | 182 MHz | 143.5 MHz |
| worst in-band S11 | −11.15 dB | −16 dB |
| insertion loss (peak / worst in band) | −1.70 / −2.58 dB | — |
| board | 165.78 × 45.79 mm | — |

`l_cav1=33.939, l_cav2=35.503, w_iris=14.416, w_ext=13.96, l_taper=15.738, w_ms=1.6636` (mm)

- **Fab package:** [`docs/final_check/fab/`](docs/final_check/fab/): JLCPCB
  gerber/drill zip, `FAB_CHECKLIST.md` (34/34), `FAB_NOTES.md`, and CST
  macros (time and frequency domain).
- **Verdict and JLCPCB check:** [`docs/final_check/REPORT.md`](docs/final_check/REPORT.md).
  The board can be ordered with order notes: RO4350B 0.76 mm (not FR-4), no
  soldermask, and copper/stitching vias at the board edge. JLCPCB offers only
  1 oz copper, which is marginal for the SMA fork fit.
- **Measured provenance:** [`golden/cascade_N3/`](golden/cascade_N3/).
- A dual-mode single-cavity N=2 design was explored first. It lost the
  head-to-head comparison and is kept as a documented negative result.

The full project state and history are in [`docs/STATE.md`](docs/STATE.md)
and [`docs/PLAN.md`](docs/PLAN.md).

## Setup

Needs [uv](https://docs.astral.sh/uv/). The EM stages also need
[Palace](https://awslabs.github.io/palace/), found via `$PALACE_BIN`, `palace`
on `$PATH`, or `~/opt/palace/bin/palace`.

```bash
uv sync
```

## Usage

```bash
siw                      # light pipeline: synth → geometry → layout → cst → report
siw --list               # all stages (light + heavy EM) and subcommands
siw --only synth layout  # just these stages, in order
siw --stage palace-opt   # one heavy (EM) stage
```

Light stages take seconds. Heavy ones run Palace solves and are opt-in. Every
module also runs standalone: `uv run python -m siwfilter.<module>`.

### Regenerating the fabricated board

```bash
P=l_cav1=33.939,l_cav2=35.503,w_iris=14.416,w_ext=13.96,l_taper=15.738,w_ms=1.6636
siw kicad --topology cascade --N 3 --params $P --launch cpwg   # → output/kicad/ (+ FAB_CHECKLIST.md)
siw cst   --topology cascade --N 3 --params $P --launch cpwg   # → output/bas/
```

### Designing a filter

```bash
siw calibrate --what both --N 3   # k(w_iris) eigenmode + Qe(w_ext) driven, cached
siw synth-design --N 3            # invert the calibrations → assemble → confirm
siw design --topology cascade --N 3 --seed <params> --span 2 --patience 14  # local GP polish
```

For the cascade, use calibrate-and-invert. A global Bayesian search over the
assembled filter does not converge because its bandwidth objective jumps
discontinuously with the external coupling. Use the GP only for local
refinement with `--seed`. `docs/STATE.md` gives the measured reasoning.

| Command | Does |
|---|---|
| `siw calibrate` / `siw synth-design` | EM calibrations; calibrated design pipeline |
| `siw design` | Bayesian search, global or local (`--seed`) |
| `siw layout` / `siw sweep` / `siw scan` | layout check, wideband sweep, 1-D parameter scan |
| `siw compare` / `siw compare-designs` / `siw compare-fab-variants` | comparison figures |
| `siw cst` / `siw kicad` | CST `.bas` macro, KiCad board + gerbers + drill + STEP |

`--topology` also accepts `corner_cut`, `circular_cross` and `rhombic`. These
are parked experimental geometries from closed exploration work
(`docs/geometry_exploration/`).

## Repository layout

| Path | What |
|---|---|
| `src/siwfilter/` | the package and the `siw` CLI (`cli.py`) |
| `  config.py` | spec, substrate/via presets, fab rules, output paths — single source of truth |
| `  synthesis.py` → `siw_geometry.py` → `layout_plot.py` | design chain |
| `  topologies/` | per-topology adapters with `calibrate()` / `calibrate_qe()` |
| `  palace_*.py` | Palace FEM meshers (eigenmode + driven) |
| `  synth_design.py`, `optimize.py` | calibrate→invert pipeline; GP search |
| `  cst_export.py`, `kicad_export.py`, `fab_check.py` | fabrication outputs |
| `golden/` | curated designs and their measured S-parameters ([README](golden/README.md)) |
| `docs/` | `STATE.md`, `PLAN.md`, `final_check/` (fab verdict), `cst_guide/`, `paper/` (thesis proposal), historical studies |
| `output/` | generated artifacts (gitignored except the calibration cache) |
