"""EM calibration of the SIW coupling structures (CLAUDE.md sec. 6).

This is the numerically critical step: closed-form iris formulas for SIW are
unreliable, so we extract the coupling from openEMS and fit it.

  k  <- iris width:  simulate two coupled SIW cavities, sweep iris width w,
        extract the split eigenmode pair (f1, f2) from the weak-coupling
        transmission, compute k = (f2^2 - f1^2)/(f2^2 + f1^2), fit w(k).

  Qe <- taper:       single cavity fed by the microstrip taper, extract Qe from
        the S11 group delay at resonance:  Qe = omega0 * tau(omega0) / 4.

Results are cached to calibration.json keyed by (substrate, d_via, p_via) so
they are reused. siw_geometry.py can then read the fits to pick physical
dimensions from the synthesized k / Qe.

NOTE: each FDTD point is minutes of compute; a full sweep is long. Use
--build-only to validate the model cheaply first. Set
LD_LIBRARY_PATH=$HOME/opt/openEMS/lib before running.

Run:  uv run python calibrate.py --sweep         # k(w) sweep
      uv run python calibrate.py --qe            # external Q
      uv run python calibrate.py --build-only    # cheap model check
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass

import numpy as np

from CSXCAD import ContinuousStructure
from openEMS import openEMS

from .config import SPEC, FilterSpec, out_data, out_img
from .siw_geometry import Geometry, build_geometry, _dedupe_vias
from . import openems_sim as oe

# Absolute path: openEMS.Run() chdir's into the sim directory, so a relative
# path would otherwise be written there instead of the project output dir.
CACHE = out_data("calibration.json")


def _clean_lines(lines, min_gap: float) -> list[float]:
    """Sort mesh lines and drop any closer than ``min_gap`` to the previous kept
    line (prevents degenerate sub-micron cells that crater the timestep)."""
    out: list[float] = []
    for v in sorted(lines):
        if not out or v - out[-1] >= min_gap:
            out.append(v)
    return out


def _cache_key(spec: FilterSpec) -> str:
    return (f"{spec.substrate_name}_d{spec.d_via*1e3:.2f}_p{spec.p_via*1e3:.2f}"
            f"_f{spec.f0/1e9:.3f}")


# ---------------------------------------------------------------------------
# Two-cavity model for k extraction
# ---------------------------------------------------------------------------
def _two_cavity_vias(g: Geometry, iris_w: float) -> list[tuple[float, float]]:
    """Build the via list for two cavities of length L_cav sharing one iris wall.

    Outer ends are CLOSED via walls (no gap); the centre wall has a gap=iris_w.
    """
    spec = g.spec
    p = spec.p_via
    half = g.a_siw / 2.0
    L = g.L_cav
    Ltot = 2 * L

    # side columns: even count so the centre wall lands on a column
    n_side = max(2, 2 * round(Ltot / p / 2))
    xs = np.linspace(0.0, Ltot, n_side + 1)
    col_mid = n_side // 2

    vias: list[tuple[float, float]] = []
    for x in xs:
        vias.append((x, +half))
        vias.append((x, -half))

    n_trans = int(round(g.a_siw / p))
    y_grid = np.linspace(-half, half, n_trans + 1)
    # transverse walls: index 0 (closed), col_mid (iris), n_side (closed)
    for col, gap in ((0, 0.0), (col_mid, iris_w), (n_side, 0.0)):
        x_wall = xs[col]
        for y in y_grid:
            if abs(y) > gap / 2.0:
                vias.append((x_wall, y))
    return _dedupe_vias(vias, min_sep=0.9 * spec.d_via)


def build_two_cavity(g: Geometry, iris_w: float, res_factor: float = 18.0,
                     couple_inset: float = 0.18):
    """CSX + FDTD for two weakly-probed coupled cavities. Returns (fdtd, ports)."""
    spec = g.spec
    # wide Gaussian (short time pulse) centred at f0; peaks are read out later
    # over the narrow band. end_criteria 1e-4 for a first pass (speed).
    fdtd = oe.make_fdtd(spec.f0, 0.5 * spec.f0, end_criteria=1e-4)
    # fully enclosed cavity -> boundaries irrelevant; PEC bottom, MUR elsewhere
    fdtd.SetBoundaryCond(["MUR", "MUR", "MUR", "MUR", "PEC", "MUR"])
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)

    h = oe._m(spec.substrate.h)
    radius = oe._m(spec.d_via) / 2.0
    half = oe._m(g.a_siw) / 2.0
    over = oe._m(spec.d_via)
    L = oe._m(g.L_cav)

    vias = _two_cavity_vias(g, iris_w)
    pec, _ = oe._add_substrate_and_planes(csx, spec, -over, 2 * L + over,
                                          -half - over, half + over)
    oe._add_vias(pec, vias, radius, h)

    # weak-coupling lumped ports near the outer wall of each cavity
    xin = couple_inset * L
    yoff = half * 0.5
    p_in = fdtd.AddLumpedPort(1, 50, [xin, yoff, 0], [xin, yoff, h], "z",
                              excite=1, priority=5)
    xout = 2 * L - couple_inset * L
    p_out = fdtd.AddLumpedPort(2, 50, [xout, yoff, 0], [xout, yoff, h], "z",
                               excite=0, priority=5)

    # mesh — via coords are in METRES; convert to the mm working unit (oe._m).
    # The via fence only behaves as a wall if each 0.8 mm via spans >=3 cells,
    # so anchor thirds-rule lines (c, c+/-d/3) at every via column/row.
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(oe.UNIT)
    f_max = spec.f0 * 1.2
    res = 2.99792458e8 / (f_max * np.sqrt(spec.substrate.eps_r)) / oe.UNIT / res_factor
    third = oe._m(spec.d_via) / 3.0
    xs = sorted({round(oe._m(x), 4) for x, _ in vias})
    ys = sorted({round(oe._m(y), 4) for _, y in vias})
    xlines = sorted({c + dx for c in xs for dx in (-third, 0.0, third)} | {xin, xout})
    ylines = sorted({c + dy for c in ys for dy in (-third, 0.0, third)} | {yoff})
    mesh.AddLine("x", xlines)
    mesh.SmoothMeshLines("x", res)
    mesh.AddLine("y", ylines)
    mesh.SmoothMeshLines("y", res)
    mesh.AddLine("z", np.linspace(0, h, 3))
    mesh.SmoothMeshLines("z", res)
    return fdtd, [p_in, p_out]


def run_two_cavity(g: Geometry, iris_w: float, res_factor: float = 18.0,
                   n_freq: int = 2001, sim_path: str | None = None):
    """Run one two-cavity sim; return (f1, f2, k)."""
    if sim_path is None:
        sim_path = os.path.join(tempfile.gettempdir(), "siw_2cav")
    fdtd, ports = build_two_cavity(g, iris_w, res_factor=res_factor)
    fdtd.Run(sim_path, cleanup=True)

    f = np.linspace(g.spec.f0 * 0.80, g.spec.f0 * 1.20, n_freq)
    for p in ports:
        p.CalcPort(sim_path, f)
    s21 = np.abs(ports[1].uf_ref / ports[0].uf_inc)

    f1, f2 = _two_peaks(f, s21)
    k = (f2**2 - f1**2) / (f2**2 + f1**2)
    return f1, f2, k


def _two_peaks(f: np.ndarray, mag: np.ndarray) -> tuple[float, float]:
    """Return the two strongest, well-separated resonance peaks (f1 < f2)."""
    # interior local maxima
    idx = [i for i in range(1, len(mag) - 1)
           if mag[i] > mag[i - 1] and mag[i] >= mag[i + 1]]
    if len(idx) < 2:
        raise RuntimeError("Could not find two resonance peaks — check coupling "
                           "strength / mesh / frequency span.")
    idx.sort(key=lambda i: mag[i], reverse=True)
    top = sorted(idx[:2])
    return float(f[top[0]]), float(f[top[1]])


# ---------------------------------------------------------------------------
# Single-cavity model for Qe extraction (taper-fed)
# ---------------------------------------------------------------------------
def build_single_cavity_qe(g: Geometry, res_factor: float = 18.0):
    """Single taper-fed cavity, far end closed by a via wall. Returns (fdtd, port)."""
    spec = g.spec
    fdtd = oe.make_fdtd(spec.f0, 0.5 * spec.f0, end_criteria=1e-4)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)

    h = oe._m(spec.substrate.h)
    radius = oe._m(spec.d_via) / 2.0
    half = oe._m(g.a_siw) / 2.0
    over = oe._m(spec.d_via)
    L = oe._m(g.L_cav)
    p = spec.p_via

    # one cavity: closed wall at far end (x=L), open (taper) at x=0
    n_side = max(2, round(L / oe._m(p)))
    xs = np.linspace(0.0, L, n_side + 1)
    vias: list[tuple[float, float]] = []
    for x in xs:
        vias.append((x / 1e3, +half / 1e3))   # store in metres for the via list
        vias.append((x / 1e3, -half / 1e3))
    n_trans = int(round(g.a_siw / p))
    y_grid = np.linspace(-g.a_siw / 2, g.a_siw / 2, n_trans + 1)
    for y in y_grid:                            # closed far wall at x=L
        vias.append((L / 1e3, y))
    vias = _dedupe_vias(vias, min_sep=0.9 * spec.d_via)

    x_lo = -oe._m(g.L_taper + g.L_feed)
    pec, _ = oe._add_substrate_and_planes(csx, spec, x_lo, L + over,
                                          -half - over, half + over)
    oe._add_vias(pec, vias, radius, h)

    # mesh FIRST (AddMSLPort needs >=5 lines in the feed before it is created).
    # thirds-rule lines resolve the vias; _clean_lines drops near-duplicates so
    # the MSL port / via lines don't collapse a cell (-> tiny timestep).
    f_max = spec.f0 * 1.2
    res = 2.99792458e8 / (f_max * np.sqrt(spec.substrate.eps_r)) / oe.UNIT / res_factor
    third = oe._m(spec.d_via) / 3.0
    xs = sorted({round(oe._m(x), 4) for x, _ in vias})
    ys = sorted({round(oe._m(y), 4) for _, y in vias})
    xlines = {c + dx for c in xs for dx in (-third, 0.0, third)} \
        | {x_lo, -oe._m(g.L_taper), 0.0, L}
    ylines = {c + dy for c in ys for dy in (-third, 0.0, third)}

    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(oe.UNIT)
    mesh.AddLine("x", _clean_lines(xlines, third / 4))
    mesh.SmoothMeshLines("x", res)
    mesh.AddLine("y", _clean_lines(ylines, third / 4))
    mesh.SmoothMeshLines("y", res)
    mesh.AddLine("z", list(np.linspace(0, h, 3)) + list(h + np.array([res, 8 * res, 20 * res])))
    mesh.SmoothMeshLines("z", res)

    port = oe._add_taper_feed_port(csx, fdtd, pec, g, h, 1, "in", res, excite=True)
    return fdtd, port


def run_qe(g: Geometry, res_factor: float = 18.0, n_freq: int = 4001,
           sim_path: str | None = None) -> tuple[float, float]:
    """Run the single-cavity sim; return (f_res, Qe) via S11 group delay."""
    if sim_path is None:
        sim_path = os.path.join(tempfile.gettempdir(), "siw_qe")
    fdtd, port = build_single_cavity_qe(g, res_factor=res_factor)
    fdtd.Run(sim_path, cleanup=True)

    f = np.linspace(g.spec.f0 * 0.80, g.spec.f0 * 1.20, n_freq)
    port.CalcPort(sim_path, f, ref_impedance=50)
    s11 = port.uf_ref / port.uf_inc

    # group delay tau = -dphi/domega ; resonance where |tau| peaks
    phi = np.unwrap(np.angle(s11))
    w = 2 * np.pi * f
    tau = -np.gradient(phi, w)
    i0 = int(np.argmax(np.abs(tau)))
    f_res = f[i0]
    Qe = w[i0] * abs(tau[i0]) / 4.0
    return float(f_res), float(Qe)


# ---------------------------------------------------------------------------
# Sweep + fit + cache
# ---------------------------------------------------------------------------
def sweep_iris(g: Geometry, widths_mm: list[float], res_factor: float = 18.0):
    """Sweep iris width, extract k for each, fit w(k) and k(w), cache to JSON."""
    pts = []
    for w_mm in widths_mm:
        f1, f2, k = run_two_cavity(g, w_mm * 1e-3, res_factor=res_factor)
        print(f"  w={w_mm:5.2f} mm -> f1={f1/1e9:.4f} f2={f2/1e9:.4f} GHz  k={k:.4f}")
        pts.append((w_mm, k))

    w_arr = np.array([p[0] for p in pts])
    k_arr = np.array([p[1] for p in pts])
    deg = min(3, len(pts) - 1)
    w_of_k = np.polyfit(k_arr, w_arr, deg).tolist()   # w(k)
    k_of_w = np.polyfit(w_arr, k_arr, deg).tolist()   # k(w)

    _store(g.spec, "iris", dict(points=pts, w_of_k=w_of_k, k_of_w=k_of_w,
                                res_factor=res_factor))
    # report the synthesized target
    k_target = float(g.syn.k[0])
    w_target = float(np.polyval(w_of_k, k_target))
    print(f"\nFit w(k): target k={k_target:.4f} -> iris width = {w_target:.3f} mm")
    return pts, w_of_k


def calibrate_qe(g: Geometry, res_factor: float = 18.0):
    f_res, Qe = run_qe(g, res_factor=res_factor)
    print(f"  taper-fed cavity: f_res={f_res/1e9:.4f} GHz  Qe={Qe:.2f}")
    print(f"  (synthesis target Qe={g.syn.qe_in:.2f})")
    _store(g.spec, "qe", dict(f_res=f_res, Qe=Qe, taper_L_mm=g.L_taper * 1e3,
                              res_factor=res_factor))
    return Qe


def _store(spec: FilterSpec, section: str, data: dict) -> None:
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as fh:
            cache = json.load(fh)
    cache.setdefault(_cache_key(spec), {})[section] = data
    with open(CACHE, "w") as fh:
        json.dump(cache, fh, indent=2)
    print(f"Cached '{section}' to {CACHE} under [{_cache_key(spec)}]")


def load_calibration(spec: FilterSpec) -> dict | None:
    if not os.path.exists(CACHE):
        return None
    with open(CACHE) as fh:
        return json.load(fh).get(_cache_key(spec))


def iris_width_for_k(spec: FilterSpec, k: float) -> float | None:
    """Return calibrated iris width [m] for coupling k, or None if uncalibrated."""
    cal = load_calibration(spec)
    if not cal or "iris" not in cal:
        return None
    return float(np.polyval(cal["iris"]["w_of_k"], k)) * 1e-3


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="SIW EM calibration")
    ap.add_argument("--sweep", action="store_true", help="run iris k(w) sweep")
    ap.add_argument("--qe", action="store_true", help="run external-Q extraction")
    ap.add_argument("--build-only", action="store_true",
                    help="build models + write XML, no FDTD run")
    ap.add_argument("--res", type=float, default=18.0, help="mesh res factor")
    ap.add_argument("--widths", type=str, default="5,7,9,11,13",
                    help="iris widths [mm] to sweep, comma-separated")
    args = ap.parse_args()

    g = build_geometry(SPEC)
    widths = [float(x) for x in args.widths.split(",")]

    if args.build_only:
        out = os.path.join(tempfile.gettempdir(), "siw_cal")
        os.makedirs(out, exist_ok=True)
        fdtd, ports = build_two_cavity(g, widths[len(widths) // 2] * 1e-3,
                                       res_factor=args.res)
        csx = fdtd.GetCSX()
        csx.Write2XML(os.path.join(out, "two_cavity.xml"))
        gx = csx.GetGrid()
        n = [gx.GetQtyLines(a) for a in "xyz"]
        print(f"two-cavity CSX OK  mesh {n[0]}x{n[1]}x{n[2]} = {np.prod(n):,} cells")

        fdtd2, port = build_single_cavity_qe(g, res_factor=args.res)
        csx2 = fdtd2.GetCSX()
        csx2.Write2XML(os.path.join(out, "single_cavity.xml"))
        gx2 = csx2.GetGrid()
        n2 = [gx2.GetQtyLines(a) for a in "xyz"]
        print(f"single-cavity CSX OK  mesh {n2[0]}x{n2[1]}x{n2[2]} = {np.prod(n2):,} cells")
    elif args.sweep:
        print(f"=== iris k(w) sweep: {widths} mm (res={args.res}) ===")
        sweep_iris(g, widths, res_factor=args.res)
    elif args.qe:
        print(f"=== external Q extraction (res={args.res}) ===")
        calibrate_qe(g, res_factor=args.res)
    else:
        ap.print_help()
