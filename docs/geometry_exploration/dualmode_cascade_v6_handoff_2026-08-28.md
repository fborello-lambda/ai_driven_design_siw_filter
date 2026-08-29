# dualmode_cascade v6 — handoff: root-cause analysis and the simpler model to follow

Date: 2026-08-28. Status: **analysis + plan, not yet implemented.** This document is the
handoff after the v1–v5 searches; it explains why five rounds of black-box optimization
never produced an acceptable N=4 response, what the actual physical defect of the current
geometry is, and lays out a *directed* design procedure (v6) that replaces the black-box
search with the coupling-matrix method the project brief (CLAUDE.md §6) already prescribes
for the inline filter — applied here to the cascade.

Prior history (v1–v5, all raw numbers): `dualmode_enhancements_2026-08-26.md`.

---

## 1. Problem statement

Target: order-4 bandpass, f0 = 2.87 GHz, FBW = 5% (143.5 MHz), 0.1 dB Chebyshev, on
AD250C 1.524 mm. Topology under test: `dualmode_cascade` — two dual-mode square SIW
cavities in series (2 poles each), one inter-cavity via-row aperture, microstrip-taper
ports at both ends.

Best result after five search campaigns (v5 eval4, coarse mesh):
fc ≈ 2.813 GHz (−57 MHz off), **bw ≈ 56 MHz (39% of target)**, best S11 −14.5 dB at one
frequency only, IL at peak −5.7 dB. The fine 4 MHz-step rescan of the manual asymmetric-
port test showed the signature clearly: **exactly ONE S11 null** (−10.4 dB @ 2.768 GHz)
where an N=4 filter must show four, and a sagging, asymmetric S21.

## 2. Root cause — a missing coupling channel, not a mistuned one

### 2.1 The geometry is exactly mirror-symmetric in y — verified

Every via row in `dualmode_cascade()` is generated as symmetric pairs (+o, −o) about the
SIW axis y = 0, including the "defect" mechanism (it removes a symmetric *pair*).
Verified numerically on the v5 best design (all 11 params, both defects active): 150 vias,
**zero** y-asymmetric positions.

### 2.2 Consequence: half the modes are starved of coupling

All three coupling apertures — port 1 (`w_ext`), inter-cavity slot (`w_inter`), port 2
(`w_ext2`) — are gaps **centered on y = 0**. A centered aperture samples the field around
y ≈ 0 and therefore couples strongly only to modes **even in y**; a mode odd in y has a
null there and is nearly invisible to it. Each dual-mode cavity contributes one even-ish
and one odd-ish mode (that is what the internal splitting iris creates), so of the four
modes of the cascade, roughly two have no viable route from port to port. Observed
consequences, all reproduced across v1–v5:

- one real S11 null instead of four (only the well-coupled mode chain rings);
- bandwidth stuck at ~40–110 MHz vs 143.5 target (the poles cannot interleave);
- IL −5…−8 dB (power forced through weakly coupled modes is dissipated, not delivered);
- an S11 match ceiling ~−1.5…−2 dB for every symmetric variant, because by x-mirror
  symmetry the naive design's degenerate pole pairs sit on top of each other, and every
  attempt to split them (stagger, defects, `w_ext2`) makes the modes *localize* in one
  cavity or the other, which centered ports then couple to unequally.

`w_ext2_mm` (v5) helped — it is an x-asymmetry that mixes mode character and bought the
first ≥−10 dB null this topology has shown — but it cannot repair a **y**-symmetry
selection rule. That is why v5 still plateaued.

### 2.3 Secondary mismatch: the realized topology is not inline Chebyshev

Each port feeds a dual-mode cavity, so it couples to *both* of that cavity's modes at
once: the realized coupling topology is a cascaded-doublet / transversal one, which
generically produces transmission zeros and asymmetric skirts. Fitting its S21 against a
pure inline Chebyshev target charges the optimizer for physics the geometry cannot
remove. The scoring should target the *synthesized coupling matrix*, not the literal
ideal curve (see §4).

## 3. Why the optimizer could not dig this out

