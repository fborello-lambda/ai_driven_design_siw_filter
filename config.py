"""Single source of truth for the SIW bandpass filter design.

Every tunable number lives here; all other modules import from this file.
See CLAUDE.md sections 1, 7 for the meaning of each parameter.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Output layout (single source of truth for where every script writes/reads).
# Centralising this here keeps inter-script dependencies consistent: e.g.
# compare.py reads the .s2p that synthesis.py / openems_sim.py wrote, and
# siw_geometry.py reads the calibration cache that calibrate.py wrote.
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(_ROOT, "output")


def _out(subdir: str, name: str) -> str:
    """Absolute path to ``name`` inside ``output/<subdir>/`` (dir created)."""
    d = os.path.join(OUTPUT_DIR, subdir)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def out_img(name: str) -> str:
    """output/imgs/<name> — plots and figures (.png)."""
    return _out("imgs", name)


def out_s2p(name: str) -> str:
    """output/s2p/<name> — Touchstone S-parameter files (.s2p)."""
    return _out("s2p", name)


def out_bas(name: str) -> str:
    """output/bas/<name> — CST VBA macros (.bas)."""
    return _out("bas", name)


def out_data(name: str) -> str:
    """output/data/<name> — caches, CSVs, JSON (calibration, via coords)."""
    return _out("data", name)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
C0 = 2.99792458e8          # speed of light [m/s]
EPS0 = 8.8541878128e-12    # vacuum permittivity [F/m]
MU0 = 4e-7 * math.pi       # vacuum permeability [H/m]

# ---------------------------------------------------------------------------
# Substrate stock (confirmed from datasheets — real available material)
# ---------------------------------------------------------------------------
#   eps_r : design dielectric constant (Dk)
#   tan_d : dielectric loss tangent (Df) at 10 GHz
#   h     : substrate thickness [m]
#   cu_oz : copper cladding weight [oz] (1 oz ~= 35 um)
SUBSTRATES = {
    # Rogers RO4350B — design Dk 3.66, tand 0.0037 @10GHz
    "RO4350B_1.52mm": dict(eps_r=3.66, tan_d=0.0037, h=1.52e-3,  cu_oz=1.0),
    "RO4350B_0.76mm": dict(eps_r=3.66, tan_d=0.0037, h=0.76e-3,  cu_oz=0.5),
    "RO4350B_0.25mm": dict(eps_r=3.66, tan_d=0.0037, h=0.25e-3,  cu_oz=1.0),
    "RO4350B_0.10mm": dict(eps_r=3.36, tan_d=0.0037, h=0.10e-3,  cu_oz=1.0),  # 4-mil laminate: spec Dk differs (3.36)
    # Arlon/Rogers AD250C — design Dk 2.50, tand 0.0013 @10GHz
    "AD250C_1.524mm": dict(eps_r=2.50, tan_d=0.0013, h=1.524e-3, cu_oz=1.0),
}
DEFAULT_SUBSTRATE = "RO4350B_0.76mm"


@dataclass(frozen=True)
class Substrate:
    """Resolved substrate properties."""
    name: str
    eps_r: float
    tan_d: float
    h: float        # thickness [m]
    cu_oz: float    # copper weight [oz]

    @property
    def cu_thickness(self) -> float:
        """Copper cladding thickness [m] (1 oz ~= 35 um)."""
        return self.cu_oz * 35e-6

    def kappa(self, f: float) -> float:
        """Equivalent dielectric conductivity for openEMS/CST loss model.

        kappa = 2*pi*f*eps0*eps_r*tan_d   [S/m]
        This reproduces the datasheet loss tangent at frequency ``f``.
        """
        return 2.0 * math.pi * f * EPS0 * self.eps_r * self.tan_d


def get_substrate(name: str | None = None) -> Substrate:
    """Resolve a substrate preset by key into a :class:`Substrate`."""
    key = name or DEFAULT_SUBSTRATE
    if key not in SUBSTRATES:
        raise KeyError(f"Unknown substrate {key!r}; choose from {list(SUBSTRATES)}")
    return Substrate(name=key, **SUBSTRATES[key])


@dataclass(frozen=True)
class FilterSpec:
    """Complete parametric specification of the SIW bandpass filter."""

    # --- Electrical spec ---
    f0: float = 2.87e9          # center frequency [Hz]
    FBW: float = 0.05           # fractional bandwidth (f2-f1)/f0
    N: int = 3                  # filter order (number of cavities)
    ripple_db: float = 0.1      # Chebyshev passband ripple [dB]

    # --- Substrate ---
    substrate_name: str = DEFAULT_SUBSTRATE

    # --- SIW physical parameters ---
    d_via: float = 0.8e-3       # via diameter [m]
    p_via: float = 1.5e-3       # via pitch (center-to-center) [m]
    fc_ratio: float = 0.7       # f_c10 / f0 target (operate near 1.4*f_c)

    @property
    def substrate(self) -> Substrate:
        return get_substrate(self.substrate_name)

    # Convenience derived quantities ----------------------------------------
    @property
    def f1(self) -> float:
        """Lower band edge [Hz]."""
        return self.f0 * (1.0 - self.FBW / 2.0)

    @property
    def f2(self) -> float:
        """Upper band edge [Hz]."""
        return self.f0 * (1.0 + self.FBW / 2.0)

    @property
    def fc_target(self) -> float:
        """Target TE10 cutoff frequency [Hz] (~0.7*f0)."""
        return self.fc_ratio * self.f0

    @property
    def lambda0(self) -> float:
        """Free-space wavelength at f0 [m]."""
        return C0 / self.f0


# Default design instance used across the project unless overridden.
SPEC = FilterSpec()


# ---------------------------------------------------------------------------
# FINAL design — Palace-optimized values (2026-06-20).
# The analytical first pass in siw_geometry gets these dimensions wrong because
# the microstrip tapers + external irises load the cavities. These numbers come
# from the per-cavity Palace optimizer (palace_opt.py): S11 < -16 dB in band,
# IL ~1.5 dB, centred ~2.87 GHz. When USE_OPTIMIZED is True, build_geometry
# overrides the computed L_cav / iris / w_ext / feed with these (dimensions mm).
# (Optimizer found L_end=34.4, L_mid=34.3 -> ~equal, so uniform 34.4 is used.)
# ---------------------------------------------------------------------------
USE_OPTIMIZED = True
OPTIMIZED_DESIGN = {
    "L_cav_mm":   34.4,
    "w_iris_mm":  13.0,
    "w_ext_mm":   16.0,
    "W_ms_mm":    2.26,
    "L_taper_mm": 15.46,
}


if __name__ == "__main__":
    spec = SPEC
    sub = spec.substrate
    print("=== FilterSpec ===")
    print(f"f0        = {spec.f0/1e9:.3f} GHz")
    print(f"FBW       = {spec.FBW*100:.2f} %  (f1={spec.f1/1e9:.4f} GHz, f2={spec.f2/1e9:.4f} GHz)")
    print(f"N         = {spec.N}")
    print(f"ripple    = {spec.ripple_db} dB")
    print(f"d_via     = {spec.d_via*1e3:.3f} mm")
    print(f"p_via     = {spec.p_via*1e3:.3f} mm  (p/d = {spec.p_via/spec.d_via:.3f})")
    print(f"fc target = {spec.fc_target/1e9:.3f} GHz")
    print()
    print(f"=== Substrate: {sub.name} ===")
    print(f"eps_r     = {sub.eps_r}")
    print(f"tan_d     = {sub.tan_d}")
    print(f"h         = {sub.h*1e3:.3f} mm")
    print(f"cu        = {sub.cu_oz} oz ({sub.cu_thickness*1e6:.1f} um)")
    print(f"kappa(f0) = {sub.kappa(spec.f0):.5f} S/m")
    print()
    print("Available substrates:", list(SUBSTRATES))
