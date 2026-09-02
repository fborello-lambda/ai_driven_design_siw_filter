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
    palace-eig   -> palace_geometry.py: Palace eigenmode (2-cavity k)
    palace-driven-> palace_driven.py  : Palace driven full-filter solve
    palace-opt   -> palace_opt.py     : autonomous coordinate-descent tuner

Plus AI-driven design subcommands (see HANDOFF.md), all Palace/Topology-based:

    compare                     : standing comparison of every landed design vs
                                   the ideal Chebyshev target; cached, so a new
                                   run can be placed against them cheaply
    compare-baselines           : regenerate the 3 standard artifacts for the
                                   already-landed N=3 cascade / N=2 dual-mode
                                   designs, as a regression check
    design --topology ...       : full Bayesian search for a new design
    layout --topology ...       : fast layout-only sanity check (no solve)
    sweep  --topology ...       : wideband sweep of an existing design
    compare-fab-variants        : ONE overlay of every fabrication variant of a
                                   design (PEC vs copper/ENIG/soldermask/
                                   silkscreen/via options) + the ideal Chebyshev
                                   target; also saves the plot data as JSON
    compare-designs --golden .. : fabrication-decision comparison across an
                                   arbitrary list of golden/ design entries --
                                   S11/S21 on identical axes + true-to-scale
                                   board footprints (report.build_design_comparison)

Examples:
    siw                              # light pipeline (synth..report)
    siw --only synth geometry layout # just those stages, in that order
    siw --stage palace-opt           # run one heavy stage
    siw --list                       # show all stages
    siw compare                      # cached comparison table + figure
    siw compare --add-run output/data/opt_dualmode_best.json
    siw design --topology dualmode --evals 18
    siw layout --topology dualmode --params a=57.21,w_iris=15.26,x_iris=28.68,y_wall=8.62,w_ext=16.31
