"""Driven (2-port, real feed) model of the isolated dual-mode square cavity,
IN-LINE port placement: both openings on opposite walls (x=0 input, x=a
output), centered on the same y=0 axis, "one in front of the other" -- same
axis convention as the rest of the filter chain (palace_driven.py's 3-cavity
model also puts both ports at x=X0/x=X1 on one axis), so this cavity can
slot into that same cascade later instead of needing a bent/L-shaped board.

Feed = Deslandes taper, same as the main filter (palace_driven.py): the
microstrip trace stays at the true 50-ohm width W_ms near the SMA connector
(so the connector match doesn't get broken), then flares out over length
L_taper to the FULL cavity wall width at x=0/x=a. The via-fence wall
OPENING (w_ext) is an independent parameter, narrower than the full flare --
same as the main filter's own external iris: the copper overhangs the solid
part of the via wall, only the w_ext gap actually couples fields into the
cavity. (An earlier version pinned w_ext=W_ms directly, no flare -- a 25-eval
Bayesian search over that topology never found a design with more than
-24dB peak S21 anywhere in a wide 5D box; decoupling the two, like the main
filter already does successfully, is the fix.)

INTERNAL iris: a single transverse via row perpendicular to the port axis,
at x=x_iris (tunable distance from the x=0 wall, default a/2), floating
between the two side walls (held off by y_wall on each end, not a full
partition), with a centered gap of width w_iris. This is the secondary
tuning control (mode-splitting/internal coupling), on top of the external
w_ext/w_ms feed match.

Run: uv run python -m siwfilter.palace_dualmode_driven --preview
"""
from __future__ import annotations

import argparse
import math

import gmsh
import numpy as np

from .config import SPEC, VIA_PRESETS, out_data, out_img
from .siw_geometry import microstrip_width_50ohm, microstrip_eps_eff, microstrip_guided_wavelength
from .palace_dualmode import A_SIW_MM, D_VIA_MM, P_VIA_MM

MM = 1e3


def _near(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) < tol


def _dims(a_mm, w_ms_mm, l_taper_mm, l_feed_mm):
    # NOTE: deliberately NOT using siw_geometry.build_geometry(SPEC).W_ms --
    # that returns the STALE pre-SMA-fix W_ms=2.26mm from config.py's
    # OPTIMIZED_DESIGN cache (tuned against an idealized self-normalizing
    # port, ~41 ohm, not real 50 ohm -- see docs/sma_connector/README.md).
    # Recompute the true 50-ohm width directly instead.
    sub = SPEC.substrate
    W = w_ms_mm if w_ms_mm is not None else microstrip_width_50ohm(sub.eps_r, sub.h) * MM
    eps_eff_ms = microstrip_eps_eff(sub.eps_r, sub.h, W / MM)
    lambda_g_ms = microstrip_guided_wavelength(SPEC.f0, eps_eff_ms) * MM
    Lt = l_taper_mm if l_taper_mm is not None else lambda_g_ms / 4.0
    Lf = l_feed_mm if l_feed_mm is not None else lambda_g_ms / 4.0
    return W, Lt, Lf


def _segment_vias(lo: float, hi: float, p: float) -> np.ndarray:
    """Evenly-spaced positions spanning EXACTLY [lo, hi] (inclusive), pitch
    ~p. Endpoints move continuously with lo/hi -- unlike filtering a fixed
    a/p grid (the previous approach), this makes gap-width parameters
    (w_ext, w_iris, y_wall) genuinely continuous instead of only taking
    effect in ~p-sized steps when a threshold crosses a fixed grid point."""
    if hi <= lo:
        return np.array([])
    n = max(1, round((hi - lo) / p))
    return np.linspace(lo, hi, n + 1)


