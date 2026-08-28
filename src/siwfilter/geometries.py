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

from .config import FAB_RULES


def _segment(lo: float, hi: float, p: float) -> np.ndarray:
    """Evenly spaced positions spanning EXACTLY [lo, hi], pitch ~p.

    Endpoints move continuously with lo/hi, so gap parameters stay smooth for
    the optimizer instead of snapping in p-sized jumps (the quantization bug
    documented in docs/dualmode_cavity/README.md)."""
    if hi <= lo:
        return np.array([])
    n = max(1, round((hi - lo) / p))
    return np.linspace(lo, hi, n + 1)


def _defect_index(offsets: np.ndarray, frac: float | None) -> int:
    """Map a 0..1 fraction to an index into `offsets` (a fence via to drop).

    `frac=None` -> -1, which never matches a real index, i.e. "no defect"."""
    if frac is None or len(offsets) == 0:
        return -1
    frac = max(0.0, min(1.0, frac))
    return round(frac * (len(offsets) - 1))


def min_via_centre_sep(d_mm: float, fab: str = "JLCPCB_2layer") -> float:
    """Smallest centre-to-centre spacing the fab allows for d_mm vias."""
    return d_mm + FAB_RULES[fab]["min_hole_to_hole"]


def _dedupe(vias, r: float):
    """Drop vias closer than the fab's minimum hole-to-hole spacing.

    The threshold used to be 0.9*d -- BELOW one via diameter, so it happily
    emitted pairs whose copper physically overlapped, and anything between
    0.9*d and d+0.5 was unbuildable on JLCPCB. Measured over corner_cut's
    search box, 36% of designs violated the 0.5mm hole-to-hole rule and the
    worst case was 1.353mm centre-to-centre for 1.5mm vias -- overlapping
    barrels. Found by eye in the 2D board view, which is exactly what that
    drawing is for.

    Merging rather than erroring is the right response: a via fence with two
    coincident vias merged is still a continuous fence, so the electrical
    intent survives while the layout becomes manufacturable.
    """
    lim2 = min_via_centre_sep(2.0 * r) ** 2
    out: list[tuple[float, float]] = []
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= lim2 for kx, ky in out):
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


