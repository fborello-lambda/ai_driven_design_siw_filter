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
import math
import gmsh
import numpy as np

from .config import SPEC, FilterSpec, out_data
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
               l_cavs_mm: list[float] | None = None,
               # Per-iris widths (one per internal iris, input->output order).
               # w_iris_mm sets every iris to the SAME width, which cannot
               # express the asymmetric coupling profile Chebyshev needs at
               # N>=4 (k23 is 26% weaker than k12/k34) -- see
               # topologies/cascade._n_iris_params. Takes precedence over
               # w_iris_mm when both are given.
               w_irises_mm: list[float] | None = None,
               with_sma: bool = False, sma_len_mm: float = 6.0,
               sma_rin_mm: float = 0.35, sma_rout_mm: float = 1.164,
               sma_eps_r: float = 2.08, sma_tand: float = 4.0e-4,
               preview: bool = False, render_png: str | None = None,
               spec: FilterSpec | None = None) -> dict:
    """
    with_sma=True replaces the bare microstrip WavePort at each feed end with a
    coax launch (pin r=sma_rin_mm, PTFE r=sma_rout_mm, eps_r=2.08 -> ~50 ohm by
    construction) soldered to the existing trace end.

    Default rin/rout (0.35/1.164mm): close to a real, in-stock, mainstream
    part -- Cinch/Johnson Components 142-0701-881 (DigiKey #210495), "SMA
    Jack, Board Edge, End Launch Solder," spec'd for 0.031in (0.79mm) PCB
    thickness (essentially this board, 0.76mm) with a 0.030in (0.381mm
    radius) round contact -- but backed off slightly from that exact 0.381mm
    to 0.35mm. Bisection found a razor-thin (~4 micron!) meshing/tolerance
    edge case in this geometry construction between rin=0.375mm (clean) and
    rin=0.379mm (extra spurious PEC faces appear, near-total reflection) --
    0.381mm sits right on that unstable edge. 0.35mm is safely clear of it,
    verified working (-13 to -46dB), and still realistic/smaller than the
    trace. rout is back-solved from the 50-ohm PTFE coax formula at that pin
    size (any SMA-family part is 50 ohm by definition, which fixes the
    ln(rout/rin) ratio). This replaces an earlier attempt that used full
    SMA/RG-401 body
    size (0.82/2.73mm) -- a pin that size is literally taller than this board
    (0.76mm) and gave near-total reflection (-0.2dB) even with a verified-
    correct port/connectivity setup; real connectors for thin boards use a
    proportionally thinner launch pin for exactly this reason, confirmed by
    this actual datasheet. The board edge (x=X0/X1) stays exactly where it
    was; the coax stub is new geometry bolted on beyond it, so the SIW/taper/feed pipeline
    is unchanged. The PTFE cylinder is clipped to z>=0 near the board edge
    only (not the whole stub -- clipping the whole thing severs the coax
    ring, killing the TEM mode) so its shell meets the bottom ground plane
    (the connector's ground flange/legs -- see calibration-status memory for
    why grounding matters: a wave port dropped straight on the microstrip
    self-normalizes to whatever the local trace impedance is, so it can't
    reveal a true 50-ohm mismatch).
    """
    spec = spec or SPEC
    g = build_geometry(spec)
    # ---- tuning overrides: reset dimensions then rebuild via/taper primitives ----
    _ovr = (l_cav_mm, w_iris_mm, w_ext_mm, w_ms_mm, l_taper_mm, l_feed_mm,
            l_cavs_mm, w_irises_mm)
    if any(v is not None for v in _ovr):
        from .siw_geometry import _build_primitives
        if l_cavs_mm is not None:
            g.L_cavs = [v * 1e-3 for v in l_cavs_mm]
        if l_cav_mm is not None:
            g.L_cav = l_cav_mm * 1e-3
        if w_irises_mm is not None:
            if len(w_irises_mm) != len(g.iris_widths):
                raise ValueError(
                    f"w_irises_mm has {len(w_irises_mm)} entries but this "
                    f"geometry has {len(g.iris_widths)} internal irises")
            g.iris_widths = [v * 1e-3 for v in w_irises_mm]
        elif w_iris_mm is not None:
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
    h = spec.substrate.h * MM
    r = spec.d_via / 2.0 * MM
    Xf = Lt + Lf                      # feed+taper length each side
    X0, X1 = -Xf, Li + Xf
    Xc0, Xc1 = X0 - sma_len_mm, X1 + sma_len_mm   # SMA coax port planes
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

    # ---- SMA coax launch stubs (standard RG-401/SMA size: pin r=sma_rin_mm,
    # PTFE r=sma_rout_mm, eps_r~2.08 -> ~50 ohm by construction). Bolted onto
    # the existing trace end at x=X0/X1; board/taper/feed geometry above is
    # untouched.
    #
    # Grounding the shell to z=0 needs care: clipping the WHOLE stub to z>=0
    # (as a first attempt did) severs the ring, because sma_rin_mm > h means
    # the clip plane cuts through the FULL annulus width at the bottom angle
    # (both the rin and rout points there sit below z=0) -- the shell becomes
    # a simply-connected "C" cross-section, not a ring around the pin hole.
    # A simply-connected port cross-section has no TEM solution (only
    # evanescent higher modes), confirmed against Palace's own coaxial
    # example (which finds clean TEM, Z_PV=50.0 ohm, on an unclipped ring).
    # Fix: only clip a short ground-contact segment right at the board edge;
    # the port face (at Xc0/Xc1) and most of the stub stay a full, proper
    # coax ring so the eigensolver finds the real TEM mode. ----
    ptfe_vols: list[tuple[int, int]] = []
    sma_caps: list[tuple[int, int]] = []
    sma_ground_mm = min(1.5, 0.4 * sma_len_mm)   # ground-contact segment length
    if with_sma:
        zlo = -(sma_rout_mm + 2.0)
        for x_edge, x_far in ((X0, Xc0), (X1, Xc1)):
            x0s, x1s = min(x_edge, x_far), max(x_edge, x_far)
            length = x1s - x0s
            pin = (3, occ.addCylinder(x0s, 0, h, length, 0, 0, sma_rin_mm))
            ptfe = (3, occ.addCylinder(x0s, 0, h, length, 0, 0, sma_rout_mm))

            sign = 1.0 if x_far > x_edge else -1.0
            gx0, gx1 = sorted([x_edge, x_edge + sign * sma_ground_mm])
            clipbox = (3, occ.addBox(gx0 - 0.1, -(sma_rout_mm + 2.0), zlo,
                                      (gx1 - gx0) + 0.2, 2 * (sma_rout_mm + 2.0),
                                      -zlo))
            cut, _ = occ.cut([ptfe], [pin, clipbox],
                             removeObject=True, removeTool=True)
            ptfe_vols += [(d, t) for d, t in cut if d == 3]

            cap = (2, occ.addDisk(x_edge, 0, h, sma_rin_mm, sma_rin_mm))
            occ.rotate([cap], x_edge, 0, h, 0, 1, 0, math.pi / 2)
            # clip to z>=0 too: sma_rin_mm > h means the disk otherwise pokes
            # a sliver below the board with no volume to embed into there ->
            # dangling face -> MFEM STable3D abort (same failure mode as an
            # unclipped via cut, see the note below). The cap sits exactly at
            # x_edge, inside the ground-clip segment, so this is consistent.
            cap_clip = (3, occ.addBox(x_edge - 0.5, -(sma_rin_mm + 1.0), zlo,
                                      1.0, 2 * (sma_rin_mm + 1.0), -zlo))
            cap_cut, _ = occ.cut([cap], [cap_clip], removeObject=True, removeTool=True)
            sma_caps += [(d, t) for d, t in cap_cut if d == 2]

    occ.synchronize()

    # ---- cut vias out of the substrate (PEC holes), THEN fragment with air +
    # trace sheets so all shared faces are conformal. (fragment+remove leaves
    # dangling via faces -> MFEM STable3D abort.) ----
    cut_out, _ = occ.cut([sub], cyls, removeObject=True, removeTool=True)
    occ.synchronize()
    sub_tags = [(d, t) for (d, t) in cut_out if d == 3]
    occ.fragment(sub_tags + ptfe_vols + [air_in, air_out],
                 [trace_in, trace_out] + sma_caps)
    occ.synchronize()

    via_centres = [(x * MM, y * MM) for x, y in via_xy]

    # ---- identify volumes: dielectric (slab 0<z<h), air (z>h), or the SMA
    # PTFE stubs (anything entirely outside the board footprint x<X0/x>X1).
    # Re-classified by geometry post-fragment rather than tracked tags, since
    # fragment can renumber/split entities. ----
    diel_clean, air_vols, sma_diel = [], [], []
    for dim, tag in gmsh.model.getEntities(3):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, tag)
        if with_sma and (cx < X0 - 1e-6 or cx > X1 + 1e-6):
            sma_diel.append(tag)
        elif cz < h:
            diel_clean.append(tag)
        else:
            air_vols.append(tag)

    # ---- physical groups: volumes ----
    gmsh.model.addPhysicalGroup(3, diel_clean, tag=1, name="dielectric")
    gmsh.model.addPhysicalGroup(3, air_vols, tag=2, name="air")
    if sma_diel:
        gmsh.model.addPhysicalGroup(3, sma_diel, tag=3, name="sma_ptfe")

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
        xmin, ymin_f, _, xmax, ymax_f, _ = gmsh.model.getBoundingBox(2, tag)
        adj_up, _ = gmsh.model.getAdjacencies(2, tag)
        is_boundary = len(adj_up) <= 1            # face on outer boundary

        on_via = any((cx - vx) ** 2 + (cy - vy) ** 2 < (1.3 * r) ** 2
                     for vx, vy in via_centres) and cz <= h + 1e-6

        # SMA coax stub faces: pin wall (r=rin) / PTFE shell (r=rout), both
        # curved cylindrical faces spanning the stub length; identified by
        # their y-extent (untouched by the z>=0 ground clip, since it only
        # cuts the bottom, at z=h>0) rather than centroid radius, which is
        # unreliable once the shell is clipped asymmetrically. The end cap
        # disk (pin-to-trace bridge) is identified by its small radius.
        on_sma_pin = on_sma_shell = on_sma_cap = False
        if with_sma:
            in_in_span = (Xc0 - 1e-3 <= xmin) and (xmax <= X0 + 1e-3)
            in_out_span = (X1 - 1e-3 <= xmin) and (xmax <= Xc1 + 1e-3)
            elongated = (xmax - xmin) > 0.3 * sma_len_mm
            yext = max(abs(ymin_f), abs(ymax_f))
            if (in_in_span or in_out_span) and elongated:
                if _near(yext, sma_rin_mm, 0.15):
                    on_sma_pin = True
                elif _near(yext, sma_rout_mm, 0.3):
                    on_sma_shell = True
            rad = math.hypot(cy, cz - h)
            # See palace_dualmode_driven.py for the full root-cause note: the
            # centroid-radius test alone misclassifies the clipped PTFE
            # annulus end-face as the pin cap once sma_rin_mm > ~0.3773mm,
            # tagging the coax dielectric PEC and shorting the launch. Gate it
            # on EXTENT too (cap spans ~rin, annulus spans ~rout).
            if ((_near(cx, X0) or _near(cx, X1)) and rad < sma_rin_mm * 1.05
                    and yext <= sma_rin_mm * 1.5):
                on_sma_cap = True

        if _near(cz, 0.0):                                    # bottom ground
            pec.append(tag)
        elif on_via or on_sma_pin or on_sma_shell or on_sma_cap:
            pec.append(tag)                                   # via/pin/shell/cap
        elif with_sma and _near(cx, Xc0) and xmax - xmin < 1e-3:
            wave_in.append(tag)                               # coax port (in)
        elif with_sma and _near(cx, Xc1) and xmax - xmin < 1e-3:
            wave_out.append(tag)                              # coax port (out)
        elif not with_sma and _near(cx, X0) and xmax - xmin < 1e-3:
            wave_in.append(tag)                               # microstrip port (in)
        elif not with_sma and _near(cx, X1) and xmax - xmin < 1e-3:
            wave_out.append(tag)                              # microstrip port (out)
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

    if preview:
        print(f"  faces: pec={len(pec)} port_in={len(wave_in)} "
              f"port_out={len(wave_out)} absorbing={len(absorbing)}"
              + (f"  sma_ptfe_vols={len(sma_diel)}" if with_sma else ""))
        print("  opening Gmsh GUI for a visual check (close the window to "
              "continue)...")
        gmsh.fltk.run()
        gmsh.finalize()
        return {"preview": True}

    if render_png:
        # offscreen shaded render (no interactive window needed): a fast 2D
        # surface mesh is enough to shade-render the CAD, no 3D tets needed.
        gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_min)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_max)
        gmsh.model.mesh.generate(2)
        gmsh.option.setNumber("Mesh.SurfaceFaces", 1)
        gmsh.option.setNumber("Mesh.SurfaceEdges", 0)
        gmsh.option.setNumber("Mesh.VolumeFaces", 0)
        gmsh.option.setNumber("Mesh.ColorCarousel", 2)   # color by physical group
        gmsh.option.setNumber("General.Trackball", 0)
        gmsh.option.setNumber("General.RotationX", 55)
        gmsh.option.setNumber("General.RotationY", 0)
        gmsh.option.setNumber("General.RotationZ", 20)
        gmsh.option.setNumber("General.Axes", 0)
        gmsh.fltk.initialize()
        gmsh.fltk.wait(0.5)
        gmsh.write(render_png)
        gmsh.finalize()
        return {"render_png": render_png}

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
    sma_info = None
    if with_sma:
        legend["sma_ptfe"] = 3
        # VoltagePath for the Palace WavePort config: [signal(pin), ground(shell)]
        # at the port cross-section, offset radially in +y (axisymmetric mode,
        # any radial direction works) -- mirrors examples/coaxial in the Palace
        # source tree.
        sma_info = {
            "rin_mm": sma_rin_mm, "rout_mm": sma_rout_mm,
            "eps_r": sma_eps_r, "tand": sma_tand,
            "port_in_x_mm": Xc0, "port_out_x_mm": Xc1,
            "voltage_path_in": [[Xc0, sma_rin_mm, h], [Xc0, sma_rout_mm, h]],
            "voltage_path_out": [[Xc1, sma_rin_mm, h], [Xc1, sma_rout_mm, h]],
        }
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
            "ports": (len(wave_in), len(wave_out)), "sma": sma_info}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=float, default=3.0, help="MeshSizeMax mm")
    ap.add_argument("--min", type=float, default=0.5, help="MeshSizeMin mm")
    ap.add_argument("--hair", type=float, default=8.0, help="air height / h")
    ap.add_argument("--no-wext", action="store_true", help="omit external iris")
    ap.add_argument("--out", default="siw_filter.msh", help="mesh filename")
    ap.add_argument("--sma", action="store_true",
                    help="replace the microstrip wave ports with SMA coax launches")
    ap.add_argument("--sma-len", type=float, default=6.0, help="coax stub length mm")
    ap.add_argument("--preview", action="store_true",
                    help="open the Gmsh GUI (color-coded groups) instead of meshing")
    args = ap.parse_args()
    build_mesh(mesh_max=args.max, mesh_min=args.min, h_air_factor=args.hair,
               with_wext=not args.no_wext, out_name=args.out,
               with_sma=args.sma, sma_len_mm=args.sma_len, preview=args.preview)