def _via_layout(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm, y_wall_mm=3.0):
    """Pure-geometry via-position computation, shared by build_mesh (gmsh)
    and plot_layout_2d (matplotlib) so the two never drift apart."""
    Li = a_mm
    half = a_mm / 2.0
    r = d_via_mm / 2.0
    p = p_via_mm
    x_iris = x_iris_mm if x_iris_mm is not None else a_mm / 2.0

    n = max(1, round(Li / p))
    xs = np.linspace(0.0, Li, n + 1)
    vias: list[tuple[float, float]] = []
    # external wall gaps: segments span EXACTLY [w_ext/2, half] (continuous
    # in w_ext_mm), not a filtered fixed grid.
    for o in _segment_vias(w_ext_mm / 2.0, half, p):
        vias.append((0.0, o)); vias.append((0.0, -o))
        vias.append((Li, o)); vias.append((Li, -o))
    for xv in xs:
        vias.append((xv, -half))
        vias.append((xv, half))
    # internal iris row: floats between the two side walls, held off by
    # y_wall_mm at each end (not a full wall-to-wall partition), with a
    # centered gap of width w_iris_mm -- see palace_dualmode.py for why.
    # Segments span EXACTLY [w_iris/2, half-y_wall] (continuous in both).
    if w_iris_mm is not None:
        for o in _segment_vias(w_iris_mm / 2.0, half - y_wall_mm, p):
            vias.append((x_iris, o)); vias.append((x_iris, -o))

    final: list[tuple[float, float]] = []
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= (0.9 * 2 * r) ** 2
               for kx, ky in final):
            final.append((x, y))
    return final, x_iris


