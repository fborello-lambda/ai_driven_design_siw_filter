"""Physics-derived cascade design: calibrate -> invert -> assemble.

This replaces black-box search as the PRIMARY design route for the inline
cascade. Written 2026-08-30 after a long session in which a GP search over
the full filter never beat -5 dB S11 in 60+ driven evaluations, while the
calibrate-and-invert route below reached each of its targets in about three
cheap solves apiece.

WHY (all measured this session, not assumed):

  * Calibrations measure a SMOOTH observable on a SMALL structure and they
    converged: k(w_iris) from a 2-cavity eigenmode split landed within 2% of
    the Chebyshev target; the fc correction put N=4 exactly on 2.870 GHz.

  * Sweeps and searches measure a COMPOSITE observable on the WHOLE filter
    and they did not. The passband width is DISCONTINUOUS in w_ext: below a
    coupling threshold only the centre pole clears -3 dB so the measured band
    is a single pole, above it all N poles merge and the band jumps. Measured
    on N=3: 16 / 22 / 36 / 65 / 215 MHz, with the 143.5 MHz target sitting
    inside that jump. Any GP whose objective contains that bandwidth inherits
    the problem, because a GP models smooth functions.

  * The failure signature agreed: the N=3 driven S11 showed three reflection
    zeros (2.809 / 2.869 / 2.989 GHz -- the right pole COUNT, so the topology
    was fine) but unevenly spaced with -6..-11 dB ripple between them instead
    of -16 dB equiripple. That is k and Qe mismatched relative to each other,
    and k was already calibrated and verified.

DESIGN CHAIN
    synthesis        -> k[i], Qe                 (Chebyshev, exact)
    calibrate()      -> k(w_iris)   -> w_iris    (2-cavity eigenmode)
    calibrate_qe()   -> Qe(w_ext)   -> w_ext     (1-cavity driven, loaded Q)
    fc correction    -> l_cav                    (TE101 + iris loading)

Each step inverts a measured curve instead of searching. A GP is then only
worth running as a LOCAL polish around the result -- the regime it already
works in for the dual-mode topology.

Caveats kept in the open:
  * calibrate_qe's Qu is the dielectric limit 1/tan_d (270.3, matching the
    closed-cavity eigenmode), so it ignores conductor, via-leakage and
    radiation loss and slightly OVER-estimates Qe.
  * closed-cavity eigenmodes cannot see the external apertures, so the
    resulting fc is high by ~100 MHz until the driven correction is applied.
"""
from __future__ import annotations

import json
import math

import numpy as np

from .config import C0, FilterSpec, out_data
from .synthesis import synthesize
from .topologies.cascade import CascadeTopology, _len_keys, _iris_keys


def invert_k(cal: dict, k: float) -> float:
    """Physical iris width for a synthesized coupling k, from calibrate()."""
    fit = cal.get("w_of_k")
    if fit is None:
        raise ValueError("k calibration has no w_of_k fit (need >=3 good points)")
    ks = [r["k"] for r in cal["points"].values() if r.get("ok")]
    if ks and not (min(ks) <= k <= max(ks)):
        print(f"  WARNING: k={k:.5f} outside calibrated [{min(ks):.5f},{max(ks):.5f}]"
              " -- extrapolating")
    return float(np.polyval(fit, k))


def invert_qe(cal: dict, qe: float) -> float:
    """Physical w_ext for a synthesized Qe, from calibrate_qe()."""
    fit = cal.get("w_of_logQe")
    if fit is None:
        raise ValueError("Qe calibration has no w_of_logQe fit")
    rng = cal.get("Qe_range")
    if rng and not (rng[0] <= qe <= rng[1]):
        print(f"  WARNING: Qe={qe:.2f} outside calibrated [{rng[0]:.2f},{rng[1]:.2f}]"
              " -- extrapolating")
    return float(np.polyval(fit, math.log(qe)))


