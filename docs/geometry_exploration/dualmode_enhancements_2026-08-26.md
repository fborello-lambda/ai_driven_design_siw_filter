# Dual-mode enhancements: cascade and second-wall experiments (2026-08-26)

User-prompted architecture changes on the WINNING design (dual-mode, score
9.31), motivated by its one persistent shortfall documented all session:
bandwidth stuck at ~318MHz against the 143.5MHz (5% FBW) target, confirmed
by a 60-eval Bayesian search of the landed 5D box (`a, w_iris, x_iris,
y_wall, w_ext`) that converged on the exact pre-session point a much
smaller search had already found -- decisive evidence that box's optimum,
not a search-budget problem (see `overnight_dualmode_2026-08-24.md`). Two
genuinely new degrees of freedom that box never had, tried in parallel.

## dualmode_2wall: a second parallel iris row -- negative result

**"What happens with another wall in parallel, some distance from the
existing one?"** Implemented `dualmode_2wall`: the landed cavity plus a
second floating transverse iris row (`w_iris2_mm`, `iris_sep_mm`),
identical construction to the existing row, defaulting to reproduce
dual-mode exactly at `w_iris2_mm<=0` (regression-verified byte-identical).

Round 1 (4 isolated screens, second wall bolted onto the landed point,
`w_iris2_mm` and `iris_sep_mm` in {8,15}): **all 4 failed decisively**
(S11 ~-2.6 to -2.7dB, resonance destroyed, S21 down to -40dB).

Round 2 (promoted `w_iris2_mm`/`iris_sep_mm` to searched dimensions, full
22-eval joint search over all 7D): **21 of 22 evaluated points screened out
entirely (zero resonance, `fc=0`)** -- not merely a bad score, no resonance
in the fit window at all. The one non-screened point (the search's own
warm-start, `w_iris2_mm=10, iris_sep_mm=10`) also failed (screened on the
FINE confirm). Every region of the 7D box that was actually sampled --
including near-zero `w_iris2_mm` values that should behave close to plain
dual-mode -- destroys the resonance.

**Final confirmed score: 28.51** (FINE=28.72, FAB-TOLERANCE=28.51, at the
un-improved warm-start point since the GP search never found anything
better) -- `s11w=-1.20dB, il=-32.49dB`: essentially total reflection with
massive insertion loss, the worst confirmed result of any geometry this
entire session.

