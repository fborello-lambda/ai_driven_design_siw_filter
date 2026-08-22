"""y_wall sensitivity sweep at fixed w_iris (near the k=0.069 target found
by dualmode_calibrate_v2.py's w_iris sweep at y_wall=6mm) -- k depends on
BOTH w_iris and y_wall, not just w_iris in isolation, so this checks whether
a different y_wall gives a better combination (e.g. same k with a smaller
w_iris, or less fc droop) before committing to a single calibrated point."""
from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data  # noqa: E402
from siwfilter.palace_dualmode import A_SIW_MM  # noqa: E402
from dualmode_calibrate_v2 import run_one, K_TARGET, F0  # noqa: E402


def main():
    x_iris = A_SIW_MM / 2.0
    w_iris = 16.0   # near the k=0.069 crossing found at y_wall=6mm
    y_walls = [3.0, 6.0, 9.0, 12.0]
    results = {}
    for yw in y_walls:
        r = run_one(w_iris, x_iris_mm=x_iris, y_wall_mm=yw)
        results[yw] = r
        json.dump({str(k): v for k, v in results.items()}, open(out_data("dualmode_cal_ywall.json"), "w"),
                  indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"\n=== summary (w_iris={w_iris}, x_iris={x_iris:.2f}) ===")
    for yw, r in results.items():
        if r.get("ok"):
            print(f"  y_wall={yw:.1f}mm -> k={r['k']:.5f} fc={r['fc']:.4f}GHz "
                 f"(target k={K_TARGET}, target fc={F0})")
        else:
            print(f"  y_wall={yw:.1f}mm -> FAILED")


if __name__ == "__main__":
    main()
