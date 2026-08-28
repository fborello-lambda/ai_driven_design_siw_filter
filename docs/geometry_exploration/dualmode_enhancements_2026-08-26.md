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

## dualmode_cascade: eigenmode-targeted search, round 5 -- a real breakthrough (2026-08-27)

Computed the exact ideal N=4 closed-cavity pole target analytically
(eigenvalues of the inner 4x4 coupling matrix, no simulation): poles at
2.7836/2.8298/2.9108/2.9590 GHz, gaps **46.1/81.1/48.2 MHz**, centered
2.8708GHz. v3's outer gaps (45, 48MHz) already nearly matched this --
`w_iris` was never the problem. Only the middle gap (governed by
`w_inter_mm`) was wrong (197MHz vs ideal 81.1MHz).

Ran an 8-point eigenmode-only sweep of `w_inter_mm` (13-22mm, `a=60`/
`w_iris=19.1` held fixed), scoring against this ideal gap pattern directly
(gap RMSE in MHz) -- ground truth, no driven S-parameter proxy:

| w_inter_mm | gap1 | gap2 | gap3 | center | RMSE |
|---|---|---|---|---|---|
| 13.0 | 51.7 | 253.5 | 51.0 | 2.803 | 99.6 |
| 14.0 | 64.7 | 244.8 | 59.6 | 2.797 | 95.3 |
| 15.0 | 79.7 | 236.0 | 68.2 | 2.791 | 92.2 |
| 16.0 | 98.8 | 226.9 | 77.0 | 2.783 | 91.0 |
| 17.0 | 117.9 | 218.8 | 84.9 | 2.776 | 92.2 |
| 18.0 | 138.6 | 211.3 | 92.4 | 2.768 | 95.7 |
| **20.0** | **114.2** | **83.9** | **105.4** | **2.827** | **51.4** |
| 22.0 | 7.7 (near-crossing) | 180.7 | 115.1 | 2.797 | 72.7 |
| ideal | 46.1 | 81.1 | 48.2 | 2.871 | 0 |

![pole migration vs w_inter_mm](../../output/imgs/dualmode_cascade_pole_migration.png)

**Surprise finding #1**: 13-18mm is a dead end -- RMSE plateaus around
91-100MHz, never approaching v3's own 12mm point (~67MHz). Increasing
`w_inter_mm` from 12 initially makes the middle gap WORSE, not better.

