"""Eigenmode k12 calibration for the CURRENT dual-mode shape (floating
internal iris row, held off the side walls by y_wall, centered gap w_iris --
see palace_dualmode.py). Sweeps w_iris_mm (primary coupling knob) at a fixed
x_iris/y_wall to find the value that gives k12=0.0691 (N=2, 0.1dB-ripple
Chebyshev target -- see palace_opt_dualmode.py docstring for the g-value
derivation). Much cheaper per-eval than the driven 2-port+SMA search (no
ports, no air/SMA region, closed-cavity eigenmode solve only) -- this is the
calibration step the driven optimizer should have started from instead of
blind-searching the full 5D driven response.

Run: uv run python scripts/dualmode_calibrate_v2.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data  # noqa: E402
from siwfilter.palace_dualmode import build_mesh, A_SIW_MM  # noqa: E402

PALACE = "/home/fd/opt/palace/bin/palace"
F0 = 2.87
K_TARGET = 0.0691   # N=2, 0.1dB ripple Chebyshev (see palace_opt_dualmode.py)


def run_one(w_iris_mm: float | None, x_iris_mm: float | None = None,
           y_wall_mm: float = 6.0, a_mm: float = A_SIW_MM,
           mesh_max: float = 1.5, mesh_min: float = 0.4,
           n_modes: int = 6, window: float = 0.5) -> dict:
    x_iris = x_iris_mm if x_iris_mm is not None else a_mm / 2.0
    tag = (f"dualmodeV2_wi{w_iris_mm:.2f}_xi{x_iris:.1f}_yw{y_wall_mm:.1f}"
          if w_iris_mm is not None else "dualmodeV2_bare")
    mesh = tag + ".msh"
    build_mesh(a_mm=a_mm, w_iris_mm=w_iris_mm, x_iris_mm=x_iris_mm, y_wall_mm=y_wall_mm,
              mesh_max=mesh_max, mesh_min=mesh_min, out_name=mesh, show_stats=True)
    cfg = {
        "Problem": {"Type": "Eigenmode", "Verbose": 2, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": [
            {"Attributes": [1], "Permeability": 1.0, "Permittivity": 3.66, "LossTan": 0.0037}]},
        "Boundaries": {"PEC": {"Attributes": [2]}},
        # Save=0 -- we only ever read eig.csv (frequencies), never the field
        # solution. Save=n_modes (the previous setting) writes a full
        # ParaView field dump per mode (~500-700MB per run) that filled the
        # disk to 100% during this session; skip it entirely.
        "Solver": {"Eigenmode": {"N": n_modes, "Save": 0, "Target": F0 - window,
                                 "TargetUpper": F0 + window, "Tol": 1e-8,
                                 "Type": "SLEPc"}},
    }
    cfgp = out_data(f"{tag}.json")
    json.dump(cfg, open(cfgp, "w"), indent=2)
    env = dict(os.environ, PATH=f"/home/fd/opt/palace/bin:{os.environ['PATH']}")
    logp = out_data(f"{tag}.log")
    subprocess.run([PALACE, "-np", "4", os.path.basename(cfgp)], cwd=out_data(""),
                   env=env, stdout=open(logp, "w"), stderr=subprocess.STDOUT, check=False)
    csv = out_data(f"postpro/{tag}/eig.csv")
    if not os.path.exists(csv):
        print(f"[{tag}] FAILED, tail of log:")
        print("\n".join(open(logp).read().splitlines()[-25:]))
        return {"ok": False}
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    freqs = np.sort(np.atleast_1d(d[d.dtype.names[1]]))
    print(f"[{tag}] FULL mode list in window: {freqs}")
    if len(freqs) < 2:
        return {"ok": False, "freqs": freqs.tolist()}
    gaps = np.diff(freqs)
    i = int(np.argmin(gaps))
    f1, f2 = freqs[i], freqs[i + 1]
    k = abs(f2**2 - f1**2) / (f2**2 + f1**2)
    fc = (f1 + f2) / 2.0
    print(f"[{tag}] f1={f1:.4f} f2={f2:.4f} GHz (closest-gap pair) -> k={k:.5f}, fc={fc:.4f}")
    return {"ok": True, "f1": float(f1), "f2": float(f2), "k": float(k), "fc": float(fc)}


def main():
    x_iris = A_SIW_MM / 2.0
    y_wall = 6.0
    # bracket the current driven-search range (5-14mm) plus a bit wider,
    # since we don't yet know where k=0.0691 actually lands for this shape
    w_irises = [5.0, 7.0, 9.0, 11.0, 13.0, 16.0]
    results = {}
    for w in w_irises:
        r = run_one(w, x_iris_mm=x_iris, y_wall_mm=y_wall)
        results[w] = r
        json.dump({str(k): v for k, v in results.items()}, open(out_data("dualmode_cal_v2.json"), "w"),
                  indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("\n=== summary (x_iris=%.2f, y_wall=%.2f) ===" % (x_iris, y_wall))
    for w, r in results.items():
        if r.get("ok"):
            print(f"  w_iris={w:.1f}mm -> k={r['k']:.5f} fc={r['fc']:.4f}GHz "
                 f"(target k={K_TARGET}, target fc={F0})")
        else:
            print(f"  w_iris={w:.1f}mm -> FAILED")


if __name__ == "__main__":
    main()
