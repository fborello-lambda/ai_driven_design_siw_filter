"""Isolated square SIW cavity with an internal perturbation via row ->
eigenmode k extraction for a dual-mode resonator (2 poles from 1 physical
cavity).

A square SIW cavity has a degenerate TE10n pair (n along either axis) that
doesn't couple by symmetry. TE101 is NOT that pair -- swapping its own
indices gives the same mode back. The lowest genuinely degenerate pair is
TE102/TE201, which needs a larger cavity (~61mm here) than the TE101 formula
gives, since higher-order modes need more room.

The internal perturbation is a floating via row on the cavity's transverse
axis rather than a boundary cut, so the outer square stays fully intact
(Zhang et al., Sci. Rep. 6:31922, Fig. 1) -- it perturbs the two degenerate
mode fields differently since they carry different magnitude off-axis,
splitting and coupling them. No closed-form k(row) relationship exists, so
k is swept and extracted the same way as the main iris:
    k = (f2^2 - f1^2) / (f2^2 + f1^2)
The cavity is closed (every boundary PEC), which avoids re-tagging faces
after the boolean cut -- tag the whole boundary "pec" and let Palace's
eigenmode solver find the pair.

Run: uv run python -m siwfilter.palace_dualmode [dp_mm]
Outputs output/data/siw_dualmode.msh (+ prints mesh stats).
"""
from __future__ import annotations

import sys
import gmsh
import numpy as np

from .config import out_data

A_SIW_MM = 61.05    # square cavity side, sized for TE102/TE201 (see module docstring)

# Standard PCB drill sizes, well inside the a_eff/5 and lambda_g/5 leakage
# ceilings for this design (7.8mm, 15.3mm) -- not arbitrary round numbers.
D_VIA_MM = 1.5
P_VIA_MM = 3.0


def build_mesh(a_mm: float | None = None, w_iris_mm: float | None = 6.0,
               x_iris_mm: float | None = None, y_wall_mm: float = 3.0,
               d_via_mm: float = D_VIA_MM, p_via_mm: float = P_VIA_MM,
               mesh_max: float = 2.0, mesh_min: float = 0.35, h_mm: float = 0.76,
               show_stats: bool = True, out_name: str = "siw_dualmode.msh") -> str:
    a = a_mm if a_mm is not None else A_SIW_MM
    r = d_via_mm / 2.0
    p = p_via_mm
    h = h_mm
    half = a / 2.0
    x_iris = x_iris_mm if x_iris_mm is not None else a / 2.0

    # ---- via centres for the closed square cavity (all 4 walls, intact) ----
    n = max(1, round(a / p))
    xs = np.linspace(0.0, a, n + 1)
    ys = np.linspace(-half, half, n + 1)
    vias: list[tuple[float, float]] = []
    for x in xs:                      # end walls x=0, x=a (full y range)
        vias.append((x, -half)); vias.append((x, half))
    for y in ys:                      # side walls y=+/-half (full x range)
        vias.append((0.0, y)); vias.append((a, y))

    # Internal perturbation: a transverse via row at x=x_iris, held off the
    # side walls by y_wall_mm on each end -- a floating segment, not a full
    # partition. w_iris_mm=None skips it (bare cavity, to check the
    # degeneracy exists before trusting a k(w_iris) sweep).
    #
    # Segments span EXACTLY [w_iris/2, half-y_wall], continuous in w_iris_mm
    # and y_wall_mm, rather than filtering a fixed a/p grid -- filtering only
    # lets these params act in p-sized jumps, which breaks a Bayesian
    # optimizer's smoothness assumption.
    if w_iris_mm is not None:
        lo, hi = w_iris_mm / 2.0, half - y_wall_mm
        if hi > lo:
            n_int = max(1, round((hi - lo) / p))
            for yv in np.linspace(lo, hi, n_int + 1):
                vias.append((x_iris, yv)); vias.append((x_iris, -yv))

    # dedupe overlapping/near-coincident vias
    final: list[tuple[float, float]] = []
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= (0.9 * 2 * r) ** 2
               for kx, ky in final):
            final.append((x, y))

    # ---- gmsh model ----
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1 if show_stats else 0)
    gmsh.model.add("siw_dualmode")
    occ = gmsh.model.occ

    box = occ.addBox(-r, -half - r, 0.0, a + 2 * r, a + 2 * r, h)
    cyls = [(3, occ.addCylinder(x, y, 0.0, 0, 0, h, r)) for x, y in final]
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

    if show_stats:
        ntet = len(gmsh.model.mesh.getElementsByType(4)[0])
        nnode = len(gmsh.model.mesh.getNodes()[0])
        w_str = f"{w_iris_mm:.2f}mm" if w_iris_mm is not None else "None (bare)"
        print(f"\n--- dual-mode square cavity (a={a:.2f}mm, w_iris={w_str}, "
              f"x_iris={x_iris:.2f}mm, y_wall={y_wall_mm:.2f}mm, d_via={d_via_mm}mm) ---")
        print(f"  {len(final)} vias")
        print(f"  nodes={nnode:,}  tets={ntet:,}")
        print(f"  WROTE {out}")
    gmsh.finalize()
    return out


if __name__ == "__main__":
    w = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    build_mesh(w_iris_mm=w)