def correct_l_cav_to(spec: FilterSpec, fc_meas_ghz: float, l_cav_mm: float,
                     f_target_ghz: float) -> float:
    """Cavity length that moves a measured resonance onto an arbitrary target
    frequency (generalizes correct_l_cav, which always targets spec.f0).

    Backs the EFFECTIVE transverse dimension out of the measured (fc, l_cav)
    pair -- which folds in whatever loading was present -- then re-solves the
    TE101 relation at f_target holding it fixed:

        (1/a_eff)^2 = (2*fc*sqrt(eps_r)/c)^2 - (1/L)^2
        (1/L_new)^2 = (2*f_target*sqrt(eps_r)/c)^2 - (1/a_eff)^2
    """
    eps = spec.substrate.eps_r
    fc, L = fc_meas_ghz * 1e9, l_cav_mm * 1e-3
    inv_a2 = (2 * fc * math.sqrt(eps) / C0) ** 2 - (1.0 / L) ** 2
    rhs = (2 * f_target_ghz * 1e9 * math.sqrt(eps) / C0) ** 2 - inv_a2
    return l_cav_mm if rhs <= 0 else (1.0 / math.sqrt(rhs)) * 1e3


def correct_l_cav(spec: FilterSpec, fc_meas_ghz: float, l_cav_mm: float) -> float:
    """Cavity length that moves a measured resonance onto f0.

    Verified to +8 MHz on the first application; the residual is closed by
    iterating against a DRIVEN solve, since a closed cavity cannot see the
    external apertures (they pull fc down ~100 MHz).
    """
    return correct_l_cav_to(spec, fc_meas_ghz, l_cav_mm, spec.f0 / 1e9)


def design_from_calibration(spec: FilterSpec, k_cal: dict, qe_cal: dict,
                            l_taper_mm: float = 15.73) -> dict:
    """Assemble a cascade design by INVERTING the two calibrations."""
    from .siw_geometry import microstrip_width_50ohm

    syn = synthesize(spec)
    N = spec.N
    ws = [invert_k(k_cal, float(k)) for k in syn.k]
    n_ind = (len(ws) + 1) // 2
    iris_ind = ws[:n_ind]
    w_ext = invert_qe(qe_cal, float(syn.qe_in))

    # Cavity length: start from the k-calibration's own (w_iris, fc) point and
    # correct for the loading it measured. The driven correction that follows
    # is what removes the external-aperture pull.
    pts = [(w, r) for w, r in k_cal["points"].items() if r.get("ok")]
    pts.sort(key=lambda t: float(t[0]))
    wsx = np.array([float(w) for w, _ in pts])
    fcs = np.array([r["fc"] for _, r in pts])
    l_cal = k_cal.get("l_cav_mm", 34.4)
    l_cav = correct_l_cav(spec, float(np.interp(iris_ind[0], wsx, fcs)), l_cal)

    p: dict[str, float] = {
        "w_ext": round(w_ext, 2),
        "l_taper": l_taper_mm,
        "w_ms": round(microstrip_width_50ohm(spec.substrate.eps_r,
                                             spec.substrate.h) * 1e3, 4),
    }
    for key in _len_keys(N):
        p[key] = round(l_cav, 2)
    for key, v in zip(_iris_keys(N), iris_ind):
        p[key] = round(v, 2)
    return {"params": p, "targets": {"k": [float(x) for x in syn.k],
                                     "Qe": float(syn.qe_in)},
            "w_iris_all": [round(x, 2) for x in ws]}


