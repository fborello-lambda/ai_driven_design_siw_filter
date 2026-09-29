"""The standing design comparison: every landed variant on ONE mesh policy and
ONE frequency sweep, overlaid with the ideal Chebyshev target.

Why this exists as a command rather than a script: the interesting question is
never a single design, it is "how does this new run stack up against what we
already have". Recomputing five references every time you want to place one new
result costs ~1.5h of Palace, so each case's S-parameters are cached on disk
(output/data/comparison/<tag>.npz) and reused until asked to refresh.

Comparability is the whole point, so it is enforced rather than assumed:
  * one frequency grid for every case (SWEEP below),
  * each topology's own validated CPU mesh preset -- NOT one shared mesh, since
    cascade and dualmode have very different DOF needs and forcing a single
    setting would degrade one of them,
  * the ideal lossless Chebyshev for both orders drawn on the same axes.

Mesh caveat: fc is not fully mesh-converged -- measured shifts of 20-27 MHz
between neighbouring mesh densities. Cases here are mutually consistent, so
RELATIVE ranking is sound; absolute fc carries more uncertainty than its
printed precision suggests.

Run:  siw compare                      # cached, instant
      siw compare --refresh            # recompute every reference case
      siw compare --add-run best.json  # place a new design against them
"""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np

from .config import FilterSpec, SPEC, out_data, out_img
from .optimize import _mesh_preset, band_edges, plot_comparison, run_driven
from .topologies import REGISTRY

# One grid for every case: wide enough to show the skirts, fine enough (10 MHz)
# to resolve the in-band ripple that a coarser step aliases over.
SWEEP = (2.60, 3.15, 0.01)

# The landed dual-mode geometry (docs/dualmode_cavity/README.md) and the v2
# cascade (docs/sma_connector/README.md), i.e. the published references.
LANDED_DM = {"a": 57.212, "w_iris": 15.261, "x_iris": 28.678,
             "y_wall": 8.619, "w_ext": 16.311}
CASCADE_V2 = {"l_cav1": 32.81, "l_cav2": 33.86, "w_iris": 13.0,
              "w_ext": 16.5, "l_taper": 15.73, "w_ms": 1.664}
OLD_SMA = {"sma_rin_mm": 0.35, "sma_rout_mm": 1.164, "gnd_stitch": False}
REAL_SMA = {"sma_rin_mm": 0.38, "sma_rout_mm": 1.2639}


def _best_params(topology: str, fallback: dict | None = None) -> dict | None:
    """Best design from the last `siw design --topology <topology>` run,
    preferring the fab-rounded variant (it is what would actually be built,
    and it has confirmed no worse than the unrounded optimum).

    Returns None when that topology has never been optimized, so cases() can
    leave it out rather than silently comparing an un-optimized geometry
    against tuned ones -- which would read as a fair fight and is not.
    """
    p = out_data(f"opt_{topology}_best.json")
    if not os.path.exists(p):
        return dict(fallback) if fallback is not None else None
    d = json.load(open(p))
    got = d.get("fab_tolerance", {}).get("params") or d.get("params")
    if got:
        return dict(got)
    return dict(fallback) if fallback is not None else None


def _retuned_dualmode() -> dict:
    return _best_params("dualmode", LANDED_DM)


#: Alternative cavity shapes, in the order they should appear. Each is included
#: only once optimized (see _best_params). Their numbering continues the five
#: reference cases so the legend reads as one ranked list.
GEOMETRY_CASES = [
    ("corner_cut",     "6. corner-cut cavity, real SMA"),
    ("circular_cross", "7. circular + cross, real SMA"),
    ("rhombic",        "8. rhombic cavity, real SMA"),
]


