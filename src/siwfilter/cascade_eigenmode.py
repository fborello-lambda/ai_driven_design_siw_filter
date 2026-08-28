"""Closed-cavity (no-port) eigenmode analysis of dualmode_cascade -- ground
truth for how many real resonances exist near the band and where, without
S-parameter interpretation ambiguity.

Built 2026-08-27 to settle whether dualmode_cascade's observed "two center
frequencies" shape (see docs/geometry_exploration/dualmode_enhancements_
2026-08-26.md, round 4) is a genuine distinct spurious mode or a
pole-pair-splitting artifact of under-coupled cavities. Answer: the latter
-- v3/coupling-corrected designs have exactly 4 real poles, split into two
tight pairs (each cavity's own internal splitting) separated by a large gap
because the inter-cavity coupling (w_inter_mm) is too weak relative to the
(enlarged) intra-cavity coupling (w_iris) to interleave them.

Reuses geometries.dualmode_cascade()'s via-layout generator UNCHANGED --
`w_ext_mm=0` collapses the port gap, sealing both ends (the same
driven-to-closed transformation palace_dualmode.py already applies to the
single-cavity case) -- so eigenmode via positions are guaranteed identical
to the real driven design's, just with ports closed.
"""
from __future__ import annotations

import json
import os
import subprocess

import gmsh
import numpy as np

from .config import FilterSpec, find_palace, out_data
from .geometries import LAYOUTS


def build_closed_mesh(a_mm: float, w_iris_mm: float, x_iris_mm: float, y_wall_mm: float,
                      w_inter_mm: float, d_via_mm: float = 1.5, p_via_mm: float = 3.0,
                      h_mm: float = 0.76, mesh_max: float = 2.5, mesh_min: float = 0.5,
                      out_name: str = "dmcasc_eig.msh", layout_name: str = "dualmode_cascade",
                      **extra) -> str:
    """`layout_name` selects any cascade-style via-layout from geometries.LAYOUTS
    (e.g. "dualmode_cascade_floatinter") -- `**extra` passes its own structural
    knobs through (e.g. y_wall_inter_mm)."""
    layout_fn = LAYOUTS[layout_name]
    vias, meta = layout_fn(a_mm=a_mm, w_iris_mm=w_iris_mm, x_iris_mm=x_iris_mm,
                           w_ext_mm=0.0, d_via_mm=d_via_mm, p_via_mm=p_via_mm,
                           y_wall_mm=y_wall_mm, w_inter_mm=w_inter_mm, **extra)
    half = meta["half"]
    Li = 2.0 * a_mm
    r = d_via_mm / 2.0

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("dmcasc_eig")
    occ = gmsh.model.occ
    box = occ.addBox(-r, -half - r, 0.0, Li + 2 * r, 2 * half + 2 * r, h_mm)
    cyls = [(3, occ.addCylinder(x, y, 0.0, 0, 0, h_mm, r)) for x, y in vias]
    occ.cut([(3, box)], cyls)
    occ.synchronize()

    vols = gmsh.model.getEntities(3)
    gmsh.model.addPhysicalGroup(3, [v[1] for v in vols], name="dielectric")
    surfs = gmsh.model.getBoundary(vols, oriented=False)
    gmsh.model.addPhysicalGroup(2, [s[1] for s in surfs], name="pec")

    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_min)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_max)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 16)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.mesh.generate(3)

    out = out_data(out_name)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.write(out)
    gmsh.finalize()
    return out


def run_eigenmode(spec: FilterSpec, params: dict, tag: str, n_modes: int = 8,
                  window: float = 0.6, device: str = "CPU",
                  layout_name: str = "dualmode_cascade") -> dict:
    """Closed-cavity eigenmode solve. device="CPU" is the safe default --
    "GPU" needs the same MFEM_MEMORY=cuda fix optimize.py's run_driven()
    applies (this mesh is ~2x a single dual-mode cavity's size, enough to
    trip the pooled-allocator OOM the fix avoids); not wired up here since
    this is a one-off diagnostic tool, not a repeated search.

    `params` beyond a/w_iris/x_iris/y_wall/w_inter_mm (e.g. y_wall_inter_mm
    for dualmode_cascade_floatinter) are passed through automatically."""
    known = {"a", "w_iris", "x_iris", "y_wall", "w_inter_mm"}
    extra = {k: v for k, v in params.items() if k not in known}
    mesh = build_closed_mesh(
        a_mm=params["a"], w_iris_mm=params["w_iris"], x_iris_mm=params["x_iris"],
        y_wall_mm=params["y_wall"], w_inter_mm=params["w_inter_mm"],
        h_mm=spec.substrate.h * 1000, out_name=f"{tag}.msh",
        layout_name=layout_name, **extra)
    cfg = {
        "Problem": {"Type": "Eigenmode", "Verbose": 1, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": [
            {"Attributes": [1], "Permeability": 1.0,
             "Permittivity": spec.substrate.eps_r, "LossTan": spec.substrate.tan_d}]},
        "Boundaries": {"PEC": {"Attributes": [2]}},
        "Solver": {"Device": device,
                   "Eigenmode": {"N": n_modes, "Save": 0,
                                "Target": spec.f0 / 1e9 - window,
                                "TargetUpper": spec.f0 / 1e9 + window,
                                "Tol": 1e-8, "Type": "SLEPc"}},
    }
    cfgp = out_data(f"{tag}.json")
    json.dump(cfg, open(cfgp, "w"), indent=2)
    palace = find_palace()
    env = dict(os.environ, PATH=f"{os.path.dirname(palace)}:{os.environ['PATH']}")
    if device == "GPU":
        env.update({"MFEM_MEMORY": "cuda"})  # see optimize.py's GPU_ENV docstring
    np_ranks = "1" if device == "GPU" else "4"
    logp = out_data(f"{tag}.log")
    subprocess.run([palace, "-np", np_ranks, os.path.basename(cfgp)],
                    cwd=out_data(""), env=env, stdout=open(logp, "w"),
                    stderr=subprocess.STDOUT, check=False)
    csv = out_data(f"postpro/{tag}/eig.csv")
    if not os.path.exists(csv):
        return {"ok": False, "log": logp}
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    freqs = np.sort(np.atleast_1d(d[d.dtype.names[1]]))
    try:
        os.remove(mesh)
    except OSError:
        pass
    return {"ok": True, "freqs_ghz": freqs.tolist()}


if __name__ == "__main__":
    spec = FilterSpec()
    params = dict(a=60.0, w_iris=17.0, x_iris=30.1, y_wall=9.0, w_inter_mm=12.0)
    print(run_eigenmode(spec, params, "cascade_eig_demo"))