- 11 dimensions, 36-eval budget; a GP surrogate needs ~10×D informative points.
- The viable region is tiny: v5's **narrow** box still screened out 30 of 31 evals. The
  graded fail score (1e6 + margins) gave the GP *some* slope in fail-land, but there is
  still a 1e6 → ~25 cliff at the screen boundary; the surrogate learns the fail plateau,
  not the pass basin.
- The objective is one scalar (curve RMSE + terms). "Mode 3 is 40 MHz low and starved of
  port-2 coupling" and "everything slightly detuned" collapse to the same number — the
  search direction that fixes the actual defect is invisible.
- Extreme fragility on top: eval14, at nearly identical parameters to passing eval4,
  screened out (mode crossings + coarse-grid aliasing; the 0.02 GHz screen grid straddled
  a real −10.4 dB null that a 4 MHz rescan later found).

Conclusion: more budget, wider boxes (v4) or narrower boxes (v5) do not fix this. The
information the optimizer needs must come from a *decomposed* measurement, and the
geometry needs the missing degree of freedom first.

## 4. v6 — the simpler model to follow

### 4.1 Geometry additions (small, targeted)

1. **`y_inter_off_mm`** — offset the inter-cavity aperture's center off y = 0. This is
   *the* missing knob: it directly sets the even/odd-mode coupling ratio between the two
   cavities (at offset 0 the odd channel is closed; increasing offset opens it).
2. **`y_ext_off_mm` / `y_ext2_off_mm`** — the same offset for each port aperture,
   controlling how strongly each port excites each of its cavity's two modes (and, with
   the taper following the aperture via `face_ty()`, the feed line shifts with it — the
   mesh builder already derives taper flare from actual via positions per face, so no
   driver change is expected; verify once).
3. Optional, second wave: independent cavity lengths `L1_mm`, `L2_mm` (today hardwired
   Li = 2a with the boundary at x = a) — direct control of each mode pair's center
   frequency instead of leaning entirely on the internal irises.

Regression rule as always: every new parameter defaults to the exact current behavior
(offset 0 / None), verified by identical via lists.

### 4.2 Replace the black-box search with the coupling-matrix procedure

Synthesis targets (from `synthesize(FilterSpec(N=4))`, verified this session):

- core-matrix couplings: **k12 = k34 = 0.0415, k23 = 0.0329, Qe = 22.2**
- closed-cavity (unloaded, ports sealed) eigenfrequency targets, f0·(1 + FBW·λi/2):
  **2.7823 / 2.8295 / 2.9105 / 2.9577 GHz**

**Stage A — eigenmode calibration (cheap, mostly 1-D sweeps).**
`cascade_eigenmode.py` already builds the sealed closed cavity from the same via
generator (`w_ext_mm = 0`; NOTE the trap: `w_ext2_mm` must be excluded/zeroed too or the
second port stays open). Sweep one knob at a time and extract eigenfrequencies:
- k_intra(w_iris) per cavity: split of that cavity's own pair,
  k = (f2² − f1²)/(f2² + f1²);
- k_inter(w_inter, y_inter_off): with intra-couplings held, the inter-cavity split;
- Qe(w_ext, y_ext_off): single loaded cavity, S11 group delay, Qe = ω0·τ(ω0)/4.
Fit low-order polynomials, cache to JSON keyed by (substrate, d_via, p_via) — exactly the
CLAUDE.md §6 pattern.

**Stage B — assemble the predicted design** from the fits (invert the polynomials at the
target k's/Qe), then run ONE driven confirm.

**Stage C — local polish only.** Nelder-Mead or CMA-ES with small steps around the
Stage-B point. Objective: per-mode errors, not curve RMSE — vector-fit the simulated
S-params (scikit-rf `VectorFitting`), extract the 4 pole frequencies/Qs, and penalize
each pole's deviation from the synthesis targets separately (plus band-edge and IL
terms as *reports*). This yields ~8 informative error components with no screen cliff.

