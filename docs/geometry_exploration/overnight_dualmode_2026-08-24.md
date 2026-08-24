# Overnight dual-mode re-tune -- result (2026-08-24)

## What ran

60-eval Bayesian search on `dualmode` alone (3x the previous run's budget),
with the validated fast screen (`screen_at_f0`, `S11_SCREEN_DB=-10`,
`S21_SCREEN_FLOOR_DB=-6` in screen-mesh units) enabled by default, targeting
a narrower, more selective response (closer to the 143.5 MHz / 5% FBW
target) than the 320 MHz the previous 20-eval run landed at.

## Result: no improvement found

| stage | a | w_iris | x_iris | y_wall | w_ext | fc | IL | BW | S11 worst | score |
|---|---|---|---|---|---|---|---|---|---|---|
| coarse winner (eval 1, warm-start) | 57.21 | 15.26 | 28.68 | 8.62 | 16.31 | -- | -- | -- | -- | 10.046 |
| dense confirm | " | " | " | " | " | 2.911 | -1.42 | 318 | -17.70 | 9.310 |
| fab-rounded (0.1mm) | 57.2 | 15.3 | 28.7 | 8.6 | 16.3 | 2.911 | -1.43 | 320 | -16.73 | 9.535 |

**The winner is the eval-1 warm-start point** -- literally the pre-session
landed design (`LANDED_DM` in `comparison.py` / `_PARAMS`'s init values in
`topologies/dualmode.py`) -- **not a new point the search found.** None of
the other 59 evals (10 screened out before a full sweep, 49 fully evaluated)
beat it. This is a decisive negative result, not an inconclusive one: 60
Bayesian-guided evals, with a working fast-reject screen freeing up budget
for live candidates, still converged on the same design a previous much
smaller/coarser search had already found. That is strong evidence this
IS the optimum of the current 5D search box (`a`, `w_iris`, `x_iris`,
`y_wall`, `w_ext`), not an artifact of insufficient search budget.

Confirms and slightly improves on the previous night's number (v17 retune,
20 evals): S11 -17.70dB vs -17.2dB, same BW (~320 MHz), same fc (~2.91 GHz).

**Bandwidth remains stuck at ~318-320 MHz against the 143.5 MHz target --
2.2x over.** The search DID explore toward lower coupling (`w_iris` reached
13.26, `w_ext` reached its exact box floor of 14.10 mm) without finding a
combination that keeps S11 acceptable at lower BW; those attempts scored
worse (S11 degrading to -7 to -13 dB). This is the same finding as
`baseline_2026-08-24/README.md`'s original conclusion, now confirmed with
3x the search budget and a working screen instead of 20 near-random evals:
**this design is not reachable at 5% FBW within the current box.** Whether
it's reachable at all with this topology (vs. structurally over-coupled by
the feed/aperture geometry) is what tomorrow's coupling-only sweep
(`sweep_coupling.py`) is meant to isolate, by decoupling `w_iris`/`w_ext`
from cavity size `a` -- the joint search may be trading them against each
other in a way that never tries the combination that would work.

## Wideband (0.1-8 GHz) sanity check: spurious bands confirmed stable

Run at eval 30 (checkpoint) and again on the eval-60 final design. Both
landed on effectively the same spurious signature:

| band | checkpoint30 (mid-search) | final60 (converged) |
|---|---|---|
| ~5.0-5.4 GHz | S21 -7.2 to -7.8 dB | S21 -7.2 to -7.8 dB |
| ~7.2-8.0 GHz | S21 up to -3.96 dB, S11 down to -18.9 dB | S21 up to -3.96 dB, S11 down to -18.9 dB |

Essentially unchanged between a mid-search point and the final design --
confirms this is a structural property of the ~57mm dual-mode cavity (a
higher-order TE10n mode, consistent with f0 * ~2.5 ~ 7.2GHz), not something
sensitive to the small parameter differences explored, and not a meshing
artefact (same result on two different designs, two different mesh
instances). See `baseline_2026-08-24/wideband_checkpoint30.png` and
`wideband_final60.png`.

Practical read: if the eventual system has energy in 5-8 GHz near this
filter, it will pass through nearly as well as the intended 2.87 GHz
passband. Worth tracking for any out-of-band rejection requirement; does
not block in-band use.

## Files

- `docs/geometry_exploration/baseline_2026-08-24/dualmode_best_overnight60.json`
  -- full result, for comparison against any future re-tune.
- `output/data/opt_dualmode_log.csv` -- all 60 rows (coarse only; the 10
  fast-rejected-by-screen rows are the ones with `score >= 1e8`, no CSV
  column for it -- `evaluate()`'s sentinel for a screen fail).
