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
straight out of the box, with no tuning at all. *(GP-refined final score
pending -- see status note.)*

*(This document will be updated with dualmode_cascade's confirmed
FINE/FAB-TOLERANCE score, whether the GP search beat the naive starting
point, and a verdict on whether it's worth adopting as a genuine N=4
alternative.)*
