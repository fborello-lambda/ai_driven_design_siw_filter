"""Cascade topology: N single-mode SIW TE101 cavities in a row (the
project's original design). Thin adapter over ``palace_driven.py`` --
no mesh-construction logic is duplicated here.

Per-cavity lengths: for N>3 cavities, ``ceil(N/2)`` independent length
parameters are generated and mirrored into the ``l_cavs_mm`` list
``palace_driven.build_mesh()`` already accepts (mirror-symmetric structure,
the standard assumption for a symmetric bandpass response).
"""
from __future__ import annotations

import math

from ..config import FilterSpec
from ..palace_driven import build_mesh as _build_mesh
from ..siw_geometry import build_geometry, _build_primitives, microstrip_width_50ohm
from ..layout_plot import plot_layout
from .base import MeshResult, ParamRange

# Calibrated for the N=3 default (see palace_opt_sma.py); reused per-cavity
# for other N since no per-N calibration exists yet -- a reasonable first
# cut, not a claim of optimality for N!=3.
_L_INIT, _L_LO, _L_HI = 34.4, 30.0, 40.0
# 2026-08-29 (v18): coupling lower bounds extended downward for the same
# reason as dualmode's (see its _PARAMS comment) -- a narrower passband needs
# WEAKER coupling, and the old floors (w_iris 8.0, w_ext 12.0) were set for a
# wide-band design. N=3 targets k12=k23~0.046/Qe~20.6 and N=4 k12=k34~0.0415,
# k23~0.0329/Qe~22.2, all weaker than the N=2 case, so the inline cascades
# need at least as much headroom below.
_W_IRIS = (13.0, 4.0, 15.9)
_W_EXT = (16.5, 7.0, 26.0)
_L_TAPER = (15.73, 8.0, 26.0)

# CPWG launch, matched 50-ohm (docs/TUNING_PLAN_2026-08-29.md sec 2, solved
# not guessed): signal 1.2mm, coplanar gap 0.2512mm, ground inner edge
# 0.8512mm -> 50.00 ohm (cpwg_gap_50ohm, Wadell/Simons conformal mapping).
# Ground pads 0.851->3.6mm, 5mm deep; 6 stitch vias/side at +-2.62mm, fully
# inside the copper. Real, sourceable part: Taoglas EMPCB.SMAFSTJ.B.HT.
#
# 2026-08-31: this was solved and verified in August but never actually
# turned on as a default anywhere -- cascade only had a bare SMA coax stub
# (with_sma, no ground plane at all near the launch), and even dualmode's own
# TAOGLAS_SMA only enabled pad-only ground stitching (cpwg_gap_mm=None),
# not the impedance-matched gap. This is the first place either topology
# actually uses the solved CPWG numbers by default.
TAOGLAS_SMA: dict[str, float | bool | int] = {
    "sma_rin_mm": 0.38,
    "sma_rout_mm": 1.2639,
    "sma_eps_r": 2.08,
    "sma_tand": 4.0e-4,
    "gnd_stitch": True,
    "n_gnd_stitch": 6,
    "gnd_stitch_offset_mm": 2.62,
    "cpwg_gap_mm": 0.2512,
    "cpwg_y_gnd_mm": 0.8512,
    "cpwg_y_out_mm": 3.6,
    "cpwg_w_feed_mm": 1.2,
}


def _n_len_params(N: int) -> int:
    return math.ceil(N / 2)


def _mirror(values: list[float], N: int) -> list[float]:
    """values[i] for cavity i, mirrored about the center (values has
    ceil(N/2) entries; cavity i uses values[min(i, N-1-i)])."""
    return [values[min(i, N - 1 - i)] for i in range(N)]


def _len_keys(N: int) -> list[str]:
    return [f"l_cav{i + 1}" for i in range(_n_len_params(N))]


def _n_iris_params(N: int) -> int:
    """Independent iris widths for an N-cavity inline cascade.

    There are N-1 internal irises, mirror-symmetric about the centre, so
    ceil((N-1)/2) of them are independent -- the same counting `_n_len_params`
    does for cavity lengths.

    2026-08-30: this used to be hard-coded to ONE shared width for every
    iris, which silently made the N=4 Chebyshev spec unrealizable. N=4 needs
    k = [0.0415, 0.0329, 0.0415]: the middle coupling is 26% WEAKER than the
    outer two, and identical irises can only produce k12 = k23 = k34. The
    N=4 search could therefore never satisfy its own target no matter how
    many evaluations it spent -- a missing degree of freedom, not a search
    failure. (N=3 is unaffected: its k = [0.046, 0.046] really are equal, so
    ceil(2/2) = 1 reproduces the old single-width behaviour exactly.)
    """
    return math.ceil((N - 1) / 2)


