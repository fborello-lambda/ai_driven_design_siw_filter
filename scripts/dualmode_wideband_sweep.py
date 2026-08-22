"""Full 0.1-7.0GHz S-parameter sweep of a single dual-mode design, driven+SMA
model, same mesh settings as palace_opt_dualmode.evaluate() (mesh_max=1.5,
mesh_min=0.25, h_air_factor=3.0, d_via/p_via=1.0/2.0mm). Overview sweep, not
a passband-detail sweep -- 0.1GHz step (70 points) trades resolution for a
run that finishes in a few hours on this machine rather than being infeasible
at fine step across a 6.9GHz span.

Run (detached):
  setsid nohup uv run python scripts/dualmode_wideband_sweep.py \
      > output/data/wideband_sweep_master.log 2>&1 < /dev/null &
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data  # noqa: E402
from siwfilter.palace_dualmode_driven import build_mesh  # noqa: E402
from siwfilter.palace_opt_dualmode import W_MS_FIXED  # noqa: E402

PALACE = "/home/fd/opt/palace/bin/palace"

# v16 winner (eval #14, score=4.44, fc=2.91GHz, s11w=-16.26dB coarse /
# -13.40dB true fine-mesh worst-in-band -- see opt_dualmode_best.json)
PARAMS = dict(a=57.047, w_iris=13.654, x_iris=28.639, y_wall=10.234, w_ext=15.417)
D_VIA, P_VIA = 1.0, 2.0

TAG = "wideband_" + "_".join(f"{v:.2f}" for v in PARAMS.values())
FMIN, FMAX, FSTEP = 0.1, 7.0, 0.1


def main():
    mesh = TAG + ".msh"
    res = build_mesh(a_mm=PARAMS["a"], w_iris_mm=PARAMS["w_iris"], x_iris_mm=PARAMS["x_iris"],
                     y_wall_mm=PARAMS["y_wall"], w_ext_mm=PARAMS["w_ext"], w_ms_mm=W_MS_FIXED,
                     d_via_mm=D_VIA, p_via_mm=P_VIA,
                     mesh_max=1.5, mesh_min=0.25, h_air_factor=3.0,
                     with_sma=True, out_name=mesh, show=False)
    print(f"mesh: {res['tets']:,} tets, {res['nodes']:,} nodes, ports={res['ports']}", flush=True)
    if res["ports"] != (1, 1):
        print("BAD PORTS, aborting")
        return
    sma = res["sma"]
    cfg = {
        "Problem": {"Type": "Driven", "Verbose": 1, "Output": f"postpro/{TAG}"},
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
                   "Driven": {"Samples": [{"Type": "Linear", "MinFreq": FMIN, "MaxFreq": FMAX, "FreqStep": FSTEP}]},
                   "Linear": {"Type": "Default", "KSPType": "GMRES", "Tol": 1e-8, "MaxIts": 300}},
    }
    cfgp = out_data(f"{TAG}.json")
    json.dump(cfg, open(cfgp, "w"), indent=2)
    env = dict(os.environ, PATH=f"/home/fd/opt/palace/bin:{os.environ['PATH']}")
    logp = out_data(f"{TAG}.log")
    print(f"launching palace, log at {logp}", flush=True)
    subprocess.run([PALACE, "-np", "4", os.path.basename(cfgp)], cwd=out_data(""),
                   env=env, stdout=open(logp, "w"), stderr=subprocess.STDOUT, check=False)
    csv = out_data(f"postpro/{TAG}/port-S.csv")
    if not os.path.exists(csv):
        print("FAILED, no csv produced")
        return
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    print(f"DONE: {len(np.atleast_1d(d))} points written to {csv}")
    try:
        os.remove(out_data(mesh))
    except OSError:
        pass


if __name__ == "__main__":
    main()
