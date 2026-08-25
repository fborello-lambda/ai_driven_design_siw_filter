# Structural-variant exploration: two rounds (2026-08-25)

Task #31, user request: don't just re-tune existing knobs (task #29 already did
that) -- add genuinely **new structural parameters** to each geometry, verify
DRC (via-to-via spacing) for any new via placement, build a fast S11/S21-near-f0
screen to reject non-starters before full simulation, and run autonomously
against a hard deadline (2026-08-25 21:00 UTC) targeting the 4 best new
geometries besides dual-mode.

## New structural knobs added

Four new layout functions in `geometries.py` (registered in `LAYOUTS`), each a
thin wrapper around its parent that returns the parent unchanged at the
knob's default value (regression-verified: identical tets/ports/board size):

| new geometry | parent | new knob | mechanism |
|---|---|---|---|
| `circular_cross_nvia` | circular_cross | `n_perturb` | cluster of extra vias at each cross-arm tip |
| `circular_cross_ring2` | circular_cross | `ring2_frac`, `ring2_span_deg` | partial inner via arc at `ring2_frac*R` |
| `corner_cut_2corner` | corner_cut | `n_corners` | mirrors the single corner cut to a second corner |
| `rhombic_2diag` | rhombic | `w_iris2_mm` | second tuning-via pair on the feed-axis diagonal |

DRC: every layout still ends in the existing `_dedupe(vias, r)` (uses
`min_via_centre_sep`, JLCPCB hole-to-hole rule) -- no new validator was needed
since all new vias share the uniform via diameter already enforced there.

## Methodology: two-phase triage, both rounds

- **Phase A (screen)**: `screen_at_f0()` on the ultra-coarse mesh -- a
  window-scan of S11/S21 near f0 at the parent's already-known coupling
  params, ~2min/point. Answers "does this even resonate usefully" before
  spending real budget.
- **Phase B (refine)**: for phase-A survivors only, a real Bayesian coupling
  search (`optimize()`, same v17 `score()` used everywhere else this
  session) with the structural knob held fixed -- this is what actually
  tests competitiveness, not just resonance.

## Round 1: fixed w_ext, 14 combinations across 4 geometries

Phase A screened every structural value at the **parent's fixed best
coupling params** (including `w_ext` held constant). Result: **1/14
survived** phase A.

- **`circular_cross_nvia`** (n_perturb=2,3,4,6) and **`circular_cross_ring2`**
  (ring2_frac=0.3-0.7): **0/9 passed**. S11 stuck at a hard ~-4dB ceiling
  regardless of internal perturbation strength -- flat across 9 different
  values, strongly suggesting the limiter is external to the internal split
  mechanism (the fixed `w_ext=20.7` inherited from the parent), not the
  perturbation itself.
- **`rhombic_2diag`** (w_iris2_mm=4,8,12,16): **0/4 passed**, but a clean
  monotonic trade-off: w_iris2=4 gave S11=-19.3dB but S21=-7.0dB, just
  missing the -6.0dB IL floor; larger values made IL progressively worse
  without improving S11 further.
