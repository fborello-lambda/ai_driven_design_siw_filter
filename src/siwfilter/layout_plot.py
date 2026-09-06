"""2D top-view layout drawing + via-coordinate CSV export (sanity check).

Draws the SIW filter geometry from siw_geometry.build_geometry(): board
outline, vias as circles, microstrip feed + tapers, cavity boundaries and a
few key dimension annotations. Export the via centres to CSV for inspection
BEFORE any heavy simulation.

Run:  uv run python layout_plot.py
"""

from __future__ import annotations

import csv

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Rectangle

from .config import SPEC, FilterSpec, out_img, out_data
from .siw_geometry import Geometry, build_geometry
from .palace_dualmode_driven import gnd_stitch_layout

MM = 1e3  # metres -> mm for plotting/CSV



def _cpwg_feed_polys(g: Geometry, launch: dict):
    """Feed outline for a CPWG launch, in METRES, matching what the mesher
    builds: width cpwg_w_feed_mm from the board edge through cpwg_len_mm,
    linearly tapered over cpwg_taper_mm to the microstrip width g.W_ms, then
    constant to the SIW wall. Mirrored at the output end."""
    wp = launch["cpwg_w_feed_mm"] / MM          # mm -> m
    wm = g.W_ms
    clen = launch.get("cpwg_len_mm", 5.0) / MM
    ctap = launch.get("cpwg_taper_mm", 4.0) / MM
    Lf, Lt, Li = g.L_feed, g.L_taper, g.L_inner
    X0 = -(Lt + Lf)
    out = []
    for x_edge, sgn in ((X0, +1.0), (Li + Lt + Lf, -1.0)):
        xa = x_edge + sgn * clen                # end of constant CPWG section
        xb = xa + sgn * ctap                    # end of the taper
        xc = x_edge + sgn * Lf                  # microstrip end / start of SIW flare
        out.append(np.array([
            (x_edge, -wp / 2), (xa, -wp / 2), (xb, -wm / 2), (xc, -wm / 2),
            (xc,  wm / 2), (xb,  wm / 2), (xa,  wp / 2), (x_edge,  wp / 2),
        ]))
    return out

def _draw_launch_footprint(ax, g: Geometry, launch: dict) -> None:
    """Overlay the connector ground pads, stitching vias and pin -- same
    geometry Palace actually meshes (gnd_stitch_layout, shared with
    palace_driven.py/palace_dualmode_driven.py) so this drawing can't drift
    from what gets simulated. `launch` is a TAOGLAS_SMA-style kwargs dict:
    sma_rin_mm, gnd_stitch_offset_mm/pitch_mm, gnd_via_d_mm, cpwg_gap_mm,
    cpwg_y_gnd_mm, cpwg_y_out_mm, cpwg_len_mm, cpwg_taper_mm."""
    W = g.W_ms * MM
    half = g.a_siw / 2 * MM
    ym = half + 3.0
    X0 = -(g.L_taper + g.L_feed) * MM
    X1 = (g.L_inner + g.L_taper + g.L_feed) * MM
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
    # Return what was actually DRAWN, not the requested n_gnd_stitch -- the
    # layout helper fits as many vias as clear, which need not equal the
    # request.
    n_in = sum(1 for x, _y in via_centres if x < 0.5 * (X0 + X1))
    return {"n_stitch_per_side": n_in, "n_stitch_total": len(via_centres),
            "gap_mm": (launch.get("cpwg_y_gnd_mm", 0.0)
                       - launch.get("cpwg_w_feed_mm", 0.0) / 2.0)}


def export_via_csv(g: Geometry, path: str = "via_coords.csv") -> None:
    """Write via centres (mm) and diameter to CSV."""
    d_mm = g.spec.d_via * MM
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["index", "x_mm", "y_mm", "diameter_mm"])
        for i, (x, y) in enumerate(g.vias):
            w.writerow([i, f"{x*MM:.4f}", f"{y*MM:.4f}", f"{d_mm:.4f}"])
    print(f"Wrote {path} ({len(g.vias)} vias)")


