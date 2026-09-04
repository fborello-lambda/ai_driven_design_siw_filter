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
        # --real-metal now works for CASCADE too (the exterior-face split was
        # ported into palace_driven on 2026-09-03). --enig still does not:
        # ENIG/soldermask/silkscreen are meshed layers, unresolvable at this
        # mesh density, and ENIG is in any case shielded behind ~14 skin
        # depths of ground-plane copper. See docs/STATE.md.
        if args.topology == "cascade" and getattr(args, "enig", False):
            print("--enig is not available for cascade (and is an RF no-op: the "
                  "plating sits on the shielded side of the ground plane). Use "
                  "--real-metal."); return 1
        if args.topology not in ("dualmode", "cascade"):
            print("--enig/--real-metal are only wired for dualmode/cascade so far"); return 1
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
    # Objective reweighting. Measured 2026-09-03 on dualmode N=2: bandwidth
    # and return loss are in DIRECT OPPOSITION across every geometry
    # parameter (w_iris, w_ext at two irises, y_wall -- all scanned on the
    # assembled filter), so the default w_bw=3.0 charges ~3.5 at the
    # 310MHz/-10.35dB corner and steers the search away from the best match
    # this structure can produce. --w-bw 0 chases return loss alone and
    # accepts whatever bandwidth follows; that is a deliberate spec
    # trade-off, so it is an explicit flag rather than a changed default.
    score_kwargs = {}
    if args.w_bw is not None:
        score_kwargs["w_bw"] = args.w_bw
    if args.w_fc is not None:
        score_kwargs["w_fc"] = args.w_fc
    if score_kwargs:
        print(f"objective reweighted: {score_kwargs}")
    result = optimize(topo, spec, budget=args.evals, device=args.device, np_ranks=args.np,
                      fine_sweep=fine_sweep, patience=args.patience,
                      score_kwargs=score_kwargs or None,
                      log_name=f"opt_{prefix}_log.csv", best_json_name=f"opt_{prefix}_best.json")
    print(f"\nBest design: {result['params']}")
    from .optimize import evaluate
    r = evaluate(topo, spec, result["params"], fine=True, tag_prefix="designfinal",
                device=args.device, np_ranks=args.np,
                score_kwargs=score_kwargs or None)
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
    if getattr(args, "plot_only", False):
        p = out_data(f"calibration_{topo.name}_N{spec.N}.json")
        _plot_calibration(_json.load(open(p)), topo.name, spec.N)
        return 0
    # Both calibration testbeds must use the cavity actually being designed.
    # They default to module constants (a=61.05mm, y_wall=6.0mm), so without
    # this the calibration measures a DIFFERENT resonator than the design --
    # which is exactly what happened on the first run.
    cav = _json.loads(args.cavity) if args.cavity else {}

    def _cav_for(fn) -> dict:
        """Keep only the cavity keys this testbed actually accepts.

        The two testbeds are different structures, so they take different
        cavity keys: the k testbed is a CLOSED two-mode cavity and needs
        x_iris_mm, while the Qe testbed removes the internal iris entirely
        (w_iris=None, x_iris=None) and has no such parameter. Passing the
        same --cavity dict to both raised
        `calibrate_qe() got an unexpected keyword argument 'x_iris_mm'`
        AFTER the 9-minute k sweep had already completed, losing the whole
        Qe sweep, the inversion and the confirm.
        """
        import inspect
        allowed = set(inspect.signature(fn).parameters)
        drop = sorted(set(cav) - allowed)
        if drop:
            print(f"  ({fn.__name__}: ignoring cavity keys {drop} -- not "
                  f"parameters of this testbed)")
        return {k: v for k, v in cav.items() if k in allowed}

    if args.what in ("k", "both"):
        # Forward the device choice. This was NOT forwarded, so the k sweep
        # always used calibrate()'s own default (GPU for dualmode) regardless
        # of --device, and every one of its 6 eigenmode points died with
        # CUDA_ERROR_OUT_OF_MEMORY -- silently, since calibrate() records a
        # failed point as {"ok": False} rather than raising. The whole k
        # curve came back empty and the k inversion produced nothing, which
        # only surfaced later as --confirm failing with "mesh:'w_iris'".
        k_kw = _cav_for(topo.calibrate)
        if args.w_iris:
            k_kw["w_irises"] = [float(x) for x in args.w_iris.split(",")]
        # No `except TypeError: calibrate(spec)` fallback here any more: it
        # silently threw away --device and --cavity on any signature mismatch,
        # which is how the k sweep ran on the wrong device in the first place.
        out["k"] = topo.calibrate(spec, device=args.device, **k_kw)
        _kpts = out["k"].get("points", {})
        _kok = sum(1 for r in _kpts.values() if isinstance(r, dict) and r.get("ok"))
        if _kpts and _kok == 0:
            print(f"  ERROR: all {len(_kpts)} k points FAILED -- the k curve is empty, "
                  f"so no w_iris can be inverted. Check the newest "
                  f"output/data/dmcal_wi*.log; a CUDA out-of-memory there means "
                  f"retrying with --device CPU.")
        pts = out["k"].get("points", {})
        for w, r in sorted(pts.items(), key=lambda t: float(t[0])):
            if r.get("ok"):
                print(f"  w_iris={float(w):6.2f} -> k={r['k']:.5f}  fc={r['fc']:.4f} GHz")
    if args.what in ("qe", "both"):
        if not hasattr(topo, "calibrate_qe"):
            print(f"calibrate_qe not implemented for topology {topo.name!r}")
            return 1
        qe_kw = _cav_for(topo.calibrate_qe)
        if args.w_ext:
            qe_kw["w_exts"] = [float(x) for x in args.w_ext.split(",")]
        if args.qe_window:
            lo, hi, st = (float(x) for x in args.qe_window.split(","))
            qe_kw.update(fmin_ghz=lo, fmax_ghz=hi, step_ghz=st)
        out["qe"] = topo.calibrate_qe(spec, device=args.device,
                                      np_ranks=args.np, **qe_kw)
        for w, r in sorted(out["qe"].get("points", {}).items(),
                           key=lambda t: float(t[0])):
            if r.get("ok"):
                print(f"  w_ext={float(w):6.2f} -> Qe={r['Qe']:8.2f}  "
                      f"Q_L={r['Q_L']:7.2f}  bw={r['bw']:6.1f} MHz")
    # ---- invert: measured curves -> physical geometry for the spec ----
    # Previously the CLI only MEASURED; inverting and confirming lived in
    # synth_design.py, which is cascade-only, so every dual-mode run had to
    # go through an ad-hoc script. This keeps the whole chain in the CLI.
    if args.invert:
        import numpy as _np
        from .synthesis import synthesize
        syn = synthesize(spec)
        k_t = float(_np.asarray(syn.k).ravel()[0])
        qe_t = float(syn.qe_in)
        print(f"\ntargets for N={spec.N}, {spec.ripple_db}dB, FBW={spec.FBW}: "
              f"k={k_t:.4f}  Qe={qe_t:.2f}")
        geom: dict[str, float] = {}

        if "qe" in out and out["qe"].get("w_of_logQe"):
            we = float(_np.polyval(out["qe"]["w_of_logQe"], _np.log(qe_t)))
            qes = [d["Qe"] for d in out["qe"]["points"].values() if d.get("ok")]
            if qes and not (min(qes) <= qe_t <= max(qes)):
                print(f"  WARNING: Qe target {qe_t:.2f} is OUTSIDE the measured "
                      f"range [{min(qes):.1f}, {max(qes):.1f}] -- this is an "
                      f"EXTRAPOLATION. Widen the w_ext sweep instead of trusting it.")
            # BRACKET CHECK. The range test above only asks whether the
            # target lies between the extreme measured Qe values; it cannot
            # tell that some of those values are junk. Measured: two
            # window-truncated points shared Qe=8.52, dragging the quadratic
            # so it returned w_ext=15.51mm when the target was bracketed by
            # 16mm and 19mm -- an answer outside its own bracket, reported
            # without complaint. Verify the inverted value actually sits
            # between the two points that straddle the target.
            okp = sorted((float(w), d["Qe"])
                         for w, d in out["qe"]["points"].items() if d.get("ok"))
            lo = max((w for w, q in okp if q >= qe_t), default=None)
            hi = min((w for w, q in okp if q <= qe_t), default=None)
            if lo is not None and hi is not None and not (min(lo, hi) - 1e-9 <= we <= max(lo, hi) + 1e-9):
                print(f"  WARNING: inverted w_ext={we:.3f}mm falls OUTSIDE its own "
                      f"bracket [{min(lo,hi):.1f}, {max(lo,hi):.1f}]mm -- the fit is "
                      f"not tracking the data. Check for rejected//truncated points "
                      f"and re-sweep near the bracket before trusting this.")
            geom["w_ext"] = round(we, 3)
            print(f"  Qe={qe_t:.2f} -> w_ext = {we:.3f} mm"
                  + (f"  (bracketed by {min(lo,hi):.1f}-{max(lo,hi):.1f}mm)"
                     if lo is not None and hi is not None else ""))
        elif "qe" in out:
            print("  Qe inversion unavailable (need >=3 usable points)")

        if "k" in out:
            pts = [(float(w), r["k"]) for w, r in out["k"].get("points", {}).items()
                   if r.get("ok")]
            if len(pts) >= 3:
                ws = _np.array([q[0] for q in pts]); ks = _np.array([q[1] for q in pts])
                fit = _np.polyfit(ks, ws, min(2, len(pts) - 1))
                wi = float(_np.polyval(fit, k_t))
                if not (ks.min() <= k_t <= ks.max()):
                    print(f"  WARNING: k target {k_t:.4f} is OUTSIDE the measured "
                          f"range [{ks.min():.4f}, {ks.max():.4f}] -- EXTRAPOLATION.")
                geom["w_iris"] = round(wi, 3)
                print(f"  k={k_t:.4f} -> w_iris = {wi:.3f} mm")
            else:
                print("  k inversion unavailable (need >=3 usable points)")

        out["targets"] = {"k": k_t, "Qe": qe_t}
        out["inverted_geometry"] = geom

        if args.confirm and geom:
            from .optimize import evaluate, pole_shape
            import numpy as _np2
            base = _json.loads(args.confirm_base) if args.confirm_base else {}
            P = dict(base); P.update(geom)
            print(f"\nCONFIRM with {P}")
            r = evaluate(topo, spec, P, fine=True,
                        tag_prefix=f"cal_confirm_{topo.name}",
                        device=args.device, np_ranks=args.np)
            if r.get("ok"):
                sh = pole_shape(_np2.array(r["f"]), _np2.array(r["s11_db"]), spec.N)
                print(f"  fc={r.get('fc_3db', r['fc']):.3f}GHz  IL={r['il']:.2f}dB  "
                      f"BW={r['bw']:.0f}MHz  S11w={r['s11w']:.2f}dB  "
                      f"poles={sh['n_zeros']} (want {spec.N})")
                out["confirm"] = {"params": P,
                                  "metrics": {k: v for k, v in r.items()
                                              if k not in ("f", "s11_db", "s21_db", "csv")},
                                  "f_ghz": list(r["f"]), "s11_db": list(r["s11_db"]),
                                  "s21_db": list(r["s21_db"])}
            else:
                print(f"  CONFIRM FAILED: {r.get('err')}")

    p = out_data(f"calibration_{topo.name}_N{spec.N}.json")
    _json.dump(out, open(p, "w"), indent=2,
               default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"WROTE {p}")
    _plot_calibration(out, topo.name, spec.N)
    return 0


