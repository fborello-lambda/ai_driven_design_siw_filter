"""Minimal 2-port driven test of the dual-mode cavity ALONE (no companion
cavity, no microstrip taper/connector yet). The closed eigenmode cavity in
palace_dualmode.py has every boundary tagged PEC -- it was never meant to be
fed. Following the SAME pattern palace_driven.py uses for the main filter
(external-iris gap in the via fence -> feed channel -> flat WavePort face at
the channel's far end, matched via the `_near`+bounding-box convention), this
adds:
  - a gap of width w_ext in the via fence on the x=0 wall (INPUT), centered
    y=0, feeding a short via-fenced straight SIW stub that ends in a flat
    port face at x=-L_stub;
  - a second gap on the y=-half wall (OUTPUT, the ADJACENT wall -- this tests
    the untested wall-placement assumption that input/output must be on
    ADJACENT walls, not opposite ones, to couple into the two different
    orthogonal degenerate modes), centered x=a/2, feeding a stub ending at
    y=-(half+L_stub).
No microstrip/taper/air region -- pure SIW-mode port the whole way, single
dielectric material throughout, same simplification level as a first-look
check (matches project pattern: analytical/cheap pass first, then refine)."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import gmsh
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data  # noqa: E402
from siwfilter.palace_dualmode import A_SIW_MM, D_VIA_MM, P_VIA_MM  # noqa: E402

PALACE = "/home/fd/opt/palace/bin/palace"


def _near(a, b, tol=1e-3):
    return abs(a - b) < tol


def build_mesh(dp_mm: float = 5.0, w_ext_mm: float = 40.0, l_stub_mm: float = 20.0,
               a_mm: float = A_SIW_MM, d_via_mm: float = D_VIA_MM, p_via_mm: float = P_VIA_MM,
               h_mm: float = 0.76, mesh_max: float = 1.5, mesh_min: float = 0.4,
               out_name: str = "dualmode_2port.msh") -> dict:
    a = a_mm
    r = d_via_mm / 2.0
    p = p_via_mm
    h = h_mm
    half = a / 2.0
    we = w_ext_mm
    ls = l_stub_mm

    n = max(1, round(a / p))
    xs = np.linspace(0.0, a, n + 1)
    ys = np.linspace(-half, half, n + 1)
    vias: list[tuple[float, float]] = []
    # main cavity via fence, walls x=0 (INPUT gap at y=0) and x=a (closed)
    for yv in ys:
        if abs(yv) > we / 2.0:
            vias.append((0.0, yv))
        vias.append((a, yv))
    # walls y=-half (OUTPUT gap at x=a/2, adjacent wall) and y=+half (closed)
    for xv in xs:
        if abs(xv - a / 2.0) > we / 2.0:
            vias.append((xv, -half))
        vias.append((xv, half))

    # internal perturbation via pair (same as calibrated eigenmode cavity)
    cx, cy = a / 2.0, 0.0
    d = dp_mm / np.sqrt(2.0)
    vias.append((cx + d, cy + d))
    vias.append((cx - d, cy - d))

    # input stub side-wall via fences: y = +-we/2, x from -ls to 0
    n_stub = max(1, round(ls / p))
    xs_stub = np.linspace(-ls, 0.0, n_stub + 1)
    for xv in xs_stub:
        vias.append((xv, we / 2.0))
        vias.append((xv, -we / 2.0))
    # output stub side-wall via fences: x = a/2 +- we/2, y from -half to -half-ls
    ys_stub = np.linspace(-half, -half - ls, n_stub + 1)
    for yv in ys_stub:
        vias.append((a / 2.0 + we / 2.0, yv))
        vias.append((a / 2.0 - we / 2.0, yv))

    final: list[tuple[float, float]] = []
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= (0.9 * 2 * r) ** 2
               for kx, ky in final):
            final.append((x, y))

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("dualmode_2port")
    occ = gmsh.model.occ

    main_box = occ.addBox(-r, -half - r, 0.0, a + 2 * r, a + 2 * r, h)
    in_stub = occ.addBox(-ls, -we / 2.0 - r, 0.0, ls + 2 * r, we + 2 * r, h)
    out_stub = occ.addBox(a / 2.0 - we / 2.0 - r, -half - ls, 0.0, we + 2 * r, ls + 2 * r, h)
    fused, _ = occ.fuse([(3, main_box)], [(3, in_stub), (3, out_stub)])
    cyls = [(3, occ.addCylinder(x, y, 0.0, 0, 0, h, r)) for x, y in final]
    occ.cut(fused, cyls)
    occ.synchronize()

    vols = gmsh.model.getEntities(3)
    gmsh.model.addPhysicalGroup(3, [v[1] for v in vols], tag=1, name="dielectric")

    pec, wave_in, wave_out = [], [], []
    for dim, tag in gmsh.model.getEntities(2):
        cx2, cy2, cz2 = gmsh.model.occ.getCenterOfMass(2, tag)
        xmin, ymin_f, _, xmax, ymax_f, _ = gmsh.model.getBoundingBox(2, tag)
        if _near(cx2, -ls) and (xmax - xmin) < 1e-3:
            wave_in.append(tag)
        elif _near(cy2, -half - ls) and (ymax_f - ymin_f) < 1e-3:
            wave_out.append(tag)
        else:
            pec.append(tag)

    gmsh.model.addPhysicalGroup(2, sorted(set(pec)), tag=10, name="pec")
    gmsh.model.addPhysicalGroup(2, wave_in, tag=11, name="port_in")
    gmsh.model.addPhysicalGroup(2, wave_out, tag=12, name="port_out")

    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_min)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_max)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 16)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.mesh.generate(3)

    out = out_data(out_name)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.write(out)
    ntet = len(gmsh.model.mesh.getElementsByType(4)[0])
    print(f"--- dualmode 2-port test (dp={dp_mm}mm, w_ext={we}mm, l_stub={ls}mm) ---")
    print(f"  vias={len(final)} pec={len(pec)} port_in={len(wave_in)} port_out={len(wave_out)}")
    print(f"  tets={ntet:,}  WROTE {out}")
    gmsh.finalize()
    return {"mesh": out, "ports": (len(wave_in), len(wave_out))}


def run(dp_mm=5.0, w_ext_mm=40.0, l_stub_mm=20.0, fmin=2.6, fmax=3.1, fstep=0.02):
    res = build_mesh(dp_mm=dp_mm, w_ext_mm=w_ext_mm, l_stub_mm=l_stub_mm)
    if res["ports"] != (1, 1):
        print(f"WARNING: unexpected port face count {res['ports']}, expected (1,1)")
        return None
    cfg = {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": "postpro/dualmode_2port"},
        "Model": {"Mesh": "dualmode_2port.msh", "L0": 1.0e-3},
        "Domains": {"Materials": [
            {"Attributes": [1], "Permeability": 1.0, "Permittivity": 3.66, "LossTan": 0.0037}]},
        "Boundaries": {"PEC": {"Attributes": [10]},
                       "WavePort": [
                           {"Index": 1, "Attributes": [11], "Mode": 1, "Excitation": 1,
                            "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6},
                           {"Index": 2, "Attributes": [12], "Mode": 1,
                            "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6}]},
        "Solver": {"Order": 1, "Device": "CPU",
                   "Driven": {"Samples": [{"Type": "Linear", "MinFreq": fmin,
                                           "MaxFreq": fmax, "FreqStep": fstep}]},
                   "Linear": {"Type": "Default", "KSPType": "GMRES", "Tol": 1e-8, "MaxIts": 300}},
    }
    cfgp = out_data("dualmode_2port.json")
    json.dump(cfg, open(cfgp, "w"), indent=2)
    env = dict(os.environ, PATH=f"/home/fd/opt/palace/bin:{os.environ['PATH']}")
    logp = out_data("dualmode_2port.log")
    subprocess.run([PALACE, "-np", "4", os.path.basename(cfgp)], cwd=out_data(""),
                   env=env, stdout=open(logp, "w"), stderr=subprocess.STDOUT, check=False)
    csv = out_data("postpro/dualmode_2port/port-S.csv")
    if not os.path.exists(csv):
        print("FAILED, tail of log:")
        print("\n".join(open(logp).read().splitlines()[-30:]))
        return None
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    nm = d.dtype.names
    print("\nfreq(GHz)  S11(dB)  S21(dB)")
    for row in d:
        print(f"{row[nm[0]]:.3f}   {row[nm[1]]:.2f}   {row[nm[3]]:.2f}")
    return d


if __name__ == "__main__":
    run()
