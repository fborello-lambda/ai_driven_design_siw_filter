"""Parametric Gmsh mesh of the FULL 3-cavity SIW filter for a Palace DRIVEN solve.

Counterpart to palace_geometry.py (which does the closed 2-cavity eigenmode for
internal k). This one includes the microstrip FEED + TAPER and two microstrip
WAVE PORTS at the feed ends, so Palace computes S11/S21 with *modal* ports (like
CST). External coupling Qe then follows from the group delay of S11.

Geometry / BC model
-------------------
- Substrate dielectric box, z in [0, h].  Bottom face z=0 = PEC ground (full).
- Over the SIW region x in [0, Li] the top is a SOLID ground plane (PEC at z=h)
  -> no air needed there (fields are enclosed in the dielectric).
- Over the two feed regions the microstrip is an OPEN line: a copper trace sheet
  (taper+feed outline) embedded at z=h = PEC, with an AIR box above it for the
  quasi-TEM mode. Only these two short regions carry air -> keeps the mesh small.
- Vias (incl. external-iris vias) = PEC cylinders in the substrate.
- Feed-end cross-sections x=X0 and x=X1 (substrate + air) = WAVE PORTS.
- Remaining outer air faces + exposed substrate edges = Absorbing (radiation).

Memory note: target machine has ~7 GB RAM. Mesh is kept deliberately coarse and
the Palace solve runs at Order 1. Generate-only first to check tet count.

Run:  uv run python palace_driven.py            # mesh only, prints stats
      uv run python palace_driven.py --max 3.5  # coarser
Outputs output/data/siw_filter.msh (+ a tag legend printed for the .json).
"""
from __future__ import annotations

import argparse
import gmsh
import numpy as np

from .config import SPEC, out_data
from .siw_geometry import build_geometry

MM = 1e3


def _near(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) < tol


