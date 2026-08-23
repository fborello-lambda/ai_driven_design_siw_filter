"""Dual-mode topology: N/2 dual-mode square SIW cavities (2 filter poles per
physical cavity, via a TE102/TE201 degenerate-mode pair split by an internal
floating iris row). Thin adapter over ``palace_dualmode_driven.py`` --
see docs/dualmode_cavity/README.md for the physics/validation history.

Only N=2 (a single dual-mode cavity) is wired up here, matching what's
actually been validated -- see HANDOFF.md, "no equivalent gap" note (unlike
cascade.py, palace_dualmode_driven.build_mesh() already takes all geometry
as explicit arguments, no module-global spec dependency to fix).
"""
from __future__ import annotations

import json
import os
import subprocess

import numpy as np

from ..config import FilterSpec, find_palace, out_data
from ..palace_dualmode_driven import build_mesh as _build_mesh, _dims, plot_layout_2d as _plot_layout_2d
from ..palace_dualmode import build_mesh as _build_eig_mesh, A_SIW_MM, D_VIA_MM, P_VIA_MM
from .base import MeshResult, ParamRange

# Winning 1.5/3.0mm design region (docs/dualmode_cavity/README.md) -- centers
# the default search box on what's already validated rather than blind-
# searching the original wide box.
_PARAMS: dict[str, ParamRange] = {
    "a":      (57.21, 55.3, 58.7),
    "w_iris": (15.26, 12.5, 15.9),
    "x_iris": (28.68, 27.0, 30.4),
    "y_wall": (8.62,  7.5, 13.0),
    "w_ext":  (16.31, 14.1, 17.6),
}

# Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA jack -- the real, sourceable part
# this design now targets. Pin radius is the datasheet 0.76mm diameter / 2,
# modelled at its TRUE size: the historical 0.35mm backoff existed only to
# dodge the PEC-misclassification bug since fixed in
# palace_dualmode_driven.build_mesh (see docs/sma_connector/README.md). rout
# follows the same Z0=50ohm PTFE coax relation as before (rout/rin = 3.326).
# gnd_stitch models the connector's 4 discrete ground legs at +-2.62mm and the
# top-side pour they solder to, rather than the idealised continuous ring.
TAOGLAS_SMA: dict[str, float | bool | int] = {
    "sma_rin_mm": 0.38,
    "sma_rout_mm": 1.2639,
    "sma_eps_r": 2.08,
    "sma_tand": 4.0e-4,
    "gnd_stitch": True,
    "n_gnd_stitch": 2,
    "gnd_stitch_offset_mm": 2.62,
}


