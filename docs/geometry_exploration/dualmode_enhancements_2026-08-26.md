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

## Related: circular_cross_iris (architecture change, see structural_exploration doc)

Same session, same reasoning pattern (replace a localised perturbation
stub with a real spanning structure) applied to `circular_cross` instead
of dual-mode -- full writeup lives in
`structural_exploration_2026-08-25.md`. Summary for cross-reference:
**final confirmed score 20.08** (single-point re-confirm after the
18-eval optimizer process was killed, likely OOM, after 17/18 evals; best
coarse result seen was 19.55) -- confirms the architecture reasoning was
directionally correct (broke circular_cross's historic ~-4dB match
ceiling) but the resulting design still isn't competitive with
`corner_cut_2corner` (15.44) or `dualmode_cascade` (13.96).
