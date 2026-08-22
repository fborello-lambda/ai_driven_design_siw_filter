"""Topology protocol: the one interface every physical filter structure
implements so ``optimize.py``/``cli.py`` can drive any of them identically.

See HANDOFF.md's "Architecture: unified AI-driven design CLI" section for
the rationale. This is a thin adapter layer only -- no mesh-construction
logic lives here; each concrete Topology wraps an existing, validated
builder module (``palace_driven.py`` / ``palace_dualmode_driven.py``)
unchanged.
"""
from __future__ import annotations

from typing import Optional, Protocol, TypedDict

from ..config import FilterSpec

# (init, lo, hi), all in mm -- matches the PARAMS dicts already used by
# palace_opt.py/palace_opt_sma.py/palace_opt_dualmode.py.
ParamRange = tuple[float, float, float]


class SmaInfo(TypedDict, total=False):
    rin_mm: float
    rout_mm: float
    eps_r: float
    tand: float
    voltage_path_in: list[list[float]]
    voltage_path_out: list[list[float]]


class MeshResult(TypedDict, total=False):
    mesh_path: str
    ports: tuple[int, int]
    tets: int
    nodes: int
    sma: Optional[SmaInfo]
    eps_r: float
    tand: float


class Topology(Protocol):
    name: str
    poles_per_cavity: int      # 1 = single-mode cavity, 2 = dual-mode, ...

    def param_space(self, spec: FilterSpec) -> dict[str, ParamRange]:
        """Search-space bounds (mm) for every free geometry parameter."""
        ...

    def build_mesh(self, spec: FilterSpec, out_name: str, **params: float) -> MeshResult:
        """Build the Palace-ready mesh for this design point."""
        ...

    def plot_layout_2d(self, spec: FilterSpec, path: str, **params: float) -> str:
        """Fast matplotlib top view (no mesh/solve needed). Returns the path."""
        ...

    def board_length_mm(self, spec: FilterSpec, **params: float) -> float:
        """Overall board length (x-extent) for this design point, mm."""
        ...

    def calibrate(self, spec: FilterSpec) -> dict | None:
        """Optional cheap eigenmode pre-pass (k12-vs-geometry sweep, etc.).

        Returns None if this topology has no calibration step.
        """
        ...