def build_mesh(a_mm: float = A_SIW_MM, w_iris_mm: float = 6.0, x_iris_mm: float | None = None,
               y_wall_mm: float = 3.0,
               d_via_mm: float = D_VIA_MM, p_via_mm: float = P_VIA_MM,
               h_mm: float | None = None, w_ext_mm: float | None = None,
               w_ms_mm: float | None = None, l_taper_mm: float | None = None,
               l_feed_mm: float | None = None, h_air_factor: float = 8.0,
               with_sma: bool = True, sma_len_mm: float = 6.0,
               sma_rin_mm: float = 0.35, sma_rout_mm: float = 1.164,
               sma_eps_r: float = 2.08, sma_tand: float = 4.0e-4,
               gnd_stitch: bool = False, n_gnd_stitch: int = 3,
               gnd_stitch_offset_mm: float = 2.62,
               gnd_stitch_pitch_mm: float = VIA_PRESETS["gnd_stitch"]["p_mm"],
               gnd_clearance_mm: float = 0.3,
               gnd_via_d_mm: float = VIA_PRESETS["gnd_stitch"]["d_mm"],
               mesh_max: float = 1.5, mesh_min: float = 0.4,
               out_name: str = "dualmode_driven.msh",
               preview: bool = False, render_png: str | None = None,
               render_hide_air: bool = True,
               show: bool = True, rot_xyz: tuple[float, float, float] = (55, 0, 20)) -> dict:
    W, Lt, Lf = _dims(a_mm, w_ms_mm, l_taper_mm, l_feed_mm)
    Xf = Lt + Lf
    we = w_ext_mm if w_ext_mm is not None else 25.0   # external iris gap, independent of W

    Li = a_mm
    half = a_mm / 2.0
    r = d_via_mm / 2.0
    eps_r, tand = SPEC.substrate.eps_r, SPEC.substrate.tan_d

    X0, X1 = -Xf, Li + Xf
    Xc0, Xc1 = X0 - sma_len_mm, X1 + sma_len_mm
    ym = half + 3.0
    Hair = h_air_factor * (h_mm if h_mm is not None else SPEC.substrate.h * MM)
    h = h_mm if h_mm is not None else SPEC.substrate.h * MM

    final, x_iris = _via_layout(a_mm, w_iris_mm, x_iris_mm, we, d_via_mm, p_via_mm, y_wall_mm)

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1 if show else 0)
    gmsh.model.add("dualmode_driven")
    occ = gmsh.model.occ

    sub = (3, occ.addBox(X0, -ym, 0.0, X1 - X0, 2 * ym, h))
    air_in = (3, occ.addBox(X0, -ym, h, Xf, 2 * ym, Hair))
    air_out = (3, occ.addBox(Li, -ym, h, Xf, 2 * ym, Hair))

    cyls = [(3, occ.addCylinder(x, y, 0.0, 0, 0, h, r)) for x, y in final]

    # ---- microstrip trace: straight 50-ohm feed (width W) from the port to
    # x_taper, then a Deslandes flare from W up to the FULL cavity wall
    # width (+-half) at the SIW edge -- same shape as palace_driven.py's
    # trace_surface. The via-fence gap (we) is independent and narrower,
    # sitting within this flared footprint (copper overhangs the solid part
    # of the wall). ----
    def trace_surface(x_in: float, x_taper: float, x_siw: float) -> int:
        pts = [(x_in, +W / 2), (x_taper, +W / 2), (x_siw, +half),
               (x_siw, -half), (x_taper, -W / 2), (x_in, -W / 2)]
        tags = [occ.addPoint(px, py, h) for px, py in pts]
        lines = [occ.addLine(tags[i], tags[(i + 1) % len(tags)]) for i in range(len(tags))]
        return occ.addPlaneSurface([occ.addCurveLoop(lines)])

    trace_in = (2, trace_surface(X0, -Lt, 0.0))
    trace_out = (2, trace_surface(X1, Li + Lt, Li))

    # ---- connector ground: top-side pour + stitching vias ----
    # The Taoglas EMPCB.SMAFSTJ.B.HT grounds through 4 discrete legs at the
    # board edge (+-2.62mm either side of the centre signal pad), not the
    # continuous ring the bare coax stub models. Without top-side copper in
    # the feed span there is nothing for those legs to land on, and the
    # return path has to detour to the bottom plane -- so this adds real
    # coplanar ground beside the trace plus vias tying it down, which is what
    # the fabricated board will actually have. Off by default: it changes the
    # feed environment, so every design tuned against the old model stays
    # reproducible until explicitly re-tuned with it.
    gnd_polys: list[np.ndarray] = []
    gnd_surfs: list[tuple[int, int]] = []
    gnd_via_centres: list[tuple[float, float]] = []
    if gnd_stitch:
        # DISCRETE PADS, not a continuous pour. The datasheet footprint has two
        # ground pads per face flanking the centre signal pad -- and modelling
        # it as a full-length pour is not just less faithful, it is wrong: the
        # stitch vias at +-2.62mm (r=0.75 -> inner edge 1.87mm) cap the usable
        # clearance at ~1.04mm = 1.37*h, close enough to turn the 50-ohm
        # microstrip into a grounded coplanar line and detune the very match
        # this connector model exists to study. Localised pads keep the feed a
        # true microstrip and confine the coplanar perturbation to the ~few mm
        # right at the launch, which is what the real board does.
        # Stitching vias get their OWN diameter: the SIW fence uses d_via_mm
        # (1.5mm here, sized for the cavity wall), which is far larger than a
        # real stitching via (~0.3mm drill / 0.6mm finished on JLCPCB). Reusing
        # the fence size wasted pad area and capped the via count -- smaller
        # barrels let several fit per pad, which is the point: more parallel
        # vias = lower ground-return inductance at the launch.
        rg = gnd_via_d_mm / 2.0
        pad_margin = 0.25                      # copper beyond the via barrel
        y_lo = gnd_stitch_offset_mm - rg - pad_margin
        y_hi = gnd_stitch_offset_mm + rg + pad_margin
        n_st = max(0, n_gnd_stitch)
        for x_edge, sign in ((X0, +1.0), (X1, -1.0)):
            x_first = x_edge + sign * (rg + pad_margin)
            x_last = x_first + sign * max(0, n_st - 1) * gnd_stitch_pitch_mm
            xa, xb = sorted([x_edge, x_last + sign * (rg + pad_margin)])
            for sgn in (+1.0, -1.0):
                ys = sorted([sgn * y_lo, sgn * y_hi])
                if min(abs(ys[0]), abs(ys[1])) <= W / 2.0 + gnd_clearance_mm:
                    continue          # would encroach on the trace clearance
                if max(abs(ys[0]), abs(ys[1])) > ym:
                    continue          # off the board
                poly = np.array([(xa, ys[0]), (xb, ys[0]), (xb, ys[1]), (xa, ys[1])])
                gnd_polys.append(poly)
                pts = [occ.addPoint(px, py, h) for px, py in poly]
                ln = [occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
                gnd_surfs.append((2, occ.addPlaneSurface([occ.addCurveLoop(ln)])))
            for k in range(n_st):
                xv = x_first + sign * k * gnd_stitch_pitch_mm
                for sgn in (+1.0, -1.0):
                    yv = sgn * gnd_stitch_offset_mm
                    if abs(yv) - rg <= W / 2.0 + gnd_clearance_mm or abs(yv) > ym - rg:
                        continue
                    gnd_via_centres.append((xv, yv))
        cyls += [(3, occ.addCylinder(x, y, 0.0, 0, 0, h, rg)) for x, y in gnd_via_centres]

    # ---- SMA coax launch stubs (same construction as palace_driven.py) ----
    ptfe_vols: list[tuple[int, int]] = []
    sma_caps: list[tuple[int, int]] = []
    sma_ground_mm = min(1.5, 0.4 * sma_len_mm)
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
                                      (gx1 - gx0) + 0.2, 2 * (sma_rout_mm + 2.0), -zlo))
            cut, _ = occ.cut([ptfe], [pin, clipbox], removeObject=True, removeTool=True)
            ptfe_vols += [(dd, t) for dd, t in cut if dd == 3]

            cap = (2, occ.addDisk(x_edge, 0, h, sma_rin_mm, sma_rin_mm))
            occ.rotate([cap], x_edge, 0, h, 0, 1, 0, math.pi / 2)
            cap_clip = (3, occ.addBox(x_edge - 0.5, -(sma_rin_mm + 1.0), zlo,
                                      1.0, 2 * (sma_rin_mm + 1.0), -zlo))
            cap_cut, _ = occ.cut([cap], [cap_clip], removeObject=True, removeTool=True)
            sma_caps += [(dd, t) for dd, t in cap_cut if dd == 2]

    occ.synchronize()

    cut_out, _ = occ.cut([sub], cyls, removeObject=True, removeTool=True)
    occ.synchronize()
    sub_tags = [(dd, t) for (dd, t) in cut_out if dd == 3]
    occ.fragment(sub_tags + ptfe_vols + [air_in, air_out],
                 [trace_in, trace_out] + sma_caps + gnd_surfs)
    occ.synchronize()

    via_centres = final + gnd_via_centres

    diel_clean, air_vols, sma_diel = [], [], []
    for dim, tag in gmsh.model.getEntities(3):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, tag)
        if with_sma and (cx < X0 - 1e-6 or cx > X1 + 1e-6):
            sma_diel.append(tag)
        elif cz < h:
            diel_clean.append(tag)
        else:
            air_vols.append(tag)

    gmsh.model.addPhysicalGroup(3, diel_clean, tag=1, name="dielectric")
    gmsh.model.addPhysicalGroup(3, air_vols, tag=2, name="air")
    if sma_diel:
        gmsh.model.addPhysicalGroup(3, sma_diel, tag=3, name="sma_ptfe")

    def _outline(x_in, x_taper, x_siw):
        return np.array([(x_in, +W / 2), (x_taper, +W / 2), (x_siw, +half),
                         (x_siw, -half), (x_taper, -W / 2), (x_in, -W / 2)])
    # Ground pour counts as copper for face classification, exactly like the
    # trace -- both are PEC sheets at z=h, just electrically distinct nets.
    trace_polys = [_outline(X0, -Lt, 0.0), _outline(X1, Li + Lt, Li)] + gnd_polys

    def _in_poly(px, py, poly) -> bool:
        n = len(poly); inside = False; j = n - 1
        for i in range(n):
            xi, yi = poly[i]; xj, yj = poly[j]
            if ((yi > py) != (yj > py)) and \
               (px < (xj - xi) * (py - yi) / (yj - yi + 1e-30) + xi):
                inside = not inside
            j = i
        return inside

    pec, wave_in, wave_out, absorbing = [], [], [], []
    for dim, tag in gmsh.model.getEntities(2):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(2, tag)
        xmin, ymin_f, _, xmax, ymax_f, _ = gmsh.model.getBoundingBox(2, tag)
        adj_up, _ = gmsh.model.getAdjacencies(2, tag)
        is_boundary = len(adj_up) <= 1

        on_via = any((cx - vx) ** 2 + (cy - vy) ** 2 < (1.3 * r) ** 2
                     for vx, vy in via_centres) and cz <= h + 1e-6

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
            # The centroid-radius test alone is NOT sufficient: clipping the
            # PTFE bottom (z>=0 ground contact) pulls the annulus end-face's
            # centroid up toward the pin axis, to rad~0.396mm. Since the
            # threshold scales with sma_rin_mm, it crosses that value at
            # rin~0.3773mm and the coax DIELECTRIC cross-section gets tagged
            # PEC -- shorting the coax, giving near-total reflection
            # (S21~-80dB). That is the "razor-thin meshing instability"
            # documented in docs/sma_connector/README.md (found there by
            # bisection at 0.375/0.379 and only avoided, never explained);
            # it is a classification bug, not a meshing tolerance, and it
            # blocks the real Taoglas EMPCB.SMAFSTJ.B.HT pin (0.38mm).
            # Disambiguate by EXTENT, which is unambiguous: the real cap disk
            # spans ~rin, the PTFE annulus spans ~rout.
            if ((_near(cx, X0) or _near(cx, X1)) and rad < sma_rin_mm * 1.05
                    and yext <= sma_rin_mm * 1.5):
                on_sma_cap = True

        if _near(cz, 0.0):
            pec.append(tag)
        elif on_via or on_sma_pin or on_sma_shell or on_sma_cap:
            pec.append(tag)
        elif with_sma and _near(cx, Xc0) and xmax - xmin < 1e-3:
            wave_in.append(tag)
        elif with_sma and _near(cx, Xc1) and xmax - xmin < 1e-3:
            wave_out.append(tag)
        elif not with_sma and _near(cx, X0) and xmax - xmin < 1e-3:
            wave_in.append(tag)
        elif not with_sma and _near(cx, X1) and xmax - xmin < 1e-3:
            wave_out.append(tag)
        elif _near(cz, h):
            if 0.0 - 1e-6 <= cx <= Li + 1e-6:
                pec.append(tag)                               # cavity top ground
            elif any(_in_poly(cx, cy, poly) for poly in trace_polys):
                pec.append(tag)                                # microstrip trace
        elif is_boundary:
            absorbing.append(tag)

    pec = sorted(set(pec))
    absorbing = sorted(set(absorbing) - set(pec) - set(wave_in) - set(wave_out))

    gmsh.model.addPhysicalGroup(2, pec, tag=10, name="pec")
    gmsh.model.addPhysicalGroup(2, wave_in, tag=11, name="port_in")
    gmsh.model.addPhysicalGroup(2, wave_out, tag=12, name="port_out")
    gmsh.model.addPhysicalGroup(2, absorbing, tag=13, name="absorbing")

    if preview:
        print(f"  faces: pec={len(pec)} port_in={len(wave_in)} "
              f"port_out={len(wave_out)} absorbing={len(absorbing)}")
        print("  opening Gmsh GUI (close window to continue)...")
        gmsh.fltk.run()
        gmsh.finalize()
        return {"preview": True}

    if render_png:
        if render_hide_air:
            # The air boxes over the feeds enclose the trace, ground pour and
            # stitching vias, so a shaded render is just a blue slab and the
            # footprint can't be checked. Hiding them (render-only; the mesh
            # itself is untouched) exposes the copper at z=h.
            for t in air_vols:
                gmsh.model.setVisibility([(3, t)], 0, recursive=True)
        gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_min)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_max)
        gmsh.model.mesh.generate(2)
        gmsh.option.setNumber("Mesh.SurfaceFaces", 1)
        gmsh.option.setNumber("Mesh.SurfaceEdges", 0)
        gmsh.option.setNumber("Mesh.VolumeFaces", 0)
        gmsh.option.setNumber("Mesh.ColorCarousel", 2)
        gmsh.option.setNumber("General.Trackball", 0)
        gmsh.option.setNumber("General.RotationX", rot_xyz[0])
        gmsh.option.setNumber("General.RotationY", rot_xyz[1])
        gmsh.option.setNumber("General.RotationZ", rot_xyz[2])
        gmsh.option.setNumber("General.Axes", 0)
        gmsh.fltk.initialize()
        gmsh.fltk.wait(0.5)
        gmsh.write(render_png)
        gmsh.finalize()
        return {"render_png": render_png, "faces": {"pec": len(pec),
                "port_in": len(wave_in), "port_out": len(wave_out)}}

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
        sma_info = {
            "rin_mm": sma_rin_mm, "rout_mm": sma_rout_mm,
            "eps_r": sma_eps_r, "tand": sma_tand,
            "voltage_path_in": [[Xc0, sma_rin_mm, h], [Xc0, sma_rout_mm, h]],
            "voltage_path_out": [[Xc1, sma_rin_mm, h], [Xc1, sma_rout_mm, h]],
        }
    if show:
        print(f"\n--- dual-mode driven mesh, in-line ports (Li={Li}mm, "
              f"w_iris={w_iris_mm}mm, x_iris={x_iris:.2f}mm, y_wall={y_wall_mm}mm, "
              f"w_ext={we:.3f}mm) ---")
        print(f"  box x[{X0:.1f},{X1:.1f}] y[{-ym:.1f},{ym:.1f}] z[0,{h:.2f}]")
        print(f"  vias={len(final)} diel_vols={len(diel_clean)} air_vols={len(air_vols)}")
        print(f"  faces: pec={len(pec)} port_in={len(wave_in)} port_out={len(wave_out)} "
              f"absorbing={len(absorbing)}")
        print(f"  nodes={nnode:,}  tets={ntet:,}")
        print(f"  WROTE {out}")
    gmsh.finalize()
    return {"mesh": out, "tets": ntet, "nodes": nnode, "legend": legend,
            "ports": (len(wave_in), len(wave_out)), "sma": sma_info,
            "eps_r": eps_r, "tand": tand}