def _iris_keys(N: int) -> list[str]:
    """Iris parameter names. N<=3 keeps the historical single "w_iris" name so
    existing configs, logs, warm-starts and cached results keep working
    unchanged; N>=4 splits into w_iris1..w_irisM."""
    m = _n_iris_params(N)
    if m <= 1:
        return ["w_iris"]
    return [f"w_iris{i + 1}" for i in range(m)]


class CascadeTopology:
    name = "cascade"
    poles_per_cavity = 1

    def param_space(self, spec: FilterSpec) -> dict[str, ParamRange]:
        space: dict[str, ParamRange] = {
            k: (_L_INIT, _L_LO, _L_HI) for k in _len_keys(spec.N)
        }
        w_ms0 = round(microstrip_width_50ohm(spec.substrate.eps_r, spec.substrate.h) * 1e3, 4)
        # One entry per INDEPENDENT iris (see _n_iris_params): for N>=4 the
        # inner coupling must be realizable separately from the outer ones.
        space.update({k: _W_IRIS for k in _iris_keys(spec.N)})
        space.update({
            "w_ext": _W_EXT,
            "l_taper": _L_TAPER,
            # NOT searched by the optimizer by convention (see palace_opt_sma.py:
            # fixing W_ms avoids resurrecting the self-normalizing-port artifact
            # where a wrong-impedance trace "looks" better matched) -- included
            # here so callers/CLI can still see+override it explicitly.
            "w_ms": (w_ms0, w_ms0, w_ms0),
        })
        return space

    def _l_cavs_mm(self, spec: FilterSpec, params: dict) -> list[float]:
        keys = _len_keys(spec.N)
        values = [params[k] for k in keys]
        return _mirror(values, spec.N)

    def _iris_widths_mm(self, spec: FilterSpec, params: dict) -> list[float] | None:
        """The N-1 internal iris widths, mirrored from the independent ones.
        Returns None if the caller supplied no iris parameter at all (keeps
        build_geometry's own analytical widths, as before)."""
        n_iris = spec.N - 1
        if n_iris <= 0:
            # A SINGLE cavity has no internal irises. N=1 is a legitimate
            # configuration -- it is the resonator the Qe(w_ext) calibration
            # measures -- and _iris_keys() still reports "w_iris" for it, so
            # without this the caller passes one width for zero irises and
            # build_mesh's length guard rejects the mesh.
            return None
        keys = _iris_keys(spec.N)
        values = [params[k] for k in keys if params.get(k) is not None]
        if not values:
            return None
        # _mirror indexes with min(i, n-1-i), which is exactly the symmetric
        # pairing the iris row needs too (iris i and iris n_iris-1-i share a
        # width), so reuse it rather than repeating the index arithmetic.
        return _mirror(values, n_iris)

    def build_mesh(self, spec: FilterSpec, out_name: str, **params) -> MeshResult:
        p = dict(params)
        l_cavs_mm = self._l_cavs_mm(spec, p)
        iris_widths_mm = self._iris_widths_mm(spec, p)
        for k in _len_keys(spec.N):
            p.pop(k, None)
        for k in _iris_keys(spec.N):
            p.pop(k, None)
        w_ext = p.pop("w_ext", None)
        l_taper = p.pop("l_taper", None)
        w_ms = p.pop("w_ms", None)
        p.setdefault("with_sma", True)  # real connector by default (see HANDOFF)
        for k, v in TAOGLAS_SMA.items():   # caller can still override any of these
            p.setdefault(k, v)
        res = _build_mesh(spec=spec, out_name=out_name, l_cavs_mm=l_cavs_mm,
                          w_irises_mm=iris_widths_mm, w_ext_mm=w_ext,
                          l_taper_mm=l_taper, w_ms_mm=w_ms, **p)
        if "mesh" not in res:
            # render_png=/preview= short-circuit before a real mesh is built
            # (see palace_driven.build_mesh) -- nothing to translate.
            return res  # type: ignore[return-value]
        return {"mesh_path": res["mesh"], "ports": res["ports"], "tets": res["tets"],
                "nodes": res["nodes"], "sma": res.get("sma"),
                "eps_r": spec.substrate.eps_r, "tand": spec.substrate.tan_d}

    def _geometry(self, spec: FilterSpec, params: dict):
        g = build_geometry(spec)
        l_cavs_mm = self._l_cavs_mm(spec, params)
        g.L_cavs = [v * 1e-3 for v in l_cavs_mm]
        iris_widths_mm = self._iris_widths_mm(spec, params)
        if iris_widths_mm is not None:
            g.iris_widths = [v * 1e-3 for v in iris_widths_mm]
        if params.get("w_ext") is not None:
            g.w_ext = params["w_ext"] * 1e-3
        if params.get("l_taper") is not None:
            g.L_taper = params["l_taper"] * 1e-3
        if params.get("w_ms") is not None:
            g.W_ms = params["w_ms"] * 1e-3
        _build_primitives(g)
        return g

    def plot_layout_2d(self, spec: FilterSpec, path: str, **params) -> str:
        g = self._geometry(spec, params)
        plot_layout(g, path, launch=TAOGLAS_SMA)
        return path

    def board_length_mm(self, spec: FilterSpec, **params) -> float:
        g = self._geometry(spec, params)
        xmin, xmax, _, _ = g.board
        return (xmax - xmin) * 1e3

    def calibrate(self, spec: FilterSpec, w_irises: list[float] | None = None,
                  l_cav_mm: float | None = None,
                  mesh_max: float = 2.0, mesh_min: float = 0.35,
                  n_modes: int = 6, window: float = 0.6,
                  device: str = "GPU", np_ranks: int = 1) -> dict | None:
        """EM k(w_iris) calibration for the inline cascade -- CLAUDE.md sec.6.

        Two identical closed SIW cavities sharing one iris split into an
        even/odd pair; the internal coupling follows from the split:

            k = (f2^2 - f1^2) / (f2^2 + f1^2)

        Sweeping w_iris and fitting w(k) inverts the relation, so a synthesized
        k can be turned straight into a physical iris width instead of being
        hunted for by a driven-solve search.

        This existed for dualmode but was a `return None` stub here, which is
        the direct cause of the cascade searches failing: with no calibrated
        design region, the box stayed centred on `_L_INIT = 34.4` (documented
        in docs/sma_connector/README.md as the "old (mismatch-blind)" design
        that measures -4.6 dB against a real connector), and the GP was left
        doing blind global search in 5-6D. Measured screen-out rates tell the
        story: dualmode 34-37% (19 informative points, converges) versus
        cascade 57-83% (2-9 informative points, cannot).

        Closed-cavity eigenmode solves are far cheaper than the driven+SMA
        sweeps the search uses, so a ~6-point sweep costs a fraction of one
        30-eval search.

        Runs on GPU at np_ranks=1 by default (same configuration dualmode's
        calibrate() uses): this mesh is just two dielectric cavities -- no SMA
        stub, no air box, no taper -- so it fits a 6GB card comfortably, while
        >1 rank would OOM because each MPI rank opens its own CUDA context.
        Falls back to CPU per point if the GPU solve produces no eigenvalues,
        so a card that cannot take a particular mesh costs one retry rather
        than a hole in the sweep.
        """
        import json
        import os
        import shutil
        import subprocess

        import numpy as np

        from ..config import find_palace, out_data
        from ..optimize import GPU_ENV, has_gpu
        from ..palace_geometry import build_mesh as _build_2cav
        from ..siw_geometry import build_geometry

        if device == "GPU" and not has_gpu():
            device = "CPU"
        if device == "GPU" and np_ranks != 1:
            # One CUDA context per rank; >1 rank OOMs a single card.
            np_ranks = 1

        g = build_geometry(spec)
        l_cav = l_cav_mm if l_cav_mm is not None else g.L_cav * 1e3
        # Span the synthesized k for N=3..4 with margin on both sides; the fit
        # is only trusted by calibrated_iris_width() INSIDE the swept range.
        w_irises = w_irises if w_irises is not None else [6.0, 9.0, 12.0, 15.0, 18.0, 21.0]

        results: dict[float, dict] = {}
        palace = find_palace()
        for w in w_irises:
            tag = f"cascal_wi{w:.2f}_L{l_cav:.2f}"
            mesh = tag + ".msh"
            try:
                _build_2cav(iris_mm=w, mesh_max=mesh_max, mesh_min=mesh_min,
                            show_stats=False, spec=spec, l_cav_mm=l_cav,
                            out_name=mesh)
            except Exception as e:
                results[w] = {"ok": False, "err": f"mesh:{e}"}
                continue
            def _solve(dev: str, ranks: int) -> str | None:
                cfg = {
                    "Problem": {"Type": "Eigenmode", "Verbose": 1,
                                "Output": f"postpro/{tag}"},
                    "Model": {"Mesh": mesh, "L0": 1.0e-3},
                    "Domains": {"Materials": [
                        {"Attributes": [1], "Permeability": 1.0,
                         "Permittivity": spec.substrate.eps_r,
                         "LossTan": spec.substrate.tan_d}]},
                    "Boundaries": {"PEC": {"Attributes": [2]}},
                    "Solver": {"Device": dev,
                               "Eigenmode": {"N": n_modes, "Save": 0,
                                             "Target": spec.f0 / 1e9 - window,
                                             "TargetUpper": spec.f0 / 1e9 + window,
                                             "Tol": 1e-8, "Type": "SLEPc"}},
                }
                cfgp = out_data(f"{tag}.json")
                json.dump(cfg, open(cfgp, "w"), indent=2)
                env = dict(os.environ,
                           PATH=f"{os.path.dirname(palace)}:{os.environ['PATH']}")
                if dev == "GPU":
                    # Disables MFEM's pooled device allocator, whose fixed
                    # ~4GiB request alone exhausts a 6GB card (see GPU_ENV).
                    env.update(GPU_ENV)
                logp = out_data(f"{tag}.log")
                # A stale eig.csv from a previous attempt would read as success.
                shutil.rmtree(out_data(f"postpro/{tag}"), ignore_errors=True)
                subprocess.run([palace, "-np", str(ranks), os.path.basename(cfgp)],
                               cwd=out_data(""), env=env, stdout=open(logp, "w"),
                               stderr=subprocess.STDOUT, check=False)
                csvp = out_data(f"postpro/{tag}/eig.csv")
                if not os.path.exists(csvp):
                    return None
                d = np.genfromtxt(csvp, delimiter=",", names=True,
                                  deletechars="", replace_space="")
                return np.sort(np.atleast_1d(d[d.dtype.names[1]]))

            freqs = _solve(device, np_ranks)
            # A TRUNCATED result counts as failure, not just a missing file:
            # on a 6GB card this mesh converges all N eigenvalues and then
            # OOMs in postprocessing (cudaMalloc failed), leaving a
            # valid-looking eig.csv with a single row. Silently accepting that
            # would drop the split pair and poison the fit.
            if (freqs is None or len(freqs) < 2) and device == "GPU":
                print(f"[{tag}] GPU eigenmode gave "
                      f"{0 if freqs is None else len(freqs)} mode(s) "
                      f"(needs >=2) -> retrying on CPU", flush=True)
                freqs = _solve("CPU", 4)
            if freqs is None or len(freqs) < 2:
                results[w] = {"ok": False,
                              "freqs": [] if freqs is None else freqs.tolist(),
                              "err": f"<2 modes (see {out_data(f'{tag}.log')})"}
                continue
            # Select the even/odd pair by PROXIMITY TO f0, not by smallest
            # gap. Palace returns N converged eigenvalues near the target
            # without hard-clipping them to [Target, TargetUpper], so the list
            # also carries higher-order modes -- and those cluster far more
            # tightly than the split pair we want. Measured at w_iris=13mm:
            #   2.9026  3.0770 | 4.6021 4.6492 4.6621 | 5.0653
            #   gaps:   0.174    1.525  0.047  0.013    0.403
            # A smallest-gap rule picks the 0.013 GHz pair at ~4.65 GHz (a
            # higher-order family) instead of the real TE101 pair at
            # 2.90/3.08, silently producing a meaningless k. Restrict to the
            # requested window around f0 first, then take the two lowest --
            # the fundamental's even/odd split.
            f0_ghz = spec.f0 / 1e9
            in_win = freqs[np.abs(freqs - f0_ghz) <= window]
            if len(in_win) < 2:
                results[w] = {"ok": False, "freqs": freqs.tolist(),
                              "err": f"<2 modes within +-{window} GHz of f0"}
                continue
            f1, f2 = float(in_win[0]), float(in_win[1])
            k = abs(f2**2 - f1**2) / (f2**2 + f1**2)
            results[w] = {"ok": True, "f1": f1, "f2": f2, "k": k,
                          "fc": (f1 + f2) / 2.0}
            try:
                os.remove(out_data(mesh))
            except OSError:
                pass

        ok = [(w, r["k"]) for w, r in results.items() if r.get("ok")]
        fit = k_fit = None
        if len(ok) >= 3:
            ws, ks = zip(*ok)
            fit = np.polyfit(ks, ws, 2).tolist()     # w(k), same convention as calibrate.py
            k_fit = np.polyfit(ws, ks, 3).tolist()   # k(w), for reporting/plots
        return {"points": results, "w_of_k": fit, "k_of_w": k_fit,
                "l_cav_mm": l_cav, "a_siw_mm": g.a_siw * 1e3,
                "d_via_mm": spec.d_via * 1e3, "p_via_mm": spec.p_via * 1e3}

    def calibrate_qe(self, spec: FilterSpec, w_exts: list[float] | None = None,
                     l_cav_mm: float = 34.46, device: str = "auto",
                     np_ranks: int = 4) -> dict:
        """EM Qe(w_ext) external-coupling calibration -- CLAUDE.md sec.6.

        The counterpart to calibrate()'s k(w_iris). A SINGLE driven cavity
        (N=1: two feeds, no internal iris) is a symmetric doubly-loaded
        resonator, so its -3 dB bandwidth gives the loaded Q and

            1/Q_L = 1/Qu + 2/Qe    ->    Qe = 2 / (1/Q_L - 1/Qu)

        WHY A SINGLE RESONATOR AND NOT A w_ext SWEEP ON THE WHOLE FILTER:
        the assembled filter's passband width is DISCONTINUOUS in w_ext --
        below a coupling threshold only the centre pole clears -3 dB so the
        measured band is one pole, above it all N poles merge and the band
        leaps. Measured on the N=3 cascade: 16 / 22 / 36 / 65 / 215 MHz, with
        the 143.5 MHz target falling inside the jump. A GP objective
        containing that bandwidth has the same problem, since GPs model
        smooth functions. One resonator has no poles to merge, so its loaded
        Q is smooth and monotonic in w_ext.

        Qu is taken as the dielectric limit 1/tan_d, which the closed-cavity
        eigenmode independently measured (Q=270.3 vs 1/0.0037=270.3). It
        therefore ignores conductor, via-leakage and radiation loss, so the
        returned Qe is a slight OVER-estimate of a real board's.

        Returns {points, w_of_logQe, Qu, ...}; w_of_logQe inverts a target Qe
        to a physical w_ext via numpy.polyval(fit, log(Qe)).
        """
        import numpy as np

        from ..config import FilterSpec as _FS
        from ..optimize import run_driven, band_edges, _mesh_preset

        spec1 = _FS(N=1, f0=spec.f0, FBW=spec.FBW, ripple_db=spec.ripple_db,
                    substrate_name=spec.substrate_name,
                    d_via=spec.d_via, p_via=spec.p_via, fc_ratio=spec.fc_ratio)
        qu = 1.0 / spec1.substrate.tan_d
        w_exts = w_exts if w_exts is not None else [8.0, 10.0, 12.0, 14.0,
                                                    16.0, 18.0, 20.0, 22.0]
        mmax, mmin, hair = _mesh_preset(self.name, "CPU")
        f0 = spec1.f0 / 1e9

        points: dict[float, dict] = {}
        for we in w_exts:
            p = dict(l_cav1=l_cav_mm, w_ext=we, l_taper=15.73,
                     w_ms=round(microstrip_width_50ohm(spec1.substrate.eps_r,
                                                       spec1.substrate.h) * 1e3, 4))
            r = run_driven(self, spec1, p, f"qecal_we{we:.1f}",
                           f0 - 0.6, f0 + 0.6, 0.005, mmax, mmin, hair,
                           device=device, np_ranks=np_ranks)
            if not r.get("ok"):
                points[we] = {"ok": False, "err": r.get("err")}
                continue
            e = band_edges(r["f"], r["s21_db"])
            bw = float(e.get("bw", 0.0))                     # MHz
            fc = e.get("fc_3db") or float(r["f"][int(np.argmax(r["s21_db"]))])
            if bw <= 0:
                points[we] = {"ok": False, "err": "no -3dB band"}
                continue
            q_l = (fc * 1000.0) / bw
            inv = 1.0 / q_l - 1.0 / qu
            points[we] = {"ok": True, "fc": fc, "bw": bw, "Q_L": q_l,
                          "Qe": (2.0 / inv) if inv > 0 else float("inf"),
                          "il": float(r["s21_db"].max())}

        ok = [(w, m["Qe"]) for w, m in points.items()
              if m.get("ok") and np.isfinite(m["Qe"])]
        fit = None
        if len(ok) >= 3:
            ws = np.array([w for w, _ in ok])
            qs = np.array([q for _, q in ok])
            # Qe falls steeply as the aperture opens; fit in log(Qe) for a
            # well-conditioned inverse.
            fit = np.polyfit(np.log(qs), ws, 2).tolist()
        return {"points": points, "w_of_logQe": fit, "Qu": qu,
                "l_cav_mm": l_cav_mm,
                "Qe_range": [float(min(q for _, q in ok)),
                             float(max(q for _, q in ok))] if ok else None}