**New/changed metrics summary:** (a) eigenfrequency-vector error = the primary cheap
screen; (b) per-pole vector-fit errors = the polish objective; (c) the corrected
contiguous-band `band_edges()` bandwidth stays as a reported figure of merit, not the
main gradient signal.

Budget estimate: 30–50 eigenmode solves + a handful of driven runs — less compute than
one v5 campaign, and every run answers a specific question.

### 4.3 De-risk fallback

If v6's Stage A shows the 4 eigenfrequencies *cannot* be steered to the target pattern
even with y-offsets, the honest exit is the known-good pair of alternatives:
- the classic inline 4-cavity `cascade` topology (single-mode, well understood), or
- the landed standalone dual-mode N=2 design (score 9.31) for fabrication.

## 5. Simulation speed and the 6 GB GPU OOM

Measured constraints: GTX 1660 SUPER 6 GB; `GPU_MAX_TETS = 176k` (empirical ceiling);
the cascade board (~122 mm + tapers) exceeds it on any decent mesh, so cascade driven
runs fall back to CPU (`-np 4`). Solve cost is dominated by meshing/assembly + number of
frequency points, not Krylov iterations (loosening tol 10⁴× bought only 1.23×).

Levers, in order of payoff:

1. **y-symmetry half-model (2× memory, ~2× time).** The current geometry AND its
   excitation are exactly y-mirror-symmetric (verified, §2.1). Cutting at y = 0 with a
   PMC (magnetic-wall) boundary halves the tets — the cascade then fits under
   GPU_MAX_TETS at search-mesh density. Caveat: a half-model only represents even-in-y
   fields, so it is valid for today's centered-aperture designs and for Stage-A sweeps
   that keep offsets at 0, but NOT once `y_*_off` breaks the symmetry. Use it for the
   symmetric calibrations; full model for offset designs.
2. **Eigenmode instead of driven for screening/calibration.** A sealed-cavity eigenmode
   solve (no air box, no ports, no frequency sweep) is far smaller and faster than a
   16–31-point driven sweep, fits the GPU, and directly measures the thing v6 optimizes
   (pole positions). This removes most driven solves from the loop.
3. **Palace adaptive fast frequency sweep (PROM).** The installed build
   (v0.17.0-293-g3c83b9db0) supports it — schema fields `Solver.Driven.AdaptiveTol`,
   `AdaptiveMaxSamples`, `AdaptiveConvergenceMemory` confirmed present. For the fine
   65-point confirms, set `AdaptiveTol` (e.g. 1e-3): Palace solves a handful of full
   points and interpolates the rest with certified error — typically 5–10× on wide
   sweeps. Slightly more memory per solve, so pair with the CPU fine mesh (where the
   time is spent anyway), not the GPU.
4. Already exhausted / not worth it: MFEM_MEMORY=cuda (in place; kills the pooled
   allocator's fixed ~4 GiB grab), `-np 1` on GPU (multi-rank per card OOMs, clamped in
   code), looser Krylov tolerance (≤1.23×), FP32 (needs an MFEM rebuild).

## 6. Pre-handoff verification runs (2026-08-28)

- **y-symmetry of the via layout**: v5 best design, all 11 params incl. both defects —
  150 vias, 0 asymmetric. Confirms §2.1 and the half-model validity claim.
- **Synthesis targets**: k12 = k34 = 0.0415, k23 = 0.0329, Qe = 22.2; closed-cavity
  eigenfrequency targets 2.7823 / 2.8295 / 2.9105 / 2.9577 GHz.
- **Adaptive-sweep support**: confirmed in the installed Palace's config schema.
- **Closed-cavity eigenmode of the v5 best design**: see §6.1.

### 6.1 Eigenmode ground truth of v5-best vs targets

(recorded from `v5best_eig.py`, sealed ports, CPU, mesh 2.5/0.5)

Measured eigenfrequencies (GHz), next higher modes at 3.65+ — a clean, isolated
4-pole set in band:

| pole | target | measured | error |
|------|--------|----------|-------|
| 1 | 2.7823 | 2.7886 | +6.3 MHz |
| 2 | 2.8295 | 2.8443 | +14.8 MHz |
| 3 | 2.9105 | 2.9000 | −10.5 MHz |
| 4 | 2.9577 | 2.9318 | −25.9 MHz |

