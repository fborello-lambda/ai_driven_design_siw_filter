"""Two-phase autonomous exploration of the 4 new structural via-layout
variants (2026-08-25), per user request: try several new structural
parameters, reject non-starters fast by checking S11/S21 near f0, refine
survivors, keep going until a deadline.

PHASE A (triage): for each candidate (structural_name, structural_value),
run screen_at_f0 at the PARENT geometry's already-known best coupling
params -- cheap (~2min on the validated screen mesh), no full coarse eval.
This answers "does this structural change even resonate somewhere useful"
before spending real budget on it.

PHASE B (refine): screen survivors get a REAL Bayesian coupling search
(optimize(), same machinery as every other geometry this session) with the
structural knob held fixed at its winning value -- this is what actually
finds a competitive design at that structural setting, not just confirms it
resonates.

Runs until DEADLINE_UTC, checkpointing a leaderboard to disk after every
phase-B result so a kill/restart loses nothing. Every candidate geometry
still ends in _dedupe() with a uniform via diameter, so DRC (JLCPCB
hole-to-hole) is enforced by construction -- see geometries.py.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .config import FilterSpec, out_data
from .optimize import screen_at_f0, optimize
from .topologies.geometry import GeometryTopology, _SPACES

DEADLINE_UTC = datetime(2026, 8, 25, 21, 0, tzinfo=timezone.utc)
LEADERBOARD = out_data("structural_leaderboard.json")

# (topology_name, parent_best_coupling_params, structural_kwarg, [values to try])
CANDIDATES = [
    ("circular_cross_nvia",
     {"a": 67.0, "w_iris": 16.0, "y_wall": 24.0, "w_ext": 20.7},
     "n_perturb", [2, 3, 4, 6]),
    ("circular_cross_ring2",
     {"a": 67.0, "w_iris": 16.0, "y_wall": 24.0, "w_ext": 20.7},
     "ring2_frac", [0.3, 0.4, 0.5, 0.6, 0.7]),
    ("corner_cut_2corner",
     {"a": 59.4, "w_iris": 3.0, "w_ext": 17.0},
     "n_corners", [2]),
    ("rhombic_2diag",
     {"a": 75.3, "w_iris": 7.0, "y_wall": 35.0, "w_ext": 19.7},
     "w_iris2_mm", [4, 8, 12, 16]),
]


def _load_board() -> dict:
    if not __import__("os").path.exists(LEADERBOARD):
        return {}
    return json.load(open(LEADERBOARD))


def _save_board(board: dict) -> None:
    json.dump(board, open(LEADERBOARD, "w"), indent=2)


def time_left() -> float:
    return (DEADLINE_UTC - datetime.now(timezone.utc)).total_seconds()


def phase_a(name: str, base_params: dict, knob: str, value) -> dict:
    topo = GeometryTopology(name)
    spec = FilterSpec(N=2)
    params = {**base_params, knob: value}
    tag = f"struct_{name}_{knob}{value}"
    print(f"\n=== PHASE A: {name} {knob}={value} ===", flush=True)
    t = time.time()
    s = screen_at_f0(topo, spec, params, tag, device="auto", np_ranks=1)
    dt = time.time() - t
    s["dt"] = dt
    print(f"  {dt:.0f}s  pass={s['pass']}  s11={s.get('s11_best')}  "
         f"s21={s.get('s21_best')}", flush=True)
    return s


def phase_b(name: str, base_params: dict, knob: str, value, budget: int = 14) -> dict:
    """Real Bayesian coupling search with the structural knob fixed."""
    topo = GeometryTopology(name)
    spec = FilterSpec(N=2)
    tag = f"struct_{name}_{knob}{value}"
    print(f"\n=== PHASE B: {name} {knob}={value} ({budget} evals) ===", flush=True)

    class _FixedKnobTopology:
        """Wraps GeometryTopology so optimize()'s skopt search never sees the
        structural knob -- it stays fixed at `value` on every eval, only the
        coupling knobs (a/w_iris/w_ext/y_wall) get searched."""
        name = topo.name
        poles_per_cavity = topo.poles_per_cavity

        def param_space(self, spec):
            return topo.param_space(spec)

        def build_mesh(self, spec, out_name, **params):
            return topo.build_mesh(spec, out_name, **{**params, knob: value})

        def plot_layout_2d(self, spec, path, **params):
            return topo.plot_layout_2d(spec, path, **{**params, knob: value})

        def board_length_mm(self, spec, **params):
            return topo.board_length_mm(spec, **{**params, knob: value})

        def board_area_mm2(self, spec, **params):
            return topo.board_area_mm2(spec, **{**params, knob: value})

        def calibrate(self, spec):
            return None

    result = optimize(_FixedKnobTopology(), spec, budget=budget,
                      log_name=f"opt_{tag}_log.csv",
                      best_json_name=f"opt_{tag}_best.json")
    return result


def main():
    board = _load_board()
    print(f"time left: {time_left()/3600:.1f}h", flush=True)

    # ---- PHASE A: triage every candidate value ----
    survivors = []
    for name, base, knob, values in CANDIDATES:
        for v in values:
            key = f"{name}:{knob}={v}"
            if key in board.get("phase_a", {}):
                print(f"skip (cached): {key}", flush=True)
                if board["phase_a"][key].get("pass"):
                    survivors.append((name, base, knob, v))
                continue
            if time_left() < 900:
                print("DEADLINE approaching, stopping phase A early", flush=True)
                break
            s = phase_a(name, base, knob, v)
            board.setdefault("phase_a", {})[key] = s
            _save_board(board)
            if s["pass"]:
                survivors.append((name, base, knob, v))

    print(f"\nPhase A done: {len(survivors)} survivors out of "
         f"{sum(len(v) for _,_,_,v in CANDIDATES)} candidates", flush=True)
    for name, _, knob, v in survivors:
        print(f"  {name} {knob}={v}", flush=True)

    # ---- PHASE B: real coupling search for each survivor, budget scaled to
    # remaining time (each eval is a full coarse solve, ~3-4min) ----
    n_left = len(survivors)
    for i, (name, base, knob, v) in enumerate(survivors):
        key = f"{name}:{knob}={v}"
        if key in board.get("phase_b", {}):
            print(f"skip (cached): {key}", flush=True)
            continue
        remaining_h = time_left() / 3600
        remaining_candidates = n_left - i
        if remaining_h < 0.5:
            print("DEADLINE reached, stopping phase B", flush=True)
            break
        # leave headroom for later survivors: budget per candidate shrinks as
        # the deadline approaches, floor of 8 evals (still random+GP-guided)
        budget = max(8, min(18, int(remaining_h * 3600 / max(1, remaining_candidates) / 220)))
        try:
            r = phase_b(name, base, knob, v, budget=budget)
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

    print("\nSTRUCTURAL_EXPLORATION_DONE", flush=True)
    board = _load_board()
    ranked = sorted(
        ((k, v["score"]) for k, v in board.get("phase_b", {}).items()
        if v.get("score") is not None),
        key=lambda kv: kv[1])
    print("\n=== Leaderboard (lower score = better) ===")
    for k, sc in ranked:
        print(f"  {sc:7.3f}  {k}")


if __name__ == "__main__":
    main()
