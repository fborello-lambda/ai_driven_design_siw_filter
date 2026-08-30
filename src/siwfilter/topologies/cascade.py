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
        keys = _iris_keys(spec.N)
        values = [params[k] for k in keys if params.get(k) is not None]
        if not values:
            return None
        n_iris = max(1, spec.N - 1)
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
        plot_layout(g, path)
        return path

    def board_length_mm(self, spec: FilterSpec, **params) -> float:
        g = self._geometry(spec, params)
        xmin, xmax, _, _ = g.board
        return (xmax - xmin) * 1e3

    def calibrate(self, spec: FilterSpec) -> dict | None:
        # No cheap eigenmode pre-pass wired up for the cascade topology yet
        # (palace_geometry.py's 2-cavity eigenmode exists but isn't plumbed
        # into a w(k) fit the way dualmode's is) -- explicitly out of scope
        # for this pass, see HANDOFF.md.
        return None
