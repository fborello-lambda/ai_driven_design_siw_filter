"""Parametric Substrate Integrated Waveguide (SIW) bandpass filter.

3 inline TE101 cavities, inductive-iris coupled, Chebyshev response, f0=2.87 GHz.
``config`` is the single source of truth for every tunable number; the design
flows synthesis -> geometry -> layout/CST export -> (openEMS/Palace) -> report.

Entry point: ``siwfilter.cli:main`` (console script ``siw``).
"""

__version__ = "0.1.0"
