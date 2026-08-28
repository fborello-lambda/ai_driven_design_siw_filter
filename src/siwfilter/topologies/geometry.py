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
# entirely), so its ceiling stays well under a.
#
# Round-3 correction: the w_ext floors, not the ceilings, are what bind under
# v17. v16 drove w_ext UP because its unclipped S11 term rewarded landing the
# reflection nulls, which a broad over-coupled response does easily -- so the
# round-2 widening (upward) was in the wrong direction. The first honest
# untruncated measurement puts the warm start at 437 MHz, 3.0x the 143.5 MHz
# target, and external coupling is what sets that. Scaling to target needs
# w_ext ~ 11-13 (BW ~ w^3 gives 13.1, BW ~ w^2 gives 10.9), i.e. AT or BELOW
# the old 13 floor. Floors dropped to 7-8 so the optimum is interior.
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
        "w_ext":  (13.0, 7.0, 24.0),     # floor dropped 13 -> 7, see note above
    },
    # cavity size already lands the midpoint on 2.85 GHz; the arms set the split
    "circular_cross": {
        "a":      (64.4, 61.0, 67.0),
        "w_iris": (13.0, 3.0, 25.0),     # was (3,14); winner at 13.06, near the ceiling
        "y_wall": (11.3, 2.0, 25.0),     # was (2,12); winner at 11.35, near the ceiling
        "w_ext":  (14.0, 8.0, 24.0),     # floor dropped 12 -> 8, see note above
    },
    # resonated ~40% high, so both diagonals scale up together
    "rhombic": {
        "a":      (80.0, 74.0, 86.0),
        "w_iris": (10.0, 4.0, 18.0),
        "y_wall": (37.6, 32.0, 44.0),    # transverse half-diagonal
        "w_ext":  (14.0, 8.0, 24.0),     # floor dropped 12 -> 8, see note above
    },
    # -------------------------------------------------------------------
    # Structural variants (2026-08-25). Coupling boxes re-centred on each
    # PARENT's coupling-only sweep winner (docs/geometry_exploration/
    # coupling_sweep_*_2026-08-24.md), not the original joint-search box --
    # that sweep is the better-founded estimate of where the good region is.
    # The new structural knob (n_perturb/ring2_frac/n_corners/w_iris2) is
    # NOT part of this space -- see explore_structural.py, which fixes it
    # per exploration run and only lets skopt search the coupling knobs at
    # that fixed structural setting.
    # -------------------------------------------------------------------
    "circular_cross_nvia": {
        "a":      (67.0, 63.0, 71.0),
        "w_iris": (16.0, 8.0, 24.0),
        "y_wall": (24.0, 12.0, 32.0),
        "w_ext":  (20.7, 14.0, 26.0),
    },
    "circular_cross_ring2": {
        "a":      (67.0, 63.0, 71.0),
        "w_iris": (16.0, 8.0, 24.0),
        "y_wall": (24.0, 12.0, 32.0),
        "w_ext":  (20.7, 14.0, 26.0),
    },
    # 2026-08-25, second pass: adds a flat launch facet (wf_mm, fixed per run
    # by explore_taper.py, not searched here) instead of another internal
    # perturbation -- tests the coupling-sweep doc's taper-less-launch
    # hypothesis directly. Same coupling box as circular_cross_ring2/nvia.
    "circular_cross_taper": {
        "a":      (67.0, 63.0, 71.0),
        "w_iris": (16.0, 8.0, 24.0),
        "y_wall": (24.0, 12.0, 32.0),
        "w_ext":  (20.7, 14.0, 26.0),
    },
    "corner_cut_2corner": {
        "a":      (59.4, 56.0, 63.0),
        "w_iris": (5.0, 3.0, 14.0),      # the SECOND cut adds coupling too, so
                                         # the single-cut optimum (w_iris=3, the
                                         # saturation floor) may not still be best
        "w_ext":  (15.0, 8.0, 22.0),
    },
    "rhombic_2diag": {
        "a":      (75.3, 71.0, 80.0),
        "w_iris": (7.0, 4.0, 14.0),
        "y_wall": (35.0, 30.0, 40.0),
        "w_ext":  (19.7, 12.0, 26.0),
    },
    # 2026-08-26: architecture change, not another delta -- replaces the
    # centre "cross" stub with a real SPANNING transverse iris row (dual-
    # mode's own mechanism) at the circle's equator, reasoned from dual-mode/
    # corner_cut (both couple via a structure spanning most of the transverse
    # width) beating circular_cross/rhombic (localised stubs) all session
    # regardless of internal tuning -- see geometries.py's docstring on
    # circular_cross_iris. w_iris/y_wall mean what they mean for dualmode
    # here (gap width / standoff from the fence), NOT cross-arm length, so
    # the box is centred on dualmode-like ratios against this cavity's
    # R=33.5mm rather than circular_cross's own box. y_wall kept SMALL
    # (3-15, vs 12-32 for the cross variants) since a real iris row sits
    # close to the fence -- much larger than R would shrink the row to
    # nothing.
    "circular_cross_iris": {
        "a":      (67.0, 63.0, 71.0),
        "w_iris": (16.0, 6.0, 28.0),
        "y_wall": (8.0, 3.0, 15.0),
        "w_ext":  (20.7, 14.0, 26.0),
    },
    # 2026-08-26, user-prompted: 2 dual-mode cavities in series (N=4). Box
    # ORIGINALLY centred on dual-mode's own landed values with x_iris2/w_iris2
    # mirrored (not searched) -- see v4 revision below for why that box was
    # replaced.
    #
    # v4 revision (2026-08-28): promoted to a genuinely ASYMMETRIC, 10D box,
    # after two full sessions of evidence that the mirrored 6D box cannot
    # reach a real N=4 passband:
    #   - eigenmode ground truth (this repo's own cascade_eigenmode.py)
    #     proved the mirror (x-swap) symmetry forces the 4-pole spectrum into
    #     an even/odd pair split no amount of coupling-WIDTH tuning escapes --
    #     x_iris2_mm/w_iris2_mm must be free, independent dimensions.
    #   - the `band_edges()` bandwidth-bridging bug (fixed alongside this
    #     box) hid that EVERY prior "narrower bandwidth" cascade result
    #     (this session and the last) was actually the response splitting
    #     into two disconnected resonance lobes, not a real merged, narrower
    #     N=4 Chebyshev passband. Re-measured with the fix: the naive
    #     symmetric baseline (w_inter=16.31, well-matched, s11w=-10.28dB) has
    #     ONE genuine ~290MHz lobe; every asymmetric/narrowed attempt this
    #     session (v1/v2/v3 of the eigenmode search) split into two ~20-55MHz
    #     lobes instead. Classic coupled-resonator theory: two cavities merge
    #     into one passband only while inter-cavity coupling stays comparable
    #     to each cavity's own loaded-Q; narrowing `w_inter_mm` in isolation
    #     (every previous session's strategy) while `w_ext`/Qe stays
    #     chronically under-coupled (measured 4-5x the ideal 22.18 across
    #     the ENTIRE `w_ext` range ever tried, up to 24mm) pushes the system
    #     into the weak-coupling/split regime instead of narrowing smoothly.
    #   - `w_ext` ceiling raised 24->36mm (still comfortably under `a`'s 50mm
    #     floor, see the w_ext/a-clearance note above) specifically to let
    #     the search test stronger external coupling than any prior round --
    #     nobody has found where, or if, critical coupling (Qe~22) exists for
    #     this port aperture; round 3 stopped short of finding out.
    #   - `iris_defect_frac`/`iris2_defect_frac` (commit 1ea9d2a, 2026-08-28,
    #     user-prompted "remove vias inside the cavity") added as genuinely
    #     new coupling dims: drop one via pair from a cavity's own internal
    #     fence at a chosen point, a localized coupling defect no continuous
    #     width/position parameter can reach. `<0` (the floor) is the
    #     no-defect sentinel, matching `dualmode_cascade()`'s own `None`
    #     convention.
    # This is a genuinely bigger, more expensive search than the box below
    # replaces -- deliberately paired with `screen_at_f0()`'s cheap GPU
    # pre-screen (already wired into `optimize()`'s coarse stage) to reject
    # non-viable candidates fast, rather than spending a full sweep on each.
    # v5 revision (2026-08-28): v4's WIDE box (above, kept in comments for the
    # record) found ZERO survivors across all 40 evals -- a real result, not
    # a search-budget problem: the GPU screen is a hard pass/fail with no
    # graded signal, so a GP surrogate has nothing to climb within the failed
    # region, and the viable pocket the eigenmode-ground-truth searches found
    # is narrow enough that 40 wide-box draws never landed in it. v5 instead
    # searches TIGHTLY around that known pocket (eval18's exact params,
    # +-15-30%) rather than exploring wide bounds -- paired with two fixes:
    # (1) `screen_at_f0()`'s failures now get a GRADED score (see
    # `evaluate()`'s screen branch) instead of a flat 1e9 tie, so the
    # surrogate has real gradient even while every candidate still fails;
    # (2) `w_ext2_mm` (new, independent second-port aperture, commit-pending)
    # added as a genuinely new dimension: analysis of the v4 fallback's raw
    # S11 showed only ONE real return-loss null across the whole sweep (the
    # other 3 poles ride along in S21 with no null of their own) -- consistent
    # with cavity-1-vs-cavity-2 asymmetry making each driven mode couple
    # differently to each end, which a single SYMMETRIC w_ext cannot fix.
    # `iris_defect_frac`/`iris2_defect_frac` kept at their full natural range
    # (already bounded, narrowing a discrete-ish selector doesn't help the
    # way narrowing a continuous dimension does).
    "dualmode_cascade": {
        "a":      (61.18, 58.0, 64.0),
        "w_iris": (9.89, 8.0, 12.0),
        "x_iris": (29.74, 27.0, 32.0),
        "y_wall": (10.42, 8.0, 13.0),
        "w_ext":  (16.0, 12.0, 22.0),
        # NOTE: keys below must be the exact LAYOUTS function kwarg names --
        # unlike a/w_iris/x_iris/y_wall/w_ext, these bypass _kw()'s explicit
        # pop-based renaming and flow through the generic structural-knob
        # passthrough (_extra()), same as wf_mm/n_corners/ring2_frac
        # elsewhere in this dict.
        "w_inter_mm":         (10.03, 8.0, 13.0),
        "w_iris2_mm":         (12.92, 10.0, 16.0),
        "x_iris2_mm":         (30.27, 27.0, 34.0),
        "iris_defect_frac":   (0.12, -0.1, 1.0),
        "iris2_defect_frac":  (-0.1, -0.1, 1.0),
        "w_ext2_mm":          (16.0, 8.0, 36.0),
    },
    # 2026-08-26, user-prompted: dual-mode's own landed 5D box, unchanged --
    # the second wall (w_iris2_mm, iris_sep_mm) is the structural knob, fixed
    # per phase-A/B run exactly like the other _2xxx variants, not searched
    # here. See dualmode_2wall's docstring in geometries.py for why (BW stuck
    # at 318MHz across dual-mode's own 60-eval search of this exact box).
    "dualmode_2wall": {
        "a":      (57.21, 54.0, 61.0),
        "w_iris": (15.26, 8.0, 22.0),
        "x_iris": (28.68, 20.0, 37.0),
        "y_wall": (8.62, 3.0, 15.0),
        "w_ext":  (16.31, 10.0, 24.0),
        # 2026-08-26 round 2: promoted from a fixed structural knob to a
        # searched dimension -- all 4 isolated screens at the landed dual-
        # mode point (w_iris2 in {8,15} x iris_sep in {8,15}) failed badly
        # (S11 ~-2.6 to -2.7dB, resonance destroyed), meaning the other 5
        # knobs need to move together with the second wall, not just have
        # it bolted on. w_iris2_mm<=0 still means "no second wall" if the
        # search lands there.
        "w_iris2_mm": (10.0, 0.0, 20.0),
        "iris_sep_mm": (10.0, 4.0, 20.0),
    },
    # 2026-08-27, user-prompted: dualmode_cascade's inter-cavity coupling
    # made a FLOATING segment (y_wall_inter_mm) instead of a full
    # wall-to-wall slot -- a genuinely different coupling mechanism, not a
    # re-tune of the same one (see dualmode_cascade_floatinter's docstring
    # in geometries.py for the root-cause reasoning: a full-wall slot's
    # y-profile couples unevenly to the cavity's two internal w_iris-split
    # field patterns, capping what (w_iris, w_inter_mm) alone can achieve --
    # measured outer-gap asymmetry ~90MHz vs ~38MHz at the best point found,
    # ideal wants ~46/48). Box centred on that night's landed values
    # (a=59.0, w_iris=12.8, x_iris=29.6, y_wall=8.9, w_ext=14.0,
    # w_inter_mm=13.7); y_wall_inter_mm=0 reproduces dualmode_cascade
    # exactly, so 0 is a valid in-box fallback if floating doesn't help.
    "dualmode_cascade_floatinter": {
        "a":      (59.0, 52.0, 64.0),
        "w_iris": (12.8, 8.0, 20.0),
        "x_iris": (29.6, 20.0, 37.0),
        "y_wall": (8.9, 3.0, 15.0),
        "w_ext":  (14.0, 10.0, 22.0),
        "w_inter_mm": (13.7, 8.0, 24.0),
        "y_wall_inter_mm": (0.0, 0.0, 15.0),
    },
}


