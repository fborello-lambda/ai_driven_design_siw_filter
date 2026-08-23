"""Cavity via-layouts for the geometry exploration.

Every candidate topology differs from the landed dual-mode cavity ONLY in
where the vias go. The substrate box, feed taper, SMA launch, ground pads,
port faces and face classification are identical and already validated
(palace_dualmode_driven.build_mesh), so each geometry here is a small pure
function returning via centres in mm rather than another copy of a 400-line
mesh builder.

Convention shared by every layout: the cavity spans x in [0, Li] with the
feed axis along y=0, so the existing taper/port code lines up unchanged. Each
function returns (vias, info) where `info` carries whatever the 2D plot wants
to annotate.

Feasibility note: this project is a TWO-LAYER board (one 0.76mm substrate,
top+bottom copper). The largest published SIW miniaturisations -- folded
(FSIW), double-folded, multilayer circular -- need 3+ copper layers and are
NOT buildable on this stack, so they are deliberately absent. What remains
feasible in-plane:

  dualmode      the landed reference: square cavity, floating internal iris row
  halfmode      cut along the E-plane symmetry; one side wall omitted, that
                edge left open. ~50% width. (Hong & Lancaster / HMSIW
                literature: the symmetry plane of TE10 is a magnetic wall, so
                half the cavity resonates at the same frequency.)
  circular_cross  circular via fence + a cross/plus of perturbation vias at
                the centre instead of an iris row -- circular cavities carry
                better Q per unit area, and the cross splits the degenerate
                pair by perturbing the two orthogonal mode patterns unequally.
  rhombic       diamond via fence; the diagonal walls couple the degenerate
                pair without any separate internal iris.
  quartermode   cut along BOTH symmetry planes. ~75% area, the most aggressive
                in-plane option, at the cost of radiation from two open sides.

The open edges of half/quarter mode are not modelled with a magnetic wall:
the substrate simply continues to the board margin whose outer face is
Absorbing, which is physically what an open SIW edge does (it radiates). That
is the honest model -- the radiation loss those topologies are known for shows
up in the result rather than being assumed away.
"""
from __future__ import annotations

import math

import numpy as np


def _segment(lo: float, hi: float, p: float) -> np.ndarray:
    """Evenly spaced positions spanning EXACTLY [lo, hi], pitch ~p.

    Endpoints move continuously with lo/hi, so gap parameters stay smooth for
    the optimizer instead of snapping in p-sized jumps (the quantization bug
    documented in docs/dualmode_cavity/README.md)."""
    if hi <= lo:
        return np.array([])
    n = max(1, round((hi - lo) / p))
    return np.linspace(lo, hi, n + 1)


def _dedupe(vias, r: float):
    out: list[tuple[float, float]] = []
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= (0.9 * 2 * r) ** 2 for kx, ky in out):
            out.append((float(x), float(y)))
    return out


def _arc(cx, cy, radius, a0, a1, p, r):
    """Vias along an arc at ~p pitch."""
    span = abs(a1 - a0) * radius
    n = max(1, int(round(span / p)))
    return [(cx + radius * math.cos(a), cy + radius * math.sin(a))
            for a in np.linspace(a0, a1, n + 1)]