def run_pipeline(spec: FilterSpec, device: str = "auto", np_ranks: int = 4,
                 w_irises: list[float] | None = None,
                 w_exts: list[float] | None = None,
                 cache: bool = True, refine: bool = True,
                 fc_trim: bool = True, mid_trim: bool = True,
                 seed_params: dict | None = None) -> dict:
    """Full physics chain for the cascade topology. Returns the design dict.

    Calibrations are cached per (substrate, vias, f0) so the expensive part is
    paid once and reused across orders -- N=3 and N=4 share both curves,
    differing only in the targets they invert.

    seed_params: skip calibration/invert/refine entirely and start fc_trim/
    mid_trim directly from this params dict. For resuming a known-good
    fc-trimmed point (calibration + refine are fully deterministic given the
    same calibration cache, so redoing them just to re-tune mid_trim's
    parameters wastes real driven-solve time) or for retrying mid_trim alone
    with different tuning.
    """
    topo = CascadeTopology()
    if seed_params is not None:
        d = {"params": dict(seed_params)}
        if fc_trim:
            d["params"] = driven_fc_trim(spec, topo, d["params"], np_ranks=np_ranks)
            print(f"[pipeline] fc-trimmed -> {d['params']}", flush=True)
        if mid_trim and len(_len_keys(spec.N)) >= 2:
            print("[pipeline] middle-cavity correction ...", flush=True)
            d["params"] = correct_middle_cavity(spec, topo, d["params"], np_ranks=np_ranks)
            print(f"[pipeline] middle-trimmed -> {d['params']}", flush=True)
        return d

    key = (f"{spec.substrate_name}_d{spec.d_via*1e3:.2f}_p{spec.p_via*1e3:.2f}"
           f"_f{spec.f0/1e9:.3f}")
    path = out_data("cascade_pipeline_cal.json")
    store = {}
    if cache:
        try:
            store = json.load(open(path))
        except (OSError, ValueError):
            store = {}
    entry = store.get(key, {})

    if "k" not in entry:
        print(f"[pipeline] k(w_iris) calibration for {key} ...", flush=True)
        entry["k"] = topo.calibrate(spec, w_irises=w_irises)
    else:
        print(f"[pipeline] reusing cached k calibration for {key}", flush=True)

    if "qe" not in entry:
        print(f"[pipeline] Qe(w_ext) calibration for {key} ...", flush=True)
        entry["qe"] = topo.calibrate_qe(spec, w_exts=w_exts, device=device,
                                        np_ranks=np_ranks)
    else:
        print(f"[pipeline] reusing cached Qe calibration for {key}", flush=True)

    if cache:
        store[key] = entry
        json.dump(store, open(path, "w"), indent=2,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))

    d = design_from_calibration(spec, entry["k"], entry["qe"])
    print(f"[pipeline] N={spec.N} targets k={[round(x,5) for x in d['targets']['k']]} "
          f"Qe={d['targets']['Qe']:.2f}", flush=True)
    print(f"[pipeline] first pass -> {d['params']}", flush=True)

    if refine:
        # The first pass inverts k at the CALIBRATION's cavity length and then
        # corrects the length for fc -- but those are coupled, so the corrected
        # length invalidates the k it was derived from (measured: k fell 17%
        # when the length moved to fix fc). Refine each independent iris
        # jointly against (k, fc); ~3 cheap eigenmodes apiece.
        print("[pipeline] joint (k, fc) refinement ...", flush=True)
        iris_keys = _iris_keys(spec.N)
        len_keys = _len_keys(spec.N)
        for i, ik in enumerate(iris_keys):
            k_t = float(d["targets"]["k"][i])
            r = refine_joint(spec, topo, k_t, d["params"][ik],
                             d["params"][len_keys[0]])
            status = "converged" if r.get("ok") else f"NOT converged ({r.get('err')})"
            print(f"[pipeline]   {ik}: w_iris {d['params'][ik]} -> {r['w_iris']}, "
                  f"l_cav -> {r['l_cav']}  [{status}]", flush=True)
            d["params"][ik] = r["w_iris"]
            # cavity i sits against iris i; mirrored lengths follow the same
            # index convention as _len_keys
            if i < len(len_keys):
                d["params"][len_keys[i]] = r["l_cav"]
            last_l = r["l_cav"]
        # There are ceil((N-1)/2) irises but ceil(N/2) cavity lengths, so for
        # odd N the loop above leaves the trailing length untouched. Carry the
        # last refined value into it: leaving the stale first-pass number there
        # produced an unintended 0.08mm split (l_cav1=37.59 vs l_cav2=37.51)
        # that no physics asked for. A genuine end-vs-middle difference has to
        # come from the DRIVEN correction, which can see the external
        # apertures a closed-cavity eigenmode cannot.
        for lk in len_keys[len(iris_keys):]:
            d["params"][lk] = last_l
        print(f"[pipeline] refined -> {d['params']}", flush=True)

    if fc_trim:
        # Final stage: centre fc against a DRIVEN solve. Everything above is
        # closed-cavity, which cannot see the external apertures -- measured,
        # the N=3 refined design assembled at 2.727 GHz, 143 MHz low, despite
        # every eigenmode-level target being met.
        d["params"] = driven_fc_trim(spec, topo, d["params"], np_ranks=np_ranks)
        print(f"[pipeline] fc-trimmed -> {d['params']}", flush=True)

    if mid_trim and len(_len_keys(spec.N)) >= 2:
        # fc_trim only ever scales every cavity length by ONE common factor,
        # so it can centre the band but can never separate the middle
        # cavity's length from the ends' -- the physics behind the missing-
        # pole / skewed-zero-spacing failures (see correct_middle_cavity).
        print("[pipeline] middle-cavity correction ...", flush=True)
        d["params"] = correct_middle_cavity(spec, topo, d["params"], np_ranks=np_ranks)
        print(f"[pipeline] middle-trimmed -> {d['params']}", flush=True)
    return d

