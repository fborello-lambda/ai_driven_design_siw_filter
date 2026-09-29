"""THE launch footprint. One definition, used by every topology.

Real Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA jack + its impedance-matched
CPWG launch (gap solved to 50 ohm, see docs/TUNING_PLAN_2026-08-29.md (tag docs-archive-2026-09-29) sec 2).

Deliberately only ONE launch dict per variant. Per-topology copies have
previously drifted apart (a launch simulated by one topology but not
another, or a drawing preset that didn't match build_mesh's). To compare a
different launch, add a new named dict and tag it (golden/README.md's
launch-tag convention) -- don't fork TAOGLAS_CPWG.

Pin radius is the datasheet 0.76mm diameter / 2, modelled at true size. rout
follows the Z0=50ohm PTFE coax relation (rout/rin=3.326). gnd_stitch models
the connector's discrete ground legs and the pour they solder to, not an
idealised continuous ring.
"""
from __future__ import annotations

TAOGLAS_CPWG: dict[str, float | bool | int] = {
    # rin: datasheet SPE-12-8-134/C/WY sec.2, pin diameter 0.76mm.
    # rout: DERIVED (no dielectric OD in the datasheet) -- Z0=50ohm in PTFE
    # eps_r 2.08 -> rout/rin = 3.326.
    "sma_rin_mm": 0.38,
    "sma_rout_mm": 1.2639,
    "sma_eps_r": 2.08,
    "sma_tand": 4.0e-4,
    # Offset is the datasheet footprint pitch (sec.3.1: 2.62mm) so the
    # connector's legs land on the pours. n_gnd_stitch is a REQUEST --
    # gnd_stitch_layout fits as many as clear; report the measured count.
    "gnd_stitch": True,
    "n_gnd_stitch": 6,
    "gnd_stitch_offset_mm": 2.62,
    # DELIBERATELY NOT the datasheet's recommended footprint (1mm ground
    # pads at 2.12mm off centre, 0.85+-0.2mm signal pad). The pour inner
    # edge is pulled in to 0.8512mm because that gap against a 1.2mm trace
    # is what solves to 50 ohm on 0.76mm RO4350B. The connector still lands
    # entirely on copper and solders normally; the one deviation is trace
    # width, 1.2mm vs the datasheet's 0.85mm.
    "cpwg_gap_mm": 0.2512,
    "cpwg_y_gnd_mm": 0.8512,
    "cpwg_y_out_mm": 3.6,
    "cpwg_w_feed_mm": 1.2,
}

# Datasheet PCB-thickness limits (sec.2: 0.8mm max; sec.3.1's footprint note:
# 0.79mm). This board's finished stack is 0.795mm -- between the two, no
# margin. 1oz copper would give 0.830mm and would not fit, so 0.5oz is
# load-bearing, not a preference.
TAOGLAS_MAX_BOARD_MM = 0.80
TAOGLAS_MAX_BOARD_FOOTPRINT_NOTE_MM = 0.79

#: Tag for golden entries measured under this launch (golden/README.md).
LAUNCH_TAG = "cpwg_taoglas"


# Pad-only launch (no CPWG ground pour, cpwg_gap_mm=None), kept as a named
# alternative: on the dual-mode cavity it measured -17.7dB where the CPWG
# launch caps out at -10.35dB across the full parameter scan, since the CPWG
# gap was solved to 50 ohm for the cascade's feed, not this cavity.
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
