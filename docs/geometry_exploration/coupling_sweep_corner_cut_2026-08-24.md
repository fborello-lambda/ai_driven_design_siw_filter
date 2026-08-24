# Coupling-only sweep: corner_cut (2026-08-24)

## Setup

Cavity size `a` fixed at 59.4 mm (its screened resonance), grid over
`w_iris` (corner-cut depth) x `w_ext` (feed aperture), 6x6 = 36 points.
`screen_at_f0` rejected 12/36 before a full coarse eval.

## Result: confirms the joint search's optimum, and narrows it

| | w_iris | w_ext | fc | IL | BW | S11 worst | score |
|---|---|---|---|---|---|---|---|
| **grid best** | 3.0 | 17.0 | 2.875 | -2.24 | **223 MHz** | -8.73 | **11.65** |
| joint Bayesian winner (corner_cut best.json) | 3.0 | 17.8 | 2.880 | -1.26 | 331 MHz | -9.30 | 11.76 |

Essentially the same score, but **34% narrower bandwidth** at the grid's
best point -- `w_ext=17.0` sits just inside where the joint search's `w_ext`
landed (17.8), and the difference between the two is entirely inside the
BW/IL trade the score function makes.

**The main finding is what `w_iris` does across the grid, not `w_ext`.**
Every row from `w_iris=3` to `w_iris=15` landed within noise of each other
at the same `w_ext` (score 11.65-12.15, BW 201-223 MHz) -- confirming
`w_iris` has **no detectable effect** in that range, consistent with
`corner_cut()`'s known saturation (`cut = max(p_via, w_iris)`, `p_via=3.0`).
Only at `w_iris=18` did the pattern break: fc shifted up to 2.95 GHz and
match degraded across the whole row (best score in that row: 16.5, worse
than everywhere else). At that depth the cut is deep enough to meaningfully
change the cavity's effective size, not just couple two modes.

**`w_ext` is the entire story for this geometry.** Every row shows the same
curve versus `w_ext`: 8-11 screened out (aperture too small, mismatched),
14 badly under-coupled (BW ~70 MHz, S11 ~-2.7dB), 17 the sweet spot (BW
~210-225 MHz, S11 ~-9dB), 20 excellent match but over-coupled (S11 down to
-18dB, BW ~460-480 MHz), 23 over-coupled and mismatched again (BW ~550-600
MHz, S11 ~-9dB). None of the 36 points reach the -16dB / 143.5MHz target
simultaneously -- the trade-off curve passes NEAR both targets but not
through their intersection at this grid resolution.

## What this confirms about task #27's finding

The overnight dual-mode conclusion generalizes: **decoupling the search
does not unlock a fundamentally better operating point** for corner_cut
either. The grid's best (11.65) and the joint search's winner (11.76) are
statistically the same design. What decoupling DID reveal, that the joint
search's score function didn't reward finding: a meaningfully narrower BW
(223 vs 331 MHz) at equal match quality -- worth keeping in mind for a
future finer sweep of `w_ext` in 15.5-18.5 (2-3 points), since the true
optimum likely sits between the 17 and 20 grid points, not on either.

## Files

`output/data/sweep_corner_cut_coupling.csv` -- all 36 rows.