# ---------------------------------------------------------------------------
# 5. Structural variants (2026-08-25) -- genuinely NEW knobs, not re-tunes of
# an existing parameter. Requested after the coupling-only sweeps found that
# re-tuning w_iris/w_ext/y_wall within the existing via-placement logic
# cannot close the gap to dual-mode for any of the three geometries. Each
# function here is a small delta on an existing one and reduces to it EXACTLY
# when the new kwarg is at its default -- so registering these does not
# change the already-validated originals' behaviour.
#
# All four still end in _dedupe(vias, r) with the SAME uniform d_via_mm as
# every other via in the layout, which is what makes _dedupe's existing
# fab-rule spacing check sufficient on its own -- no separate DRC validator
# needed for these, since a per-pair check with mixed diameters was the only
# case _dedupe doesn't already cover, and none of these introduce a second
# via size.
# ---------------------------------------------------------------------------
def circular_cross_nvia(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                        y_wall_mm=3.0, n_perturb=1, **_):
    """circular_cross with a CLUSTER of n_perturb vias at each arm tip instead
    of a single via -- a wider effective obstacle perturbing more of the
    mode's field at that point, rather than a stronger perturbation further
    out (which is what increasing w_iris/y_wall alone already does, and the
    coupling sweep showed saturates). n_perturb=1 reproduces circular_cross
    exactly. Cluster vias are laid out transverse to each arm at min_via_
    centre_sep spacing, which is why this needs no extra DRC check."""
    vias, info = circular_cross(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm,
                                p_via_mm, y_wall_mm)
    if n_perturb <= 1:
        return vias, info
    r = d_via_mm / 2.0
    step = min_via_centre_sep(2.0 * r) * 1.02   # tiny margin over the DRC floor
    cx = info["cx"]
    extra = []
    # arm_x tips (+-arm_x, 0): cluster spreads in y (transverse to the arm)
    for sx in (-1, 1):
        x0 = cx + sx * info["arm_x"]
        for k in range(1, n_perturb):
            off = step * ((k + 1) // 2) * (1 if k % 2 else -1)
            extra.append((x0, off))
    # arm_y tips (0, +-arm_y): cluster spreads in x
    for sy in (-1, 1):
        y0 = sy * info["arm_y"]
        for k in range(1, n_perturb):
            off = step * ((k + 1) // 2) * (1 if k % 2 else -1)
            extra.append((cx + off, y0))
    return _dedupe(list(vias) + extra, r), {**info, "n_perturb": n_perturb}


def circular_cross_ring2(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                         y_wall_mm=3.0, ring2_frac=0.0, ring2_span_deg=90.0, **_):
    """circular_cross plus a SECOND, inner, PARTIAL via arc at radius
    ring2_frac*R -- an intra-cavity iris-like obstacle the plain cross
    perturbation doesn't have. Deliberately a partial arc (ring2_span_deg
    wide), not a closed ring: a closed inner ring would wall off a smaller
    sub-cavity and likely kill the intended TE-pair resonance rather than
    perturb it, the same failure mode documented for half/quarter-mode
    (wrong boundary condition on the enclosed region). Centred on the x-axis
    (theta=0), on the same side as the arm_x perturbation, so it reinforces
    rather than competes with the existing split mechanism.
    ring2_frac=0 reproduces circular_cross exactly."""
    vias, info = circular_cross(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm,
                                p_via_mm, y_wall_mm)
    if ring2_frac <= 0:
        return vias, info
    r = d_via_mm / 2.0
    R2 = ring2_frac * info["R"]
    half_span = math.radians(ring2_span_deg) / 2.0
    ring = _arc(info["cx"], 0.0, R2, -half_span, half_span, p_via_mm, r)
    return _dedupe(list(vias) + ring, r), {**info, "R2": R2}


def circular_cross_taper(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                         y_wall_mm=3.0, wf_mm=0.0, **_):
    """circular_cross with a short FLAT launch facet at each feed aperture,
    replacing the tangent point circular_cross feeds through with an actual
    wall the Deslandes taper can flare onto -- see TAPER_TO_WALL in
    palace_dualmode_driven.py for why the plain circular fence gets no taper
    at all (a flare needs a flat wall of the right width to land on; a curve
    only touches the feed axis at one point). This is the direct test of the
    coupling-sweep doc's hypothesis that the taper-less launch, not the
    internal perturbation, is what caps circular_cross's achievable match.

    The facet is a flat wall at x=0/x=a_mm spanning y in [w_ext/2, w_ext/2+wf]
    (mirrored to -y), same pattern as the standard end-wall in
    palace_dualmode_driven._via_layout. The circular fence resumes from
    wherever it naturally reaches that same y, with a short horizontal via
    row closing the step between the flat facet and the resumed arc (the
    fence is a discrete via chain already, so this step is no different in
    kind from the pitch-sized gaps everywhere else in it).

    wf_mm<=0 reproduces circular_cross exactly (delegates directly -- no
    facet, no connector, byte-identical via list)."""
    if wf_mm <= 0:
        return circular_cross(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm,
                              p_via_mm, y_wall_mm)
    R, r, p = a_mm / 2.0, d_via_mm / 2.0, p_via_mm
    cx = R
    half_gap_lin = w_ext_mm / 2.0
    yw = min(half_gap_lin + wf_mm, R - p)
    vias = []
    for o in _segment(half_gap_lin, yw, p):
        vias.append((0.0, o)); vias.append((0.0, -o))
        vias.append((a_mm, o)); vias.append((a_mm, -o))
    theta_from = math.asin(min(0.99, yw / R))
    x_from = R - R * math.cos(theta_from)      # where the circle naturally reaches y=+-yw
    for xv in np.linspace(0.0, x_from, max(1, round(x_from / p)) + 1):
        vias.append((xv, yw)); vias.append((xv, -yw))
        vias.append((a_mm - xv, yw)); vias.append((a_mm - xv, -yw))
    vias += _arc(cx, 0.0, R, theta_from, math.pi - theta_from, p, r)
    vias += _arc(cx, 0.0, R, math.pi + theta_from, 2 * math.pi - theta_from, p, r)
    arm_x, arm_y = w_iris_mm / 2.0, y_wall_mm / 2.0
    for dx in (-arm_x, arm_x):
        vias.append((cx + dx, 0.0))
    for dy in (-arm_y, arm_y):
        vias.append((cx, dy))
    return _dedupe(vias, r), {"R": R, "cx": cx, "arm_x": arm_x, "arm_y": arm_y,
                              "wf_mm": wf_mm}


def circular_cross_iris(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                        y_wall_mm=8.0, wf_mm=1.0, **_):
    """Circular via fence (with the taper-launch facet proven in
    circular_cross_taper) perturbed by a REAL SPANNING transverse iris row at
    the cavity's equator (x=cx, the widest point -- local half-width is
    exactly R there) instead of circular_cross's centred 'cross' stub.

    Reasoning (2026-08-26, user-prompted architecture change instead of more
    parameter search): dual-mode and corner_cut -- the two best performers all
    session -- both couple via a structure that SPANS most of the cavity's
    transverse width (dual-mode's floating iris row; corner_cut's truncated
    wall). circular_cross's cross and rhombic's diagonal tuning vias are both
    localised STUBS near the centre that perturb the field locally without
    ever creating a real constriction -- plausibly why both stayed chronically
    over-coupled in every joint/coupling search this session regardless of
    internal tuning. This borrows dual-mode's own w_iris/y_wall row mechanism
    verbatim (same `_segment` construction), just centred on the circle's
    equator instead of a rectangle's midline. Not a delta on circular_cross --
    a different perturbation mechanism entirely, so there is no parent value
    this reduces to; wf_mm defaults to 1.0 (the screened optimum for the
    facet fix) since this variant is meant to combine both fixes."""
    R, r, p = a_mm / 2.0, d_via_mm / 2.0, p_via_mm
    cx = R
    half_gap_lin = w_ext_mm / 2.0
    vias = []
    if wf_mm > 0:
        yw = min(half_gap_lin + wf_mm, R - p)
        for o in _segment(half_gap_lin, yw, p):
            vias.append((0.0, o)); vias.append((0.0, -o))
            vias.append((a_mm, o)); vias.append((a_mm, -o))
        theta_from = math.asin(min(0.99, yw / R))
        x_from = R - R * math.cos(theta_from)
        for xv in np.linspace(0.0, x_from, max(1, round(x_from / p)) + 1):
            vias.append((xv, yw)); vias.append((xv, -yw))
            vias.append((a_mm - xv, yw)); vias.append((a_mm - xv, -yw))
    else:
        theta_from = math.asin(min(0.99, half_gap_lin / R))
    vias += _arc(cx, 0.0, R, theta_from, math.pi - theta_from, p, r)
    vias += _arc(cx, 0.0, R, math.pi + theta_from, 2 * math.pi - theta_from, p, r)
    # real transverse iris row at the equator -- identical construction to
    # _via_layout's internal row, just using R as the local half-width.
    if w_iris_mm is not None:
        for o in _segment(w_iris_mm / 2.0, R - y_wall_mm, p):
            vias.append((cx, o)); vias.append((cx, -o))
    return _dedupe(vias, r), {"R": R, "cx": cx, "wf_mm": wf_mm}


def corner_cut_2corner(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                       y_wall_mm=3.0, n_corners=1, **_):
    """corner_cut with a SECOND truncated corner at (+x,-y) -- mirrors the
    existing (+x,+y) cut across the feed axis, so the cavity stays symmetric
    about y=0 (unlike cutting an adjacent corner, which would break that
    symmetry and likely couple to spurious asymmetric modes). Two equal cuts
    scatter roughly twice the energy between the mode pair per unit cut
    depth, which is the direct test of whether corner_cut's IL/match problem
    is a coupling-STRENGTH shortfall (more cutting helps) or something else
    entirely (it doesn't). n_corners=1 reproduces corner_cut exactly."""
    vias, info = corner_cut(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm,
                            p_via_mm, y_wall_mm)
    if n_corners <= 1:
        return vias, info
    Li, r, p = a_mm, d_via_mm / 2.0, p_via_mm
    half, cut = info["half"], info["cut"]
    extra = []
    for o in _segment(w_ext_mm / 2.0, half, p):
        if o <= half - cut:
            extra.append((Li, -o))
    for xv in _segment(0.0, Li, p):
        if not (xv > Li - cut):
            extra.append((xv, -half))
    n = max(1, int(round(cut * math.sqrt(2) / p)))
    for t in np.linspace(0.0, 1.0, n + 1):
        extra.append((Li - cut * (1 - t), -(half - cut * t)))
    return _dedupe(list(vias) + extra, r), {**info, "n_corners": n_corners}


def rhombic_2diag(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                  y_wall_mm=3.0, w_iris2_mm=0.0, **_):
    """rhombic plus a SECOND pair of tuning vias on the FEED diagonal (near
    centre, along x through cx) -- the existing w_iris tuning vias sit only
    on the transverse diagonal. A second, independent knob on the other
    diagonal is what the coupling sweep found it structurally lacked: that
    sweep showed y_wall alone dominates the whole outcome (transverse-
    diagonal-only story), so this tests whether a feed-axis perturbation can
    contribute independently rather than being redundant with y_wall.
    w_iris2_mm=0 reproduces rhombic exactly."""
    vias, info = rhombic(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm,
                         p_via_mm, y_wall_mm)
    if w_iris2_mm <= 0:
        return vias, info
    r = d_via_mm / 2.0
    p, cx = p_via_mm, info["cx"]
    off = min(cx - p, w_iris2_mm / 2.0)
    extra = [(cx - off, 0.0), (cx + off, 0.0)]
    return _dedupe(list(vias) + extra, r), {**info, "w_iris2": w_iris2_mm}


def dualmode_2wall(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                   y_wall_mm=3.0, w_iris2_mm=0.0, iris_sep_mm=10.0, **_):
    """dualmode's landed rectangular cavity plus a SECOND floating transverse
    iris row, parallel to the first and offset by iris_sep_mm along the feed
    axis.

    User-prompted (2026-08-26): what happens with another wall in parallel,
    some distance from the existing one? Motivated by dual-mode's one
    persistent shortfall across this whole session -- a 60-eval Bayesian
    search of the existing single-iris 5D box (a, w_iris, x_iris, y_wall,
    w_ext) converged on the SAME point a much smaller search had already
    found (see overnight_dualmode_2026-08-24.md), with bandwidth stuck at
    ~318MHz against the 143.5MHz (5% FBW) target -- decisive evidence that
    box's optimum, not a search-budget problem. A second internal wall is a
    genuinely new degree of freedom that box never had: a two-iris cavity
    is closer to a proper 2-resonator coupled structure (each iris a
    partial reflector), which is the standard way a physical waveguide
    filter gets steeper skirts/narrower response without touching the
    external match at all -- untestable with only one iris no matter how
    much a/w_iris/w_ext/y_wall are searched.

    w_iris2_mm<=0 reproduces dualmode's single-iris layout exactly (same
    rectangular fence + one iris row, built the same way as
    palace_dualmode_driven._via_layout)."""
    Li, r, p = a_mm, d_via_mm / 2.0, p_via_mm
    half = a_mm / 2.0
    x_iris = x_iris_mm if x_iris_mm is not None else a_mm / 2.0
    vias = []
    for o in _segment(w_ext_mm / 2.0, half, p):
        vias.append((0.0, o)); vias.append((0.0, -o))
        vias.append((Li, o)); vias.append((Li, -o))
    for xv in np.linspace(0.0, Li, max(1, round(Li / p)) + 1):
        vias.append((xv, -half)); vias.append((xv, half))
    if w_iris_mm is not None:
        for o in _segment(w_iris_mm / 2.0, half - y_wall_mm, p):
            vias.append((x_iris, o)); vias.append((x_iris, -o))
    if w_iris2_mm and w_iris2_mm > 0:
        x_iris2 = min(Li - p, x_iris + iris_sep_mm)
        for o in _segment(w_iris2_mm / 2.0, half - y_wall_mm, p):
            vias.append((x_iris2, o)); vias.append((x_iris2, -o))
    return _dedupe(vias, r), {"x_iris": x_iris, "half": half}


def dualmode_cascade(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                     y_wall_mm=3.0, w_inter_mm=None, x_iris2_mm=None,
                     w_iris2_mm=None, y_iris_off_mm=0.0, y_iris2_off_mm=0.0,
                     iris_defect_frac=None, iris2_defect_frac=None,
                     w_ext2_mm=None, **_):
    """TWO dual-mode square cavities in series (N=4: 2 poles/cavity x 2
    cavities), joined by a NEW inter-cavity coupling row -- genuinely new
    mesh topology, not a delta: the single-cavity dualmode builder has no
    notion of a second cavity at all, so there is no parameter that
    reduces this to it.

    User-prompted (2026-08-26): "2 dualmodes in cascade" for an order-4
    filter. Both cavities share the same width a_mm (mirror-symmetric --
    the same convention cascade.py already uses for N>3 single-mode
    cavities), each with its OWN internal iris row for mode-splitting
    (x_iris/w_iris for cavity 1, x_iris2/w_iris2 for cavity 2, independently
    tunable but defaulting to mirror cavity 1's values), plus a THIRD
    transverse row at their shared boundary (x=a_mm): the inter-cavity
    coupling, w_inter_mm -- a FULL wall-to-wall partition (unlike the
    floating internal irises), the same convention the end walls and the
    original single-mode cascade.py's inter-cavity walls both use, since
    its job is dividing two resonators, not perturbing one.

    w_inter_mm defaults to w_ext_mm (stages start out coupled about as
    strongly as each is coupled to its own port, to be tuned from there).

    iris_defect_frac / iris2_defect_frac (2026-08-28, user-prompted: "remove
    vias if needed, inside the cavity, that would give more parameters"):
    drop ONE via pair (symmetric +-o, so each cavity's own up/down mirror
    stays intact) from that cavity's internal mode-splitting fence, at
    fractional position `frac` (0=nearest the iris gap, 1=nearest y_wall)
    along the fence. This is NOT reachable by continuously tuning w_iris/
    x_iris/y_iris_off_mm -- those move the whole fence; this punches a
    single localized defect/leak at a chosen point along an otherwise
    intact fence, a genuinely new coupling mechanism. Deliberately restricted
    to the INTERNAL fence only (never the perimeter side/end/inter-cavity
    via rows a few lines below) so SIW confinement is never compromised --
    only the mode-splitting perturbation is touched. Both default to None,
    reproducing the exact original fence with no defect (regression-
    verified).

    w_ext2_mm (2026-08-28): independent external-coupling aperture at the
    x=Li port, separate from `w_ext_mm` at x=0. Motivation: once cavity 1
    and cavity 2 are genuinely different (x_iris2_mm/w_iris2_mm/defects),
    breaking the cascade's x-mirror symmetry, the 4 driven eigenmodes are no
    longer simple even/odd combinations of two IDENTICAL cavities -- each
    is a different mix of "cavity-1 character" vs "cavity-2 character", so
    a mode localized mostly in cavity 1 couples well to port 1 but poorly
    to port 2 (or vice versa). A single symmetric `w_ext_mm` cannot
    simultaneously present good coupling to differently-localized modes at
    both ends; keeping the two ports independent lets the search find each
    end's own optimum. Observed directly: the FAB-tolerance confirm of the
    v4 fallback design showed exactly ONE real S11 null (-7.94dB at one
    frequency) with the other 3 poles never producing their own null,
    despite contributing to a broad S21 passband -- consistent with
    asymmetric per-mode port coupling, not a a scalar over/under-coupling
    problem `w_ext` alone (symmetric) can fix. Defaults to `None`, meaning
    "same as `w_ext_mm`" -- reproduces the exact prior symmetric-port
    behavior (regression-verified).

    y_iris_off_mm / y_iris2_off_mm (2026-08-27, user-prompted: "the inner
    parts of each cavity should change and they can be off centered too"):
    shift each cavity's OWN internal iris gap off the cavity's y-centerline
    -- previously hardcoded symmetric (mirrored +-o pairs about y=0).
    Motivation: the two cavities' exact mirror (x-swap) symmetry forces the
    4-pole spectrum into an even/odd pair split that neither coupling-width
    tuning nor a floating-coupling redesign could escape (see
    dualmode_cascade_floatinter's docstring); staggering x_iris2/w_iris2
    (already supported) breaks that x-symmetry, and this breaks the
    INTERNAL iris's own y-parity too -- an independent knob, same
    zero-board-size-cost philosophy. Both default to 0.0, reproducing the
    exact original symmetric iris (regression-verified). Clamped to
    +-y_wall_mm so the row never crosses its own cavity's side wall."""
    half = a_mm / 2.0
    r, p = d_via_mm / 2.0, p_via_mm
    Li = 2.0 * a_mm                      # total cavity length, both stages
    w_inter = w_inter_mm if w_inter_mm is not None else w_ext_mm
    x_iris1 = x_iris_mm if x_iris_mm is not None else a_mm / 2.0
    x_iris2 = a_mm + (x_iris2_mm if x_iris2_mm is not None else a_mm / 2.0)
    w_iris_b = w_iris2_mm if w_iris2_mm is not None else w_iris_mm

    w_ext2 = w_ext2_mm if w_ext2_mm is not None else w_ext_mm

    vias = []
    # end walls (true ports) at x=0 and x=Li -- independently sized apertures
    for o in _segment(w_ext_mm / 2.0, half, p):
        vias.append((0.0, o)); vias.append((0.0, -o))
    for o in _segment(w_ext2 / 2.0, half, p):
        vias.append((Li, o)); vias.append((Li, -o))
    # continuous side walls the full length (both cavities share the width)
    for xv in np.linspace(0.0, Li, max(1, round(Li / p)) + 1):
        vias.append((xv, -half)); vias.append((xv, half))
    # inter-cavity coupling wall at the shared boundary (full extent)
    for o in _segment(w_inter / 2.0, half, p):
        vias.append((a_mm, o)); vias.append((a_mm, -o))
    # each cavity's own floating internal mode-splitting iris -- off_1/2
    # clamped to +-y_wall_mm so the shifted row stays inside the cavity.
    if w_iris_mm is not None:
        off1 = max(-y_wall_mm, min(y_wall_mm, y_iris_off_mm))
        offsets1 = _segment(w_iris_mm / 2.0, half - y_wall_mm, p)
        drop1 = _defect_index(offsets1, iris_defect_frac)
        for i, o in enumerate(offsets1):
            if i == drop1:
                continue
            vias.append((x_iris1, o + off1)); vias.append((x_iris1, -o + off1))
    if w_iris_b is not None:
        off2 = max(-y_wall_mm, min(y_wall_mm, y_iris2_off_mm))
        offsets2 = _segment(w_iris_b / 2.0, half - y_wall_mm, p)
        drop2 = _defect_index(offsets2, iris2_defect_frac)
        for i, o in enumerate(offsets2):
            if i == drop2:
                continue
            vias.append((x_iris2, o + off2)); vias.append((x_iris2, -o + off2))
    return _dedupe(vias, r), {"x_iris": x_iris1, "x_iris2": x_iris2, "half": half}


def dualmode_cascade_floatinter(a_mm, w_iris_mm, x_iris_mm, w_ext_mm, d_via_mm, p_via_mm,
                                y_wall_mm=3.0, w_inter_mm=None, x_iris2_mm=None,
                                w_iris2_mm=None, y_wall_inter_mm=0.0, **_):
    """dualmode_cascade with a FLOATING inter-cavity coupling row (standoff
    y_wall_inter_mm from the side walls, same construction as the internal
    mode-splitting irises) instead of a full wall-to-wall partition.

    Root-cause motivated (2026-08-27): eigenmode ground truth showed the
    4-pole spectrum from a single centered wall-to-wall coupling slot never
    converges to the ideal's near-symmetric outer gaps (measured ~90MHz vs
    ~38MHz at the best (w_iris, w_inter_mm) found by a full 2D search,
    ideal wants ~46/48) -- the two cavities' mirror symmetry means the 4
    poles split into an even/odd pair under cavity-swap, and a full
    wall-to-wall slot's y-profile couples unevenly to the two internal
    (w_iris-split) field patterns, capping what ANY (w_iris, w_inter_mm)
    combination can achieve with that one coupling shape. Making the row
    floating (leakage paths past its ends too, not just through the centre
    gap) changes that y-overlap profile -- a genuinely different coupling
    mechanism, not a parameter delta on the same one.

    y_wall_inter_mm=0.0 reproduces dualmode_cascade() exactly (regression-
    verified: identical via list)."""
    half = a_mm / 2.0
    r, p = d_via_mm / 2.0, p_via_mm
    Li = 2.0 * a_mm
    w_inter = w_inter_mm if w_inter_mm is not None else w_ext_mm
    x_iris1 = x_iris_mm if x_iris_mm is not None else a_mm / 2.0
    x_iris2 = a_mm + (x_iris2_mm if x_iris2_mm is not None else a_mm / 2.0)
    w_iris_b = w_iris2_mm if w_iris2_mm is not None else w_iris_mm

    vias = []
    for o in _segment(w_ext_mm / 2.0, half, p):
        vias.append((0.0, o)); vias.append((0.0, -o))
        vias.append((Li, o)); vias.append((Li, -o))
    for xv in np.linspace(0.0, Li, max(1, round(Li / p)) + 1):
        vias.append((xv, -half)); vias.append((xv, half))
    # inter-cavity coupling row -- now a FLOATING segment (standoff
    # y_wall_inter_mm), same construction as the internal irises below.
    for o in _segment(w_inter / 2.0, half - y_wall_inter_mm, p):
        vias.append((a_mm, o)); vias.append((a_mm, -o))
    if w_iris_mm is not None:
        for o in _segment(w_iris_mm / 2.0, half - y_wall_mm, p):
            vias.append((x_iris1, o)); vias.append((x_iris1, -o))
    if w_iris_b is not None:
        for o in _segment(w_iris_b / 2.0, half - y_wall_mm, p):
            vias.append((x_iris2, o)); vias.append((x_iris2, -o))
    return _dedupe(vias, r), {"x_iris": x_iris1, "x_iris2": x_iris2, "half": half}


LAYOUTS = {
    "halfmode": halfmode,
    "circular_cross": circular_cross,
    "rhombic": rhombic,
    "quartermode": quartermode,
    "corner_cut": corner_cut,
    "circular_cross_nvia": circular_cross_nvia,
    "circular_cross_ring2": circular_cross_ring2,
    "circular_cross_taper": circular_cross_taper,
    "circular_cross_iris": circular_cross_iris,
    "corner_cut_2corner": corner_cut_2corner,
    "rhombic_2diag": rhombic_2diag,
    "dualmode_2wall": dualmode_2wall,
    "dualmode_cascade": dualmode_cascade,
    "dualmode_cascade_floatinter": dualmode_cascade_floatinter,
}
