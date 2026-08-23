"""Generic Palace-driven optimizer: one implementation for every Topology,
replacing palace_opt.py / palace_opt_sma.py / palace_opt_dualmode.py (each a
~200-500 line copy of the same GP-surrogate search / CSV logging / plotting
boilerplate, one per topology -- see HANDOFF.md's "Architecture" section for
the full rationale).

Methodology (v17; v16 was validated in palace_opt_dualmode.py this session):
  1. Ideal (lossless) target response for ANY N via synthesis.chebyshev_g /
     coupling_matrix / sparams_from_matrix -- these were already fully
     general, not N=2-specific; this retires palace_opt_dualmode.py's
     hand-rolled ideal_response_db().
  2. GP-surrogate (skopt) coarse search: score = curve-fit RMSE of the
     simulated |S11|,|S21| against the ideal response (S21 peak-normalized
     before fitting, so real substrate-loss-limited insertion loss never
     enters the shape error) + a mild direct-IL term + a board-length term
     (biases every search toward the cheaper/smaller design among
     electrically-similar fits) + centre-frequency and bandwidth terms.
     See score() for what each term is for; v17 changed three things:
       - |S11| is CLIPPED at S11_FLOOR_DB before the RMSE. Unclipped, the
         term was dominated by how exactly a design lands the ideal's
         reflection nulls (which go to -inf in dB) rather than by whether it
         is well matched.
       - an EXPLICIT centre-frequency term (with a deadband for mesh
         uncertainty); previously frequency error was only implicit.
       - the bandwidth term is two-sided; it used to be a one-sided hinge
         that said nothing about a too-narrow passband.
     Band edges are interpolated (band_edges()), not snapped to sweep points.
  3. Fine-mesh, wide-frequency confirm of the coarse winner.
  4. Fab-tolerance check: round the winner to 0.1mm, re-confirm.

Mesh-quality defaults (mesh_max/mesh_min/h_air_factor) were re-derived on
this session's machine (15GB RAM, no swap) by profiling the FULL 13-point
coarse sweep (not just one point -- the old 7.4GB-box compromises were hit
by memory *accumulating across frequency samples within one run*, not just
per-point peak): mesh_max=1.2/mesh_min=0.2/h_air_factor=6.0 measured
~2.1GB peak per MPI rank at -np 4 (~8.4GB worst-case total), safely under
this machine's 15GB with no swap -- see the CLI-consolidation session notes.
This is NOT re-derived per machine automatically; re-profile before trusting
these on a smaller box (search for "mesh_max" in this file).

Device split (per user request this session): the driven+SMA solves here
default to CPU with multi-rank domain decomposition -- a 6GB GPU card OOMs
past -np 1 (each MPI rank opens its own CUDA context), and this mesh is too
big for single-rank GPU to help. Topology.calibrate() (cheap eigenmode,
small mesh) is the piece that actually benefits from GPU/np=1 -- see
DualModeTopology.calibrate().
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

import numpy as np

from .config import FilterSpec, find_palace, has_gpu, out_data, out_img
from .synthesis import chebyshev_g, coupling_matrix, sparams_from_matrix
from .topologies.base import Topology

# ---------------------------------------------------------------------------
# Mesh-quality / device defaults -- see module docstring for how these were
# derived on this machine.
#
# "Fine" deliberately reuses the SAME mesh settings as "coarse" -- only the
# frequency step/range tightens. This mesh density was already validated as
# ACCURATE (see palace_opt_dualmode.py's docstring history: "fine=(0.6,0.15)
# OOM-crashed... 1.0mm was already validated as ACCURATE... there's no
# correctness reason to go finer") -- fine-mesh refinement buys no accuracy
# the project has ever needed, only OOM risk.
#
# PER-TOPOLOGY, not a single global preset: cascade (N=3, 196 vias) and
# dualmode (1 cavity, 78 vias) sit at very different DOF counts for the same
# mesh_min (which resolves via/trace features and is NOT safe to coarsen --
# that's the actual accuracy-critical knob per the history above). Reusing
# dualmode's tightly-tuned (1.2, 0.2, 6.0) for cascade OOM-killed (signal 9)
# the fine confirm at ~1M tets / ~14GB on this 15GB machine -- discovered the
# hard way this session. Cascade's preset instead matches what
# palace_opt.py/palace_opt_sma.py already used successfully (mesh_max=3.5,
# mesh_min=0.6, h_air_factor=6.0) -- don't re-tighten this without re-running
# the same full-sweep RSS profiling done for dualmode's preset (see the
# CLI-consolidation session notes).
# ---------------------------------------------------------------------------
MESH_PRESETS: dict[str, tuple[float, float, float]] = {
    "cascade": (3.5, 0.6, 6.0),
    "dualmode": (1.2, 0.2, 6.0),
}
DEFAULT_MESH_PRESET = MESH_PRESETS["dualmode"]
CPU_NP = 4

# --- GPU path -------------------------------------------------------------
# GPU driven solves work, but only in a specific configuration found by
# bisection this session (everything here is load-bearing; changing any one
# of them reintroduces CUDA_ERROR_OUT_OF_MEMORY on a 6GB card):
#
#   1. MFEM_MEMORY=cuda -- disables MFEM's default Umpire *pooled* device
#      allocator. The pool requests a fixed ~4GiB block (observed failing at
#      exactly 2^32+16 bytes, byte-identical across three different mesh
#      sizes), which alone exhausts a 6GB card regardless of problem size.
#      Plain cudaMalloc allocates what's actually needed instead.
#   2. -np 1 -- one MPI rank per GPU (each rank opens its own CUDA context;
#      see run_driven's clamp).
#   3. A slightly coarser mesh than the CPU dualmode preset. Note this is NOT
#      an accuracy compromise: (1.5, 0.25, 3.0) is exactly the setting
#      palace_opt_dualmode.py used for every validated dual-mode result in
#      docs/dualmode_cavity/README.md.
#
# Whether GPU is actually FASTER is hardware-dependent -- Palace solves in
# double precision, and consumer NVIDIA cards run FP64 at 1/32 rate, so a
# many-core CPU can win despite the GPU's much higher memory bandwidth.
# Benchmark before assuming; --device is exposed on every CLI subcommand.
GPU_MESH_PRESETS: dict[str, tuple[float, float, float]] = {
    "dualmode": (1.5, 0.25, 3.0),
    # cascade's GPU-viable mesh is NOT yet established -- its CPU preset is
    # already much coarser and its DOF count far higher (196 vias vs 78). Fall
    # back to the CPU preset and let it fail loudly rather than silently
    # shipping an unvalidated mesh.
}
GPU_ENV = {"MFEM_MEMORY": "cuda"}

# Largest mesh this GPU actually completes a driven solve on. Measured on the
# 6GB card: 164.5k / 166.4k / 174.6k tets finish the full sweep; 178.4k and
# 180.0k OOM at the error estimator. The boundary is therefore 174.6k..178.4k,
# and 176k sits inside that gap.
#
# This is a PREDICTION so we skip GPU rather than discover the failure: a
# doomed attempt still costs 40-140s of meshing+assembly before it dies, and
# the ceiling falls inside this project's search boxes, so a naive GPU-first
# policy pays that toll on a large fraction of evals.
#
# Set it from MEASUREMENTS ON BOTH SIDES. A first cut of 168k was derived from
# the OOM points alone and silently excluded the 174.6k case that demonstrably
# runs -- which sent the nominal design to CPU for no reason, the exact waste
# this constant exists to prevent. The runtime fallback below still catches
# anything that slips through.
GPU_MAX_TETS = 176_000


def resolve_device(device: str, topology_name: str) -> str:
    """Turn a requested device ("auto"/"GPU"/"CPU") into an actual one.

    "auto" picks GPU only when all three hold: a GPU exists, and this topology
    has a GPU-validated mesh preset. Anything else falls back to CPU, so the
    same command works unchanged on a machine with no GPU at all.

    Measured on this session's GTX 1660 SUPER (6GB), dualmode 161k tets,
    13-point sweep: GPU -np 1 = 133.5s vs CPU -np 4 = 165.2s (~1.24x), with
    S-params agreeing to <1e-9 dB -- so GPU is preferred where validated, but
    the margin is hardware-specific (Palace is FP64; consumer cards run FP64
    at 1/32 rate and win here on memory bandwidth, not FLOPs).
    """
    if device != "auto":
        return device
    if topology_name in GPU_MESH_PRESETS and has_gpu():
        return "GPU"
    return "CPU"


def _mesh_preset(topology_name: str, device: str = "CPU") -> tuple[float, float, float]:
    if device == "GPU":
        if topology_name in GPU_MESH_PRESETS:
            return GPU_MESH_PRESETS[topology_name]
        print(f"WARNING: no GPU-validated mesh preset for topology '{topology_name}'. "
              f"Using its CPU preset, which may exceed GPU memory -- if this OOMs, "
              f"bisect a coarser mesh for it the way GPU_MESH_PRESETS['dualmode'] was "
              f"found, or run this topology with --device CPU.")
    return _cpu_mesh_preset(topology_name)


def _cpu_mesh_preset(topology_name: str) -> tuple[float, float, float]:
    return MESH_PRESETS.get(topology_name, DEFAULT_MESH_PRESET)


def _db(x: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return 20 * np.log10(np.maximum(np.abs(x), 1e-12))


def ideal_target_db(spec: FilterSpec, f_ghz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ideal (lossless) |S11|,|S21| in dB for spec.N/ripple_db/FBW, via the
    general (N+2)-node coupling-matrix formulation -- works for any N,
    including N=2 (dual-mode: 2 poles, 1 physical cavity)."""
    g = chebyshev_g(spec.N, spec.ripple_db)
    M = coupling_matrix(g, spec.FBW)
    f_hz = np.atleast_1d(np.asarray(f_ghz, dtype=float)) * 1e9
    s11, s21 = sparams_from_matrix(M, spec.FBW, spec.f0, f_hz)
    return _db(s11), _db(s21)


