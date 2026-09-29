"""Generic Palace-driven optimizer: one implementation shared by every
Topology, replacing three ~200-500 line per-topology copies of the same
GP-surrogate search / CSV logging / plotting boilerplate.

Methodology:
  1. Ideal (lossless) target response for any N via synthesis.chebyshev_g /
     coupling_matrix / sparams_from_matrix.
  2. GP-surrogate (skopt) coarse search: score = curve-fit RMSE of the
     simulated |S11|,|S21| against the ideal response (S21 peak-normalized
     before fitting, so real dielectric loss never enters the shape error)
     plus direct-IL, board-length, centre-frequency and bandwidth terms --
     see score(). |S11| is clipped at S11_FLOOR_DB before the RMSE (unclipped,
     the term is dominated by how exactly a design lands the ideal's -inf-dB
     nulls rather than by whether it is well matched). Band edges come from
     band_edges()'s interpolated crossings, not the nearest sweep point.
  3. Fine-mesh, wide-frequency confirm of the coarse winner.
  4. Fab-tolerance check: round the winner to 0.1mm, re-confirm.

Mesh-quality defaults (mesh_max/mesh_min/h_air_factor) are sized to this
project's 15GB-RAM boxes with no swap; profile the full coarse sweep (memory
accumulates across frequency samples within one run, not just per-point
peak) before trusting them on a smaller machine -- search "mesh_max" here.

Driven+SMA solves default to CPU with multi-rank domain decomposition: a 6GB
GPU card OOMs past -np 1 (one CUDA context per MPI rank) and this mesh is too
big for single-rank GPU to help. Topology.calibrate() (cheap eigenmode, small
mesh) is the piece that benefits from GPU/np=1.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import subprocess

import numpy as np

from .config import FilterSpec, find_palace, has_gpu, out_data
from .synthesis import chebyshev_g, coupling_matrix, sparams_from_matrix
from .topologies.base import Topology

# ---------------------------------------------------------------------------
# Mesh-quality / device defaults.
#
# "Fine" reuses the SAME mesh as "coarse" -- only the frequency step/range
# tightens. This density is already validated as accurate; going finer buys
# no accuracy this project has needed, only OOM risk.
#
# PER-TOPOLOGY, not one global preset: cascade (N=3, 196 vias) and dualmode
# (1 cavity, 78 vias) sit at very different DOF counts for the same mesh_min
# (the accuracy-critical knob, since it resolves via/trace features and is
# not safe to coarsen). Reusing dualmode's tighter preset for cascade
# OOM-kills the fine confirm (~1M tets on a 15GB machine); don't re-tighten
# cascade's preset without re-profiling the full coarse sweep's peak RSS.
# ---------------------------------------------------------------------------
MESH_PRESETS: dict[str, tuple[float, float, float]] = {
    "cascade": (3.5, 0.6, 6.0),
    "dualmode": (1.2, 0.2, 6.0),
}
DEFAULT_MESH_PRESET = MESH_PRESETS["dualmode"]
CPU_NP = 4

# --- GPU path -------------------------------------------------------------
# GPU driven solves need this exact configuration -- changing any one of
# these reintroduces CUDA_ERROR_OUT_OF_MEMORY on a 6GB card:
#   1. MFEM_MEMORY=cuda -- disables MFEM's pooled (Umpire) device allocator,
#      which requests a fixed ~4GiB block that alone exhausts a 6GB card
#      regardless of problem size. Plain cudaMalloc allocates only what's
#      needed.
#   2. -np 1 -- one MPI rank per GPU (each rank opens its own CUDA context;
#      see run_driven's clamp).
#   3. (1.5, 0.25, 3.0), a validated dual-mode mesh, not an accuracy
#      compromise for GPU.
#
# GPU is not necessarily faster: Palace solves in FP64, and consumer NVIDIA
# cards run FP64 at 1/32 rate, so a many-core CPU can win on some hardware
# despite the GPU's memory-bandwidth edge. Benchmark before assuming.
GPU_MESH_PRESETS: dict[str, tuple[float, float, float]] = {
    "dualmode": (1.5, 0.25, 3.0),
    # The alternative cavity shapes share dualmode's mesh builder (only the
    # via layout differs) but are physically larger, so dualmode's preset
    # puts them at or over GPU_MAX_TETS. Each entry below is measured at its
    # search box's upper bound (the biggest board it can ask for) and, where
    # noted, coarsened further to fit. mesh_min=0.35 still resolves a 1.5mm
    # via barrel with ~4 cells; the fine confirm re-runs the winner on the
    # dense mesh, so the coarse mesh only has to rank designs, not measure
    # them (coarse fc is indicative only, good to ~25 MHz -- task #17).
    "corner_cut": (2.5, 0.35, 2.0),
    "circular_cross": (2.5, 0.35, 2.0),
    "rhombic": (2.5, 0.35, 2.0),
    "circular_cross_nvia": (2.5, 0.35, 2.0),
    "circular_cross_ring2": (2.5, 0.35, 2.0),
    "corner_cut_2corner": (2.5, 0.35, 2.0),
    "rhombic_2diag": (2.5, 0.35, 2.0),
    "circular_cross_taper": (2.5, 0.35, 2.0),
    "circular_cross_iris": (2.5, 0.35, 2.0),
    "dualmode_2wall": (2.5, 0.35, 2.0),
    # Two cavities in series roughly doubles tet count over the other
    # geometries here; the standard preset exceeds GPU_MAX_TETS, so these use
    # a dedicated coarser one (also used for the screen preset below -- the
    # usual coarse-vs-fine gap barely helps at this scale).
    "dualmode_cascade": (5.5, 0.8, 4.0),
    "dualmode_cascade_floatinter": (5.5, 0.8, 4.0),
    # cascade has no GPU-validated preset yet -- its CPU preset is already
    # coarser and its DOF count far higher (196 vias vs 78). Falls back to
    # the CPU preset and fails loudly rather than shipping an unvalidated one.
}
GPU_ENV = {"MFEM_MEMORY": "cuda"}

# Largest mesh the 6GB GPU completes a driven solve on: 174.6k tets finish,
# 178.4k OOMs at the error estimator; 176k sits between the two. Checked
# before solving (not just caught on failure) because a doomed GPU attempt
# still costs 40-140s of meshing/assembly, and this ceiling falls inside the
# project's search boxes often enough that skipping it wastes real time. The
# runtime fallback in run_driven still catches anything that slips through.
GPU_MAX_TETS = 176_000


def resolve_device(device: str, topology_name: str) -> str:
    """Turn a requested device ("auto"/"GPU"/"CPU") into an actual one.

    "auto" picks GPU only when a GPU exists AND this topology has a
    GPU-validated mesh preset; anything else falls back to CPU, so the same
    command works unchanged on a machine with no GPU. The margin when GPU
    wins is hardware-specific (Palace is FP64; consumer cards run FP64 at
    1/32 rate), so benchmark rather than assume it's always faster.
    """
    if device != "auto":
        return device
    if topology_name in GPU_MESH_PRESETS and has_gpu():
        return "GPU"
    return "CPU"


def _env_mesh_override() -> tuple[float, float, float] | None:
    """SIW_COARSE_MESH="max,min,h_air" overrides the GPU coarse-search preset.

    Exists so an automated speed-vs-fidelity study can hand its verdict to the
    run that follows it without editing source between the two.
    """
    raw = os.environ.get("SIW_COARSE_MESH")
    if not raw:
        return None
    try:
        mm, mn, hh = (float(v) for v in raw.split(","))
    except ValueError:
        print(f"WARNING: ignoring malformed SIW_COARSE_MESH={raw!r}")
        return None
    return mm, mn, hh


def _mesh_preset(topology_name: str, device: str = "CPU") -> tuple[float, float, float]:
    if device == "GPU":
        ov = _env_mesh_override()
        if ov is not None:
            return ov
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

    Edges are the crossings bounding the CONTIGUOUS run around the peak, not
    the first/last crossing over the whole window: when the response is
    genuinely two separated resonances (a notch drops below -3dB between
    them), bridging first-to-last would silently report both disconnected
    lobes as one wide passband instead of the real split.

    `fc_3db` (band centre) is what the score uses, not the argmax peak: on a
    double-humped response argmax picks whichever pole happens to be taller,
    which can sit an entire ripple-width off the true centre.
    """
    thr = float(s21_db.max()) - 3.0
    idx = np.flatnonzero(s21_db >= thr)
    if idx.size == 0:
        return {"bw": 0.0, "fc_3db": float(f[int(np.argmax(s21_db))]),
                "f_lo": 0.0, "f_hi": 0.0, "band_truncated": True,
                "n_lobes": 0, "lobe_split_mhz": 0.0}

    # Count the lobes too, not just measure the peak's: a split response
    # (n_lobes>1) is otherwise numerically indistinguishable from a narrow
    # one, and inverting a "bandwidth curve" built from split points seeds a
    # search at the merge threshold, where no geometry produces that width.
    _splits = np.flatnonzero(np.diff(idx) > 1)
    n_lobes = int(_splits.size) + 1
    lobe_split = 0.0
    if n_lobes > 1:
        # widest sub-threshold notch between consecutive lobes, in MHz --
        # how far the response is from merging into one passband
        gaps = [(float(f[idx[s + 1]]) - float(f[idx[s]])) * 1000.0 for s in _splits]
        lobe_split = float(max(gaps))

    def _cross(i, j):
        """f where s21 crosses thr on the segment i->j."""
        y0, y1 = float(s21_db[i]), float(s21_db[j])
        if y1 == y0:
            return float(f[j])
        return float(f[i] + (f[j] - f[i]) * (thr - y0) / (y1 - y0))

    peak_i = int(np.argmax(s21_db))          # always in idx: s21[peak_i] == max >= thr
    pos = int(np.searchsorted(idx, peak_i))
    lo = hi = pos
    while lo > 0 and idx[lo - 1] == idx[lo] - 1:
        lo -= 1
    while hi < len(idx) - 1 and idx[hi + 1] == idx[hi] + 1:
        hi += 1
    i0, i1 = int(idx[lo]), int(idx[hi])
    trunc = (i0 == 0) or (i1 == len(f) - 1)
    f_lo = _cross(i0 - 1, i0) if i0 > 0 else float(f[0])
    f_hi = _cross(i1 + 1, i1) if i1 < len(f) - 1 else float(f[-1])
    return {"bw": (f_hi - f_lo) * 1000.0, "fc_3db": 0.5 * (f_lo + f_hi),
            "f_lo": f_lo, "f_hi": f_hi, "band_truncated": trunc,
            "n_lobes": n_lobes, "lobe_split_mhz": lobe_split}


