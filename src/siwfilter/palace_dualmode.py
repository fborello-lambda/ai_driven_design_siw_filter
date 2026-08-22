"""Isolated square SIW cavity with an internal perturbation via pair ->
eigenmode k extraction for a dual-mode resonator (2 poles from 1 physical
cavity).

Companion to palace_geometry.py's 2-cavity iris eigenmode setup, same idea:
a square SIW cavity supports a degenerate TE10n pair (n along either axis)
that don't couple to each other by symmetry. TE101 (this project's usual
single-mode formula) is NOT that pair -- swapping its own indices gives back
the same mode. The lowest genuinely degenerate pair is TE102/TE201 (m=1,p=2
vs m=2,p=1), confirmed empirically: a cavity sized for TE101 (a=39.45mm)
showed exactly one isolated mode near f0 with nothing else until +1.6GHz --
no degenerate partner, because there isn't one for that mode. For the square
cavity, f_mp = (c/2sqrt(er))*sqrt((m/a)^2+(p/a)^2), so TE102/TE201 needs
a = (c/2sqrt(er))*sqrt(5)/f0 -- a LARGER cavity (~61mm) than the single-mode
formula would give, since higher-order modes need more room. This makes the
dual-mode cavity bigger than a single-mode cavity on its own, so for a LOW
order filter (N=3: trading 2 single-mode cavities for 1 dual-mode) the net
length savings are more modest than for higher order (N=4+, more cavities
eliminated per dual-mode cavity added).

Perturbation: rather than cutting the boundary (tried first, see git
history -- also had a real bug: only the via *positions* moved, the
dielectric box shape didn't, so the box's own outer wall stayed a perfect
square and got tagged PEC anyway, making the "cut" nearly a no-op --
k=0.00065 at what should've been a moderate 6mm cut), two small internal
tuning vias are placed symmetrically on the cavity's main diagonal, off the
center. This keeps the outer boundary a clean, fully intact square (see
Zhang et al., Sci. Rep. 6:31922, Fig. 1, which uses the same idea) --
electrically it perturbs the two degenerate mode fields differently (they
have different field magnitude at an off-center, off-symmetry-axis point),
splitting and coupling them. No closed-form k(dp) relationship exists in the
literature (same story as iris-width<->k) -- swept and extracted via the
same eigenmode-split formula already validated for that:
    k = (f2^2 - f1^2) / (f2^2 + f1^2)
A *closed* PEC cavity means every boundary surface is PEC, so (like
palace_geometry.py) we sidestep re-tagging faces after boolean cuts: tag the
whole boundary "pec" and let Palace's eigenmode solver find the mode pair.

Run: uv run python -m siwfilter.palace_dualmode [dp_mm]
Outputs output/data/siw_dualmode.msh (+ prints mesh stats).
"""
from __future__ import annotations

import sys
import gmsh
import numpy as np

from .config import out_data

A_SIW_MM = 61.05    # square cavity side, sized for TE102/TE201 (see module docstring)

# Via size for this cavity specifically (bigger than the main filter's
# 0.8/1.5mm default, scoped to the dual-mode piece only -- see conversation:
# 1.5mm/3.0mm are both genuine standard PCB drill sizes (not arbitrary round
# numbers), give fewer holes / more spacing, and land nowhere near the
# a_eff/5, lambda_g/5 design-rule ceilings computed for this design (7.8mm,
# 15.3mm respectively).
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

    # ---- internal perturbation: a single transverse via row, perpendicular
    # to the port axis, at x=x_iris (distance `x_iris_mm` from the x=0 wall,
    # tunable -- default centered at a/2). The row does NOT reach the side
    # walls -- it stops short by `y_wall_mm` on each end (a real gap there,
    # not just the centered iris gap), leaving the row as a floating segment
    # rather than a full wall-to-wall partition. Same construction as the
    # main filter's own inter-cavity iris (transverse row + centered gap),
    # just placed inside a single cavity footprint AND held off the side
    # walls. w_iris_mm=None skips the row entirely -- bare/unperturbed
    # cavity, for checking whether a genuine degeneracy exists at all before
    # trusting any k(w_iris) sweep. w_iris_mm, x_iris_mm and y_wall_mm are
    # all meant to be free parameters for the optimizer. ----
    # Segments span EXACTLY [w_iris/2, half-y_wall] (continuous in both
    # w_iris_mm and y_wall_mm) rather than filtering a fixed a/p grid -- the
    # latter only lets these params take effect in ~p-sized jumps, which
    # fights a Bayesian optimizer's smoothness assumption (see
    # palace_dualmode_driven.py's _segment_vias for the same fix, applied
    # there first after a GP search stalled on this quantization).
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