# ---------------------------------------------------------------------------
# 1. Half-mode: the landed cavity cut along y=0, upper half kept.
# ---------------------------------------------------------------------------
def halfmode(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
             y_wall_mm=3.0, w_cav_mm=None, **_):
    """TWO half-mode TE101 cells in series, sharing a coupling iris.

    IMPORTANT -- this is not a cut of the dual-mode cavity, and the first
    attempt that was got a decisive negative result worth recording. HMSIW
    works by cutting on a plane where E is MAXIMUM, which behaves as a
    magnetic wall. The dual-mode cavity runs on TE102/TE201, whose field goes
    as sin(2*pi*y/a): its centre plane is a NULL, i.e. an ELECTRIC wall.
    Cutting there and leaving it open imposes the opposite boundary condition
    to the one the mode wants, and the resonance is destroyed -- measured
    S21 = -37.9 dB with no passband anywhere in 1.5-5 GHz.

    TE101 is the mode whose centre plane IS a field maximum, so that is what
    gets half-moded here: a_mm is the TOTAL length of the two cells, w_cav_mm
    the transverse width of the (half) cavity, and the open edge is y=0. Two
    cells give N=2, matching the dual-mode's order for a fair comparison.
    """
    Li, r, p = a_mm, d_via_mm / 2.0, p_via_mm
    # transverse width of the half cell; a TE101 half-cell is ~a_cell/2 wide
    top = w_cav_mm if w_cav_mm is not None else a_mm / 4.0
    vias = []
    # end walls x=0 and x=Li, only the kept half, with the external iris gap
    for o in _segment(w_ext_mm / 2.0, top, p):
        vias.append((0.0, o)); vias.append((Li, o))
    # the single remaining side wall at y=top
    for xv in np.linspace(0.0, Li, max(1, round(Li / p)) + 1):
        vias.append((xv, top))
    # internal iris row, held off the open edge and the side wall
    x_iris = x_iris_mm if x_iris_mm is not None else Li / 2.0
    if w_iris_mm is not None:
        for o in _segment(w_iris_mm / 2.0, top - y_wall_mm, p):
            vias.append((x_iris, o))
    return _dedupe(vias, r), {"x_iris": x_iris, "top": top, "open_edge_y": 0.0}


# ---------------------------------------------------------------------------
# 2. Circular cavity with a cross of perturbation vias.
# ---------------------------------------------------------------------------
def circular_cross(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                   y_wall_mm=3.0, **_):
    """Circular via fence of diameter a_mm, fed on the y=0 axis through gaps
    of width w_ext at both ends. Instead of an iris ROW, four perturbation
    vias sit on a cross (plus) at the centre: w_iris sets the cross arm
    length, y_wall the transverse arm. Unequal arms perturb the two
    degenerate modes differently, which is what splits them."""
    R, r, p = a_mm / 2.0, d_via_mm / 2.0, p_via_mm
    cx = R                       # cavity spans x in [0, a_mm]
    vias = []
    # fence, skipping the feed apertures at theta ~ 0 and pi
    half_gap = math.asin(min(0.99, (w_ext_mm / 2.0) / R))
    vias += _arc(cx, 0.0, R, half_gap, math.pi - half_gap, p, r)
    vias += _arc(cx, 0.0, R, math.pi + half_gap, 2 * math.pi - half_gap, p, r)
    # cross perturbation at the centre: arms along x (w_iris) and y (y_wall)
    arm_x, arm_y = w_iris_mm / 2.0, y_wall_mm / 2.0
    for dx in (-arm_x, arm_x):
        vias.append((cx + dx, 0.0))
    for dy in (-arm_y, arm_y):
        vias.append((cx, dy))
    return _dedupe(vias, r), {"R": R, "cx": cx, "arm_x": arm_x, "arm_y": arm_y}


# ---------------------------------------------------------------------------
# 3. Rhombic / diamond cavity.
# ---------------------------------------------------------------------------
def rhombic(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
            y_wall_mm=3.0, **_):
    """Diamond fence with vertices on the feed axis (x=0, x=a_mm) and at
    +-half transverse. The slanted walls reflect energy between the two
    orthogonal mode patterns, so the pair couples WITHOUT a separate iris row
    -- w_iris instead sets a pair of tuning vias on the transverse diagonal,
    which is the knob that trims the split."""
    Li, r, p = a_mm, d_via_mm / 2.0, p_via_mm
    # diagonals: Li along the feed axis, 2*half transverse. y_wall_mm scales
    # the transverse diagonal, so the diamond's aspect ratio is a free knob --
    # that ratio is what sets the split between the two degenerate modes.
    half = max(p, y_wall_mm)
    cx = Li / 2.0
    vias = []
    # four slanted walls, leaving a feed gap of w_ext at each vertex on y=0
    gap = w_ext_mm / 2.0
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        # from the on-axis vertex out to the transverse vertex
        x0 = cx + sx * (Li / 2.0)
        p0 = np.array([x0, 0.0])
        p1 = np.array([cx, sy * half])
        seg = p1 - p0
        L = float(np.hypot(*seg))
        n = max(1, int(round(L / p)))
        for t in np.linspace(0.0, 1.0, n + 1):
            pt = p0 + t * seg
            # Open a real feed aperture of +-w_ext/2 at each on-axis vertex.
            # An earlier version required the via to be EXACTLY at the vertex
            # to be skipped, so the walls converged into the feed and closed
            # it: the cavity still resonated (S11 dipped to -17.7dB at
            # 2.45GHz) but nothing coupled out (S21 = -75dB).
            if abs(pt[1]) < gap:
                continue
            vias.append((float(pt[0]), float(pt[1])))
    # tuning vias on the transverse diagonal trim the mode split
    if w_iris_mm:
        for sy in (1, -1):
            vias.append((cx, sy * min(half - p, w_iris_mm / 2.0)))
    return _dedupe(vias, r), {"half": half, "cx": cx}