def _fit_window_ghz(spec: FilterSpec) -> tuple[float, float]:
    f0_ghz = spec.f0 / 1e9
    half = 1.5 * (spec.FBW * f0_ghz) / 2.0
    return f0_ghz - half, f0_ghz + half


def _band_ghz(spec: FilterSpec) -> tuple[float, float]:
    return spec.f1 / 1e9, spec.f2 / 1e9


def band_edges(f: np.ndarray, s21_db: np.ndarray) -> dict:
    """-3dB band edges, LINEARLY INTERPOLATED between sweep points.

    Taking the edges as the outermost sampled points above the threshold
    quantizes both bandwidth and centre frequency to the sweep step -- 20 MHz
    on the coarse sweep, which is a seventh of the whole 143 MHz target
    bandwidth. That granularity is far too coarse to optimize against: every
    design in a wide neighbourhood reports the identical bw, so the objective
    is flat where it should be informative. Interpolating the two crossings
    recovers sub-step resolution from the same data.

    Edges are the FIRST and LAST crossings over the window, not a walk outward
    from the peak: a dual-mode response is double-humped, and walking from the
    taller hump would stop at the dip between the poles and report half the
    passband.

    `fc_3db` (band centre) is what the score uses, not the argmax peak: on a
    double-humped response argmax picks whichever pole happens to be taller,
    which can sit an entire ripple-width off the true centre.
    """
    thr = float(s21_db.max()) - 3.0
    idx = np.flatnonzero(s21_db >= thr)
    if idx.size == 0:
        return {"bw": 0.0, "fc_3db": float(f[int(np.argmax(s21_db))]),
                "f_lo": 0.0, "f_hi": 0.0, "band_truncated": True}

    def _cross(i, j):
        """f where s21 crosses thr on the segment i->j."""
        y0, y1 = float(s21_db[i]), float(s21_db[j])
        if y1 == y0:
            return float(f[j])
        return float(f[i] + (f[j] - f[i]) * (thr - y0) / (y1 - y0))

    i0, i1 = int(idx[0]), int(idx[-1])
    trunc = (i0 == 0) or (i1 == len(f) - 1)
    f_lo = _cross(i0 - 1, i0) if i0 > 0 else float(f[0])
    f_hi = _cross(i1 + 1, i1) if i1 < len(f) - 1 else float(f[-1])
    return {"bw": (f_hi - f_lo) * 1000.0, "fc_3db": 0.5 * (f_lo + f_hi),
            "f_lo": f_lo, "f_hi": f_hi, "band_truncated": trunc}