**Surprise finding #2, important**: the user's own visual pick from the
EARLIER driven S21 overlay plot -- w_inter_mm=18, which looked like the
most merged/single-passband shape by eye -- is actually **eigenmode-confirmed
as one of the worst points tested** (RMSE=95.7, middle gap 211MHz, wider
than v3's own 197MHz). The apparent visual improvement in the driven S21
curve was almost certainly a port-excitation artifact (the weaker pole
becoming harder for the port to excite/see, not actually moving closer in
frequency) -- exactly the ambiguity building the eigenmode tool was meant to
resolve. Driven S-parameter shape is not a reliable proxy for pole-structure
correctness in this fragile regime.

**Breakthrough**: `w_inter_mm=20` gives **RMSE=51.4MHz, the best result of
the entire multi-day cascade investigation** -- beating v3, the coupling-
corrected design, and every earlier attempt. The middle gap (83.9MHz)
almost exactly matches the ideal 81.1MHz. There's a genuine regime
transition between w=18 (worst) and w=20 (best) -- consistent with the
mode-crossing/discontinuity behavior seen earlier in the driven sweeps
(the w=12.5 discontinuity). w=22 shows an actual near-crossing (7.7MHz
gap between two poles) -- w=20 sits close to a sensitive transition point,
so this region may be fragile and needs care around exact dimensions.

At w=20, the OUTER gaps (114, 105MHz) are now too large vs ideal (46, 48)
-- `w_iris=19.1` is the thing out of balance at this coupling strength.
Center (2.827) is ~44MHz low of ideal, needs `a` re-centering.

**Next step (not yet run, pending user go-ahead)**: a small joint
follow-up -- reduce `w_iris` (try ~15-17mm) paired with `w_inter_mm` near
20, still eigenmode-only (cheap, no driven sim needed yet), to bring the
outer gaps down to ~46/48 while keeping the middle gap near 81. Once a
good eigenmode candidate is found, re-center `a`, THEN move to Stage 2
(external `w_ext`/Qe tuning via driven sweep) and Stage 3 (final FINE+FAB
confirm) as originally planned.

## dualmode_cascade: joint eigenmode search -- best bandwidth of the whole investigation (2026-08-27)

User's follow-up: "run the eigenmode, find the best, then optimize with
RMSE if that's the best approach, or propose another." Confirmed: RMSE
against the analytically-computed ideal pole pattern, searched jointly over
`(w_iris, w_inter_mm)`, is the right approach -- and it worked.

### A cautionary note first: the user's own visual pick was wrong

The user picked `w_inter_mm=18` from the earlier driven S21 overlay plot as
looking "most like a 4th order Chebyshev." The 1D eigenmode sweep (prior
section) directly disproved this: w=18 eigenmode-confirms as one of the
*worst* points tested (gap RMSE=95.7, middle gap 211MHz -- wider than v3's
own 197MHz). The apparent visual improvement in the driven S21 curve was a
port-excitation artifact (a pole becoming harder for the feed to see, not
actually moving closer in frequency) -- exactly the ambiguity eigenmode
ground truth exists to catch. Worth remembering for future visual
inspection of driven S-parameter plots on this fragile topology.

### Joint (w_iris, w_inter_mm) GP search

Warm-started with the 9 already-known 1D-sweep points (no re-simulation),
then explored jointly (skopt GP, 16 new eigenmode-only evals, ~25 total),
minimizing RMSE against the ideal gaps (46.1/81.1/48.2 MHz). Converged
tightly and repeatably (4 consecutive evals within noise of each other):

**Winner: `w_iris=13.0mm`, `w_inter_mm=13.706mm`** -- gap RMSE=**26.1MHz**,
gaps [90/83/38]MHz, center 2.8957GHz. This is the best gap-pattern match of
the entire cascade investigation (previous best: v3's own RMSE~67MHz at
w_iris=19.1/w_inter_mm=12). Confirms the hypothesis from the 1D sweep: a
*smaller* `w_iris` (13.0 vs the 19.1 arrived at through rounds 2-3's
uncoordinated single-knob tuning) paired with `w_inter_mm` near 13.7-14
brings the middle gap in line with ideal without blowing up the outer gaps.

Tested a candidate x_iris-symmetry fix (x_iris=30.0 exactly vs the
carried-over 30.1, in case the 0.1mm offset between the two nominally
mirror-identical cavities explained the outer-gap asymmetry) -- negative
result, RMSE actually got very slightly worse (27.4 vs 26.1). The
asymmetry is a real feature of this coupling regime, not a symmetry bug.

### Driven confirm

Re-centered `a` (60.0->60.52, proportional scaling of x_iris/y_wall/w_iris
with it, `w_inter_mm` held fixed as the deliberate knob) for the measured
eigenmode center (2.8957 vs ideal 2.8708), then ran ONE driven sweep
(`w_ext=18.1` unchanged -- Stage 2 external-Q retuning not yet done):

```
a=60.52  w_iris=13.11  x_iris=30.36  y_wall=9.08  w_ext=18.1  w_inter_mm=13.71
fc=2.800GHz   bw=165.5MHz   s11w=-2.20dB   il=-3.92dB
```

![eigenmode-search winner vs ideal N=4](../../output/imgs/dualmode_cascade_eigensearch_vs_ideal.png)

**bw=165.5MHz is the best bandwidth match of the ENTIRE cascade
investigation** -- vs v3's 348MHz (2.4x over target) and every earlier
attempt. This directly validates the eigenmode-targeted approach: fixing
the actual pole structure (not chasing an aggregate S-parameter proxy)
produces a design whose bandwidth control is fundamentally sound, without
even touching external coupling. `fc` is 70MHz low of target -- the
unloaded-eigenmode-to-loaded-driven frequency shift is design-dependent
(v3 shifted UP under loading, this candidate shifted DOWN) and isn't
captured by the simple 1/a rescaling; a further small `a` correction
informed by this measurement would fix it. Match (`s11w`=-2.20dB) remains
poor because `w_ext` has never been retuned for this candidate -- Stage 2
(external coupling, planned from the start) is the natural next step, not
yet run.

### Status

This is the strongest structural result of the whole cascade investigation
-- correct pole interleaving AND close-to-target bandwidth, achieved via
principled eigenmode-ground-truth search rather than driven-response
guesswork. Remaining work before a final confirmed design: (1) a small
further `a` correction for the loading-induced fc shift, (2) Stage 2
external-`w_ext` retuning for match, (3) final FINE+FAB driven confirm.
Not run tonight -- flagged as the next step.

## dualmode_cascade: fc + external-Q fix -- the best shape of the whole investigation (2026-08-27)

Final chapter. Fixed the two remaining problems in the joint-eigenmode-
search winner (fc 70MHz low, match poor because `w_ext` was still carrying
a value tuned for a completely different internal structure from round 2/3).

### fc fix: direct empirical `a` correction

Rather than route through the unloaded eigenmode center (unreliable --
each design's unloaded-to-loaded frequency shift is design-dependent, not
a fixed offset), corrected `a` directly from the measured DRIVEN fc via
the same fc~1/a scaling used all session: `a=60.52 -> 59.044` (measured
fc=2.800 -> target 2.870), with `w_iris`/`x_iris`/`y_wall` scaled
proportionally. Result: **fc=2.860, only 10MHz off target** -- confirms
the direct approach works better than trying to model the loading shift.

### External-Q fix: group-delay method attempted, fell back to empirical scan

Attempted the standard method CLAUDE.md specifies (`Qe =
omega0*tau_S11(omega0)/4`, using the phase column Palace already writes to
`port-S.csv` -- no new Palace config needed). Result came back **negative**
(-8.50 vs ideal 22.18) -- a sign/convention artifact, most likely because
the shallow match at this point gives no clean S11 resonance feature for
the method to lock onto (a chicken-and-egg limitation: the method needs a
decent match to measure reliably, but measuring is how you'd get there).
Rather than trust an unreliable analytic correction from this (the exact
mistake that diverged badly in round 3), fell back to the same safe
empirical `w_ext` scan methodology that worked before:

| w_ext | fc (GHz) | bw (MHz) | s11w (dB) | il (dB) |
|---|---|---|---|---|
| 12.0 | 2.940 | 85.1 | -1.60 | -6.38 |
| **14.0** | **2.860** | **170.3** | **-4.17** | -3.97 |
| 16.0 | 2.880 | 122.1 | -3.31 | -3.04 |
| 18.1 (unchanged baseline) | 2.860 | 175.5 | -2.92 | -3.20 |
| 20.0 | 2.840 | 171.5 | -2.05 | -4.11 |
| 22.0 | 2.980 | 165.0 | -1.73 | -4.50 |
| 24.0 | 2.940 | 73.4 | -1.34 | -19.63 |

`w_ext=14.0` clearly best.

### Final confirmed result (FAB-TOLERANCE)

```
a=59.0  w_iris=12.8  x_iris=29.6  y_wall=8.9  w_ext=14.0  w_inter_mm=13.7
fc=2.907GHz   bw=199MHz   s11w=-5.01dB   il=-3.18dB
standard v17 score = 16.531
```

![final fixed cascade vs ideal N=4](../../output/imgs/dualmode_cascade_final_fixed_vs_ideal.png)

**Numerically this scores worse than v3 (16.53 vs 13.83).** But the plot
tells a different, better story than the score does: this response shows
genuine equal-ripple structure -- two visible humps in S21 and **three
distinct S11 nulls** (best -21dB, right in the middle of the passband),
tracking the ideal N=4 curve's skirts and null positions far more closely
than v3's accidental single-spike-plus-satellite ever did. This is a real,
qualitative shape improvement the v17 score's specific weighting (tuned
against other geometries' typical failure modes, not this one) does not
credit. **Score alone should not be trusted as the sole judge of "is this
a real filter" for this fragile topology** -- visual/eigenmode inspection
remains necessary, exactly the lesson of this whole multi-round
investigation.

### Overall verdict on dualmode_cascade (closing this investigation)

Across all 5 rounds tonight: fixed a real scoring bug (N2 vs N4), fixed a
real geometry-scaling bug (v2->v3), diagnosed and explained the
"degenerate two-center-frequency" shape via ground-truth eigenmode
analysis (a real structural defect, not a scoring artifact), found and
fixed it via a principled joint eigenmode search, then closed the loop
with fc/`w_ext` corrections. The final design here is genuinely the best
*shape* achieved, though not the best *score* -- both facts should be
weighed, and neither result is yet fabrication-ready (match is still only
-5 to -21dB in spots, short of a clean -16dB+ across the whole band).

**The standalone dual-mode cavity (score 9.31, single-cavity, already
validated with real SMA and match consistently at or better than -16dB)
remains the best, most reliable result of the entire session, by a clear
margin over every dualmode_cascade variant tried.** `dualmode_cascade`
is a genuinely more capable topology (N=4 vs N=2, steeper theoretical
selectivity) and tonight's work materially improved understanding of how
to tune it correctly -- but it is not yet a finished, competitive design.

## dualmode_cascade: architectural experiment -- floating inter-cavity coupling, disproven (2026-08-27)

User's architectural insight, well-reasoned from first principles: the
standalone dual-mode cavity's external ports use a taper; cascading two
such cavities replaces that taper connection with a bare coupling iris at
the shared wall. Proposed testing whether the coupling MECHANISM itself
(not just its width) was the limiting factor, since 2D tuning of
`(w_iris, w_inter_mm)` on the existing full-wall-slot coupling never
closed the persistent outer-gap asymmetry (~90 vs ~38MHz, ideal wants
~46/48).

Implemented `dualmode_cascade_floatinter` (new via-layout, committed):
the inter-cavity coupling row becomes a floating segment (its own
`y_wall_inter_mm` standoff) instead of spanning the full wall, mirroring
how the internal mode-splitting irises are already built.
`y_wall_inter_mm=0` regression-verified identical to the original.

Ran a full 3D eigenmode-ground-truth search `(w_iris, w_inter_mm,
y_wall_inter_mm)`, warm-started with all 19 already-known 2D points (free)
plus 11 new evals spanning `y_wall_inter_mm` from 0 to 15mm (its full
range). **Result: every meaningfully-floating point scored worse (RMSE
29-121) than the un-floated mechanism.** The search's own best point
(RMSE=23.9, a genuine ~9% improvement over the prior 26.1) landed at
`y_wall_inter_mm=0` -- i.e. still the original mechanism, just a better
point within it that the earlier, coarser 2D search hadn't found.

**The floating-coupling hypothesis is disproven.** Shortening a
symmetric slot's extent doesn't change which internal mode combination
it preferentially couples to -- it's still symmetric in shape, just
smaller. Confirmed the new "best" point via driven sweep anyway: fc=2.980
(110MHz off), **bw=44.6MHz** (way under-coupled once real ports load it,
despite looking better in the unloaded eigenmode metric), s11w=-2.04dB,
il=-5.83dB -- clearly worse in practice than every other confirmed
cascade design this session. The eigenmode gap-RMSE metric, while
essential for diagnosing the pole-splitting problem, does not reliably
predict driven performance at tight coupling values where external
loading dominates.

### Final verdict on dualmode_cascade

Across the full investigation (rounds 1-6): fixed a real scoring bug,
fixed a real geometry-scaling bug, diagnosed the "two center frequencies"
shape defect via ground-truth eigenmode analysis, fixed the internal pole
structure via a principled joint search, closed the loop with empirical
fc/`w_ext` corrections (best confirmed shape: score 16.53, genuine
equal-ripple structure with 3 S11 nulls), and finally tested and
disproved the most promising remaining architectural idea (floating
inter-cavity coupling). No configuration found this session reaches a
clean, centered, well-matched (-16dB+ across the band) order-4 response.

**Recommendation: stop further tuning of this specific coupling
mechanism (bare/floating slot between two dual-mode cavities) -- it has
been explored thoroughly and the remaining gap is not closing with
further parameter search.** If an order-4 filter remains a goal, the
next real step is a different physical coupling mechanism entirely (e.g.
an intentionally asymmetric/off-center coupling element, or reconsidering
a conventional inline chain of 4 single-mode cavities -- well-established
coupling behavior, unlike this dual-mode-to-dual-mode bridge) -- a
substantial new undertaking, not a quick fix. **The standalone dual-mode
cavity (score 9.31, real SMA, consistently -16dB+) remains this
project's best, most reliable, fabrication-ready result.**

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

## dualmode_cascade: stagger-tuning breaks the mirror symmetry -- the shape problem finally solved, match hits a hard ceiling (2026-08-28)

Round 6's recommendation was to try "an intentionally asymmetric/off-center
coupling element" next, since the bare-vs-floating inter-cavity slot
experiment proved the coupling *mechanism* wasn't the bottleneck -- the two
cavities' exact mirror (x-swap) symmetry was, forcing the 4-pole spectrum
into an even/odd pair split no amount of coupling-width tuning could escape.
This session picks that up directly: **stagger the two cavities' own
internal irises against each other** (`x_iris2_mm`/`w_iris2_mm`, both
already-existing but never-independently-searched parameters) instead of
tuning coupling width or mechanism.

### Breakthrough: x-stagger search

A 5D eigenmode-ground-truth GP search (`w_iris, x_iris, w_iris2_mm,
x_iris2_mm, w_inter_mm`, `a=59.0` fixed) found `rmse=16.1` -- by far the
best of the whole multi-round investigation to that point (previous best
23.9), with the eigenmode center landing almost exactly on the ideal
2.8708GHz. A follow-up 7D search adding `y_iris_off_mm`/`y_iris2_off_mm`
(each cavity's iris allowed to shift off its own y-centerline, not just
stagger in x) converged both offsets back to 0.0 -- y-offsetting doesn't
help beyond x-stagger alone.

**Driven confirm of the raw winner**: `bw=142.8MHz`, matching the
143.5MHz target almost exactly (the best bandwidth result of the entire
session) -- but `fc=2.980GHz` (110MHz high, `w_ext` untuned) and poor match
(`s11w=-2.71dB`).

### Bandwidth-collapse diagnostic: the naive `a`-rescale trick breaks on this design

The standard fc-recentering fix used successfully in every earlier round
(`a_new = a_old * fc_measured/fc_target`, proportionally rescaling every
cavity-scale dimension) was applied here too (`a: 59.0->61.261`). It fixed
`fc` (2.860GHz, only 10MHz off) but **collapsed bandwidth to 43.7MHz** --
an unexplained regression. A 7-point eigenmode diagnostic sweep (scale
factor 1.0 through the full 1.038 rescale, plus two isolating variants:
scale only cavity size / scale `w_inter_mm` too) showed the sharp
discontinuity directly: `rmse` jumps from 16.1 at exactly `a=59.0` to
29-32 for EVERY other scale factor tried (1.01 through 1.038), and both
isolating variants land in the same bad regime -- a genuine mode-relabeling
discontinuity, not smooth drift. **The x-stagger winner is a narrow,
fragile local optimum at exactly `a=59.0`; proportional rescaling can't
safely move it.**

### Objective correction: symmetry was under-penalized

User's review of the diagnosis correctly flagged the result as still
looking "degenerate... like an order 2 and another one off centered" --
checking the raw gaps confirmed it: the "best" `rmse=16.1` point has gaps
`[38.3, 75.9, 74.5]` against the ideal's symmetric `[46.1, 81.1, 48.2]` --
gap1 and gap3 differ by 36MHz, nowhere near the small-large-small shape a
symmetric Chebyshev N=4 response requires. Plain gap-RMSE doesn't
penalize this asymmetry enough. Re-scored all 54 eigenmode points
collected so far with a corrected objective (`rmse + |gap1-gap3| +
|center-2.8708|*1000`): **none scored well** (best re-ranked score 53.6) --
the objective itself, not just the search, needed fixing.

### New geometry DOF: via-defects (user idea)

User proposed removing individual vias from inside the cavity (never the
perimeter walls) as an additional, genuinely new coupling mechanism.
Added `iris_defect_frac`/`iris2_defect_frac` to `geometries.dualmode_cascade()`
(commit `1ea9d2a`): drops ONE symmetric via pair from a cavity's own
internal mode-splitting fence at a chosen fractional position along it --
localizes a small extra coupling defect at a specific point, something no
continuous width/position parameter can represent. Defaults to `None` (no
defect), regression-verified byte-identical to prior behavior; restricted
by construction to the internal fence, never the side/end/inter-cavity
walls that keep this a valid SIW structure.

### v2/v3: sensitivity-informed re-search with the corrected objective

**v2** (7D: `a, y_wall` now free for the first time alongside the 5
coupling dims, corrected symmetry-aware objective, warm-started from all
54 prior points): best found `score=41.0` -- `gaps=[31.4, 110.3, 49.5]`,
excellent centering (`2.8748GHz`, 4MHz off) but symmetry still short
(`|gap1-gap3|=18.1`, above the 15MHz bar).

A dimension-sensitivity re-analysis (RandomForest + Spearman on all 80
points) confirmed `a`/`y_wall` had been essentially unexplored before v2
(5 distinct values crammed into a 2mm range) -- not unimportant, just
never varied -- and identified `w_inter_mm` as the dominant, strictly
monotonic driver of bad shape (bigger `w_inter_mm` blows the middle gap
past the ideal 81.1MHz).

**v3** (9D: sensitivity-informed narrower bounds on `w_inter_mm`/`x_iris`/
`x_iris2_mm`, full range kept on `w_iris` since two distinct basins existed
there, plus the new `iris_defect_frac`/`iris2_defect_frac` dims): found
**`score=19.6`, `rmse~3.9`** (best of the entire session by a wide
margin) -- `gaps=[48.5, 82.8, 54.2]` against ideal `[46.1, 81.1, 48.2]`,
`|gap1-gap3|=5.7`, center only 10.1MHz off target. **Uses
`iris_defect_frac=0.93`** (a real via removed near the far end of cavity
1's fence) -- directly validates the via-defect idea. All three
success criteria (rmse<20, symmetry<15, center<15MHz) met simultaneously
for the first time in the whole investigation.

**Lesson learned the hard way**: a second v3 candidate (`rmse=8.6`, even
better than the eventual winner, using NO defect at all) drove BADLY
(`bw` collapsed to 16.3MHz) at the one `w_ext` value tested -- this
topology's `w_ext`-sensitivity is severe enough that no eigenmode
candidate can be judged from a single driven point; every promising
candidate needs its own `w_ext` mini-scan before comparison.

### `w_ext` scans: centering + bandwidth achieved, match will not move

Full 5-point `w_ext` scans (10/12/14/16/18mm) on both the `rmse=19.6`
winner ("eval18") and the `rmse=3.9` point ("eval45"):

| design | best w_ext | fc (GHz) | bw (MHz) | s11w (dB) | il (dB) |
|---|---|---|---|---|---|
| eval18 | 16 | 2.880 (10MHz off) | 126.6 | -1.88 | -10.00 |
| eval45 | 14 | 2.900 (30MHz off) | 126.7 | -2.00 | -8.31 |

Bandwidth is non-monotonic and occasionally collapses at specific `w_ext`
values (12mm collapsed both designs to 15-18MHz) -- consistent with the
mode-crossing fragility seen throughout this session -- but **match
(`s11w`) never exceeds about -2.0dB across either design's entire scan**,
regardless of which internal coupling realization produced it. This is
the best confirmed driven result for `dualmode_cascade` this whole session
on 3 of 4 axes (centering, bandwidth, and -- critically -- genuine 4-pole
shape rather than the "order 2 + order 2" degenerate look flagged earlier).

### Stagger-ramp test: is the match ceiling structural or avoidable?

Critical cross-check against the session's own history:
`docs/geometry_exploration/dualmode_enhancements_2026-08-26.md` documents
that the ORIGINAL naive symmetric cascade (`a=57.2, w_iris=15.3,
x_iris=28.7, y_wall=8.6, w_ext=16.3, w_inter_mm=16.3`, both cavities
identical) had `s11w=-10.28dB` -- excellent match, with a degenerate
(driven-overcoupled, single-wide-hump) pole spectrum. Round 3 (an earlier
session) already found the same ~-2dB match ceiling via coupling-matrix
curve-fitting and called it "a genuine ceiling, not a tuning miss," but
never tested whether a SMALL stagger (vs. the large, multi-parameter
9D-search excursion this session used) would preserve more of the naive
design's good match.

Ran an 8-point eigenmode-only ramp, staggering ONLY `x_iris2_mm` away from
`x_iris_mm` in small steps (0 to 8mm) from the exact naive baseline,
everything else held fixed at the naive design's own values (including
`w_inter_mm=16.3`, already known to be too loose vs. the ideal
coupling-matrix ratio). **Result: `rmse` never beat the unstaggered
baseline's 73.8 at ANY tested delta** -- it worsened monotonically through
2mm of stagger (73.8 -> 83.6 -> 93.4 -> 106.7 -> 123.3), then went chaotic
(125.3, then two points losing a mode entirely past 3mm). Single-parameter
stagger from the naive `w_inter_mm=16.3` point is not a productive
direction on its own -- confirms that eval18/eval45's success required
the coordinated multi-parameter shift (lower `w_inter_mm`, different
`w_iris`, larger `a`, plus stagger and/or a defect) that the 9D search
found, not a small nudge from the well-matched starting point.

### Final verdict

**The pole-shape problem that motivated this whole investigation ("looks
like an order 2 filter with another order 2 with an offset") is solved**:
eval18 achieves genuinely well-separated, symmetric, centered poles
(`rmse=19.6`, `|gap1-gap3|=5.7`) and translates to a real driven response
with matching centering and bandwidth -- the best `dualmode_cascade` shape
result of the entire multi-session investigation, by a wide margin.

**Match quality has a hard ceiling around -2dB that no method tried this
session (or the prior session's coupling-matrix correction) can move**,
and the stagger-ramp test shows it is not simply "not enough tuning" --
gentle perturbation from the well-matched naive point makes shape worse,
not better, and every design with genuinely good shape (eval18, eval45,
v3, the coupling-corrected design) lands at essentially the same -2 to
-3dB match regardless of exactly how the needed asymmetry was introduced.
This looks like a real structural trade-off in this specific coupling
mechanism (dual-mode cavity cascaded via a bare/staggered iris), between
achieving proper N=4 pole separation and preserving the taper/port match
that a symmetric, single-hump design enjoys for free.

**Recommendation: `dualmode_cascade` is now a fully characterized,
genuinely-N=4-shaped alternative, but the standalone dual-mode cavity
(score 9.31, real SMA, consistently -16dB+ match) remains this project's
best, most reliable, fabrication-ready result.** If N=4 selectivity is
specifically wanted despite the match cost, eval18's parameters
(`a=61.18, y_wall=10.42, w_iris=9.89, x_iris=29.74, w_iris2_mm=12.92,
x_iris2_mm=30.27, w_inter_mm=10.03, iris_defect_frac=0.12, w_ext=16.0`)
are the best starting point found; fixing match further would need a
genuinely new external-coupling mechanism (a different taper/feed
geometry specifically re-derived for this asymmetric internal structure's
impedance, not just re-scanning `w_ext` on the existing taper) -- a
substantial new undertaking, not attempted here.

### Official FINE + FAB-TOLERANCE confirm (dense mesh, standard `evaluate()`)

```
FINE:          fc=2.887GHz  bw=138MHz  s11w=-1.51dB  il=-9.16dB  score=24.415
FAB-TOLERANCE: fc=2.887GHz  bw=39MHz   s11w=-1.64dB  il=-6.76dB  score=24.645
(0.1mm-rounded params: a=61.2, y_wall=10.4, w_iris=9.9, x_iris=29.7,
 w_iris2_mm=12.9, x_iris2_mm=30.3, w_inter_mm=10.0, iris_defect_frac=0.1, w_ext=16.0)
```

Two honest findings the coarse `w_ext`-scan numbers above didn't fully
capture:

1. **The official v17 score (24.4-24.6) is WORSE than every prior
   `dualmode_cascade` result this session** (old naive 13.964/15.563, v3
   13.827, coupling-corrected 17.878, fc/`w_ext`-fixed 16.531) -- despite
   eval18 having the best pole-shape, tightest centering, and closest
   bandwidth match of the whole investigation. The score formula weights
   match (`s11w`) heavily, and eval18's match never moved off the ~-1.5 to
   -2dB ceiling documented above. This is the same "the aggregate score
   doesn't credit real shape" pattern already seen for v3 vs the
   coupling-corrected design earlier in this file -- confirmed again,
   more starkly, here.
2. **Bandwidth collapses from 138MHz to 39MHz under 0.1mm fab-tolerance
   rounding alone** -- a real PCB fab holding only standard tolerance
   would land far short of the simulated full-precision bandwidth. This
   is a new, more concrete problem than "match is imperfect": the design
   is fragile enough that realistic manufacturing rounding, by itself,
   breaks the bandwidth by 3.5x. Combined with the mode-crossing
   sensitivity documented throughout this session (small parameter
   changes repeatedly causing large, non-smooth jumps), this strongly
   suggests `dualmode_cascade`'s current best point sits very close to
   an unstable boundary in parameter space, not a broad, robust optimum.

**Updated final recommendation**: `dualmode_cascade`'s pole-degeneracy
problem is genuinely solved at the eigenmode/physics level, a real and
useful result for understanding this topology -- but the resulting best
design is neither better-scoring nor more fabrication-robust than earlier
attempts. **The standalone dual-mode cavity (score 9.31) remains the
clear, correct choice for actual fabrication.** `dualmode_cascade` should
be treated as a characterized research result (how to achieve genuine
N=4 pole separation in this coupling mechanism), not a competing
deliverable, until both its match ceiling and its fab-tolerance fragility
are separately addressed -- likely via a redesigned external-coupling/
taper mechanism together with a search objective that penalizes parameter
sensitivity, not just landed performance at exact (unrounded) values.
