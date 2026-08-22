# Handoff — moving to the GPU machine

Written at the end of a session on branch `sma_conn`. This is the pickup
document — read this first, then `docs/dualmode_cavity/README.md` and
`docs/sma_connector/README.md` for the full technical history.

## TL;DR

1. The **N=2 dual-mode cavity compaction is done and landed** — best design
   is the 1.5mm/3.0mm-via version, half the board length of the N=3 cascade,
   beats it on both S11 (-18.09dB vs -15.98dB) and S21. Full writeup:
   `docs/dualmode_cavity/README.md`.
2. **New task, not yet started:** swap in a real, sourceable connector — the
   Taoglas `EMPCB.SMAFSTJ.B.HT` edge-mount SMA jack — in place of the
   generic coax-launch abstraction used so far, and add top-layer ground via
   stitching at its footprint. Compatibility check + concrete plan below.
   **Read the "critical risk" section before running anything** — this
   connector's real pin size sits right on a previously-documented meshing
   instability.
3. This branch (`sma_conn`) is 2 commits ahead of `origin/main` and was never
   pushed. Squash-PR instructions at the bottom.

## Environment setup on the new machine

This repo's own `CLAUDE.md` only documents the **openEMS** install (it
predates the Palace-based work). Palace itself has no install doc in this
repo — you'll need to build it fresh from
[github.com/awslabs/palace](https://github.com/awslabs/palace) (or wherever
your fork/version lives) and confirm the resulting binary path.

```bash
uv sync                                                        # package + deps
export LD_LIBRARY_PATH=$HOME/opt/openEMS/lib:$LD_LIBRARY_PATH  # only for openEMS stages
```

Every Palace script in this repo hardcodes `PALACE = "/home/fd/opt/palace/bin/palace"`
(`palace_opt.py`, `palace_opt_sma.py`, `palace_opt_dualmode.py`, and the
scripts in `scripts/`) — **update this path** (or symlink `~/opt/palace` on
the new machine) before running anything.

**GPU note — don't assume it's automatic.** Palace supports GPU-accelerated
assembly/solve via a libCEED + MFEM CUDA (or HIP) backend, but only if it was
*built* with that support, and only if the run config actually asks for it.
Every Solver block in this codebase currently hardcodes `"Device": "CPU"`
(e.g. `palace_opt_dualmode.py` around the `cfg["Solver"]` dict). To get the
speedup:
1. Confirm the new Palace build was configured with CUDA support (check its
   build log / CMake cache for `PALACE_WITH_CUDA` or equivalent).
2. Change `"Device": "CPU"` → `"Device": "GPU"` in the config dicts you use.
3. **Verify on a cheap eigenmode run first** (`palace_dualmode.py`, seconds
   to run) that it actually engages the GPU (check Palace's own stdout for
   device info, and `nvidia-smi` during the run) before trusting a full
   driven+SMA search to be faster — if the build lacks GPU support the
   `"Device": "GPU"` key may be silently ignored or may hard-error,
   depending on Palace's version.
4. This machine's binding memory constraint (7.4GB RAM, repeatedly forced
   `mesh_max`/`h_air_factor` compromises documented in
   `palace_opt_dualmode.py`'s comments) should mostly go away on a
   workstation-class GPU machine — that alone likely matters more than the
   GPU itself, since every compromise made this session was RAM-bound, not
   CPU-bound. Worth re-relaxing `mesh_max`/`mesh_min`/`h_air_factor` back
   toward the original, more-accurate values once you confirm you have
   headroom (search each file for the comments explaining why they were
   tightened).

## Current results (dual-mode cavity)

Full writeup, figures, bug history, and scoring methodology:
**`docs/dualmode_cavity/README.md`**. One-line summary: N=2 dual-mode
cavity at 1.5mm/3.0mm via pitch (`a=57.21, w_iris=15.26, x_iris=28.68,
y_wall=8.62, w_ext=16.31` mm) is the best landed filter — fc=2.92GHz,
S11=-18.09dB, S21=-1.41dB, BW=300MHz, at half the length of the N=3 cascade.
1.0mm/2.0mm vias were tried three separate times under three different
scoring methods and never matched this — treat that as settled.

## New task: Taoglas EMPCB.SMAFSTJ.B.HT connector

### Can it be used? Yes, with one real risk to check first.

