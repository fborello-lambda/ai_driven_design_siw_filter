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
    # SMA coax stub.
    #   rin  = datasheet SPE-12-8-134/C/WY sec.2, pin diameter 0.76mm.
    #          (Checked against the PDF in docs/sma_connector/, 2026-09-04.)
    #   rout = DERIVED, not from the datasheet, which gives no dielectric OD:
    #          Z0 = 50 ohm in PTFE eps_r 2.08 -> rout/rin = 3.326.
    "sma_rin_mm": 0.38,
    "sma_rout_mm": 1.2639,
    "sma_eps_r": 2.08,
    "sma_tand": 4.0e-4,
    # Ground stitching. The offset is the datasheet footprint pitch
    # (sec.3.1: 2.62 / 2.62mm between the three front pads), so the
    # connector's ground legs land on the pours. n_gnd_stitch is a REQUEST;
    # gnd_stitch_layout fits as many as clear -- it builds 4 per pad, 16
    # total. Report the measured count, never this number.
    "gnd_stitch": True,
    "n_gnd_stitch": 6,
    "gnd_stitch_offset_mm": 2.62,
    # Impedance-matched CPWG launch. DELIBERATELY NOT the datasheet's
    # recommended footprint: its ground pads are 1mm wide starting 2.12mm
    # off centre, and its signal pad is 0.85 +-0.2mm. The pour inner edge is
    # pulled in to 0.8512mm because that gap (0.2512mm against a 1.2mm
    # trace) is what solves to 50 ohm on 0.76mm RO4350B. The connector still
    # lands entirely on copper -- pin (0.76mm dia) on the 1.2mm trace, both
    # legs (2.12..3.12mm) inside the 0.8512..3.6mm pours -- so it solders
    # normally. The one deviation is trace width: 1.2mm vs 0.85 +-0.2mm.
    "cpwg_gap_mm": 0.2512,
    "cpwg_y_gnd_mm": 0.8512,
    "cpwg_y_out_mm": 3.6,
    "cpwg_w_feed_mm": 1.2,
}

#: Datasheet limits that constrain the BOARD rather than the launch pattern.
#: sec.2's table says 0.8mm max PCB thickness; sec.3.1's footprint note says
#: 0.79mm. This board's finished stack is 0.760 dielectric + 2 x 0.0175
#: copper = 0.795mm, i.e. between the two, with no margin. It fits (the fork
#: is sprung) but 1 oz copper would make it 0.830mm and it would NOT -- so
#: the 0.5 oz specification is load-bearing, not a preference.
TAOGLAS_MAX_BOARD_MM = 0.80
TAOGLAS_MAX_BOARD_FOOTPRINT_NOTE_MM = 0.79

#: Tag for golden entries measured under this launch (golden/README.md).
LAUNCH_TAG = "cpwg_taoglas"


#: The pre-2026-09-02 pad-only launch, restored as a NAMED ALTERNATIVE for
#: comparison -- not a fork of TAOGLAS_CPWG, and not the default.
#:
#: Restored 2026-09-03 to settle a specific question with a measurement
#: instead of by elimination. Under the CPWG launch the dual-mode cavity
#: cannot be matched better than -10.35 dB by any combination of its four
#: geometry parameters (w_iris, w_ext, y_wall and x_iris were each scanned;
#: return loss improves only in the direction that ruins bandwidth). The
#: SAME cavity measured -17.7 dB under this pad-only launch, which makes the
#: launch itself the prime suspect -- it was solved to 50 ohm for the
#: CASCADE's feed, never for this cavity. Running one geometry under both
#: launches tests that directly.
#:
#: `cpwg_gap_mm=None` is what selects pad-only in
#: palace_dualmode_driven.build_mesh: no coplanar ground pour, just the
#: connector pads and their stitching vias.
TAOGLAS_PAD_ONLY: dict[str, float | bool | int | None] = {
    "sma_rin_mm": 0.38,
    "sma_rout_mm": 1.2639,
    "sma_eps_r": 2.08,
    "sma_tand": 4.0e-4,
    "gnd_stitch": True,
    "n_gnd_stitch": 2,
    "gnd_stitch_offset_mm": 2.62,
    "cpwg_gap_mm": None,      # <- no CPWG; pad-only launch
}

#: Tag for golden entries measured under the pad-only launch.
PAD_ONLY_TAG = "sma_taoglas"

#: Selectable by name from the CLI. Adding a launch here is the supported
#: way to compare launches; forking a dict is not (see the module docstring).
LAUNCHES: dict[str, dict] = {
    "cpwg": TAOGLAS_CPWG,
    "pad": TAOGLAS_PAD_ONLY,
}
LAUNCH_TAGS: dict[str, str] = {"cpwg": LAUNCH_TAG, "pad": PAD_ONLY_TAG}