def cases() -> dict[str, dict]:
    """tag -> case definition. Tags are stable so the cache survives edits."""
    dm, casc = REGISTRY["dualmode"], REGISTRY["cascade"]
    spec2 = FilterSpec(N=2)
    spec3 = FilterSpec(N=3, substrate_name=SPEC.substrate_name)
    retuned = _retuned_dualmode()
    out = {
        "n2_ideal_port": dict(label="1. N=2, no SMA (ideal port)", topo=dm, spec=spec2,
                              params={**retuned, "with_sma": False, "gnd_stitch": False}),
        "n2_old_sma":    dict(label="2. N=2, old SMA (r=0.35)", topo=dm, spec=spec2,
                              params={**LANDED_DM, **OLD_SMA}),
        "n2_real_sma":   dict(label="3. N=2, real SMA (Taoglas)", topo=dm, spec=spec2,
                              params=dict(retuned)),
        "n3_real_sma":   dict(label="4. N=3 cascade, real SMA", topo=casc, spec=spec3,
                              params={**CASCADE_V2, **REAL_SMA}),
        "n3_baseline":   dict(label="5. baseline N=3, old SMA", topo=casc, spec=spec3,
                              params={**CASCADE_V2, "sma_rin_mm": 0.35, "sma_rout_mm": 1.164}),
    }
    # The alternative cavity shapes all carry the real Taoglas SMA by default
    # (GeometryTopology._kw), so they need no extra connector params -- that is
    # what makes them directly comparable to case 3.
    for name, label in GEOMETRY_CASES:
        p = _best_params(name)
        if p is not None:
            out[f"geom_{name}"] = dict(label=label, topo=REGISTRY[name],
                                       spec=spec2, params=p)
    return out


def _cache_path(tag: str) -> str:
    d = out_data("comparison")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{tag}.npz")


def _params_key(params: dict) -> str:
    """Stable fingerprint of the geometry a cached curve belongs to."""
    items = sorted((k, round(v, 6) if isinstance(v, float) else v)
                   for k, v in params.items())
    return hashlib.sha1(repr(items).encode()).hexdigest()[:16]


def load_case(tag: str, params: dict | None = None) -> dict | None:
    """Cached S-params for `tag`, but ONLY if they were computed for these
    same parameters.

    The cache is keyed by tag, and several tags (n2_real_sma, n2_ideal_port)
    take their geometry from whatever the latest `siw design` run produced.
    Re-tuning the dual-mode cavity therefore changes what those tags MEAN
    while leaving the tag itself identical -- so a tag-only cache would
    silently plot the pre-retune curves under the retuned design's label,
    which is exactly the kind of error a comparison figure must not make.
    """
    p = _cache_path(tag)
    if not os.path.exists(p):
        return None
    z = np.load(p)
    if params is not None:
        want = _params_key(params)
        got = str(z["params_key"]) if "params_key" in z else None
        if got != want:
            print(f"  cache for {tag} is stale (geometry changed) -> recomputing",
                  flush=True)
            return None
    return {"ok": True, "f": z["f"], "s11_db": z["s11"], "s21_db": z["s21"]}


def save_case(tag: str, r: dict, params: dict | None = None) -> None:
    np.savez(_cache_path(tag), f=r["f"], s11=r["s11_db"], s21=r["s21_db"],
             params_key=_params_key(params or {}))


def compute_case(tag: str, case: dict, device: str = "auto") -> dict:
    topo, spec = case["topo"], case["spec"]
    mmax, mmin, hair = _mesh_preset(topo.name, "CPU")   # validated mesh per topology
    fmin, fmax, step = SWEEP
    r = run_driven(topo, spec, case["params"], f"cmpq_{tag}", fmin, fmax, step,
                   mmax, mmin, hair, device=device)
    if r.get("ok"):
        save_case(tag, r, case["params"])
    return r