Datasheet: `EMPCB.SMAFSTJ.B.HT`, SMA(F) edge-mount PCB jack.

| Spec | Value | Fits this project? |
|---|---|---|
| Impedance | 50Ω | Yes |
| Frequency range | 0-12.4GHz | Yes, comfortably covers 2.87GHz |
| Max PCB thickness | 0.8mm (0.79mm per footprint note) | **Only if using the RO4350B 0.76mm substrate** (the one this session's dual-mode work actually used). The project's other documented default, AD250C 1.524mm (`CLAUDE.md` §7), is **too thick for this connector** — don't mix the two without re-checking. |
| Connector pin diameter | 0.76mm (radius 0.38mm) | **Sits on/past a known meshing instability — see below.** |
| Body / insulator | Brass (gold), Teflon (PTFE) insulator | Same PTFE assumption (`eps_r=2.08, tand=4e-4`) already used for the existing connector model — no change needed there. |
| Mounting | Edge mount, 4 ground legs (2 front pads flanking a center signal pad, 2 back pads) + center signal pin, all soldered | See "ground stitching" plan below — this is the part that's genuinely new work, not just a dimension swap. |

### Critical risk: pin radius sits on the known meshing cliff

`docs/sma_connector/README.md` documents a **~4-micron-wide instability**
found by bisection: `sma_rin_mm=0.375` meshes clean, `sma_rin_mm=0.379`
produces extra spurious PEC faces and near-total reflection — not a physics
effect, a meshing/classification bug that was never root-caused, only
avoided (current default backed off to 0.35mm specifically to clear it).

**This connector's real half-pin-diameter is 0.38mm — past the unstable
0.379mm point already found.** Do not skip straight to a full driven+SMA
re-tune with this value. First:

1. Re-run the **isolated bare-line bisection check** (the same kind of
   fast, ~1-2 minute check used to originally find the cliff — see the
   "razor-thin meshing instability" paragraph in `docs/sma_connector/README.md`
   for the method) at `sma_rin_mm=0.38` specifically, before trusting any
   mesh built with it.
2. If it lands in the unstable zone (likely), you have two options: (a) back
   off slightly the same way the original connector was (document the real
   vs. modeled value difference, same as the existing README does), or (b)
   actually root-cause the classification bug this time, since you'll now
   have hit it with *two independent real connectors* — that's a stronger
   signal it's worth fixing properly rather than dodging again. Worth a look
   at the face-classification logic in `build_mesh()` (`palace_dualmode_driven.py`
   lines ~245-258, the `on_sma_pin`/`on_sma_shell` detection by `_near(yext, ...)`
   proximity) — my guess without having debugged it: it's a mesh-tolerance
   issue in how `_near()` bins a face's extent to the pin vs. shell radius
   when the two get close together relative to local mesh size, not a
   geometry-construction bug per se, but that's a guess, not a finding.

### Derived simulation parameters

The datasheet gives pin diameter but not the PTFE outer diameter directly.
The existing connector model's default (`sma_rout_mm=1.164mm` from
`sma_rin_mm=0.35mm`) was itself derived, not sourced from a datasheet — via
the standard coax impedance formula `Z0 = (60/√εr)·ln(D/d)` solved for
`D/d` at `Z0=50Ω, εr=2.08` (PTFE), giving a fixed ratio `D/d ≈ 3.326`
regardless of pin size. Applying the same ratio to this connector's real
pin diameter:

```
sma_rin_mm  = 0.38     # 0.76mm pin diameter / 2, from the datasheet
sma_rout_mm = 1.264     # 3.326 * sma_rin_mm, same Z0=50/PTFE derivation
                         # as the existing default -- verify this is still
                         # reasonable once you've cleared the meshing check
                         # above, don't just trust the arithmetic blindly
sma_eps_r   = 2.08      # unchanged (PTFE)
sma_tand    = 4.0e-4    # unchanged
```

Pass these directly to `build_mesh(..., sma_rin_mm=0.38, sma_rout_mm=1.264, ...)`
in `palace_dualmode_driven.py` (or `palace_driven.py` for the N=3 model, if
you want the connector on both). No code change needed for this part, just
different call-site arguments — don't hardcode these as new defaults until
the meshing check above passes.

### Ground stitching at the connector footprint — plan, not yet implemented

