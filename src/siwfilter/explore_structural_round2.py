"""Round 2 of structural exploration (2026-08-25), queued to run after round
1 (explore_structural.py) finishes.

Round 1's phase A screened every structural candidate at the PARENT's fixed
best coupling params (w_ext included), which found: circular_cross's match
sits at a hard ~-4dB ceiling regardless of internal perturbation strength
(nvia 0/4, ring2 0/5, all converging on -3.9 to -4.4dB no matter how much
S21 improved) -- consistent with the external aperture, not the internal
split mechanism, being the real limiter. rhombic_2diag's w_iris2 showed a
clean monotonic match-vs-IL trade-off (w_iris2=4: S11 -19.3dB but S21 -7.0dB,
just missing the -6.0dB floor; w_iris2=8/12/16 progressively worse IL) --
never re-tested with w_ext also varied, so it's possible a lower w_ext at
low w_iris2 crosses both thresholds where the fixed w_ext=19.7 didn't.

Round 2 directly tests both: vary the structural knob AND w_ext together
(small 2D grid), instead of fixing w_ext at the parent's value. Same
phase_a/phase_b machinery as round 1, just a richer per-candidate space.
"""
from __future__ import annotations

import itertools
import json
import time

from .config import out_data
from .explore_structural import (
    DEADLINE_UTC, LEADERBOARD, phase_a, phase_b, time_left,
    _load_board, _save_board,
)

# (topology_name, fixed_base_minus_w_ext, knob, knob_values, w_ext_values)
ROUND2 = [
    ("rhombic_2diag", {"a": 75.3, "w_iris": 7.0, "y_wall": 35.0},
     "w_iris2_mm", [1, 2, 3], [15.0, 19.7, 23.0]),
    ("circular_cross_ring2", {"a": 67.0, "w_iris": 16.0, "y_wall": 24.0},
     "ring2_frac", [0.4, 0.5, 0.6], [14.0, 17.0, 20.7, 24.0]),
    ("circular_cross_nvia", {"a": 67.0, "w_iris": 16.0, "y_wall": 24.0},
     "n_perturb", [2, 3], [14.0, 17.0, 20.7, 24.0]),
]


def main():
    board = _load_board()
    print(f"round 2 start, time left: {time_left()/3600:.1f}h", flush=True)

    survivors = []
    for name, base, knob, kvals, wexts in ROUND2:
        for kv, we in itertools.product(kvals, wexts):
            key = f"{name}:{knob}={kv},w_ext={we}"
            if key in board.get("phase_a", {}):
                print(f"skip (cached): {key}", flush=True)
                if board["phase_a"][key].get("pass"):
                    survivors.append((name, {**base, "w_ext": we}, knob, kv))
                continue
            if time_left() < 900:
                print("DEADLINE approaching, stopping round-2 phase A", flush=True)
                break
            s = phase_a(name, {**base, "w_ext": we}, knob, kv)
            board.setdefault("phase_a", {})[key] = s
            _save_board(board)
            if s["pass"]:
                survivors.append((name, {**base, "w_ext": we}, knob, kv))

    print(f"\nRound 2 phase A done: {len(survivors)} survivors", flush=True)
    for name, base, knob, kv in survivors:
        print(f"  {name} {knob}={kv} w_ext={base['w_ext']}", flush=True)

    n_left = len(survivors)
    for i, (name, base, knob, kv) in enumerate(survivors):
        key = f"{name}:{knob}={kv},w_ext={base['w_ext']}"
        if key in board.get("phase_b", {}):
            print(f"skip (cached): {key}", flush=True)
            continue
        remaining_h = time_left() / 3600
        if remaining_h < 0.5:
            print("DEADLINE reached, stopping round-2 phase B", flush=True)
            break
        budget = max(8, min(16, int(remaining_h * 3600 / max(1, n_left - i) / 220)))
        try:
            r = phase_b(name, base, knob, kv, budget=budget)
        except Exception as e:                                  # noqa: BLE001
            print(f"  PHASE B FAILED: {e}", flush=True)
            r = {"error": str(e)}
        board.setdefault("phase_b", {})[key] = {
            "score": r.get("metrics", {}).get("score") if isinstance(r, dict) else None,
            "params": r.get("params") if isinstance(r, dict) else None,
            "metrics_summary": {
                k: r.get("metrics", {}).get(k) for k in
                ("fc_3db", "il", "bw", "s11w")} if isinstance(r, dict) else None,
        }
        _save_board(board)

    print("\nSTRUCTURAL_ROUND2_DONE", flush=True)


if __name__ == "__main__":
    main()