**Conclusion: negative.** A second floating iris row, at least built the
same way as the first and searched across this box, does not work for
this cavity. Two candidate reasons, neither confirmed: (a) two floating
iris rows may over-constrain the degenerate TE102/TE201 pair's field
pattern in a way one row does not -- a single "partial reflector" perturbs
without destroying the pair, but a second one might block the mode
entirely rather than adding a second `resonant section`; (b) the box's
ranges may simply not contain the narrow region (if any) where it works.
Not chasing (b) further under this deadline -- (a) is the more likely
explanation given how UNIFORMLY it failed (21/22, not "mostly except a
corner of the box").

## dualmode_cascade: two cavities in series (N=4) -- promising result

**"We can also try to add 2 dualmodes in cascade, order 4 filter."**
Implemented `dualmode_cascade`: two square dual-mode cavities sharing
width `a_mm` (mirror-symmetric), each with its own floating internal iris
(cavity 1: `x_iris`/`w_iris`; cavity 2 mirrors by default), joined by a
NEW full wall-to-wall inter-cavity coupling row (`w_inter_mm`, defaults to
`w_ext_mm`) -- genuinely new mesh topology, not a delta (the single-cavity
builder has no notion of a second cavity). `poles_per_cavity` correctly
reports 4 via a per-name override. ~2x the tets of every other geometry
this session, needed its own coarser mesh preset (147461 tets at
(5.5,0.8,4.0), vs 295908 at the standard preset).

Screen results: **3 of 3 tested points passed cleanly** (S11 -22.1, -30.4,
-23.5dB across w_inter=16.31/12/20) -- remarkably robust even at the naive,
un-tuned mirror-symmetric starting guess. Full 20-eval optimization
(6D: `a, w_iris, x_iris, y_wall, w_ext, w_inter_mm`): the very first
point (the naive mirror-symmetric guess, identical params to dual-mode's
own landed design duplicated for both cavities) scored **14.72**
(`s11w=-7.76dB, bw=336.6MHz, il=-2.33dB`) -- already close to
`corner_cut_2corner`'s 15.44 (the best non-dual-mode result all session)
straight out of the box, with no tuning at all.

**Final confirmed score: 13.964** (`s11w=-10.28dB, bw=348MHz, il=-1.92dB`,
FAB-TOLERANCE at a=57.2, w_iris=15.3, x_iris=28.7, y_wall=8.6, w_ext=16.3,
w_inter=16.3). The 20-eval GP search never found anything better than the
naive mirror-symmetric starting point (12/20 evals screened out entirely --
a fragile search space, but the one good region is very robust): best
(coarse)=14.722, FINE=14.346, FAB-TOLERANCE=13.964. **This is the best new
(non-dual-mode) result of the entire session**, clearly ahead of
`corner_cut_2corner`'s 15.44, though still short of dual-mode's 9.31.

**Verdict: adopt.** Unlike every other new structural variant this
session, `dualmode_cascade` needed essentially no tuning to work well --
duplicating dual-mode's own already-optimized single-cavity parameters
into two cascaded cavities landed within 10% of the joint search's best
found value. That's a strong practical result: an N=4 filter, built from
a proven N=2 building block, reaching competitive performance on the
first educated guess. Worth prototyping over any of the single-cavity
alternative geometries explored this session.

### 0.1-8 GHz comparison

![dual-mode vs dualmode_cascade, 0.1-8GHz](../../output/imgs/final_dualmode_vs_cascade_0_8ghz.png)

Confirms the qualitative benefit expected from going N=2 -> N=4: the
cascade's passband skirts are visibly steeper than the standalone dual-
mode's (faster roll-off on both sides of 2.87GHz), the direct payoff of
adding a second resonant stage. The standalone design still wins on the
v17 score (9.31 vs 13.96) because that score weights match/bandwidth-to-
target more heavily than selectivity -- the cascade is the more
_capable_ filter (closer to a real N=4 response shape) even though it
isn't yet as precisely tuned to the 143.5MHz target as dual-mode's own
60-eval-refined design. Both share a similar spurious-mode floor above
~4GHz, as expected since they're built from the same unit cell.

## dualmode_cascade selectivity investigation (2026-08-26, follow-up)

User-prompted follow-up: "can we try to make the cascade more selective?"
Two-part investigation: fix the scoring, then try a coupling-matrix-directed
design change. Net result: the scoring bug is real and fixed, but the
directed fix attempted here did not yield a better design -- see verdict.

### Part 1: the search was scored against the wrong ideal target

`dualmode_cascade` is a genuine 4-pole device (`poles_per_cavity` override =
4 in `topologies/geometry.py`: 2 cascaded cavities x 2 degenerate TE102/TE201
modes each). The 2026-08-26 search that produced the "adopt, score=13.964"
verdict above scored it with `FilterSpec(N=2)` -- the same default every
scratch script this session used for the single-cavity dual-mode design,
copy-pasted without checking it was still appropriate. Scoring a 4-pole
device's shape against a 2-pole Chebyshev ideal never rewards the steeper
skirts / flatter passband a correctly-tuned 4-pole filter should have.

Verified numerically before spending compute on a re-run: rescoring the
already-computed FINE-confirm response (same physical measurement) against
a proper `FilterSpec(N=4)` ideal target raised the RMSE-based score from
14.346 to 15.681 -- i.e. the existing design is *further* from a true 4-pole
equal-ripple shape than the old (wrong) score suggested, not closer.

Re-ran the full pipeline under the corrected objective: a fresh 22-eval GP
search (same 6D box), FINE confirm, FAB-TOLERANCE confirm, all scored against
`FilterSpec(N=4)`. Result: **the search converged to the IDENTICAL physical
geometry** (a=57.2, w_iris=15.3, x_iris=28.7, y_wall=8.6, w_ext=16.3,
w_inter_mm=16.3 -- bit-for-bit the same landed point), with identical
measured electricals (fc=2.887, bw=348MHz, s11w=-10.28dB, il=-1.92dB) --
only the score changed, from 13.964 (wrong N=2 comparison) to **15.563
(correct N=4 comparison, official)**. Same fragility pattern as before
(15/22 evals screened to zero resonance either way). **The scoring bug is
real and now fixed, but it was not the reason the search couldn't find a
more selective design** -- the GP search itself, under either objective,
keeps re-finding the same naive point as the best reachable in its budget.

### Part 2: coupling-matrix-directed sweep (not blind search)

Rather than run more blind GP evals, computed what the ideal N=4 design
actually calls for: `synthesis.chebyshev_g(4, 0.1)` + `coupling_matrix` (both
already N-generic, no new code needed) give, for FBW=5%:

```
k12 = k34 = 0.0415   (each cavity's own internal iris coupling, ~ w_iris)
k23        = 0.0329   (inter-cavity coupling, ~ w_inter_mm)
k23/k12    = 0.79     (the middle coupling should be noticeably WEAKER)
Qe_in = Qe_out = 22.18
```

The naive design has `w_inter_mm` (16.3) *larger* than `w_iris` (15.3) --
the inter-cavity link is if anything looser than each cavity's own internal
coupling, the opposite of what a symmetric N=4 Chebyshev wants. Hypothesis:
this is why the measured response is one wide, soft hump (bw=348MHz, 2.4x
the 143.5MHz target) instead of a properly split 4-pole passband -- the
middle coupling isn't decoupled enough to let the two cavity-pairs act as
distinct stages.

Ran a directed (not GP, not blind) 6-point sweep of `w_inter_mm` alone
(9.0/10.5/12.0/13.5/16.31-baseline/18.5), all other landed dimensions held
fixed, scored under `FilterSpec(N=4)`:

| w_inter_mm | fc (GHz) | bw (MHz) | s11w (dB) | il (dB) | score |
|---|---|---|---|---|---|
| 9.0  | -- (screened, zero resonance) | | | | 1e9 |
| 10.5 | 3.049 | 87.4  | -2.40 | -3.21 | 27.73 |
| 12.0 | 3.009 | 124.4 | -3.20 | -2.87 | 25.07 |
| 13.5 | 2.989 | 290.2 | -4.95 | -2.74 | 21.48 |
| **16.31 (baseline)** | **2.929** | **336.6** | **-7.76** | **-2.33** | **15.57** |
| 18.5 | 2.889 | 259.1 | -4.16 | -2.23 | 16.77 |

![w_inter_mm sweep](../../output/imgs/dualmode_cascade_winter_sweep.png)

**Finding: `w_inter_mm` is not an independent bandwidth knob in this
topology -- it also detunes the cavity's own resonant frequency.** Narrowing
it (9.0->13.5) does narrow bandwidth as the coupling-matrix math predicted,
but it *also* drags `fc` up from 2.887 toward 3.05 GHz (physically sensible:
a narrower full-width via-fence gap adds more inductive loading, raising the
loaded resonance of both cavities), and match quality (`s11w`) gets
monotonically *worse* in that direction, not better. Widening it past
baseline (18.5) pulls `fc` back down closer to 2.87 GHz and narrows bandwidth
too, but again at the cost of match quality. **No point in the sweep beat
the baseline's score (15.57 remains the best of all 6).**

### Verdict

The N=2/N=4 scoring bug was real and is now fixed (corrected official score:
**15.563**, not 13.964 -- still the best new non-dual-mode result of the
whole session, ahead of `corner_cut_2corner`'s 15.44... actually now
essentially tied with it). But a 1-dimensional directed sweep cannot
separate "more selective" from "detuned," because `w_inter_mm` moves both at
once. **Genuinely improving this design's selectivity needs a joint
re-optimization** -- at minimum `a` (cavity size, to re-center `fc` as
`w_inter_mm` moves) together with `w_inter_mm` itself, ideally a fresh full
6D GP search run under the now-corrected `FilterSpec(N=4)` objective with a
larger budget than 22 evals (this topology's screen-out rate, ~65-70%,
already eats most of a small budget). **Not launched automatically** --
flagged here as the concrete next step, pending the user's go-ahead, since
this investigation already used substantial compute this session.

## dualmode_cascade: directed re-optimization, round 2 -- a real win (2026-08-26)

User asked to kill the blind extended search and re-optimize "with new
algorithms and not blindly," after two more findings needed acting on: (a)
the design "is also not centered around the desired center frequency" and
(b) a proposal to use the cheap coarse-GPU eval as a fast triage before
committing to deeper search. Both addressed directly.

**Score fix.** `evaluate()` gained an optional `score_kwargs` passthrough to
`score()` (backward compatible). The default centering weight (`w_fc=0.05`)
was too weak: for the landed design it contributed only ~1.4 of a ~15.7
total score, versus ~6.4 for shape and ~4.2 for bandwidth -- centering was
mostly enforced *indirectly*, through the fixed-window shape-fit. Reran with
`w_fc=0.2` so centering is a first-class term.

**Algorithm ("new, not blind"): physics-informed ridge search.** Root cause
of the wide bandwidth: `w_inter_mm` (inter-cavity coupling) is NOT
independent of `fc` in this topology -- narrowing it (correctly, per the
N=4 coupling-matrix math) also drags `fc` up, because the cavity scales
self-similarly (`L_cav = 2*a`), so `fc ~ 1/a` to first order. Fix: for each
candidate `w_inter_mm`, compute the `a` that re-centers `fc` to 2.87GHz via
`a_new = 57.21 * fc_sweep(w) / 2.87` (`fc_sweep` interpolated from the
earlier 5-point sweep), then test it directly -- a design-of-experiments
line search, not GP/random sampling.

**v2 attempt -- failed, root-caused, not just abandoned.** First try grew
`a` while leaving `w_iris`/`x_iris`/`y_wall`/`w_ext` fixed in absolute mm.
3/3 points screened out. Diagnosed with a wide 2.0-3.6GHz sweep (bypassing
the narrow screen window) rather than accepting the negative result: a
resonance DID exist, but badly matched (-7.94dB at ~2.70GHz, not the
predicted 2.87GHz, messy non-clean shape) -- growing the cavity without
scaling the iris/aperture positions moved them to the wrong relative
location, degrading coupling directly, not just shifting frequency.

**v3 fix -- self-similar scaling.** Scale `w_iris`/`x_iris`/`y_wall`/`w_ext`
by the SAME factor as `a` (preserves their relative position/coupling on
the bigger cavity); only `w_inter_mm` stays at its deliberately-chosen
absolute value (the one knob intentionally perturbed away from pure
self-similarity). Single-point validation: `w_inter_mm=12.0` gave
**fc=2.869GHz (1.3MHz off target)** and bw=101.5MHz -- confirms the fc~1/a
model was right all along; only the missing proportional scaling was the
bug.

**Ridge search results** (8 points, w_inter_mm 11.0-16.31, each with
correctly-scaled companion `a`/`w_iris`/`x_iris`/`y_wall`/`w_ext`):

| w_inter_mm | fc (GHz) | bw (MHz) | note |
|---|---|---|---|
| 11.0 | 2.869 | 81.4 | |
| 11.5 | 2.869 | 88.7 | |
| 12.0 | 2.869 | 100.3 | best ridge point |
| 12.5 | -- | -- | screened out |
| 13.0 | 2.869 | 263.8 | jump -- discontinuity |
| 13.5 | 2.869 | 272.7 | plateaued near 13.0 |
| 14.5 | -- | -- | screened out |
| 16.31 (re-centered) | 2.869 | 325.2 | |

`fc` landed at the EXACT SAME value (2.869GHz) for every single non-screened
point -- the self-similar-scaling recipe for centering is completely robust.
But bandwidth is NOT a smooth function of `w_inter_mm`: it jumps roughly 2.6x
between w=12.0 and w=13.0, with w=12.5 screening out in between -- a genuine
discontinuity/mode-transition in this narrow design space, not measurement
noise (consistent with the ~50-70% screen-out fragility seen everywhere in
this topology all session).

**Local refinement** (nudging `w_iris`/`w_ext` around the w=12.0 winner,
greedy/sequential): `w_iris +1.0mm` then `w_ext +1.0mm` compounded to
improve the boosted score from 15.19 to **13.48**, also improving match
(`s11w` from -2.83 to -3.92dB) and bandwidth (100.3 -> 107.4MHz).

**Final confirmed result (FAB-TOLERANCE, 0.1mm):**

```
a=60.0  w_iris=17.0  x_iris=30.1  y_wall=9.0  w_ext=18.1  w_inter_mm=12.0
fc=2.867GHz   bw=119MHz   s11w=-3.35dB   il=-2.28dB
standard v17 score = 13.827
```

![new optimized dualmode_cascade vs ideal N=4](../../output/imgs/dualmode_cascade_v3_vs_ideal_N4.png)

**Comparison to the old naive (mirror-duplicate) design:**

| | old naive | new optimized | ideal N=4 target |
|---|---|---|---|
| fc | 2.887 GHz | **2.867 GHz** | 2.870 GHz |
| bw | 348 MHz | **119 MHz** | 143.5 MHz |
| s11w | **-10.28 dB** | -3.35 dB | (well-matched) |
| il | **-1.92 dB** | -2.28 dB | 0 dB (lossless) |
| standard v17 score | 15.563 | **13.827** | 0 |

**Verdict: a genuine, honest improvement, not a strictly-better-in-every-way
one.** Centering and bandwidth are both dramatically closer to the true N=4
target (bandwidth error dropped from 2.4x-over to 0.83x-under -- overall
closer to target either way). Match quality (`s11w`) got WORSE in exchange
(-3.35 vs -10.28dB) -- the net v17 score improves because the objective
weights shape/bandwidth/centering more heavily than raw match, but a real
board built to `s11w=-3.35dB` would reflect noticeably more power than the
old design. **The remaining open problem for this design is match quality**,
not centering or bandwidth anymore -- a further round tuning `w_ext`
specifically for external Q (Qe_in=22.18 for N=4, per the earlier
coupling-matrix calculation) is the natural next step, not attempted here
given the compute already spent on this investigation.

## Related: circular_cross_iris (architecture change, see structural_exploration doc)

Same session, same reasoning pattern (replace a localised perturbation
stub with a real spanning structure) applied to `circular_cross` instead
of dual-mode -- full writeup lives in
`structural_exploration_2026-08-25.md`. Summary for cross-reference:
**final confirmed score 19.93** (FAB-TOLERANCE; the 18-eval search only
*appeared* stalled under heavy concurrent load -- a flawed process check
misdiagnosed it as an OOM kill mid-session, corrected in
`structural_exploration_2026-08-25.md` once it finished normally) --
confirms the architecture reasoning was directionally correct (broke
circular_cross's historic ~-4dB match ceiling) but the resulting design
still isn't competitive with `corner_cut_2corner` (15.44) or
`dualmode_cascade` (13.96).
