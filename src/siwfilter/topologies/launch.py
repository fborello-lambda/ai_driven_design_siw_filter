"""THE launch footprint. One definition, used by every topology.

Real Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA jack + its impedance-matched
CPWG launch (gap solved to 50 ohm, see docs/TUNING_PLAN_2026-08-29.md sec 2).

There is deliberately only ONE launch in this project. There used to be
several -- a pad-only variant, a separate "visual" overlay, and duplicate
per-topology copies -- and every one of them caused a real, measured
problem:

  * cascade simulated the CPWG launch while dual-mode simulated pad-only
    stitching, so the launch that was actually solved to 50 ohm was not the
    one on the board intended for fabrication;
  * the stackup drawing read the "visual" preset while build_mesh read
    another, so published figures showed a CPWG launch that no dual-mode
    simulation had ever run;
  * because the presets were duplicated per topology, they could drift
    apart silently.

Keeping a single dict removes that entire failure class by construction. If
a genuinely different launch is ever needed, add it as a NEW named dict and
tag its results distinctly (see golden/README.md's launch-tag convention) --
do not fork this one.

Pin radius is the datasheet 0.76mm diameter / 2, modelled at true size; the
historical 0.35mm backoff existed only to dodge a PEC-misclassification bug
since fixed in palace_dualmode_driven.build_mesh (docs/sma_connector/README.md).
rout follows the Z0=50ohm PTFE coax relation (rout/rin = 3.326). gnd_stitch
models the connector's discrete ground legs and the top-side pour they
solder to, rather than an idealised continuous ring.
"""
from __future__ import annotations

TAOGLAS_CPWG: dict[str, float | bool | int] = {
    # SMA coax stub
    "sma_rin_mm": 0.38,
    "sma_rout_mm": 1.2639,
    "sma_eps_r": 2.08,
    "sma_tand": 4.0e-4,
    # ground stitching
    "gnd_stitch": True,
    "n_gnd_stitch": 6,
    "gnd_stitch_offset_mm": 2.62,
    # impedance-matched CPWG launch
    "cpwg_gap_mm": 0.2512,
    "cpwg_y_gnd_mm": 0.8512,
    "cpwg_y_out_mm": 3.6,
    "cpwg_w_feed_mm": 1.2,
}

#: Tag for golden entries measured under this launch (golden/README.md).
LAUNCH_TAG = "cpwg_taoglas"
