# Coupling-only sweep: rhombic (2026-08-24)

## Setup

Cavity size `a` fixed at 75.3 mm, `w_ext` fixed at 19.7 (joint search's
winner). Grid over `w_iris` (tuning vias on the transverse diagonal) x
`y_wall` (transverse half-diagonal), 5x5 = 25 points. `screen_at_f0`
rejected 6/25, all at `y_wall` in {32, 35, 38} with `w_iris` 4/7/10/13 --
good match (S11 down to -14dB) but insufficient IL (worse than the -6.0dB
screen floor).

## Result: worse than corner_cut and circular_cross, confirms the batch ranking

| | w_iris | y_wall | fc | IL | BW | S11 worst | score |
|---|---|---|---|---|---|---|---|
| **grid best** | 7.0 | 35.0 | 2.985 | -6.01 | 368 MHz | -5.95 | **19.48** |
| joint Bayesian winner (rhombic best.json) | 13.0 | 35.0 | 3.008 | -5.04 | 358 MHz | -5.23 | 21.50 |
| corner_cut grid best, for reference | -- | -- | -- | -- | 223 MHz | -8.73 | 11.65 |
| circular_cross grid best, for reference | -- | -- | -- | -- | 288 MHz | -6.15 | 16.13 |

Same pattern as circular_cross: the coupling-only grid beats the joint
search (19.48 vs 21.50, ~9%) but the gap to spec stays enormous -- IL never
gets better than -4.97dB anywhere in 25 points (the dielectric-loss floor
for this filter is ~-0.47dB; even the BEST rhombic point costs 10x that).
This confirms rhombic as the weakest of the three geometries, matching the
original joint-search ranking exactly (corner_cut < circular_cross <
rhombic in score, worst to best... i.e. corner_cut best, rhombic worst).

## What the grid reveals: `y_wall` alone sets the outcome

This is the cleanest single-parameter story of the three geometries. Every
one of the top 5 points sits at **exactly `y_wall=35.0`**, across the ENTIRE
`w_iris` range tested (4, 7, 10, 13, 16) -- w_iris moves the score by less
than 2.6 points (19.48 to 22.05) at fixed y_wall=35, while y_wall alone
moves it by up to 19 points (19.48 at y_wall=35 vs 38.27 at y_wall=44, same
w_iris=16). `y_wall` is the transverse half-diagonal -- i.e. it is close to
a cavity-SIZE parameter (it sets the diamond's aspect ratio), not a pure
coupling knob the way `w_ext` is in the other two geometries. That likely
explains why it dominates so completely: changing it moves the resonance
itself, not just how strongly two modes couple.

## Read for the geometry

rhombic's IL problem (never below -5dB) is structural, not a coupling
mis-tune: 25 points spanning the full box found no combination that
approaches the ~-1 to -2dB IL the working geometries (dualmode, corner_cut)
achieve. Two live hypotheses, neither tested by this sweep: (1) the diamond
via fence has more perimeter than a square/circle of similar area, so more
via-to-via leakage per unit enclosed area; (2) like circular_cross, rhombic
also has no taper (`TAPER_TO_WALL=False` -- the feed lands on a VERTEX, not
a flat wall), so the launch itself may again be the bottleneck rather than
the internal diamond geometry.

## Files

`output/data/sweep_rhombic_coupling.csv` -- all 25 rows.
