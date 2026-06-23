"""openEMS FDTD model of the SIW filter + shared CSX builders.

Builds the 3D model from siw_geometry output:
  - substrate box (Rogers material, eps_r + kappa from tan_d),
  - bottom ground = PEC z-min boundary, top copper = PEC sheet at z=h,
  - vias as PEC cylinders (z 0..h); irises are the gaps already encoded in the
    via list from siw_geometry,
  - microstrip feed + quarter-wave taper + MSLPort at each end.
Runs FDTD, extracts S-params, writes openems.s2p, plots |S11|/|S21|.

The builder helpers (_add_substrate_and_planes, _add_vias, _add_taper_feed_port,
auto_mesh) are reused by calibrate.py for the two-cavity / single-cavity test
structures.

NOTE: SIW FDTD is expensive (the via fence wants >=3 cells across d=0.8 mm).
A full-filter run is minutes-to-tens-of-minutes depending on `res_factor`.
Set LD_LIBRARY_PATH=$HOME/opt/openEMS/lib before running.

Run:  uv run python openems_sim.py
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

import numpy as np

from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0 as OEMS_C0

from .config import SPEC, EPS0, FilterSpec, out_s2p, out_img
from .siw_geometry import Geometry, build_geometry

UNIT = 1e-3   # geometry passed to openEMS in millimetres

# openEMS.Run() chdir's into the sim path, so anchor output files to the project
# directory to keep them next to the modules.
_PROJ_DIR = os.path.dirname(os.path.abspath(__file__))


def _proj(path: str) -> str:
    """Resolve a relative output path against the project dir (Run() chdir-safe)."""
    return path if os.path.isabs(path) else os.path.join(_PROJ_DIR, path)


def db(x: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


# ---------------------------------------------------------------------------
# Shared CSX builders (metres in -> mm out)
# ---------------------------------------------------------------------------
def _m(x: float) -> float:
    """metres -> mm (the openEMS working unit here)."""
    return x * 1e3


def make_fdtd(f_center: float, f_cutoff: float, end_criteria: float = 1e-4,
              max_timesteps: int | None = None) -> openEMS:
    """Create an openEMS instance with a Gaussian excitation and SIW-friendly BCs.

    z-min = PEC acts as the continuous bottom ground plane; z-max = MUR leaves
    air above the microstrip trace; x ends are PML (the ports); y walls are MUR
    just outside the via fence.
    """
    kw = dict(EndCriteria=end_criteria)
    if max_timesteps:
        kw["NrTS"] = max_timesteps
    fdtd = openEMS(**kw)
    fdtd.SetGaussExcite(f_center, f_cutoff)
    fdtd.SetBoundaryCond(["PML_8", "PML_8", "MUR", "MUR", "PEC", "MUR"])
    return fdtd


def _add_substrate_and_planes(csx: ContinuousStructure, spec: FilterSpec,
                              x0: float, x1: float, y0: float, y1: float,
                              top_x0: float | None = None,
                              top_x1: float | None = None):
    """Substrate box (z 0..h) + top PEC copper plane.

    The substrate spans [x0..x1]x[y0..y1]. The top PEC plane spans
    [top_x0..top_x1] (defaults to the full substrate). Restrict the top plane
    to the SIW cavity region so it does NOT short out a microstrip feed/taper
    that lives in the lead-in region.
    """
    sub = spec.substrate
    h = _m(sub.h)
    kappa = sub.kappa(spec.f0)
    mat = csx.AddMaterial("substrate", epsilon=sub.eps_r, kappa=kappa)
    mat.AddBox([x0, y0, 0.0], [x1, y1, h], priority=1)
    pec = csx.AddMetal("copper")
    tx0 = x0 if top_x0 is None else top_x0
    tx1 = x1 if top_x1 is None else top_x1
    # top SIW plane (zero-thickness sheet at z=h)
    pec.AddBox([tx0, y0, h], [tx1, y1, h], priority=10)
    return pec, h


def _add_vias(pec, vias: list[tuple[float, float]], radius: float, h: float):
    """PEC via cylinders from z=0 (ground) to z=h (top plane)."""
    for (x, y) in vias:
        pec.AddCylinder([_m(x), _m(y), 0.0], [_m(x), _m(y), h], radius=radius,
                        priority=10)


def _add_taper_feed_port(csx: ContinuousStructure, fdtd: openEMS, pec, g: Geometry,
                         h: float, port_nr: int, side: str,
                         feed_res: float, excite: bool):
    """Add one microstrip feed + quarter-wave taper + MSLPort.

    side: 'in' (x<0, propagates +x) or 'out' (x>L_inner, propagates -x).
    Returns the port object.
    """
    W = _m(g.W_ms)
    Lt = _m(g.L_taper)
    Lf = _m(g.L_feed)
    half = _m(g.a_siw) / 2.0
    L_inner = _m(g.L_inner)

    if side == "in":
        x_feed_out, x_taper0, x_siw = -(Lt + Lf), -Lt, 0.0
        taper_pts = np.array([[x_taper0, -W / 2], [x_siw, -half],
                              [x_siw, +half], [x_taper0, +W / 2]])
        p_start = [x_feed_out, -W / 2, h]
        p_stop = [x_taper0, +W / 2, 0.0]
        exc_dir = -1 if excite else 0          # excite into +x
    else:
        x_feed_out, x_taper0, x_siw = L_inner + Lt + Lf, L_inner + Lt, L_inner
        taper_pts = np.array([[x_taper0, -W / 2], [x_siw, -half],
                              [x_siw, +half], [x_taper0, +W / 2]])
        p_start = [x_feed_out, -W / 2, h]
        p_stop = [x_taper0, +W / 2, 0.0]
        exc_dir = 0

    # taper as a flat PEC polygon at z=h (norm 'z')
    pec.AddPolygon(taper_pts.T.tolist(), "z", h, priority=10)

    # MSL port over the straight feed; the port creates the feed trace metal.
    # Shifts must stay INSIDE the (short) feed line, else the excitation /
    # measurement plane lands outside it and collapses a mesh cell.
    port = fdtd.AddMSLPort(port_nr, pec, p_start, p_stop, "x", "z",
                           excite=exc_dir, FeedShift=0.5 * Lf,
                           MeasPlaneShift=0.25 * Lf, priority=10)
    return port


def _clean_lines(lines: list[float], min_gap: float) -> list[float]:
    """Remove mesh lines closer than min_gap to prevent near-zero cells."""
    out: list[float] = []
    for v in sorted(lines):
        if not out or abs(v - out[-1]) >= min_gap:
            out.append(v)
    return out


def auto_mesh(csx: ContinuousStructure, g: Geometry, h: float,
              x_lo: float, x_hi: float, res_factor: float = 20.0):
    """Build a graded mesh: lambda/res_factor in dielectric, via centres anchored,
    thirds-rule cells around each via, air above the substrate."""
    sub = g.spec.substrate
    f_max = g.spec.f0 * 1.4
    res = OEMS_C0 / (f_max * np.sqrt(sub.eps_r)) / UNIT / res_factor   # mm
    d_mm = _m(g.spec.d_via)
    third = d_mm / 3.0          # thirds-rule offset for via resolution
    min_gap = third * 0.5       # dedup threshold: half a third

    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)
    half = _m(g.a_siw) / 2.0

    # --- x: via centres + thirds-rule + domain bounds ---
    raw_x = [x_lo, x_hi, 0.0, _m(g.L_inner)]
    for (x, _) in g.vias:
        c = round(_m(x), 4)
        raw_x += [c, c - third, c + third]
    mesh.AddLine("x", _clean_lines(raw_x, min_gap))
    mesh.SmoothMeshLines("x", res)

    # --- y: via centres + thirds-rule + midpoints between adjacent vias ---
    raw_y = [-half - 4 * res, half + 4 * res]
    unique_y = sorted({round(_m(y), 4) for (_, y) in g.vias})
    for c in unique_y:
        raw_y += [c, c - third, c + third]
    # midpoint between every adjacent via pair so the gap gets >=1 cell
    for a, b in zip(unique_y[:-1], unique_y[1:]):
        raw_y.append((a + b) / 2.0)
    # feed width edges
    w2 = _m(g.W_ms) / 2.0
    raw_y += [w2, -w2]
    mesh.AddLine("y", _clean_lines(raw_y, min_gap))
    mesh.SmoothMeshLines("y", res)

    # --- z: substrate layers + air above ---
    mesh.AddLine("z", np.linspace(0.0, h, 4))
    mesh.AddLine("z", h + np.array([res, 8 * res, 20 * res]))
    mesh.SmoothMeshLines("z", res)
    return mesh, res


# ---------------------------------------------------------------------------
# Full filter — lumped-port variant (no taper, ports at SIW end faces)
# ---------------------------------------------------------------------------
def build_full_filter_lumped(g: Geometry, res_factor: float = 18.0,
                             end_criteria: float = 1e-4):
    """Full N-cavity filter with lumped ports directly at the SIW end faces.

    Bypasses the microstrip taper entirely — ports sit at x=0 and x=L_inner,
    centred at y=0, z=h/2. This is the same weak-coupling approach used in
    calibrate.py and avoids the MSLPort/taper issues seen in the MSL model.
    The impedance is not 50 Ohm matched (SIW Z_PI != 50 Ohm) so S11 will look
    poor, but S21 passband shape and centre frequency are reliable.
    """
    spec = g.spec
    fdtd = make_fdtd(spec.f0, 0.5 * spec.f0, end_criteria=end_criteria)
    fdtd.SetBoundaryCond(["MUR", "MUR", "MUR", "MUR", "PEC", "MUR"])
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)

    h = _m(spec.substrate.h)
    radius = _m(spec.d_via) / 2.0
    half = _m(g.a_siw) / 2.0
    over = _m(spec.d_via)
    L_inner = _m(g.L_inner)

    pec, _ = _add_substrate_and_planes(csx, spec,
                                       -over, L_inner + over,
                                       -half - over, half + over)
    _add_vias(pec, g.vias, radius, h)

    # Lumped ports at the SIW end faces, inset slightly from the end wall
    inset = _m(g.L_cav) * 0.15
    yoff  = half * 0.5
    port_in  = fdtd.AddLumpedPort(1, 50,
                                   [inset, yoff, 0], [inset, yoff, h],
                                   "z", excite=1, priority=5)
    port_out = fdtd.AddLumpedPort(2, 50,
                                   [L_inner - inset, yoff, 0],
                                   [L_inner - inset, yoff, h],
                                   "z", excite=0, priority=5)

    # mesh — same thirds-rule approach as calibrate.py
    d_mm  = _m(spec.d_via)
    third = d_mm / 3.0
    min_gap = third * 0.5

    sub = spec.substrate
    f_max = spec.f0 * 1.4
    res = OEMS_C0 / (f_max * np.sqrt(sub.eps_r)) / UNIT / res_factor

    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(UNIT)

    xs_via = sorted({round(_m(x), 4) for x, _ in g.vias})
    ys_via = sorted({round(_m(y), 4) for _, y in g.vias})

    raw_x = [-over, L_inner + over, inset, L_inner - inset]
    for c in xs_via:
        raw_x += [c, c - third, c + third]
    mesh.AddLine("x", _clean_lines(raw_x, min_gap))
    mesh.SmoothMeshLines("x", res)

    raw_y = [-half - 4 * res, half + 4 * res, yoff]
    for c in ys_via:
        raw_y += [c, c - third, c + third]
    for a, b in zip(ys_via[:-1], ys_via[1:]):
        raw_y.append((a + b) / 2.0)
    mesh.AddLine("y", _clean_lines(raw_y, min_gap))
    mesh.SmoothMeshLines("y", res)

    mesh.AddLine("z", np.linspace(0, h, 4))
    mesh.AddLine("z", [h + res, h + 8 * res])
    mesh.SmoothMeshLines("z", res)

    return fdtd, csx, [port_in, port_out]


# ---------------------------------------------------------------------------
# Full filter model + run
# ---------------------------------------------------------------------------
@dataclass
class SimResult:
    f: np.ndarray
    s11: np.ndarray
    s21: np.ndarray


def build_full_filter(g: Geometry, res_factor: float = 18.0,
                      end_criteria: float = 1e-4):
    """Assemble the complete CSX + FDTD for the N-cavity filter. Returns
    (fdtd, csx, [port_in, port_out])."""
    spec = g.spec
    f_lo, f_hi = 2.0e9, 3.7e9
    fdtd = make_fdtd(0.5 * (f_lo + f_hi), 0.5 * (f_hi - f_lo),
                     end_criteria=end_criteria)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)

    h = _m(spec.substrate.h)
    radius = _m(spec.d_via) / 2.0
    half = _m(g.a_siw) / 2.0
    over = _m(spec.d_via)           # top-plane overhang past the via centres

    # extents (include feed lead-in on both ends)
    x_lo = -_m(g.L_taper + g.L_feed)
    x_hi = _m(g.L_inner + g.L_taper + g.L_feed)

    # substrate spans the whole board; top plane ONLY over the cavity region
    # so the microstrip feed/taper in the lead-in is not shorted to ground.
    pec, _ = _add_substrate_and_planes(csx, spec, x_lo, x_hi,
                                       -half - over, half + over,
                                       top_x0=0.0, top_x1=_m(g.L_inner))

    _add_vias(pec, g.vias, radius, h)

    mesh, res = auto_mesh(csx, g, h, x_lo, x_hi, res_factor=res_factor)

    port_in = _add_taper_feed_port(csx, fdtd, pec, g, h, 1, "in", res, excite=True)
    port_out = _add_taper_feed_port(csx, fdtd, pec, g, h, 2, "out", res, excite=False)
    return fdtd, csx, [port_in, port_out]


def run_filter_sim(g: Geometry | None = None, sim_path: str | None = None,
                   res_factor: float = 18.0, n_freq: int = 601,
                   save_s2p: str | None = None, plot: bool = True,
                   end_criteria: float = 1e-4, nr_threads: int = 8,
                   lumped: bool = False) -> SimResult:
    if g is None:
        g = build_geometry(SPEC)
    if save_s2p is None:
        save_s2p = out_s2p("openems.s2p")
    if sim_path is None:
        sim_path = os.path.join(tempfile.gettempdir(), "siw_filter")

    builder = build_full_filter_lumped if lumped else build_full_filter
    fdtd, csx, ports = builder(g, res_factor=res_factor, end_criteria=end_criteria)
    fdtd.Run(sim_path, cleanup=True, numThreads=nr_threads)

    f = np.linspace(2.0e9, 3.7e9, n_freq)
    for p in ports:
        p.CalcPort(sim_path, f, ref_impedance=50)
    s11 = ports[0].uf_ref / ports[0].uf_inc
    s21 = ports[1].uf_ref / ports[0].uf_inc

    if save_s2p:
        _write_s2p(_proj(save_s2p), f, s11, s21)
        print(f"Wrote {_proj(save_s2p)}")
    if plot:
        _plot(f, s11, s21, g, out_img("openems_response.png"))
    return SimResult(f=f, s11=s11, s21=s21)


def _write_s2p(path: str, f: np.ndarray, s11: np.ndarray, s21: np.ndarray) -> None:
    import skrf as rf
    n = len(f)
    s = np.zeros((n, 2, 2), dtype=complex)
    s[:, 0, 0] = s11
    s[:, 1, 0] = s21
    s[:, 0, 1] = s21
    s[:, 1, 1] = s11
    ntwk = rf.Network(frequency=rf.Frequency.from_f(f, unit="Hz"), s=s, z0=50.0,
                      name="siw_openems")
    ntwk.write_touchstone(path, write_z0=True)


def _plot(f, s11, s21, g, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(f / 1e9, db(s11), label="|S11|")
    ax.plot(f / 1e9, db(s21), label="|S21|")
    ax.axvspan(g.spec.f1 / 1e9, g.spec.f2 / 1e9, color="green", alpha=0.1)
    ax.set_xlabel("Frequency [GHz]")
    ax.set_ylabel("Magnitude [dB]")
    ax.set_ylim(-60, 2)
    ax.set_title(f"openEMS SIW filter — N={g.spec.N}, {g.spec.f0/1e9:.3f} GHz")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print(f"Wrote {path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="openEMS SIW filter simulation")
    ap.add_argument("--res", type=float, default=18.0,
                    help="mesh res factor (lambda/res in dielectric); higher=finer/slower")
    ap.add_argument("--end-criteria", type=float, default=1e-4,
                    help="FDTD end criteria (1e-3 = fast/rough, 1e-4 = normal, 1e-5 = accurate)")
    ap.add_argument("--threads", type=int, default=8,
                    help="number of CPU threads for openEMS")
    ap.add_argument("--fast", action="store_true",
                    help="quick check: res=10, end_criteria=1e-3 (~5-10 min)")
    ap.add_argument("--lumped", action="store_true",
                    help="use lumped ports at SIW faces (no taper); reliable passband shape")
    ap.add_argument("--build-only", action="store_true",
                    help="build CSX and write XML, do not run FDTD")
    args = ap.parse_args()

    if args.fast:
        args.res = 10.0
        args.end_criteria = 1e-3

    g = build_geometry(SPEC)
    if args.build_only:
        fdtd, csx, ports = build_full_filter(g, res_factor=args.res,
                                             end_criteria=args.end_criteria)
        out = os.path.join(tempfile.gettempdir(), "siw_filter")
        os.makedirs(out, exist_ok=True)
        xml = os.path.join(out, "siw_filter.xml")
        csx.Write2XML(xml)
        nx = csx.GetGrid().GetQtyLines("x")
        ny = csx.GetGrid().GetQtyLines("y")
        nz = csx.GetGrid().GetQtyLines("z")
        print(f"Built CSX OK -> {xml}")
        print(f"Mesh: {nx} x {ny} x {nz} = {nx*ny*nz:,} cells")
    else:
        run_filter_sim(g, res_factor=args.res, end_criteria=args.end_criteria,
                       nr_threads=args.threads, lumped=args.lumped)
