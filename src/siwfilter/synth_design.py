"""Physics-derived cascade design: calibrate -> invert -> assemble.

This replaces black-box search as the PRIMARY design route for the inline
cascade. Written 2026-08-30 after a long session in which a GP search over
the full filter never beat -5 dB S11 in 60+ driven evaluations, while the
calibrate-and-invert route below reached each of its targets in about three
cheap solves apiece.

WHY (all measured this session, not assumed):

  * Calibrations measure a SMOOTH observable on a SMALL structure and they
    converged: k(w_iris) from a 2-cavity eigenmode split landed within 2% of
    the Chebyshev target; the fc correction put N=4 exactly on 2.870 GHz.

  * Sweeps and searches measure a COMPOSITE observable on the WHOLE filter
    and they did not. The passband width is DISCONTINUOUS in w_ext: below a
    coupling threshold only the centre pole clears -3 dB so the measured band
    is a single pole, above it all N poles merge and the band jumps. Measured
    on N=3: 16 / 22 / 36 / 65 / 215 MHz, with the 143.5 MHz target sitting
    inside that jump. Any GP whose objective contains that bandwidth inherits
    the problem, because a GP models smooth functions.

  * The failure signature agreed: the N=3 driven S11 showed three reflection
    zeros (2.809 / 2.869 / 2.989 GHz -- the right pole COUNT, so the topology
    was fine) but unevenly spaced with -6..-11 dB ripple between them instead
    of -16 dB equiripple. That is k and Qe mismatched relative to each other,
    and k was already calibrated and verified.

DESIGN CHAIN
    synthesis        -> k[i], Qe                 (Chebyshev, exact)
    calibrate()      -> k(w_iris)   -> w_iris    (2-cavity eigenmode)
    calibrate_qe()   -> Qe(w_ext)   -> w_ext     (1-cavity driven, loaded Q)
    fc correction    -> l_cav                    (TE101 + iris loading)

Each step inverts a measured curve instead of searching. A GP is then only
worth running as a LOCAL polish around the result -- the regime it already
works in for the dual-mode topology.

Caveats kept in the open:
  * calibrate_qe's Qu is the dielectric limit 1/tan_d (270.3, matching the
    closed-cavity eigenmode), so it ignores conductor, via-leakage and
    radiation loss and slightly OVER-estimates Qe.
  * closed-cavity eigenmodes cannot see the external apertures, so the
    resulting fc is high by ~100 MHz until the driven correction is applied.
"""
from __future__ import annotations

import json
import math

import numpy as np

from .config import C0, FilterSpec, out_data
from .synthesis import synthesize
from .topologies.cascade import CascadeTopology, _len_keys, _iris_keys


def invert_k(cal: dict, k: float) -> float:
    """Physical iris width for a synthesized coupling k, from calibrate()."""
    fit = cal.get("w_of_k")
    if fit is None:
        raise ValueError("k calibration has no w_of_k fit (need >=3 good points)")
    ks = [r["k"] for r in cal["points"].values() if r.get("ok")]
    if ks and not (min(ks) <= k <= max(ks)):
        print(f"  WARNING: k={k:.5f} outside calibrated [{min(ks):.5f},{max(ks):.5f}]"
              " -- extrapolating")
    return float(np.polyval(fit, k))


def invert_qe(cal: dict, qe: float) -> float:
    """Physical w_ext for a synthesized Qe, from calibrate_qe()."""
    fit = cal.get("w_of_logQe")
    if fit is None:
        raise ValueError("Qe calibration has no w_of_logQe fit")
    rng = cal.get("Qe_range")
    if rng and not (rng[0] <= qe <= rng[1]):
        print(f"  WARNING: Qe={qe:.2f} outside calibrated [{rng[0]:.2f},{rng[1]:.2f}]"
              " -- extrapolating")
    return float(np.polyval(fit, math.log(qe)))


