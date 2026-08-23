"""Physical filter topologies, each implementing the ``Topology`` protocol
(see ``base.py``) so ``optimize.py``/``cli.py`` can drive any of them the
same way. See HANDOFF.md's "Architecture: unified AI-driven design CLI"
section for the design rationale.
"""
from .base import Topology, ParamRange, MeshResult
from .cascade import CascadeTopology
from .dualmode import DualModeTopology
from .geometry import GeometryTopology

REGISTRY: dict[str, Topology] = {
    "cascade": CascadeTopology(),
    "dualmode": DualModeTopology(),
    # Alternative cavity shapes that SCREENED with a real passband. halfmode
    # and quartermode exist in geometries.py but are not registered: four
    # attempts produced no resonance in 1.5-5 GHz (see geometry.py docstring).
    "corner_cut": GeometryTopology("corner_cut"),
    "circular_cross": GeometryTopology("circular_cross"),
    "rhombic": GeometryTopology("rhombic"),
}

__all__ = ["Topology", "ParamRange", "MeshResult", "REGISTRY",
           "CascadeTopology", "DualModeTopology", "GeometryTopology"]
