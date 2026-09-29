"""Driven (2-port, real feed) model of the isolated dual-mode square cavity,
IN-LINE port placement: both openings on opposite walls (x=0 input, x=a
output), centered on the same y=0 axis -- same convention as palace_driven.py's
3-cavity model, so this cavity can slot into that cascade without a bent board.

Feed = Deslandes taper: the microstrip stays at the true 50-ohm width W_ms
near the connector, then flares over L_taper to the full cavity wall width
at x=0/x=a. The via-fence wall opening (w_ext) is an independent parameter,
narrower than the flare -- pinning w_ext=W_ms directly (no flare) could never
find a design better than -24dB peak S21 over a wide search; decoupling them
fixes it, same as the main filter's external iris.

INTERNAL iris: a transverse via row at x=x_iris, floating between the side
walls (held off by y_wall, not a full partition), with a centered gap of
width w_iris -- the secondary tuning control on top of the external feed match.

Run: uv run python -m siwfilter.palace_dualmode_driven --preview
"""
from __future__ import annotations

import argparse
import math

import gmsh
import numpy as np

from .config import SPEC, VIA_PRESETS, out_data, out_img
from .geometries import min_via_centre_sep, _wall_with_gap
from .siw_geometry import microstrip_width_50ohm, microstrip_eps_eff, microstrip_guided_wavelength
from .palace_dualmode import A_SIW_MM, D_VIA_MM, P_VIA_MM

MM = 1e3


def _near(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) < tol


def _dims(a_mm, w_ms_mm, l_taper_mm, l_feed_mm):
    # Recompute the true 50-ohm width directly rather than reading it off a
    # cached Geometry -- see docs/sma_connector/README.md for why that cache
    # can be stale (tuned against a self-normalizing port, not real 50 ohm).
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


def _via_layout(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm, y_wall_mm=3.0,
                y_ext_off_mm=0.0, y_ext2_off_mm=0.0):
    """Pure-geometry via-position computation, shared by build_mesh (gmsh)
    and plot_layout_2d (matplotlib) so the two never drift apart.

    y_ext_off_mm / y_ext2_off_mm shift the port-1 (x=0) / port-2 (x=Li)
    coupling gap off y=0, independently, via the same `_wall_with_gap` helper
    `geometries.dualmode_cascade()` uses for its own port apertures. Both
    default to 0.0, reproducing the prior centred-gap via list exactly."""
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
    for o in _wall_with_gap(w_ext_mm / 2.0, y_ext_off_mm, half, p):
        vias.append((0.0, o))
    for o in _wall_with_gap(w_ext_mm / 2.0, y_ext2_off_mm, half, p):
        vias.append((Li, o))
    for xv in xs:
        vias.append((xv, -half))
        vias.append((xv, half))
    # internal iris row: floats between the side walls, held off by y_wall_mm
    # at each end (not a full partition); segments span EXACTLY
    # [w_iris/2, half-y_wall] (continuous), see palace_dualmode.py.
    if w_iris_mm is not None:
        for o in _segment_vias(w_iris_mm / 2.0, half - y_wall_mm, p):
            vias.append((x_iris, o)); vias.append((x_iris, -o))

    # Fab-rule spacing, not 0.9*d: that threshold sat below one via diameter
    # and permitted physically overlapping barrels.
    lim2 = min_via_centre_sep(2.0 * r) ** 2
    final: list[tuple[float, float]] = []
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= lim2 for kx, ky in final):
            final.append((x, y))
    return final, x_iris


#: Does this geometry's feed face present a FLAT wall for the taper to flare
#: onto? The Deslandes taper transforms the 50-ohm microstrip up to the full
#: waveguide width, which presupposes a wall of that width at the aperture.
#:
#:   dualmode / corner_cut  square cavity, flat end walls -> flare
#:   circular_cross         the fence is a CURVE; at the feed axis it is
#:                          tangent, so there is no wall to flare onto
#:   rhombic                the feed lands on a VERTEX, likewise
#:
#: For the latter two the trace stays at the true 50-ohm width through the
#: aperture. The aperture (w_ext) remains the coupling knob either way.
TAPER_TO_WALL: dict[str, bool] = {
    "corner_cut": True,
    "circular_cross": False,
    "circular_cross_taper": True,  # adds a flat facet at the feed -- see geometries.py
    "circular_cross_iris": True,   # same flat facet, different internal iris
    "rhombic": False,
    "halfmode": True,
    "quartermode": True,
}


def face_ty(geometry, vias, xf: float, W: float, half: float,
            ym: float, ym_lo: float) -> tuple[float, float]:
    """Taper flare extent at the end face x=xf: (y_lo, y_hi).

    PER FACE, not one global pair -- the two faces need not have the same
    wall extent. corner_cut truncates the +x/+y corner, so its OUTPUT wall
    stops 8.6mm short of its input wall; flaring both to the global maximum
    put 8.6mm of taper copper over open substrate where the wall had been
    removed. The flare is supposed to land ON the wall it feeds.

    A flare also only makes sense against a FLAT wall (see TAPER_TO_WALL):
    for a curve or a vertex the trace stays at the 50-ohm width W.
    """
    if geometry is None:
        return -half, half
    if not TAPER_TO_WALL.get(geometry, True):
        return -W / 2.0, W / 2.0              # no flare: straight 50-ohm feed
    ys = [q[1] for q in vias if abs(q[0] - xf) < 1e-6]
    if not ys:                                # no flat wall on this face
        return -W / 2.0, W / 2.0
    lo = min(0.0, min(ys)) if min(ys) >= 0.0 else min(ys)
    return max(lo, ym_lo + 0.5), min(max(ys), ym - 0.5)


