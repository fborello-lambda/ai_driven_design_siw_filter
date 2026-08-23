"""Topology adapters for the alternative cavity geometries.

One class parameterised by layout name, rather than a file each: these all
share the dual-mode builder and differ only in via placement (see
geometries.py), so a per-geometry class would be four copies of the same
delegation.

Search boxes are centred on each geometry's SCREENED resonance, not on
guesses. The wideband screen (1.5-5 GHz) measured where each actually
resonates, and `a` is pre-scaled by the ratio needed to bring that to f0 --
starting a Bayesian search on a cavity resonating 40% off target just spends
the budget rediscovering the scale factor.

Screen results that set these boxes:
  corner_cut      peak S21 -1.9dB @ 3.00GHz, S11 -28.6dB   -> scale a x1.045
  circular_cross  bands 2.60 & 3.10GHz (midpoint 2.85)      -> a already right,
                  the two degenerate modes just need their split closed
  rhombic         bands 3.95 & 4.40GHz                      -> scale a x1.40

halfmode and quartermode are deliberately absent: four attempts produced no
resonance anywhere in 1.5-5 GHz. See geometries.py for what each attempt ruled
out. Fractional-mode cavities want a feed on the open edge, which this
builder's coax-on-the-axis architecture does not provide.
"""
from __future__ import annotations

from ..config import FilterSpec
from ..palace_dualmode_driven import build_mesh as _build_mesh, _dims
from .base import MeshResult, ParamRange
from .dualmode import TAOGLAS_SMA

# name -> (param_space, extra build kwargs)
#
# Boxes WIDENED after the first 18-eval round: the winners of both completed
# geometries sat hard against a bound, which means the box was the binding
# constraint and the reported optimum was an artefact of where it was drawn.
# Every widened bound below is annotated with what pinned it.
#
# w_ext is the feed aperture; it must stay clear of the cavity wall
# (corner_cut's end wall spans w_ext/2 -> a/2, so w_ext -> a removes the wall
# entirely). 26mm against a >= 57 leaves >= 2.5mm of wall at the worst corner.
_SPACES: dict[str, dict[str, ParamRange]] = {
    # a scaled 3.00 -> 2.87 GHz; w_iris is the corner-cut depth = the coupling
    # knob. NO y_wall: corner_cut() ignores that argument entirely (verified --
    # the via list is byte-identical for y_wall 4 vs 10), so searching it spent
    # a whole GP dimension on a parameter that cannot change the result, which
    # is also why the first round's top six had scattered y_wall at near-equal
    # scores. 3D instead of 4D.
    "corner_cut": {
        "a":      (58.9, 56.0, 63.0),
        "w_iris": (7.0, 3.0, 20.0),      # was (7,18); winner pinned at the 7 floor.
                                         # Below p_via the cut saturates, so 3 = p is
                                         # the real floor.
        "w_ext":  (19.0, 13.0, 26.0),    # was (13,19); winner pinned at the 19 ceiling
    },
    # cavity size already lands the midpoint on 2.85 GHz; the arms set the split
    "circular_cross": {
        "a":      (64.4, 61.0, 67.0),
        "w_iris": (13.0, 3.0, 25.0),     # was (3,14); winner at 13.06, near the ceiling
        "y_wall": (11.3, 2.0, 25.0),     # was (2,12); winner at 11.35, near the ceiling
        "w_ext":  (19.8, 12.0, 30.0),    # was (12,20); winner pinned at the 20 ceiling
    },
    # resonated ~40% high, so both diagonals scale up together
    "rhombic": {
        "a":      (80.0, 74.0, 86.0),
        "w_iris": (10.0, 4.0, 18.0),
        "y_wall": (37.6, 32.0, 44.0),    # transverse half-diagonal
        # widened pre-emptively to match the other two: both pinned their w_ext
        # ceiling, and there is no reason rhombic's external coupling wants less.
        "w_ext":  (16.3, 12.0, 30.0),
    },
}