def refine_joint(spec: FilterSpec, topo, k_target: float, w0: float, L0: float,
                 k_tol_rel: float = 0.03, fc_tol_mhz: float = 15.0,
                 max_it: int = 6, dkdw_seed: float = 0.0103,
                 device: str = "GPU", np_ranks: int = 1) -> dict:
    """Solve (w_iris, l_cav) JOINTLY against (k, fc). Needed because the two
    are COUPLED and sequential one-shot corrections do not converge.

    Measured: inverting k at the calibration's own cavity length gave
    w_iris=13.85 with k on target, but fc 140 MHz high; correcting the length
    to 37.51mm fixed fc to +8 MHz and simultaneously dropped k to 0.0382
    (-17%). Lengthening the cavity weakens the coupling, so the iris has to
    grow to compensate -- a 2x2 root find, not two independent fixes. The
    converged answer for N=3 was w_iris=14.81, l_cav=37.59.

    Each iteration costs ONE closed-cavity eigenmode (the split gives k, its
    mean gives fc), so a full solve is far cheaper than a single driven sweep.
    Damped secant on dk/dw, seeded from the calibration curve's slope.
    """
    import numpy as np

    w, L = w0, L0
    hist = []
    for _ in range(max_it):
        r = topo.calibrate(spec, w_irises=[round(w, 2)],
                           l_cav_mm=round(L, 2))["points"].get(round(w, 2), {})
        if not r.get("ok"):
            return {"ok": False, "err": r.get("err"), "w_iris": round(w, 2),
                    "l_cav": round(L, 2)}
        k, fc = r["k"], r["fc"]
        dk_rel = (k - k_target) / k_target
        dfc_mhz = (fc - spec.f0 / 1e9) * 1000
        hist.append((w, L, k, fc))
        if abs(dk_rel) < k_tol_rel and abs(dfc_mhz) < fc_tol_mhz:
            return {"ok": True, "w_iris": round(w, 2), "l_cav": round(L, 2),
                    "k": k, "fc": fc, "iters": len(hist), "history": hist}
        dkdw = dkdw_seed
        if len(hist) >= 2:
            (w1, _, k1, _), (w2, _, k2, _) = hist[-2], hist[-1]
            if abs(w2 - w1) > 1e-6:
                sl = (k2 - k1) / (w2 - w1)
                if sl > 1e-5:            # keep it physical: k rises with w
                    dkdw = sl
        w_new = float(np.clip(w + (k_target - k) / dkdw, 4.0, 24.0))
        L_new = correct_l_cav(spec, fc, L)
        # damp, so the two coupled updates do not chase each other
        w, L = w + 0.7 * (w_new - w), L + 0.7 * (L_new - L)
    return {"ok": False, "err": "not converged", "w_iris": round(w, 2),
            "l_cav": round(L, 2), "history": hist}


