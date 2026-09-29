"""Autonomous coordinate-descent tuner for the full SIW filter in Palace.

Runs unattended in the background: evaluates (L_cav, w_iris, w_ext, L_taper,
W_ms), scores each against the target (fc=2.87 GHz, BW~145 MHz, in-band S11<-16
dB, low IL), and walks downhill until the steps shrink or the eval budget runs
out. Serializes Palace runs (only one fits in 7 GB). Everything is logged so the
chat stays free — check progress by reading output/data/opt_log.csv and the live
plot output/imgs/palace_opt_best.png.

Run (detached):  nohup uv run python palace_opt.py > output/data/opt_master.log 2>&1 &
"""
from __future__ import annotations

import json
import os
import subprocess
import time

import numpy as np

from .config import find_palace, out_data, out_img
from .palace_driven import build_mesh

F0 = 2.87
BW_TGT = 145.0           # MHz
RL_TGT = -16.0           # dB in-band return loss goal
BAND = (2.7975, 2.9425)  # FIXED target passband (2.87 +/- 72.5 MHz) for S11 metric
# COARSE = fast exploration during the descent; FINE = confirm the winner.
COARSE_GRID, FMIN_C, FMAX_C = 0.02, 2.70, 3.00   # 16 pts, ~6 min/run
FINE_GRID,   FMIN_F, FMAX_F = 0.01, 2.65, 3.05   # 41 pts, ~16 min/run
MAX_EVALS = 50

LOG = out_data("opt_log.csv")
BEST_JSON = out_data("opt_best.json")