def plot_layout_2d(a_mm: float = A_SIW_MM, w_iris_mm: float = 6.0,
                   x_iris_mm: float | None = None, y_wall_mm: float = 3.0,
                   d_via_mm: float = D_VIA_MM,
                   p_via_mm: float = P_VIA_MM, w_ms_mm: float | None = None,
                   l_taper_mm: float | None = None, l_feed_mm: float | None = None,
                   w_ext_mm: float | None = None, path: str = "dualmode_layout_2d.png") -> str:
    """Fast pure-matplotlib top view (no gmsh/mesh needed) -- same style as
    layout_plot.py: vias as circles, feed traces as filled rectangles,
    internal iris highlighted + dimensioned."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Rectangle, Polygon

    W, Lt, Lf = _dims(a_mm, w_ms_mm, l_taper_mm, l_feed_mm)
    Xf = Lt + Lf
    we = w_ext_mm if w_ext_mm is not None else 25.0
    half = a_mm / 2.0
    r = d_via_mm / 2.0
    final, x_iris = _via_layout(a_mm, w_iris_mm, x_iris_mm, we, d_via_mm, p_via_mm, y_wall_mm)

    fig, ax = plt.subplots(figsize=(11, 4.5))

    # cavity + feed board outline
    ax.add_patch(Rectangle((0.0, -half), a_mm, 2 * half, fill=False, ec="0.4", lw=1.0))
    poly_in = [(-Xf, +W / 2), (-Lt, +W / 2), (0.0, +half),
               (0.0, -half), (-Lt, -W / 2), (-Xf, -W / 2)]
    poly_out = [(a_mm + Xf, +W / 2), (a_mm + Lt, +W / 2), (a_mm, +half),
                (a_mm, -half), (a_mm + Lt, -W / 2), (a_mm + Xf, -W / 2)]
    ax.add_patch(Polygon(poly_in, closed=True, fc="#d9a441", ec="#a06d12", lw=0.8, alpha=0.75, zorder=1))
    ax.add_patch(Polygon(poly_out, closed=True, fc="#d9a441", ec="#a06d12", lw=0.8, alpha=0.75, zorder=1))
    ax.add_patch(Rectangle((0.0, -half), a_mm, 2 * half, fc="#cfe8ff", ec="none", alpha=0.4, zorder=0))
    ax.annotate("", xy=(0.0, we / 2), xytext=(0.0, -we / 2),
               arrowprops=dict(arrowstyle="<->", color="#a06d12"))

    for x, y in final:
        internal = _near(x, x_iris) and 0.0 < x < a_mm
        ax.add_patch(Circle((x, y), r, fc=("#b00" if internal else "#444"), ec="none", zorder=2))

    # dimension annotations
    ax.annotate("", xy=(x_iris, -w_iris_mm / 2), xytext=(x_iris, w_iris_mm / 2),
               arrowprops=dict(arrowstyle="<->", color="#b00"))
    ax.text(x_iris + 1.5, 0, f"w_iris={w_iris_mm:.2f}mm", color="#b00", fontsize=9, va="center")
    ax.annotate("", xy=(x_iris, half - y_wall_mm), xytext=(x_iris, half),
               arrowprops=dict(arrowstyle="<->", color="#0a8"))
    ax.text(x_iris + 1.5, half - y_wall_mm / 2, f"y_wall={y_wall_mm:.2f}mm",
           color="#0a8", fontsize=8, va="center")
    ax.annotate("", xy=(0.0, half + 5), xytext=(x_iris, half + 5),
               arrowprops=dict(arrowstyle="<->", color="#2a5d8f"))
    ax.text(x_iris / 2, half + 6.5, f"x_iris={x_iris:.2f}mm (from wall)",
           color="#2a5d8f", fontsize=9, ha="center")
    ax.text(a_mm / 2, -half - 5, f"a={a_mm:.2f}mm", ha="center", fontsize=9, color="0.3")
    ax.text(2, we / 2 + 2, f"w_ext={we:.2f}mm", ha="left", fontsize=8, color="#a06d12")
    ax.text(-Xf / 2, half + 2, f"W_ms={W:.3f}mm, L_taper={Lt:.1f}mm", ha="center",
           fontsize=8, color="#a06d12")

    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title(f"Dual-mode cavity, in-line ports, Deslandes taper "
               f"(W_ms={W:.3f}mm -> w_ext={we:.2f}mm) + floating internal iris row "
               f"(w_iris={w_iris_mm:.2f}mm @ x_iris={x_iris:.2f}mm, y_wall={y_wall_mm:.2f}mm)",
               fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(-Xf - 5, a_mm + Xf + 5)
    ax.set_ylim(-half - 12, half + 12)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    out = out_img(path)
    fig.savefig(out, dpi=140)
    print(f"Wrote {out}  ({len(final)} vias, w_ms={W:.3f}mm)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--render", default=None, help="write shaded PNG here instead")
    ap.add_argument("--plot2d", default=None, help="write 2D top-view PNG here instead")
    ap.add_argument("--no-sma", action="store_true")
    ap.add_argument("--w-iris", type=float, default=6.0)
    args = ap.parse_args()
    if args.plot2d:
        plot_layout_2d(w_iris_mm=args.w_iris, path=args.plot2d)
    else:
        build_mesh(w_iris_mm=args.w_iris, with_sma=not args.no_sma,
                   preview=args.preview, render_png=args.render)
