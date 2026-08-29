# SIW Bandpass Filter — 2.87 GHz

Parametric **Substrate Integrated Waveguide** bandpass filter. Originally scoped as
3 inline TE101 cavities; the **landed design is an N=2 single-cavity dual-mode
filter** (see Status below).

- **f0 = 2.87 GHz**, FBW target = 5 %, 0.1 dB ripple
- Substrate **Rogers RO4350B 0.76 mm** (εr 3.66, tanδ 0.0037), **vias Ø 1.5 mm, pitch 3.0 mm**
  (1.5/3.0 mm was chosen over smaller sizes after three separate searches — see
  `VIA_PRESETS` in `config.py`)

### Status (2026-08-29)

**Landed design**: N=2 single-cavity dual-mode, `output/data/opt_dualmode_best.json`
— score 9.31, S11 −17.7 dB, IL −1.42 dB, ~119 mm board, real Taoglas SMA modelled.

**Open item**: its bandwidth is 318 MHz vs the 143.5 MHz target (2.2× too wide).
Fixing this needs a proper k12/Qe coupling calibration (targets: k12 ≈ 0.069,
Qe ≈ 16.9) rather than black-box search.

**N=4 compact**: extensively investigated and currently closed — five structurally
different mechanisms plus a joint GP optimization all hit the same ceiling. Full
negative results in `docs/geometry_exploration/dualmode_cascade_v6_handoff_2026-08-28.md`
§9–16. Read that before restarting any N=4 geometry work.

Synthesis → physical geometry → native parametric **CST 2021** model (`.bas` macro).
**openEMS** (FDTD) is a fast pre-check; **Palace** (FEM) gave the final, optimized
dimensions. `config.py` is the single source of truth.

## Setup

Needs the openEMS core at `~/opt/openEMS` and Palace at `~/opt/palace` (see `CLAUDE.md`).

```bash
uv sync                                                        # install package + deps
export LD_LIBRARY_PATH=$HOME/opt/openEMS/lib:$LD_LIBRARY_PATH  # only for EM stages
```

## Usage

```bash
siw                      # light pipeline: synth → geometry → layout → cst → report
siw --list               # all stages (light + heavy EM)
siw --only synth layout  # just these, in order
siw --stage palace-opt   # one heavy stage
```

Light stages take seconds. Heavy ones (`palace-eig`, `palace-driven`, `palace-opt`)
run EM solves and are opt-in. Any module also runs standalone:
`uv run python -m siwfilter.<module>`.

## Layout

| Path | What |
|------|------|
| `src/siwfilter/` | the package — all design modules + `cli.py` (`siw`) |
| `config.py` | spec, substrate presets, output paths |
| `synthesis.py` → `siw_geometry.py` → `layout_plot.py` → `cst_export.py` | design chain |
| `palace_geometry.py`, `palace_driven.py`, `palace_opt.py` | Palace FEM + optimizer |
| `compare.py`, `report.py` | figures + IEEE PDF |
| `output/` | generated artifacts (imgs / s2p / bas / data) |
| `cst_palacetrained/` | final CST deliverable (macro, s2p, instructions) |
| `docs/` | IEEE report sources + figures |
| `cst_data/` | user-provided CST exports |

## Deliverable

`cst_palacetrained/` holds the final CST package. Import `siw_filter.bas` into
CST 2021, run the Time Domain solver, export the `.s2p` — see
`cst_palacetrained/INSTRUCCIONES_CST.md`.