class GeometryTopology:
    """Drives one alternative cavity layout through the standard pipeline."""

    poles_per_cavity = 2

    def __init__(self, name: str):
        if name not in _SPACES:
            raise KeyError(f"no search box for geometry {name!r}; "
                           f"have {sorted(_SPACES)}")
        self.name = name

    def param_space(self, spec: FilterSpec) -> dict[str, ParamRange]:
        return dict(_SPACES[self.name])

    def _kw(self, params: dict) -> dict:
        p = dict(params)
        kw = dict(
            a_mm=p.pop("a"),
            w_iris_mm=p.pop("w_iris", None),
            x_iris_mm=p.pop("x_iris", None),
            y_wall_mm=p.pop("y_wall", 3.0),
            w_ext_mm=p.pop("w_ext", None),
            w_cav_mm=p.pop("w_cav", None),
            w_ms_mm=p.pop("w_ms", 1.664),
            d_via_mm=p.pop("d_via", 1.5),
            p_via_mm=p.pop("p_via", 3.0),
        )
        kw.update(p)                       # mesh_max/mesh_min/h_air_factor/etc
        kw.setdefault("with_sma", True)
        for k, v in TAOGLAS_SMA.items():   # real connector by default
            kw.setdefault(k, v)
        return kw

    def build_mesh(self, spec: FilterSpec, out_name: str, **params) -> MeshResult:
        res = _build_mesh(geometry=self.name, out_name=out_name, show=False,
                          **self._kw(params))
        if "mesh" not in res:              # render_png/preview short-circuit
            return res                     # type: ignore[return-value]
        return {"mesh_path": res["mesh"], "ports": res["ports"],
                "tets": res["tets"], "nodes": res["nodes"],
                "sma": res.get("sma"),
                "eps_r": res.get("eps_r", spec.substrate.eps_r),
                "tand": res.get("tand", spec.substrate.tan_d)}

    def plot_layout_2d(self, spec: FilterSpec, path: str, **params) -> str:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
        from ..geometries import LAYOUTS

        kw = self._kw(params)
        vias, info = LAYOUTS[self.name](
            a_mm=kw["a_mm"], w_iris_mm=kw["w_iris_mm"], x_iris_mm=kw["x_iris_mm"],
            w_ext_mm=kw["w_ext_mm"], d_via_mm=kw["d_via_mm"],
            p_via_mm=kw["p_via_mm"], y_wall_mm=kw["y_wall_mm"],
            w_cav_mm=kw.get("w_cav_mm"))
        W, Lt, Lf = _dims(kw["a_mm"], kw["w_ms_mm"], None, None)
        r = kw["d_via_mm"] / 2.0
        xs = [v[0] for v in vias]; ys = [v[1] for v in vias]

        fig, ax = plt.subplots(figsize=(11, 5.5))
        for x, y in vias:
            ax.add_patch(Circle((x, y), r, fc="#333", ec="none", zorder=3))
        ax.axhline(0.0, color="#0a0", ls=":", lw=1.0, label="feed axis")
        ax.plot([min(xs) - (Lt + Lf), min(xs)], [0, 0], color="#d9a441", lw=3,
                solid_capstyle="butt", label="microstrip feed")
        ax.plot([max(xs), max(xs) + (Lt + Lf)], [0, 0], color="#d9a441", lw=3,
                solid_capstyle="butt")
        ax.set_aspect("equal"); ax.grid(alpha=.25)
        ax.set_xlabel("x [mm]"); ax.set_ylabel("y [mm]")
        ax.set_title(f"{self.name}: {len(vias)} vias, cavity "
                     f"{max(xs)-min(xs):.1f} x {max(ys)-min(ys):.1f} mm  "
                     f"(a={kw['a_mm']:.1f}, w_iris={kw['w_iris_mm']:.1f}, "
                     f"w_ext={kw['w_ext_mm']:.1f}, y_wall={kw['y_wall_mm']:.1f})",
                     fontsize=10)
        ax.legend(fontsize=8, loc="upper right")
        fig.tight_layout(); fig.savefig(path, dpi=140)
        plt.close(fig)
        print(f"Wrote {path}  ({len(vias)} vias)")
        return path

    def board_length_mm(self, spec: FilterSpec, **params) -> float:
        kw = self._kw(params)
        W, Lt, Lf = _dims(kw["a_mm"], kw["w_ms_mm"], None, None)
        from ..geometries import LAYOUTS
        vias, _ = LAYOUTS[self.name](
            a_mm=kw["a_mm"], w_iris_mm=kw["w_iris_mm"], x_iris_mm=kw["x_iris_mm"],
            w_ext_mm=kw["w_ext_mm"], d_via_mm=kw["d_via_mm"],
            p_via_mm=kw["p_via_mm"], y_wall_mm=kw["y_wall_mm"],
            w_cav_mm=kw.get("w_cav_mm"))
        return max(v[0] for v in vias) + 2 * (Lt + Lf)

    def board_area_mm2(self, spec: FilterSpec, **params) -> float:
        """Board footprint -- what JLCPCB actually charges for. Length alone
        understates a wide cavity, and these geometries differ in width."""
        kw = self._kw(params)
        from ..geometries import LAYOUTS
        vias, _ = LAYOUTS[self.name](
            a_mm=kw["a_mm"], w_iris_mm=kw["w_iris_mm"], x_iris_mm=kw["x_iris_mm"],
            w_ext_mm=kw["w_ext_mm"], d_via_mm=kw["d_via_mm"],
            p_via_mm=kw["p_via_mm"], y_wall_mm=kw["y_wall_mm"],
            w_cav_mm=kw.get("w_cav_mm"))
        ys = [v[1] for v in vias]
        width = (max(0.0, max(ys)) + 3.0) - (min(0.0, min(ys)) - 3.0)
        return self.board_length_mm(spec, **params) * width

    def calibrate(self, spec: FilterSpec) -> dict | None:
        return None