# ---------------------------------------------------------------------------
# 4. Quarter-mode: cut along BOTH symmetry planes.
# ---------------------------------------------------------------------------
def quartermode(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                y_wall_mm=3.0, w_cav_mm=None, **_):
    """Two quarter-mode TE101 cells in series: each cell is cut on BOTH of its
    field-maximum planes, so it keeps one quadrant of a TE101 cavity and
    radiates from two open edges. The most aggressive in-plane option.

    Built on TE101 for the same reason as halfmode() -- a quarter of the
    DUAL-MODE cavity would be cutting on nulls, which does not resonate (see
    that docstring). a_mm is the total length of the two cells; w_cav_mm the
    transverse width. Expect worse IL and Q than half-mode: two open edges
    radiate roughly twice as much, so judge it on the measured numbers rather
    than on the area saving alone."""
    Li, r, p = a_mm, d_via_mm / 2.0, p_via_mm
    top = w_cav_mm if w_cav_mm is not None else a_mm / 4.0
    vias = []
    # fed end walls at both ends, each with a coupling aperture at the open edge
    for o in _segment(w_ext_mm / 2.0, top, p):
        vias.append((0.0, o)); vias.append((Li, o))
    for xv in np.linspace(0.0, Li, max(1, round(Li / p)) + 1):
        vias.append((xv, top))                           # the one closed side wall
    # y=0 stays open (magnetic wall); coupling iris between the two cells
    x_iris = x_iris_mm if x_iris_mm is not None else Li / 2.0
    if w_iris_mm is not None:
        for o in _segment(w_iris_mm / 2.0, top - y_wall_mm, p):
            vias.append((x_iris, o))
    return _dedupe(vias, r), {"x_iris": x_iris, "top": top, "Li": Li}


# ---------------------------------------------------------------------------
# 5. Square cavity with a cut corner -- the classic dual-mode perturbation.
# ---------------------------------------------------------------------------
def corner_cut(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
               y_wall_mm=3.0, **_):
    """Square cavity with one corner truncated by a diagonal via row.

    The textbook way to couple a degenerate pair (Hong & Lancaster Ch.10): the
    45-degree wall is asymmetric with respect to the two orthogonal mode
    patterns, so it scatters energy between them. w_iris_mm sets how deep the
    cut is, which is the coupling knob -- no separate internal iris needed.

    Included as the low-risk member of the set: it stays closest to the
    already-working dual-mode cavity, so it is the one most likely to resonate
    where expected."""
    Li, r, p = a_mm, d_via_mm / 2.0, p_via_mm
    half = a_mm / 2.0
    cut = max(p, w_iris_mm)          # diagonal cut depth measured along each wall
    vias = []
    # end walls with the feed apertures; the x=Li wall must ALSO stop short of
    # the truncated corner, otherwise it fills back in the corner the diagonal
    # is supposed to remove.
    for o in _segment(w_ext_mm / 2.0, half, p):
        vias.append((0.0, o)); vias.append((0.0, -o))
        vias.append((Li, -o))
        if o <= half - cut:
            vias.append((Li, o))
    # side walls, stopping short of the truncated corner (+x, +y)
    for xv in _segment(0.0, Li, p):
        if not (xv > Li - cut):
            vias.append((xv, half))
        vias.append((xv, -half))
    # the 45-degree corner wall itself
    n = max(1, int(round(cut * math.sqrt(2) / p)))
    for t in np.linspace(0.0, 1.0, n + 1):
        vias.append((Li - cut * (1 - t), half - cut * t))
    return _dedupe(vias, r), {"cut": cut, "half": half}


LAYOUTS = {
    "halfmode": halfmode,
    "circular_cross": circular_cross,
    "rhombic": rhombic,
    "quartermode": quartermode,
    "corner_cut": corner_cut,
}
