# SIW Bandpass Filter — 2.87 GHz

Parametric **Substrate Integrated Waveguide** bandpass filter. Originally scoped as
3 inline TE101 cavities; the **landed design is an N=2 single-cavity dual-mode
filter** (see Status below).

- **f0 = 2.87 GHz**, FBW target = 5 %, 0.1 dB ripple
- Substrate **Rogers RO4350B 0.76 mm** (εr 3.66, tanδ 0.0037), **vias Ø 1.5 mm, pitch 3.0 mm**
  (1.5/3.0 mm was chosen over smaller sizes after three separate searches — see
  `VIA_PRESETS` in `config.py`)

### Status (2026-08-30)

**Landed design**: N=2 single-cavity dual-mode, `output/data/opt_dualmode_best.json`
— score 9.31, S11 −17.7 dB, IL −1.42 dB, ~119 mm board, real Taoglas SMA modelled.

**Open item**: its bandwidth is 318 MHz vs the 143.5 MHz target (2.2× too wide).
Fixing this needs a proper k12/Qe coupling calibration (targets: k12 ≈ 0.069,
Qe ≈ 16.9) rather than black-box search.

**Cascade (N=3/N=4) — reworked 2026-08-30, not yet meeting spec.** Five bugs were
found that *each independently* invalidated every earlier cascade search, so **all
pre-2026-08-30 cascade numbers are void**: `w_iris` was quantized (the search box
spanned ~2 distinct geometries), N≥4 could not express its asymmetric coupling
profile, `FilterSpec` vias were stale at 0.8/1.5 mm, `CascadeTopology.calibrate()`
was an unimplemented stub, and the eigenmode pair-selection returned a 21×-wrong `k`.

With those fixed, the calibrate-and-invert route (`siw synth-design`) now solves
internal coupling (within 2 % of target), cavity resonance, and centre frequency
(N=4 landed exactly on 2.870 GHz) — each in ~3 cheap solves. **Still open**: S11
(−5 dB vs −16 target) and bandwidth (215 vs 143.5 MHz), both traced to the external
coupling. The N=3 S11 shows the right *number* of reflection zeros but unevenly
spaced with −6…−11 dB ripple — the signature of `k` and `Qe` mismatched, with `k`
already verified.

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
| `config.py` | spec, substrate presets, output paths |
| `synthesis.py` → `siw_geometry.py` → `layout_plot.py` → `cst_export.py` | design chain |
| `palace_geometry.py`, `palace_driven.py`, `palace_opt.py` | Palace FEM + optimizer |
| `synth_design.py` | calibrate → invert → assemble pipeline (`siw synth-design`) |
| `optimize.py` | scoring, screening, GP search, `local_topology()` |
| `topologies/*.py` | per-topology adapters + their `calibrate()` / `calibrate_qe()` |
| `compare.py`, `report.py` | figures + IEEE PDF |
| `output/` | generated artifacts (imgs / s2p / bas / data) |
| `cst_palacetrained/` | final CST deliverable (macro, s2p, instructions) |
| `docs/` | IEEE report sources + figures |
| `cst_data/` | user-provided CST exports |

## Deliverable

`cst_palacetrained/` holds the final CST package. Import `siw_filter.bas` into
CST 2021, run the Time Domain solver, export the `.s2p` — see
`cst_palacetrained/INSTRUCCIONES_CST.md`.