#: Informational only (see base.Topology's docstring) -- 2-cavity cascades
#: report the TOTAL pole count (2 dual-mode cavities x 2 poles each), not
#: the per-instance class default.
_POLES_PER_CAVITY_OVERRIDE: dict[str, int] = {
    "dualmode_cascade": 4,
    "dualmode_cascade_floatinter": 4,
}


class GeometryTopology:
    """Drives one alternative cavity layout through the standard pipeline."""

    poles_per_cavity = 2

    def __init__(self, name: str):
        if name not in _SPACES:
            raise KeyError(f"no search box for geometry {name!r}; "
                           f"have {sorted(_SPACES)}")
        self.name = name
        self.poles_per_cavity = _POLES_PER_CAVITY_OVERRIDE.get(
            name, GeometryTopology.poles_per_cavity)

    def param_space(self, spec: FilterSpec) -> dict[str, ParamRange]:
        return dict(_SPACES[self.name])

    _LAYOUT_KNOWN_KEYS = {'a_mm','w_iris_mm','x_iris_mm','w_ext_mm','d_via_mm','p_via_mm','y_wall_mm','w_cav_mm'}

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

    def _extra(self, kw: dict) -> dict:
        """NEW structural knobs (per-arm via count, second ring, cut angle,
        etc.) present in kw but not one of the standard params LAYOUTS calls
        already pass by name. Mesh/SMA/device settings also land here but are
        harmless: every layout function's signature ends in **_, so passing
        them through is a no-op for layouts that don't declare the key --
        this is what lets a brand new structural parameter reach a layout
        function without editing every call site that invokes LAYOUTS."""
        skip = self._LAYOUT_KNOWN_KEYS | {
            "with_sma", "w_ms_mm", "mesh_max", "mesh_min", "h_air_factor"}
        return {k: v for k, v in kw.items()
               if k not in skip and not k.startswith(("sma_", "gnd_"))}

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
            w_cav_mm=kw.get("w_cav_mm"), **self._extra(kw))
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
            w_cav_mm=kw.get("w_cav_mm"), **self._extra(kw))
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
            w_cav_mm=kw.get("w_cav_mm"), **self._extra(kw))
        ys = [v[1] for v in vias]
        width = (max(0.0, max(ys)) + 3.0) - (min(0.0, min(ys)) - 3.0)
        return self.board_length_mm(spec, **params) * width

    def calibrate(self, spec: FilterSpec) -> dict | None:
        return None
