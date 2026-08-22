"""Sweep corner-cut size on the isolated dual-mode cavity, extract the split
eigenmode pair, compute k=(f2^2-f1^2)/(f2^2+f1^2) -- same method already
validated for iris-width<->k in calibrate.py/palace_geometry.py."""
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


def run_one(dp_mm: float | None, mesh_max: float = 1.5, mesh_min: float = 0.4,
           n_modes: int = 6, window: float = 0.5) -> dict:
    # NOTE: mesh_max=3.5 vs 1.5 gave near-IDENTICAL results (k~0.17-0.19 both
    # ways) -- mesh resolution was a red herring, not the actual issue. The
    # real difference from the original single-point k=0.091 was a NARROWER
    # eigenmode search window (+/-0.3GHz) that never looked below 2.57GHz,
    # so a real lower mode was simply never returned. dp_mm=None builds the
    # bare/unperturbed cavity (no internal vias at all) to check whether a
    # genuine degeneracy exists before trusting any k(dp) sweep.
    tag = f"dualmode_cut{dp_mm:.2f}" if dp_mm is not None else "dualmode_bare"
    mesh = tag + ".msh"
    build_mesh(dp_mm=dp_mm, mesh_max=mesh_max, mesh_min=mesh_min,
              out_name=mesh, show_stats=True)
    cfg = {
        "Problem": {"Type": "Eigenmode", "Verbose": 2, "Output": f"postpro/{tag}"},
        "Model": {"Mesh": mesh, "L0": 1.0e-3},
        "Domains": {"Materials": [
            {"Attributes": [1], "Permeability": 1.0, "Permittivity": 3.66, "LossTan": 0.0037}]},
        "Boundaries": {"PEC": {"Attributes": [2]}},
        "Solver": {"Eigenmode": {"N": n_modes, "Save": n_modes, "Target": F0 - window,
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
    freqs = np.atleast_1d(d[d.dtype.names[1]])   # "Re{f} (GHz)", not "m" (mode index)
    freqs = np.sort(freqs)
    print(f"[{tag}] FULL mode list in window: {freqs}")
    if len(freqs) < 2:
        return {"ok": False, "freqs": freqs}
    # the true split pair is the two ADJACENT modes with the SMALLEST gap
    # (not just the two lowest frequencies -- confirmed necessary: an
    # unrelated mode can sort lower than the actual partner and silently
    # produce a wrong, physically-nonsensical k if you just take freqs[0:2]).
    gaps = np.diff(freqs)
    i = int(np.argmin(gaps))
    f1, f2 = freqs[i], freqs[i + 1]
    k = abs(f2**2 - f1**2) / (f2**2 + f1**2)
    print(f"[{tag}] f1={f1:.4f} f2={f2:.4f} GHz (closest-gap pair, idx {i}) -> k={k:.5f}")
    return {"ok": True, "f1": f1, "f2": f2, "k": k}


def main():
    # dp=8mm -> k=0.091 (verified); target k=0.046. Bracket downward since
    # k should shrink as the perturbation via moves toward the center.
    dps = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    results = {}
    for c in dps:
        r = run_one(c)
        results[c] = r
        json.dump({str(k): v for k, v in results.items()}, open(out_data("dualmode_cal.json"), "w"), indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("\n=== summary ===")
    for c, r in results.items():
        if r.get("ok"):
            print(f"  dp={c:.1f}mm -> k={r['k']:.5f}  (f1={r['f1']:.4f} f2={r['f2']:.4f})")
        else:
            print(f"  dp={c:.1f}mm -> FAILED")


if __name__ == "__main__":
    main()
