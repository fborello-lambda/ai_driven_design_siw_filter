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