**This is the decisive measurement.** The closed cavity has four real, well-separated
poles, centred almost perfectly (mean 2.866 vs 2.870 GHz) and each within 26 MHz of its
target — yet the *driven* response of this very design shows ONE S11 null, a 56 MHz
band and −5.7 dB IL. The poles exist and are roughly where they should be; the ports
cannot reach them. That isolates the failure to **external/port coupling per mode**
(§2.2's mechanism), not pole placement — exactly what the y-offset apertures (§4.1) and
per-mode Qe calibration (§4.2) address, and what no amount of further 11-D black-box
search over the existing knobs could fix.

Secondary observation: the measured gap pattern is 55.7 / 55.7 / 31.8 MHz vs the
target's 47.2 / 81.0 / 47.2 — the inter-cavity coupling (which sets the large middle
gap) is too weak relative to the intra-cavity splittings, and the top pair is pinched.
Stage A's k_inter sweep is the direct fix; total spread 143 vs 175 MHz says overall
coupling is only ~20% shy, i.e. well within tuning range.

## 6.2 v6 step 1 result: y-offset apertures implemented, but a point-check does NOT yet confirm the fix

`y_ext_off_mm` / `y_ext2_off_mm` / `y_inter_off_mm` were added to
`dualmode_cascade()` (commit `6580725`) via a new `_wall_with_gap()` helper
that opens the port/inter-cavity gap off-centre instead of at y=0, with
`off=0.0` regression-verified byte-identical to the prior via list (150/150
vias, exact match) and a smoke-tested mesh build (145,654 tets, both ports
found) confirming the taper/port machinery needs no changes (`face_ty()`'s
flare bound is anchored at the wall's true outer extent ±half regardless of
where the gap sits inside it, as predicted in §4.1).

A quick 4-point driven de-risking test (v5-best geometry, 2.70–2.95 GHz @
8 MHz step, screen mesh) gave:

| variant | best S11 | IL peak | real nulls (<−8dB) |
|---|---|---|---|
| baseline (all offsets 0) | −14.91 dB | −5.51 dB | 1 @ 2.828 GHz |
| yoff_all (port ±6/∓4mm, inter 3mm) | −15.97 dB | −5.67 dB | 1 @ 2.828 GHz |
| yoff_inter_only (3mm) | −14.99 dB | −5.80 dB | 1 @ 2.828 GHz |
| yoff_ports_only (±6/∓4mm) | −11.44 dB (worse) | −6.09 dB | 1 @ 2.812 GHz |

**This does NOT confirm the y-parity hypothesis as stated.** At these
offset magnitudes (10–20% of the cavity half-width, 30.5mm), the response
barely moved — the same single null, marginally better or worse — not the
second/third/fourth null a clean y-even/y-odd selection rule predicts.
`yoff_ports_only` alone made the match worse.

Two readings, not mutually exclusive:
1. **The offsets tested may simply be too small.** Three spot values is not
   a sweep; the true k_inter(y_inter_off) / Qe(y_ext_off) functions could
   need a larger offset, or a different sign/combination, to reach the
   under-coupled modes. This is exactly why §4.2's Stage A calls for a real
   swept calibration with a fitted curve, not point guesses.
2. **The y-even/y-odd framing may be incomplete.** A dual-mode SIW cavity's
   near-degenerate pair (typically TE102/TE201-like) are diagonal, mixed
   x-y field patterns, not clean reflection eigenstates of y → −y. A modest
   y-shift may not toggle their coupling as cleanly as a simple standing-
   wave-mode argument predicts; the real lever might need a combined x-y
   perturbation (e.g. a diagonal or corner-offset aperture) rather than a
   pure y-shift.

