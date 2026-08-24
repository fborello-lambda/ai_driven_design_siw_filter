"""Coupling-only grid sweep: separate the external/internal coupling knobs
(w_iris, w_ext, y_wall) from cavity size, which the joint Bayesian search
never does on its own.

Why this exists (docs/geometry_exploration/plan_2026-08-24.md section 3):
every geometry this session's joint search touched landed 2.2-2.5x over the
5% FBW target bandwidth, and corner_cut's `w_iris` was found railed at its
own saturation floor without anyone noticing until the run finished --
because a joint search happily trades `a` against `w_iris` against `w_ext`
to chase the score, and nothing in that process asks "what does coupling
alone do, at a fixed, correctly-resonant cavity size?" A grid sweep at fixed
`a` answers exactly that question, and is the natural place to spend the
fast screen (screen_at_f0 in optimize.py): most grid points will be
uninteresting (way over- or under-coupled), and the screen's whole point is
to throw those away before paying for a full coarse eval.

Run:
    uv run python -m siwfilter.sweep_coupling --topology corner_cut \\
        --a 59.36 --w-iris 3,6,9,12,15,18 --w-ext 10,13,16,19,22

    uv run python -m siwfilter.sweep_coupling --topology dualmode \\
        --a 57.3 --x-iris 28.7 --w-iris 10,13,16,19 --w-ext 13,16,19 \\
        --y-wall 6,9,12
"""
from __future__ import annotations

import argparse
import csv
import itertools
import time

from .config import FilterSpec, out_data
from .optimize import band_edges, evaluate, screen_at_f0
from .topologies import REGISTRY


def _grid(spec_str: str | None) -> list[float] | None:
    if spec_str is None:
        return None
    return [float(v) for v in spec_str.split(",")]


def run(topology_name: str, fixed: dict, grids: dict[str, list[float]],
        spec: FilterSpec, device: str = "auto", np_ranks: int = 1,
        screen: bool = True, log_name: str | None = None) -> str:
    topo = REGISTRY[topology_name]
    keys = list(grids.keys())
    log_path = out_data(log_name or f"sweep_{topology_name}_coupling.csv")
    n_total = 1
    for v in grids.values():
        n_total *= len(v)
    print(f"coupling sweep: {topology_name}  {n_total} grid points over "
         f"{keys}  fixed={fixed}", flush=True)

    with open(log_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["n", *keys, "screened", "s11_screen", "s21_screen",
                   "fc_3db", "il", "bw", "s11w", "score", "seconds"])
        n = 0
        for combo in itertools.product(*grids.values()):
            n += 1
            params = {**fixed, **dict(zip(keys, combo))}
            t0 = time.time()
            if screen:
                s = screen_at_f0(topo, spec, params, f"scrsweep_{topology_name}{n}",
                                 device=device, np_ranks=np_ranks)
                if not s["pass"]:
                    dt = time.time() - t0
                    w.writerow([n, *combo, 1, s.get("s11_best"), s.get("s21_best"),
                               "", "", "", "", "", f"{dt:.1f}"])
                    fh.flush()
                    print(f"[{n}/{n_total}]  {dict(zip(keys, combo))}  "
                         f"SCREENED OUT ({dt:.0f}s)  s11={s.get('s11_best')} "
                         f"s21={s.get('s21_best')}", flush=True)
                    continue
            r = evaluate(topo, spec, params, fine=False,
                        tag_prefix=f"sweep{topology_name}",
                        device=device, np_ranks=np_ranks, screen=False)
            dt = time.time() - t0
            if not r.get("ok"):
                w.writerow([n, *combo, 0, "", "", "", "", "", "", "", f"{dt:.1f}"])
                fh.flush()
                print(f"[{n}/{n_total}]  {dict(zip(keys, combo))}  FAILED "
                     f"{r.get('err')} ({dt:.0f}s)", flush=True)
                continue
            e = band_edges(r["f"], r["s21_db"])
            w.writerow([n, *combo, 0, "", "", f"{e['fc_3db']:.4f}",
                       f"{r['il']:.2f}", f"{e['bw']:.1f}", f"{r['s11w']:.2f}",
                       f"{r['score']:.3f}", f"{dt:.1f}"])
            fh.flush()
            print(f"[{n}/{n_total}]  {dict(zip(keys, combo))}  "
                 f"fc={e['fc_3db']:.3f} il={r['il']:.2f} bw={e['bw']:.0f} "
                 f"s11w={r['s11w']:.1f} score={r['score']:.2f} ({dt:.0f}s)",
                 flush=True)

    print(f"\nWrote {log_path}")
    return log_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topology", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--a", type=float, required=True,
                    help="fixed cavity size (mm) -- the one dimension NOT swept")
    ap.add_argument("--x-iris", type=float, default=None)
    ap.add_argument("--w-iris", type=str, default=None, help="comma list, mm")
    ap.add_argument("--w-ext", type=str, default=None, help="comma list, mm")
    ap.add_argument("--y-wall", type=str, default=None, help="comma list, mm")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--np", type=int, default=1)
    ap.add_argument("--no-screen", action="store_true")
    args = ap.parse_args()

    fixed = {"a": args.a}
    if args.x_iris is not None:
        fixed["x_iris"] = args.x_iris
    grids = {}
    for name, raw in (("w_iris", args.w_iris), ("w_ext", args.w_ext),
                      ("y_wall", args.y_wall)):
        g = _grid(raw)
        if g is not None:
            grids[name] = g
    if not grids:
        ap.error("give at least one of --w-iris/--w-ext/--y-wall as a comma list")

    run(args.topology, fixed, grids, FilterSpec(N=2), device=args.device,
        np_ranks=args.np, screen=not args.no_screen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