def plot_layout(g: Geometry, path: str = "layout.png", launch: dict | None = None,
                zoom_launch: bool = False) -> None:
    """Top view. zoom_launch=True crops to the INPUT launch instead of the
    whole board -- at board scale the CPWG gap (0.2512mm over ~170mm) is
    sub-pixel and the footprint cannot be inspected."""
    spec, sub = g.spec, g.spec.substrate
    fig, ax = plt.subplots(figsize=(9, 7) if zoom_launch else (13, 4.5))

    # Board outline
    xmin, xmax, ymin, ymax = (v * MM for v in g.board)
    ax.add_patch(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin,
                           fill=False, ec="0.4", lw=1.0, ls="--"))

    # Copper feed + tapers. With a CPWG launch the feed is NOT constant-width:
    # it's the CPWG 50-ohm width through the coplanar section (set by the
    # gap, not the microstrip formula), tapering to the microstrip width
    # where the ground pours end. Must derive from the same launch params
    # the mesher uses, or the drawing shows a different launch than simulated.
    feed_polys = list(g.feed_polys)
    if launch and launch.get("cpwg_gap_mm") is not None:
        feed_polys = _cpwg_feed_polys(g, launch)
    for poly in feed_polys + g.taper_polys:
        ax.add_patch(Polygon(np.asarray(poly) * MM, closed=True, fc="#d9a441",
                             ec="#a06d12", lw=0.8, alpha=0.7, zorder=1))

    # Cavity boundary shading (alternating) + labels
    half = g.a_siw / 2 * MM
    for i, (x0, x1) in enumerate(g.cavity_bounds):
        ax.add_patch(Rectangle((x0 * MM, -half), (x1 - x0) * MM, 2 * half,
                               fc=("#cfe8ff" if i % 2 == 0 else "#e8f4ff"),
                               ec="none", alpha=0.5, zorder=0))
        ax.text((x0 + x1) / 2 * MM, 0, f"cav {i+1}", ha="center", va="center",
                fontsize=9, color="#2a5d8f", zorder=3)

    # Vias as circles (main filter walls dark; external iris vias highlighted)
    r = g.spec.d_via / 2 * MM
    for (x, y) in g.vias:
        ax.add_patch(Circle((x * MM, y * MM), r, fc="#444", ec="none", zorder=2))
    for (x, y) in g.ext_iris_vias:
        ax.add_patch(Circle((x * MM, y * MM), r, fc="#b00", ec="none", zorder=3))

    # Dimension annotations
    L_inner = g.L_inner * MM
    _dim_h(ax, 0, g.L_cav * MM, -half - 4, f"L_cav={g.L_cav*MM:.1f}")
    _dim_v(ax, L_inner + 2, -half, half, f"a_siw={g.a_siw*MM:.1f}")
    for i, w in enumerate(g.iris_widths, start=1):
        x_wall = i * g.L_cav * MM
        _dim_v(ax, x_wall, -w / 2 * MM, w / 2 * MM,
               f"w{i}{i+1}={w*MM:.1f}", color="#b00", off=0)
    # external iris gap (input/output) -> Qe -> bandwidth
    if g.w_ext > 0.0:
        we = g.w_ext * MM
        for x_face in (0.0, g.L_inner * MM):
            _dim_v(ax, x_face, -we / 2, we / 2, f"w_ext={we:.1f}",
                   color="#b00", off=0)

    lp = _draw_launch_footprint(ax, g, launch) if launch else None

    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    iris_src = "EM-calibrated iris widths" if g.iris_calibrated \
        else "PLACEHOLDER iris widths (run calibrate.py --sweep)"
    ax.set_title(
        f"SIW BPF top view — N={spec.N}, f0={spec.f0/1e9:.3f} GHz, "
        f"{sub.name}  (vias d={spec.d_via*MM:.2f} mm, p={spec.p_via*MM:.2f} mm)\n"
        f"{iris_src}",
        fontsize=10)
    ax.set_aspect("equal")
    if zoom_launch:
        # Frame the input launch: from just outside the board edge to a little
        # past where the CPWG ground pads end and the taper meets the SIW wall.
        x_edge = -(g.L_taper + g.L_feed) * MM
        span = (g.L_taper + g.L_feed) * MM
        ax.set_xlim(x_edge - 2.0, x_edge + span + 4.0)
        yl = max(g.W_ms * MM * 6.0, (launch or {}).get("cpwg_y_out_mm", 3.6) * 2.5)
        ax.set_ylim(-yl, yl)
        lk = launch or {}
        ax.set_title(
            f"CPWG launch footprint (input) — coplanar gap {lp['gap_mm']:.4f} mm "
            f"(measured from the drawn outline)\n"
            f"feed {lk.get('cpwg_w_feed_mm', 0):.2f} mm through the CPWG section, "
            f"tapered to microstrip W={g.W_ms*MM:.3f} mm; "
            f"{lp['n_stitch_per_side']} stitch vias/side (drawn)", fontsize=10)
    else:
        ax.set_xlim(xmin - 3, xmax + 8)
        ax.set_ylim(ymin - 8, ymax + 8)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"Wrote {path}")


def _dim_h(ax, x0, x1, y, label, color="0.3"):
    ax.annotate("", (x0, y), (x1, y),
                arrowprops=dict(arrowstyle="<->", color=color, lw=0.8))
    ax.text((x0 + x1) / 2, y - 1.5, label, ha="center", va="top",
            fontsize=8, color=color)


def _dim_v(ax, x, y0, y1, label, color="0.3", off=2):
    ax.annotate("", (x + off, y0), (x + off, y1),
                arrowprops=dict(arrowstyle="<->", color=color, lw=0.8))
    ax.text(x + off + 1, (y0 + y1) / 2, label, ha="left", va="center",
            fontsize=8, color=color, rotation=90)


if __name__ == "__main__":
    g = build_geometry(SPEC)
    export_via_csv(g, out_data("via_coords.csv"))
    plot_layout(g, out_img("layout.png"))