def feed_trace_poly(x_in: float, x_taper: float, x_siw: float,
                    W: float, ty_lo: float, ty_hi: float,
                    w_pad: float | None = None,
                    x_pad_end: float | None = None,
                    x_pad_hold: float | None = None) -> np.ndarray:
    """Deslandes feed outline: constant 50-ohm width W from the port to
    x_taper, then a linear flare to the FULL cavity wall width at x_siw.

    Pure geometry, shared by the mesh builder and every 2D drawing for the
    same reason _via_layout is -- a drawing that recomputes the shape
    silently drifts from what is actually simulated. (It did: a first pass
    at the geometry comparison drew the feed as a constant-width line, which
    made it look as though the design had no taper at all.)
    """
    if w_pad is not None and x_pad_end is not None:
        # CPWG launch pad (2026-08-29): the centre conductor starts at
        # `w_pad` at the connector and tapers to the 50-ohm microstrip width
        # W by x_pad_end. Per edge-launch practice (Cinch/Copper Mountain/
        # Altium app notes) the pad is deliberately WIDER than the pin -- the
        # pad is capacitive and the taper supplies the compensating localised
        # inductance, so the pair lands near 50 ohm. Matching the pad to the
        # 0.76mm pin instead would need a ~0.095mm coplanar gap, below
        # JLCPCB's 0.127mm minimum trace spacing, so it is not buildable here
        # anyway. Defaults keep this off (plain constant-width feed).
        xh = x_pad_hold if x_pad_hold is not None else x_in
        return np.array([
            (x_in, +w_pad / 2), (xh, +w_pad / 2), (x_pad_end, +W / 2),
            (x_taper, +W / 2), (x_siw, ty_hi), (x_siw, ty_lo),
            (x_taper, -W / 2), (x_pad_end, -W / 2), (xh, -w_pad / 2),
            (x_in, -w_pad / 2)])
    return np.array([(x_in, +W / 2), (x_taper, +W / 2), (x_siw, ty_hi),
                     (x_siw, ty_lo), (x_taper, -W / 2), (x_in, -W / 2)])


def gnd_stitch_layout(X0: float, X1: float, W: float, ym: float, ym_lo: float,
                      n_gnd_stitch: int = 3,
                      gnd_stitch_offset_mm: float = 2.62,
                      gnd_stitch_pitch_mm: float = VIA_PRESETS["gnd_stitch"]["p_mm"],
                      gnd_via_d_mm: float = VIA_PRESETS["gnd_stitch"]["d_mm"],
                      gnd_clearance_mm: float = 0.3,
                      cpwg_gap_mm: float | None = None,
                      cpwg_y_gnd_mm: float | None = None,
                      cpwg_y_out_mm: float | None = None,
                      cpwg_len_mm: float = 5.0,
                      cpwg_taper_mm: float = 4.0,
                      ) -> tuple[list[np.ndarray], list[tuple[float, float]]]:
    """Connector ground pads + stitching via centres (Taoglas footprint).

    Returns (pad_polys, via_centres). Pure geometry, shared with the drawing
    code -- see feed_trace_poly.
    """
    rg = gnd_via_d_mm / 2.0
    pad_margin = 0.25                      # copper beyond the via barrel
    y_lo = gnd_stitch_offset_mm - rg - pad_margin
    y_hi = gnd_stitch_offset_mm + rg + pad_margin
    n_st = max(0, n_gnd_stitch)
    polys: list[np.ndarray] = []
    centres: list[tuple[float, float]] = []

    # ---- CPWG launch ----------------------------------------------------
    # When cpwg_gap_mm is given, the coplanar grounds are a real CPWG: a
    # rectangular ground pad per side per port, its INNER edge held at
    # cpwg_y_gnd_mm for cpwg_len_mm. That edge is fixed, not tracking the
    # trace, so it must not extend over the signal taper -- a widening trace
    # under a fixed-gap ground pad closes the gap to nothing. The inner edge
    # is the synthesised 50-ohm gap for the actual (constant-width) trace, so
    # the launch is 50 ohm with no signal taper needed. Pinning it to the
    # connector legs (2.62mm) instead would leave 51.3 ohm and put the stitch
    # vias half in the gap, since they sit on that line.
    # cpwg_gap_mm=None reproduces plain pad-only behaviour (small pads sized
    # around the stitch vias, not impedance-matched).
    if cpwg_gap_mm is not None:
        y_in = cpwg_y_gnd_mm if cpwg_y_gnd_mm is not None else (W / 2.0 + cpwg_gap_mm)
        y_out = (cpwg_y_out_mm if cpwg_y_out_mm is not None
                 else gnd_stitch_offset_mm + gnd_via_d_mm / 2.0 + 0.6)
        for x_edge, sign in ((X0, +1.0), (X1, -1.0)):
            x_end = x_edge + sign * cpwg_len_mm
            xa, xb = sorted([x_edge, x_end])
            for sgn in (+1.0, -1.0):
                y_lim = ym if sgn > 0 else ym_lo
                if abs(y_lim) <= y_in:
                    continue
                yo = min(y_out, abs(y_lim))
                polys.append(np.array([(xa, sgn * y_in), (xb, sgn * y_in),
                                       (xb, sgn * yo), (xa, sgn * yo)]))
            for k in range(n_st):
                xv = x_edge + sign * (rg + pad_margin + k * gnd_stitch_pitch_mm)
                if abs(xv - x_edge) > cpwg_len_mm - (rg + pad_margin):
                    continue
                for sgn in (+1.0, -1.0):
                    yv = sgn * gnd_stitch_offset_mm
                    if (abs(yv) - rg < y_in or abs(yv) + rg > y_out
                            or yv + rg > ym or yv - rg < ym_lo):
                        continue
                    centres.append((xv, yv))
        return polys, centres

    for x_edge, sign in ((X0, +1.0), (X1, -1.0)):
        x_first = x_edge + sign * (rg + pad_margin)
        x_last = x_first + sign * max(0, n_st - 1) * gnd_stitch_pitch_mm
        xa, xb = sorted([x_edge, x_last + sign * (rg + pad_margin)])
        for sgn in (+1.0, -1.0):
            ys = sorted([sgn * y_lo, sgn * y_hi])
            if min(abs(ys[0]), abs(ys[1])) <= W / 2.0 + gnd_clearance_mm:
                continue          # would encroach on the trace clearance
            if max(ys) > ym or min(ys) < ym_lo:
                continue          # off the board
            polys.append(np.array([(xa, ys[0]), (xb, ys[0]),
                                   (xb, ys[1]), (xa, ys[1])]))
        for k in range(n_st):
            xv = x_first + sign * k * gnd_stitch_pitch_mm
            for sgn in (+1.0, -1.0):
                yv = sgn * gnd_stitch_offset_mm
                if (abs(yv) - rg <= W / 2.0 + gnd_clearance_mm
                        or yv + rg > ym or yv - rg < ym_lo):
                    continue
                centres.append((xv, yv))
    return polys, centres