def _plot_calibration(cal: dict, topo_name: str, N: int) -> None:
    from .report import build_calibration_plot
    try:
        build_calibration_plot(cal, f"calibration_{topo_name}_N{N}")
    except Exception as exc:                       # a plot must never lose a sweep
        print(f"  (calibration plot skipped: {exc})")


def cmd_scan(args) -> int:
    """Scan one geometry parameter on the ASSEMBLED filter and invert for a
    target bandwidth.

    Why this exists. `siw calibrate` measures k and Qe on small PROXY
    structures and inverts the textbook bandpass mapping. For the cascade
    that transfers. For dual-mode it demonstrably does NOT: on 2026-09-03
    both couplings were driven onto their synthesis targets (k=0.069,
    Qe=16.86) and the assembled filter came back 334 MHz wide with ONE
    reflection zero and -5.9 dB return loss -- worse than the un-calibrated
    starting point. The reason is structural: the Qe testbed removes the
    internal iris row to isolate "one resonator", but in a dual-mode cavity
    the two resonators are two modes of the SAME cavity, so removing the
    iris does not isolate one of them -- it produces a different, single-mode
    resonator (measured 120 MHz higher in frequency). There is no proxy to
    calibrate on, so measure the real structure instead.

    Writes output/data/scan_<topology>_N<N>_<param>.json and a plot; both
    are incremental, so a scan that is still running is still readable.
    """
    import json as _json
    import numpy as _np
    from .topologies import REGISTRY
    from .optimize import evaluate, pole_shape
    from .config import out_data

    topo = REGISTRY[args.topology]
    spec = _make_spec(args)
    base = _parse_params(args.params)
    name, _, vals_s = args.scan.partition("=")
    if not vals_s:
        print("--scan needs NAME=V1,V2,..."); return 1
    vals = [float(v) for v in vals_s.split(",")]
    target_bw = args.target_bw if args.target_bw is not None else spec.FBW * spec.f0 / 1e6

    launch = getattr(args, "launch", "cpwg")
    suffix = "" if launch == "cpwg" else f"_{launch}"
    path = out_data(f"scan_{topo.name}_N{spec.N}_{name}{suffix}.json")
    out = {"base": base, "param": name, "values": vals, "launch": launch,
           "target_bw_mhz": target_bw, "points": {}}

    print(f"scanning {name} over {vals} (target BW {target_bw:.1f} MHz, "
          f"launch={launch})")
    for v in vals:
        P = dict(base); P[name] = v
        if launch != "cpwg":
            P["launch"] = launch
        # The launch is not part of the mesh tag (it is not a dimension), so
        # two launches at ONE geometry would otherwise write to the same
        # files. Keep them apart via the prefix.
        r = evaluate(topo, spec, P, fine=True,
                     tag_prefix=f"scan_{topo.name}_{name}{suffix}",
                     device=args.device, np_ranks=args.np)
        if not r.get("ok"):
            out["points"][str(v)] = {"ok": False, "err": r.get("err")}
            print(f"  {name}={v:g}: FAILED {r.get('err')}")
            _json.dump(out, open(path, "w"), indent=2, default=str)
            continue
        sh = pole_shape(_np.array(r["f"]), _np.array(r["s11_db"]), spec.N)
        # Two guards, both recorded per point rather than averaged into the fit:
        #   truncated -- a -3dB band running off the sweep window reads
        #     NARROWER than it is (the failure that made the Qe calibration
        #     report 61 where the truth was 22);
        #   n_lobes>1 -- the response is SPLIT into disjoint passbands and the
        #     `bw` number is one lobe, not the filter's band. Fitting through
        #     those produced a smooth-looking 35/66/122/284 MHz curve whose
        #     inversion pointed at the merge threshold, where no geometry
        #     delivers the target bandwidth.
        rec = {"ok": True, "fc": r.get("fc_3db", r["fc"]), "bw": r["bw"],
               "il": r["il"], "s11w": r["s11w"], "poles": sh["n_zeros"],
               "truncated": bool(r.get("band_truncated")),
               "n_lobes": int(r.get("n_lobes", 1)),
               "lobe_split_mhz": float(r.get("lobe_split_mhz", 0.0)),
               "f_ghz": list(r["f"]), "s11_db": list(r["s11_db"]),
               "s21_db": list(r["s21_db"])}
        out["points"][str(v)] = rec
        print(f"  {name}={v:g}: fc={rec['fc']:.3f}GHz  BW={rec['bw']:.0f}MHz  "
              f"IL={rec['il']:.2f}dB  S11w={rec['s11w']:.2f}dB  "
              f"poles={rec['poles']}"
              + ("  TRUNCATED" if rec["truncated"] else "")
              + (f"  SPLIT into {rec['n_lobes']} lobes "
                 f"({rec['lobe_split_mhz']:.0f}MHz notch) -- BW is ONE lobe"
                 if rec["n_lobes"] > 1 else ""))
        _json.dump(out, open(path, "w"), indent=2, default=str)

    good = sorted((float(k), p) for k, p in out["points"].items()
                  if p.get("ok") and not p["truncated"]
                  and p.get("n_lobes", 1) == 1)
    if len(good) >= 2:
        xs = _np.array([g[0] for g in good])
        bws = _np.array([g[1]["bw"] for g in good])
        deg = min(2, len(good) - 1)
        fit = _np.polyfit(bws, xs, deg)
        star = float(_np.polyval(fit, target_bw))
        inside = bws.min() <= target_bw <= bws.max()
        out["inverted"] = {name: round(star, 3), "bracketed": bool(inside)}
        print(f"\nINVERT: BW={target_bw:.1f}MHz -> {name} = {star:.3f} mm"
              + ("" if inside else
                 f"  WARNING: EXTRAPOLATION, measured BW spans "
                 f"[{bws.min():.0f}, {bws.max():.0f}]MHz"))
    else:
        n_split = sum(1 for _, p in out["points"].items()
                      if p.get("ok") and p.get("n_lobes", 1) > 1)
        print(f"\nNO INVERSION: only {len(good)} single-passband point(s)"
              + (f"; {n_split} point(s) were SPLIT into disjoint lobes, where "
                 f"bandwidth is not defined for the filter as a whole. Move the "
                 f"mode splitting (w_iris) rather than the loading (w_ext)."
                 if n_split else "."))
    _json.dump(out, open(path, "w"), indent=2, default=str)
    print(f"WROTE {path}")
    try:
        from .report import build_scan_plot
        build_scan_plot(out, f"scan_{topo.name}_N{spec.N}_{name}")
    except Exception as exc:
        print(f"  (scan plot skipped: {exc})")
    return 0