class DualModeTopology:
    name = "dualmode"
    poles_per_cavity = 2

    def param_space(self, spec: FilterSpec) -> dict[str, ParamRange]:
        return dict(_PARAMS)

    def build_mesh(self, spec: FilterSpec, out_name: str, **params) -> MeshResult:
        p = dict(params)
        a = p.pop("a", A_SIW_MM)
        w_iris = p.pop("w_iris")
        x_iris = p.pop("x_iris", None)
        y_wall = p.pop("y_wall", 3.0)
        w_ext = p.pop("w_ext", None)
        p.setdefault("with_sma", True)
        for k, v in TAOGLAS_SMA.items():   # caller can still override any of these
            p.setdefault(k, v)
        res = _build_mesh(a_mm=a, w_iris_mm=w_iris, x_iris_mm=x_iris, y_wall_mm=y_wall,
                          w_ext_mm=w_ext, out_name=out_name, **p)
        if "mesh" not in res:
            # render_png=/preview= short-circuit before a real mesh is built
            # (see palace_dualmode_driven.build_mesh) -- nothing to translate.
            return res  # type: ignore[return-value]
        return {"mesh_path": res["mesh"], "ports": res["ports"], "tets": res["tets"],
                "nodes": res["nodes"], "sma": res.get("sma"),
                "eps_r": res.get("eps_r", spec.substrate.eps_r),
                "tand": res.get("tand", spec.substrate.tan_d)}

    def plot_layout_2d(self, spec: FilterSpec, path: str, **params) -> str:
        p = dict(params)
        a = p.pop("a", A_SIW_MM)
        w_iris = p.pop("w_iris")
        x_iris = p.pop("x_iris", None)
        y_wall = p.pop("y_wall", 3.0)
        w_ext = p.pop("w_ext", None)
        p.pop("with_sma", None)
        return _plot_layout_2d(a_mm=a, w_iris_mm=w_iris, x_iris_mm=x_iris,
                               y_wall_mm=y_wall, w_ext_mm=w_ext, path=path, **p)

    def board_length_mm(self, spec: FilterSpec, **params) -> float:
        a = params.get("a", A_SIW_MM)
        w_ms = params.get("w_ms")
        l_taper = params.get("l_taper")
        l_feed = params.get("l_feed")
        W, Lt, Lf = _dims(a, w_ms, l_taper, l_feed)
        return a + 2 * (Lt + Lf)

    def calibrate(self, spec: FilterSpec, w_irises: list[float] | None = None,
                 x_iris_mm: float | None = None, y_wall_mm: float = 6.0,
                 a_mm: float = A_SIW_MM, mesh_max: float = 1.5, mesh_min: float = 0.4,
                 n_modes: int = 6, window: float = 0.5, device: str = "GPU") -> dict:
        """Cheap closed-cavity eigenmode k12(w_iris) sweep, folded in from
        scripts/dualmode_calibrate_v2.py per HANDOFF.md's cleanup plan.

        Runs each point at GPU/np=1 by default -- a single-rank eigenmode
        solve on this small a closed-cavity mesh fits comfortably in a 6GB
        card (verified: ~1.2GB peak, see the CLI-consolidation session's
        GPU-verification note), unlike the driven+SMA solves used by
        build_mesh(), which need multi-rank CPU domain decomposition.
        """
        x_iris = x_iris_mm if x_iris_mm is not None else a_mm / 2.0
        w_irises = w_irises if w_irises is not None else [5.0, 7.0, 9.0, 11.0, 13.0, 16.0]
        results: dict[float, dict] = {}
        for w in w_irises:
            tag = f"dmcal_wi{w:.2f}_xi{x_iris:.1f}_yw{y_wall_mm:.1f}"
            mesh = tag + ".msh"
            _build_eig_mesh(a_mm=a_mm, w_iris_mm=w, x_iris_mm=x_iris, y_wall_mm=y_wall_mm,
                            mesh_max=mesh_max, mesh_min=mesh_min, out_name=mesh, show_stats=False)
            cfg = {
                "Problem": {"Type": "Eigenmode", "Verbose": 1, "Output": f"postpro/{tag}"},
                "Model": {"Mesh": mesh, "L0": 1.0e-3},
                "Domains": {"Materials": [
                    {"Attributes": [1], "Permeability": 1.0,
                     "Permittivity": spec.substrate.eps_r, "LossTan": spec.substrate.tan_d}]},
                "Boundaries": {"PEC": {"Attributes": [2]}},
                "Solver": {"Device": device,
                           "Eigenmode": {"N": n_modes, "Save": 0,
                                        "Target": spec.f0 / 1e9 - window,
                                        "TargetUpper": spec.f0 / 1e9 + window,
                                        "Tol": 1e-8, "Type": "SLEPc"}},
            }
            cfgp = out_data(f"{tag}.json")
            json.dump(cfg, open(cfgp, "w"), indent=2)
            palace = find_palace()
            env = dict(os.environ, PATH=f"{os.path.dirname(palace)}:{os.environ['PATH']}")
            logp = out_data(f"{tag}.log")
            # GPU here means -np 1 (single MPI rank): each rank opens its own
            # CUDA context, and a 6GB card OOMs at -np 4 even on mesh sizes
            # this small (verified during CLI-consolidation env setup) --
            # unlike the driven+SMA solves, this closed-cavity eigenmode mesh
            # is cheap enough that a single GPU rank still beats CPU/np=4.
            np_ranks = "1" if device == "GPU" else "4"
            subprocess.run([palace, "-np", np_ranks, os.path.basename(cfgp)],
                           cwd=out_data(""), env=env, stdout=open(logp, "w"),
                           stderr=subprocess.STDOUT, check=False)
            csv = out_data(f"postpro/{tag}/eig.csv")
            if not os.path.exists(csv):
                results[w] = {"ok": False}
                continue
            d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
            freqs = np.sort(np.atleast_1d(d[d.dtype.names[1]]))
            if len(freqs) < 2:
                results[w] = {"ok": False, "freqs": freqs.tolist()}
                continue
            gaps = np.diff(freqs)
            i = int(np.argmin(gaps))
            f1, f2 = float(freqs[i]), float(freqs[i + 1])
            k = abs(f2**2 - f1**2) / (f2**2 + f1**2)
            results[w] = {"ok": True, "f1": f1, "f2": f2, "k": k, "fc": (f1 + f2) / 2.0}
        ok = [(w, r["k"]) for w, r in results.items() if r.get("ok")]
        fit = None
        if len(ok) >= 3:
            ws, ks = zip(*ok)
            fit = np.polyfit(ks, ws, 2).tolist()   # w(k), same convention as calibrate.py
        return {"points": results, "w_of_k": fit,
                "x_iris_mm": x_iris, "y_wall_mm": y_wall_mm, "a_mm": a_mm}