The datasheet footprint (page 4) shows the real connector's 4 ground legs
landing on two pads on the front face (flanking the center signal pad, at
±2.62mm) and two on the back face (±2.615mm) — i.e. real, discrete ground
contacts at the board edge, not the continuous idealized ground ring the
current ` build_mesh()` models (a full-perimeter PTFE-clip-to-ground
abstraction, which is a fine simplification for getting a clean coax mode,
but doesn't reflect this specific connector's discrete-leg grounding).

You asked for board-side ground vias at this footprint so the *physical*
board has a good, low-inductance return path right at the connector — that
is a real gap right now: **the feed/taper region outside the SIW cavity
currently has no top-side ground copper at all** (only the microstrip trace
itself is copper there — see `build_mesh()`'s face classification, the
`_near(cz, h)` branch only assigns PEC to the cavity span `0<=cx<=Li` or the
trace polygon, nothing else). Adding stitching vias needs two things
together, not vias alone:

1. **Top-side ground copper pour** flanking the microstrip trace in the feed
   span (`X0` to `0`, and `Li` to `X1`), with normal microstrip ground
   clearance around the trace — this doesn't exist yet and has to be added
   as new copper polygon(s) alongside `trace_surface()`.
2. **A small row of vias** (4-6, positioned near the connector's real leg
   pad locations, ±2.6mm off-axis) through that new copper pour down to the
   bottom ground plane (which is already solid PEC everywhere, including
   under the feed — see the `_near(cz, 0.0): pec.append(tag)` branch, so the
   via's bottom end has something to land on already).

Suggested signature: `build_mesh(..., gnd_stitch: bool = False, n_gnd_stitch: int = 4,
gnd_stitch_offset_mm: float = 3.0)`, wired in next to the existing SMA
construction block (`palace_dualmode_driven.py` ~line 168 onward) and the
face-classification loop (~line 236 onward, needs a new `on_gnd_via` case
alongside the existing `on_via` check, and the new copper pour needs its own
polygon check next to `trace_polys`).

**I did not implement this in code this session** — it needs new geometry
(copper pour, not just vias) plus careful face-classification changes in a
part of the code that has a documented history of subtle bugs (ring-severing,
the meshing cliff above), and I'd rather hand you a specific, scoped plan
than a change I couldn't render-check and verify end-to-end. Recommended
order: (a) clear the meshing-cliff check above first with the *existing*
continuous-ring model at the new pin size, so you know that part is solid;
then (b) add the ground pour + stitching vias as a separate, isolated change,
sanity-checked with `plot_layout_2d()`/a `render_png` preview (cheap, no
Palace solve needed) before running any real driven simulation with it.

### Suggested step-by-step order on the new machine

1. Environment setup (above), confirm `uv run python -c "from CSXCAD import ...; print('ok')"`
   and a trivial Palace eigenmode run both work.
2. Point `PALACE` at the new install; re-run the existing dual-mode
   eigenmode calibration (`scripts/dualmode_calibrate_v2.py`) as a smoke
   test that the environment reproduces last session's numbers.
3. Bare-line bisection check at `sma_rin_mm=0.38` (new, not yet run — see
   "critical risk" above). This is the single highest-priority, cheapest
   next step.
4. If clear (or backed off to a safe value): re-run the driven+SMA sanity
   check on the *already-landed* 1.5mm/3.0mm dual-mode design with the new
   connector dimensions swapped in, to see how much (if at all) it changes
   the already-good result — don't assume it's neutral.
5. Ground-stitching geometry (plan above) as a separate, isolated change,
   preview-rendered before any real solve.
6. Only then, if warranted, a fresh Bayesian re-tune against the new
   connector + stitching — same GP-surrogate pattern as
   `palace_opt_dualmode.py`.

## Branch / PR status

`sma_conn` is 2 commits ahead of `origin/main`, never pushed. This session's
work (all of `docs/dualmode_cavity/`, this file, and the untracked
`src/siwfilter/palace_dualmode*.py` / `scripts/dualmode_*.py` modules) will
be committed and squash-merged into a single PR against `main` so the whole
dual-mode phase lands as one reviewable unit. See the PR description for the
final commit message; this file stays as the pickup doc on `main` after
merge (or delete it once you've actually picked the task up and it's stale
— it's a handoff note, not permanent project documentation).