"""

from __future__ import annotations

import argparse
import json
import os
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
    ("palace-eig", "siwfilter.palace_geometry"),
    ("palace-driven", "siwfilter.palace_driven"),
    ("palace-opt", "siwfilter.palace_opt"),
]
STAGES = dict(LIGHT + HEAVY)

# Landed baseline designs (see docs/dualmode_cavity/README.md,
# docs/sma_connector/README.md) -- used by `siw compare-baselines`.
BASELINES = {
    # No cascade entry: neither N=3 nor N=4 has a design that both meets
    # spec and was measured under the real CPWG launch cascade now defaults
    # to (see CLAUDE.md sec 1b/10). The old N=3 entry here (l_cav1=32.81,
    # l_cav2=33.86, w_iris=13.0, w_ext=16.5) predates the 2026-08-30 bugfixes
    # and the CPWG launch -- documented at -15.98dB, re-measured at -4.3dB
    # this session, and would just burn a driven solve on every
    # compare-baselines run. Add a fresh entry once siw synth-design lands
    # one worth keeping (golden/cascade_N3|N4/ per golden/README.md).
    "N=2 dualmode (1.5/3.0mm)": {
        "topology": "dualmode",
        "N": 2,
        "params": {"a": 57.212, "w_iris": 15.261, "x_iris": 28.678,
                  "y_wall": 8.619, "w_ext": 16.311},
    },
}


def _topology_choices():
    # Driven from the registry so a newly registered geometry is usable
    # immediately, instead of silently missing from --topology.
    from .topologies import REGISTRY
    return sorted(REGISTRY)


_TOPOLOGY_CHOICES = _topology_choices()

_DEVICE_HELP = (
    "Solver device. auto (default): GPU when this machine has one AND the topology has a "
    "GPU-validated mesh preset, else CPU -- so the same command works on a GPU-less box. "
    "GPU runs single-rank (-np forced to 1) with MFEM's pooled allocator disabled; measured "
    "~1.24x faster than CPU -np 4 on a GTX 1660 SUPER for dualmode, with S-params matching "
    "to <1e-9 dB. CPU: multi-rank domain decomposition, works for every topology."
)


def _run(name: str, module: str) -> None:
    print(f"\n{'=' * 70}\n[{name}]  python -m {module}\n{'=' * 70}")
    t0 = time.time()
    runpy.run_module(module, run_name="__main__")
    print(f"[{name}] done in {time.time() - t0:.1f} s")


def _parse_params(s: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for pair in s.split(","):
        if not pair.strip():
            continue
        k, v = pair.split("=")
        out[k.strip()] = float(v)
    return out


def _make_spec(args):
    from .config import SPEC, FilterSpec
    N = args.N if args.N is not None else (2 if getattr(args, "topology", None) == "dualmode" else SPEC.N)
    return FilterSpec(
        f0=args.f0 if args.f0 is not None else SPEC.f0,
        FBW=args.fbw if args.fbw is not None else SPEC.FBW,
        N=N,
        ripple_db=args.ripple if args.ripple is not None else SPEC.ripple_db,
        substrate_name=args.substrate if args.substrate is not None else SPEC.substrate_name,
        d_via=SPEC.d_via, p_via=SPEC.p_via,
    )


def _add_spec_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--f0", type=float, default=None, help="center frequency [Hz], default from config.SPEC")
    ap.add_argument("--N", type=int, default=None, help="filter order / pole count")
    ap.add_argument("--fbw", type=float, default=None, help="fractional bandwidth")
    ap.add_argument("--ripple", type=float, default=None, help="Chebyshev ripple [dB]")
    ap.add_argument("--substrate", default=None, help="substrate key from config.SUBSTRATES")


def _spec_kwargs(spec) -> dict:
    return {"f0": spec.f0, "FBW": spec.FBW, "N": spec.N, "ripple_db": spec.ripple_db,
           "substrate_name": spec.substrate_name, "d_via": spec.d_via, "p_via": spec.p_via}


def _render_worker(payload_path: str) -> int:
    """Runs in its own subprocess (see _artifacts): gmsh's offscreen FLTK
    renderer segfaults (not a catchable Python exception) if a second
    render_png session runs in the same process after a first one -- hit
    for real when compare-baselines looped both topologies in-process.
    Isolating each render in a fresh interpreter sidesteps that entirely,
    the same way every Palace solve in this codebase is already isolated."""
    from .config import FilterSpec
    from .topologies import REGISTRY
    payload = json.load(open(payload_path))
    spec = FilterSpec(**payload["spec"])
    topo = REGISTRY[payload["topology"]]
    topo.build_mesh(spec, payload["out_name"], render_png=payload["render_path"],
                    show=False, **payload["params"])
    return 0


def _artifacts(topology, spec, params: dict, prefix: str, r: dict | None = None):
    """The black-box pipeline's 3 standard artifacts: top view, 3D render,
    S21/S11 comparison (see HANDOFF.md). Returns the 3 output paths."""
    import subprocess
    import tempfile
    from .config import out_img
    from .optimize import plot_comparison

    layout_path = out_img(f"{prefix}_layout2d.png")
    topology.plot_layout_2d(spec, layout_path, **params)

    render_path = out_img(f"{prefix}_render.png")
    payload = {"topology": topology.name, "spec": _spec_kwargs(spec), "params": params,
              "out_name": f"{prefix}_render_tmp.msh", "render_path": render_path}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        payload_path = fh.name
    cmd = [sys.executable, "-m", "siwfilter.cli", "_render-worker", payload_path]
    # gmsh's FLTK renderer needs a display even for offscreen rendering; wrap
    # with a virtual one when there isn't a real one already (headless boxes
    # like this session's -- see `sudo apt-get install xvfb`).
    import shutil
    if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True)
        if cp.returncode != 0:
            print(f"(3D render skipped: exit {cp.returncode}\n{cp.stderr[-2000:]})")
            render_path = None
    finally:
        os.remove(payload_path)

    compare_path = None
    if r is not None and r.get("ok"):
        compare_path = out_img(f"{prefix}_response.png")
        plot_comparison({prefix: r}, spec, compare_path)
    return layout_path, render_path, compare_path


def cmd_compare_baselines(args) -> int:
    from .config import SPEC
    from .optimize import evaluate, plot_comparison

    designs: dict[str, dict] = {}
    for label, cfg in BASELINES.items():
        from .config import FilterSpec
        from .topologies import REGISTRY
        spec = FilterSpec(N=cfg["N"], substrate_name=SPEC.substrate_name)
        topo = REGISTRY[cfg["topology"]]
        print(f"\n=== {label} ({cfg['topology']}, N={cfg['N']}) ===")
        r = evaluate(topo, spec, cfg["params"], fine=True, tag_prefix="baseline",
                    device=args.device, np_ranks=args.np)
        designs[label] = r
        board = topo.board_length_mm(spec, **cfg["params"])
        if r.get("ok"):
            print(f"  fc={r.get('fc_3db', r['fc']):.3f}GHz  IL={r['il']:.2f}dB  "
                 f"BW={r['bw']:.0f}MHz  S11w={r['s11w']:.2f}dB  board={board:.1f}mm")
            from .optimize import pole_shape
            import numpy as _np
            # cfg["N"] is the filter ORDER (total pole count) regardless of
            # topology -- for dualmode a single cavity IS N=2, not 1 cavity
            # x poles_per_cavity=2 (that would double-count).
            shape = pole_shape(_np.array(r["f"]), _np.array(r["s11_db"]), cfg["N"])
            flag = "OK" if shape["matches_order"] else "MISMATCH"
            print(f"  SHAPE CHECK [{flag}]: {shape['n_zeros']} S11 zeros (want {cfg['N']}), "
                 f"{shape['n_peaks']} ripple peaks (want {cfg['N'] - 1})")
            slug = label.replace(" ", "_").replace("/", "-")
            from .config import out_data
            result_path = out_data(f"baseline_{slug}_result.json")
            json.dump({"topology": cfg["topology"], "N": cfg["N"], "params": cfg["params"],
                      "metrics": {k: v for k, v in r.items() if k not in ("f", "s11_db", "s21_db")},
                      "shape": shape, "board_length_mm": board,
                      "f_ghz": list(r["f"]), "s11_db": list(r["s11_db"]), "s21_db": list(r["s21_db"])},
                     open(result_path, "w"), indent=2)
            print(f"  Wrote {result_path}")
            _artifacts(topo, spec, cfg["params"], slug, r)
        else:
            print(f"  FAILED: {r.get('err')}")

    from .config import out_img
    plot_comparison(designs, SPEC, out_img("compare_baselines.png"))
    return 0


def cmd_design(args) -> int:
    from .topologies import REGISTRY
    from .optimize import optimize

    topo = REGISTRY[args.topology]
    spec = _make_spec(args)
    if args.calibrate:
        cal = topo.calibrate(spec, device=args.calibrate_device) if topo.name == "dualmode" \
            else topo.calibrate(spec)
        print(f"calibrate(): {cal}" if cal is not None else "calibrate(): not implemented for this topology")

    # --seed turns the GLOBAL search into a LOCAL polish around a known point.
    # That distinction decided the cascade work: a global GP never beat -5 dB
    # S11 in 60+ evals (its objective contains the passband width, which is
    # discontinuous in w_ext), while the same optimizer works locally around a
    # physics-derived seed -- the regime it already succeeds in for dualmode.
    # Pair with `siw synth-design` to generate that seed.
    fab = {}
    if getattr(args, "real_metal", False) or getattr(args, "enig", False):
        if args.topology != "dualmode":
            print("--enig/--real-metal are only wired for dualmode so far"); return 1
        from .topologies.dualmode import (JLCPCB_METAL, JLCPCB_ENIG,
                                          JLCPCB_SOLDERMASK, JLCPCB_SILKSCREEN, VIA_OPEN)
        fab.update(JLCPCB_METAL)
        if args.enig:
            fab.update(JLCPCB_ENIG); fab.update(JLCPCB_SOLDERMASK)
            fab.update(JLCPCB_SILKSCREEN); fab.update(VIA_OPEN)
        from .optimize import fixed_extras
        topo = fixed_extras(topo, fab)
        print(f"fabrication stack ON for every evaluation: {sorted(fab)}")

    if args.seed:
        from .optimize import local_topology
        seed = _parse_params(args.seed)
        topo = local_topology(topo, seed, default_span=args.span)
        print(f"local search around {seed} (span +-{args.span} mm)")
        print(f"  box: {topo.param_space(spec)}")

    fine_sweep = None
    if args.fine_sweep is not None:
        f0, f1, step_hz = args.fine_sweep
        fine_sweep = (f0 / 1e9, f1 / 1e9, step_hz / 1e9)
    # Include N in every output name: log_name/best_json_name default to
    # opt_{topology.name}_*, which has no N in it, so an N=4 run silently
    # overwrote an N=3 run's saved best/log/artifacts (measured this
    # session -- lost the N=3 search's raw result this way).
    prefix = f"{args.topology}_N{spec.N}"
    result = optimize(topo, spec, budget=args.evals, device=args.device, np_ranks=args.np,
                      fine_sweep=fine_sweep, patience=args.patience,
                      log_name=f"opt_{prefix}_log.csv", best_json_name=f"opt_{prefix}_best.json")
    print(f"\nBest design: {result['params']}")
    from .optimize import evaluate
    r = evaluate(topo, spec, result["params"], fine=True, tag_prefix="designfinal",
                device=args.device, np_ranks=args.np)
    _artifacts(topo, spec, result["params"], f"design_{prefix}", r)
    return 0


def cmd_synth_design(args) -> int:
    """Physics-derived cascade design: calibrate -> invert -> assemble.

    Replaces black-box search as the primary route for the cascade. See
    synth_design.py for why: calibrations measure smooth observables on small
    structures and converge in ~3 solves; searches measure the assembled
    filter's bandwidth, which is DISCONTINUOUS in w_ext, and did not.
    """
    from .synth_design import run_pipeline
    from .optimize import evaluate
    from .topologies.cascade import CascadeTopology

    spec = _make_spec(args)
    seed_params = _parse_params(args.seed_params) if args.seed_params else None
    d = run_pipeline(spec, device=args.device, np_ranks=args.np,
                     cache=not args.no_cache, refine=not args.no_refine,
                     fc_trim=not args.no_fc_trim, mid_trim=not args.no_mid_trim,
                     seed_params=seed_params)
    if args.no_confirm:
        return 0
    topo = CascadeTopology()
    r = evaluate(topo, spec, d["params"], fine=True,
                 tag_prefix=f"synthN{spec.N}", device=args.device,
                 np_ranks=args.np, screen=False)
    if r.get("ok"):
        print(f"\nFINE CONFIRM: fc={r['fc']:.3f} GHz  s11w={r['s11w']:.2f} dB  "
              f"bw={r['bw']:.0f} MHz  il={r['il']:.2f} dB  score={r['score']:.3f}")
        print(f"  vs spec: S11 -16 dB | bw {spec.FBW*spec.f0/1e6:.1f} MHz | "
              f"fc {(r['fc']-spec.f0/1e9)*1000:+.0f} MHz")
        from .optimize import pole_shape
        import numpy as _np
        shape = pole_shape(_np.array(r["f"]), _np.array(r["s11_db"]), spec.N)
        flag = "OK" if shape["matches_order"] else "MISMATCH"
        print(f"  SHAPE CHECK [{flag}]: {shape['n_zeros']} S11 zeros "
              f"(want {spec.N}), {shape['n_peaks']} ripple peaks (want {spec.N - 1})"
              f"  zeros@{[round(z, 3) for z in shape['zeros_ghz']]} GHz")
        if not shape["matches_order"]:
            print(f"  -> this is NOT a real order-{spec.N} response despite the score/S11 "
                  f"numbers above -- do not treat this design as landed.")
        _artifacts(topo, spec, d["params"], f"synth_cascade_N{spec.N}", r)
    else:
        print(f"\nFINE CONFIRM FAILED: {r.get('err')}")
        return 1
    return 0


def cmd_calibrate(args) -> int:
    """Run (and cache) the k(w_iris) and/or Qe(w_ext) EM calibrations."""
    import json as _json
    from .topologies import REGISTRY
    from .config import out_data

    topo = REGISTRY[args.topology]
    spec = _make_spec(args)
    out = {}
    if args.what in ("k", "both"):
        out["k"] = topo.calibrate(spec)
        pts = out["k"].get("points", {})
        for w, r in sorted(pts.items(), key=lambda t: float(t[0])):
            if r.get("ok"):
                print(f"  w_iris={float(w):6.2f} -> k={r['k']:.5f}  fc={r['fc']:.4f} GHz")
    if args.what in ("qe", "both"):
        if not hasattr(topo, "calibrate_qe"):
            print(f"calibrate_qe not implemented for topology {topo.name!r}")
            return 1
        out["qe"] = topo.calibrate_qe(spec, device=args.device, np_ranks=args.np)
        for w, r in sorted(out["qe"].get("points", {}).items(),
                           key=lambda t: float(t[0])):
            if r.get("ok"):
                print(f"  w_ext={float(w):6.2f} -> Qe={r['Qe']:8.2f}  "
                      f"Q_L={r['Q_L']:7.2f}  bw={r['bw']:6.1f} MHz")
    p = out_data(f"calibration_{topo.name}_N{spec.N}.json")
    _json.dump(out, open(p, "w"), indent=2,
               default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"WROTE {p}")
    return 0


def cmd_layout(args) -> int:
    from .topologies import REGISTRY
    topo = REGISTRY[args.topology]
    spec = _make_spec(args)
    params = _parse_params(args.params) if args.params else {
        k: v[0] for k, v in topo.param_space(spec).items()}
    # Include N in the prefix: two different orders of the same topology
    # (e.g. cascade N=3 vs N=4) are different geometries and must not share
    # a filename, or the second overwrites the first's baseline picture.
    prefix = f"layout_{args.topology}_N{spec.N}"
    r = None
    if args.render is not None:
        _artifacts(topo, spec, params, prefix)
    else:
        from .config import out_img
        path = out_img(f"{prefix}_2d.png")
        topo.plot_layout_2d(spec, path, **params)
    print(f"params: {params}")
    return 0


def cmd_compare(args) -> int:
    from .comparison import run
    run(refresh=args.refresh, add_run=args.add_run, device=args.device,
        out_name=args.out)
    return 0


def cmd_sweep(args) -> int:
    from .topologies import REGISTRY
    from .optimize import run_driven, plot_comparison, _mesh_preset
    from .config import out_img

    topo = REGISTRY[args.topology]
    spec = _make_spec(args)
    if args.params_file:
        data = json.load(open(args.params_file))
        params = data.get("params", data)
    else:
        params = _parse_params(args.params)
    if getattr(args, "enig", False) or getattr(args, "real_metal", False):
        if args.topology != "dualmode":
            print("--enig/--real-metal are only wired for dualmode so far"); return 1
        from .topologies.dualmode import (JLCPCB_ENIG, JLCPCB_METAL,
                                          JLCPCB_SOLDERMASK, JLCPCB_SILKSCREEN,
                                          VIA_COVERED, VIA_OPEN)
        # Any real-fabrication flag implies REAL COPPER, not PEC. PEC (the
        # idealised lossless conductor) stays the default for a plain
        # `siw sweep`, so every existing golden still reproduces exactly --
        # but it makes no sense to model a soldermask/ENIG/via stack on top
        # of a perfect conductor, so the fab flags switch the metal too.
        preset = dict(JLCPCB_METAL)
        if getattr(args, "enig", False):
            preset.update(JLCPCB_ENIG)
            preset.update(JLCPCB_SOLDERMASK)
        if getattr(args, "cover", None) is not None:
            preset.update(VIA_COVERED if args.cover == "true" else VIA_OPEN)
        if getattr(args, "silkscreen", None) == "true":
            preset.update(JLCPCB_SILKSCREEN)
        for k, v in preset.items():
            params.setdefault(k, v)   # --params can still override any of these

    # Include N: two orders of the same topology (e.g. cascade N=3 vs N=4)
    # share a mesh tag without this and silently overwrite each other's
    # plot/JSON (measured this session -- lost an N=3 sweep result this way).
    prefix = f"sweep_{args.topology}_N{spec.N}"
    mmax, mmin, hair = _mesh_preset(topo.name, args.device)
    r = run_driven(topo, spec, params, prefix,
                   args.fmin, args.fmax, args.step, mmax, mmin, hair,
                   device=args.device, np_ranks=args.np)
    if not r.get("ok"):
        print(f"FAILED: {r.get('err')}")
        return 1
    print(f"fc={r.get('fc_3db', r['fc']):.3f}GHz IL={r['il']:.2f}dB "
          f"BW={r['bw']:.0f}MHz S11w={r['s11w']:.2f}dB")
    plot_comparison({f"{args.topology} sweep": r}, spec, out_img(f"{prefix}.png"))
    from .config import out_data
    sparams_path = out_data(f"{prefix}_sparams.json")
    json.dump({"f_ghz": list(r["f"]), "s11_db": list(r["s11_db"]),
              "s21_db": list(r["s21_db"]), "params": params,
              "fmin": args.fmin, "fmax": args.fmax, "step": args.step},
             open(sparams_path, "w"), indent=2)
    print(f"Wrote {sparams_path}")
    return 0


def cmd_stackup(args) -> int:
    from .report import (build_stackup_view, build_stackup_topview,
                         verify_drawing_matches_mesh)
    spec = _make_spec(args)
    ok = build_stackup_view(spec=spec, out_name=args.out_name)
    if not args.no_topview:
        ok = build_stackup_topview(spec=spec, out_name=f"{args.out_name}_topview") and ok
    if args.verify:
        ok = verify_drawing_matches_mesh(spec=spec) and ok
    return 0 if ok else 1


def cmd_compare_fab_variants(args) -> int:
    from .report import build_fab_variant_comparison
    ok = build_fab_variant_comparison(result_json=args.result_json, f0_ghz=args.f0,
                                      fbw=args.fbw, spec_db=args.spec_db,
                                      out_name=args.out_name)
    return 0 if ok else 1


def cmd_compare_designs(args) -> int:
    from .report import build_design_comparison
    ok = build_design_comparison(args.golden, f0_ghz=args.f0, fbw=args.fbw,
                                 spec_db=args.spec_db, out_name=args.out_name,
                                 labels=args.labels)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="siw", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list all stages and exit")
    ap.add_argument("--stage", action="append", default=[], metavar="NAME",
                    help="run a single stage (repeatable); allows heavy stages")
    ap.add_argument("--only", nargs="+", default=None, metavar="NAME",
                    help="run exactly these stages, in the given order")

    sub = ap.add_subparsers(dest="cmd")

    p_cmp = sub.add_parser("compare-baselines", help="regenerate artifacts for the landed baseline designs")
    p_cmp.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                       help=_DEVICE_HELP)
    p_cmp.add_argument("--np", type=int, default=4, help="MPI ranks (CPU only; GPU always uses 1)")
    p_cmp.set_defaults(func=cmd_compare_baselines)

    p_syn = sub.add_parser(
        "synth-design",
        help="physics-derived cascade design (calibrate -> invert -> assemble)")
    _add_spec_args(p_syn)
    p_syn.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                       help=_DEVICE_HELP)
    p_syn.add_argument("--np", type=int, default=4,
                       help="MPI ranks (CPU only; GPU always uses 1)")
    p_syn.add_argument("--no-cache", action="store_true",
                       help="recompute the EM calibrations instead of reusing "
                            "the cached curves for this substrate/via/f0")
    p_syn.add_argument("--no-refine", action="store_true",
                       help="skip the joint (k, fc) refinement and emit the raw "
                            "first pass. The first pass inverts k at the "
                            "calibration's cavity length then corrects that "
                            "length for fc, but the two are coupled -- measured, "
                            "k fell 17%% when the length moved -- so the raw pass "
                            "is an estimate, not a converged design.")
    p_syn.add_argument("--no-fc-trim", action="store_true",
                       help="skip the final DRIVEN centre-frequency trim. The "
                            "closed-cavity stages cannot see the external "
                            "apertures, which pull fc down ~140 MHz, so without "
                            "this trim the assembled filter is detuned.")
    p_syn.add_argument("--no-mid-trim", action="store_true",
                       help="skip the middle-cavity independent-length correction "
                            "(N>=3 only). fc-trim can only scale every cavity length "
                            "by one common factor, so without this the middle cavity "
                            "keeps the same length as the ends -- the cause of both "
                            "the collapsed-2-pole and skewed-zero-spacing failures.")
    p_syn.add_argument("--no-confirm", action="store_true",
                       help="assemble the design but skip the fine-mesh confirm")
    p_syn.add_argument("--seed-params", default=None,
                       help="k=v,k=v,... -- skip calibration/invert/refine entirely and "
                            "start fc-trim/mid-trim directly from this params dict. For "
                            "resuming a known fc-trimmed point (calibration+refine are "
                            "deterministic given the same cache, so redoing them just to "
                            "retry mid-trim wastes real driven-solve time) or retrying "
                            "mid-trim alone after a tuning change.")
    p_syn.set_defaults(func=cmd_synth_design)

    p_cal = sub.add_parser("calibrate",
                           help="run the EM calibrations (k and/or Qe) and cache them")
    _add_spec_args(p_cal)
    p_cal.add_argument("--topology", default="cascade", choices=_TOPOLOGY_CHOICES)
    p_cal.add_argument("--what", default="both", choices=["k", "qe", "both"],
                       help="k: iris coupling; qe: external coupling; both (default)")
    p_cal.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                       help=_DEVICE_HELP)
    p_cal.add_argument("--np", type=int, default=4,
                       help="MPI ranks (CPU only; GPU always uses 1)")
    p_cal.set_defaults(func=cmd_calibrate)

    p_des = sub.add_parser("design", help="Bayesian search for a new design")
    p_des.add_argument("--topology", required=True, choices=_TOPOLOGY_CHOICES)
    _add_spec_args(p_des)
    p_des.add_argument("--evals", type=int, default=18)
    p_des.add_argument("--fine-sweep", type=float, nargs=3, default=None,
                       metavar=("FMIN_HZ", "FMAX_HZ", "STEP_HZ"),
                       help="override the fine-confirm frequency sweep, e.g. 2.5e9 3.0e9 1e7")
    p_des.add_argument("--seed", default=None, metavar="K=V,...",
                       help="warm-start a LOCAL search in a tight box around these "
                            "params (e.g. from `siw synth-design`). Without it the "
                            "search is global, which for the cascade never beat "
                            "-5 dB S11 in 60+ evals -- its objective contains the "
                            "passband width, discontinuous in w_ext.")
    p_des.add_argument("--span", type=float, default=2.5, metavar="MM",
                       help="half-width of the local box around --seed (default 2.5mm)")
    p_des.add_argument("--patience", type=int, default=None, metavar="N",
                       help="stop after N consecutive non-improving evals "
                            "(default: run the full budget)")
    p_des.add_argument("--calibrate", action="store_true", help="run the cheap eigenmode pre-pass first")
    p_des.add_argument("--calibrate-device", default=None, choices=["CPU", "GPU"],
                       help="device for the --calibrate eigenmode pre-pass. Default: auto -- GPU "
                            "when one is present (small closed-cavity mesh, confirmed faster and "
                            "fits; see DualModeTopology.calibrate), CPU otherwise. Independent of "
                            "--device, which governs the much larger driven+SMA search where GPU "
                            "has been confirmed not to fit on a 6GB card.")
    p_des.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                       help=_DEVICE_HELP)
    p_des.add_argument("--np", type=int, default=4, help="MPI ranks (CPU only; GPU always uses 1)")
    p_des.add_argument("--real-metal", action="store_true",
                       help="evaluate every design with REAL lossy copper instead of PEC")
    p_des.add_argument("--enig", action="store_true",
                       help="evaluate every design with the full JLCPCB stack "
                            "(real copper + ENIG + soldermask + silkscreen + open vias)")
    p_des.set_defaults(func=cmd_design)

    p_lay = sub.add_parser("layout", help="fast layout-only sanity check (no solve)")
    p_lay.add_argument("--topology", required=True, choices=_TOPOLOGY_CHOICES)
    _add_spec_args(p_lay)
    p_lay.add_argument("--params", default=None, help="k=v,k=v,... (mm); default = param_space init values")
    p_lay.add_argument("--render", nargs="?", const=True, default=None,
                       help="also write the 3D shaded render")
    p_lay.set_defaults(func=cmd_layout)

    p_cmpq = sub.add_parser("compare",
                            help="standing comparison of every landed design + the ideal "
                                 "Chebyshev target (cached; use --refresh to recompute)")
    p_cmpq.add_argument("--refresh", action="store_true",
                        help="recompute every reference case instead of using the cache")
    p_cmpq.add_argument("--add-run", default=None, metavar="BEST_JSON",
                        help="also plot a new design, from a `siw design` best-JSON "
                             "(optionally carrying 'topology'/'N'/'label' keys)")
    p_cmpq.add_argument("--out", default="final_comparison.png", help="figure filename")
    p_cmpq.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                        help=_DEVICE_HELP)
    p_cmpq.set_defaults(func=cmd_compare)

    p_swp = sub.add_parser("sweep", help="wideband sweep of an existing design")
    p_swp.add_argument("--topology", required=True, choices=_TOPOLOGY_CHOICES)
    _add_spec_args(p_swp)
    p_swp.add_argument("--params", default=None, help="k=v,k=v,... (mm)")
    p_swp.add_argument("--params-file", default=None, help="JSON file with {'params': {...}}")
    p_swp.add_argument("--enig", action="store_true",
                       help="JLCPCB's real ENIG stack (dualmode only): Rogers -> Cu -> ENIG "
                            "-> soldermask, IPC-4552 numbers (4.5um Ni, sigma=1.67e6 S/m, "
                            "mu_r=1.0 -- see topologies/dualmode.JLCPCB_ENIG). Combine with "
                            "--params soldermask_um=20 for the masked case, or omit it for "
                            "ENIG exposed directly to air.")
    p_swp.add_argument("--real-metal", action="store_true",
                       help="model exterior metal as REAL lossy copper (5.96e7 S/m, 35um 1oz) "
                            "instead of PEC (perfect, lossless). Every golden to date is "
                            "PEC-only, i.e. dielectric loss only -- this adds the missing "
                            "conductor loss (modelled Qu 270 -> ~188, ~0.6dB more IL).")
    p_swp.add_argument("--cover", choices=["true", "false"], default=None,
                       help="via cover/fill: true = resin-filled + copper-capped (solid plug, "
                            "no hole through the board); false = standard open plated barrel "
                            "(hollow copper shell, air core). Implies real copper vias.")
    p_swp.add_argument("--silkscreen", choices=["true", "false"], default=None,
                       help="silkscreen epoxy ink layer (12um) on top of the soldermask")
    p_swp.add_argument("--fmin", type=float, default=0.5, help="GHz")
    p_swp.add_argument("--fmax", type=float, default=6.0, help="GHz")
    p_swp.add_argument("--step", type=float, default=0.05, help="GHz")
    p_swp.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                       help=_DEVICE_HELP)
    p_swp.add_argument("--np", type=int, default=4)
    p_swp.set_defaults(func=cmd_sweep)

    p_stk = sub.add_parser("stackup",
                           help="cross-section view of the real fabrication stack at the feed "
                                "(substrate / copper / ENIG / soldermask / silkscreen), drawn "
                                "both with the feed covered and with the soldermask opened")
    _add_spec_args(p_stk)
    p_stk.add_argument("--out-name", default="stackup", help="output basename")
    p_stk.add_argument("--verify", action="store_true",
                       help="build the real mesh and assert the drawn via positions / CPWG "
                            "gap match what was actually meshed (guards against the drawing "
                            "depicting a launch that is not simulated)")
    p_stk.add_argument("--no-topview", action="store_true",
                       help="cross-section only; skip the top view showing soldermask "
                            "coverage and the recommended feed opening")
    p_stk.set_defaults(func=cmd_stackup)

    p_fab = sub.add_parser("compare-fab-variants",
                           help="ONE overlay of every fabrication variant of a design "
                                "(PEC vs copper/ENIG/soldermask/silkscreen/via options) plus "
                                "the ideal Chebyshev target, on shared axes. Reads the "
                                "incremental variant-sweep JSON, so it works while cells are "
                                "still solving; also saves the plotted curves + metrics as JSON.")
    p_fab.add_argument("--result-json", default=None,
                       help="variant sweep results (default: output/data/four_variants_result.json)")
    p_fab.add_argument("--f0", type=float, default=2.87, help="GHz, for the FBW shading")
    p_fab.add_argument("--fbw", type=float, default=0.05, help="fractional BW, for the shading")
    p_fab.add_argument("--spec-db", type=float, default=-16.0, help="S11 spec line")
    p_fab.add_argument("--out-name", default="fab_variant_comparison",
                       help="output basename -> output/imgs/<n>.png, docs/<n>.png, "
                            "output/data/<n>_plotdata.json")
    p_fab.set_defaults(func=cmd_compare_fab_variants)

    p_cmpd = sub.add_parser("compare-designs",
                            help="fabrication-decision comparison across a list of golden/ "
                                 "design entries -- S11/S21 on identical axes + true-to-scale "
                                 "board footprints (no re-solving, reads existing golden data)")
    p_cmpd.add_argument("--golden", nargs="+", required=True,
                        help="paths to golden/<topology_N>/<stem>.json entries "
                             "(each needs a companion <stem>.s11s21.json)")
    p_cmpd.add_argument("--f0", type=float, default=2.87, help="GHz, for the FBW shading")
    p_cmpd.add_argument("--fbw", type=float, default=0.05, help="fractional BW, for the shading")
    p_cmpd.add_argument("--spec-db", type=float, default=-16.0, help="S11 spec line")
    p_cmpd.add_argument("--out-name", default="design_comparison",
                        help="output basename -- writes <out-name>_sparams.png and "
                             "<out-name>_board_scale.png to output/imgs/ and docs/")
    p_cmpd.add_argument("--labels", nargs="+", default=None,
                        help="one label per --golden entry, same order (default: "
                             "'<topology> N=<N>', since landed-vs-best-known isn't "
                             "reliably inferable from the golden schema)")
    p_cmpd.set_defaults(func=cmd_compare_designs)

    # Internal only (see _artifacts/_render_worker): isolates one gmsh
    # render_png call per subprocess, not meant to be invoked directly.
    p_rw = sub.add_parser("_render-worker")
    p_rw.add_argument("payload_path")
    p_rw.set_defaults(func=lambda a: _render_worker(a.payload_path))

    args = ap.parse_args(argv)

    if getattr(args, "cmd", None) is not None:
        return args.func(args)

    if args.list:
        print("Light (default pipeline):")
        for n, m in LIGHT:
            print(f"  {n:<14} {m}")
        print("Heavy (opt-in via --stage / --only):")
        for n, m in HEAVY:
            print(f"  {n:<14} {m}")
        print("AI-driven design subcommands: compare, compare-baselines, design, layout, "
              "sweep (see `siw <subcommand> --help`)")
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