def build_mesh(a_mm: float = A_SIW_MM, w_iris_mm: float = 6.0, x_iris_mm: float | None = None,
               geometry: str | None = None, w_cav_mm: float | None = None,
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
               cpwg_gap_mm: float | None = None,
               cpwg_y_gnd_mm: float | None = None,
               cpwg_y_out_mm: float | None = None,
               cpwg_w_feed_mm: float | None = None,
               # 5mm, not 3mm: at the 1.2mm stitch pitch a 3mm-deep pad only
               # fits 2 vias per side, which is thin for the ground return at
               # 2.87GHz. 5mm fits 4, and a couple of extra mm of ground pad
               # is free on a ~119mm board.
               cpwg_len_mm: float = 5.0,
               cpwg_taper_mm: float = 4.0,
               gnd_via_d_mm: float = VIA_PRESETS["gnd_stitch"]["d_mm"],
               mesh_max: float = 1.5, mesh_min: float = 0.4,
               out_name: str = "dualmode_driven.msh",
               preview: bool = False, render_png: str | None = None,
               render_hide_air: bool = True,
               show: bool = True, rot_xyz: tuple[float, float, float] = (55, 0, 20),
               y_ext_off_mm: float = 0.0, y_ext2_off_mm: float = 0.0,
               slot_x_mm: float | None = None, slot_y_mm: float = 0.0,
               slot_w_mm: float = 4.0, slot_l_mm: float = 3.0, slot_h_mm: float = 3.0,
               slot_pec_cap: bool = False,
               soldermask_um: float | None = None,
               soldermask_eps_r: float = 3.5, soldermask_tand: float = 0.02,
               silkscreen_um: float | None = None,
               silkscreen_eps_r: float = 3.2, silkscreen_tand: float = 0.02,
               enig_um: float | None = None,
               enig_conductivity_sm: float = 1.67e6, enig_mu_r: float = 1.0,
               metal_conductivity_sm: float | None = None,
               metal_thickness_um: float = 35.0,
               via_conductivity_sm: float | None = None,
               via_plating_um: float | None = None,
               **geom_extra) -> dict:
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
    ym_lo = -ym            # board spans y in [ym_lo, ym_hi]; symmetric by default
    Hair = h_air_factor * (h_mm if h_mm is not None else SPEC.substrate.h * MM)
    h = h_mm if h_mm is not None else SPEC.substrate.h * MM

    if geometry is None:
        final, x_iris = _via_layout(a_mm, w_iris_mm, x_iris_mm, we, d_via_mm,
                                    p_via_mm, y_wall_mm,
                                    y_ext_off_mm=y_ext_off_mm, y_ext2_off_mm=y_ext2_off_mm)
    else:
        # Alternative cavity shapes (see geometries.py) differ ONLY in via
        # placement, so they reuse every bit of machinery below.
        from .geometries import LAYOUTS
        # geom_extra: NEW structural knobs (per-arm via count, second ring,
        # cut angle, etc.) that a given layout function declares explicitly
        # instead of absorbing into its **_ catch-all. Threaded through as a
        # generic passthrough rather than adding a named build_mesh parameter
        # per knob per geometry, which would not scale past two or three
        # candidates -- see geometries.py for what each key means for a given
        # layout.
        final, _info = LAYOUTS[geometry](a_mm=a_mm, w_iris_mm=w_iris_mm,
                                         x_iris_mm=x_iris_mm, w_ext_mm=we,
                                         d_via_mm=d_via_mm, p_via_mm=p_via_mm,
                                         y_wall_mm=y_wall_mm, w_cav_mm=w_cav_mm,
                                         **geom_extra)
        x_iris = _info.get("x_iris", a_mm / 2.0)
        # Shrink the board onto the actual cavity instead of assuming a full
        # a_mm square, so a half-mode cavity's smaller-board benefit isn't
        # thrown away. The feed sits on y=0, which must stay inside the board
        # even when the cavity is entirely on one side of it.
        vy = [p[1] for p in final]; vx = [p[0] for p in final]
        margin = 3.0
        if min(vy) >= 0.0:
            # y=0 is an OPEN edge here (half/quarter mode): a real HMSIW
            # board is physically cut there, and the dielectric-air step
            # sustains the mode. Extending substrate past it into the
            # Absorbing face turns the open edge into a sink instead (no
            # resonance forms). Leave just enough substrate for the feed.
            ym_lo = -(W / 2.0 + 0.3)
        else:
            ym_lo = min(vy) - margin
        ym = max(0.0, max(vy)) + margin       # ym is now the UPPER edge
        Li = max(vx)
        X0, X1 = -Xf, Li + Xf
        Xc0, Xc1 = X0 - sma_len_mm, X1 + sma_len_mm
        half = (ym - ym_lo) / 2.0             # taper flares to the board half-width

    # Taper flare bounds, PER END FACE, not one global pair. Symmetric
    # geometries flare to +-half, but half/quarter-mode cavities live on one
    # side of the feed axis (a symmetric flare would put half the trace
    # outside the shrunken substrate -> dangling faces -> MFEM abort), and
    # asymmetric shapes like corner_cut have different wall extents on each
    # end (flaring both to the global max puts copper over open substrate on
    # the shorter wall). A flare needs a FLAT wall to land on -- the
    # Deslandes taper transforms the microstrip into the waveguide's full
    # transverse width. circular_cross and rhombic present a curve/vertex at
    # the feed axis instead, so those feed through at the true 50-ohm width
    # (TAPER_TO_WALL below).
    def _face_ty(xf: float) -> tuple[float, float]:
        return face_ty(geometry, final, xf, W, half, ym, ym_lo)

    ty_in_lo, ty_in_hi = _face_ty(0.0)
    ty_out_lo, ty_out_hi = _face_ty(Li)
    # Top-metal window: for a fractional-mode (half/quarter) cavity, metal
    # must NOT extend past the open edge -- substrate with PEC top AND
    # bottom running into the Absorbing face is a parallel-plate stub, and
    # the cavity can never store energy. The top metal must stop with the
    # cavity.
    if geometry is None:
        top_y_lo, top_y_hi = ym_lo, ym
    else:
        _vy2 = [p[1] for p in final]
        top_y_lo = min(_vy2) - p_via_mm if min(_vy2) < 0 else 0.0
        top_y_hi = max(_vy2) + p_via_mm

    y_span = ym - ym_lo

    # Clear a leaked gmsh session: every gmsh.finalize() below sits on a
    # success path, so an exception in between leaves gmsh initialised and
    # the next build in this process dies with "I'm busy!" -- turning one
    # real failure into two unrelated-looking ones.
    if gmsh.isInitialized():
        gmsh.finalize()
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1 if show else 0)
    gmsh.model.add("dualmode_driven")
    occ = gmsh.model.occ

    sub = (3, occ.addBox(X0, ym_lo, 0.0, X1 - X0, y_span, h))
    # Soldermask: a thin dielectric slab z in [h, h+t_mask] over the FEED
    # region only, not the enclosed cavity top (that top has no air above it
    # to subdivide, and mask over a fully-enclosed ground plane can't reach
    # the cavity fields). The feed's fringing fields ARE partly in air, so a
    # mask there shifts the microstrip's effective permittivity, Z0 and
    # electrical length. soldermask_um=None reproduces the old geometry
    # exactly.
    #
    # ENIG: a real thin CONDUCTOR volume z in [h, h+t_enig], directly on the
    # copper -- a volumetric Domains.Materials Conductivity domain (unlike
    # Boundaries.Conductivity, which is exterior-only and cannot be used
    # here). It must be confined to feed_trace_poly's actual outline, not a
    # full board-width slab: a full-width conductor shorts the entire feed
    # cross-section rather than lightly loading the trace (a full-width
    # attempt measured S11w=-0.01dB, IL=-86dB, 0 poles -- an electromagnetic
    # short, not a loss term). The leftover width outside the trace is
    # filled with plain air, which costs nothing physically.
    # Only the scalar thickness is needed here; the ENIG solids are built
    # further down once gnd_polys (the CPWG ground pads) exist, since ENIG
    # covers the ground pour too, not just the signal trace.
    enig_cond_objs_pre: list[tuple[int, int]] = []
    enig_gap_in: list[tuple[int, int]] = []
    enig_gap_out: list[tuple[int, int]] = []
    t_enig = (enig_um * 1e-3) if enig_um else 0.0
    mask_in = mask_out = None
    t_mask = (soldermask_um * 1e-3) if soldermask_um else 0.0
    if soldermask_um:
        mask_in = (3, occ.addBox(X0, ym_lo, h + t_enig, Xf, y_span, t_mask))
        mask_out = (3, occ.addBox(Li, ym_lo, h + t_enig, Xf, y_span, t_mask))
    # Silkscreen: epoxy ink layer ON TOP of soldermask (real process order),
    # same feed footprint. Thinner and slightly lower-eps than soldermask.
    silk_in = silk_out = None
    t_silk = (silkscreen_um * 1e-3) if silkscreen_um else 0.0
    if silkscreen_um:
        silk_in = (3, occ.addBox(X0, ym_lo, h + t_enig + t_mask, Xf, y_span, t_silk))
        silk_out = (3, occ.addBox(Li, ym_lo, h + t_enig + t_mask, Xf, y_span, t_silk))
    z_stack = h + t_enig + t_mask + t_silk
    _hair = Hair - t_enig - t_mask - t_silk
    air_in = (3, occ.addBox(X0, ym_lo, z_stack, Xf, y_span, _hair))
    air_out = (3, occ.addBox(Li, ym_lo, z_stack, Xf, y_span, _hair))

    # Electric coupling slot: a cutout in the top ground plane, distinct
    # from a via-fence gap (magnetic coupling only) -- cascaded dual-mode
    # SIW filters need both a magnetic coupling window and a separate
    # electric coupling slot to reach the other mode independently (see
    # docs/geometry_exploration/dualmode_cascade_v6_handoff_2026-08-28.md
    # sec 8/v8 for why widening a single via-fence aperture cannot do both).
    # slot_x_mm=None (default) adds no geometry.
    #
    # A small, local air pocket above a slot_l_mm x slot_w_mm hole in the
    # top ground at (slot_x_mm, slot_y_mm), capped by Absorbing on its own
    # outer faces (open/lossy, not a closed PEC stub -- the simpler first
    # model). Must not overlap air_in/air_out or the cavity side walls.
    air_slot = None
    if slot_x_mm is not None:
        air_slot = (3, occ.addBox(slot_x_mm - slot_l_mm / 2.0, slot_y_mm - slot_w_mm / 2.0, h,
                                  slot_l_mm, slot_w_mm, slot_h_mm))

    cyls = [(3, occ.addCylinder(x, y, 0.0, 0, 0, h, r)) for x, y in final]

    # Filled vs unfilled (plated barrel) vias: the main via fence's
    # cylindrical hole is filled with a real conductor volume rather than
    # tagging its lateral surface PEC -- a volumetric Domains.Materials
    # Conductivity domain, same reasoning as ENIG (Boundaries.Conductivity
    # is exterior-only and invalid on an internal via wall; Palace's own
    # MFEM warning confirms this on that face).
    # via_plating_um=None -> solid/filled; a given thickness -> hollow,
    # plated to that depth, air inside. Scope: main via fence only (`final`),
    # not the CPWG ground-stitch vias.
    via_plated = via_conductivity_sm is not None
    via_shell_objs: list[tuple[int, int]] = []
    via_core_objs: list[tuple[int, int]] = []
    via_inner_r = None
    if via_plated:
        t_via_shell = (via_plating_um * 1e-3) if via_plating_um else None
        if t_via_shell is not None and t_via_shell < r:
            via_inner_r = r - t_via_shell
        for vx, vy in final:
            cond = (3, occ.addCylinder(vx, vy, 0.0, 0, 0, h, r))
            if via_inner_r is not None and via_inner_r > 1e-6:
                core = (3, occ.addCylinder(vx, vy, 0.0, 0, 0, h, via_inner_r))
                shell_cut, _ = occ.cut([cond], [core], removeObject=True, removeTool=False)
                via_shell_objs += [(dd, t) for dd, t in shell_cut if dd == 3]
                via_core_objs.append(core)
            else:
                via_shell_objs.append(cond)

    # ---- microstrip trace: straight 50-ohm feed (width W) from the port to
    # x_taper, then a Deslandes flare from W up to the FULL cavity wall
    # width (+-half) at the SIW edge -- same shape as palace_driven.py's
    # trace_surface. The via-fence gap (we) is independent and narrower,
    # sitting within this flared footprint (copper overhangs the solid part
    # of the wall). ----
    def trace_surface(x_in: float, x_taper: float, x_siw: float,
                      tlo: float, thi: float,
                      w_pad: float | None = None,
                      x_pad_end: float | None = None,
                      x_pad_hold: float | None = None) -> int:
        pts = list(feed_trace_poly(x_in, x_taper, x_siw, W, tlo, thi,
                                   w_pad, x_pad_end, x_pad_hold))
        tags = [occ.addPoint(px, py, h) for px, py in pts]
        lines = [occ.addLine(tags[i], tags[(i + 1) % len(tags)]) for i in range(len(tags))]
        return occ.addPlaneSurface([occ.addCurveLoop(lines)])

    # CPWG launch feed width (2026-08-29): inside the coplanar section the
    # 50-ohm width is set by the CPWG gap, which is NOT the same as the
    # 50-ohm microstrip width -- so the feed is built at the CPWG width and
    # tapered to the microstrip width where the coplanar grounds end.
    _wp = cpwg_w_feed_mm if (cpwg_gap_mm is not None) else None
    _xp_in = X0 + (cpwg_len_mm + cpwg_taper_mm) if _wp is not None else None
    _xp_out = X1 - (cpwg_len_mm + cpwg_taper_mm) if _wp is not None else None
    _xh_in = X0 + cpwg_len_mm if _wp is not None else None
    _xh_out = X1 - cpwg_len_mm if _wp is not None else None
    trace_in = (2, trace_surface(X0, -Lt, 0.0, ty_in_lo, ty_in_hi, _wp, _xp_in, _xh_in))
    trace_out = (2, trace_surface(X1, Li + Lt, Li, ty_out_lo, ty_out_hi, _wp, _xp_out, _xh_out))
    # Ground truth for report.verify_drawing_matches_mesh: the exact feed
    # outlines meshed, including the CPWG pad taper. Verifying only via
    # positions missed a drawing that omitted the taper entirely.
    _trace_poly_in = feed_trace_poly(X0, -Lt, 0.0, W, ty_in_lo, ty_in_hi,
                                     _wp, _xp_in, _xh_in).tolist()
    _trace_poly_out = feed_trace_poly(X1, Li + Lt, Li, W, ty_out_lo, ty_out_hi,
                                      _wp, _xp_out, _xh_out).tolist()

    # Connector ground: top-side pour + stitching vias. The Taoglas jack
    # grounds through 4 discrete legs at the board edge; without top-side
    # copper in the feed span there is nothing for those legs to land on and
    # the return path detours to the bottom plane. Off by default, since it
    # changes the feed environment for any design tuned without it.
    gnd_polys: list[np.ndarray] = []
    gnd_surfs: list[tuple[int, int]] = []
    gnd_via_centres: list[tuple[float, float]] = []
    if gnd_stitch:
        # Discrete pads, not a continuous pour, unless cpwg_gap_mm is set: a
        # naive full-length pour at fixed clearance turns the 50-ohm
        # microstrip into an unmatched grounded coplanar line. With
        # cpwg_gap_mm the grounds ARE a coplanar plane, but a deliberately
        # impedance-matched one (gap synthesised for 50 ohm), which is what
        # the real footprint actually is.
        # Stitching vias use their own diameter, not the SIW fence's d_via_mm
        # (sized for the cavity wall and far larger than a real stitching
        # via) -- smaller barrels let several fit per pad, lowering the
        # ground-return inductance at the launch.
        # Geometry comes from gnd_stitch_layout(), the same helper the 2D
        # drawings use, so the meshed model and the drawings can't drift
        # apart.
        rg = gnd_via_d_mm / 2.0
        gnd_polys, gnd_via_centres = gnd_stitch_layout(
            X0, X1, W, ym, ym_lo,
            n_gnd_stitch=n_gnd_stitch,
            gnd_stitch_offset_mm=gnd_stitch_offset_mm,
            gnd_stitch_pitch_mm=gnd_stitch_pitch_mm,
            gnd_via_d_mm=gnd_via_d_mm,
            gnd_clearance_mm=gnd_clearance_mm,
            cpwg_gap_mm=cpwg_gap_mm,
            cpwg_y_gnd_mm=cpwg_y_gnd_mm,
            cpwg_y_out_mm=cpwg_y_out_mm,
            cpwg_len_mm=cpwg_len_mm,
            cpwg_taper_mm=cpwg_taper_mm)
        for poly in gnd_polys:
            pts = [occ.addPoint(px, py, h) for px, py in poly]
            ln = [occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
            gnd_surfs.append((2, occ.addPlaneSurface([occ.addCurveLoop(ln)])))
        cyls += [(3, occ.addCylinder(x, y, 0.0, 0, 0, h, rg)) for x, y in gnd_via_centres]

    # ENIG solids (built here so gnd_polys exists). ENIG plates all exposed
    # copper in reality, but electromagnetically only matters where fields
    # actually touch it -- the feed's top copper, whose fringing fields are
    # partly in air. On the cavity top/bottom ground planes ENIG sits on the
    # OUTER face, shielded from the cavity fields by ~28 skin depths of PEC
    # copper, so modelling it there cannot change the answer. Covered here:
    # the signal trace and the CPWG ground pour (the gap-adjacent copper
    # where the launch concentrates its fields). Ni-P's skin depth at
    # 2.87GHz (~7.3um) exceeds the 4.5um layer, so it is a partially
    # field-penetrable lossy film where it does sit, not a shield.
    if enig_um:
        def _extrude_poly(poly, dz):
            pts = [occ.addPoint(px, py, h) for px, py in poly]
            ln = [occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
            surf = occ.addPlaneSurface([occ.addCurveLoop(ln)])
            out = occ.extrude([(2, surf)], 0, 0, dz)
            return [(dd, t) for dd, t in out if dd == 3][0]
        enig_polys_in = [feed_trace_poly(X0, -Lt, 0.0, W, ty_in_lo, ty_in_hi)]
        enig_polys_out = [feed_trace_poly(X1, Li + Lt, Li, W, ty_out_lo, ty_out_hi)]
        for poly in gnd_polys:
            xs = [p[0] for p in poly]
            (enig_polys_in if sum(xs) / len(xs) < Li / 2.0 else enig_polys_out).append(poly)
        cond_in = [_extrude_poly(p, t_enig) for p in enig_polys_in]
        cond_out = [_extrude_poly(p, t_enig) for p in enig_polys_out]
        enig_cond_objs_pre = cond_in + cond_out
        gap_box_in = (3, occ.addBox(X0, ym_lo, h, Xf, y_span, t_enig))
        gap_box_out = (3, occ.addBox(Li, ym_lo, h, Xf, y_span, t_enig))
        cut_gi, _ = occ.cut([gap_box_in], cond_in, removeObject=True, removeTool=False)
        cut_go, _ = occ.cut([gap_box_out], cond_out, removeObject=True, removeTool=False)
        enig_gap_in = [(dd, t) for dd, t in cut_gi if dd == 3]
        enig_gap_out = [(dd, t) for dd, t in cut_go if dd == 3]

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
    enig_cond_objs = enig_cond_objs_pre
    enig_gap_objs = enig_gap_in + enig_gap_out
    mask_boxes = [b for b in (mask_in, mask_out) if b is not None]
    silk_boxes = [b for b in (silk_in, silk_out) if b is not None]
    air_boxes = ([air_in, air_out] + ([air_slot] if air_slot is not None else [])
                + mask_boxes + silk_boxes + enig_gap_objs)
    frag_objects = (sub_tags + ptfe_vols + air_boxes + via_shell_objs + via_core_objs
                    + enig_cond_objs)
    _, frag_map = occ.fragment(frag_objects, [trace_in, trace_out] + sma_caps + gnd_surfs)
    occ.synchronize()
    # A full 360-degree annulus (the via plating shell) has its (x,y)
    # centroid AT THE AXIS by rotational symmetry, identical to the solid
    # core's -- geometric classification by centroid can't tell them apart.
    # Track identity through fragment's own mapping instead, which is
    # parallel to frag_objects.
    n_shell, n_core = len(via_shell_objs), len(via_core_objs)
    n_enig = len(enig_cond_objs)
    _base = len(frag_objects) - n_shell - n_core - n_enig
    shell_out_tags = {t for entry in frag_map[_base:_base + n_shell]
                      for (dd, t) in entry if dd == 3}
    core_out_tags = {t for entry in frag_map[_base + n_shell:_base + n_shell + n_core]
                     for (dd, t) in entry if dd == 3}
    # Same identity-tracking need as the via shell/core: the ENIG conductor
    # prism and the air filling the rest of that z-slice occupy the SAME
    # z-range, so a height-based test cannot separate them.
    enig_out_tags = {t for entry in frag_map[_base + n_shell + n_core:]
                     for (dd, t) in entry if dd == 3}

    via_centres = final + gnd_via_centres

    diel_clean, air_vols, sma_diel, mask_vols, enig_vols, silk_vols = [], [], [], [], [], []
    via_shell_vols, via_core_vols = [], []
    for dim, tag in gmsh.model.getEntities(3):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, tag)
        if with_sma and (cx < X0 - 1e-6 or cx > X1 + 1e-6):
            sma_diel.append(tag)
        elif tag in shell_out_tags:
            via_shell_vols.append(tag)
        elif tag in core_out_tags:
            via_core_vols.append(tag)
        elif tag in enig_out_tags:
            enig_vols.append(tag)
        elif cz < h:
            diel_clean.append(tag)
        elif soldermask_um and cz < h + t_enig + t_mask + 1e-9:
            mask_vols.append(tag)
        elif silkscreen_um and cz < h + t_enig + t_mask + t_silk + 1e-9:
            silk_vols.append(tag)
        else:
            air_vols.append(tag)
    air_vols += via_core_vols   # the hollow core of a plated (unfilled) via is just air

    gmsh.model.addPhysicalGroup(3, diel_clean, tag=1, name="dielectric")
    gmsh.model.addPhysicalGroup(3, air_vols, tag=2, name="air")
    if mask_vols:
        gmsh.model.addPhysicalGroup(3, mask_vols, tag=4, name="soldermask")
    if enig_vols:
        gmsh.model.addPhysicalGroup(3, enig_vols, tag=5, name="enig")
    if silk_vols:
        gmsh.model.addPhysicalGroup(3, silk_vols, tag=7, name="silkscreen")
    if via_shell_vols:
        gmsh.model.addPhysicalGroup(3, via_shell_vols, tag=6, name="via_conductor")
    if sma_diel:
        gmsh.model.addPhysicalGroup(3, sma_diel, tag=3, name="sma_ptfe")

    def _outline(x_in, x_taper, x_siw, tlo, thi):
        return feed_trace_poly(x_in, x_taper, x_siw, W, tlo, thi)
    # Ground pour counts as copper for face classification, exactly like the
    # trace -- both are PEC sheets at z=h, just electrically distinct nets.
    trace_polys = [_outline(X0, -Lt, 0.0, ty_in_lo, ty_in_hi),
                   _outline(X1, Li + Lt, Li, ty_out_lo, ty_out_hi)] + gnd_polys

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
    pec_ext_flag: dict[int, bool] = {}
    _all_boundary_faces: list[int] = []
    for dim, tag in gmsh.model.getEntities(2):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(2, tag)
        xmin, ymin_f, _, xmax, ymax_f, _ = gmsh.model.getBoundingBox(2, tag)
        adj_up, _ = gmsh.model.getAdjacencies(2, tag)
        is_boundary = len(adj_up) <= 1
        if is_boundary:
            _all_boundary_faces.append(tag)

        on_via = any((cx - vx) ** 2 + (cy - vy) ** 2 < (1.3 * r) ** 2
                     for vx, vy in via_centres) and cz <= h + 1e-6
        # Only the MAIN fence (`final`) gets real conductor volumes; the CPWG
        # ground-stitch vias keep empty holes. Must be distinguished here or
        # the stitch-via walls are skipped from PEC with no conductor behind
        # them, leaving unassigned exterior faces (see the catch-all below).
        on_main_via = any((cx - vx) ** 2 + (cy - vy) ** 2 < (1.3 * r) ** 2
                          for vx, vy in final) and cz <= h + 1e-6

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
            # Centroid-radius alone is not sufficient: clipping the PTFE
            # bottom pulls the annulus end-face's centroid toward the pin
            # axis, misclassifying it as the pin cap (and tagging the coax
            # dielectric PEC, shorting the launch) once sma_rin_mm exceeds
            # ~0.3773mm -- see docs/sma_connector/README.md. Disambiguate by
            # EXTENT instead: the real cap disk spans ~rin, the annulus ~rout.
            if ((_near(cx, X0) or _near(cx, X1)) and rad < sma_rin_mm * 1.05
                    and yext <= sma_rin_mm * 1.5):
                on_sma_cap = True

        if _near(cz, 0.0):
            pec.append(tag); pec_ext_flag[tag] = is_boundary
        elif on_main_via and via_plated and is_boundary:
            # A via CAP face (z=0 or z=h), i.e. exterior. For a filled +
            # capped via this is solid metal continuous with the ground
            # plane; for an open barrel the inner disc is a real aperture
            # while the surrounding annular ring is still metal. Tell them
            # apart by lateral extent (a full annulus's centroid sits on the
            # axis, so centroid position cannot): the core disc spans
            # ~2*via_inner_r, the annulus spans ~2*r.
            span = max(xmax - xmin, ymax_f - ymin_f)
            if via_inner_r is not None and span < 2 * via_inner_r + 0.2 * r:
                absorbing.append(tag)          # open hole: radiates to free space
            else:
                # EXTERIOR-ness is a mesh-topology fact, never an assumption
                # (a hardcoded True here is right for a bare board but wrong
                # once ENIG/soldermask/silkscreen are meshed above, turning
                # this cap into an internal two-sided sheet -- which would
                # then wrongly get Palace's exterior-only Conductivity BC).
                pec.append(tag); pec_ext_flag[tag] = is_boundary   # metal cap / ring
        elif on_main_via and via_plated:
            # The via wall's lateral surface is a real conductor-dielectric
            # material interface (via_shell_objs/via_core_objs above), not a
            # boundary condition -- leave it unclassified so it falls
            # through with no explicit BC, like the ENIG-to-air interface.
            # Its Ohmic loss is carried by the via_conductor material
            # domain's volumetric Conductivity, not by this face.
            pass
        elif on_via or on_sma_pin or on_sma_shell or on_sma_cap:
            pec.append(tag); pec_ext_flag[tag] = is_boundary
        elif with_sma and _near(cx, Xc0) and xmax - xmin < 1e-3:
            wave_in.append(tag)
        elif with_sma and _near(cx, Xc1) and xmax - xmin < 1e-3:
            wave_out.append(tag)
        elif not with_sma and _near(cx, X0) and xmax - xmin < 1e-3:
            wave_in.append(tag)
        elif not with_sma and _near(cx, X1) and xmax - xmin < 1e-3:
            wave_out.append(tag)
        elif _near(cz, h):
            in_slot = (slot_x_mm is not None
                      and abs(cx - slot_x_mm) <= slot_l_mm / 2.0 + 1e-6
                      and abs(cy - slot_y_mm) <= slot_w_mm / 2.0 + 1e-6)
            if in_slot:
                pass                                           # v8 coupling slot: leave open
            elif (0.0 - 1e-6 <= cx <= Li + 1e-6
                    and top_y_lo - 1e-6 <= cy <= top_y_hi + 1e-6):
                pec.append(tag); pec_ext_flag[tag] = is_boundary   # cavity top ground
            elif any(_in_poly(cx, cy, poly) for poly in trace_polys):
                pec.append(tag); pec_ext_flag[tag] = is_boundary   # microstrip trace
        elif (slot_pec_cap and slot_x_mm is not None and cz > h + 1e-6
              and abs(cx - slot_x_mm) <= slot_l_mm / 2.0 + 1e-6
              and abs(cy - slot_y_mm) <= slot_w_mm / 2.0 + 1e-6):
            pec.append(tag)     # v8 closed-slot variant: cap the air pocket, keep energy reactive
        elif is_boundary:
            absorbing.append(tag)

    pec = sorted(set(pec))
    absorbing = sorted(set(absorbing) - set(pec) - set(wave_in) - set(wave_out))

    # CATCH-ALL: every exterior face MUST carry a boundary condition. The
    # classification above is an if/elif chain, so a face that enters a
    # branch but matches none of its sub-cases falls out entirely without
    # reaching the `elif is_boundary` default -- harmless with PEC-only
    # geometry (those faces were interior), but the stacked fabrication
    # layers introduce exterior faces that hit exactly that hole, and Palace
    # then warns "no associated boundary element" and produces invalid
    # physics rather than failing. Absorbing is the physically correct
    # default for a dielectric stack's outer faces. Reported, never silent.
    _assigned = set(pec) | set(wave_in) | set(wave_out) | set(absorbing)
    _leftover = sorted(t for t in _all_boundary_faces if t not in _assigned)
    if _leftover:
        _zs = [gmsh.model.occ.getCenterOfMass(2, t)[2] for t in _leftover]
        if show:
            print(f"  [catch-all] {len(_leftover)} unclassified exterior face(s) "
                  f"-> Absorbing (z {min(_zs):.4f}..{max(_zs):.4f})")
        absorbing = sorted(set(absorbing) | set(_leftover))

    # Real (lossy) metal. Palace's Boundaries.Conductivity (surface
    # impedance) is EXTERIOR-ONLY -- invalid on via barrels and the trace
    # (internal two-sided sheets), valid on the ground planes (true exterior
    # mesh boundaries, and the biggest share of wall current). Split the PEC
    # group on that basis. The field-facing side of an exterior ground face
    # is its INNER surface (copper against the substrate), so copper's
    # conductivity is right here -- any ENIG sits on the far, shielded side.
    # metal_conductivity_sm=None (default) keeps everything PEC.
    pec_real = []
    if metal_conductivity_sm:
        pec_real = sorted(t for t in pec if pec_ext_flag.get(t))
        pec = sorted(set(pec) - set(pec_real))

    gmsh.model.addPhysicalGroup(2, pec, tag=10, name="pec")
    if pec_real:
        gmsh.model.addPhysicalGroup(2, pec_real, tag=15, name="metal_real")
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
    # An EMPTY mesh is a hard failure, not a small mesh: gmsh reports
    # boundary-recovery trouble as warnings and still writes a valid-looking
    # .msh with nothing in it, so Palace then "solves" it and the run reads
    # as a solver problem rather than a meshing one. Typically caused by an
    # extreme-aspect-ratio sliver -- thin fabrication layers over a narrow
    # CPWG gap, for instance. Fail here, where the cause is still visible.
    if ntet == 0 or nnode == 0:
        gmsh.finalize()
        raise RuntimeError(
            f"gmsh produced an EMPTY mesh (nodes={nnode} tets={ntet}) for "
            f"{out}. Boundary recovery failed -- most likely a sliver from "
            f"thin stack layers crossing the CPWG gap. Check the gmsh "
            f"warnings above; do not treat this as a solver failure.")
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
    mask_info = None
    if mask_vols:
        legend["soldermask"] = 4
        mask_info = {"eps_r": soldermask_eps_r, "tand": soldermask_tand,
                     "thickness_um": soldermask_um}
    via_cond_info = None
    if via_shell_vols:
        legend["via_conductor"] = 6
        via_cond_info = {"conductivity_sm": via_conductivity_sm, "mu_r": 1.0,
                         "plating_um": via_plating_um}
    silk_info = None
    if silk_vols:
        legend["silkscreen"] = 7
        silk_info = {"eps_r": silkscreen_eps_r, "tand": silkscreen_tand,
                     "thickness_um": silkscreen_um}
    metal_info = None
    if pec_real:
        legend["metal_real"] = 15
        metal_info = {"conductivity_sm": metal_conductivity_sm,
                      "thickness_um": metal_thickness_um,
                      "n_faces": len(pec_real)}
    enig_info = None
    if enig_vols:
        legend["enig"] = 5
        enig_info = {"conductivity_sm": enig_conductivity_sm, "mu_r": enig_mu_r,
                     "thickness_um": enig_um}
    if show:
        print(f"\n--- dual-mode driven mesh, in-line ports (Li={Li}mm, "
              f"w_iris={w_iris_mm}mm, x_iris={x_iris:.2f}mm, y_wall={y_wall_mm}mm, "
              f"w_ext={we:.3f}mm) ---")
        print(f"  box x[{X0:.1f},{X1:.1f}] y[{ym_lo:.1f},{ym:.1f}] z[0,{h:.2f}]")
        print(f"  vias={len(final)} diel_vols={len(diel_clean)} air_vols={len(air_vols)}")
        print(f"  faces: pec={len(pec)} port_in={len(wave_in)} port_out={len(wave_out)} "
              f"absorbing={len(absorbing)}")
        print(f"  nodes={nnode:,}  tets={ntet:,}")
        print(f"  WROTE {out}")
    gmsh.finalize()
    return {"mesh": out, "tets": ntet, "nodes": nnode, "legend": legend,
            "ports": (len(wave_in), len(wave_out)), "sma": sma_info,
            "soldermask": mask_info, "via_conductivity": via_cond_info,
            "enig": enig_info, "metal_real": metal_info, "silkscreen": silk_info,
            # Ground-truth launch geometry as MESHED, so any drawing can be
            # verified against it instead of re-deriving from a preset (which
            # is how the stackup view came to draw a launch that was never
            # simulated). See report.verify_drawing_matches_mesh.
            "launch_geom": {"gnd_via_centres": [list(map(float, c)) for c in gnd_via_centres],
                            "via_centres": [list(map(float, c)) for c in final],
                            "cpwg_gap_mm": cpwg_gap_mm,
                            "n_gnd_stitch": n_gnd_stitch,
                            "trace_poly_in": _trace_poly_in,
                            "trace_poly_out": _trace_poly_out,
                            "w_pad": _wp, "x_pad_end_in": _xp_in,
                            "x_pad_hold_in": _xh_in},
            "eps_r": eps_r, "tand": tand}


def plot_layout_2d(a_mm: float = A_SIW_MM, w_iris_mm: float = 6.0,
                   x_iris_mm: float | None = None, y_wall_mm: float = 3.0,
                   d_via_mm: float = D_VIA_MM,
                   p_via_mm: float = P_VIA_MM, w_ms_mm: float | None = None,
                   l_taper_mm: float | None = None, l_feed_mm: float | None = None,
                   w_ext_mm: float | None = None, path: str = "dualmode_layout_2d.png",
                   launch: dict | None = None) -> str:
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

    if launch:
        ym = half + 3.0
        X0, X1 = -Xf, a_mm + Xf
        polys, via_centres = gnd_stitch_layout(
            X0, X1, W, ym, -ym,
            n_gnd_stitch=launch.get("n_gnd_stitch", 3),
            gnd_stitch_offset_mm=launch.get("gnd_stitch_offset_mm", 2.62),
            gnd_stitch_pitch_mm=launch.get("gnd_stitch_pitch_mm", 1.2),
            gnd_via_d_mm=launch.get("gnd_via_d_mm", 0.6),
            gnd_clearance_mm=launch.get("gnd_clearance_mm", 0.3),
            cpwg_gap_mm=launch.get("cpwg_gap_mm"),
            cpwg_y_gnd_mm=launch.get("cpwg_y_gnd_mm"),
            cpwg_y_out_mm=launch.get("cpwg_y_out_mm"),
            cpwg_len_mm=launch.get("cpwg_len_mm", 5.0),
            cpwg_taper_mm=launch.get("cpwg_taper_mm", 4.0))
        for poly in polys:
            ax.add_patch(Polygon(poly, closed=True, fc="#7a8c7a", ec="#3d4a3d",
                                 lw=0.6, alpha=0.85, zorder=4))
        rg = launch.get("gnd_via_d_mm", 0.6) / 2.0
        for x, y in via_centres:
            ax.add_patch(Circle((x, y), rg, fc="#0a5c0a", ec="none", zorder=5))
        rin = launch.get("sma_rin_mm")
        if rin:
            for x_edge in (X0, X1):
                ax.add_patch(Circle((x_edge, 0.0), rin, fc="none", ec="#c00",
                                    lw=1.2, zorder=6))

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
