# SIW Bandpass Filter — 2.87 GHz

Parametric **Substrate Integrated Waveguide** bandpass filter. **The board being
fabricated is an inline single-mode N=3 cascade** — see `docs/STATE.md` /
`docs/PLAN.md` for the current status and rationale (a dual-mode N=2 design was
explored first and is kept as a real, documented negative result; it lost a
head-to-head comparison on 2026-09-04 and is not being built).

- **f0 = 2.87 GHz**, FBW target = 5 %, 0.1 dB ripple
- Substrate **Rogers RO4350B 0.76 mm** (εr 3.66, tanδ 0.0037), **vias Ø 1.5 mm, pitch 3.0 mm**
  (1.5/3.0 mm was chosen over smaller sizes after three separate searches — see
  `VIA_PRESETS` in `config.py`)

### Status

**`docs/STATE.md` and `docs/PLAN.md` are the source of truth** — this file only
orients a new reader. Both are kept as living documents, not a changelog; where
a fact here disagrees with them, they are right.

In brief, as of 2026-09-04: cascade N=3, fc 2.879 GHz, IL −1.85 dB (−2.44 dB on
real copper), BW 189 MHz, S11w −13.37 dB against a −16 dB / 143.5 MHz target —
the deviation is written down and accepted, not hidden. Fabrication outputs
(CST macro, KiCad gerbers/drill/STEP, a 29-check `FAB_CHECKLIST.md`) are built
and passing. `golden/cascade_N3/` holds the measured provenance.

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

### Designing a filter

Two routes. **Prefer the calibrated one for the cascade** — see why below.

```bash
# 1. EM calibrations — cached per (substrate, via size, f0), so N=3 and N=4
#    share them and the expensive part is paid once.
siw calibrate --what both --N 3       # k(w_iris) eigenmode + Qe(w_ext) driven

# 2. Physics-derived design: calibrate → invert → assemble → fine confirm
siw synth-design --N 3
siw synth-design --N 4                # reuses the cached curves

# 3. Optional GP polish in a tight box around that design
siw design --topology cascade --N 3 \
    --seed l_cav1=34.46,l_cav2=34.46,w_iris=14.81,w_ext=13.0 \
    --span 2 --patience 14

# Global Bayesian search — the mode that works for dual-mode, whose search
# box is already centred on a validated design region
siw design --topology dualmode --evals 28 --patience 14
```

| Command | Does |
|---|---|
| `siw calibrate --what k\|qe\|both` | run + cache the EM calibrations |
| `siw synth-design` | invert the calibrations into a design, then confirm it |
| `siw design` | Bayesian search — global, or local with `--seed` |
| `siw layout` / `siw sweep` / `siw compare` | layout check, wideband sweep, comparison |
| `siw scan` | 1-D parameter scan on the assembled filter, with inversion |
| `siw compare-fab-variants` | PEC vs. real copper / ENIG / soldermask, one overlay |
| `siw cst` / `siw kicad` | CST `.bas` macro / KiCad board + gerbers + `siw kicad --check` |

**Why calibrate-and-invert rather than search, for the cascade** (measured
2026-08-30): a *global* GP over the assembled filter never beat −5 dB S11 in
60+ driven evaluations. Its objective contains the passband width, which is
**discontinuous** in the external coupling — below a threshold only the centre
pole clears −3 dB so the measured band is a single pole; above it all N poles
merge and the band jumps (16 / 22 / 36 / 65 / 215 MHz measured on N=3, with the
143.5 MHz target inside that jump). GPs model smooth functions, so the search
inherits the problem.

The calibrations instead measure a *smooth* observable on a *small* structure —
mode split on two coupled closed cavities for `k`, loaded Q of one driven cavity
for `Qe` — and each converged in about three cheap solves. Use `--seed` to make
the GP a **local polish** around that result, which is the regime it already
succeeds in for dual-mode.

Known gap: `calibrate_qe` takes Qu as the dielectric limit `1/tanδ` (270.3,
independently matched by the closed-cavity eigenmode Q), so it ignores conductor,
via-leakage and radiation loss and slightly **over-estimates** Qe.

## Layout

| Path | What |
|------|------|
| `src/siwfilter/` | the package — all design modules + `cli.py` (`siw`) |
| `config.py` | spec, substrate presets, fab rules, output paths |
| `synthesis.py` → `siw_geometry.py` → `layout_plot.py` | design chain |
| `cst_export.py` / `kicad_export.py` / `fab_check.py` | fabrication outputs (`siw cst` / `siw kicad`) |
| `palace_driven.py`, `palace_dualmode_driven.py` | Palace FEM meshers (cascade / dualmode) |
| `palace_geometry.py`, `palace_dualmode.py` | eigenmode calibration meshers |
| `synth_design.py` | calibrate → invert → assemble pipeline (`siw synth-design`) |
| `optimize.py` | scoring, screening, GP search, `local_topology()` |
| `topologies/*.py` | per-topology adapters + their `calibrate()` / `calibrate_qe()` |
| `comparison.py`, `report.py` | figures + comparisons |
| `output/` | generated artifacts (imgs / bas / kicad / data), gitignored except `data/calibration.json` |
| `golden/` | curated, reproducible designs + their measured S-parameters |
| `docs/` | `STATE.md` / `PLAN.md` (current) + historical reports/figures |

## Deliverable

`siw kicad --topology cascade --N 3 --params ... --launch cpwg` writes
`output/kicad/`: the `.kicad_pcb`, JLCPCB gerbers + drill files (zipped),
a STEP solid, review renders, `FAB_NOTES.md`, and a 29-check
`FAB_CHECKLIST.md`. `siw cst --topology cascade --N 3 --params ... --launch cpwg`
writes the matching CST 2021 `.bas` to `output/bas/`. See `docs/STATE.md` for
the exact `--params` currently being fabricated.
