"""Physical filter topologies, each implementing the ``Topology`` protocol
(see ``base.py``) so ``optimize.py``/``cli.py`` can drive any of them the
same way. See HANDOFF.md's "Architecture: unified AI-driven design CLI"
section for the design rationale.
"""
from .base import Topology, ParamRange, MeshResult
from .cascade import CascadeTopology
from .dualmode import DualModeTopology

REGISTRY: dict[str, Topology] = {
    "cascade": CascadeTopology(),
    "dualmode": DualModeTopology(),
}

__all__ = ["Topology", "ParamRange", "MeshResult", "REGISTRY",
           "CascadeTopology", "DualModeTopology"]