# parameter: [init, step, min, max]   (per-cavity, symmetric: end cavs = l_end,
# middle cav = l_mid; seed shorter than the uniform best to push fc up to 2.87)
PARAMS = {
    "l_end":   [35.0, 0.6, 32.0, 38.0],
    "l_mid":   [35.5, 0.6, 32.0, 38.0],
    "w_iris":  [13.0, 0.8, 8.0, 15.0],
    "w_ext":   [19.0, 1.5, 12.0, 26.0],
    "l_taper": [15.46, 3.0, 8.0, 26.0],
    "w_ms":    [1.66, 0.3, 1.0, 2.4],
}
ORDER = ["l_end", "l_mid", "w_iris", "w_ext", "l_taper", "w_ms"]
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
    tag = ("optF_" if fine else "opt_") + "_".join(f"{p[k]:.2f}" for k in ORDER)
    mesh = tag + ".msh"
    try:
        build_mesh(mesh_max=3.5, mesh_min=0.6, h_air_factor=6.0, with_wext=True,
                   out_name=mesh, show=False,
                   l_cavs_mm=[p["l_end"], p["l_mid"], p["l_end"]],
                   w_iris_mm=p["w_iris"], w_ext_mm=p["w_ext"],
                   l_taper_mm=p["l_taper"], w_ms_mm=p["w_ms"])
    except Exception as e:
        r = {"ok": False, "err": f"mesh:{e}", "score": 1e9}
        _cache[key] = r
        return r
    cfg = {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": [
            {"Attributes": [1], "Permeability": 1.0, "Permittivity": 3.66, "LossTan": 0.0037},
            {"Attributes": [2], "Permeability": 1.0, "Permittivity": 1.0, "LossTan": 0.0}]},
        "Boundaries": {"PEC": {"Attributes": [10]},
                       "Absorbing": {"Attributes": [13], "Order": 1},
                       "WavePort": [
                           {"Index": 1, "Attributes": [11], "Mode": 1, "Excitation": 1,
                            "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6},
                           {"Index": 2, "Attributes": [12], "Mode": 1,
                            "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6}]},
        "Solver": {"Order": 1, "Device": "CPU",
                   "Driven": {"Samples": [{"Type": "Linear", "MinFreq": fmin,
                                           "MaxFreq": fmax, "FreqStep": grid}]},
                   "Linear": {"Type": "Default", "KSPType": "GMRES", "Tol": 1e-8, "MaxIts": 300}},
    }
    cfgp = out_data(f"{tag}.json")
    json.dump(cfg, open(cfgp, "w"), indent=2)
    _wait_for_free_palace()
    palace = find_palace()
    env = dict(os.environ, PATH=f"{os.path.dirname(palace)}:{os.environ['PATH']}")
    subprocess.run([palace, "-np", "4", os.path.basename(cfgp)], cwd=out_data(""),
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
    # ---- in-band match over the FIXED target band (the thing to improve) ----
    band = (f >= BAND[0]) & (f <= BAND[1])
    s11_band = float(s11[band].max()) if band.any() else 0.0   # worst (closest to 0)
    il_band = float(s21[band].min()) if band.any() else -99.0  # worst (deepest) IL in band
    # objective (lower = better): DOMINATED by in-band return loss, then IL in band,
    # then center, then BW. Forces the matched region INTO the target band.
    score = (1.0 * max(0.0, s11_band - RL_TGT)            # want S11<-16 across band
             + 0.30 * max(0.0, (-il_band) - 2.5)          # want low IL across band
             + 6.0 * abs(fc - F0)                         # center
             + 1.0 * abs(bw - BW_TGT) / BW_TGT)           # bandwidth
    s11w = s11_band
    r = {"ok": True, "fc": fc, "il": il, "bw": bw, "s11w": s11w,
         "il_band": il_band, "score": score, "tag": tag}
    _cache[key] = r
    # cleanup big mesh to save disk (keep csv)
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
    json.dump({"params": p, "metrics": r}, open(BEST_JSON, "w"), indent=2)
    # plot the best run's curve
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
    ax.set_title(f"BEST  Lend={p['l_end']:.2f} Lmid={p['l_mid']:.2f} "
                 f"wi={p['w_iris']:.2f} we={p['w_ext']:.2f} Lt={p['l_taper']:.1f}\n"
                 f"fc={r['fc']:.3f} IL={r['il']:.2f} BW={r['bw']:.0f}MHz "
                 f"S11={r['s11w']:.1f}dB score={r['score']:.3f}")
    ax.grid(alpha=.3); ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout(); fig.savefig(out_img("palace_opt_best.png"), dpi=130)
    plt.close(fig)


def main():
    p = {k: PARAMS[k][0] for k in ORDER}
    step = {k: PARAMS[k][1] for k in ORDER}
    lo = {k: PARAMS[k][2] for k in ORDER}
    hi = {k: PARAMS[k][3] for k in ORDER}
    n = 0
    best = evaluate(p, fine=False); n += 1; log_row(n, p, best); save_best(p, best)
    print(f"[{n}] init score={best['score']:.3f} {best}")

    cycles_no_improve = 0
    while n < MAX_EVALS and cycles_no_improve < 2:
        improved_cycle = False
        for k in ORDER:
            improved_k = True
            while improved_k and n < MAX_EVALS:
                improved_k = False
                for sgn in (+1, -1):
                    cand = dict(p)
                    cand[k] = round(min(hi[k], max(lo[k], p[k] + sgn * step[k])), 3)
                    if cand[k] == p[k]:
                        continue
                    r = evaluate(cand, fine=False); n += 1; log_row(n, cand, r)
                    print(f"[{n}] {k}{'+' if sgn>0 else '-'} -> {cand[k]:.2f} "
                          f"score={r['score']:.3f} (best {best['score']:.3f})")
                    if r["score"] < best["score"] - 1e-4:
                        p = cand; best = r; save_best(p, best)
                        improved_k = improved_cycle = True
                        break
                    if n >= MAX_EVALS:
                        break
        if not improved_cycle:
            for k in ORDER:
                step[k] *= 0.5
            cycles_no_improve += 1
            print(f"--- no improvement; halving steps (round {cycles_no_improve}) ---")
        else:
            cycles_no_improve = 0

    print(f"\n=== COARSE DONE after {n} evals ===  best(coarse)={best['score']:.3f} {p}")
    # ---- fine confirmation of the winner ----
    fine = evaluate(p, fine=True)
    log_row(n + 1, p, fine)
    save_best(p, fine)
    print(f"=== FINE confirm: fc={fine['fc']:.3f} s11w={fine['s11w']:.2f} "
          f"BW={fine['bw']:.0f} IL={fine['il']:.2f} score={fine['score']:.3f} ===")
    print(f"BEST params: {p}")


if __name__ == "__main__":
    main()