def pole_shape(f: np.ndarray, s11_db: np.ndarray, n_expected: int,
              zero_thresh_db: float = -8.0, peak_max_db: float = -1.0) -> dict:
    """Count S11 reflection zeros and in-band ripple peaks and compare against
    the order the design is SUPPOSED to be.

    A Chebyshev bandpass of order N has exactly N reflection zeros (S11 dips)
    and N-1 ripple peaks between them. This is the acceptance check the score
    alone does not give you: `score()` and `s11w` can both look reasonable on
    a response that is structurally the wrong order (2 zeros/1 peak reported
    as an "N=3" design -- the missing-middle-resonator bug -- or the reverse,
    extra structure reading as a higher order than what was actually
    synthesized). Always check this before trusting a fine-confirm's numbers.

    Zeros: local minima of S11 below `zero_thresh_db`. Peaks: local maxima of
    S11 between two zeros, below `peak_max_db` (so a maximum that never really
    dips back down between two supposed poles -- i.e. two poles that merged
    into one -- doesn't get counted as a separating ripple).
    """
    zeros_idx = [i for i in range(1, len(s11_db) - 1)
                if s11_db[i] < s11_db[i - 1] and s11_db[i] < s11_db[i + 1]
                and s11_db[i] < zero_thresh_db]
    peaks_idx = [i for i in range(1, len(s11_db) - 1)
                if s11_db[i] > s11_db[i - 1] and s11_db[i] > s11_db[i + 1]
                and s11_db[i] < peak_max_db]
    n_zeros, n_peaks = len(zeros_idx), len(peaks_idx)
    return {"n_zeros": n_zeros, "n_peaks": n_peaks,
            "zeros_ghz": [float(f[i]) for i in zeros_idx],
            "matches_order": (n_zeros == n_expected and n_peaks == max(0, n_expected - 1)),
            "n_expected": n_expected}


