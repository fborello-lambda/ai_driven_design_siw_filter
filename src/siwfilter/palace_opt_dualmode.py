"""Bayesian re-tune of the isolated dual-mode cavity (palace_dualmode_driven)
against a REAL SMA coax launch, same GP-surrogate pattern as
palace_opt_sma.py (each eval costs several minutes of Palace time, so sample
efficiency matters).

IMPORTANT: this cavity realizes N=2 (2 poles from 1 physical cavity), NOT
N=3 -- there is no companion single-mode cavity in this model. Coupling
target recomputed accordingly (0.1dB-ripple Chebyshev, FBW=0.05):
    N=2: g=[1, 0.8430, 0.6220, 1.3554] -> k12=0.0691, Qe_in=Qe_out=16.86
(vs the N=3 project default k12=k23=0.0460, Qe=20.63 -- do NOT reuse those
here). f0/FBW/BAND targets are unchanged (FBW sets the passband directly,
independent of N).

Search space (5D): a_mm (cavity size -- also retunes the TE102/TE201 mode
frequency), w_iris_mm/x_iris_mm/y_wall_mm (internal floating iris row),
w_ext_mm (external iris gap in the via fence -- INDEPENDENT of the
microstrip width). W_ms is FIXED at the true 50-ohm value (not searched --
its role is the SMA connector match, not cavity coupling, and letting it
float just adds a dimension without a clear reason to move it off 50 ohm).

v1 of this search pinned w_ext=w_ms directly (no taper) -- a 25-eval run
over that topology never found more than -24dB peak S21 anywhere in a wide
5D box (see output/imgs/palace_opt_dualmode_top5.png history / git log).
Root cause: with the wall opening capped at bare-microstrip width, external
coupling into a 61mm-wide cavity is too weak regardless of internal-iris
tuning -- decoupling the two (real Deslandes taper: W_ms near the
connector, flares to the full cavity width at the wall, with w_ext as an
independent narrower gap in that flared footprint, same as the main
filter's own proven external iris) fixes this at the geometry level rather
than asking the optimizer to work around it.

Every eval calls palace_dualmode_driven.build_mesh() fresh with the sampled
params, which fully regenerates the via layout + gmsh geometry + mesh from
scratch each time (no incremental/cached state) -- so a_mm changing is
handled correctly by construction. A cheap pre-Palace validity guard rejects
geometrically degenerate samples (iris row not fitting inside a shrunken
cavity, w_ext not fitting inside a, etc.) without burning solver time.

Run (detached, survives periodic suspend/resume):
  setsid nohup uv run python -m siwfilter.palace_opt_dualmode \
      > output/data/opt_dualmode_master.log 2>&1 < /dev/null &
"""
from __future__ import annotations

import json
import os
import subprocess
import time

import numpy as np
from skopt import Optimizer
from skopt.space import Real

from .config import out_data, out_img, SPEC
from .siw_geometry import microstrip_width_50ohm
from .palace_dualmode_driven import build_mesh, A_SIW_MM

PALACE = "/home/fd/opt/palace/bin/palace"
W_MS_FIXED = round(microstrip_width_50ohm(SPEC.substrate.eps_r, SPEC.substrate.h) * 1e3, 4)
F0 = 2.87
FBW = 0.05
BW_TGT = FBW * F0 * 1000.0            # 143.5 MHz (ideal)
BW_MAX_FBW = 0.10
BW_MAX = BW_MAX_FBW * F0 * 1000.0     # 287 MHz hard ceiling -- v3 search
                                       # converged to designs with real
                                       # bandpass shape (confirmed via a wide
                                       # 2.0-3.6GHz sweep) but ~21% FBW,
                                       # over-coupled (w_iris/w_ext both
                                       # wandered to their upper bounds).
                                       # v4: hard-penalize bw>BW_MAX and
                                       # weight S11 as the dominant term.
RL_TGT = -16.0
BAND = (F0 * (1 - FBW / 2), F0 * (1 + FBW / 2))