def build_mesh(mesh_max: float = 3.0, mesh_min: float = 0.5,
               h_air_factor: float = 8.0, with_wext: bool = True,
               out_name: str = "siw_filter.msh", show: bool = True,
               l_cav_mm: float | None = None, w_iris_mm: float | None = None,
               w_ext_mm: float | None = None, w_ms_mm: float | None = None,
               l_taper_mm: float | None = None, l_feed_mm: float | None = None,
               l_cavs_mm: list[float] | None = None) -> dict:
    g = build_geometry(SPEC)
    # ---- tuning overrides: reset dimensions then rebuild via/taper primitives ----
    _ovr = (l_cav_mm, w_iris_mm, w_ext_mm, w_ms_mm, l_taper_mm, l_feed_mm, l_cavs_mm)
    if any(v is not None for v in _ovr):
        from .siw_geometry import _build_primitives
        if l_cavs_mm is not None:
            g.L_cavs = [v * 1e-3 for v in l_cavs_mm]
        if l_cav_mm is not None:
            g.L_cav = l_cav_mm * 1e-3
        if w_iris_mm is not None:
            g.iris_widths = [w_iris_mm * 1e-3] * len(g.iris_widths)
        if w_ext_mm is not None:
            g.w_ext = w_ext_mm * 1e-3
        if w_ms_mm is not None:
            g.W_ms = w_ms_mm * 1e-3
        if l_taper_mm is not None:
            g.L_taper = l_taper_mm * 1e-3
        if l_feed_mm is not None:
            g.L_feed = l_feed_mm * 1e-3
        _build_primitives(g)
    half = g.a_siw / 2.0 * MM
    Li = g.L_inner * MM
    Lt = g.L_taper * MM
    Lf = g.L_feed * MM
    W = g.W_ms * MM
    h = SPEC.substrate.h * MM
    r = SPEC.d_via / 2.0 * MM
    Xf = Lt + Lf                      # feed+taper length each side
    X0, X1 = -Xf, Li + Xf
    ym = half + 3.0                   # substrate side margin (board outline)
    Hair = h_air_factor * h

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1 if show else 0)
    gmsh.model.add("siw_filter")
    occ = gmsh.model.occ

    # ---- volumes ----
    sub = (3, occ.addBox(X0, -ym, 0.0, X1 - X0, 2 * ym, h))
    air_in = (3, occ.addBox(X0, -ym, h, Xf, 2 * ym, Hair))
    air_out = (3, occ.addBox(Li, -ym, h, Xf, 2 * ym, Hair))

    # ---- via cylinders (main walls + optional external-iris rows) ----
    via_xy = list(g.vias) + (list(g.ext_iris_vias) if with_wext else [])
    cyls = [(3, occ.addCylinder(x * MM, y * MM, 0.0, 0, 0, h, r))
            for x, y in via_xy]

    # ---- microstrip trace sheets at z=h (taper+feed merged outline) ----
    def trace_surface(sign_out: float, x_in: float, x_taper: float,
                      x_siw: float) -> int:
        # outline: feed end -> taper -> full a_siw width at SIW edge -> back
        pts = [(x_in, +W / 2), (x_taper, +W / 2), (x_siw, +half),
               (x_siw, -half), (x_taper, -W / 2), (x_in, -W / 2)]
        tags = [occ.addPoint(px, py, h) for px, py in pts]
        lines = [occ.addLine(tags[i], tags[(i + 1) % len(tags)])
                 for i in range(len(tags))]
        wire = occ.addCurveLoop(lines)
        return occ.addPlaneSurface([wire])

    trace_in = (2, trace_surface(-1.0, X0, -Lt, 0.0))
    trace_out = (2, trace_surface(+1.0, X1, Li + Lt, Li))

    occ.synchronize()

    # ---- cut vias out of the substrate (PEC holes), THEN fragment with air +
    # trace sheets so all shared faces are conformal. (fragment+remove leaves
    # dangling via faces -> MFEM STable3D abort.) ----
    cut_out, _ = occ.cut([sub], cyls, removeObject=True, removeTool=True)
    occ.synchronize()
    sub_tags = [(d, t) for (d, t) in cut_out if d == 3]
    occ.fragment(sub_tags + [air_in, air_out], [trace_in, trace_out])
    occ.synchronize()

    via_centres = [(x * MM, y * MM) for x, y in via_xy]

    # ---- identify volumes: dielectric (slab 0<z<h) vs air (z>h) ----
    diel_clean, air_vols = [], []
    for dim, tag in gmsh.model.getEntities(3):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, tag)
        if cz < h:
            diel_clean.append(tag)
        else:
            air_vols.append(tag)

    # ---- physical groups: volumes ----
    gmsh.model.addPhysicalGroup(3, diel_clean, tag=1, name="dielectric")
    gmsh.model.addPhysicalGroup(3, air_vols, tag=2, name="air")

    # trace outlines (z=h, in mm) for point-in-polygon metal test
    def _outline(x_in, x_taper, x_siw):
        return np.array([(x_in, +W / 2), (x_taper, +W / 2), (x_siw, +half),
                         (x_siw, -half), (x_taper, -W / 2), (x_in, -W / 2)])
    trace_polys = [_outline(X0, -Lt, 0.0), _outline(X1, Li + Lt, Li)]

    def _in_poly(px, py, poly) -> bool:
        n = len(poly); inside = False; j = n - 1
        for i in range(n):
            xi, yi = poly[i]; xj, yj = poly[j]
            if ((yi > py) != (yj > py)) and \
               (px < (xj - xi) * (py - yi) / (yj - yi + 1e-30) + xi):
                inside = not inside
            j = i
        return inside

    # ---- classify boundary surfaces ----
    pec, wave_in, wave_out, absorbing = [], [], [], []
    for dim, tag in gmsh.model.getEntities(2):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(2, tag)
        xmin, _, _, xmax, _, _ = gmsh.model.getBoundingBox(2, tag)
        adj_up, _ = gmsh.model.getAdjacencies(2, tag)
        is_boundary = len(adj_up) <= 1            # face on outer boundary

        on_via = any((cx - vx) ** 2 + (cy - vy) ** 2 < (1.3 * r) ** 2
                     for vx, vy in via_centres) and cz <= h + 1e-6

        if _near(cz, 0.0):                                    # bottom ground
            pec.append(tag)
        elif on_via:                                          # via wall
            pec.append(tag)
        elif _near(cx, X0) and xmax - xmin < 1e-3:            # input port face
            wave_in.append(tag)
        elif _near(cx, X1) and xmax - xmin < 1e-3:            # output port face
            wave_out.append(tag)
        elif _near(cz, h):                                    # z=h plane
            if 0.0 - 1e-6 <= cx <= Li + 1e-6:                 # SIW top ground
                pec.append(tag)
            elif any(_in_poly(cx, cy, poly) for poly in trace_polys):
                pec.append(tag)                               # microstrip trace
            # else: open substrate/air interface -> no BC (internal)
        elif is_boundary:                                     # outer air/diel
            absorbing.append(tag)

    pec = sorted(set(pec))
    absorbing = sorted(set(absorbing) - set(pec) - set(wave_in) - set(wave_out))

    gmsh.model.addPhysicalGroup(2, pec, tag=10, name="pec")
    gmsh.model.addPhysicalGroup(2, wave_in, tag=11, name="port_in")
    gmsh.model.addPhysicalGroup(2, wave_out, tag=12, name="port_out")
    gmsh.model.addPhysicalGroup(2, absorbing, tag=13, name="absorbing")

    # ---- mesh sizing ----
    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_min)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_max)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 10)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.mesh.generate(3)

    out = out_data(out_name)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.write(out)

    ntet = len(gmsh.model.mesh.getElementsByType(4)[0])
    nnode = len(gmsh.model.mesh.getNodes()[0])
    legend = {"dielectric": 1, "air": 2, "pec": 10, "port_in": 11,
              "port_out": 12, "absorbing": 13}
    if show:
        print(f"\n--- full-filter driven mesh ---")
        print(f"  box x[{X0:.1f},{X1:.1f}] y[{-ym:.1f},{ym:.1f}] z[0,{h:.2f}] "
              f"+ air {Hair:.1f} over feeds")
        print(f"  vias={len(via_xy)}  diel_vols={len(diel_clean)} "
              f"air_vols={len(air_vols)}")
        print(f"  faces: pec={len(pec)} port_in={len(wave_in)} "
              f"port_out={len(wave_out)} absorbing={len(absorbing)}")
        print(f"  nodes={nnode:,}  tets={ntet:,}")
        # crude memory estimate: Order-1 ND unknowns ~ #edges ~ 6*nnode; the
        # 2-cav ref was 577k edges -> 5.5 GB. Scale linearly.
        approx_edges = 6.0 * nnode
        est_gb = 5.5 * approx_edges / 576953.0
        print(f"  ~edges≈{approx_edges:,.0f} -> EST peak ≈ {est_gb:.1f} GB "
              f"(7 GB ceiling) at Order 1")
        print(f"  tag legend: {legend}")
        print(f"  WROTE {out}")
    gmsh.finalize()
    return {"mesh": out, "tets": ntet, "nodes": nnode, "legend": legend,
            "ports": (len(wave_in), len(wave_out))}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=float, default=3.0, help="MeshSizeMax mm")
    ap.add_argument("--min", type=float, default=0.5, help="MeshSizeMin mm")
    ap.add_argument("--hair", type=float, default=8.0, help="air height / h")
    ap.add_argument("--no-wext", action="store_true", help="omit external iris")
    ap.add_argument("--out", default="siw_filter.msh", help="mesh filename")
    args = ap.parse_args()
    build_mesh(mesh_max=args.max, mesh_min=args.min, h_air_factor=args.hair,
               with_wext=not args.no_wext, out_name=args.out)
