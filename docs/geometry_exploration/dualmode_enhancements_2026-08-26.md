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

## dualmode_cascade: coupling-matrix extraction, round 3 -- the honest ceiling (2026-08-26/27)

User looked at the round-2 (v3) comparison plot and correctly called it out:
*"that one just seems an order 2 filter with another order 2 with an
offset, doesn't seem to be optimal."* Checking the raw data confirmed it:
v3's response was a very narrow, high-Q near-single-pole notch (S11 down to
-26.7dB but only within ~20MHz of center) sitting next to a weak, detuned
satellite bump ~250MHz below it -- not a real 4-pole equal-ripple passband.
Root cause: the v3 ridge search optimized a SINGLE (fc, bandwidth) pair
against the target, which says nothing about whether the underlying 4 poles
are actually distributed the way a Chebyshev filter needs.

### Coupling-matrix extraction (new diagnostic tool)

Built a least-squares fit of the standard mirror-symmetric N=4
coupled-resonator model (`A = M + Omega*W - jR`, `Omega=(f/f0-f0/f)`, reusing
`synthesis.sparams_from_matrix` unchanged) directly against a measured
S11/S21 sweep, recovering the ACTUAL realized `k12=k34`, `k23`, `Qe`, `f0` --
no new EM simulation needed, pure post-processing of data already in hand.
Fitting it to v3's own FAB-TOLERANCE sweep gave the smoking gun:

| | v3 (measured) | ideal N=4 |
|---|---|---|
| k12=k34 | 0.0313 (0.75x -- too weak) | 0.0415 |
| k23 | 0.0367 (1.12x) | 0.0329 |
| Qe | 46.27 (2.09x -- way under-coupled to feed) | 22.18 |

This is the correct methodology CLAUDE.md always intended (section 6's
eigenmode-based k-calibration), realized via curve-fitting instead of
symmetry-wall eigenmode decomposition -- cheaper (reuses existing sweeps)
though less first-principles.

### Iterative coupling-directed correction

Ran an automated loop: sweep -> fit couplings -> apply a damped
`sqrt(ideal/measured)` proportional correction to the responsible dimension
(`w_iris` for k12/k34, `w_inter_mm` for k23, `w_ext` for Qe) -> re-center `a`
(self-similar scaling, same fix as v2->v3) -> repeat.

**k12/k23 converged almost immediately and almost exactly**: after ONE
correction step, `w_iris` 17.0->19.081mm and `w_inter_mm` 12.0->11.001mm
gave **k12=0.0412 (0.99x ideal), k23=0.0318 (0.97x ideal)** -- confirms the
proportional-correction methodology works well for these two.

**Qe/`w_ext` diverged and had to be caught.** The same damped correction
pushed `w_ext` 18.1->27.944mm, which made Qe WORSE (52.88->143.11), not
better -- the naive "wider aperture couples more strongly" assumption broke
down, and the next planned step would have pushed `w_ext` to 70.9mm (killed
before that ran). Diagnosed by falling back to a safe empirical scan of
`w_ext` within the previously-validated 10-24mm search box, at the
now-frozen good `w_iris`/`x_iris`/`y_wall`/`w_inter_mm`:

| w_ext | Qe (fit) | k12 | k23 | bw (raw) | s11w (raw) |
|---|---|---|---|---|---|
| 18.1 | 96.29 (4.3x) | 0.84x | 1.08x | 86.5 MHz | -2.83 dB |
| 20.0 | 111.79 (5.0x) | 0.99x | 0.93x | 113.7 MHz | -1.79 dB |
| 22.0 | 103.41 (4.7x) | 0.96x | 0.96x | 142.7 MHz | -2.72 dB |
| 24.0 | 113.73 (5.1x) | 0.98x | 0.96x | 168.1 MHz | -2.65 dB |

Two findings: (1) Qe never gets anywhere near 22.18 across the entire safe
`w_ext` range -- stuck at 4.3-5.1x, non-monotonic (up/down/up), most likely
reflecting a poorly-conditioned fit in this weak-coupling regime rather than
a real reversed physical law. (2) Match quality (raw `s11w`, the directly
trustworthy number) stays uniformly poor (-1.8 to -2.8dB) across the WHOLE
range regardless of `w_ext` -- a genuine ceiling, not a tuning miss.
Bandwidth DOES respond as expected to `w_ext` (86->114->143->168MHz,
w_ext=22.0 lands almost exactly on the 143.5MHz target), confirming `w_ext`
does control bandwidth normally; it's specifically the MATCH that won't
improve.