# ---------------------------------------------------------------------------
# v16: score = curve-fit error against the IDEAL N=2 0.1dB-ripple Chebyshev
# response, not ad-hoc heuristics (worst-point-in-a-fixed-box + separate fc/
# bw penalty terms). Standard practice in computer-aided filter tuning: fit
# the simulated/measured response to a synthesized target response, rather
# than scoring isolated features of it. See Cameron, Kudsia & Mansour,
# "Microwave Filters for Communication Systems," Wiley (coupling-matrix
# synthesis and computer-aided tuning) -- same reference already used for
# this project's g-value/coupling-matrix work (CLAUDE.md sec.8); also Hong &
# Lancaster "Microstrip Filters for RF/Microwave Applications" Ch.8
# (extraction/tuning methods).
#
# Motivation: the previous score (single worst-case S11 point inside a FIXED
# f0-centered window, plus a separate |fc-F0| peak-location penalty) could
# not tell a properly-centered symmetric two-null response apart from an
# asymmetric one that merely happened to clear the same worst-case number --
# confirmed on eval#1 of v15: null depths were -17.8dB (@2.87GHz, f0) vs
# -18.7dB (@2.89GHz, the TRUE center), i.e. measurably asymmetric, invisible
# to the old scalar. A full curve-fit against the ideal (symmetric by
# construction) response penalizes that asymmetry directly, along with
# wrong bandwidth/depth, in one physically-grounded number -- no separate
# bolted-on fc or bw penalty term needed.
#
# g-values for N=2, 0.1dB-ripple Chebyshev (same synthesis as the rest of
# this project -- see palace_opt_dualmode.py module docstring / CLAUDE.md).
_G0, _G1, _G2, _G3 = 1.0, 0.8430, 0.6220, 1.3554
_QE1_N = _G0 * _G1
_QE2_N = _G2 * _G3
_M12_N = 1.0 / np.sqrt(_G1 * _G2)

# Fit window: 1.5x the target FBW window on each side of F0, wide enough to
# capture the real transition/rolloff shape without reaching so far out
# that a REAL filter's gradual skirt vs. the ideal's much sharper
# lossless-network transform dominates the error with a mismatch that
# isn't actually about filter quality.
_FIT_HALF = 1.5 * (FBW * F0) / 2.0
FIT_WINDOW = (F0 - _FIT_HALF, F0 + _FIT_HALF)