def cmd_cst(args) -> int:
    """Generate the CST VBA macro for a LANDED design, with the real launch."""
    from .config import SPEC, FilterSpec, out_bas
    from .topologies import REGISTRY
    from .topologies.launch import LAUNCHES
    from .cst_export import write_bas

    topo = REGISTRY[args.topology]
    spec = FilterSpec(f0=SPEC.f0, FBW=SPEC.FBW,
                      N=args.N if args.N is not None else SPEC.N,
                      ripple_db=SPEC.ripple_db, substrate_name=SPEC.substrate_name,
                      d_via=SPEC.d_via, p_via=SPEC.p_via)
    params = _parse_params(args.params) if args.params else None
    if params is None:
        print("--params is required: the analytical default is NOT any optimised "
              "geometry, and exporting it would hand CST a design nobody chose.")
        return 1
    if not hasattr(topo, "_geometry"):
        print(f"topology {topo.name!r} has no _geometry(); CST export supports "
              f"cascade for now"); return 1
    g = topo._geometry(spec, params)
    launch = None if args.launch == "none" else LAUNCHES[args.launch]
    path = args.out or out_bas(f"siw_{args.topology}_N{spec.N}.bas")
    write_bas(path, spec=spec, geometry=g, launch=launch, sma_len_mm=args.sma_len)
    if launch:
        print(f"  launch: {args.launch} (real SMA coax stubs + coaxial ports)")
    else:
        print("  launch: NONE -- bare microstrip with waveguide ports. This is "
              "NOT what was simulated; use --launch cpwg for the real thing.")
    return 0