### Final confirmed result (FAB-TOLERANCE, coupling-corrected design)

```
a=60.0  w_iris=19.1  x_iris=30.1  y_wall=9.0  w_ext=18.1  w_inter_mm=11.0
fc=2.867GHz   bw=101MHz   s11w=-2.79dB   il=-3.78dB
standard v17 score = 17.878
```

**Worse aggregate score than v3 (17.88 vs 13.83)** -- but examining the raw
S11/S21 curve directly (not just the score) shows something the score
misses: the main passband is now noticeably broader and more physically
sensible (a single, smooth S11 dip spanning roughly 2.80-2.94GHz, best point
-7.36dB) instead of v3's absurd near-single-frequency -26.7dB spike. The
underlying pole coupling (k12, k23) IS now correct. **But a persistent weak
satellite mode near 2.55-2.60GHz remains in BOTH v3 and this
coupling-corrected design** -- same order of magnitude, same rough location,
present regardless of the coupling correction. This is not an artifact of
the search methodology; it is a real additional resonance of the physical
cascade structure that the simple in-line 4-pole coupling-matrix model does
not account for (likely a spurious mode of the coupled-cavity system outside
the intended TE102/TE201 dual-mode pair -- not identified further tonight).

![v3 vs coupling-corrected vs ideal N=4](../../output/imgs/dualmode_cascade_final_comparison.png)

### Honest final verdict

- The N2/N4 scoring bug (round 2) was real and stays fixed.
- The self-similar-scaling bug (v2->v3) was real and stays fixed; v3's
  centering/bandwidth-matching methodology is sound.
- v3's *shape*, however, was an illusion the aggregate score could not
  detect -- the user's visual read was correct, and the coupling-matrix
  extraction tool built tonight confirmed exactly why, in quantitative terms.
- Individual coupling correction (k12, k23) works well and is now validated
  as a real, reusable technique for this topology.
- External-Q correction via `w_ext` hit a genuine wall: bandwidth responds
  normally, but IN-BAND MATCH does not improve anywhere in the safe range.
  Fixing this for real needs a different external-coupling mechanism (a
  different taper/feed geometry, not just a wider aperture on the same
  structure) -- out of scope for tonight.
- A persistent spurious satellite mode near 2.55-2.60GHz appears in every
  attempt regardless of coupling tuning -- a genuine, previously-undetected
  structural issue with `dualmode_cascade` worth investigating before
  further optimization effort is spent on this topology.