**Conclusion: do not treat the y-offset apertures as a proven fix yet.**
The geometry capability is real and regression-safe, but its effect on the
actual defect (per-mode external coupling) is still unmeasured beyond this
inconclusive spot check. The next required step is §4.2 Stage A done
properly — a swept, fitted Qe(y_ext_off) and k_inter(y_inter_off) via
eigenmode/group-delay, not another round of driven point-guesses — before
deciding whether this lever is sufficient or whether the fallback (§4.3)
is warranted.

## 6.3 Stage A on the reference cavity: the y-offset lever is FALSIFIED as a mode-unlocking switch

The inconclusive cascade spot-check (§6.2) left two readings open: offsets
too small, or the y-parity mechanism itself wrong. To settle it cleanly,
`y_ext_off_mm`/`y_ext2_off_mm` were also added to the STANDALONE reference
single dual-mode cavity (`palace_dualmode_driven._via_layout`/`build_mesh`,
commit `eaf5c35`) -- the same a/w_iris/x_iris/y_wall/w_ext that scores 9.31
in production, with its real Taoglas SMA connector and the real CPU fine
mesh (1.2/0.2/6.0), i.e. the exact conditions known to produce −17.7 to
−24dB. This isolates the offset's effect from mesh/connector confounds
(a first attempt using the coarse screen mesh + no SMA connector gave a
barely-resonant −2 to −4dB baseline even at offset 0 -- unusable signal,
not a real test; see the abandoned `v6_stageA_qe_sweep.py`/its Qe-extraction
bug for that dead end).

Result, full fidelity, 3 points:

| y_ext_off_mm | S11 best | resonance f | IL peak |
|---|---|---|---|
| 0 | −24.45 dB | 2.910 GHz | −1.42 dB |
| 8 | −16.52 dB | 2.940 GHz | −1.63 dB |
| 16 | −5.32 dB | 3.000 GHz (hit sweep edge) | −4.00 dB |

**Clean, monotonic degradation as the offset grows — no second resonance
appears.** This falsifies the y-parity "selection-rule switch" mechanism
proposed in §2.2/§4.1: offsetting the port gap does not open a new coupling
path to a previously-invisible mode. It simply de-tunes and de-couples the
SAME mode pair the centred aperture already reaches (weaker coupling +
frequency pulling), consistent with a purely local perturbation of the
aperture's own near-field overlap, not a parity-based gating effect.

**Conclusion: the y-offset apertures (`y_ext_off_mm`/`y_ext2_off_mm`/
`y_inter_off_mm`) are a legitimate, regression-safe, working NEW geometry
capability (they do measurably and controllably change coupling strength,
useful for fine Qe tuning within a mode a port already reaches) -- but they
are NOT the fix for dualmode_cascade's core defect (one real S11 null
instead of four).** §4.2's Stage A/B/C plan, as originally scoped around
this lever, does not resolve the problem; k_inter(y_inter_off) may still be
worth a quick companion check for completeness, but the weight of evidence
now says the missing-mode-coupling problem needs a DIFFERENT geometric
mechanism than a pure y-shift of an existing centred gap -- e.g. a genuinely
off-axis (diagonal/corner) aperture that couples to a different field
component entirely, not just a shifted version of the same one, or
accepting the standalone N=2 design (§4.3 fallback) as dualmode_cascade's
practical outcome.

## 6.4 v7: near-corner coupling, also FALSIFIED -- the aperture-position mechanism is exhausted

Literature search (web search this session) on dual-mode SIW/waveguide
filters found degenerate-mode coupling structures described as sitting NEAR
THE CAVITY CORNER, not at a moderate offset -- raising the hypothesis that
v6's Stage A (§6.3, offsets up to 16mm of a 28.6mm half-width, ~56%) simply
hadn't pushed far enough, and that the true corner might present a
qualitatively different (not just weaker) coupling regime.

