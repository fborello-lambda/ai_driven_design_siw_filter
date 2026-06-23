"""SIW filter pipeline orchestrator.

Runs the design stages in order by executing each module's ``__main__`` demo,
so the orchestrator stays decoupled from each module's internal API.

Two tiers of stages:

  Light (run by default, seconds):
    synth     -> synthesis.py     : Chebyshev g-values, coupling matrix, target.s2p
    geometry  -> siw_geometry.py  : map spec -> physical SIW dimensions
    layout    -> layout_plot.py   : 2D top-view drawing + via-coordinate CSV
    cst       -> cst_export.py    : parametric CST VBA macro (siw_filter.bas)
    report    -> report.py        : comparison figures + IEEE PDF

  Heavy (opt-in — EM solves, minutes to hours):
    calibrate    -> calibrate.py      : openEMS iris-width <-> k calibration
    qe           -> qe_calibrate.py   : openEMS taper -> external Qe
    openems      -> openems_sim.py    : full openEMS FDTD of the filter
    palace-eig   -> palace_geometry.py: Palace eigenmode (2-cavity k)
    palace-driven-> palace_driven.py  : Palace driven full-filter solve
    palace-opt   -> palace_opt.py     : autonomous coordinate-descent tuner

Examples:
    siw                              # light pipeline (synth..report)
    siw --only synth geometry layout # just those stages, in that order
    siw --stage palace-opt           # run one heavy stage
    siw --list                       # show all stages
"""

from __future__ import annotations

import argparse
import runpy
import sys
import time

# stage name -> module to run as "__main__"
LIGHT = [
    ("synth", "siwfilter.synthesis"),
    ("geometry", "siwfilter.siw_geometry"),
    ("layout", "siwfilter.layout_plot"),
    ("cst", "siwfilter.cst_export"),
    ("report", "siwfilter.report"),
]
HEAVY = [
    ("calibrate", "siwfilter.calibrate"),
    ("qe", "siwfilter.qe_calibrate"),
    ("openems", "siwfilter.openems_sim"),
    ("palace-eig", "siwfilter.palace_geometry"),
    ("palace-driven", "siwfilter.palace_driven"),
    ("palace-opt", "siwfilter.palace_opt"),
]
STAGES = dict(LIGHT + HEAVY)


def _run(name: str, module: str) -> None:
    print(f"\n{'=' * 70}\n[{name}]  python -m {module}\n{'=' * 70}")
    t0 = time.time()
    runpy.run_module(module, run_name="__main__")
    print(f"[{name}] done in {time.time() - t0:.1f} s")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="siw", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list all stages and exit")
    ap.add_argument("--stage", action="append", default=[], metavar="NAME",
                    help="run a single stage (repeatable); allows heavy stages")
    ap.add_argument("--only", nargs="+", default=None, metavar="NAME",
                    help="run exactly these stages, in the given order")
    args = ap.parse_args(argv)

    if args.list:
        print("Light (default pipeline):")
        for n, m in LIGHT:
            print(f"  {n:<14} {m}")
        print("Heavy (opt-in via --stage / --only):")
        for n, m in HEAVY:
            print(f"  {n:<14} {m}")
        return 0

    if args.only is not None:
        order = args.only
    elif args.stage:
        order = args.stage
    else:
        order = [n for n, _ in LIGHT]

    unknown = [s for s in order if s not in STAGES]
    if unknown:
        ap.error(f"unknown stage(s): {', '.join(unknown)} (try --list)")

    for name in order:
        _run(name, STAGES[name])
    print(f"\nPipeline complete: {' -> '.join(order)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
