"""Re-tune the filter against the REAL SMA coax launch, with W_ms fixed at the
true 50-ohm synthesis value (1.66 mm) -- not a free parameter.

Why a separate script from palace_opt.py: that optimizer scored designs
against an idealized microstrip WavePort, which self-normalizes to whatever
the local trace impedance is. Its W_ms search (1.66-2.4mm) drifted to 2.26mm
because a WIDER (wrong-impedance) trace "looked" better matched to that
self-referencing port -- confirmed by sma_compare_run.py: with a genuine
50-ohm coax launch, that 2.26mm design shows near-total reflection
(worst in-band S11 -0.2 dB vs -18.6 dB against the idealized port). See
output/data/versions/sma-v1.json.

If W_ms were left free here, the same artifact could reappear (though less
severely, since the port is now a real 50-ohm reference rather than a
self-normalizing one -- but there's no reason to re-litigate that axis).
Instead W_ms is pinned to the Hammerstad 50-ohm value and only the cavity/
iris/taper-length knobs (which don't affect absolute port impedance) are
re-searched, using the SMA-launch mesh (build_mesh(with_sma=True)) for every
Palace evaluation so the score can't be gamed by the port artifact again.

Uses Bayesian optimization (Gaussian-process surrogate, skopt) instead of
coordinate descent: each eval costs ~6-8 min of Palace time, so sample
efficiency matters far more than in a cheap-eval problem, and a GP surrogate
captures cross-parameter interactions (e.g. L_cav vs w_ext) that one-
variable-at-a-time descent ignores entirely.

Run (detached, survives the machine's periodic suspend/resume -- see
calibration-status memory):
  setsid nohup uv run python -m siwfilter.palace_opt_sma \
      > output/data/opt_sma_master.log 2>&1 < /dev/null &
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
from .palace_driven import build_mesh

PALACE = "/home/fd/opt/palace/bin/palace"
F0 = 2.87
BW_TGT = 145.0
RL_TGT = -16.0
BAND = (2.7975, 2.9425)
COARSE_GRID, FMIN_C, FMAX_C = 0.02, 2.70, 3.00
FINE_GRID,   FMIN_F, FMAX_F = 0.01, 2.65, 3.05
MAX_EVALS = 30   # ~10-15x dimensionality is the usual GP-BO rule of thumb for 5D;
                 # keeps wall-clock bounded (~30 * 7min coarse + 1 fine ~ 3.5-4h)

W_MS_FIXED = round(microstrip_width_50ohm(SPEC.substrate.eps_r, SPEC.substrate.h) * 1e3, 4)

LOG = out_data("opt_sma_log.csv")
BEST_JSON = out_data("opt_sma_best.json")

# W_ms is NOT here -- fixed at W_MS_FIXED for every eval. Warm-started from
# the (mismatch-blind) previous optimum since those other knobs are still a
# reasonable starting point, just no longer assumed correct.
PARAMS = {
    "l_end":   [34.4, 0.6, 30.0, 38.0],
    "l_mid":   [34.3, 0.6, 30.0, 38.0],
    "w_iris":  [13.0, 0.8, 8.0, 15.0],
    "w_ext":   [16.0, 1.5, 10.0, 26.0],
    "l_taper": [15.46, 3.0, 8.0, 26.0],
}
ORDER = ["l_end", "l_mid", "w_iris", "w_ext", "l_taper"]
_cache: dict[tuple, dict] = {}


def _wait_for_free_palace():
    while subprocess.run(["pgrep", "-f", "palace-x86_64.bin"],
                         capture_output=True).returncode == 0:
        time.sleep(10)


def evaluate(p: dict, fine: bool = False) -> dict:
    grid = FINE_GRID if fine else COARSE_GRID
    fmin, fmax = (FMIN_F, FMAX_F) if fine else (FMIN_C, FMAX_C)
    key = tuple(round(p[k], 3) for k in ORDER) + ("F" if fine else "C",)
    if key in _cache:
        return _cache[key]
    tag = ("optSmaF_" if fine else "optSma_") + "_".join(f"{p[k]:.2f}" for k in ORDER)
    mesh = tag + ".msh"
    try:
        res = build_mesh(mesh_max=3.5, mesh_min=0.6, h_air_factor=6.0, with_wext=True,
                         out_name=mesh, show=False, with_sma=True,
                         l_cavs_mm=[p["l_end"], p["l_mid"], p["l_end"]],
                         w_iris_mm=p["w_iris"], w_ext_mm=p["w_ext"],
                         l_taper_mm=p["l_taper"], w_ms_mm=W_MS_FIXED)
    except Exception as e:
        r = {"ok": False, "err": f"mesh:{e}", "score": 1e9}
        _cache[key] = r
        return r
    sma = res["sma"]
    cfg = {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": [
            {"Attributes": [1], "Permeability": 1.0, "Permittivity": 3.66, "LossTan": 0.0037},
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
    f = d[d.dtype.names[0]]; s11 = d[d.dtype.names[1]]; s21 = d[d.dtype.names[3]]
    ip = int(np.argmax(s21)); fc = float(f[ip]); il = float(s21[ip])
    inb = s21 >= il - 3.0
    bw = float((f[inb].max() - f[inb].min()) * 1000) if inb.any() else 0.0
    band = (f >= BAND[0]) & (f <= BAND[1])
    s11_band = float(s11[band].max()) if band.any() else 0.0
    il_band = float(s21[band].min()) if band.any() else -99.0
    score = (1.0 * max(0.0, s11_band - RL_TGT)
             + 0.30 * max(0.0, (-il_band) - 2.5)
             + 6.0 * abs(fc - F0)
             + 1.0 * abs(bw - BW_TGT) / BW_TGT)
    s11w = s11_band
    r = {"ok": True, "fc": fc, "il": il, "bw": bw, "s11w": s11w,
         "il_band": il_band, "score": score, "tag": tag}
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
            fh.write("eval," + ",".join(ORDER) + ",fc,il,bw,s11w,score\n")
        fh.write(f"{n}," + ",".join(f"{p[k]:.3f}" for k in ORDER) +
                 f",{r.get('fc',0):.4f},{r.get('il',0):.2f},{r.get('bw',0):.0f},"
                 f"{r.get('s11w',0):.2f},{r.get('score',1e9):.4f}\n")


def save_best(p, r):
    json.dump({"params": dict(p, w_ms=W_MS_FIXED), "metrics": r}, open(BEST_JSON, "w"), indent=2)
    csv = out_data(f"postpro/{r['tag']}/port-S.csv")
    if not os.path.exists(csv):
        return
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    f = d[d.dtype.names[0]]; s11 = d[d.dtype.names[1]]; s21 = d[d.dtype.names[3]]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(f, s21, "-o", color="#d62728", ms=3, label="|S21|")
    ax.plot(f, s11, "-o", color="#1f77b4", ms=3, label="|S11|")
    ax.axvline(F0, color="k", ls=":", lw=1); ax.axhline(-16, color="grey", ls="--", lw=.8)
    ax.set_xlim(f.min(), f.max()); ax.set_ylim(-40, 2)
    ax.set_xlabel("Frequency (GHz)"); ax.set_ylabel("dB")
    ax.set_title(f"BEST (SMA launch, W_ms={W_MS_FIXED}mm fixed)  Lend={p['l_end']:.2f} "
                 f"Lmid={p['l_mid']:.2f} wi={p['w_iris']:.2f} we={p['w_ext']:.2f} Lt={p['l_taper']:.1f}\n"
                 f"fc={r['fc']:.3f} IL={r['il']:.2f} BW={r['bw']:.0f}MHz "
                 f"S11={r['s11w']:.1f}dB score={r['score']:.3f}")
    ax.grid(alpha=.3); ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout(); fig.savefig(out_img("palace_opt_sma_best.png"), dpi=130)
    plt.close(fig)


N_INITIAL = 10   # random exploration budget before the GP starts guiding search


def _to_dict(x: list[float]) -> dict:
    return {k: round(float(v), 3) for k, v in zip(ORDER, x)}


def main():
    print(f"W_ms fixed at true 50-ohm value: {W_MS_FIXED} mm")
    space = [Real(PARAMS[k][2], PARAMS[k][3], name=k) for k in ORDER]
    opt = Optimizer(space, base_estimator="GP", acq_func="gp_hedge",
                    n_initial_points=N_INITIAL, random_state=0)

    n = 0
    best_p, best = None, {"score": 1e9}

    # warm-start with the previous (mismatch-blind) optimum -- still a
    # reasonable starting guess, just no longer assumed correct -- so the GP
    # has one informative point before its random exploration begins.
    warm = {k: PARAMS[k][0] for k in ORDER}
    x0 = [warm[k] for k in ORDER]
    r = evaluate(warm, fine=False); n += 1; log_row(n, warm, r)
    opt.tell(x0, r["score"])
    best_p, best = warm, r
    save_best(best_p, best)
    print(f"[{n}] warm-start score={r['score']:.3f} {r}")

    while n < MAX_EVALS:
        x = opt.ask()
        p = _to_dict(x)
        r = evaluate(p, fine=False); n += 1; log_row(n, p, r)
        opt.tell(x, r["score"])
        tag = "*" if r["score"] < best["score"] - 1e-4 else " "
        print(f"[{n}]{tag} {p} -> score={r['score']:.3f} (best {min(best['score'], r['score']):.3f})")
        if r["score"] < best["score"] - 1e-4:
            best_p, best = p, r
            save_best(best_p, best)

    print(f"\n=== GP SEARCH DONE after {n} evals ===  best(coarse)={best['score']:.3f} {best_p}")
    fine = evaluate(best_p, fine=True)
    log_row(n + 1, best_p, fine)
    save_best(best_p, fine)
    print(f"=== FINE confirm: fc={fine['fc']:.3f} s11w={fine['s11w']:.2f} "
          f"BW={fine['bw']:.0f} IL={fine['il']:.2f} score={fine['score']:.3f} ===")
    print(f"BEST params: {best_p}  (W_ms fixed {W_MS_FIXED})")
    print(f"BEST params: {p}  (W_ms fixed {W_MS_FIXED})")


if __name__ == "__main__":
    main()
