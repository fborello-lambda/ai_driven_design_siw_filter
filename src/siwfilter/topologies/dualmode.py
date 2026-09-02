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
# THE launch -- one definition for the whole project (see launch.py).
from .launch import TAOGLAS_CPWG as TAOGLAS_SMA

# Winning 1.5/3.0mm design region (docs/dualmode_cavity/README.md) -- centers
# the default search box on what's already validated rather than blind-
# searching the original wide box.
_PARAMS: dict[str, ParamRange] = {
    "a":      (57.21, 55.3, 58.7),
    # 2026-08-29 (v18): lower bounds on the two COUPLING widths extended well
    # below the landed design. The old box was centred on the wide-bandwidth
    # optimum (landed w_iris=15.26 sat just under its own 15.9 ceiling), so a
    # search for a NARROWER passband could not physically reach the region it
    # needed: bandwidth scales with both couplings, and narrowing it requires
    # WEAKER coupling, i.e. smaller w_iris (internal, sets k12) and smaller
    # w_ext (external, sets Qe). Target for N=2/0.1dB/5%: k12~0.069, Qe~16.9,
    # versus the landed design's measured 318MHz (11.1% FBW) -- roughly 2.2x
    # too wide, so real room below is required, not a token margin.
    "w_iris": (15.26, 6.0, 15.9),
    "x_iris": (28.68, 27.0, 30.4),
    "y_wall": (8.62,  7.5, 13.0),
    "w_ext":  (16.31, 8.0, 17.6),
}

# Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA jack -- the real, sourceable part
# this design now targets. Pin radius is the datasheet 0.76mm diameter / 2,
# modelled at its TRUE size: the historical 0.35mm backoff existed only to
# dodge the PEC-misclassification bug since fixed in
# palace_dualmode_driven.build_mesh (see docs/sma_connector/README.md). rout
# follows the same Z0=50ohm PTFE coax relation as before (rout/rin = 3.326).
# gnd_stitch models the connector's 4 discrete ground legs at +-2.62mm and the
# top-side pour they solder to, rather than the idealised continuous ring.
# JLCPCB's actual finish stack (2026-09-02, per the user): Rogers substrate
# -> copper -> ENIG -> soldermask -- "overall" ENIG (plated before masking),
# not the cheaper "selective" default (mask first, ENIG only at exposed
# pads). Real IPC-4552 numbers, the standard JLCPCB follows: nickel
# 3.0-6.0um (4.5um midpoint used here), gold flash 0.05-0.1um (too thin to
# matter separately, not modelled). Conductivity/permeability from
# electroless Ni-P plating data (Advanced Plating Technologies / Nickel
# Institute): medium-phosphorus (5-9% P, the standard solderable
# formulation) gives ~50-70 uOhm-cm resistivity (1.67e6 S/m used here) and
# is essentially non-magnetic at RF (mu_r~1.0 for P>=5%, vs >1 for low-P --
# low-P is specifically avoided in RF-sensitive applications per
# intermodulation-distortion literature). Modelled as a real volumetric
# conductor (Domains.Materials Conductivity), NOT the exterior-only
# Boundaries.Conductivity surface BC -- see palace_dualmode_driven.py's
# enig_um docstring for why that distinction matters.
JLCPCB_ENIG: dict[str, float] = {
    "enig_um": 4.5,
    "enig_conductivity_sm": 1.67e6,
    "enig_mu_r": 1.0,
}

# Real (lossy) copper instead of PEC. 5.96e7 S/m is annealed copper. The
# THICKNESS is not hardcoded: it comes from the substrate's own copper
# cladding weight (config.SUBSTRATES' cu_oz -> Substrate.cu_thickness()).
# For the default RO4350B_0.76mm that is cu_oz=0.5, i.e. 17.5um -- NOT the
# 1oz/35um a generic FR4 assumption would give. At 2.87GHz copper's skin
# depth is 1.22um, so even 17.5um is ~14 skin depths: electrically thick,
# so the surface-impedance model applies and anything plated on the far
# side (ENIG) stays shielded from the cavity fields.
# NOTE: this is the BASE cladding. A plated-through-hole process adds
# roughly 20-25um more on the outer layers, so finished outer copper is
# thicker still; the base value is the conservative choice.
JLCPCB_METAL: dict[str, float] = {
    "metal_conductivity_sm": 5.96e7,
}

# Soldermask + silkscreen, JLCPCB standard LPI process. Soldermask Dk 3.8 /
# Df 0.02 are JLCPCB's own published-ish values (jitxlib.jlcpcb.materials;
# their Df is flagged "a guess" there, and they publish no better one).
# 20um is mid-range of their 15-30um cured LPI thickness. Silkscreen is a
# thinner epoxy ink layer applied ON TOP of soldermask.
JLCPCB_SOLDERMASK: dict[str, float] = {
    "soldermask_um": 20.0, "soldermask_eps_r": 3.8, "soldermask_tand": 0.02,
}
JLCPCB_SILKSCREEN: dict[str, float] = {
    "silkscreen_um": 12.0, "silkscreen_eps_r": 3.2, "silkscreen_tand": 0.02,
}

# Via cover/fill. cover=True models the premium resin-filled + copper-capped
# via (a solid conductor plug, no hole through the board); cover=False models
# the standard open plated barrel (hollow copper shell, air core). Plating is
# 50um rather than the realistic 20-25um purely because of a MESHING floor
# measured on this geometry: 40um meshes, 35um and below fail with a
# TetGen/OCC PLC error (not a mesh-density knob -- mesh_min=0.01mm also
# fails). Physically harmless for the comparison: both 25um and 50um are
# tens of copper skin depths at 2.87GHz, so both are "electrically thick".
VIA_COVERED: dict[str, float] = {"via_conductivity_sm": 5.96e7}
VIA_OPEN: dict[str, float] = {"via_conductivity_sm": 5.96e7, "via_plating_um": 50.0}




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
        if p.get("metal_conductivity_sm") and "metal_thickness_um" not in p:
            # Real copper thickness comes from the SUBSTRATE's cladding weight,
            # not a generic 1oz assumption (RO4350B_0.76mm is 0.5oz = 17.5um).
            p["metal_thickness_um"] = spec.substrate.cu_thickness * 1e6
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
                "tand": res.get("tand", spec.substrate.tan_d),
                "soldermask": res.get("soldermask"),
                "via_conductivity": res.get("via_conductivity"),
                "enig": res.get("enig"),
                "metal_real": res.get("metal_real"),
                "silkscreen": res.get("silkscreen"),
                "legend": res.get("legend"),
                "launch_geom": res.get("launch_geom")}

    def plot_layout_2d(self, spec: FilterSpec, path: str, **params) -> str:
        p = dict(params)
        a = p.pop("a", A_SIW_MM)
        w_iris = p.pop("w_iris")
        x_iris = p.pop("x_iris", None)
        y_wall = p.pop("y_wall", 3.0)
        w_ext = p.pop("w_ext", None)
        p.pop("with_sma", None)
        return _plot_layout_2d(a_mm=a, w_iris_mm=w_iris, x_iris_mm=x_iris,
                               y_wall_mm=y_wall, w_ext_mm=w_ext, path=path,
                               launch=TAOGLAS_SMA, **p)

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
