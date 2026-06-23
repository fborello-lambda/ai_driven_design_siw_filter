"""Parametric Gmsh mesh of TWO coupled SIW cavities -> eigenmode k extraction.

This is the Palace (FEM) counterpart of cst_export.py: same source of truth
(config.py / siw_geometry.py), but instead of emitting CST VBA it builds the
3D geometry with the Gmsh Python API and writes a .msh for a finite-element
eigenmode solve.

Why two closed cavities: the internal coupling k is extracted from the two
split resonances of a pair of identical cavities sharing one iris:
    k = (f2^2 - f1^2) / (f2^2 + f1^2)
A *closed* PEC cavity means EVERY boundary surface is PEC, so we sidestep the
usual pain of re-tagging faces after boolean cuts: tag the whole boundary "pec".

Run: uv run python palace_geometry.py [iris_mm]
Outputs output/data/siw_2cav.msh (+ prints mesh stats).
"""
from __future__ import annotations

import sys
import gmsh

from .config import SPEC, out_data
from .siw_geometry import build_geometry


def build_mesh(iris_mm: float | None = None, mesh_max: float = 2.0,
               mesh_min: float = 0.35, show_stats: bool = True) -> str:
    g = build_geometry(SPEC)
    a = g.a_siw * 1e3           # mm
    L = g.L_cav * 1e3
    r = SPEC.d_via / 2 * 1e3
    p = SPEC.p_via * 1e3
    h = SPEC.substrate.h * 1e3
    iris = iris_mm if iris_mm is not None else g.iris_widths[0] * 1e3
    half = a / 2.0
    Ltot = 2 * L                # two cavities along x

    # ---- via centres for the 2-cavity closed box ----
    import numpy as np
    vias: list[tuple[float, float]] = []
    n_side = max(1, round(Ltot / p))
    for x in np.linspace(0.0, Ltot, n_side + 1):       # side walls y = +/-half
        vias += [(x, half), (x, -half)]
    n_tr = max(1, round(a / p))
    ys = np.linspace(-half, half, n_tr + 1)
    for x in (0.0, Ltot):                              # end walls (closed)
        for y in ys:
            vias.append((x, y))
    for y in ys:                                       # middle iris (gap=iris)
        if abs(y) > iris / 2.0:
            vias.append((L, y))
    # dedupe overlapping corners
    kept: list[tuple[float, float]] = []
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= (0.9 * 2 * r) ** 2
               for kx, ky in kept):
            kept.append((x, y))

    # ---- gmsh model ----
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1 if show_stats else 0)
    gmsh.model.add("siw_2cav")
    occ = gmsh.model.occ

    # dielectric box, vias fully inside (margin r on every side)
    box = occ.addBox(-r, -half - r, 0.0, Ltot + 2 * r, a + 2 * r, h)
    cyls = [(3, occ.addCylinder(x, y, 0.0, 0, 0, h, r)) for x, y in kept]
    occ.cut([(3, box)], cyls)            # subtract vias -> PEC holes
    occ.synchronize()

    # ---- physical groups ----
    vols = gmsh.model.getEntities(3)
    gmsh.model.addPhysicalGroup(3, [v[1] for v in vols], name="dielectric")
    # closed cavity: every boundary surface is PEC
    surfs = gmsh.model.getBoundary(vols, oriented=False)
    gmsh.model.addPhysicalGroup(2, [s[1] for s in surfs], name="pec")

    # ---- mesh sizing ----
    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_min)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_max)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 16)  # resolve via curve
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)             # Delaunay
    gmsh.model.mesh.generate(3)

    out = out_data("siw_2cav.msh")
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)        # MFEM/Palace-friendly
    gmsh.write(out)

    if show_stats:
        ntet = len(gmsh.model.mesh.getElementsByType(4)[0])
        nnode = len(gmsh.model.mesh.getNodes()[0])
        print(f"\n--- 2-cavity mesh (iris={iris:.2f} mm) ---")
        print(f"  box {Ltot:.1f} x {a:.1f} x {h:.2f} mm, {len(kept)} vias")
        print(f"  nodes={nnode:,}  tets={ntet:,}")
        print(f"  WROTE {out}")
    gmsh.finalize()
    return out


if __name__ == "__main__":
    iris = float(sys.argv[1]) if len(sys.argv) > 1 else None
    build_mesh(iris_mm=iris)
