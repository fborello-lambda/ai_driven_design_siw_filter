"""Extract the realized coupling matrix (k_i,i+1, Qe, f0) from a measured
S11/S21 sweep by least-squares fitting the standard coupled-resonator model
directly to the data -- no new EM simulation, pure post-processing.

Built 2026-08-27 to diagnose why dualmode_cascade's aggregate (fc, bandwidth)
score could not tell a genuine N=4 equal-ripple passband apart from a narrow
near-single-pole notch sitting next to a detuned satellite mode (see
docs/geometry_exploration/dualmode_enhancements_2026-08-26.md, round 3).
Matching an aggregate single-peak metric says nothing about whether the
underlying poles are actually distributed the way the target order's
coupling matrix needs; fitting the couplings directly answers that.

Currently supports the mirror-symmetric N=4 topology only (k12=k34, single
k23, equal Qe at both ports) -- dualmode_cascade's actual structure. Extend
`build_M`/`fit_couplings` for other symmetric N if needed.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from .synthesis import chebyshev_g, sparams_from_matrix


def build_symmetric_n4_M(ms1: float, m12: float, m23: float) -> np.ndarray:
    """(N+2)x(N+2)=6x6 normalized coupling matrix for a mirror-symmetric N=4
    in-line filter: k12=k34=m12, k23=m23, equal external coupling ms1 at
    both source and load."""
    M = np.zeros((6, 6))
    M[0, 1] = M[1, 0] = ms1
    M[1, 2] = M[2, 1] = m12
    M[2, 3] = M[3, 2] = m23
    M[3, 4] = M[4, 3] = m12
    M[4, 5] = M[5, 4] = ms1
    return M


def fit_couplings_n4(f_ghz: np.ndarray, s11_db: np.ndarray, s21_db: np.ndarray,
                     f0_guess_ghz: float = 2.87) -> dict:
    """Least-squares fit (fbw, k12=k34, k23, Qe, f0) to a measured sweep.

    Returns physical (already FBW-scaled) k12, k34, k23, and Qe = 1/(fbw*ms1^2)
    -- directly comparable to the ideal values from
    ``optimize.ideal_target_db``'s underlying ``synthesis.coupling_matrix``.
    """
    f_hz = np.asarray(f_ghz) * 1e9
    s11_meas = 10 ** (np.asarray(s11_db) / 20.0)
    s21_meas = 10 ** (np.asarray(s21_db) / 20.0)
    g = chebyshev_g(4, 0.1)
    x0 = [0.06, 1.0 / np.sqrt(g[0] * g[1]), 1.0 / np.sqrt(g[1] * g[2]),
          1.0 / np.sqrt(g[2] * g[3]), f0_guess_ghz * 1e9]

    def resid(x):
        fbw, ms1, m12, m23, f0 = x
        M = build_symmetric_n4_M(ms1, m12, m23)
        s11, s21 = sparams_from_matrix(M, fbw, f0, f_hz)
        return np.concatenate([np.abs(s11) - s11_meas, np.abs(s21) - s21_meas])

    lb = [1e-3, 0.05, 0.05, 0.05, f0_guess_ghz * 1e9 * 0.9]
    ub = [0.5, 5.0, 5.0, 5.0, f0_guess_ghz * 1e9 * 1.1]
    res = least_squares(resid, x0, bounds=(lb, ub), max_nfev=5000)
    fbw, ms1, m12, m23, f0 = res.x
    return {"k12": fbw * m12, "k34": fbw * m12, "k23": fbw * m23,
            "Qe": 1.0 / (fbw * ms1 ** 2), "f0_ghz": f0 / 1e9,
            "fbw_fit": fbw, "cost": res.cost, "success": res.success}


if __name__ == "__main__":
    import json
    from .config import FilterSpec
    from .optimize import ideal_target_db
    from .synthesis import coupling_matrix

    spec4 = FilterSpec(N=4)
    g = chebyshev_g(spec4.N, spec4.ripple_db)
    ideal = {"k12": spec4.FBW / np.sqrt(g[1] * g[2]),
             "k23": spec4.FBW / np.sqrt(g[2] * g[3]),
             "Qe": g[0] * g[1] / spec4.FBW}
    print("=== IDEAL N=4 ===", ideal)

    for path, key in [("output/data/dmcasc_directed_v3_best.json", "fab_metrics")]:
        d = json.load(open(path))
        r = d[key]
        fit = fit_couplings_n4(r["f"], r["s11_db"], r["s21_db"], f0_guess_ghz=r["fc"])
        print(f"\n{path}: {fit}")