- **Neither v3 nor the coupling-corrected design is a clean, fully genuine
  order-4 Chebyshev response.** v3 wins on the (now known to be
  incomplete) aggregate score; the coupling-corrected design wins on
  correct pole placement and a more physically sensible main passband, at
  the cost of worse absolute match. Recommend treating this whole line of
  investigation as informative but NOT yet ready to replace the standalone
  dual-mode design (still the project's best result, score 9.31) as the
  design to prototype.

## dualmode_cascade: eigenmode ground truth -- the real mechanism (2026-08-27)

User's follow-up push: *"it's not ok, let's rethink the problem, it should
be an order 4 filter centered at fc but it's like a degenerated filter with
two different center frequencies."* Right call, and now confirmed at the
ground-truth level (no S-parameter interpretation ambiguity).

### Closed-cavity eigenmode analysis (new capability)

Built a standalone eigenmode solver for `dualmode_cascade` reusing
`geometries.dualmode_cascade()`'s own via-layout generator UNCHANGED
(`w_ext_mm=0` collapses the port gap, sealing both ends -- the same
transformation `palace_dualmode.py` already applies to the single-cavity
case), so the eigenmode via positions are guaranteed identical to the real
driven design's, just with ports closed. This directly counts the real
resonances of the passive structure -- no curve-fitting, no S-parameter
ambiguity.

Results (frequencies within the band of interest, GHz):

| design | eigenmodes | structure |
|---|---|---|
| old naive (w_inter=16.31, small a/w_iris) | 2.515, 2.627, 2.768, 2.920, 3.063, 3.131 | 6 modes, roughly evenly spaced (110-150MHz gaps) -- no obvious pair clustering |
| v3 (w_inter=12.0, larger a/w_iris) | 2.701, 2.746, 2.943, 2.983 | **exactly 4 modes, split into 2 tight pairs** (45MHz, 40MHz splits) separated by a 197MHz gap |
| coupling-corrected (w_inter=11.0) | 2.646, 2.677, 2.947, 2.982 | same 2-pair pattern, gap WIDENED to 270MHz |

![eigenmode mode map](../../output/imgs/dualmode_cascade_eigenmode_map.png)

**This is the real mechanism, confirmed directly**: v3 and the
coupling-corrected design genuinely have only 4 poles (not 4+spurious as
round-3's docs speculated) -- but the inter-cavity coupling (`w_inter_mm`)
is too weak relative to each cavity's own internal splitting (driven up by
the larger `w_iris` from tonight's tuning) to interleave the two cavities'
pole-pairs into one coherent passband. Instead the two cavities behave as
two nearly-independent 2-pole sub-filters -- literally two different center
frequencies, exactly the user's diagnosis. It also explains why the earlier
coupling-matrix curve-fit (round 3) gave unreliable numbers: that fit
assumes a single interleaved in-line chain, which cannot correctly describe
two separated pairs -- the "correction" it drove (further WEAKENING
`w_inter_mm`, 12.0->11.0) made the split worse (197->270MHz gap), not
better, which the old round-3 docs mis-attributed to an unrelated "external-Q
ceiling."

### Does reverting w_inter_mm fix it? No -- not by itself

Tested directly: swept `w_inter_mm` from 11 back up to 18mm, holding
tonight's larger `a`/`w_iris`/`x_iris`/`y_wall`/`w_ext` fixed.

| w_inter_mm | bw (MHz) | fc (GHz) | satellite level |
|---|---|---|---|
| 11.0 | 79 | 2.880 | -10.1 dB |
| 13.0 | 347 | 2.860 | -5.2 dB |
| 15.0 | 378 | 2.820 | -3.2 dB |
| 16.31 (original value) | 397 | 2.800 | -2.7 dB |
| 18.0 | 423 | 2.760 | -2.6 dB |

![w_inter_mm recheck overlay](../../output/imgs/dualmode_cascade_winter_recheck_overlay.png)

The satellite weakens monotonically but **plateaus around -2.6 to -3dB and
never fully disappears**, even at w_inter_mm=18 (above the original
baseline's own 16.31). Meanwhile bandwidth overshoots 3x past the 143.5MHz
target and `fc` drifts monotonically further from 2.87GHz (2.880->2.760) as
`w_inter_mm` grows. **A straight 1D revert trades the pair-split problem for
two new ones (bandwidth blowout, centering drift) faster than it fixes the
split** -- confirms the user's original centering concern was never fully
resolved either, it's entangled with the same coupling-balance problem.

Root cause, precisely stated: growing `w_iris` (17.0->19.1mm, done to fix
k12 in round 3) increased each cavity's own internal pole splitting beyond
what the SAME `w_inter_mm` used at the old, smaller `w_iris` (15.26mm) could
still interleave. The two knobs were tuned independently (each "fixed" its
own target ratio in isolation) without accounting for how they interact.

### Honest status

A genuine order-4 passband from this topology is not yet achieved. What IS
now understood, precisely and with ground-truth evidence:
- The failure mode is real and specific: inter-cavity coupling too weak
  relative to the (now-larger) intra-cavity coupling, causing pole-pair
  splitting rather than interleaving.
- Fixing it needs a **joint** re-optimization of `w_iris` (intra) and
  `w_inter_mm` (inter) together -- not reverting one while holding the other
  fixed -- most likely landing at intermediate values for both (smaller
  `w_iris` than round 3's 19.1mm, `w_inter_mm` in the 13-16mm range where
  the pair gap first closes), plus the usual `a` re-centering for whatever
  `fc` results.
- **Not launched tonight** -- this is a genuinely new, better-informed
  starting point for a future re-optimization, not something to run
  unattended after this many hours of investigation. Flagged as the concrete
  next step, pending the user's go-ahead.

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