- **`corner_cut_2corner`** (n_corners=2, only value tried): **1/1 passed**
  phase A with an excellent screen (S11=-32.3dB). Phase B (18-eval Bayesian
  coupling search + fine/fab-tolerance confirm) converged to
  **score=15.435** (a=60.1, w_iris=12.3, w_ext=20.0mm) -- **worse** than
  corner_cut's own coupling-sweep best (11.65) and dual-mode (9.31).
  Bandwidth stayed pinned at ~505-506MHz across the entire 18-eval search
  regardless of w_ext (vs corner_cut's 223MHz) -- this is a **structural
  over-coupling** problem (the second cut admits too much energy), not a
  tuning problem that more search budget could fix.

## Round 2: vary w_ext jointly with the structural knob

Round 1's flat, w_ext-independent ceiling for the circular_cross family and
rhombic_2diag's near-miss motivated retesting both with `w_ext` freed as a
second grid dimension instead of fixed at the parent's value.

| candidate | grid | phase-A survivors |
|---|---|---|
| `rhombic_2diag` | w_iris2_mm ∈ {1,2,3} × w_ext ∈ {15,19.7,23} (finer, lower values than round 1) | 3/9 |
| `circular_cross_ring2` | ring2_frac ∈ {0.4,0.5,0.6} × w_ext ∈ {14,17,20.7,24} | 0/12 |
| `circular_cross_nvia` | n_perturb ∈ {2,3} × w_ext ∈ {14,17,20.7,24} | 2/8 (both n_perturb=2) |

**circular_cross_ring2 is conclusively eliminated.** Round 1's "hard -4dB
ceiling" hypothesis (external aperture as sole limiter) was **revised, not
confirmed**: varying w_ext freely *can* push S11 well past -4dB (down to
-10dB seen at one point), but only by collapsing S21 to -20 to -50dB in the
same move -- an inverse match/IL trade-off across the whole w_ext range, not
a fixable tuning problem. 0/12 grid points passed both thresholds
simultaneously.

**rhombic_2diag** at finer/lower w_iris2 values did pass phase A (3/9,
vs 0/4 in round 1) -- confirming round 1's monotonic trend continues below
w_iris2=4. But phase B tells a different story: **all three phase-A
survivors scored far worse than both parents on the full v17 score**:

| w_iris2_mm | phase-A screen (S11/S21) | phase-B final score |
|---|---|---|
| 1 | -20.0 / -5.2 dB | **25.58** |
| 2 | -19.6 / -5.7 dB | **23.66** |
| 3 | -10.6 / -5.3 dB | pending (in progress at time of writing) |

This is the same screen-vs-full-score discrepancy already documented for
`corner_cut_2corner`: `screen_at_f0` only asks "does *some* point near f0
look OK", while the full score also penalizes overall bandwidth shape/width
and fc deviation across the fit window. Every rhombic_2diag phase-B search
converged toward `y_wall` near its upper bound (40mm) and BW in the
250-560MHz range -- again an over-coupled/mistuned band shape that the
Bayesian search could not fix within the explored ranges, not a fluke of one
run.

**circular_cross_nvia** is the one genuinely new result: n_perturb=2 (extra
vias at the cross-arm tips, as opposed to ring2's inner arc) passed phase A
at two different w_ext values, unlike every other circular_cross variant.
This shows the family isn't uniformly dead -- the specific perturbation
mechanism matters, not just "circular_cross + some external tuning". Phase B
result: *(pending -- see status note below)*.

## Bottom line (interim, pending final nvia phase-B result)

Across both rounds, every structural variant that reached phase B (4 of 5
completed at time of writing) scored **worse than both `corner_cut`'s own
coupling-sweep best (11.65) and dual-mode (9.31)** -- often by 2x or more.
None is a drop-in improvement over its own parent, let alone a genuine new
top-4 candidate:

- `corner_cut_2corner`: 15.435 -- over-couples structurally, BW ~505MHz vs
  spec's target width, independent of w_ext.
- `rhombic_2diag` (×2 confirmed, ×1 pending): 25.58, 23.66 -- large,
  over-wide bandwidth (up to 560MHz), y_wall pinned at its range boundary.
- `circular_cross_ring2`: eliminated outright, inverse match/IL trade-off
  across the whole w_ext range.
- `circular_cross_nvia`: only phase-A-passing family member; phase-B result
  pending.

The honest read: the four new structural mechanisms tried this round (extra
vias, inner ring, second corner cut, second diagonal iris) each add a
coupling **path**, but none of them fixes the underlying bandwidth/Q
mismatch that keeps these geometries away from dual-mode's tight, well-behaved
response -- they mostly just relocate where the over-coupling happens. This
argues the gap to dual-mode is more fundamental than any single added knob
in this family of variants, consistent with task #29's taper-launch
hypothesis for circular_cross/rhombic specifically, and with corner_cut's
structural (not tunable) over-coupling for the 2-corner variant.

*(This document will be updated with `circular_cross_nvia`'s final phase-B
score once that run completes, and a final ranked verdict on whether any of
the 4 candidates warrants adoption over the existing top-3 non-dual-mode
designs from task #29.)*