def cmd_kicad(args) -> int:
    """Write the .kicad_pcb for a LANDED design and drive kicad-cli for the
    JLCPCB deliverables: gerbers (F.Cu/B.Cu/F.Mask/B.Mask/Edge.Cuts), the
    Excellon drill files, a 3D STEP, an SVG for eyeballing, and the fab
    notes a gerber cannot carry."""
    from .config import SPEC, FilterSpec, OUTPUT_DIR
    from .topologies import REGISTRY
    from .topologies.launch import LAUNCHES
    from .kicad_export import (write_kicad_pcb, run_kicad_cli, zip_for_fab,
                               write_fab_notes, render_3d, render_drill_map)

    topo = REGISTRY[args.topology]
    spec = FilterSpec(f0=SPEC.f0, FBW=SPEC.FBW,
                      N=args.N if args.N is not None else SPEC.N,
                      ripple_db=SPEC.ripple_db, substrate_name=SPEC.substrate_name,
                      d_via=SPEC.d_via, p_via=SPEC.p_via)
    params = _parse_params(args.params)
    if not hasattr(topo, "_geometry"):
        print(f"topology {topo.name!r} has no _geometry(); KiCad export "
              f"supports cascade for now")
        return 1
    g = topo._geometry(spec, params)
    launch = None if args.launch == "none" else LAUNCHES[args.launch]

    outdir = args.out or os.path.join(OUTPUT_DIR, "kicad")
    os.makedirs(outdir, exist_ok=True)
    stem = f"siw_{args.topology}_N{spec.N}"
    pcb = os.path.join(outdir, f"{stem}.kicad_pcb")

    mask = args.soldermask == "full"
    write_kicad_pcb(g, pcb, launch=launch, spec=spec, soldermask=mask)
    done = run_kicad_cli(pcb, outdir)
    write_fab_notes(os.path.join(outdir, "FAB_NOTES.md"), g, spec=spec,
                    soldermask=mask, launch=launch)
    render_drill_map(outdir)
    if done.get("step") == "ok":
        from .config import out_img
        step_path = os.path.join(outdir, "board.step")
        render_3d(step_path, out_img(f"{stem}_3d.png"))
        render_3d(step_path, out_img(f"{stem}_3d_bottom.png"), rx=240, rz=20)
        # The vias-only view exists because the assembled board hides them:
        # from above a plated via reads as a hole in the copper, and the
        # question "does this PCB actually have vias?" is a fair one to ask
        # of a picture that shows 118 dots. It shows the barrels.
        render_3d(step_path, out_img(f"{stem}_3d_vias.png"),
                  rx=292, rz=340, only_vias=True)
    if args.zip:
        zip_for_fab(outdir, os.path.join(outdir, f"{stem}_jlcpcb.zip"))

    if not mask:
        print("\nSoldermask: NONE. F.Mask/B.Mask are not empty -- each holds "
              "one board-sized opening, which is how 'no mask' is expressed "
              "in gerber. An EMPTY mask file would mean mask everywhere.")
    bad = {k: v for k, v in done.items() if v != "ok"}
    return 1 if bad else 0


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
        # --real-metal now works for CASCADE too (the exterior-face split was
        # ported into palace_driven on 2026-09-03). --enig still does not:
        # ENIG/soldermask/silkscreen are meshed layers, unresolvable at this
        # mesh density, and ENIG is in any case shielded behind ~14 skin
        # depths of ground-plane copper. See docs/STATE.md.
        if args.topology == "cascade" and getattr(args, "enig", False):
            print("--enig is not available for cascade (and is an RF no-op: the "
                  "plating sits on the shielded side of the ground plane). Use "
                  "--real-metal."); return 1
        if args.topology not in ("dualmode", "cascade"):
            print("--enig/--real-metal are only wired for dualmode/cascade so far"); return 1
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