def driven_fc_trim(spec: FilterSpec, topo, params: dict,
                   fc_tol_mhz: float = 10.0, max_it: int = 5,
                   np_ranks: int = 4) -> dict:
    """Centre fc against a DRIVEN solve -- the last stage of the chain.

    The closed-cavity eigenmode the k calibration and joint refinement use
    cannot see the EXTERNAL apertures, and those load the end cavities and
    pull the resonance DOWN. Measured on the N=3 refined design: the assembled
    filter came out at 2.727 GHz, 143 MHz below f0, even though every
    eigenmode-level target was met. So the final trim has to be made against
    the real, fed structure.

    Scales every cavity length by a common factor (f ~ 1/L locally), secant-
    refined once two points exist so the modelling error in that relation
    calibrates itself away.

    fc is measured as the -3 dB BAND CENTRE, not argmax(S21): an N-pole
    passband has N peaks and the argmax HOPS between them, which made an
    earlier version of this loop read -140/-80/+140/-50/-40 MHz -- a 3x swing
    in apparent sensitivity that is not physical. The band centre uses the
    edges and is stable. Sweep step is 5 MHz, since steering on a 10 MHz grid
    while chasing a <10 MHz tolerance is unresolvable by construction.

    Returns the trimmed params; the caller should fine-confirm afterwards.
    """
    from .optimize import (run_driven, band_edges, _mesh_preset,
                           SCREEN_MESH_PRESETS)

    len_keys = _len_keys(spec.N)
    mmax, mmin, hair = SCREEN_MESH_PRESETS.get(topo.name,
                                               _mesh_preset(topo.name, "CPU"))
    f0 = spec.f0 / 1e9
    p = dict(params)
    hist: list[tuple[float, float]] = []
    best_p, best_err = dict(p), None

    for it in range(1, max_it + 1):
        r = run_driven(topo, spec, p, f"fctrim_N{spec.N}_it{it}",
                       f0 - 0.30, f0 + 0.30, 0.005, mmax, mmin, hair,
                       device="CPU", np_ranks=np_ranks)
        if not r.get("ok"):
            print(f"[fc-trim] it{it}: FAILED {r.get('err')}", flush=True)
            break
        e = band_edges(r["f"], r["s21_db"])
        fc = e.get("fc_3db") or float(r["f"][int(np.argmax(r["s21_db"]))])
        d_mhz = (fc - f0) * 1000
        print(f"[fc-trim] it{it}: l_cav={[p[k] for k in len_keys]} -> "
              f"fc={fc:.4f} ({d_mhz:+.1f} MHz)", flush=True)
        # keep the best MEASURED point: a loop that exhausts its budget must
        # not carry forward the next, never-simulated extrapolation
        if best_err is None or abs(d_mhz) < best_err:
            best_p, best_err = dict(p), abs(d_mhz)
        if abs(d_mhz) < fc_tol_mhz:
            print("[fc-trim] centred", flush=True)
            return best_p
        hist.append((p[len_keys[0]], fc))
        factor = fc / f0
        if len(hist) >= 2 and abs(hist[-1][1] - hist[-2][1]) > 1e-6:
            (l1, f1), (l2, f2) = hist[-2], hist[-1]
            dfdl = (f2 - f1) / (l2 - l1)
            if abs(dfdl) > 1e-9:
                factor = (l2 + (f0 - f2) / dfdl) / l2
        factor = float(np.clip(factor, 0.90, 1.10))
        for k in len_keys:
            p[k] = round(p[k] * factor, 2)

    print(f"[fc-trim] best measured: {best_err:.1f} MHz err" if best_err is not None
          else "[fc-trim] no usable measurement", flush=True)
    return best_p


