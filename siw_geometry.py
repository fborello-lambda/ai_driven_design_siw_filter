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

from config import C0, EPS0, MU0, SPEC, FilterSpec
from synthesis import synthesize, SynthesisResult

_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json")

ETA0 = math.sqrt(MU0 / EPS0)        # free-space wave impedance ~376.73 ohm

# Placeholder coupling: w_iris = a_eff * IRIS_C * k**(1/3). Monotonic in k and
# gives ~0.2-0.3*a_eff windows for k~0.05. REPLACED by calibrate.py fit w(k).
IRIS_C = 0.60


# ---------------------------------------------------------------------------
# Core SIW design equations (CLAUDE.md sec. 7)
# ---------------------------------------------------------------------------
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

    # drawable primitives
    vias: list[tuple[float, float]] = field(default_factory=list)  # (x,y) centers
    cavity_bounds: list[tuple[float, float]] = field(default_factory=list)
    taper_polys: list[np.ndarray] = field(default_factory=list)
    feed_polys: list[np.ndarray] = field(default_factory=list)
    board: tuple[float, float, float, float] = (0, 0, 0, 0)  # xmin,xmax,ymin,ymax

    checks: dict[str, tuple[bool, str]] = field(default_factory=dict)

    @property
    def L_inner(self) -> float:
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
    L_cav = L_eff                              # first pass: no iris loading yet
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
        W_ms=W_ms, eps_eff_ms=eps_eff_ms, L_taper=L_taper, L_feed=L_feed,
        Z_PI=Z_PI,
        lambda_g_siw=lambda_g_siw, lambda_g_ms=lambda_g_ms, lambda0=spec.lambda0,
    )
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

    # N-1 internal transverse walls (irises) on the shared side columns.
    # y grid across the width at pitch p, symmetric about 0, centre gap removed.
    # Endpoint vias at y = +/-half coincide with the side wall -> deduped below.
    n_trans = int(round(g.a_siw / p))
    y_grid = np.linspace(-half, half, n_trans + 1)
    wall_x = [xs[i * col_per_cav] for i in range(1, N)]
    for i, x_wall in enumerate(wall_x):
        w = g.iris_widths[i]
        for y in y_grid:
            if abs(y) > w / 2.0:               # leave centred gap of width w
                vias.append((x_wall, y))

    g.vias = _dedupe_vias(vias, min_sep=0.9 * spec.d_via)
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

    # Board outline with margin
    margin = 3e-3
    xmin = -Lt - Lf - margin
    xmax = L_inner + Lt + Lf + margin
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