Tested on the SAME trustworthy full-fidelity reference cavity (real SMA +
production CPU mesh) at three more offsets, up to 98% of the geometry's own
clamp ceiling (`_wall_with_gap`'s `max_off`, ~17.45mm for this design):

| y_ext_off_mm | % of max_off | real S11 minima (<-6dB) |
|---|---|---|
| 10.47 | 60% | 2: -8.6dB @2.820GHz, -13.6dB @2.960GHz |
| 14.83 | 85% | 1: -6.5dB @2.990GHz (barely above threshold) |
| 17.10 | 98% (true corner) | **0** -- S11 never drops below -4.06dB |

Combined with v6's own 0/8/16mm points, this is ONE continuous, fully
monotonic decay curve, all the way to the physical corner: the reference
cavity's two KNOWN poles (present and strong at offset 0: -24.2dB and
-24.5dB) just get steadily weaker and weaker as the aperture moves, until
by the true corner neither is left. No third pole, no reversal, no
qualitatively new coupling regime appears anywhere along the path.

**Conclusion: shifting a single wall-gap-style aperture along y -- at any
distance, including all the way to the true corner -- is not a coupling
mechanism that reaches new modes on this cavity. It is purely a coupling-
strength dial that runs from over-coupled through critical to essentially
disconnected.** Both v6 (moderate offset) and v7 (near-corner) are now
ruled out by real, full-fidelity simulation, not by argument. The
literature's "corner-positioned" couplers are very likely discrete
conductive PROBES/POSTS (a different structure entirely -- a point contact
breaking BOTH the E- and H-field symmetry at a single localized spot) or
cross-slot perturbations at the corner of a SOLID cavity wall, not a
shifted GAP in a via-fence wall (which only removes local confinement,
it doesn't introduce a new field interaction). Reproducing that literature
mechanism in this project's via-fence-only construction would need a
genuinely different element (e.g. a shorting/coupling via post inside the
cavity, distinct from the via-fence wall vias, or a cross-shaped slot
cut at the corner) -- a new structural primitive, not a position parameter
on the existing aperture.

**This closes the aperture-position line of investigation for
dualmode_cascade.** See §8 for the final recommendation.

## 8. Final status (v1-v7) and recommendation

After seven investigation rounds -- black-box GP search (v1-v5), the
y-offset-aperture hypothesis (v6), and near-corner coupling (v7) -- the
N=4 `dualmode_cascade` topology has not produced a working design. The
root cause (eigenmode ground truth, §6.1) is clear: the closed cavity's 4
poles exist and are well-placed (within 26MHz of synthesis targets), but
every aperture geometry tried so far (centered, offset, near-corner)
couples to only a subset of them.

**Recommendation: ship the standalone N=2 dual-mode design** (a=57.21,
w_iris=15.26, x_iris=28.68, y_wall=8.62, w_ext=16.31 -- `output/data/
opt_dualmode_best.json`, score 9.31, S11 -17.7dB, IL -1.42dB, real Taoglas
SMA, already fabrication-ready) as the practical filter deliverable.

If an N=4 filter is still wanted, the next real idea is a genuinely
different coupling TOPOLOGY, not another position/offset variant of the
current via-fence wall-gap: e.g. a discrete coupling via/post inside the
cavity (not part of the confinement fence), or a cross-slot corner
perturbation, or abandoning the two-dual-mode-cavity-in-series idea
entirely for four single-mode cavities (`cascade.py`, already implemented
and validated for N=3 -- extending to N=4 is a much smaller, better-
understood step than continuing to debug dualmode_cascade). Any of these
is a bigger, unproven redesign and should be scoped as such before
starting.

## 9. v8: top-copper electric coupling slot -- FIRST CONFIRMED SECOND POLE (2026-08-29)

Literature on cascaded dual-mode SIW/waveguide filters describes inter-cavity
coupling via TWO distinct mechanisms: a magnetic via-fence window (already in
this project) plus a separate electric coupling slot cut into the top copper
at a different position, to reach the mode the magnetic window cannot. This
project's mesh builder previously had no air region above the cavity at all
(the top copper was the literal exterior boundary there), so this required
a genuinely new construction: a local air pocket over a cutout in the top
ground, added to `palace_dualmode_driven.build_mesh()` as `slot_x_mm/
slot_y_mm/slot_w_mm/slot_l_mm/slot_h_mm` (+ `slot_pec_cap` for a closed/
reactive variant), commits `4a3ce86`/`6eddbce`. Both default off
(regression-verified byte-identical mesh stats).

**Pitfall found and fixed along the way**: the first placement test
accidentally centred the slot directly over an existing via in the internal
mode-splitting fence -- that via's own PEC wall blocks the column at every
z regardless of the top copper, giving BIT-IDENTICAL S11 between the open
and closed slot variants (verified to full float precision). Always check
for via overlap before placing a slot; `_via_layout`/`dualmode_cascade`'s
own via list is the ground truth to check against.

**Single-cavity result (ambiguous but real)**: on the reference dual-mode
cavity (score 9.31, both modes already well-coupled), a via-free slot
produced a real, frequency-selective (not uniform-loss) effect: S11
improved by ~4dB at one known pole (-24.45->-28.76dB) while weakening the
other slightly, with no new resonance and no frequency shift. Promising
(clearly not just added loss) but inconclusive, since this cavity's ports
already reach both its modes -- this test alone can't distinguish "opens a
new path" from "reactively retunes existing coupling."

**Decisive test: the actual dualmode_cascade.** Same slot placed at the
REAL inter-cavity boundary (x=a_mm=61.123), in a via-free gap of the SOLID
part of the inter-cavity fence (y=10.52, between wall vias at y=8.98/12.06 --
deliberately AWAY from the existing centred magnetic coupling window
[-5.9,+5.9], to test independent access to a mode the magnetic window
doesn't reach), on the v5 best design (a=61.123, w_iris=10.716,
x_iris=30.603, y_wall=10.91, w_ext=17.374, w_inter_mm=11.793,
w_iris2_mm=10.635, x_iris2_mm=30.315, iris_defect_frac=0.105,
iris2_defect_frac=0.711, w_ext2_mm=14.063). Same screen-grade mesh/tolerance
v1-v5 used for this design (so directly comparable to v5's own numbers):

| | s11_best | real S11 minima (<-6dB) |
|---|---|---|
| no slot (v5 baseline, reconfirmed) | -14.91dB | 1: (2.828GHz, -14.9dB) |
| **with slot** | -15.03dB | **2: (2.828GHz, -15.0dB), (2.900GHz, -6.1dB)** |

**A genuinely NEW resonance appears, not present in the baseline at all --
the first time any v6/v7/v8 intervention has produced more than one real
null on this topology.** The new null's frequency (2.900GHz) lines up
closely with the closed-cavity eigenmode ground truth's pole 3 (measured
2.9000GHz exactly, see sec 6.1's table) -- strong corroborating evidence
this is the previously-invisible third pole becoming reachable, not a mesh
artefact or an unrelated resonance.

**Status: confirmed real, not yet strong.** The new null is weak (-6.1dB,
barely past the 6dB threshold) and pole 4 (eigenmode-predicted 2.932GHz)
still shows nothing. This is evidence the mechanism WORKS, not yet a
finished design -- next steps: strengthen the slot (larger footprint,
position tuning, possibly a second slot for pole 4), fine-mesh confirm
this specific point, then a short local search seeded from here rather
than a fresh wide-box GP search (that pattern already failed in v4).

## 7. How to continue (checklist)

1. Add `y_inter_off_mm`, `y_ext_off_mm`, `y_ext2_off_mm` to
   `geometries.dualmode_cascade()` (defaults reproduce current layout; regression-verify
   via identical via lists). Check `face_ty()` handles an off-center port aperture.
2. Add the PMC half-model option to the mesh builders (symmetric designs only).
3. Extend `cascade_eigenmode.py` into the Stage-A calibration driver (1-D sweeps +
   polynomial fits + JSON cache). Remember to zero `w_ext2_mm` when sealing.
4. Wire Qe extraction (group delay) for the single loaded cavity.
5. Stage B assembly + one driven confirm (use `AdaptiveTol` for the wide sweep).
6. Stage C vector-fit polish (scikit-rf `VectorFitting`, per-pole objective).
7. Decision gate: if Stage A cannot reach the target eigenfrequency pattern, fall back
   per §4.3 and close the topology out honestly.