#: Krylov solve tolerance for the COARSE search. Palace/MFEM is FP64-only, so
#: the "cheaper but less exact" knob is solver tolerance (fewer GMRES
#: iterations), not float width -- and it doesn't buy memory, since GPU
#: footprint is set by DOF count, not tolerance. Measured against a 1e-8
#: reference: 1e-5 moves the score by <0.004 (two orders below the spacing
#: between competing designs) while most of the time cost is meshing/
#: assembly, not Krylov iterations, so looser tolerances buy little speed --
#: 1e-5 takes nearly all the available gain with an order of magnitude more
#: margin than 1e-4.
COARSE_TOL = 1e-5
FINE_TOL = 1e-8


def _driven_config(mesh: str, res: dict, spec: FilterSpec, tag: str,
                   fmin: float, fmax: float, step: float, device: str,
                   tol: float = FINE_TOL, port_mode: int = 1) -> dict:
    """Build the Palace Driven-problem config for any topology's build_mesh()
    result -- generic over with_sma True/False (3rd material + WavePort
    voltage paths only appear when res['sma'] is set).

    `port_mode` picks the wave-port eigenmode (Palace orders them by
    propagation constant). A connector-less CPWG port face has four
    conductors, and modes 1-2 are the wide ground pours against the bottom
    plane, not the signal trace -- the CPWG mode there is 3."""
    sma = res.get("sma")
    materials = [
        {"Attributes": [1], "Permeability": 1.0,
         "Permittivity": res.get("eps_r", spec.substrate.eps_r),
         "LossTan": res.get("tand", spec.substrate.tan_d)},
        {"Attributes": [2], "Permeability": 1.0, "Permittivity": 1.0, "LossTan": 0.0},
    ]
    port_in = {"Index": 1, "Attributes": [11], "Mode": port_mode, "Excitation": 1,
               "Offset": 0.0, "MaxIts": 40, "KSPTol": tol, "EigenTol": 1e-6}
    port_out = {"Index": 2, "Attributes": [12], "Mode": port_mode,
                "Offset": 0.0, "MaxIts": 40, "KSPTol": tol, "EigenTol": 1e-6}
    if sma:
        materials.append({"Attributes": [3], "Permeability": 1.0,
                          "Permittivity": sma["eps_r"], "LossTan": sma["tand"]})
        port_in["VoltagePath"] = sma["voltage_path_in"]
        port_out["VoltagePath"] = sma["voltage_path_out"]
    mask = res.get("soldermask")
    if mask:
        materials.append({"Attributes": [4], "Permeability": 1.0,
                          "Permittivity": mask["eps_r"], "LossTan": mask["tand"]})
    silk = res.get("silkscreen")
    if silk:
        materials.append({"Attributes": [7], "Permeability": 1.0,
                          "Permittivity": silk["eps_r"], "LossTan": silk["tand"]})
    enig = res.get("enig")
    if enig:
        # Real volumetric conductor (Ohmic loss), not the exterior-only
        # Boundaries.Conductivity surface BC (that one only applies to true
        # one-sided exterior faces; a material domain has no such
        # restriction, since its interfaces are handled by field continuity).
        materials.append({"Attributes": [5], "Permeability": enig["mu_r"],
                          "Permittivity": 1.0, "Conductivity": enig["conductivity_sm"]})
    metal_real = res.get("metal_real")
    via_cond = res.get("via_conductivity")
    if via_cond:
        # Real volumetric conductor: a via wall is an internal two-sided
        # sheet, where Boundaries.Conductivity (exterior-only) does not
        # apply. Filled/solid vs unfilled/hollow-plated is therefore a real
        # GEOMETRY difference (built in palace_dualmode_driven.py), not a
        # Thickness parameter on a boundary condition.
        materials.append({"Attributes": [6], "Permeability": via_cond["mu_r"],
                          "Permittivity": 1.0, "Conductivity": via_cond["conductivity_sm"]})
    boundaries = {"PEC": {"Attributes": [10]},
                  "Absorbing": {"Attributes": [13], "Order": 1},
                  "WavePort": [port_in, port_out]}
    if metal_real:
        # Real copper surface impedance on the EXTERIOR ground planes (valid
        # here -- they are true one-sided exterior boundaries, unlike the via
        # barrels). Captures the conductor loss every PEC-only golden omits.
        mb = {"Attributes": [15], "Conductivity": metal_real["conductivity_sm"]}
        if metal_real.get("thickness_um"):
            mb["Thickness"] = metal_real["thickness_um"] * 1e-3   # um -> mm (L0=1mm)
        boundaries.setdefault("Conductivity", []).append(mb)
    # Every DOMAIN physical group in the mesh must have a material here, or
    # its faces get no boundary condition and Palace silently produces
    # impossible results (e.g. insertion loss better than lossless PEC)
    # instead of an error. Fail loudly instead.
    legend = res.get("legend") or {}
    DOMAIN_TAGS = {"dielectric": 1, "air": 2, "sma_ptfe": 3, "soldermask": 4,
                   "enig": 5, "via_conductor": 6, "silkscreen": 7}
    meshed = {t for name, t in legend.items() if DOMAIN_TAGS.get(name) == t}
    covered = {a for m in materials for a in m["Attributes"]}
    missing = meshed - covered
    if missing:
        names = [n for n, t in legend.items() if t in missing]
        raise RuntimeError(
            f"mesh domains {sorted(missing)} ({names}) have no material in the "
            f"Palace config -- wire them into _driven_config()")

    return {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": materials},
        "Boundaries": boundaries,
        "Solver": {"Order": 1, "Device": device,
                   "Driven": {"Samples": [{"Type": "Linear", "MinFreq": fmin,
                                           "MaxFreq": fmax, "FreqStep": step}]},
                   "Linear": {"Type": "Default", "KSPType": "GMRES",
                              "Tol": tol, "MaxIts": 300}},
    }


