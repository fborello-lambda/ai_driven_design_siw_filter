# Handoff — moving to the GPU machine

Written at the end of a session on branch `sma_conn`. This is the pickup
document — read this first, then `docs/dualmode_cavity/README.md` and
`docs/sma_connector/README.md` for the full technical history.

## TL;DR — do these in order

1. **Build the unified "AI-driven design" CLI first** (architecture below) —
   everything after this depends on having one clean pipeline instead of
   three copy-pasted optimizer scripts. First milestone inside this: a
   baseline-comparison command that reproduces the already-landed N=3
   cascade vs. N=2 dual-mode results through the new CLI, as a regression
   check that the consolidation didn't change behavior.
2. **Then** simulate the real Taoglas `EMPCB.SMAFSTJ.B.HT` SMA connector
   (with its actual footprint/ground legs, not the idealized ring used so
   far) through that CLI. Compatibility check + plan below — **read the
   "critical risk" section before running anything**, this connector's pin
   size sits right on a previously-documented meshing instability.
3. **Then** start exploring new structures for the paper — that's the actual
   point of building the CLI first.

This is a plan, not a partial implementation — no new topology/optimizer
code was committed this session (a draft `Topology` interface sketch was
written and then deleted rather than left half-wired; the design is
captured in prose below instead, precisely so nothing half-working has to be
untangled on the new machine). This branch (`sma_conn`) is 2 commits ahead
of `origin/main` and was never pushed before this session; see the bottom
for PR status.

## Architecture: unified AI-driven design CLI

### Why

The project accumulated, phase by phase: **three separate Bayesian/
coordinate-descent optimizer drivers** (`palace_opt.py`, `palace_opt_sma.py`,
`palace_opt_dualmode.py`, each ~200-500 lines of copy-pasted skopt-loop /
scoring / CSV-logging / plotting boilerplate), **a hand-rolled "ideal
Chebyshev response" function** inside `palace_opt_dualmode.py`
(`ideal_response_db()`) that reimplements math `synthesis.py` already has
*generically* (`chebyshev_g`/`coupling_matrix`/`sparams_from_matrix` already
work for any `N`, not just N=2 — nothing in them is N=2-specific), and
**11 one-off scripts in `scripts/`**, each hardcoding its own parameters for
one question asked mid-session.

A future paper on AI-driven RF design only works if adding a new structure
means implementing one small interface, not copying 500 lines and hand-
editing them. This is a **consolidation**, not a physics rewrite: the
validated gmsh/Palace mesh-construction code in `palace_driven.py` /
`palace_dualmode_driven.py` gets wrapped, not touched internally — it has a
real bug history (ring-severing, via-position quantization, a meshing
instability cliff — see `docs/*/README.md`), so nothing about *how a mesh
gets built* should change, only *how a search is driven and compared*.

DRY, simple, no cleverness for its own sake — comments only where the WHY
isn't obvious from the code (matches how this session's own code was
written; keep doing that).