def correct_l_cav(spec: FilterSpec, fc_meas_ghz: float, l_cav_mm: float) -> float:
    """Cavity length that moves a measured resonance onto f0.

    Backs the EFFECTIVE transverse dimension out of the measured (fc, l_cav)
    pair -- which folds in whatever loading was present -- then re-solves the
    TE101 relation at f0 holding it fixed:

        (1/a_eff)^2 = (2*fc*sqrt(eps_r)/c)^2 - (1/L)^2
        (1/L_new)^2 = (2*f0*sqrt(eps_r)/c)^2 - (1/a_eff)^2

    Verified to +8 MHz on the first application; the residual is closed by
    iterating against a DRIVEN solve, since a closed cavity cannot see the
    external apertures (they pull fc down ~100 MHz).
    """
    eps = spec.substrate.eps_r
    fc, L = fc_meas_ghz * 1e9, l_cav_mm * 1e-3
    inv_a2 = (2 * fc * math.sqrt(eps) / C0) ** 2 - (1.0 / L) ** 2
    rhs = (2 * spec.f0 * math.sqrt(eps) / C0) ** 2 - inv_a2
    return l_cav_mm if rhs <= 0 else (1.0 / math.sqrt(rhs)) * 1e3


def design_from_calibration(spec: FilterSpec, k_cal: dict, qe_cal: dict,
                            l_taper_mm: float = 15.73) -> dict:
    """Assemble a cascade design by INVERTING the two calibrations."""
    from .siw_geometry import microstrip_width_50ohm

    syn = synthesize(spec)
    N = spec.N
    ws = [invert_k(k_cal, float(k)) for k in syn.k]
    n_ind = (len(ws) + 1) // 2
    iris_ind = ws[:n_ind]
    w_ext = invert_qe(qe_cal, float(syn.qe_in))

    # Cavity length: start from the k-calibration's own (w_iris, fc) point and
    # correct for the loading it measured. The driven correction that follows
    # is what removes the external-aperture pull.
    pts = [(w, r) for w, r in k_cal["points"].items() if r.get("ok")]
    pts.sort(key=lambda t: float(t[0]))
    wsx = np.array([float(w) for w, _ in pts])
    fcs = np.array([r["fc"] for _, r in pts])
    l_cal = k_cal.get("l_cav_mm", 34.4)
    l_cav = correct_l_cav(spec, float(np.interp(iris_ind[0], wsx, fcs)), l_cal)

    p: dict[str, float] = {
        "w_ext": round(w_ext, 2),
        "l_taper": l_taper_mm,
        "w_ms": round(microstrip_width_50ohm(spec.substrate.eps_r,
                                             spec.substrate.h) * 1e3, 4),
    }
    for key in _len_keys(N):
        p[key] = round(l_cav, 2)
    for key, v in zip(_iris_keys(N), iris_ind):
        p[key] = round(v, 2)
    return {"params": p, "targets": {"k": [float(x) for x in syn.k],
                                     "Qe": float(syn.qe_in)},
            "w_iris_all": [round(x, 2) for x in ws]}


def run_pipeline(spec: FilterSpec, device: str = "auto", np_ranks: int = 4,
                 w_irises: list[float] | None = None,
                 w_exts: list[float] | None = None,
                 cache: bool = True) -> dict:
    """Full physics chain for the cascade topology. Returns the design dict.

    Calibrations are cached per (substrate, vias, f0) so the expensive part is
    paid once and reused across orders -- N=3 and N=4 share both curves,
    differing only in the targets they invert.
    """
    topo = CascadeTopology()
    key = (f"{spec.substrate_name}_d{spec.d_via*1e3:.2f}_p{spec.p_via*1e3:.2f}"
           f"_f{spec.f0/1e9:.3f}")
    path = out_data("cascade_pipeline_cal.json")
    store = {}
    if cache:
        try:
            store = json.load(open(path))
        except (OSError, ValueError):
            store = {}
    entry = store.get(key, {})

    if "k" not in entry:
        print(f"[pipeline] k(w_iris) calibration for {key} ...", flush=True)
        entry["k"] = topo.calibrate(spec, w_irises=w_irises)
    else:
        print(f"[pipeline] reusing cached k calibration for {key}", flush=True)

    if "qe" not in entry:
        print(f"[pipeline] Qe(w_ext) calibration for {key} ...", flush=True)
        entry["qe"] = topo.calibrate_qe(spec, w_exts=w_exts, device=device,
                                        np_ranks=np_ranks)
    else:
        print(f"[pipeline] reusing cached Qe calibration for {key}", flush=True)

    if cache:
        store[key] = entry
        json.dump(store, open(path, "w"), indent=2,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))

    d = design_from_calibration(spec, entry["k"], entry["qe"])
    print(f"[pipeline] N={spec.N} targets k={[round(x,5) for x in d['targets']['k']]} "
          f"Qe={d['targets']['Qe']:.2f}", flush=True)
    print(f"[pipeline] -> {d['params']}", flush=True)
    return d
