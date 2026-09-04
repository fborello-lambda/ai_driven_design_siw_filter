"""Map the synthesized filter spec to physical SIW dimensions (first pass).

Implements the design-equation cookbook in CLAUDE.md sec. 7 (Cassivi-Wu a_eff,
TE10 cutoff, TE101 cavity length, via design rules, microstrip-to-SIW taper).

Topology (matches synthesis.py): N TE101 cavities inline, coupled by N-1
internal inductive irises (gaps in transverse via walls) sized from k[i,i+1],
plus 2 external couplings provided by microstrip tapers sized from Qe ->
N+1 coupling structures total.

IMPORTANT: the iris-width <-> k and taper <-> Qe maps here are ANALYTICAL
PLACEHOLDERS to get the layout drawing going. The authoritative numbers come
from calibrate.py (CLAUDE.md sec. 6). Anything marked PLACEHOLDER is expected
to be overwritten by EM calibration.

Run:  uv run python siw_geometry.py
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

from .config import C0, EPS0, MU0, SPEC, FilterSpec, out_data
from .synthesis import synthesize, SynthesisResult

_CACHE = out_data("calibration.json")

ETA0 = math.sqrt(MU0 / EPS0)        # free-space wave impedance ~376.73 ohm

# Placeholder coupling: w_iris = a_eff * IRIS_C * k**(1/3). Monotonic in k and
# gives ~0.2-0.3*a_eff windows for k~0.05. REPLACED by calibrate.py fit w(k).
IRIS_C = 0.60


# ---------------------------------------------------------------------------
# Core SIW design equations (CLAUDE.md sec. 7)
# ---------------------------------------------------------------------------
def _segment_positions(lo: float, hi: float, p: float) -> np.ndarray:
    """Evenly-spaced positions spanning EXACTLY [lo, hi] inclusive at pitch ~p.

    The endpoints move continuously with lo/hi, so a gap-width parameter that
    sets `lo` takes effect smoothly rather than only when it crosses a point
    of some fixed grid. Same construction (and same motivation) as
    palace_dualmode_driven._segment_vias -- see the iris comment in
    _build_primitives for the measured quantization this removes.

    Returns an empty array when the gap has swallowed the whole arm (hi <= lo).
    """
    if hi <= lo:
        return np.array([])
    n = max(1, round((hi - lo) / p))
    return np.linspace(lo, hi, n + 1)


def a_eff_from_a_siw(a_siw: float, d: float, p: float) -> float:
    """Cassivi-Wu equivalent width: a_eff = a_siw - d^2/(0.95*p)."""
    return a_siw - d**2 / (0.95 * p)


def a_siw_from_a_eff(a_eff: float, d: float, p: float) -> float:
    """Inverse of Cassivi-Wu: physical via-row spacing for a target a_eff."""
    return a_eff + d**2 / (0.95 * p)


def te10_cutoff(a_eff: float, eps_r: float) -> float:
    """TE10 cutoff frequency f_c10 = c / (2*a_eff*sqrt(eps_r))."""
    return C0 / (2.0 * a_eff * math.sqrt(eps_r))


def te101_length(f101: float, a_eff: float, eps_r: float) -> float:
    """Effective cavity length L_eff for a TE101 resonance at f101.

    f101 = (c/(2*sqrt(eps_r))) * sqrt((1/a_eff)^2 + (1/L_eff)^2)
    -> 1/L_eff^2 = (2*f101*sqrt(eps_r)/c)^2 - (1/a_eff)^2
    """
    rhs = (2.0 * f101 * math.sqrt(eps_r) / C0) ** 2 - (1.0 / a_eff) ** 2
    if rhs <= 0:
        raise ValueError("No real TE101 length: a_eff too small for this f101.")
    return 1.0 / math.sqrt(rhs)


def siw_guided_wavelength(f: float, a_eff: float, eps_r: float) -> float:
    """Guided wavelength of the TE10 SIW mode at frequency f."""
    k0 = 2.0 * math.pi * f * math.sqrt(eps_r) / C0
    beta = math.sqrt(k0**2 - (math.pi / a_eff) ** 2)
    return 2.0 * math.pi / beta


def siw_char_impedance(f: float, a_eff: float, h: float, eps_r: float,
                       fc: float) -> float:
    """SIW characteristic (power-voltage) impedance, CLAUDE.md sec. 7.

    Z_PI = (pi^2 * eta * h) / (8 * a_eff * sqrt(1 - (fc/f)^2)),
    eta = ETA0 / sqrt(eps_r) (intrinsic impedance of the dielectric).
    """
    eta = ETA0 / math.sqrt(eps_r)
    return (math.pi**2 * eta * h) / (8.0 * a_eff * math.sqrt(1.0 - (fc / f) ** 2))


# ---------------------------------------------------------------------------
# Microstrip (Hammerstad/Wheeler) for the feed + taper
# ---------------------------------------------------------------------------
def microstrip_width_50ohm(eps_r: float, h: float, Z0: float = 50.0) -> float:
    """50-ohm microstrip width via Hammerstad inverse synthesis (W/h>2 branch)."""
    B = 377.0 * math.pi / (2.0 * Z0 * math.sqrt(eps_r))
    woh = (2.0 / math.pi) * (
        B - 1.0 - math.log(2.0 * B - 1.0)
        + ((eps_r - 1.0) / (2.0 * eps_r))
        * (math.log(B - 1.0) + 0.39 - 0.61 / eps_r)
    )
    return woh * h


def microstrip_eps_eff(eps_r: float, h: float, W: float) -> float:
    """Effective permittivity of a microstrip line (Hammerstad)."""
    return (eps_r + 1) / 2 + (eps_r - 1) / 2 * 1.0 / math.sqrt(1 + 12 * h / W)


def microstrip_guided_wavelength(f: float, eps_eff: float) -> float:
    return C0 / (f * math.sqrt(eps_eff))


# ---------------------------------------------------------------------------
# Grounded coplanar waveguide (CPWG / conductor-backed CPW) for the SMA launch
# ---------------------------------------------------------------------------
# Why this exists (2026-08-29, user-prompted): the real Taoglas
# EMPCB.SMAFSTJ.B.HT footprint is a CPWG launch -- a centre signal pad with
# coplanar ground pads either side (legs at +-2.62mm) on the SAME layer, over
# the bottom ground plane. The cavity feed, however, is a microstrip (no
# coplanar grounds). Feeding a 50-ohm microstrip directly from a CPWG pad
# without matching the CPWG section itself leaves an impedance step right at
# the connector. These functions synthesise the CPWG gap `s` that makes the
# launch 50 ohm for a given trace width, so the launch -> microstrip
# transition can then be a smooth taper rather than a step.
#
# Formulation: Wadell / Simons conformal mapping for conductor-backed CPW.
#   k1 = W/(W+2s)                      (upper, coplanar half)
#   k3 = tanh(pi*W/(4h)) / tanh(pi*(W+2s)/(4h))   (lower, backed half)
#   eps_eff = (1 + eps_r * q) / (1 + q),  q = [K(k3)/K'(k3)] / [K(k1)/K'(k1)]
#   Z0 = 60*pi / sqrt(eps_eff) / ( K(k1)/K'(k1) + K(k3)/K'(k3) )
# K/K' ratio via Hilberg's closed-form approximation (accurate to ~1e-7),
# avoiding a scipy elliptic-integral dependency in this module.
def _kkp_ratio(k: float) -> float:
    """K(k)/K'(k) via Hilberg's approximation (k in (0,1))."""
    kp = math.sqrt(max(1e-15, 1.0 - k * k))
    if k <= 1.0 / math.sqrt(2.0):
        return math.pi / math.log(2.0 * (1.0 + math.sqrt(kp)) / (1.0 - math.sqrt(kp)))
    return math.log(2.0 * (1.0 + math.sqrt(k)) / (1.0 - math.sqrt(k))) / math.pi


def cpwg_impedance(eps_r: float, h: float, W: float, s: float) -> tuple[float, float]:
    """(Z0, eps_eff) of a grounded CPW: signal width W, gap s each side,
    substrate thickness h. All lengths in the same units."""
    k1 = W / (W + 2.0 * s)
    k3 = math.tanh(math.pi * W / (4.0 * h)) / math.tanh(math.pi * (W + 2.0 * s) / (4.0 * h))
    r1, r3 = _kkp_ratio(k1), _kkp_ratio(k3)
    q = r3 / r1
    eps_eff = (1.0 + eps_r * q) / (1.0 + q)
    z0 = 60.0 * math.pi / (math.sqrt(eps_eff) * (r1 + r3))
    return z0, eps_eff


def cpwg_width_50ohm_fixed_gnd(eps_r: float, h: float, y_gnd: float,
                               Z0: float = 50.0,
                               w_lo: float = 0.2e-3, w_hi: float = 6e-3) -> float:
    """Signal width W giving Z0 when the coplanar GROUND EDGE is pinned at
    `y_gnd` from the trace centreline (so the gap is y_gnd - W/2).

    This is the footprint-constrained case: an edge-launch SMA fixes where the
    ground pads are (its legs), so the free variable is the trace width, not
    the gap. Wider trace -> smaller gap AND more capacitance -> lower Z0, so
    Z0 is monotonically decreasing in W and bisection is well posed."""
    for _ in range(200):
        w_mid = 0.5 * (w_lo + w_hi)
        gap = y_gnd - w_mid / 2.0
        if gap <= 1e-5:            # trace has eaten the gap: too wide
            w_hi = w_mid
            continue
        z, _ = cpwg_impedance(eps_r, h, w_mid, gap)
        if z > Z0:
            w_lo = w_mid           # too narrow / too high Z0 -> widen
        else:
            w_hi = w_mid
    return 0.5 * (w_lo + w_hi)


def cpwg_gap_50ohm(eps_r: float, h: float, W: float, Z0: float = 50.0,
                   s_lo: float = 1e-6, s_hi: float = 5e-3) -> float:
    """Gap `s` (each side) giving Z0 for a CPWG of signal width W.

    Bisection on the monotonic Z0(s): a wider gap weakens the coplanar
    (capacitive) loading, so Z0 rises with s. Returns metres if inputs are
    metres. Raises if the target is unreachable in [s_lo, s_hi] -- which is a
    real design signal (e.g. W far too wide for this substrate), not
    something to silently clamp."""
    z_lo, _ = cpwg_impedance(eps_r, h, W, s_lo)
    z_hi, _ = cpwg_impedance(eps_r, h, W, s_hi)
    if not (z_lo <= Z0 <= z_hi):
        raise ValueError(
            f"Z0={Z0} unreachable for W={W}, h={h}, eps_r={eps_r}: "
            f"Z0(s={s_lo})={z_lo:.2f}, Z0(s={s_hi})={z_hi:.2f} ohm")
    for _ in range(200):
        s_mid = 0.5 * (s_lo + s_hi)
        z_mid, _ = cpwg_impedance(eps_r, h, W, s_mid)
        if z_mid < Z0:
            s_lo = s_mid
        else:
            s_hi = s_mid
    return 0.5 * (s_lo + s_hi)


# ---------------------------------------------------------------------------
# Placeholder coupling maps (REPLACED by calibrate.py)
# ---------------------------------------------------------------------------
def iris_width_from_k(k: float, a_eff: float) -> float:
    """PLACEHOLDER analytical estimate of internal iris window width from k.

    Monotonic increasing in k. Real values come from the EM-fit w(k) in
    calibrate.py (CLAUDE.md sec. 6); this only seeds the layout drawing.
    """
    return a_eff * IRIS_C * (k ** (1.0 / 3.0))


def _cache_key(spec: FilterSpec) -> str:
    return (f"{spec.substrate_name}_d{spec.d_via*1e3:.2f}_p{spec.p_via*1e3:.2f}"
            f"_f{spec.f0/1e9:.3f}")


def calibrated_iris_width(spec: FilterSpec, k: float) -> float | None:
    """Iris width [m] for coupling k from the cached EM fit, or None if absent.

    Reads calibration.json directly (no import of calibrate.py -> no import
    cycle). The fit is only valid inside the swept k-range; extrapolation
    returns None so the caller falls back to the placeholder.
    """
    if not os.path.exists(_CACHE):
        return None
    try:
        cal = json.load(open(_CACHE)).get(_cache_key(spec), {}).get("iris")
    except (OSError, ValueError):
        return None
    if not cal:
        return None
    ks = [p[1] for p in cal["points"]]
    if not (min(ks) <= k <= max(ks)):       # don't trust extrapolation
        return None
    return float(np.polyval(cal["w_of_k"], k)) * 1e-3


# ---------------------------------------------------------------------------
# Geometry container
# ---------------------------------------------------------------------------
@dataclass
class Geometry:
    spec: FilterSpec
    syn: SynthesisResult

    # core dimensions [m]
    a_eff: float
    a_siw: float
    fc_actual: float
    L_eff: float
    L_cav: float
    iris_widths: list[float]            # N-1 internal irises (from k)
    iris_calibrated: bool               # True if widths came from the EM fit
    w_ext: float                        # external (input/output) iris gap [m] -> Qe

    # feed/taper [m]
    W_ms: float
    eps_eff_ms: float
    L_taper: float
    L_feed: float
    Z_PI: float

    # diagnostics
    lambda_g_siw: float
    lambda_g_ms: float
    lambda0: float

    # optional per-cavity lengths [m]; if set, overrides the uniform L_cav for
    # wall placement (end cavities can be shorter than the middle). len == N.
    L_cavs: list[float] | None = None

    # drawable primitives
    vias: list[tuple[float, float]] = field(default_factory=list)  # (x,y) centers
    ext_iris_vias: list[tuple[float, float]] = field(default_factory=list)  # input/output iris
    cavity_bounds: list[tuple[float, float]] = field(default_factory=list)
    taper_polys: list[np.ndarray] = field(default_factory=list)
    feed_polys: list[np.ndarray] = field(default_factory=list)
    board: tuple[float, float, float, float] = (0, 0, 0, 0)  # xmin,xmax,ymin,ymax

    checks: dict[str, tuple[bool, str]] = field(default_factory=dict)

    @property
    def L_inner(self) -> float:
        if self.L_cavs:
            return sum(self.L_cavs)
        return self.spec.N * self.L_cav


def build_geometry(spec: FilterSpec = SPEC,
                   syn: SynthesisResult | None = None) -> Geometry:
    """Build the analytical first-pass SIW geometry from the spec + synthesis."""
    if syn is None:
        syn = synthesize(spec)
    sub = spec.substrate
    d, p = spec.d_via, spec.p_via

    # --- core resonator/waveguide dimensions ---
    a_eff = C0 / (2.0 * spec.fc_target * math.sqrt(sub.eps_r))   # from target fc
    a_siw = a_siw_from_a_eff(a_eff, d, p)
    fc_actual = te10_cutoff(a_eff, sub.eps_r)
    L_eff = te101_length(spec.f0, a_eff, sub.eps_r)
    L_cav = L_eff                              # analytical TE101 length; matched-feed openEMS + CST confirm ~38mm is correct
    # prefer EM-calibrated iris widths (calibrate.py); fall back to placeholder
    iris_widths = []
    iris_calibrated = True
    for k in syn.k:
        w_cal = calibrated_iris_width(spec, k)
        if w_cal is None:
            iris_calibrated = False
            iris_widths.append(iris_width_from_k(k, a_eff))
        else:
            iris_widths.append(w_cal)

    # --- feed + taper ---
    W_ms = microstrip_width_50ohm(sub.eps_r, sub.h)
    eps_eff_ms = microstrip_eps_eff(sub.eps_r, sub.h, W_ms)
    lambda_g_ms = microstrip_guided_wavelength(spec.f0, eps_eff_ms)
    L_taper = lambda_g_ms / 4.0                # ~quarter-wave taper at f0
    L_feed = lambda_g_ms / 4.0                 # short straight 50-ohm lead-in
    Z_PI = siw_char_impedance(spec.f0, a_eff, sub.h, sub.eps_r, fc_actual)

    lambda_g_siw = siw_guided_wavelength(spec.f0, a_eff, sub.eps_r)

    g = Geometry(
        spec=spec, syn=syn,
        a_eff=a_eff, a_siw=a_siw, fc_actual=fc_actual, L_eff=L_eff, L_cav=L_cav,
        iris_widths=iris_widths, iris_calibrated=iris_calibrated,
        w_ext=0.6 * a_siw,                 # input/output iris gap (Qe knob); tune in CST/openEMS
        W_ms=W_ms, eps_eff_ms=eps_eff_ms, L_taper=L_taper, L_feed=L_feed,
        Z_PI=Z_PI,
        lambda_g_siw=lambda_g_siw, lambda_g_ms=lambda_g_ms, lambda0=spec.lambda0,
    )

    # Override the analytical first pass with the Palace-optimized final design.
    from .config import USE_OPTIMIZED, OPTIMIZED_DESIGN
    if USE_OPTIMIZED:
        od = OPTIMIZED_DESIGN
        g.L_cav = od["L_cav_mm"] * 1e-3
        g.iris_widths = [od["w_iris_mm"] * 1e-3] * len(g.iris_widths)
        g.iris_calibrated = True
        g.w_ext = od["w_ext_mm"] * 1e-3
        g.W_ms = od["W_ms_mm"] * 1e-3
        g.L_taper = od["L_taper_mm"] * 1e-3

    _build_primitives(g)
    _check_design_rules(g)
    return g


def _dedupe_vias(vias: list[tuple[float, float]],
                 min_sep: float) -> list[tuple[float, float]]:
    """Drop vias whose centres are closer than ``min_sep`` (overlapping copper).

    Removes the coincident corner vias where transverse iris walls meet the
    side walls. O(n^2) but n is small (a few hundred).
    """
    kept: list[tuple[float, float]] = []
    s2 = min_sep * min_sep
    for x, y in vias:
        if all((x - kx) ** 2 + (y - ky) ** 2 >= s2 for kx, ky in kept):
            kept.append((x, y))
    return kept


def _build_primitives(g: Geometry) -> None:
    """Fill in via centers, cavity bounds, taper/feed polygons, board outline."""
    spec = g.spec
    N, p = spec.N, spec.p_via
    half = g.a_siw / 2.0
    L_inner = g.L_inner

    vias: list[tuple[float, float]] = []

    # y grid across the width at pitch p, symmetric about 0 (for transverse walls)
    n_trans = int(round(g.a_siw / p))
    y_grid = np.linspace(-half, half, n_trans + 1)

    if g.L_cavs:
        # --- per-cavity lengths: place side columns segment-by-segment so every
        # internal wall lands exactly on a side column (no clashing corners). ---
        edges = [0.0]
        for Lc in g.L_cavs:
            edges.append(edges[-1] + Lc)
        for x0, x1 in zip(edges[:-1], edges[1:]):
            ncol = max(1, int(round((x1 - x0) / p)))
            for x in np.linspace(x0, x1, ncol + 1):
                vias.append((x, +half))
                vias.append((x, -half))
        wall_x = edges[1:-1]
    else:
        # Side-wall via columns along x at y = +/- a_siw/2. Force the column count
        # to a multiple of N so the internal transverse walls land *exactly* on a
        # side column (equal cavities, no clashing corner vias). p_side stays close
        # to p_via.
        n_side = int(round(L_inner / p))
        n_side = max(N, N * round(n_side / N))     # nearest multiple of N
        col_per_cav = n_side // N
        xs = np.linspace(0.0, L_inner, n_side + 1)
        for x in xs:
            vias.append((x, +half))
            vias.append((x, -half))
        wall_x = [xs[i * col_per_cav] for i in range(1, N)]

    # N-1 internal transverse walls (irises) on the shared side columns.
    # Endpoint vias at y = +/-half coincide with the side wall -> deduped below.
    #
    # 2026-08-30: the arm vias SPAN [w/2, half] instead of being filtered out
    # of the fixed y_grid. Filtering made w_iris QUANTIZED: a via only appears
    # or disappears when w/2 crosses a grid point, i.e. in ~p-sized steps of w.
    # Measured here (a_siw=39.79, p=3.0 -> grid step 3.06mm), six calibration
    # irises collapsed onto three distinct geometries:
    #     w_iris  6.0 and  9.0 -> identical mesh, k=0.01424
    #     w_iris 12.0 and 15.0 -> identical mesh, k=0.05828
    #     w_iris 18.0 and 21.0 -> identical mesh, k=0.12657
    # The cascade search's whole w_iris range (4.0-15.9mm) therefore spanned
    # only ~2 distinct structures, so the GP was tuning a coupling knob that
    # mostly did nothing -- the direct cause of its high screen-out rate and
    # failure to converge. w_ext never had this problem (it places offsets
    # from w_ext/2 outward, already continuous), which is why only the
    # internal coupling was crippled.
    #
    # This is the same defect palace_dualmode_driven._segment_vias was written
    # to fix ("...makes gap-width parameters genuinely continuous instead of
    # only taking effect in ~p-sized steps when a threshold crosses a fixed
    # grid point"); dual-mode got the fix, cascade never did.
    for i, x_wall in enumerate(wall_x):
        w = g.iris_widths[i]
        for y in _segment_positions(w / 2.0, half, p):
            vias.append((x_wall, +y))
            vias.append((x_wall, -y))

    g.vias = _dedupe_vias(vias, min_sep=0.9 * spec.d_via)

    # External coupling irises: transverse via rows at the input/output faces
    # (x=0 and x=L_inner) with a central gap of w_ext. Same placement as the
    # CST .bas: centres start at w_ext/2 + 0.5*p and step outward by p. Kept in
    # a separate list so they don't duplicate in the main via loop.
    ext: list[tuple[float, float]] = []
    if g.w_ext > 0.0:
        # Iris vias from the gap edge (w_ext/2) outward at pitch p. Keep only
        # those that stay clear of the side wall at y=half (no overlap with the
        # corner via). Offsets reference w_ext so the gap stays tunable in CST.
        radius = spec.d_via / 2.0
        k = 0
        while True:
            off = g.w_ext / 2.0 + (k + 0.5) * p
            if off + radius > half - radius:      # would touch/cross the side wall
                break
            for x_face in (0.0, L_inner):
                ext.append((x_face, +off))
                ext.append((x_face, -off))
            k += 1
    g.ext_iris_vias = ext

    # Cavity bounds from the (grid-snapped) wall positions.
    edges = [0.0] + wall_x + [L_inner]
    g.cavity_bounds = [(edges[i], edges[i + 1]) for i in range(N)]

    # Tapers: trapezoid from microstrip width W_ms (outer) to a_siw (SIW edge).
    Lt, Lf, W = g.L_taper, g.L_feed, g.W_ms
    # input taper occupies x in [-Lt, 0]
    in_taper = np.array([
        (-Lt, +W / 2), (0.0, +half), (0.0, -half), (-Lt, -W / 2),
    ])
    in_feed = np.array([
        (-Lt - Lf, +W / 2), (-Lt, +W / 2), (-Lt, -W / 2), (-Lt - Lf, -W / 2),
    ])
    # output mirrored about x = L_inner
    out_taper = np.array([
        (L_inner + Lt, +W / 2), (L_inner, +half),
        (L_inner, -half), (L_inner + Lt, -W / 2),
    ])
    out_feed = np.array([
        (L_inner + Lt + Lf, +W / 2), (L_inner + Lt, +W / 2),
        (L_inner + Lt, -W / 2), (L_inner + Lt + Lf, -W / 2),
    ])
    g.taper_polys = [in_taper, out_taper]
    g.feed_polys = [in_feed, out_feed]

    # Board outline. In x the board ENDS AT THE FEED, with no margin: the
    # launch is an edge-mount SMA, whose body straddles the board edge and
    # whose pin lands on the very end of the trace. This is also exactly what
    # the mesher builds (`palace_driven.build_mesh`: substrate box from
    # X0=-(Lt+Lf) to X1=L_inner+Lt+Lf) and what `cst_export` draws.
    #
    # It did NOT used to be. Until 2026-09-04 a 3mm margin was added on all
    # four sides, so the KiCad board outline and the 2D layout drawing were
    # 6mm longer than the substrate that was simulated, and the CPWG pads sat
    # 3mm INSIDE the edge -- a board on which the connector cannot be
    # mounted. Only the transverse margin is real (the mesher's
    # `ym = half + 3.0`): it is the dielectric shoulder outside the via wall.
    margin = 3e-3
    xmin = -Lt - Lf
    xmax = L_inner + Lt + Lf
    ymin = -half - margin
    ymax = +half + margin
    g.board = (xmin, xmax, ymin, ymax)


def _check_design_rules(g: Geometry) -> None:
    """Evaluate the SIW via design rules (CLAUDE.md sec. 7)."""
    spec = g.spec
    d, p = spec.d_via, spec.p_via
    lg = g.lambda_g_siw
    pmax = g.lambda0 * math.sqrt(spec.substrate.eps_r) / 4.0

    pd = p / d
    g.checks = {
        "0.5 <= p/d <= 2.5": (0.5 <= pd <= 2.5, f"p/d = {pd:.3f}"),
        "d < lambda_g/5":     (d < lg / 5, f"d={d*1e3:.2f}mm, lg/5={lg/5*1e3:.2f}mm"),
        "d < a_eff/5":        (d < g.a_eff / 5, f"a_eff/5={g.a_eff/5*1e3:.2f}mm"),
        "p < lambda0*sqrt(er)/4": (p < pmax, f"p={p*1e3:.2f}mm, max={pmax*1e3:.2f}mm"),
        "single-mode (f0<2*fc)": (spec.f0 < 2 * g.fc_actual,
                                  f"f0={spec.f0/1e9:.3f}, 2*fc={2*g.fc_actual/1e9:.3f}GHz"),
    }


def _mm(x: float) -> str:
    return f"{x*1e3:.3f} mm"


if __name__ == "__main__":
    g = build_geometry(SPEC)
    spec, sub = g.spec, g.spec.substrate

    print(f"=== SIW geometry (analytical first pass) ===")
    print(f"substrate     : {sub.name} (eps_r={sub.eps_r}, h={_mm(sub.h)})")
    print(f"f0            : {spec.f0/1e9:.3f} GHz   target fc: {spec.fc_target/1e9:.3f} GHz")
    print()
    print(f"a_eff         : {_mm(g.a_eff)}")
    print(f"a_siw         : {_mm(g.a_siw)}  (via-row center spacing)")
    print(f"fc actual     : {g.fc_actual/1e9:.3f} GHz")
    print(f"L_eff = L_cav : {_mm(g.L_cav)}  (TE101, no iris loading yet)")
    print(f"cavity        : {_mm(g.a_eff)} x {_mm(g.L_cav)} (near-square)")
    print(f"L_inner       : {_mm(g.L_inner)}  ({spec.N} cavities)")
    print()
    src = "EM-CALIBRATED (calibrate.py)" if g.iris_calibrated \
        else "PLACEHOLDER w(k) -> run calibrate.py --sweep"
    print(f"internal irises [{src}]:")
    for i, (k, w) in enumerate(zip(g.syn.k, g.iris_widths), start=1):
        print(f"  iris {i}{i+1}: k={k:.4f} -> w = {_mm(w)}")
    print()
    print(f"feed / taper:")
    print(f"  50-ohm microstrip W_ms : {_mm(g.W_ms)} (eps_eff={g.eps_eff_ms:.3f})")
    print(f"  taper length L_taper   : {_mm(g.L_taper)} (~lambda_g_ms/4)")
    print(f"  SIW Z_PI @ f0          : {g.Z_PI:.2f} ohm")
    print()
    print(f"diagnostics:")
    print(f"  lambda_g (SIW) : {_mm(g.lambda_g_siw)}")
    print(f"  lambda_g (MS)  : {_mm(g.lambda_g_ms)}")
    print(f"  lambda0        : {_mm(g.lambda0)}")
    print(f"  total vias     : {len(g.vias)}")
    bx = g.board
    print(f"  board outline  : {(bx[1]-bx[0])*1e3:.1f} x {(bx[3]-bx[2])*1e3:.1f} mm")
    print()
    print("design-rule checks:")
    all_ok = True
    for rule, (ok, detail) in g.checks.items():
        mark = "OK " if ok else "!! "
        all_ok &= ok
        print(f"  [{mark}] {rule:28s} {detail}")
    print(f"\n{'ALL RULES PASS' if all_ok else 'SOME RULES FAIL — review above'}")