Fixed substrate going forward: JLCPCB-available Rogers RO4350B 0.76mm
(`config.py`'s `DEFAULT_SUBSTRATE` already is this). Board size = JLCPCB
cost, so "smaller is cheaper" should be a first-class term in the score, not
an accident of whichever design the search happened to land on.

### The interface

One small `Topology` protocol every physical structure implements —
`src/siwfilter/topologies/base.py`:

```python
class Topology(Protocol):
    name: str
    poles_per_cavity: int      # 1 = single-mode cavity, 2 = dual-mode, ...

    def param_space(self, spec: FilterSpec) -> dict[str, ParamRange]: ...
    def build_mesh(self, spec: FilterSpec, out_name: str, **params) -> MeshResult: ...
    def plot_layout_2d(self, spec: FilterSpec, path: str, **params) -> str: ...
    def board_length_mm(self, spec: FilterSpec, **params) -> float: ...
    def calibrate(self, spec: FilterSpec) -> dict | None: ...   # optional cheap eigenmode step
```

`ParamRange = tuple[init, lo, hi]` (mm). `MeshResult` mirrors what
`palace_driven.build_mesh()` / `palace_dualmode_driven.build_mesh()` already
return (`mesh_path`, `ports`, `tets`, `nodes`, `sma` dict or `None`).

Two implementations, each a **thin adapter**, no mesh-construction logic
moves out of the existing files:

- `topologies/cascade.py` — wraps `palace_geometry.py`/`palace_driven.py`
  (N single-mode cavities). **One real gap found while sketching this**:
  `palace_driven.build_mesh()` currently reads the module-global `SPEC`
  directly (`build_geometry(SPEC)`, `siw_geometry.py` line ~88) instead of
  taking a `spec` argument — it can't be pointed at a different f0/N today.
  Fix is a tiny, additive, backward-compatible change: add
  `spec: FilterSpec | None = None` to `build_mesh()`'s signature and use
  `build_geometry(spec or SPEC)` — existing callers (`palace_opt.py`, the
  `siw --stage` CLI) keep working unchanged since the default is still the
  global `SPEC`.
- `topologies/dualmode.py` — wraps `palace_dualmode.py`/
  `palace_dualmode_driven.py` (N/2 dual-mode cavities). No equivalent gap —
  `palace_dualmode_driven.build_mesh()` already takes all its geometry as
  explicit arguments.
- Iris width is a single shared value across all internal irises in both
  existing builders (`w_iris_mm: float`, not a per-iris list) — keep that;
  it's what was actually validated, don't add per-iris freedom nobody asked
  for.
- For cascade with N>3, generate `ceil(N/2)` independent per-cavity-length
  parameters and mirror them into the `l_cavs_mm` list `build_mesh()` already
  accepts (assumes a mirror-symmetric physical structure, which is the
  standard assumption for a symmetric bandpass response — don't over-build
  this into fully independent per-cavity lengths unless a real design
  needs it).

### The generic optimizer — `src/siwfilter/optimize.py`

Replaces all three `palace_opt*.py` files. Takes a `Topology` + `FilterSpec`
+ a budget:

1. Ideal target response for **any N**, via `synthesis.chebyshev_g` /
   `coupling_matrix` / `sparams_from_matrix` (already general — this is
   what retires `palace_opt_dualmode.py`'s N=2-only `ideal_response_db()`).
2. Same methodology already validated this session (v16): skopt GP-surrogate
   coarse search, scoring = peak-normalized S21/S11 curve-fit RMSE against
   the ideal response (excludes real insertion loss from the shape error,
   since that's substrate-loss-limited and geometry can't fix it) → fine-
   mesh confirm on a wider/denser sweep → post-hoc fabrication-tolerance
   check (round to 0.1mm, re-confirm).
3. **New generic score term: `board_length_mm(spec, **params)`**, weighted
   and configurable (small nonzero default) — biases every future search
   toward the cheaper/smaller design among equally-good electrical fits.
   This is genuinely new behavior, present in none of the three files it
   replaces.
4. One shared CSV logger / best-JSON writer / comparison plotter instead of
   three near-identical copies.

### The "black box pipeline" — standard visual output, every run

Every `siw design` / `siw compare-baselines` run should save, per design,
exactly the three artifacts already used by hand throughout this session —
this is the actual point of calling it a "black box": feed in a spec, get
these three back, without needing to know what's inside.

1. **Top view** — `Topology.plot_layout_2d()` (matplotlib, no mesh/solve
   needed) — already exists for both topologies
   (`palace_dualmode_driven.plot_layout_2d()`; cascade has the equivalent in
   `layout_plot.py`'s `plot_layout()`).
2. **3D render of what Palace will actually simulate** — both
   `build_mesh()` functions already support this via `render_png=<path>`
   (offscreen shaded gmsh render, no full tet mesh needed — see
   `palace_driven.py`/`palace_dualmode_driven.py`, the `render_png` branch
   right before full mesh generation). Just needs to be called and wired
   into the CLI output, not built from scratch.
3. **S21/S11 comparison** — one image, two stacked subplots, S21 on top /
   S11 on bottom (exactly `docs/dualmode_cavity/results_all_variants.png`'s
   layout) — reuse that plotting code as the template, generalized to plot
   N designs instead of 4 hardcoded ones.

### CLI surface — extends existing `src/siwfilter/cli.py`

Light stages (`synth`/`geometry`/`layout`/`cst`/`report`) stay as-is. New:

```
siw compare-baselines
    # regenerates the 3 artifacts above for the already-landed designs
    # (N=3 cascade, N=2 dual-mode @ 1.5/3.0mm) as one side-by-side
    # comparison -- the first thing to get working, since the parameters
    # are already known (see docs/dualmode_cavity/README.md's table) and
    # this only needs re-running existing, validated mesh builders, not a
    # new multi-hour search. Best first regression check that the
    # consolidation preserves the historical numbers.

siw design --topology {cascade,dualmode} [--f0 2.87e9] [--N 2] [--fbw 0.05]
           [--ripple 0.1] [--evals 18] [--fine-sweep 2.5e9 3.0e9 1e7]
    # param-space init -> optional eigenmode calibration -> Bayesian coarse
    # search -> fine confirm -> fab-tolerance check -> the 3 artifacts above

siw layout --topology ... --params a=57.21,w_iris=15.26,...
    # just artifact 1+2 (no solve) -- fast geometry sanity check

siw sweep --topology ... --params-file best.json --fmin 0.1 --fmax 7 --step 0.1
    # generic wideband sweep of any landed design (generalizes
    # scripts/dualmode_wideband_sweep.py)
```

### Cleanup, once the above is built and verified (not before)

All of `scripts/sma_compare_*.py`, `sma_3way_*.py`, `sma_progress_plot.py`,
`dualmode_2port_test.py`, `dualmode_calibrate.py`,
`dualmode_calibrate_ywall.py` are superseded once `siw compare-baselines` /
`siw design` work — fully summarized already in `docs/sma_connector/
README.md` / `docs/dualmode_cavity/README.md` and preserved in git history,
so deleting them is safe. `dualmode_calibrate_v2.py`'s sweep logic folds
into `DualModeTopology.calibrate()`; `dualmode_wideband_sweep.py` folds into
`siw sweep`. **Delete these only after the replacement actually runs** —
don't remove the reference material before its replacement exists.

### Explicitly out of scope for this pass

- `calibrate.py`/`qe_calibrate.py`/`openems_sim.py` (openEMS-based, cascade-
  only) — untouched; no new topology uses openEMS, only Palace.
- `cst_export.py` — only exports the N=3 cascade today; dual-mode has no
  CST export path at all yet. Real, separate follow-up work.

### Verification (once implemented)

1. `siw compare-baselines` reproduces the numbers in
   `docs/dualmode_cavity/README.md`'s results table through the new code
   path — the regression check that matters most.
2. `siw design --topology dualmode --evals 3` (tiny budget) launches and
   produces sane early evals — full multi-hour confirmation is real,
   separate compute, not a "does it work" check.
3. `siw layout --topology dualmode --params a=57.21,w_iris=15.26,x_iris=28.68,y_wall=8.62,w_ext=16.31`
   reproduces `docs/dualmode_cavity/layout_1p5mm_final.png`.

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
the new machine) before running anything. Once the unified `optimize.py`
above exists this becomes one constant instead of N copies.

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

## Task: Taoglas EMPCB.SMAFSTJ.B.HT connector

### Can it be used? Yes, with one real risk to check first.

Datasheet: `EMPCB.SMAFSTJ.B.HT`, SMA(F) edge-mount PCB jack.

| Spec | Value | Fits this project? |
|---|---|---|
| Impedance | 50Ω | Yes |
| Frequency range | 0-12.4GHz | Yes, comfortably covers 2.87GHz |
| Max PCB thickness | 0.8mm (0.79mm per footprint note) | **Only if using the RO4350B 0.76mm substrate** (the one this session's dual-mode work actually used). The project's other documented default, AD250C 1.524mm (`CLAUDE.md` §7), is **too thick for this connector** — don't mix the two without re-checking. |
| Connector pin diameter | 0.76mm (radius 0.38mm) | **Sits on/past a known meshing instability — see below.** |
| Body / insulator | Brass (gold), Teflon (PTFE) insulator | Same PTFE assumption (`eps_r=2.08, tand=4e-4`) already used for the existing connector model — no change needed there. |
| Mounting | Edge mount, 4 ground legs (2 front pads flanking a center signal pad, 2 back pads) + center signal pin, all soldered | This is the part that needs new geometry work, not just a dimension swap — see "ground stitching" below. |

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

No code change needed for this part on its own — different call-site
arguments to the existing `build_mesh(..., sma_rin_mm=0.38, sma_rout_mm=1.264, ...)`.
Don't hardcode these as new defaults until the meshing check above passes.

### Ground stitching at the connector footprint — real geometry work, not a dimension swap

The datasheet footprint (page 4) shows the real connector's 4 ground legs
landing on two pads on the front face (flanking the center signal pad, at
±2.62mm) and two on the back face (±2.615mm) — real, discrete ground
contacts at the board edge, unlike the continuous idealized ground ring the
current `build_mesh()` models (a full-perimeter PTFE-clip-to-ground
abstraction — fine for a clean coax mode, but not this specific connector's
discrete-leg grounding).

You want board-side ground vias at this footprint so the *physical* board
has a good, low-inductance return path right at the connector — that's a
real gap right now: **the feed/taper region outside the SIW cavity
currently has no top-side ground copper at all** (only the microstrip trace
itself is copper there — see `build_mesh()`'s face classification, the
`_near(cz, h)` branch only assigns PEC to the cavity span `0<=cx<=Li` or the
trace polygon, nothing else). Two things are needed together, not vias
alone:

1. **Top-side ground copper pour** flanking the microstrip trace in the feed
   span (`X0` to `0`, and `Li` to `X1`), with normal microstrip ground
   clearance around the trace — doesn't exist yet, needs to be added as new
   copper polygon(s) alongside `trace_surface()`.
2. **A small row of vias** (4-6, near the connector's real leg pad locations,
   ±2.6mm off-axis) through that new copper pour down to the bottom ground
   plane (already solid PEC everywhere including under the feed — see the
   `_near(cz, 0.0): pec.append(tag)` branch, so the via's bottom end already
   has something to land on).

Suggested signature: `build_mesh(..., gnd_stitch: bool = False, n_gnd_stitch: int = 4,
gnd_stitch_offset_mm: float = 3.0)`, wired in next to the existing SMA
construction block (`palace_dualmode_driven.py` ~line 168 onward) and the
face-classification loop (~line 236 onward, needs a new `on_gnd_via` case
alongside the existing `on_via` check, and the new copper pour needs its own
polygon check next to `trace_polys`).

Recommended order: (a) clear the meshing-cliff check above first with the
*existing* continuous-ring model at the new pin size, so that part is known
solid; then (b) add the ground pour + stitching vias as a separate,
isolated change, sanity-checked with `plot_layout_2d()`/a `render_png`
preview (cheap, no Palace solve needed) before running any real driven
simulation with it. This is exactly the kind of change the new
`Topology.build_mesh()` wrapper should sit in front of once it exists —
build it against the unified CLI, not as another one-off script.

## Branch / PR status

`sma_conn` → `origin/main`, PR: check `gh pr list` or the repo's GitHub page
(opened earlier this session). **Recommend squash-merging** — the commits
are incremental checkpoints of one continuous investigation, not
independently meaningful history. Not merged automatically; that's a
deliberate call for whoever picks this up.
