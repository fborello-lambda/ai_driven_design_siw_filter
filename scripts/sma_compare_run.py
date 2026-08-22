"""One-off: run the full-filter Palace driven solve WITH and WITHOUT the SMA
coax launch (same mesh/solver settings otherwise) and save both S-parameter
sets, so the effect of a real 50-ohm coax launch on S11/S21 can be measured
directly instead of inferred. Matches palace_opt.py's validated FINE_GRID
(41 pts, 2.65-3.05 GHz, ~16 min/run) and mesh settings (mesh_max=3.5,
mesh_min=0.6, h_air_factor=6.0) so results are comparable to the existing
"final" design run. Palace only fits one job at a time in the 7 GB machine,
so the two runs go strictly sequentially.

Run:  uv run python scripts/sma_compare_run.py
Writes output/data/sma_compare.npz with freq/s11/s21 for both cases.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data          # noqa: E402
from siwfilter.palace_driven import build_mesh  # noqa: E402

PALACE = "/home/fd/opt/palace/bin/palace"
FMIN, FMAX, FSTEP = 2.65, 3.05, 0.01   # matches palace_opt FINE_GRID


def _wait_for_free_palace():
    while subprocess.run(["pgrep", "-f", "palace-x86_64.bin"],
                         capture_output=True).returncode == 0:
        time.sleep(10)


def run_one(with_sma: bool) -> dict:
    tag = "sma_cmp_with" if with_sma else "sma_cmp_without"
    print(f"\n{'=' * 60}\n[{tag}] meshing (with_sma={with_sma})\n{'=' * 60}", flush=True)
    res = build_mesh(mesh_max=3.5, mesh_min=0.6, h_air_factor=6.0,
                     with_wext=True, out_name=f"{tag}.msh", show=True,
                     with_sma=with_sma)
    print(f"[{tag}] tets={res['tets']:,} nodes={res['nodes']:,} "
          f"ports={res['ports']}", flush=True)

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
        "Model": {"Mesh": f"{tag}.msh", "L0": 1.0e-3},
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
        print(f"[{tag}] FAILED - no {csv}; tail of log:")
        print("\n".join(open(logp).read().splitlines()[-30:]))
        return {"ok": False, "tag": tag}

    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    nm = d.dtype.names
    f = d[nm[0]]
    o = np.argsort(f)
    f = f[o]
    s11 = 10 ** (d[nm[1]][o] / 20) * np.exp(1j * np.deg2rad(d[nm[2]][o]))
    s21 = 10 ** (d[nm[3]][o] / 20) * np.exp(1j * np.deg2rad(d[nm[4]][o]))
    return {"ok": True, "tag": tag, "f": f, "s11": s11, "s21": s21}


def main():
    r_without = run_one(with_sma=False)
    r_with = run_one(with_sma=True)

    out = {}
    for r in (r_without, r_with):
        if r["ok"]:
            key = r["tag"]
            out[f"{key}_f"] = r["f"]
            out[f"{key}_s11"] = r["s11"]
            out[f"{key}_s21"] = r["s21"]
    npz = out_data("sma_compare.npz")
    np.savez(npz, **out)
    print(f"\nSaved {npz} -> keys: {list(out.keys())}")
    print("without ok:", r_without["ok"], " with ok:", r_with["ok"])


if __name__ == "__main__":
    main()