def _driven_config(mesh: str, res: dict, spec: FilterSpec, tag: str,
                   fmin: float, fmax: float, step: float, device: str) -> dict:
    """Build the Palace Driven-problem config for any topology's build_mesh()
    result -- generic over with_sma True/False (3rd material + WavePort
    voltage paths only appear when res['sma'] is set)."""
    sma = res.get("sma")
    materials = [
        {"Attributes": [1], "Permeability": 1.0,
         "Permittivity": res.get("eps_r", spec.substrate.eps_r),
         "LossTan": res.get("tand", spec.substrate.tan_d)},
        {"Attributes": [2], "Permeability": 1.0, "Permittivity": 1.0, "LossTan": 0.0},
    ]
    port_in = {"Index": 1, "Attributes": [11], "Mode": 1, "Excitation": 1,
               "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6}
    port_out = {"Index": 2, "Attributes": [12], "Mode": 1,
                "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6}
    if sma:
        materials.append({"Attributes": [3], "Permeability": 1.0,
                          "Permittivity": sma["eps_r"], "LossTan": sma["tand"]})
        port_in["VoltagePath"] = sma["voltage_path_in"]
        port_out["VoltagePath"] = sma["voltage_path_out"]
    return {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": materials},
        "Boundaries": {"PEC": {"Attributes": [10]},
                       "Absorbing": {"Attributes": [13], "Order": 1},
                       "WavePort": [port_in, port_out]},
        "Solver": {"Order": 1, "Device": device,
                   "Driven": {"Samples": [{"Type": "Linear", "MinFreq": fmin,
                                           "MaxFreq": fmax, "FreqStep": step}]},
                   "Linear": {"Type": "Default", "KSPType": "GMRES", "Tol": 1e-8, "MaxIts": 300}},
    }


def _wait_for_free_palace():
    while subprocess.run(["pgrep", "-f", "palace-x86_64.bin"],
                         capture_output=True).returncode == 0:
        time.sleep(10)


def run_driven(topology: Topology, spec: FilterSpec, params: dict, tag: str,
               fmin: float, fmax: float, step: float,
               mesh_max: float, mesh_min: float, h_air_factor: float,
               device: str = "auto", np_ranks: int = CPU_NP,
               serialize: bool = True) -> dict:
    """Build the mesh + run one Palace Driven solve, return {ok, f, s11_db,
    s21_db, fc, il, bw, s11w, il_band, tag} (dB arrays over the swept band)."""
    device = resolve_device(device, topology.name)
    if device == "GPU" and np_ranks != 1:
        # Each MPI rank opens its own CUDA context on the SAME physical GPU --
        # verified this session that -np 4 OOMs even on the smallest eigenmode
        # mesh this project uses. There is exactly one GPU here, so >1 rank
        # can never help and reliably crashes; clamp rather than let every
        # caller remember this.
        print(f"[{tag}] GPU requested with np_ranks={np_ranks} -> forcing np_ranks=1 "
              f"(multi-rank GPU OOMs on a single card, verified this session)")
        np_ranks = 1
    mesh = tag + ".msh"
    try:
        res = topology.build_mesh(spec, mesh, mesh_max=mesh_max, mesh_min=mesh_min,
                                  h_air_factor=h_air_factor, **params)
    except Exception as e:
        return {"ok": False, "err": f"mesh:{e}"}
    # Require each port to have at least one face -- NOT exactly one. A coax
    # launch gives a single annulus, but a bare microstrip port legitimately
    # spans two faces (the substrate cross-section and the air above it), so
    # an exact ==(1,1) test silently rejects every with_sma=False run.
    n_in, n_out = res["ports"]
    if n_in < 1 or n_out < 1:
        return {"ok": False, "err": f"bad ports {res['ports']} (a port has no faces)"}

    if device == "GPU" and res.get("tets", 0) > GPU_MAX_TETS:
        # Predicted not to fit -- go straight to CPU instead of burning a
        # doomed GPU attempt first (see GPU_MAX_TETS).
        print(f"[{tag}] {res['tets']} tets > GPU_MAX_TETS={GPU_MAX_TETS} -> CPU directly",
              flush=True)
        device, np_ranks = "CPU", CPU_NP

    # Palace emits samples from fmin while <= fmax, i.e. FLOOR of the span in
    # steps, plus one. round() here over-counted by one whenever the span was
    # not an exact multiple of the step (fine sweep: 64.575 steps -> round 65
    # -> expected 66 vs the 65 actually produced), which flagged a complete
    # sweep as truncated and sent it for a pointless re-solve. The 1e-9 guards
    # a span that IS an exact multiple landing just under it in floating point.
    n_expected = int(np.floor((fmax - fmin) / step + 1e-9)) + 1
    palace = find_palace()

    def _solve(dev: str, ranks: int):
        """One Palace invocation. Returns (arrays | None, err | None)."""
        cfg = _driven_config(mesh, res, spec, tag, fmin, fmax, step, dev)
        cfgp = out_data(f"{tag}.json")
        json.dump(cfg, open(cfgp, "w"), indent=2)
        if serialize:
            _wait_for_free_palace()
        env = dict(os.environ, PATH=f"{os.path.dirname(palace)}:{os.environ['PATH']}")
        if dev == "GPU":
            # See GPU_ENV: disables MFEM's pooled (Umpire) device allocator,
            # whose fixed ~4GiB block request exhausts a 6GB card on its own.
            env.update(GPU_ENV)
        logp = out_data(f"{tag}.log")
        # Stale results from a previous attempt would look like a success.
        shutil.rmtree(out_data(f"postpro/{tag}"), ignore_errors=True)
        subprocess.run([palace, "-np", str(ranks), os.path.basename(cfgp)],
                       cwd=out_data(""), env=env, stdout=open(logp, "w"),
                       stderr=subprocess.STDOUT, check=False)
        csvp = out_data(f"postpro/{tag}/port-S.csv")
        if not os.path.exists(csvp):
            return None, "no csv"
        dd = np.genfromtxt(csvp, delimiter=",", names=True, deletechars="", replace_space="")
        nmm = dd.dtype.names
        ff = np.atleast_1d(dd[nmm[0]])
        # Palace writes port-S.csv incrementally, one row per frequency point,
        # so a run that dies partway (GPU OOM at the error estimator is how
        # this actually happens) leaves a VALID-LOOKING but truncated file.
        # Without this the design would be silently scored on part of its band.
        if len(ff) < n_expected:
            return None, f"incomplete sweep: {len(ff)}/{n_expected} points (see {logp})"
        return (ff, np.atleast_1d(dd[nmm[1]]), np.atleast_1d(dd[nmm[3]])), None

    got, err = _solve(device, np_ranks)
    if got is None and device == "GPU":
        # The GPU memory ceiling falls INSIDE this project's search boxes: the
        # same sweep succeeds for a small cavity and OOMs for a large one, so a
        # GPU-only run silently loses whichever design points happen to be big
        # (observed live -- most evals of a dualmode+stitching retune died this
        # way while two small-cavity ones survived). Falling back per-eval keeps
        # GPU's speed where it fits without dropping points where it doesn't.
        print(f"[{tag}] GPU attempt failed ({err}) -> retrying on CPU", flush=True)
        got, err = _solve("CPU", CPU_NP)
        device = "CPU"
    if got is None:
        return {"ok": False, "err": err, "tag": tag}
    f, s11_db, s21_db = got
    csv = out_data(f"postpro/{tag}/port-S.csv")

    ip = int(np.argmax(s21_db)); fc = float(f[ip]); il = float(s21_db[ip])
    b0, b1 = _band_ghz(spec)
    band = (f >= b0) & (f <= b1)
    s11w = float(s11_db[band].max()) if band.any() else 0.0
    il_band = float(s21_db[band].min()) if band.any() else -99.0
    edges = band_edges(f, s21_db)

    try:
        os.remove(out_data(mesh))
    except OSError:
        pass
    return {"ok": True, "device": device,
           "f": f, "s11_db": s11_db, "s21_db": s21_db, "fc": fc, "il": il,
           "s11w": s11w, "il_band": il_band, "tag": tag, "csv": csv, **edges}


#: Below this, a return loss is "matched enough" and further improvement is
#: not worth optimizer budget. The ideal Chebyshev |S11| plunges to -inf at
#: its reflection zeros (-35.8 dB at the sampled points for N=2/0.1dB/5%), so
#: an UNCLIPPED dB-domain RMSE is dominated by how precisely a design lands
#: those nulls -- a well-matched filter can carry a large error purely for
#: putting its zeros a few MHz off. Clipping BOTH curves to the same floor
#: makes the term measure what we actually care about: how much of the band
#: fails to reach a real, fabricable return loss.
S11_FLOOR_DB = -25.0


#: No fc penalty inside this deadband. fc is NOT mesh-converged in this
#: project -- the same design shifts 20-27 MHz between mesh densities (open
#: task #17). Penalizing linearly from zero would spend GP budget chasing
#: mesh noise; a deadband charges only for error the mesh study cannot
#: explain away. Shrink this once #17 pins the convergence down.
FC_DEADBAND_MHZ = 15.0


def score(spec: FilterSpec, r: dict, board_length_mm: float,
         w_board: float = 0.01,
         s11_floor_db: float = S11_FLOOR_DB, w_fc: float = 0.05,
         w_bw: float = 3.0, fc_deadband_mhz: float = FC_DEADBAND_MHZ) -> float:
    """v17 objective. Terms, and why each exists:

      s11_rmse    fit to the ideal Chebyshev |S11|, both curves clipped at
                  s11_floor_db (see S11_FLOOR_DB)
      s21_rmse    SHAPE fit only, both peak-normalized -- real dielectric loss
                  must not be charged here, it is charged once below
      il          direct insertion-loss term
      fc          NEW: |fc_3db - f0| outside a deadband. Previously frequency
                  error was only implicit (a detuned design fits the fixed
                  window badly), which is weak and confounded with shape
                  error: every geometry so far lands 2.89-2.93 GHz against a
                  2.87 target and nothing in the objective said so directly.
      bw          NEW: two-sided. The old term was a one-sided hinge that
                  charged for being too WIDE and nothing for being too narrow,
                  so an over-coupled design at 2x the target bandwidth was
                  barely discouraged and an under-coupled one not at all.
      board       mild size preference among electrically-similar fits
    """
    if not r.get("ok"):
        return 1e9
    fw0, fw1 = _fit_window_ghz(spec)
    fit = (r["f"] >= fw0) & (r["f"] <= fw1)
    if fit.sum() < 3:
        return 99.0
    s11_ideal, s21_ideal = ideal_target_db(spec, r["f"][fit])
    # Clip both, not just the ideal: clipping only the target would penalize a
    # design for being BETTER matched than the floor.
    s11_rmse = float(np.sqrt(np.mean(
        (np.maximum(r["s11_db"][fit], s11_floor_db)
         - np.maximum(s11_ideal, s11_floor_db)) ** 2)))
    s21_shape = r["s21_db"][fit] - r["s21_db"][fit].max()
    s21_ideal_shape = s21_ideal - s21_ideal.max()
    s21_rmse = float(np.sqrt(np.mean((s21_shape - s21_ideal_shape) ** 2)))
    f0_mhz = spec.f0 / 1e6
    fc_mhz = r.get("fc_3db", r["fc"]) * 1000.0
    fc_err = max(0.0, abs(fc_mhz - f0_mhz) - fc_deadband_mhz)

    bw_target = spec.FBW * f0_mhz
    bw_err = abs(r["bw"] - bw_target) / bw_target if bw_target > 0 else 0.0

    return (1.0 * s11_rmse + 0.5 * s21_rmse + 0.15 * abs(r["il"])
           + w_fc * fc_err + w_bw * bw_err
           + w_board * board_length_mm)


def _to_dict(order: list[str], x: list[float]) -> dict:
    return {k: round(float(v), 3) for k, v in zip(order, x)}


def evaluate(topology: Topology, spec: FilterSpec, params: dict, fine: bool = False,
            tag_prefix: str = "opt", device: str = "auto", np_ranks: int = CPU_NP,
            fine_sweep_ghz: tuple[float, float, float] | None = None) -> dict:
    device = resolve_device(device, topology.name)
    fw0, fw1 = _fit_window_ghz(spec)
    mmax, mmin, hair = _mesh_preset(topology.name, device)
    if fine:
        if fine_sweep_ghz is not None:
            fmin, fmax, step = fine_sweep_ghz
        else:
            fmin, fmax, step = fw0 - 1.0 * (fw1 - fw0), fw1 + 1.0 * (fw1 - fw0), 0.01
    else:
        fmin, fmax, step = fw0 - 0.3 * (fw1 - fw0), fw1 + 0.3 * (fw1 - fw0), 0.02
    tag = (f"{tag_prefix}F_" if fine else f"{tag_prefix}_") + "_".join(
        f"{k}{v:.2f}" for k, v in sorted(params.items()))
    r = run_driven(topology, spec, params, tag, fmin, fmax, step, mmax, mmin, hair,
                   device=device, np_ranks=np_ranks)
    board_len = topology.board_length_mm(spec, **params)
    r["score"] = score(spec, r, board_len)
    r["board_length_mm"] = board_len
    return r


def optimize(topology: Topology, spec: FilterSpec, budget: int = 18,
            n_initial: int | None = None,
            fine_sweep: tuple[float, float, float] | None = None,
            device: str = "auto", np_ranks: int = CPU_NP,
            log_name: str | None = None, best_json_name: str | None = None) -> dict:
    """GP-surrogate coarse search over topology.param_space(spec), fine-mesh
    confirm of the winner, fab-tolerance (0.1mm rounding) check. Returns the
    fine-confirmed best {params, metrics}."""
    from skopt import Optimizer
    from skopt.space import Real

    space_dict = topology.param_space(spec)
    # Params with lo==hi (e.g. cascade's w_ms, fixed at the true 50-ohm value
    # by convention -- see palace_opt_sma.py) aren't searched; skopt.Real
    # requires lo<hi anyway. Held constant across every eval instead.
    fixed = {k: v[0] for k, v in space_dict.items() if v[1] >= v[2]}
    free = {k: v for k, v in space_dict.items() if v[1] < v[2]}
    order = list(free.keys())
    space = [Real(lo, hi, name=k) for k, (_init, lo, hi) in free.items()]
    # Random-sampling phase before the GP starts exploiting. A FIXED default
    # (this was 10) silently turns a small budget into near-pure random
    # search: at budget=12 only 2 evals were GP-guided, and the "best" design
    # of such a run is just the luckiest random draw. Scale it with the budget
    # instead, keeping enough seeds to fit a surrogate over this dimensionality.
    if n_initial is None:
        n_initial = max(len(order) + 1, min(10, budget // 2))
    print(f"search: {budget} evals over {len(order)}D "
          f"({n_initial} random seed points, {budget - n_initial} GP-guided)",
          flush=True)
    opt = Optimizer(space, base_estimator="GP", acq_func="gp_hedge",
                    n_initial_points=n_initial, random_state=0)

    log_path = out_data(log_name or f"opt_{topology.name}_log.csv")
    best_json = out_data(best_json_name or f"opt_{topology.name}_best.json")

    def log_row(n, p, r):
        new = not os.path.exists(log_path)
        with open(log_path, "a") as fh:
            if new:
                fh.write("eval," + ",".join(order) +
                         ",fc,fc_3db,il,bw,s11w,board_mm,score\n")
            fh.write(f"{n}," + ",".join(f"{p[k]:.3f}" for k in order) +
                     f",{r.get('fc', 0):.4f},{r.get('fc_3db', 0):.4f},"
                     f"{r.get('il', 0):.2f},{r.get('bw', 0):.1f},"
                     f"{r.get('s11w', 0):.2f},{r.get('board_length_mm', 0):.1f},"
                     f"{r.get('score', 1e9):.4f}\n")

    warm = {**fixed, **{k: free[k][0] for k in order}}
    n = 0
    r = evaluate(topology, spec, warm, fine=False, tag_prefix=f"opt{topology.name}",
                device=device, np_ranks=np_ranks)
    n += 1; log_row(n, warm, r)
    opt.tell([warm[k] for k in order], r["score"])
    best_p, best = warm, r
    print(f"[{n}] warm-start score={r['score']:.3f} {r.get('err', '')}")

    while n < budget:
        x = opt.ask()
        p = {**fixed, **_to_dict(order, x)}
        r = evaluate(topology, spec, p, fine=False, tag_prefix=f"opt{topology.name}",
                    device=device, np_ranks=np_ranks)
        n += 1; log_row(n, p, r)
        opt.tell(x, r["score"])
        tag = "*" if r["score"] < best["score"] - 1e-4 else " "
        print(f"[{n}]{tag} {p} -> score={r['score']:.3f} (best {min(best['score'], r['score']):.3f})")
        if r["score"] < best["score"] - 1e-4:
            best_p, best = p, r

    print(f"\n=== GP SEARCH DONE after {n} evals === best(coarse)={best['score']:.3f} {best_p}")

    def _report(kind: str, r: dict) -> str:
        # A failed confirm must not take the whole run down with it: the
        # search results are the expensive part and are only persisted below.
        if not r.get("ok"):
            return f"=== {kind}: FAILED ({r.get('err')}) ==="
        return (f"=== {kind}: fc={r['fc']:.3f} s11w={r['s11w']:.2f} "
                f"bw={r['bw']:.0f} il={r['il']:.2f} score={r['score']:.3f} ===")

    fine = evaluate(topology, spec, best_p, fine=True, tag_prefix=f"opt{topology.name}",
                    device=device, np_ranks=np_ranks, fine_sweep_ghz=fine_sweep)
    print(_report("FINE confirm", fine), flush=True)

    # Fab-tolerance check: round to 0.1mm (real PCB fab resolution), re-confirm.
    rounded_p = {k: round(v, 1) for k, v in best_p.items()}
    fab = evaluate(topology, spec, rounded_p, fine=True, tag_prefix=f"opt{topology.name}fab",
                   device=device, np_ranks=np_ranks, fine_sweep_ghz=fine_sweep)
    print(_report(f"FAB-TOLERANCE (0.1mm) {rounded_p}", fab), flush=True)

    result = {"params": best_p, "coarse_score": best.get("score"),
              "metrics": {k: v for k, v in fine.items() if k not in ("csv",)},
              "fab_tolerance": {"params": rounded_p,
                                "metrics": {k: v for k, v in fab.items() if k not in ("csv",)}}}
    json.dump(result, open(best_json, "w"), indent=2, default=lambda o: o.tolist()
             if hasattr(o, "tolist") else str(o))
    return result


def plot_comparison(designs: dict[str, dict], spec: FilterSpec, out_path: str,
                    ideal_orders: tuple[int, ...] = (2, 3)) -> str:
    """S21-top/S11-bottom comparison of N designs -- the black-box pipeline's
    3rd standard artifact (docs/dualmode_cavity/results_all_variants.png's
    layout, generalized from 4 hardcoded designs to any dict of them).

    ``ideal_orders`` overlays the lossless Chebyshev target for those filter
    orders (dashed black/grey). That is the reference the optimizer actually
    scores against, so having it on the same axes shows how much of the gap to
    ideal is real loss versus a genuine shape error. Pass () to omit.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax21, ax11) = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
    colors = plt.cm.tab10.colors
    fmin = fmax = None
    for i, (label, r) in enumerate(designs.items()):
        if not r.get("ok"):
            continue
        c = colors[i % len(colors)]
        ax21.plot(r["f"], r["s21_db"], "-", color=c, lw=1.6, label=label)
        ax11.plot(r["f"], r["s11_db"], "-", color=c, lw=1.6, label=label)
        lo, hi = float(np.min(r["f"])), float(np.max(r["f"]))
        fmin = lo if fmin is None else min(fmin, lo)
        fmax = hi if fmax is None else max(fmax, hi)

    if ideal_orders and fmin is not None:
        f_id = np.linspace(fmin, fmax, 601)
        for k, N in enumerate(ideal_orders):
            ideal_spec = FilterSpec(f0=spec.f0, FBW=spec.FBW, N=N,
                                    ripple_db=spec.ripple_db,
                                    substrate_name=spec.substrate_name)
            s11_i, s21_i = ideal_target_db(ideal_spec, f_id)
            style = dict(color="k" if k == 0 else "0.45", ls="--", lw=1.3, alpha=.85)
            lbl = f"ideal N={N} Chebyshev ({spec.FBW*100:.0f}% FBW, {spec.ripple_db}dB)"
            ax21.plot(f_id, s21_i, label=lbl, **style)
            ax11.plot(f_id, s11_i, **style)

    b0, b1 = _band_ghz(spec)
    for ax in (ax21, ax11):
        ax.axvspan(b0, b1, color="green", alpha=0.08)
        ax.grid(alpha=.3)
    ax11.axhline(-16, color="grey", ls=":", lw=.9)
    ax21.set_ylabel("|S21| (dB)"); ax21.set_ylim(-40, 2)
    ax11.set_ylabel("|S11| (dB)"); ax11.set_ylim(-40, 2)
    ax11.set_xlabel("Frequency (GHz)")
    ax21.legend(loc="lower right", fontsize=7.5)
    fig.suptitle(f"Design comparison @ f0={spec.f0/1e9:.3f} GHz "
                 f"(green = design passband, dotted = -16 dB target)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"Wrote {out_path}")
    return out_path
