# Tuning plan — narrow-bandwidth filters at N=2 / N=3 / N=4

> ## ⚠ SUPERSEDED by `docs/ROADMAP_2026-08-30.md`
>
> **Section 2 (the CPWG/SMA launch geometry) is still valid and unchanged** —
> the solved 50-ohm numbers there remain the reference.
>
> **The tuning strategy is not.** This plan assumes Bayesian search over the
> assembled filter. On 2026-08-30 five bugs were found that each independently
> invalidated every cascade search behind it (quantized w_iris, missing N>=4 iris
> DOF, stale via defaults, unimplemented calibrate(), 21x-wrong eigenmode mode
> selection), and the method was replaced by calibrate-and-invert with the GP as
> a local polish only. Any cascade NUMBER quoted below is void.


Date: 2026-08-29. **This is the working document for the tuning phase.**
Everything needed to resume after a session compaction is here.

---

## 1. Confirmed configuration (do not re-derive)

| Item | Value | Where |
|---|---|---|
| Centre frequency | f0 = 2.87 GHz | `FilterSpec` |
| Target FBW / ripple | 5 % (143.5 MHz) / 0.1 dB Chebyshev | `FilterSpec` |
| Substrate | **RO4350B_0.76mm** (εr 3.66, tanδ 0.0037) | `config.DEFAULT_SUBSTRATE` |
| SIW fence vias | **d = 1.5 mm, p = 3.0 mm** | `config.VIA_PRESETS["siw_fence"]` |
| Ground stitch vias | d = 0.6 mm, p = 1.2 mm | `config.VIA_PRESETS["gnd_stitch"]` |
| Fab profile | JLCPCB 2-layer | `config.FAB_RULES` |

`CLAUDE.md` §1 and §10 carry the same values. Older AD250C / d=0.8 mm
references anywhere in the repo are **stale** — see `CLAUDE.md` §1.

## 2. SMA launch — DONE, verified, do not redo

Commits `9df609b` → `52983f1`. Final geometry, all numbers solved not guessed:

- **CPWG section** (inside the SMA footprint): signal **1.200 mm**, coplanar
  gap **0.2512 mm**, ground inner edge **0.8512 mm** → **50.00 Ω**
  (`cpwg_gap_50ohm`, Wadell/Simons conformal mapping with Hilberg's K/K′
  approximation; validated against K/K′=1 at k=1/√2 and r(k)·r(k′)=1).
  The gap must be this tight: at 0.5 mm the line is 55.6 Ω, at 1 mm 59.8 Ω.
- **Ground pads**: plain rectangles, **0.851 → 3.6 mm**, **5 mm deep**
  (footprint only — they must NOT extend over the taper, or the widening
  trace closes the gap to 0.019 mm and effectively shorts).
- **Stitch vias**: 4 per side at ±2.62 mm, fully inside the copper.
- **Taper**: signal **1.200 → 1.664 mm**, *past* the ground, then the
  existing Deslandes flare into the SIW wall.
- **Microstrip**: 1.6636 mm = 50 Ω (`microstrip_width_50ohm`).
- **DRC**: all pass with ≈2× margin (trace 1.200 mm and gap 0.2512 mm vs
  0.127 mm minimum; both via types pass drill/hole-to-hole/aspect/standard).

Enable it via `build_mesh(..., cpwg_gap_mm=0.2512, cpwg_y_gnd_mm=0.8512,
cpwg_y_out_mm=3.6, cpwg_w_feed_mm=1.2, n_gnd_stitch=6)`. With
`cpwg_gap_mm=None` the model is byte-identical to before (129604 tets /
42622 nodes) — regression-verified at every step.

## 3. The problem being solved

The landed N=2 design works but is **too wide**: measured **bw = 318 MHz**
against the **143.5 MHz** target — 2.2× over. Bandwidth is set by the
couplings, so both must be **weakened**.

Synthesis targets (from `synthesize()`, verified):

| Order | Couplings | Qe |
|---|---|---|
| N=2 | k12 ≈ 0.069 | 16.9 |
| N=3 | k12 = k23 ≈ 0.046 | 20.6 |
| N=4 | k12 = k34 ≈ 0.0415, k23 ≈ 0.0329 | 22.2 |

## 4. What was already changed for this (committed)