@contextlib.contextmanager
def _palace_lock():
    """Real, atomic cross-process mutex around one Palace invocation.

    A pgrep-based poll (what this replaced) is not a lock: two independent
    processes can both observe "nothing running" in the same gap and launch
    together, briefly sharing the one 6GB GPU -- exactly the situation an
    ad-hoc wideband sanity sweep run alongside the main optimizer creates
    (both call run_driven independently). fcntl.flock on a shared file is a
    real kernel-level mutex: the second caller BLOCKS in the open syscall
    until the first releases it, with no polling gap to race through."""
    lock_path = out_data(".palace.lock")
    with open(lock_path, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def run_driven(topology: Topology, spec: FilterSpec, params: dict, tag: str,
               fmin: float, fmax: float, step: float,
               mesh_max: float, mesh_min: float, h_air_factor: float,
               device: str = "auto", np_ranks: int = CPU_NP,
               serialize: bool = True, tol: float = FINE_TOL,
               port_mode: int = 1) -> dict:
    """Build the mesh + run one Palace Driven solve, return {ok, f, s11_db,
    s21_db, fc, il, bw, s11w, il_band, tag} (dB arrays over the swept band)."""
    device = resolve_device(device, topology.name)
    if device == "GPU" and np_ranks != 1:
        # Each MPI rank opens its own CUDA context on the same physical GPU;
        # with only one GPU here, >1 rank reliably OOMs. Clamp centrally
        # rather than rely on every caller to remember this.
        print(f"[{tag}] GPU requested with np_ranks={np_ranks} -> forcing np_ranks=1 "
              f"(multi-rank GPU OOMs on a single card)")
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

    # Palace emits samples from fmin while <= fmax: floor(span/step)+1, not
    # round(), or a span that isn't an exact multiple of step over-counts by
    # one and flags a complete sweep as truncated. 1e-9 guards an exact
    # multiple landing just under it in floating point.
    n_expected = int(np.floor((fmax - fmin) / step + 1e-9)) + 1
    palace = find_palace()

    def _solve(dev: str, ranks: int):
        """One Palace invocation. Returns (arrays | None, err | None)."""
        cfg = _driven_config(mesh, res, spec, tag, fmin, fmax, step, dev, tol,
                             port_mode)
        cfgp = out_data(f"{tag}.json")
        json.dump(cfg, open(cfgp, "w"), indent=2)
        env = dict(os.environ, PATH=f"{os.path.dirname(palace)}:{os.environ['PATH']}")
        if dev == "GPU":
            # See GPU_ENV: disables MFEM's pooled (Umpire) device allocator,
            # whose fixed ~4GiB block request exhausts a 6GB card on its own.
            env.update(GPU_ENV)
        logp = out_data(f"{tag}.log")
        # Stale results from a previous attempt would look like a success.
        shutil.rmtree(out_data(f"postpro/{tag}"), ignore_errors=True)
        # Guards only the Palace invocation itself (see _palace_lock); meshing
        # and config-writing above still overlap freely across processes,
        # which is fine since gmsh is cheap and single-threaded per call.
        if serialize:
            with _palace_lock():
                subprocess.run([palace, "-np", str(ranks), os.path.basename(cfgp)],
                               cwd=out_data(""), env=env, stdout=open(logp, "w"),
                               stderr=subprocess.STDOUT, check=False)
        else:
            subprocess.run([palace, "-np", str(ranks), os.path.basename(cfgp)],
                           cwd=out_data(""), env=env, stdout=open(logp, "w"),
                           stderr=subprocess.STDOUT, check=False)
        csvp = out_data(f"postpro/{tag}/port-S.csv")
        if not os.path.exists(csvp):
            return None, "no csv"
        dd = np.genfromtxt(csvp, delimiter=",", names=True, deletechars="", replace_space="")
        nmm = dd.dtype.names
        ff = np.atleast_1d(dd[nmm[0]])
        # Palace writes port-S.csv incrementally, so a run that dies partway
        # (e.g. GPU OOM at the error estimator) leaves a valid-looking but
        # truncated file, which would otherwise be silently scored as complete.
        if len(ff) < n_expected:
            return None, f"incomplete sweep: {len(ff)}/{n_expected} points (see {logp})"
        return (ff, np.atleast_1d(dd[nmm[1]]), np.atleast_1d(dd[nmm[3]])), None

    got, err = _solve(device, np_ranks)
    if got is None and device == "GPU":
        # The GPU memory ceiling falls inside this project's search boxes --
        # the same sweep can succeed for a small cavity and OOM for a large
        # one -- so a GPU-only run would silently lose whichever points
        # happen to be big. Falling back per-eval keeps GPU's speed where it
        # fits without dropping points where it doesn't.
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


#: No fc penalty inside this deadband: fc is not mesh-converged in this
#: project (the same design shifts 20-27 MHz between mesh densities, task
#: #17), so a deadband charges only for error the mesh study can't explain
#: away. Shrink once #17 pins the convergence down.
FC_DEADBAND_MHZ = 15.0


#: Worst-case in-band return loss target. Treated as a hinge, not a hard
#: gate, so the optimizer is guided by how far short it falls rather than
#: only pass/fail.
S11_SPEC_DB = -16.0

#: Allowed insertion loss above the pure-dielectric floor. dielectric_il_db()
#: is an optimistic lower bound (ignores conductor/via/radiation loss, which
#: measured 2.65-3.84x higher on real designs), so this turns that floor into
#: a usable target: "the dielectric loss and a little bit more".
IL_ALLOWANCE_DB = 1.0

#: Weights for the three spec terms. Chosen so a design missing S11 by ~5 dB,
#: or IL by ~2 dB, or badly lopsided, pays a penalty comparable to a large
#: shape-fit error -- enough to steer the search, not so much that it ignores
#: the curve shape entirely.
W_S11_SPEC = 0.8
W_IL_SPEC = 1.5
W_ASYM = 8.0


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
    # A passband wider than the sweep has no measurable edges: band_edges
    # then returns the window's own centre and width, not the design's, so a
    # truncated design would report fc_3db ~ f0 and collect zero frequency
    # penalty however far off it actually sits. Fall back to the peak, still
    # a real measurement, whenever that happens.
    fc_mhz = (r["fc"] if r.get("band_truncated") else
              r.get("fc_3db", r["fc"])) * 1000.0
    fc_err = max(0.0, abs(fc_mhz - f0_mhz) - fc_deadband_mhz)

    bw_target = spec.FBW * f0_mhz
    bw_err = abs(r["bw"] - bw_target) / bw_target if bw_target > 0 else 0.0

    # --- spec terms, separate from the FIT terms above -----------------
    # An RMSE-against-ideal-curve fit does not directly enforce what the
    # design is actually judged on, so a design could win on average shape
    # while failing every one of: (1) worst-case in-band S11 <= -16 dB,
    # (2) IL no worse than the dielectric floor plus a modest allowance,
    # (3) a symmetric response. All three are one-sided hinges (zero cost
    # once met), scaled to be comparable to the ~1-20 range of the RMSE terms.
    s11_spec = max(0.0, r["s11w"] - S11_SPEC_DB)          # s11w is the in-band WORST
    il_floor = dielectric_il_db(spec)
    il_spec = max(0.0, abs(r["il"]) - (il_floor + IL_ALLOWANCE_DB))

    # Symmetry: compare how far the -3dB edges sit from the peak on each
    # side. fc_pk must estimate the true passband centre INDEPENDENTLY of
    # f_lo/f_hi -- fc_3db is their midpoint by construction, so using it here
    # would make this term identically zero, not a fix. argmax(S21) is
    # independent but unstable on a multi-pole response (it hops between
    # whichever ripple peak the sweep grid happens to sample as tallest); the
    # mean of the S11 reflection zeros is independent of f_lo/f_hi and, being
    # an average over N points, is far less sensitive to grid placement.
    f_lo, f_hi = r.get("f_lo"), r.get("f_hi")
    zeros_ghz = pole_shape(r["f"], r["s11_db"], spec.N)["zeros_ghz"]
    fc_pk = (sum(zeros_ghz) / len(zeros_ghz)) if zeros_ghz else r.get("fc")
    if f_lo and f_hi and fc_pk and not r.get("band_truncated"):
        lo_arm, hi_arm = fc_pk - f_lo, f_hi - fc_pk
        denom = max(1e-9, lo_arm + hi_arm)
        asym = abs(hi_arm - lo_arm) / denom      # 0 = perfectly symmetric
    else:
        asym = 0.0

    return (1.0 * s11_rmse + 0.5 * s21_rmse + 0.15 * abs(r["il"])
           + w_fc * fc_err + w_bw * bw_err
           + w_board * board_length_mm
           + W_S11_SPEC * s11_spec + W_IL_SPEC * il_spec + W_ASYM * asym)


def _to_dict(order: list[str], x: list[float]) -> dict:
    return {k: round(float(v), 3) for k, v in zip(order, x)}


#: Ultra-coarse mesh for the f0-only screen -- deliberately coarser than the
#: coarse SEARCH mesh: meshing/assembly, not per-frequency solves, dominates
#: an eval's cost, so a single-frequency solve on the search mesh would
#: roughly double the time for every design that passes. Screening only pays
#: for itself if it is cheap even when a design passes.
#: h_air_factor=3.0, not 1.5: too-thin an air box interacts badly with the
#: absorbing boundary and introduces a systematic ~1.4dB error in peak S21,
#: enough to reject a good design on a meshing artefact.
SCREEN_MESH_PRESETS: dict[str, tuple[float, float, float]] = {
    "dualmode": (3.5, 0.5, 3.0),
    "corner_cut": (3.5, 0.5, 3.0),
    "circular_cross": (3.5, 0.5, 3.0),
    "rhombic": (3.5, 0.5, 3.0),
    "circular_cross_nvia": (3.5, 0.5, 3.0),
    "circular_cross_ring2": (3.5, 0.5, 3.0),
    "corner_cut_2corner": (3.5, 0.5, 3.0),
    "rhombic_2diag": (3.5, 0.5, 3.0),
    "circular_cross_taper": (3.5, 0.5, 3.0),
    "circular_cross_iris": (3.5, 0.5, 3.0),
    "dualmode_2wall": (3.5, 0.5, 3.0),
    "dualmode_cascade": (5.5, 0.8, 4.0),
    "dualmode_cascade_floatinter": (5.5, 0.8, 4.0),
}
SCREEN_TOL = 1e-4          # pass/fail only -- see COARSE_TOL's accuracy note
S11_SCREEN_DB = -10.0      # reject anything worse than this
#: S21 floor in THIS SCREEN MESH'S OWN units, not the dense-mesh dielectric
#: floor scaled by a multiplier (the screen mesh does not measure true IL, so
#: that scaling is the wrong space to threshold in). Calibrated instead
#: against what the screen mesh itself reports for known designs, with
#: several dB of margin above real working designs and far below a
#: deliberately broken one -- loose enough that an imperfectly tuned but
#: real design is not rejected outright; refining imperfect starts is the
#: search's job, not the screen's.
S21_SCREEN_FLOOR_DB = -6.0
#: Screen over a short WINDOW around f0, not a single point at it: a
#: multi-pole response can have a genuine dip near f0 between its poles, and
#: a design mid-search is routinely tens of MHz off-centre by intent, so a
#: single point conflates "not centred yet" with "bad". The best point across
#: a few samples answers "is there a usable resonance near where we want
#: one" without that false-reject risk, and costs little extra since solve
#: cost is dominated by meshing/assembly, shared across all the points.
SCREEN_WINDOW_FBW_MULT = 1.5   # same half-width as _fit_window_ghz
#: Frequency STEP, not a fixed point count: too few points can straddle a
#: narrow two-pole passband without ever landing near a peak. 20 MHz matches
#: the coarse search's own resolution and is affordable because the screen
#: mesh is coarser than the search mesh.
SCREEN_STEP_GHZ = 0.02


def dielectric_il_db(spec: FilterSpec) -> float:
    """Theoretical midband insertion loss from DIELECTRIC loss alone (Hong &
    Lancaster's coupled-resonator loss formula, IL_dB = 4.343*sum(g_i)/(FBW*Qu)
    with Qu = 1/tan_d). Conductor/via/leakage loss is ignored, so this is an
    OPTIMISTIC floor -- a real SIW design costs several times over (measured
    this session: 2.65x-3.84x for the four working geometries).

    NOT used to set the screen's threshold (S21_SCREEN_FLOOR_DB is calibrated
    directly against the screen mesh's own readings instead -- see that
    constant's docstring for why: the screen mesh does not measure true IL,
    so scaling a true-IL-space number was the wrong space to threshold in).
    Kept as a reference/reporting figure and for anyone re-deriving the floor
    with a different substrate or filter order.
    """
    g = chebyshev_g(spec.N, spec.ripple_db)
    return 4.343 * float(np.sum(g[1:spec.N + 1])) * spec.substrate.tan_d / spec.FBW


def screen_at_f0(topology: Topology, spec: FilterSpec, params: dict, tag: str,
                 device: str = "auto", np_ranks: int = CPU_NP) -> dict:
    """Cheap, ultra-coarse-mesh pass/fail check over a short window around f0,
    before spending a full coarse sweep on a design that cannot possibly work.

    Rejects if the best S11 anywhere in the window is worse than
    S11_SCREEN_DB, or the best S21 is worse than S21_SCREEN_FLOOR_DB. "Best
    anywhere in a window" (see SCREEN_WINDOW_FBW_MULT) gives a mistuned or
    double-humped design every chance to show a usable point.
    """
    mmax, mmin, hair = SCREEN_MESH_PRESETS.get(
        topology.name, _mesh_preset(topology.name, "GPU"))
    fw0, fw1 = _fit_window_ghz(spec)
    half = SCREEN_WINDOW_FBW_MULT * (fw1 - fw0) / 2.0
    f0 = spec.f0 / 1e9
    fmin, fmax = f0 - half, f0 + half
    r = run_driven(topology, spec, params, tag, fmin, fmax, SCREEN_STEP_GHZ,
                   mmax, mmin, hair,
                   device=device, np_ranks=np_ranks, tol=SCREEN_TOL)
    if not r.get("ok"):
        return {"pass": False, "err": r.get("err"), "s11_best": None, "s21_best": None}
    s11_best, s21_best = float(np.min(r["s11_db"])), float(np.max(r["s21_db"]))
    il_thresh = S21_SCREEN_FLOOR_DB
    ok = (s11_best <= S11_SCREEN_DB) and (s21_best >= il_thresh)
    return {"pass": ok, "s11_best": s11_best, "s21_best": s21_best,
           "il_thresh": il_thresh, "device": r.get("device")}


def evaluate(topology: Topology, spec: FilterSpec, params: dict, fine: bool = False,
            tag_prefix: str = "opt", device: str = "auto", np_ranks: int = CPU_NP,
            fine_sweep_ghz: tuple[float, float, float] | None = None,
            screen: bool = True, score_kwargs: dict | None = None) -> dict:
    device = resolve_device(device, topology.name)
    fw0, fw1 = _fit_window_ghz(spec)
    # The fine CONFIRM always uses the denser CPU-grade mesh regardless of
    # device: confirming the winner on the same coarse mesh that selected it
    # would just re-report the search's own numbers, when the point of the
    # confirm is to check the design survives a better discretization.
    mmax, mmin, hair = (_cpu_mesh_preset(topology.name) if fine
                        else _mesh_preset(topology.name, device))
    tol = FINE_TOL if fine else COARSE_TOL
    if fine:
        if fine_sweep_ghz is not None:
            fmin, fmax, step = fine_sweep_ghz
        else:
            fmin, fmax, step = fw0 - 1.0 * (fw1 - fw0), fw1 + 1.0 * (fw1 - fw0), 0.01
    else:
        # +-0.9 of the fit window, not a narrower one: designs in this
        # project run 310-340 MHz wide, and a window too close to that would
        # fill entirely, so the -3dB edges never get captured -- bandwidth
        # then reads as the window width and centre frequency as the
        # window's own midpoint, measuring the sweep instead of the filter.
        # SIW_COARSE_STEP lets an external speed-vs-fidelity study hand its
        # verdict to the run that follows without editing source.
        try:
            cstep = float(os.environ.get("SIW_COARSE_STEP", "") or 0.02)
        except ValueError:
            cstep = 0.02
        fmin, fmax, step = fw0 - 0.9 * (fw1 - fw0), fw1 + 0.9 * (fw1 - fw0), cstep
    # Only NUMERIC params go in the tag. Params also carry non-dimensional
    # conditions -- material flags, and now a launch name -- and formatting
    # those with :.2f raises (None) or is meaningless (a string). The tag is
    # a filename describing the GEOMETRY; conditions are recorded in the
    # result JSON. Callers comparing two conditions at one geometry must use
    # distinct tag_prefixes, or the two runs collide on disk.
    tag = (f"{tag_prefix}F_" if fine else f"{tag_prefix}_") + "_".join(
        f"{k}{v:.2f}" for k, v in sorted(params.items())
        if isinstance(v, (int, float)) and not isinstance(v, bool))
    # This tag becomes a filename directly and gains prefixes/suffixes
    # downstream, so a wide param dict can push it past ext4's 255-byte
    # filename limit -- which fails silently as a bare "mesh:Unable to open
    # file" screen-out, indistinguishable from a real rejection. Collapse to
    # a short stable hash before that ceiling; 120 leaves headroom.
    if len(tag) > 120:
        import hashlib
        digest = hashlib.sha1(tag.encode()).hexdigest()[:12]
        tag = (f"{tag_prefix}F_" if fine else f"{tag_prefix}_") + digest
    board_len = topology.board_length_mm(spec, **params)

    # Screen only the COARSE search, never the fine confirm -- the confirm's
    # whole purpose is to re-check a design the screen and the coarse search
    # already approved, on a mesh dense enough that the screen's own coarser
    # mesh would be the wrong tool for the job.
    if screen and not fine:
        s = screen_at_f0(topology, spec, params, f"scr_{tag}", device=device,
                         np_ranks=np_ranks)
        if not s["pass"]:
            s11b, s21b = s.get("s11_best"), s.get("s21_best")
            if s11b is None or s21b is None:
                fail_score = 1e9   # no real measurement (mesh/solver failure) -- no gradient
            else:
                # Graded rejection: still always worse than any passing score,
                # but with real spread so a GP surrogate has a gradient to
                # climb inside the failed region instead of every screened-out
                # candidate tying at exactly the same value.
                margin_s11 = max(0.0, s11b - S11_SCREEN_DB)
                margin_s21 = max(0.0, S21_SCREEN_FLOOR_DB - s21b)
                fail_score = 1e6 + margin_s11 * 100.0 + margin_s21 * 100.0
            return {"ok": False, "err": f"screened out: {s.get('err') or s}",
                   "screened": True, "score": fail_score, "board_length_mm": board_len,
                   "s11_screen": s11b, "s21_screen": s21b}

    r = run_driven(topology, spec, params, tag, fmin, fmax, step, mmax, mmin, hair,
                   device=device, np_ranks=np_ranks, tol=tol)
    r["score"] = score(spec, r, board_len, **(score_kwargs or {}))
    r["board_length_mm"] = board_len
    return r


def optimize(topology: Topology, spec: FilterSpec, budget: int = 18,
            n_initial: int | None = None,
            fine_sweep: tuple[float, float, float] | None = None,
            device: str = "auto", np_ranks: int = CPU_NP,
            log_name: str | None = None, best_json_name: str | None = None,
            patience: int | None = None, score_kwargs: dict | None = None) -> dict:
    """GP-surrogate coarse search over topology.param_space(spec), fine-mesh
    confirm of the winner, fab-tolerance (0.1mm rounding) check. Returns the
    fine-confirmed best {params, metrics}.

    patience: stop the coarse search early once this many consecutive evals
    pass with no improvement over the running best, rather than spending the
    remaining budget confirming a plateau. None (default) runs the full
    budget."""
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
    # Random-sampling phase before the GP starts exploiting. A fixed default
    # would silently turn a small budget into near-pure random search, so
    # this scales with the budget while keeping enough seeds to fit a
    # surrogate over this dimensionality.
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
    n_screened = 0
    r = evaluate(topology, spec, warm, fine=False, tag_prefix=f"opt{topology.name}",
                device=device, np_ranks=np_ranks, score_kwargs=score_kwargs)
    n += 1; log_row(n, warm, r)
    opt.tell([warm[k] for k in order], r["score"])
    best_p, best = warm, r
    print(f"[{n}] warm-start score={r['score']:.3f} {r.get('err', '')}")
    since_improve = 0

    while n < budget:
        x = opt.ask()
        p = {**fixed, **_to_dict(order, x)}
        r = evaluate(topology, spec, p, fine=False, tag_prefix=f"opt{topology.name}",
                    device=device, np_ranks=np_ranks, score_kwargs=score_kwargs)
        n += 1; log_row(n, p, r)
        opt.tell(x, r["score"])
        tag = "*" if r["score"] < best["score"] - 1e-4 else " "
        scr = " [screened]" if r.get("screened") else ""
        print(f"[{n}]{tag} {p} -> score={r['score']:.3f} "
              f"(best {min(best['score'], r['score']):.3f}){scr}")
        if r.get("screened"):
            n_screened += 1
        if r["score"] < best["score"] - 1e-4:
            best_p, best = p, r
            since_improve = 0
        else:
            since_improve += 1
        if patience is not None and since_improve >= patience:
            print(f"\n=== early stop: {since_improve} evals with no improvement "
                  f"(patience={patience}) ===", flush=True)
            break

    print(f"\n=== GP SEARCH DONE after {n} evals ({n_screened} screened out before a "
          f"full sweep) === best(coarse)={best['score']:.3f} {best_p}")

    def _report(kind: str, r: dict) -> str:
        # A failed confirm must not take the whole run down with it: the
        # search results are the expensive part and are only persisted below.
        if not r.get("ok"):
            return f"=== {kind}: FAILED ({r.get('err')}) ==="
        return (f"=== {kind}: fc={r['fc']:.3f} s11w={r['s11w']:.2f} "
                f"bw={r['bw']:.0f} il={r['il']:.2f} score={r['score']:.3f} ===")

    fine = evaluate(topology, spec, best_p, fine=True, tag_prefix=f"opt{topology.name}",
                    device=device, np_ranks=np_ranks, fine_sweep_ghz=fine_sweep,
                    score_kwargs=score_kwargs)
    print(_report("FINE confirm", fine), flush=True)

    # Fab-tolerance check: round to 0.1mm (real PCB fab resolution), re-confirm.
    rounded_p = {k: round(v, 1) for k, v in best_p.items()}
    fab = evaluate(topology, spec, rounded_p, fine=True, tag_prefix=f"opt{topology.name}fab",
                   device=device, np_ranks=np_ranks, fine_sweep_ghz=fine_sweep,
                   score_kwargs=score_kwargs)
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
    """S21-top/S11-bottom comparison of N designs -- one of the black-box
    pipeline's standard artifacts, for any dict of named results.

    ``ideal_orders`` overlays the lossless Chebyshev target for those filter
    orders (dashed black/grey) -- the reference the optimizer actually scores
    against, so the same axes show how much of the gap to ideal is real loss
    versus a genuine shape error. Pass () to omit.
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


def fixed_extras(topology, extras: dict):
    """Wrap a Topology so every build_mesh call carries `extras` (e.g. the
    fabrication stack). Keeps the optimizer's search box untouched -- these
    are fixed conditions, not search dimensions -- so a design searched under
    PEC and one searched under the real stack remain directly comparable."""
    class _Fixed:
        name = topology.name
        poles_per_cavity = getattr(topology, "poles_per_cavity", 1)

        def param_space(self, spec):
            return topology.param_space(spec)

        def build_mesh(self, spec, out_name, **params):
            merged = dict(extras); merged.update(params)
            return topology.build_mesh(spec, out_name, **merged)

        def plot_layout_2d(self, spec, path, **params):
            return topology.plot_layout_2d(spec, path, **params)

        def board_length_mm(self, spec, **params):
            return topology.board_length_mm(spec, **params)

        def calibrate(self, spec, **kw):
            return topology.calibrate(spec, **kw)

    return _Fixed()


def local_topology(topology: Topology, seed: dict[str, float],
                   spans: dict[str, float] | None = None,
                   default_span: float = 2.5,
                   floors: dict[str, float] | None = None):
    """Wrap `topology` so its param_space becomes a TIGHT box around `seed`.

    Turns a global Bayesian search into a local polish. This matters because
    the assembled filter's passband width is DISCONTINUOUS in the external
    coupling (below a threshold only the centre pole clears -3dB so the band
    measures one pole; above it all N poles merge and the band jumps) --
    GPs model smooth functions, so a global search over that objective
    doesn't converge. Around a physics-derived seed the surface is locally
    smooth and the same optimizer works.

    Parameters whose seed value is absent keep the parent's own range, and
    any parameter the parent pins (lo == hi, e.g. w_ms at the true 50-ohm
    width) stays pinned -- letting w_ms float re-creates a self-normalising-
    port artefact where the trace is tuned against the port instead of a
    real impedance.
    """
    spans = spans or {}
    floors = floors or {}
    parent = topology

    class _Local:
        name = parent.name
        poles_per_cavity = getattr(parent, "poles_per_cavity", 1)

        def param_space(self, spec):
            base = parent.param_space(spec)
            out = {}
            for k, rng in base.items():
                init, lo, hi = rng
                if lo >= hi or k not in seed:      # pinned, or not seeded
                    out[k] = rng
                    continue
                v = float(seed[k])
                s = float(spans.get(k, default_span))
                out[k] = (v, max(floors.get(k, lo), v - s), min(hi, v + s)) \
                    if hi > lo else rng
                # keep the box non-degenerate even if the seed sits on a bound
                if out[k][1] >= out[k][2]:
                    out[k] = (v, v - s, v + s)
            return out

        def __getattr__(self, item):
            return getattr(parent, item)

    return _Local()