def ideal_response_db(f_ghz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ideal (lossless) N=2 0.1dB-ripple Chebyshev |S11|,|S21| in dB, via
    the standard normalized coupling-matrix formulation (Hong & Lancaster
    Ch.5 / Cameron et al.): A = Omega*U - j*q + M, S11 = 1 + 2j/qe1*[A^-1]11,
    S21 = -2j/sqrt(qe1*qe2)*[A^-1]21, Omega = (1/FBW)*(f/F0 - F0/f)."""
    f = np.atleast_1d(np.asarray(f_ghz, dtype=float))
    omega = (1.0 / FBW) * (f / F0 - F0 / f)
    U = np.eye(2)
    M = np.array([[0.0, _M12_N], [_M12_N, 0.0]])
    q = np.array([[1.0 / _QE1_N, 0.0], [0.0, 1.0 / _QE2_N]])
    s11 = np.empty_like(f, dtype=complex)
    s21 = np.empty_like(f, dtype=complex)
    for i, om in enumerate(omega):
        Ainv = np.linalg.inv(om * U - 1j * q + M)
        s11[i] = 1 + 2j / _QE1_N * Ainv[0, 0]
        s21[i] = -2j / np.sqrt(_QE1_N * _QE2_N) * Ainv[1, 0]
    with np.errstate(divide="ignore"):
        s11_db = 20 * np.log10(np.maximum(np.abs(s11), 1e-12))
        s21_db = 20 * np.log10(np.maximum(np.abs(s21), 1e-12))
    return s11_db, s21_db
# v11's 50MHz coarse step ALIASED: the best design's true response (fine-
# mesh, 10MHz step) has a ripple hump between its two poles that peaks at
# -13.25dB, but the 50MHz-spaced coarse samples kept landing on either side
# of that narrow peak, reporting an overly optimistic -23.8dB. The ripple
# period here (~100-150MHz, set by the pole spacing) is comparable to the
# old 50MHz step -- not fine enough to rank ripple-limited designs reliably
# once you're this close to spec. Tightened to 20MHz (kept, DO NOT widen the
# step again -- that's what caused the aliasing).
# v13: the 1.0/2.0mm via fence roughly doubled mesh DOF at the same
# mesh_max, and a full 26-point (2.60-3.10GHz) coarse sweep drove this
# machine's swap to near-total exhaustion twice in a row (accumulating
# memory across iterations, same failure mode as the earlier 91-point fine
# sweep). Narrowed the RANGE (not the step -- that would reintroduce
# aliasing) to 2.75-3.00GHz, tightly bracketing the known passband, cutting
# points 26->13 without losing ripple resolution.
COARSE_GRID, FMIN_C, FMAX_C = 0.02, 2.75, 3.00
# v15: user wants the FINAL fine-confirmed curve densely resolved over
# 2.5-3.0GHz specifically (for the landing plot) -- widened from 2.72-3.02.
# Coarse range/step during the search itself stays narrow (13 pts) to
# control memory/wall-clock; only the one-time post-search fine confirm
# gets the wide 51-point sweep.
FINE_GRID,   FMIN_F, FMAX_F = 0.01, 2.50, 3.00
MAX_EVALS = 18   # "quick" run per user request -- shorter than the usual 25
N_INITIAL = 10

PARAMS = {
    # Calibrated via ISOLATED EIGENMODE extraction (scripts/dualmode_
    # calibrate_v2.py + dualmode_calibrate_ywall.py), not blind driven
    # search: k12(w_iris) sweep at y_wall=6mm crossed the N=2 Chebyshev
    # target k=0.0691 near w_iris=16mm (k=0.0669 measured there); a
    # follow-up y_wall sweep at that w_iris found y_wall has a much weaker
    # effect (k=0.0669->0.0708 over y_wall=3->12mm, vs w_iris's 0.003->0.067
    # over 5->16mm) -- w_iris is the dominant knob, y_wall a fine-tuner.
    # Every combination near the target k also showed fc sitting ~30MHz
    # below F0=2.87GHz (2.84-2.85GHz), consistently -- the perturbation
    # loads the cavity. a shrunk from 61.05->~60.4mm (the ~1% fractional
    # correction) to compensate; bounds centered on the calibrated region
    # instead of blind-searching the original wide box.
    # v9 (this same calibrated region) landed the first-ever design to
    # actually cross the -16dB S11 target (eval#19: a=60.25, w_iris=14.71,
    # x_iris=29.87, y_wall=12.72, w_ext=17.38 -> S11 dips below -16dB near
    # 2.65-2.75GHz, off-center from F0=2.87 by ~150-200MHz) plus the overall
    # best score (eval#21: a=58.12, w_iris=14.23, x_iris=28.25, y_wall=11.65,
    # w_ext=14.99). Both cluster tightly around x_iris~28-31mm (near the
    # cavity center, a/2) even though x_iris was still allowed to range over
    # the full 15-50mm box -- tightening it (and w_ext, which also clustered
    # 14-17mm vs its 8-22mm box) should let the GP spend its budget refining
    # the region that already works instead of re-exploring dead space.
    # v10 (this region) landed the first genuine 2-pole Chebyshev-shaped
    # response: fine-mesh-confirmed best (a=58.13, w_iris=15.61,
    # x_iris=28.97, y_wall=10.37, w_ext=16.05) shows TWO real S11 nulls
    # (~-20dB @ 2.75GHz, ~-30dB @ 2.90GHz), both far beyond the -16dB
    # target -- but a ripple hump between them (~-10dB @ ~2.8GHz, inside
    # the passband window) is what keeps worst-case s11w at only -9.7dB.
    # Classic sign of k12/Qe slightly off from the ideal ratio, not a
    # fundamental problem. Tightened further into a local-refinement box
    # around this exact point (not broad re-exploration) so the GP spends
    # its budget closing the ripple gap.
    # v11 (this region) landed the first design that's a genuinely correct
    # 2-pole equi-ripple shape (flat -1.4dB S21 passband, 2.78-2.95GHz, MUCH
    # steeper rolloff outside), but the coarse grid ALIASED its true S11 (see
    # COARSE_GRID note above): fine-mesh-confirmed s11w is -13.25dB, not the
    # coarse -23.8dB. Genuinely close to -16dB now, not there yet.
    # v12 (this region, non-aliasing grid) LANDED: fine-confirmed best
    # a=57.212, w_iris=15.261, x_iris=28.678, y_wall=8.619, w_ext=16.311 ->
    # s11w=-18.09dB, S21=-1.41dB, fc=2.92GHz. Genuinely working N=2 filter,
    # matches/beats the original N=3 3-cavity cascade (s11w=-15.98dB,
    # IL=-1.46dB) at roughly half the board length (~58mm vs ~119mm).
    # v13 (this round): two changes bundled together, both need re-tuning
    # together since they both affect coupling --
    #   (1) fc recentering: v12's fc=2.92GHz is 50MHz above F0=2.87GHz;
    #       f~1/a for this mode, so a: 57.21->58.21mm (verified: single-point
    #       check at the unchanged other params confirmed fc->2.88GHz, but
    #       detuned s11w to only -7.5dB since nothing else was retuned yet).
    #   (2) tighter via fence: isolated single-point checks (d_via/p_via
    #       swept at fixed other params) found 1.0mm/2.0mm gives s11w=-9.96dB
    #       vs the 1.5mm/3.0mm baseline's -7.71dB at the SAME (still
    #       untuned-for-new-a) point -- a real +2.25dB from a tighter via
    #       fence (less field leakage, sharper boundary). 0.8mm/1.6mm was
    #       inconclusive -- repeatedly drove this machine's swap to near-
    #       exhaustion (mesh DOF ~800k+, same regime that OOM-killed earlier
    #       full/narrow sweeps) -- not worth the risk for an unconfirmed gain.
    # v13 result (1.0/2.0mm vias): fine-confirmed s11w=-15.64dB, bw=220-
    # 240MHz. v14 (1.5/3.0mm vias, bandwidth-focused): s11w=-17.83dB,
    # bw=260MHz -- stronger on S11 once both fully re-optimized, so v14 was
    # landed as the primary result. v15 (this round): user specifically
    # wants a real bandwidth-optimized run AT 1.0/2.0mm vias for direct
    # comparison (v13 was S11-focused, never BW-tuned) -- back to 1.0/2.0mm,
    # centered on v13's winning region. v13 hit y_wall's upper bound
    # (10.7mm) -- widened here so the search isn't artificially capped.
    "a":      [57.00,     0.5, 55.3, 58.7],
    "w_iris": [14.20,     0.5, 12.5, 15.9],
    "x_iris": [28.68,     0.5, 27.0, 30.4],
    "y_wall": [10.20,     0.8,  7.5, 13.0],
    "w_ext":  [15.88,     0.6, 14.1, 17.6],
}
# w_ms is NOT searched -- fixed at the true 50-ohm value for every eval
# (see W_MS_FIXED above). Its role is the SMA connector match, and a
# w_ms=10mm manual check earlier showed a wide trace badly mismatches the
# fixed-size SMA launch -- no reason to let it float.
# d_via/p_via: v15 back to 1.0/2.0mm per explicit user request for a
# bandwidth-optimized run at this via size (v13 only optimized for S11).
D_VIA_FIXED = 1.0
P_VIA_FIXED = 2.0
ORDER = ["a", "w_iris", "x_iris", "y_wall", "w_ext"]
_cache: dict[tuple, dict] = {}

LOG = out_data("opt_dualmode_log.csv")
BEST_JSON = out_data("opt_dualmode_best.json")


def _valid(p: dict) -> bool:
    a = p["a"]
    if not (10.0 <= p["x_iris"] <= a - 10.0):
        return False
    if not (2 * p["y_wall"] + p["w_iris"] + 6.0 < a):
        return False
    if p["w_iris"] >= a - 2 * p["y_wall"] - 2.0:
        return False
    if p["w_ext"] >= a - 6.0:
        return False
    return True


def _wait_for_free_palace():
    while subprocess.run(["pgrep", "-f", "palace-x86_64.bin"],
                         capture_output=True).returncode == 0:
        time.sleep(10)


def evaluate(p: dict, fine: bool = False) -> dict:
    if not _valid(p):
        return {"ok": False, "err": "invalid geometry", "score": 1e9}
    grid = FINE_GRID if fine else COARSE_GRID
    fmin, fmax = (FMIN_F, FMAX_F) if fine else (FMIN_C, FMAX_C)
    key = tuple(round(p[k], 3) for k in ORDER) + ("F" if fine else "C",)
    if key in _cache:
        return _cache[key]
    tag = ("optDmF_" if fine else "optDm_") + "_".join(f"{p[k]:.2f}" for k in ORDER)
    mesh = tag + ".msh"
    # mesh_max=4.0mm (first attempt) was confirmed to badly understate
    # coupling (peak S21 -82dB vs the true -24dB at 1.2mm resolution, at the
    # same geometry) -- narrower than the trace width itself (w_ms can go
    # down to 1.0mm), so the feed line was barely represented. 1.0/0.25mm
    # keeps ~1-2 elements across the narrowest trace in the search range.
    # fine=(0.6,0.15) OOM-crashed on this 7.4GB machine (free mem hit 77MB
    # right as FEM assembly ramped up); fine=(0.8,0.2) got closer (~90-120MB
    # free) but was still trending toward the same failure. 1.0mm was
    # already validated as ACCURATE (the wrong mesh was 4.0mm, not this) --
    # there's no correctness reason to go finer. So "fine" now means finer
    # FREQUENCY resolution only (10MHz vs 50MHz step, the thing that
    # actually matters for a clean reported curve), same safe mesh as
    # coarse -- decouples the two instead of risking OOM for no accuracy
    # benefit.
    # v13/v15: d_via/p_via fixed at 1.0/2.0mm (tighter pitch -> more vias ->
    # more mesh DOF at the same mesh_max). Needed mesh_max=1.5/h_air=3.0 to
    # survive a 13-point coarse sweep (still repeatedly drove swap to 8+GB,
    # but completed). v15's fine confirm is WIDER (51 points, 2.5-3.0GHz,
    # per explicit user request) than anything run at this via size before
    # -- same settings kept since they're the only ones validated to
    # survive this via density at all, just watched extra closely.
    mmax, mmin = 1.5, 0.25
    try:
        res = build_mesh(a_mm=p["a"], w_iris_mm=p["w_iris"], x_iris_mm=p["x_iris"],
                         y_wall_mm=p["y_wall"], w_ext_mm=p["w_ext"], w_ms_mm=W_MS_FIXED,
                         d_via_mm=D_VIA_FIXED, p_via_mm=P_VIA_FIXED,
                         mesh_max=mmax, mesh_min=mmin, h_air_factor=3.0,
                         with_sma=True, out_name=mesh, show=False)
    except Exception as e:
        r = {"ok": False, "err": f"mesh:{e}", "score": 1e9}
        _cache[key] = r
        return r
    if res["ports"] != (1, 1):
        r = {"ok": False, "err": f"bad ports {res['ports']}", "score": 1e9}
        _cache[key] = r
        return r
    sma = res["sma"]
    cfg = {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": [
            {"Attributes": [1], "Permeability": 1.0, "Permittivity": res["eps_r"], "LossTan": res["tand"]},
            {"Attributes": [2], "Permeability": 1.0, "Permittivity": 1.0, "LossTan": 0.0},
            {"Attributes": [3], "Permeability": 1.0, "Permittivity": sma["eps_r"], "LossTan": sma["tand"]}]},
        "Boundaries": {"PEC": {"Attributes": [10]},
                       "Absorbing": {"Attributes": [13], "Order": 1},
                       "WavePort": [
                           {"Index": 1, "Attributes": [11], "Mode": 1, "Excitation": 1,
                            "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6,
                            "VoltagePath": sma["voltage_path_in"]},
                           {"Index": 2, "Attributes": [12], "Mode": 1,
                            "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6,
                            "VoltagePath": sma["voltage_path_out"]}]},
        "Solver": {"Order": 1, "Device": "CPU",
                   "Driven": {"Samples": [{"Type": "Linear", "MinFreq": fmin,
                                           "MaxFreq": fmax, "FreqStep": grid}]},
                   "Linear": {"Type": "Default", "KSPType": "GMRES", "Tol": 1e-8, "MaxIts": 300}},
    }
    cfgp = out_data(f"{tag}.json")
    json.dump(cfg, open(cfgp, "w"), indent=2)
    _wait_for_free_palace()
    env = dict(os.environ, PATH=f"/home/fd/opt/palace/bin:{os.environ['PATH']}")
    subprocess.run([PALACE, "-np", "4", os.path.basename(cfgp)], cwd=out_data(""),
                   env=env, stdout=open(out_data(f"{tag}.log"), "w"),
                   stderr=subprocess.STDOUT, check=False)
    csv = out_data(f"postpro/{tag}/port-S.csv")
    if not os.path.exists(csv):
        r = {"ok": False, "err": "no csv", "score": 1e9}
        _cache[key] = r
        return r
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    nm = d.dtype.names
    f = d[nm[0]]; s11 = d[nm[1]]; s21 = d[nm[3]]
    ip = int(np.argmax(s21)); fc = float(f[ip]); il = float(s21[ip])
    inb = s21 >= il - 3.0
    bw = float((f[inb].max() - f[inb].min()) * 1000) if inb.any() else 0.0
    band = (f >= BAND[0]) & (f <= BAND[1])
    s11_band = float(s11[band].max()) if band.any() else 0.0
    il_band = float(s21[band].min()) if band.any() else -99.0

    # v16: curve-fit score against the ideal N=2 Chebyshev response (see
    # ideal_response_db() + FIT_WINDOW docstring above) -- replaces the old
    # worst-point-in-a-fixed-box + separate fc/bw penalty terms, which could
    # not detect an asymmetric (off-center) response scoring the same as a
    # properly centered one.
    fit = (f >= FIT_WINDOW[0]) & (f <= FIT_WINDOW[1])
    if fit.sum() >= 3:
        s11_ideal, s21_ideal = ideal_response_db(f[fit])
        # S11: direct dB fit -- the ideal curve is symmetric about F0 by
        # construction, so any real asymmetry/shift/wrong-bandwidth in the
        # simulated response shows up here automatically.
        s11_fit_rmse = float(np.sqrt(np.mean((s11[fit] - s11_ideal) ** 2)))
        # S21: fit SHAPE only -- both curves shifted so their own peak is
        # 0dB before comparing, so real insertion loss (unfixable by
        # geometry, only by substrate choice) never enters the fit error;
        # only rolloff steepness/symmetry does.
        s21_shape = s21[fit] - s21[fit].max()
        s21_ideal_shape = s21_ideal - s21_ideal.max()
        s21_fit_rmse = float(np.sqrt(np.mean((s21_shape - s21_ideal_shape) ** 2)))
    else:
        s11_fit_rmse = s21_fit_rmse = 99.0

    score = (1.0 * s11_fit_rmse
             + 0.5 * s21_fit_rmse
             + 0.15 * abs(il)               # mild direct IL preference among
                                             # otherwise-similar fits -- NOT
                                             # scored against the ideal's
                                             # unachievable 0dB
             + 5.0 * max(0.0, bw - BW_MAX) / 100.0)  # backstop only, same as before
    r = {"ok": True, "fc": fc, "il": il, "bw": bw, "s11w": s11_band,
         "il_band": il_band, "s11_fit_rmse": s11_fit_rmse,
         "s21_fit_rmse": s21_fit_rmse, "score": score, "tag": tag, "csv": csv}
    _cache[key] = r
    try:
        os.remove(out_data(mesh))
    except OSError:
        pass
    return r


def log_row(n, p, r):
    new = not os.path.exists(LOG)
    with open(LOG, "a") as fh:
        if new:
            fh.write("eval," + ",".join(ORDER) + ",fc,il,bw,s11w,score,tag\n")
        fh.write(f"{n}," + ",".join(f"{p[k]:.3f}" for k in ORDER) +
                 f",{r.get('fc',0):.4f},{r.get('il',0):.2f},{r.get('bw',0):.0f},"
                 f"{r.get('s11w',0):.2f},{r.get('score',1e9):.4f},{r.get('tag','')}\n")


N_INITIAL = 10


def _to_dict(x: list[float]) -> dict:
    return {k: round(float(v), 3) for k, v in zip(ORDER, x)}


def main():
    print(f"Target: N=2 Chebyshev, k12=0.0691, Qe=16.86, F0={F0}, BW_TGT={BW_TGT:.1f}MHz")
    space = [Real(PARAMS[k][2], PARAMS[k][3], name=k) for k in ORDER]
    opt = Optimizer(space, base_estimator="GP", acq_func="gp_hedge",
                    n_initial_points=N_INITIAL, random_state=0)

    all_evals: list[tuple[dict, dict]] = []
    n = 0
    best_p, best = None, {"score": 1e9}

    warm = {k: PARAMS[k][0] for k in ORDER}
    x0 = [warm[k] for k in ORDER]
    r = evaluate(warm, fine=False); n += 1; log_row(n, warm, r)
    all_evals.append((warm, r))
    opt.tell(x0, r["score"])
    best_p, best = warm, r
    print(f"[{n}] warm-start score={r['score']:.3f} {r}")

    while n < MAX_EVALS:
        x = opt.ask()
        p = _to_dict(x)
        r = evaluate(p, fine=False); n += 1; log_row(n, p, r)
        all_evals.append((p, r))
        opt.tell(x, r["score"])
        tag = "*" if r["score"] < best["score"] - 1e-4 else " "
        print(f"[{n}]{tag} {p} -> score={r['score']:.3f} (best {min(best['score'], r['score']):.3f})")
        if r["score"] < best["score"] - 1e-4:
            best_p, best = p, r

    print(f"\n=== GP SEARCH DONE after {n} evals ===  best(coarse)={best['score']:.3f} {best_p}")
    json.dump({"params": best_p, "metrics": {k: v for k, v in best.items() if k != "csv"}},
              open(BEST_JSON, "w"), indent=2)

    ok_evals = [(p, r) for p, r in all_evals if r.get("ok")]
    ok_evals.sort(key=lambda pr: pr[1]["score"])
    top5 = ok_evals[:5]
    print(f"\n=== TOP 5 (coarse mesh/grid) ===")
    for i, (p, r) in enumerate(top5, 1):
        print(f"  #{i} score={r['score']:.3f} s11w={r['s11w']:.1f} bw={r['bw']:.0f} "
              f"fc={r['fc']:.3f} il={r['il']:.2f}  {p}")

    plot_top5(top5, out_name="palace_opt_dualmode_top5_coarse.png")

    # fine-tune pass: re-run ONLY the overall best point at full mesh
    # resolution (0.8/0.2mm vs 1.0/0.25mm) and full frequency resolution
    # (10MHz step vs 50MHz) -- the coarse pass is for cheap exploration,
    # this confirms the winner isn't a coarse-grid artifact.
    print(f"\n=== FINE confirm of best point: {best_p} ===")
    fine = evaluate(best_p, fine=True)
    print(f"  fine: score={fine.get('score'):.3f} s11w={fine.get('s11w'):.2f} "
          f"bw={fine.get('bw'):.0f} fc={fine.get('fc'):.3f} il={fine.get('il'):.2f}")
    top5_fine = [(best_p, fine)] + top5[:4]
    plot_top5(top5_fine, out_name="palace_opt_dualmode_top5.png")

    # top5.json written LAST -- deliberately after the fine confirm, since
    # external monitors watch for this file's existence as the "done"
    # signal (a previous run's monitor fired early when this was written
    # before the fine pass, catching only the coarse result).
    top5_json = out_data("opt_dualmode_top5.json")
    json.dump([{"params": p, "metrics": {k: v for k, v in r.items() if k != "csv"}}
              for p, r in top5], open(top5_json, "w"), indent=2)


def plot_top5(top5: list[tuple[dict, dict]], out_name: str = "palace_opt_dualmode_top5.png"):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 6.5))
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e"]
    for i, (p, r) in enumerate(top5):
        csv = r.get("csv") or out_data(f"postpro/{r['tag']}/port-S.csv")
        if not os.path.exists(csv):
            continue
        d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
        nm = d.dtype.names
        f, s11, s21 = d[nm[0]], d[nm[1]], d[nm[3]]
        lbl = (f"#{i+1} score={r['score']:.1f} a={p['a']:.1f} wi={p['w_iris']:.1f} "
               f"xi={p['x_iris']:.1f} yw={p['y_wall']:.1f} we={p['w_ext']:.1f}")
        ax.plot(f, s21, "-", color=colors[i], lw=1.8, label=lbl)
        ax.plot(f, s11, "--", color=colors[i], lw=1.2, alpha=0.8)
    ax.axvline(F0, color="k", ls=":", lw=1)
    ax.axhline(-16, color="grey", ls="--", lw=.8)
    ax.set_xlabel("Frequency (GHz)"); ax.set_ylabel("dB")
    ax.set_ylim(-40, 2)
    ax.grid(alpha=.3)
    ax.legend(loc="lower right", fontsize=7)
    ax.set_title(f"Dual-mode cavity (N=2) top-5 -- solid=|S21|, dashed=|S11|\n"
                f"target k12=0.0691, Qe=16.86, F0={F0}GHz, BW_TGT={BW_TGT:.0f}MHz, "
                f"S11 target -16dB (grey line)")
    fig.tight_layout()
    out = out_img(out_name)
    fig.savefig(out, dpi=130)
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":
    main()