def _fab_variant_specs():
    # NOTE: deliberately NO VIA_COVERED / VIA_OPEN here. Those set
    # via_conductivity_sm, which makes every SIW via a volumetric lossy
    # conductor requiring the 1.21 um copper skin depth to be resolved
    # against a 200 um finest cell -- 165x too coarse. The result is
    # enormous spurious loss (measured IL = -28.96 dB where PEC gives
    # -1.45 dB), and since the via fence IS the waveguide wall it destroys
    # the cavity rather than perturbing it. See report.FAB_VARIANTS for the
    # full reasoning, including why tented-vs-open is consequently not
    # answerable at this mesh density.
    # ONE-FACTOR-AT-A-TIME LADDER (2026-09-03). The combined stack returns
    # IL=-29dB / S11w=-0.1dB / 0 zeros where PEC gives -1.45dB, and TWO
    # successive guesses at the cause were both wrong: the via-cap exterior
    # flag (fix changed nothing) and the volumetric via conductor (removing
    # it changed nothing). Guessing a third time is not the method. Each
    # cell below adds exactly ONE ingredient to the PEC baseline, so the
    # culprit is identified by measurement instead of inference.
    from .topologies.dualmode import (JLCPCB_METAL, JLCPCB_ENIG,
                                      JLCPCB_SOLDERMASK, JLCPCB_SILKSCREEN)
    return [
        ("pec_optimized",   {}),
        ("only_cu",         {**JLCPCB_METAL}),       # exterior-plane surface impedance
        ("only_enig",       {**JLCPCB_ENIG}),        # ENIG conductor domain -- UNRESOLVABLE
        ("only_mask",       {**JLCPCB_SOLDERMASK}),  # feed-region dielectric -- UNRESOLVABLE
        ("only_silk",       {**JLCPCB_SILKSCREEN}),  # silkscreen dielectric -- UNRESOLVABLE
        # NO COPPER+ENIG CELL, and the reason is geometric rather than
        # numerical (2026-09-03, user's observation).
        #
        # It is tempting to model the finish as one effective surface
        # impedance for the two-layer stack: 4.5um Ni-P at 2.87GHz is 0.62
        # skin depths, so a wave ARRIVING THROUGH THE PLATING sees
        # Rs = 39.6 mohm/sq against copper's 13.8 -- 2.87x, equivalent to
        # sigma = 7.225e6 S/m. That arithmetic is correct and irrelevant
        # here: it describes the wrong side of the metal.
        #
        # The exterior ground planes are 17.5um of copper, ~14 skin depths.
        # RF current flows on their INNER face, against the substrate. The
        # ENIG is plated on the OUTER face, shielded behind all of that
        # copper, carrying essentially no current. Charging it ENIG loss
        # would attribute dissipation to a surface the field never reaches.
        #
        # ENIG can only matter where a plated surface FACES the field -- the
        # microstrip feed trace and the CPWG ground pads. Those are internal
        # two-sided sheets, where Palace's exterior-only Conductivity BC does
        # not apply, and they are a small fraction of the wall current in any
        # case. So the honest model is: ENIG is an RF no-op for this design.
        # See docs/STATE.md, "what the fabrication stack costs".
    ]


