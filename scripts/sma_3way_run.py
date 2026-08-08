"""Run the two remaining sims for the 3-way comparison:
  1. OLD (mismatch-blind) optimum, simulated WITH the now-fixed SMA connector.
  2. NEW re-tuned optimum, simulated WITHOUT the connector (idealized port).
(#3, NEW optimum WITH connector, already exists: postpro/optSmaF_.../port-S.csv)
Matches palace_opt_sma.py's FINE_GRID settings for a fair comparison.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data  # noqa: E402
from siwfilter.palace_driven import build_mesh  # noqa: E402

PALACE = "/home/fd/opt/palace/bin/palace"
FMIN, FMAX, FSTEP = 2.65, 3.05, 0.01

# old (mismatch-blind) optimum, from config.py OPTIMIZED_DESIGN
OLD = dict(l_cav_mm=34.4, w_iris_mm=13.0, w_ext_mm=16.0, w_ms_mm=2.26, l_taper_mm=15.46)
# new re-tuned optimum, from palace_opt_sma.py's FINE confirm
NEW = dict(l_cavs_mm=[32.807, 33.859, 32.807], w_iris_mm=12.995, w_ext_mm=16.533,
           l_taper_mm=15.725, w_ms_mm=1.6636)


def _wait_for_free_palace():
    while subprocess.run(["pgrep", "-f", "palace-x86_64.bin"],
                         capture_output=True).returncode == 0:
        time.sleep(10)


def run_one(tag: str, mesh_kwargs: dict, with_sma: bool) -> dict:
    mesh = tag + ".msh"
    res = build_mesh(mesh_max=3.5, mesh_min=0.6, h_air_factor=6.0, with_wext=True,
                     out_name=mesh, show=True, with_sma=with_sma, **mesh_kwargs)
    print(f"[{tag}] tets={res['tets']:,} ports={res['ports']}", flush=True)

    materials = [
        {"Attributes": [1], "Permeability": 1.0, "Permittivity": 3.66, "LossTan": 0.0037},
        {"Attributes": [2], "Permeability": 1.0, "Permittivity": 1.0, "LossTan": 0.0},
    ]
    wp = [
        {"Index": 1, "Attributes": [11], "Mode": 1, "Excitation": 1,
         "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6},
        {"Index": 2, "Attributes": [12], "Mode": 1,
         "Offset": 0.0, "MaxIts": 40, "KSPTol": 1e-8, "EigenTol": 1e-6},
    ]
    if with_sma:
        sma = res["sma"]
        materials.append({"Attributes": [3], "Permeability": 1.0,
                          "Permittivity": sma["eps_r"], "LossTan": sma["tand"]})
        wp[0]["VoltagePath"] = sma["voltage_path_in"]
        wp[1]["VoltagePath"] = sma["voltage_path_out"]

    cfg = {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": materials},
        "Boundaries": {"PEC": {"Attributes": [10]},
                       "Absorbing": {"Attributes": [13], "Order": 1},
                       "WavePort": wp},
        "Solver": {"Order": 1, "Device": "CPU",
                   "Driven": {"Samples": [{"Type": "Linear", "MinFreq": FMIN,
                                           "MaxFreq": FMAX, "FreqStep": FSTEP}]},
                   "Linear": {"Type": "Default", "KSPType": "GMRES",
                              "Tol": 1e-8, "MaxIts": 300}},
    }
    cfgp = out_data(f"{tag}.json")
    json.dump(cfg, open(cfgp, "w"), indent=2)

    _wait_for_free_palace()
    t0 = time.time()
    env = dict(os.environ, PATH=f"/home/fd/opt/palace/bin:{os.environ['PATH']}")
    logp = out_data(f"{tag}.log")
    print(f"[{tag}] running Palace (log: {logp}) ...", flush=True)
    subprocess.run([PALACE, "-np", "4", os.path.basename(cfgp)], cwd=out_data(""),
                   env=env, stdout=open(logp, "w"), stderr=subprocess.STDOUT,
                   check=False)
    print(f"[{tag}] done in {time.time() - t0:.0f}s", flush=True)

    csv = out_data(f"postpro/{tag}/port-S.csv")
    if not os.path.exists(csv):
        print(f"[{tag}] FAILED - no {csv}")
        return {"ok": False, "tag": tag}
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    nm = d.dtype.names
    f = d[nm[0]]; o = np.argsort(f); f = f[o]
    s11 = 10 ** (d[nm[1]][o] / 20) * np.exp(1j * np.deg2rad(d[nm[2]][o]))
    s21 = 10 ** (d[nm[3]][o] / 20) * np.exp(1j * np.deg2rad(d[nm[4]][o]))
    return {"ok": True, "tag": tag, "f": f, "s11": s11, "s21": s21}


def main():
    r_old_sma = run_one("sma3w_old_with_sma", OLD, with_sma=True)
    r_new_nosma = run_one("sma3w_new_no_sma", NEW, with_sma=False)

    out = {}
    for key, r in (("old_with_sma", r_old_sma), ("new_no_sma", r_new_nosma)):
        if r["ok"]:
            out[f"{key}_f"] = r["f"]
            out[f"{key}_s11"] = r["s11"]
            out[f"{key}_s21"] = r["s21"]
    npz = out_data("sma_3way.npz")
    np.savez(npz, **out)
    print(f"\nSaved {npz} -> keys: {list(out.keys())}")
    print("old_with_sma ok:", r_old_sma["ok"], " new_no_sma ok:", r_new_nosma["ok"])


if __name__ == "__main__":
    main()
