# Coupling-only sweep: circular_cross (2026-08-24)

## Setup

Cavity size `a` fixed at 67.0 mm (screened resonance), `w_ext` fixed at
20.7 (joint search's winner, to isolate mode-split from external match).
Grid over `w_iris` (cross arm x) x `y_wall` (cross arm y), 6x6 = 36 points.
`screen_at_f0` rejected 6/36 -- the entire `w_iris=24` row, whose best S11
(-8.92dB) missed the -10dB threshold by under 1.1dB.

## Result: worse than the joint search, and worse than corner_cut

| | w_iris | y_wall | fc | IL | BW | S11 worst | score |
|---|---|---|---|---|---|---|---|
| **grid best** | 16.0 | 24.0 | 2.837 | -2.61 | 288 MHz | -6.15 | **16.13** |
| joint Bayesian winner (circular_cross best.json) | 16.71 | 14.61 | 2.833 | -2.59 | 362 MHz | -4.27 | 19.25 |
| corner_cut's grid best, for reference | -- | -- | -- | -- | 223 MHz | -8.73 | 11.65 |

The coupling-only grid DOES beat the joint search here (16.13 vs 19.25,
~16% better) -- unlike corner_cut where it only matched it. But it never
gets close to corner_cut's result, let alone the -16dB/143.5MHz target: the
best S11 found anywhere in 36 points is -8.92dB (screened, no full eval),
and the best FULLY EVALUATED point only reaches -6.15dB.

## What the grid reveals: a non-separable interaction, not a simple trade-off

This is the interesting part, and it's different from corner_cut's clean
single-parameter story:

- **Low `w_iris` (4-8), `y_wall` increasing: monotonically WORSE.** fc drifts
  down from 2.72 to 2.67 GHz (away from the 2.87 target) and score climbs
  from ~28 to ~30.
- **`w_iris=12`: `y_wall` increasing is also worse**, but from a much better
  starting point (score 16.26 at y_wall=4, degrading to ~21-25 by y_wall=24).
- **`w_iris=16`: the trend REVERSES.** y_wall=4 is the worst point in the row
  (17.67); each further y_wall step improves the score, ending at the grid's
  overall best (16.13, y_wall=24).
- **`w_iris=20`: partial reversal**, plateauing around score ~21 rather than
  continuing to improve.
- **`w_iris=24`: entirely screened out** regardless of y_wall (S11 never
  better than -8.92dB even at the best y_wall).

So `w_iris` and `y_wall` do NOT act independently on this geometry -- the
sign of `y_wall`'s effect flips somewhere between `w_iris=12` and
`w_iris=16`. A 1D projection onto either axis alone would have missed this;
it only shows up because the sweep is a genuine 2D grid.

## Read for the geometry, not just the numbers

circular_cross remains the weaker of the two geometries checked so far, even
after removing the joint search's inability to decouple parameters. The best
match achievable anywhere in a 36-point grid centred on its screened
resonance is under -9dB -- roughly 7dB short of spec. Combined with the
missing taper (this geometry feeds through a bare 50-ohm line into a curved
via fence, since a flare has nothing flat to land on -- see
`palace_dualmode_driven.py`'s `TAPER_TO_WALL`), the aperture launch itself is
the more likely bottleneck than any single coupling parameter value. A future
finer grid around `w_iris` 14-20, `y_wall` 20-28 (following the reversal)
could close some of the gap, but is unlikely to reach -16dB without
addressing the launch.

## Files

`output/data/sweep_circular_cross_coupling.csv` -- all 36 rows.