def correct_middle_cavity(spec: FilterSpec, topo, params: dict,
                          spacing_tol_mhz: float = 15.0, max_it: int = 6,
                          np_ranks: int = 4, damping: float = 0.5) -> dict:
    """Separate the middle cavity's length from the end cavities', driven by
    a real fed structure -- physics driven_fc_trim cannot supply, since it
    scales every length by ONE common factor and so can never move the
    middle relative to the ends.

    Root cause: only the two end cavities see the external aperture and get
    pulled by it; the closed-cavity eigenmode calibration has no aperture at
    all and so cannot see this pull, and every stage downstream of it
    (design_from_calibration, refine_joint, driven_fc_trim) inherits
    identical end/middle lengths as a result. Measured failure modes: a
    fully collapsed 2-pole response (end pair pulled together, middle pole
    absent -- the original bug) or, once the real CPWG launch changed the
    external coupling, a 3-zero response with two zeros nearly merged at one
    edge and a shallow, badly-matched centre hump instead of a clean third
    zero -- same defect, different symptom.

    Correction: while the assembled response has N zeros (a real inner zero
    to grab onto), target the midpoint of the OUTER two zeros with the mean
    of the INNER zero(s), using the same TE101 f~1/L relation
    driven_fc_trim's sibling correct_l_cav already uses (correct_l_cav_to),
    applied ONLY to the middle cavity's length key so the ends stay where
    fc-trim put them -- but DAMPED (like refine_joint's 0.7 damping on its
    own coupled correction): a full undamped TE101 jump overshot past the
    target on the first real run (34.93mm, 3 zeros/bad spacing -> 33.94mm,
    collapsed to 2 zeros), because the linearized relation is only a local
    model near the CURRENT operating point, not valid over the whole jump.

    If the zero COUNT changes between two consecutive measurements (crossing
    from a full N-zero response to a collapsed one, or back), the true
    threshold lies between those two lengths -- bisect there instead of
    trusting either point's local linear model, since one of them is by
    construction on the wrong side of a real structural transition.

    Each measurement is kept only if it improves (or reaches) matches_order
    via the same best-measured pattern driven_fc_trim uses, so a run that
    exhausts its budget still returns its best point, not the last one.

    No-op for N<3 (dualmode's N=2 has no middle cavity to separate; a plain
    2-cavity cascade likewise has none).
    """
    from .optimize import run_driven, pole_shape, _mesh_preset, SCREEN_MESH_PRESETS
    import numpy as np

    len_keys = _len_keys(spec.N)
    if len(len_keys) < 2:
        return params
    mid_key = len_keys[1]
    p = dict(params)
    f0 = spec.f0 / 1e9
    mmax, mmin, hair = SCREEN_MESH_PRESETS.get(topo.name, _mesh_preset(topo.name, "CPU"))
    best_p, best_score = dict(p), None
    hist: list[tuple[float, int]] = []          # (L, n_zeros) per iteration

    for it in range(1, max_it + 1):
        r = run_driven(topo, spec, p, f"midtrim_N{spec.N}_it{it}",
                       f0 - 0.30, f0 + 0.30, 0.005, mmax, mmin, hair,
                       device="CPU", np_ranks=np_ranks)
        if not r.get("ok"):
            print(f"[mid-trim] it{it}: FAILED {r.get('err')}", flush=True)
            break
        shape = pole_shape(np.asarray(r["f"]), np.asarray(r["s11_db"]), spec.N)
        zeros = sorted(shape["zeros_ghz"])
        L = p[mid_key]
        print(f"[mid-trim] it{it}: l_cav_mid={L}  "
              f"zeros={[round(z, 4) for z in zeros]} (n={len(zeros)}, want {spec.N}) "
              f"peaks={shape['n_peaks']}", flush=True)

        err_mhz = None
        if len(zeros) >= max(3, spec.N):
            target = 0.5 * (zeros[0] + zeros[-1])
            inner = zeros[1:-1]
            actual = sum(inner) / len(inner)
            err_mhz = (actual - target) * 1000

        score = 0.0 if shape["matches_order"] else (abs(err_mhz) if err_mhz is not None else 1e9)
        if best_score is None or score < best_score:
            best_p, best_score = dict(p), score
        if shape["matches_order"]:
            print("[mid-trim] shape matches order -- done", flush=True)
            return best_p

        hist.append((L, len(zeros)))
        if len(hist) >= 2 and hist[-1][1] != hist[-2][1]:
            # Zero count changed since the last try: the real threshold sits
            # between these two lengths, so bisect there rather than trust
            # a local linear model that a structural transition just broke.
            L_new = 0.5 * (hist[-1][0] + hist[-2][0])
        elif err_mhz is not None and abs(err_mhz) > spacing_tol_mhz:
            L_lin = correct_l_cav_to(spec, actual, L, target)
            L_new = L + damping * (L_lin - L)
        else:
            # No usable spacing signal, and the zero count did NOT change
            # from the previous try (or this is the very first attempt): a
            # probe step that EXPANDS every time the same count recurs,
            # alternating direction from the length where the current streak
            # of that count started. A FIXED-size alternating step gets
            # stuck: measured on N=4, a flat +-1% step cycled 35.75mm <->
            # 36.11mm forever (both give the same collapsed 3-zero count),
            # burning the whole iteration budget without ever reaching a
            # length where the count differs, so bisection could never
            # trigger. Doubling the step on each repeat guarantees the probe
            # eventually lands somewhere with a different count.
            streak = 1
            for (_, n) in reversed(hist[:-1]):
                if n == hist[-1][1]:
                    streak += 1
                else:
                    break
            base_L = hist[-streak][0]
            frac = 0.01 * (2 ** (streak - 1))
            sign = 1.0 if streak % 2 == 1 else -1.0
            L_new = base_L + sign * frac * base_L
        p[mid_key] = round(L_new, 2)

    print(f"[mid-trim] best measured shape score {best_score}" if best_score is not None
          else "[mid-trim] no usable measurement", flush=True)
    return best_p
