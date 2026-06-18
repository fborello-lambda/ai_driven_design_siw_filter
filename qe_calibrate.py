"""Calibrate the external coupling iris w_ext -> Qe in openEMS (CLAUDE.md sec 6).

Single SIW cavity fed by a microstrip taper THROUGH an input iris of gap w_ext,
far end closed. Extract the external quality factor from the S11 group delay at
resonance:  Qe = omega0 * tau_S11(omega0) / 4. Sweep w_ext, fit Qe(w_ext), and
report the w_ext that yields the synthesis target Qe.

Run:  LD_LIBRARY_PATH=$HOME/opt/openEMS/lib uv run python qe_calibrate.py
"""
from __future__ import annotations
import os, tempfile
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0 as OEMS_C0
from config import SPEC
from siw_geometry import build_geometry
import openems_sim as oe

UNIT = 1e-3
def _m(x): return x * 1e3

def build_single_cavity(g, w_ext, res_factor=14, end_criteria=1e-4):
    spec = g.spec
    fdtd = oe.make_fdtd(spec.f0, 0.6 * spec.f0, end_criteria=end_criteria)
    fdtd.SetBoundaryCond(["PML_8", "MUR", "MUR", "MUR", "PEC", "MUR"])
    csx = ContinuousStructure(); fdtd.SetCSX(csx)

    h = _m(spec.substrate.h); radius = _m(spec.d_via)/2.0
    half = _m(g.a_siw)/2.0; over = _m(spec.d_via)
    L = _m(g.L_cav); p = _m(spec.p_via); we = _m(w_ext)
    W = _m(g.W_ms); Lt = _m(g.L_taper); Lf = _m(g.L_feed)

    x_lo = -(Lt + Lf)
    # substrate full board, top plane only over cavity [0, L]
    pec, _ = oe._add_substrate_and_planes(csx, spec, x_lo, L + over,
                                          -half - over, half + over,
                                          top_x0=0.0, top_x1=L)
    # ---- vias ----
    vias = []
    n_side = max(1, int(round(L / p)))
    xs = np.linspace(0.0, L, n_side + 1)
    for x in xs:
        vias += [(x, half), (x, -half)]
    # far-end closed wall at x=L
    n_tr = int(round(g.a_siw / spec.p_via))
    ys = np.linspace(-half, half, n_tr + 1)
    for y in ys: vias.append((L, y))
    # input iris at x=0: gap = we
    for y in ys:
        if abs(y) > we/2.0: vias.append((0.0, y))
    # dedupe
    kept = []
    for x, y in vias:
        if all((x-kx)**2+(y-ky)**2 >= (0.9*2*radius)**2 for kx,ky in kept):
            kept.append((x,y))
    for x, y in kept:
        pec.AddCylinder([x, y, 0.0], [x, y, h], radius=radius, priority=10)

    # ---- taper feed (widen W_ms -> w_ext gap) ----
    taper_pts = np.array([[-Lt, -W/2],[0.0,-we/2],[0.0,we/2],[-Lt,W/2]])
    pec.AddPolygon(taper_pts.T.tolist(), "z", h, priority=10)

    # ---- mesh (must exist before the MSLPort) ----
    res = OEMS_C0/(spec.f0*1.4*np.sqrt(spec.substrate.eps_r))/UNIT/res_factor
    third = _m(spec.d_via)/3.0; mg = third*0.5
    mesh = csx.GetGrid(); mesh.SetDeltaUnit(UNIT)
    def clean(v):
        out=[]
        for x in sorted(v):
            if not out or x-out[-1]>=mg: out.append(x)
        return out
    rx=[x_lo, L+over]
    for x,_ in kept: rx += [x, x-third, x+third]
    mesh.AddLine("x", clean(rx)); mesh.SmoothMeshLines("x", res)
    ry=[-half-4*res, half+4*res, W/2, -W/2]
    uy=sorted({round(y,4) for _,y in kept})
    for y in uy: ry += [y, y-third, y+third]
    for a,b in zip(uy[:-1],uy[1:]): ry.append((a+b)/2)
    mesh.AddLine("y", clean(ry)); mesh.SmoothMeshLines("y", res)
    mesh.AddLine("z", np.linspace(0,h,4)); mesh.AddLine("z",[h+res,h+8*res])
    mesh.SmoothMeshLines("z", res)

    # ---- MSLPort (after mesh exists) ----
    port = fdtd.AddMSLPort(1, pec, [x_lo, -W/2, h], [-Lt, W/2, 0.0],
                           "x", "z", excite=-1, FeedShift=0.5*Lf,
                           MeasPlaneShift=0.25*Lf, priority=10)
    return fdtd, port

def run_qe(g, w_ext, res_factor=14):
    sim = os.path.join(tempfile.gettempdir(), f"siw_qe_{w_ext*1e3:.1f}")
    fdtd, port = build_single_cavity(g, w_ext, res_factor=res_factor)
    fdtd.Run(sim, cleanup=True, numThreads=8)
    f = np.linspace(g.spec.f0*0.6, g.spec.f0*1.4, 4001)
    port.CalcPort(sim, f, ref_impedance=50)
    s11 = port.uf_ref/port.uf_inc
    phase = np.unwrap(np.angle(s11))
    tau = -np.gradient(phase, 2*np.pi*f)          # group delay
    # resonance = where |S11| dips (max coupling) within band
    band = (f>g.spec.f0*0.8)&(f<g.spec.f0*1.2)
    i0 = np.where(band)[0][np.argmin(np.abs(s11)[band])]
    f0 = f[i0]; w0 = 2*np.pi*f0
    Qe = w0*abs(tau[i0])/4.0
    return f0, Qe

if __name__ == "__main__":
    g = build_geometry(SPEC)
    widths = [16e-3, 20e-3, 24e-3, 28e-3, 32e-3]
    print(f"target Qe = {g.syn.qe_in:.2f}\n")
    res=[]
    for we in widths:
        f0,Qe = run_qe(g, we)
        res.append((we*1e3, f0/1e9, Qe))
        print(f"w_ext={we*1e3:5.1f}mm  f_res={f0/1e9:.3f}GHz  Qe={Qe:.2f}", flush=True)
    print("\nResumen:")
    for w,f0,Qe in res: print(f"  w_ext={w:5.1f}mm -> Qe={Qe:.2f}  (f={f0:.3f}GHz)")
    # fit Qe(w_ext)
    ws=[r[0] for r in res]; qs=[r[2] for r in res]
    c=np.polyfit(ws,qs,2)
    tgt=g.syn.qe_in
    # solve poly=tgt
    roots=np.roots([c[0],c[1],c[2]-tgt])
    roots=[r.real for r in roots if abs(r.imag)<1e-6 and min(ws)<=r.real<=max(ws)]
    if roots: print(f"\n-> w_ext para Qe={tgt:.2f}: {roots[0]:.2f} mm")