def metrics(r: dict, spec: FilterSpec, topo, params: dict) -> dict:
    f, s11, s21 = r["f"], r["s11_db"], r["s21_db"]
    ip = int(np.argmax(s21))
    band = (f >= spec.f1 / 1e9) & (f <= spec.f2 / 1e9)
    geom = {k: v for k, v in params.items() if isinstance(v, (int, float))}
    # Same interpolated -3dB edges the optimizer scores against, so the table
    # and the objective cannot disagree about a design's bandwidth or centre.
    e = band_edges(f, s21)
    out = {
        "fc_ghz": e["fc_3db"],
        "il_db": float(s21[ip]),
        "bw_mhz": e["bw"],
        "s11_inband_db": float(s11[band].max()) if band.any() else 0.0,
        "board_mm": float(topo.board_length_mm(spec, **geom)),
    }
    # Area is the honest size metric for the "make it smaller" goal -- these
    # geometries differ mainly in WIDTH, which length alone hides. Only the
    # alternative shapes implement it so far.
    area = getattr(topo, "board_area_mm2", None)
    if area is not None:
        out["board_mm2"] = float(area(spec, **geom))
    return out


def run(refresh: bool = False, add_run: str | None = None,
        device: str = "auto", out_name: str = "final_comparison.png") -> dict:
    designs, rows = {}, []
    for tag, case in cases().items():
        r = None if refresh else load_case(tag, case["params"])
        if r is None:
            print(f"computing {case['label']} ...", flush=True)
            r = compute_case(tag, case, device=device)
            if not r.get("ok"):
                print(f"  FAILED: {r.get('err')}", flush=True)
                continue
        designs[case["label"]] = r
        rows.append((case["label"], metrics(r, case["spec"], case["topo"], case["params"])))

    if add_run:
        d = json.load(open(add_run))
        params = d.get("fab_tolerance", {}).get("params") or d["params"]
        topo = REGISTRY[d.get("topology", "dualmode")]
        spec = FilterSpec(N=d.get("N", 2))
        label = d.get("label", f"NEW: {os.path.basename(add_run)}")
        mmax, mmin, hair = _mesh_preset(topo.name, "CPU")
        fmin, fmax, step = SWEEP
        print(f"computing {label} ...", flush=True)
        r = run_driven(topo, spec, params, "cmpq_new", fmin, fmax, step,
                       mmax, mmin, hair, device=device)
        if r.get("ok"):
            designs[label] = r
            rows.append((label, metrics(r, spec, topo, params)))
        else:
            print(f"  FAILED: {r.get('err')}", flush=True)

    if not designs:
        print("no cases available")
        return {}

    plot_comparison(designs, FilterSpec(N=2), out_img(out_name))
    hdr = (f"{'design':<34}{'fc GHz':>9}{'IL dB':>8}{'BW MHz':>8}{'S11 dB':>9}"
           f"{'board mm':>10}{'area cm2':>10}")
    print("\n" + hdr); print("-" * len(hdr))
    for label, m in rows:
        # area is blank for the two reference topologies, which do not
        # implement board_area_mm2 -- printing 0.0 would read as "zero area".
        area = f"{m['board_mm2'] / 100.0:>10.1f}" if "board_mm2" in m else f"{'-':>10}"
        print(f"{label:<34}{m['fc_ghz']:>9.3f}{m['il_db']:>8.2f}{m['bw_mhz']:>8.0f}"
              f"{m['s11_inband_db']:>9.2f}{m['board_mm']:>10.1f}{area}")
    print(f"\ntarget f0 = {SPEC.f0/1e9:.3f} GHz, FBW = {SPEC.FBW*100:.0f}%, "
          f"ripple = {SPEC.ripple_db} dB")
    print("NOTE: fc is not fully mesh-converged (20-27 MHz shifts between mesh "
          "densities);\n      relative ranking is sound, absolute fc is not to 3 decimals.")

    summary = {"sweep_ghz": SWEEP, "rows": [dict(label=l, **m) for l, m in rows]}
    json.dump(summary, open(out_data("final_comparison.json"), "w"), indent=2)
    print(f"Wrote {out_data('final_comparison.json')}")
    return summary


if __name__ == "__main__":
    run()