def cmd_compare_fab_variants(args) -> int:
    from .report import build_fab_variant_comparison
    from .config import out_data

    result_json = args.result_json or out_data("four_variants_result.json")
    if getattr(args, "run", False):
        import json as _json
        import numpy as _np
        from .topologies import REGISTRY
        from .optimize import evaluate, pole_shape
        if not args.params:
            print("--run needs --params (the fixed geometry to hold across variants)")
            return 1
        from .config import SPEC, FilterSpec
        topo = REGISTRY[getattr(args, "topology", "dualmode")]
        spec = FilterSpec(f0=SPEC.f0, FBW=SPEC.FBW, N=args.N,
                          ripple_db=SPEC.ripple_db,
                          substrate_name=SPEC.substrate_name,
                          d_via=SPEC.d_via, p_via=SPEC.p_via)
        base = _parse_params(args.params)
        out = _json.load(open(result_json)) if (args.resume and os.path.exists(result_json)) else {}
        out["_geometry"] = base
        print(f"fabrication variants at FIXED geometry {base}")
        specs = _fab_variant_specs()
        if topo.name != "dualmode":
            # The meshed-layer diagnostic cells (only_enig/mask/silk) exist
            # only in the dual-mode mesh builder, and their numbers are
            # meaningless anyway (unresolved slivers). For any other topology
            # the honest study is PEC vs real copper.
            specs = [(k, ov) for k, ov in specs if k in ("pec_optimized", "only_cu")]
        for key, overlay in specs:
            # Resume skips only SUCCEEDED variants. Skipping failed ones too
            # would make --resume permanently entrench a transient failure
            # (the first run lost three variants to an OOM kill, which is a
            # resource limit, not a property of the design).
            if key != "_geometry" and out.get(key, {}).get("ok"):
                print(f"  {key}: already succeeded, skipping (--resume)")
                continue
            P = dict(base, **overlay)
            # Distinct tag per variant: the overlay is mostly non-numeric
            # (material flags), and the mesh tag only encodes numeric params,
            # so without this every variant would collide on one set of files.
            r = evaluate(topo, spec, P, fine=True, tag_prefix=f"fabvar_{key}",
                         device=args.device, np_ranks=args.np)
            if not r.get("ok"):
                print(f"  {key}: FAILED {r.get('err')}")
                out[key] = {"ok": False, "err": str(r.get("err"))}
                _json.dump(out, open(result_json, "w"), indent=2, default=str)
                continue
            sh = pole_shape(_np.array(r["f"]), _np.array(r["s11_db"]), spec.N)
            out[key] = {"ok": True, "params": {k: v for k, v in P.items()},
                        "metrics": {k: v for k, v in r.items()
                                    if k not in ("f", "s11_db", "s21_db", "csv")},
                        "f_ghz": list(r["f"]), "s11_db": list(r["s11_db"]),
                        "s21_db": list(r["s21_db"]), "poles": sh["n_zeros"]}
            m = out[key]["metrics"]
            print(f"  {key}: fc={m.get('fc_3db', m['fc']):.3f}GHz  IL={m['il']:.2f}dB  "
                  f"BW={m['bw']:.0f}MHz  S11w={m['s11w']:.2f}dB  poles={sh['n_zeros']}"
                  f"  lobes={m.get('n_lobes', 1)}")
            # PHYSICS GUARD against the PEC cell. A fabrication stack adds
            # conductor and dielectric loss -- a fraction of a dB. It cannot
            # add tens of dB, and it cannot IMPROVE the match to near-total
            # reflection. Both directions have caught real modelling bugs
            # here: an unassigned material domain once returned LESS loss
            # than lossless metal, and an exterior-only surface-impedance BC
            # applied to internal faces returned IL=-28.96dB with
            # S11w=-0.07dB where PEC gives -1.45dB. Say so loudly rather
            # than letting either land in a comparison table as if it were a
            # fabrication penalty.
            pec_m = (out.get("pec_optimized") or {}).get("metrics")
            if pec_m and key != "pec_optimized":
                d_il = m["il"] - pec_m["il"]
                if d_il > 0.05:
                    print(f"    IMPOSSIBLE: IL {m['il']:.2f}dB BEATS the lossless PEC "
                          f"cell ({pec_m['il']:.2f}dB) by {d_il:.2f}dB. A lossy stack "
                          f"cannot lose less than lossless metal -- this is a modelling "
                          f"bug, not a result.")
                elif d_il < -6.0:
                    print(f"    IMPLAUSIBLE: IL {m['il']:.2f}dB is {-d_il:.1f}dB worse "
                          f"than PEC ({pec_m['il']:.2f}dB). A fabrication stack costs a "
                          f"fraction of a dB; this size of jump means a short/open in "
                          f"the model. Check Boundaries.Conductivity is applied only to "
                          f"true exterior faces.")
                if m["s11w"] > -0.5:
                    print(f"    IMPLAUSIBLE: S11w={m['s11w']:.2f}dB is near-total "
                          f"reflection -- the structure is not behaving as a filter.")
                if sh["n_zeros"] == 0:
                    print(f"    WARNING: 0 reflection zeros (expected {spec.N}).")
            _json.dump(out, open(result_json, "w"), indent=2, default=str)
        print(f"WROTE {result_json}")

    ok = build_fab_variant_comparison(result_json=result_json, f0_ghz=args.f0,
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
    p_cal.add_argument("--cavity", default=None, metavar="JSON",
                       help="cavity geometry for BOTH calibration testbeds, e.g. "
                            "'{\"a_mm\": 57.21, \"x_iris_mm\": 28.68, \"y_wall_mm\": 8.62}'. "
                            "Without it the sweeps use module defaults and measure a "
                            "different resonator than the one being designed")
    p_cal.add_argument("--w-iris", default=None, metavar="LIST",
                       help="comma-separated w_iris values for the k sweep")
    p_cal.add_argument("--w-ext", default=None, metavar="LIST",
                       help="comma-separated w_ext values for the Qe sweep, e.g. "
                            "'19,22,25,28'. Concentrate these where the target Qe "
                            "lives: points whose Q_L approaches Qu are ill-conditioned "
                            "(Qe = 2/(1/Q_L - 1/Qu) subtracts close numbers there)")
    p_cal.add_argument("--qe-window", default=None, metavar="FMIN,FMAX,STEP",
                       help="Qe sweep window in GHz, e.g. '2.40,3.05,0.010'. Size it to "
                            "the -3dB band being measured, not to f0 -- the default "
                            "used to spend ~92%% of its points far from the resonance")
    p_cal.add_argument("--plot-only", action="store_true",
                       help="skip the sweeps: re-render the calibration figure from "
                            "the cached calibration_<topology>_N<N>.json")
    p_cal.add_argument("--invert", action="store_true",
                       help="after measuring, invert the fitted curves for this spec's "
                            "k/Qe targets and report the physical geometry (warns loudly "
                            "if a target falls outside the measured range)")
    p_cal.add_argument("--confirm", action="store_true",
                       help="with --invert: run a driven fine solve on the inverted "
                            "geometry and report fc/IL/BW/S11w and the pole count")
    p_cal.add_argument("--confirm-base", default=None, metavar="JSON",
                       help="JSON dict of the non-inverted geometry parameters to hold "
                            "fixed during --confirm, e.g. '{\"a\": 57.21, \"x_iris\": 28.68}'")
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
    p_des.add_argument("--w-bw", type=float, default=None, metavar="W",
                       help="weight on the bandwidth error term (default 3.0). Use 0 to "
                            "ignore bandwidth entirely and optimise for return loss -- on "
                            "dualmode N=2 the two are in direct opposition, so this is how "
                            "you pick which end of that trade to land on.")
    p_des.add_argument("--w-fc", type=float, default=None, metavar="W",
                       help="weight on the centre-frequency error term (default 0.05)")
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

    p_cst = sub.add_parser("cst",
                           help="generate the CST Studio VBA macro (.bas) for a landed "
                                "design -- real solids, StoreParameter knobs, the real "
                                "Taoglas SMA + CPWG launch and coaxial ports")
    p_cst.add_argument("--topology", default="cascade", choices=_TOPOLOGY_CHOICES)
    p_cst.add_argument("--N", type=int, default=3, help="filter order")
    p_cst.add_argument("--params", required=True, help="geometry, k=v,k=v,... (mm)")
    p_cst.add_argument("--launch", default="cpwg", choices=["cpwg", "pad", "none"],
                       help="cpwg (default) emits the real Taoglas SMA coax stubs, "
                            "coplanar pours, stitching vias and COAXIAL ports -- the "
                            "structure actually simulated. none gives a bare microstrip "
                            "with waveguide ports, which is not.")
    p_cst.add_argument("--sma-len", type=float, default=6.0,
                       help="length of each SMA coax stub [mm]")
    p_cst.add_argument("--out", default=None, help="output .bas path")
    p_cst.set_defaults(func=cmd_cst)

    p_kic = sub.add_parser("kicad",
                           help="generate the KiCad board + the JLCPCB deliverables "
                                "for a landed design: .kicad_pcb, gerbers "
                                "(F.Cu/B.Cu/F.Mask/B.Mask/Edge.Cuts), Excellon "
                                "drill files, STEP, SVG and the fab notes")
    p_kic.add_argument("--topology", default="cascade", choices=_TOPOLOGY_CHOICES)
    p_kic.add_argument("--N", type=int, default=3, help="filter order")
    p_kic.add_argument("--params", required=True, help="geometry, k=v,k=v,... (mm)")
    p_kic.add_argument("--launch", default="cpwg", choices=["cpwg", "pad", "none"],
                       help="launch footprint; cpwg (default) is the structure "
                            "that was actually simulated")
    p_kic.add_argument("--soldermask", default="none", choices=["none", "full"],
                       help="'none' (default, the fabrication decision taken for "
                            "this board) opens the mask over the WHOLE board: "
                            "F.Mask/B.Mask each carry one board-sized opening. "
                            "An empty mask gerber would mean the opposite -- mask "
                            "everywhere. 'full' keeps a normal masked board.")
    p_kic.add_argument("--zip", action="store_true", default=True,
                       help="also write a flat JLCPCB-ready zip (default on)")
    p_kic.add_argument("--no-zip", dest="zip", action="store_false")
    p_kic.add_argument("--out", default=None,
                       help="output directory (default output/kicad)")
    p_kic.set_defaults(func=cmd_kicad)

    p_scn = sub.add_parser("scan",
                           help="1-D parameter scan on the ASSEMBLED filter: measure "
                                "bandwidth / return loss / pole count against one "
                                "geometry parameter, and invert for a target bandwidth")
    p_scn.add_argument("--topology", required=True, choices=_TOPOLOGY_CHOICES)
    _add_spec_args(p_scn)
    p_scn.add_argument("--params", required=True, help="base geometry, k=v,k=v,... (mm)")
    p_scn.add_argument("--scan", required=True, metavar="NAME=V1,V2,...",
                       help="parameter to scan and its values, e.g. 'w_ext=12.5,13.5,14.5'")
    p_scn.add_argument("--launch", default="cpwg", choices=["cpwg", "pad"],
                       help="launch footprint (dualmode only): 'cpwg' (default) is the "
                            "impedance-matched CPWG launch; 'pad' is the archived "
                            "pad-only launch, for comparing launches at a FIXED cavity "
                            "geometry. Results under 'pad' are tagged sma_taoglas, not "
                            "cpwg_taoglas -- do not mix them in one golden entry.")
    p_scn.add_argument("--target-bw", type=float, default=None, metavar="MHZ",
                       help="invert the measured bandwidth curve for this value "
                            "(default: the spec's own FBW*f0)")
    p_scn.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                       help=_DEVICE_HELP)
    p_scn.add_argument("--np", type=int, default=8)
    p_scn.set_defaults(func=cmd_scan)

    # `stackup` is deliberately NOT a CLI subcommand (2026-09-03, user's
    # call: "make the stackup a feature not used in the cli"). The drawing
    # helpers remain in report.py -- build_stackup_view, build_stackup_topview
    # and verify_drawing_matches_mesh / verify_cascade_drawing_matches_mesh --
    # and are called directly when a figure or a drawing-vs-mesh check is
    # actually needed. Removing the subcommand keeps it out of the surface
    # area to explore without losing the capability.


    p_fab = sub.add_parser("compare-fab-variants",
                           help="ONE overlay of every fabrication variant of a design "
                                "(PEC vs copper/ENIG/soldermask/silkscreen/via options) plus "
                                "the ideal Chebyshev target, on shared axes. Reads the "
                                "incremental variant-sweep JSON, so it works while cells are "
                                "still solving; also saves the plotted curves + metrics as JSON.")
    p_fab.add_argument("--result-json", default=None,
                       help="variant sweep results (default: output/data/four_variants_result.json)")
    p_fab.add_argument("--topology", default="dualmode", choices=_TOPOLOGY_CHOICES,
                       help="topology to run the variants on (default dualmode). "
                            "cascade runs PEC vs real copper only.")
    p_fab.add_argument("--run", action="store_true",
                       help="RUN the variants first (dualmode) instead of only plotting a "
                            "previous sweep. Needs --params: the one fixed geometry every "
                            "variant is evaluated at, so any difference is the stack alone.")
    p_fab.add_argument("--params", default=None,
                       help="fixed geometry for --run, k=v,k=v,... (mm)")
    p_fab.add_argument("--resume", action="store_true",
                       help="with --run, keep variants already in the result JSON and only "
                            "solve the missing ones")
    # NOT _add_spec_args here: this parser already owns --f0 in GHz for the
    # plot's FBW shading, while the spec's --f0 is in Hz. Two flags of the
    # same name with different units is exactly the kind of thing that
    # produces a silently wrong figure, so the spec is taken from config
    # defaults with only the order overridable.
    p_fab.add_argument("--N", type=int, default=2, help="filter order (default 2)")
    p_fab.add_argument("--device", default="auto", choices=["auto", "CPU", "GPU"],
                       help=_DEVICE_HELP)
    p_fab.add_argument("--np", type=int, default=8,
                       help="MPI ranks (CPU only; GPU always uses 1)")
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