- **`cf6827f` — v18 objective.** Added three one-sided hinge terms to
  `optimize.score()` so the search is judged on the actual acceptance spec,
  not just curve-fit RMSE:
  - `S11_SPEC_DB = -16.0` — worst-case in-band return loss
  - `IL_ALLOWANCE_DB = 1.0` over `dielectric_il_db()` — "dielectric loss and
    a little bit more" (the floor alone is optimistic: it ignores conductor,
    via-leakage and radiation loss, measured 2.65–3.84× higher in practice)
  - `W_ASYM = 8.0` on −3 dB skirt imbalance — enforces a **symmetric**
    response, since a lopsided passband can otherwise hit the right centre
    and width by luck
  Sanity-checked on the landed design: it already meets S11 (−17.70 dB) and
  is near-symmetric (4.1 % arm imbalance), so score moves 9.310 → 9.639 — a
  modest shift, not a distortion of the existing ranking.
- **`9d48f18` — search boxes widened downward.** The old boxes were centred
  on the *wide*-bandwidth optimum (landed `w_iris` = 15.26 sat just under
  its own 15.9 ceiling), so a narrow-bandwidth search could not physically
  reach the region it needed.
  - dualmode: `w_iris` floor 12.5 → **6.0**, `w_ext` floor 14.1 → **8.0**
  - cascade:  `w_iris` floor 8.0 → **4.0**, `w_ext` floor 12.0 → **7.0**
  Upper bounds and initial points unchanged, so landed designs stay inside
  every box and warm-starts are unaffected.

## 5. Acceptance criteria

1. **Symmetric** response (balanced −3 dB skirts).
2. **S11 ≈ −16 dB** worst-case in band.
3. **IL** ≈ dielectric floor + ~1 dB.
4. Bandwidth toward 143.5 MHz (5 % FBW).

## 6. Runs to execute

`v18_tune_all.py` (in the job tmp dir) runs these sequentially:

| Name | Topology | N | Budget | Notes |
|---|---|---|---|---|
| `dualmode_N2` | `DualModeTopology` | 2 | 40 | GPU preset exists |
| `cascade_N3` | `CascadeTopology` | 3 | 36 | CPU np=4 |
| `cascade_N4` | `CascadeTopology` | 4 | 30 | ~470k tets, CPU, expensive |

Outputs land in `output/data/v18_<name>_log.csv` and
`output/data/v18_<name>_best.json`.

**Known cost/risk notes:**
- N=4 cascade meshes at ~470–479k tets *regardless* of mesh coarseness
  (via-count/board-length dominated). A full-band 36-point sweep OOM-killed
  once at 8/36 points — Palace accumulates memory across frequency points
  within one run. If it fails, narrow the fine-confirm window rather than
  retrying blindly.
- Eval tags are hashed when long (`097b197`); do not "fix" that — it exists
  because 16-D param dicts exceeded the 255-byte filename limit and silently
  failed every eval.
- Coarse-mesh scores systematically differ from fine. **Always fine-confirm
  a winner before believing it** — a v8 result that looked like a win at
  coarse mesh (25.047) was actually *worse* than baseline at fine mesh
  (25.978).

## 7. Board sizes (for the comparison)

| Design | Board |
|---|---|
| N=2 dual-mode (landed) | ~119 mm |
| N=3 single-mode cascade | ~150–165 mm (est.) |
| N=4 single-mode cascade | ~180–206 mm |
| N=4 dual-mode cascade | ~122 mm — **but see §8** |

## 8. Do NOT restart these (already falsified with real data)

The compact N=4 **dual-mode cascade** was investigated across five
structurally different mechanisms plus a proper joint GP search; all hit the
same ceiling (2 of 4 poles, score ~25 vs the N=2's 9.31). Falsified:
y-offset apertures, near-corner placement, top-copper coupling slots,
discrete posts, and single-cavity quad-mode. Full raw numbers and reasoning:
`docs/geometry_exploration/dualmode_cascade_v6_handoff_2026-08-28.md` §9–16.

One genuine methodological gap if it is ever revisited: no attempt directly
measured per-mode external Q — everything was inferred from S11 curve shape.

## 9. Next action

Run `v18_tune_all.py`, then for each winner: fine-mesh confirm → compare
against the four acceptance criteria in §5 → plot all designs against the
ideal Chebyshev target for the side-by-side comparison.
