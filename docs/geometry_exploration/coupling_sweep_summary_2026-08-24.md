# Coupling-only sweep exploration: final summary (2026-08-24)

Task #29 -- 97 grid points across corner_cut (36), circular_cross (36) and
rhombic (25), each with cavity size `a` fixed near its screened resonance
and a grid over the coupling knobs, using `screen_at_f0` to reject
non-starters before a full coarse eval. Purpose: the joint 5D Bayesian
search cannot isolate coupling from cavity size (it trades them against
each other), so this sweep asks the question directly.

## Result table

| geometry | grid best score | joint search score | improvement | best S11 | best IL | screened/total |
|---|---|---|---|---|---|---|
| **corner_cut** | 11.65 | 11.76 | ~1% (essentially tied) | -8.73 dB | -2.24 dB | 12/36 |
| **circular_cross** | 16.13 | 19.25 | ~16% | -6.15 dB (-8.92 screened) | -2.61 dB | 6/36 |
| **rhombic** | 19.48 | 21.50 | ~9% | -5.95 dB | -6.01 dB | 6/25 |
| dual-mode (reference, for scale) | 9.31 | -- | -- | -17.70 dB | -1.42 dB | -- |

Ranking is unchanged from the original joint-search comparison:
**corner_cut < circular_cross < rhombic** (best to worst), and dual-mode
remains well ahead of all three. Decoupling the search helped circular_cross
and rhombic meaningfully (9-16% better) but only matched corner_cut's
already-tight joint result -- and in no case closed more than a fraction of
the gap to dual-mode or to the -16dB/143.5MHz spec.

## What the sweeps actually taught us (more valuable than the scores)

1. **corner_cut**: `w_iris` (cut depth) has NO effect below 15mm, confirming
   `corner_cut()`'s known saturation. `w_ext` alone sets the whole BW/match
   trade-off, and the true optimum sits between the 17 and 20 grid points --
   worth a finer follow-up sweep in 15.5-18.5.

2. **circular_cross**: `w_iris` (cross arm x) and `y_wall` (cross arm y) do
   **not** act independently -- the sign of `y_wall`'s effect on score
   flips between `w_iris=12` and `w_iris=16`. A 1D sweep of either
   parameter alone would have missed this entirely; it only showed up
   because this was a genuine 2D grid.

3. **rhombic**: the cleanest single-parameter story -- `y_wall` (transverse
   half-diagonal, effectively a cavity-shape parameter) dominates
   completely, `w_iris` barely matters. IL never gets below -5dB anywhere
   in 25 points, ~10x the pure-dielectric floor, suggesting a structural
   loss mechanism (via-fence perimeter, or the missing taper) rather than a
   coupling mis-tune.

## The taper connection

circular_cross and rhombic -- the two weaker geometries -- both lack a
taper (`TAPER_TO_WALL=False` in `palace_dualmode_driven.py`): the feed
lands on a curve (tangent) or a vertex, neither of which is a flat wall a
Deslandes flare can land on, so both feed through a bare 50-ohm line. Their
coupling-only sweeps confirm neither achieves a match close to spec no
matter how the internal geometry is tuned (best S11: -6 to -9dB across 61
combined grid points). corner_cut, which DOES have a taper, reached -8.7dB
with a much smaller grid (36 points) and a cleaner single-parameter story.
This is circumstantial, not proven, but consistent with the launch itself
-- not the internal cavity shape -- being the shared bottleneck for both
weaker geometries.

## What remains open (not run yet, pending user decision)

Two kinds of unexplored parameters, raised explicitly by the user during
this sweep:

1. **Existing but fixed**: `d_via`/`p_via` (via diameter/pitch, i.e. fence
   density) were held at their defaults (1.5/3.0mm) in every run this
   session, including the original joint search. User's own assessment:
   unlikely to matter much, deprioritized.

2. **Genuinely new, needs code**: structural parameters that do not exist
   yet in `geometries.py` --
   - corner_cut: cut angle (fixed at 45 deg), or cutting 2 corners instead
     of 1.
   - circular_cross: more vias per cross arm (currently 1 via per arm end,
     4 total) or a second concentric ring.
   - rhombic: extra tuning vias on the second diagonal (currently only 2,
     on the transverse one).
   None of these are grid values on the current parameter space -- each is
   a new geometry variant requiring new code in `geometries.py`, per the
   "structural variants" scope noted in `plan_2026-08-24.md`. Not started;
   awaiting the user's go-ahead on scope/priority before writing it.

## Bottom line

Task #27's overnight finding for dual-mode generalizes to all three new
geometries: decoupling the search from cavity size narrows or improves the
result somewhat, but does not unlock a design competitive with dual-mode
within the CURRENT parameterization of each shape. Getting closer would
need either the structural variants above, or fixing the taper-less launch
for circular_cross/rhombic -- both are new engineering, not more search
budget on the existing knobs.
