# Archived: pad-only launch (superseded 2026-09-02)

Every entry here was measured with the **pad-only** SMA launch
(`n_gnd_stitch=2`, no coplanar gap) that dual-mode used before the
impedance-matched CPWG launch was merged into `build_mesh`.

They are **not comparable** to anything measured after that change: the
launch is a physically different structure, and the launch is exactly where
the fabrication penalty was found to originate.

Kept because the measurements are real and the comparisons remain valid
*among themselves* — in particular the fabrication-variant study
(PEC vs copper+ENIG+soldermask+silkscreen, tented vs open vias), whose
findings are mechanism-level and carry over:

- return loss, not insertion loss, is the dominant fabrication penalty;
- real copper costs ~0.37 dB of IL that PEC-only models omit entirely;
- via tenting and silkscreen are electrically irrelevant (<0.03 dB).

Do not cite the absolute numbers as current. Re-measure under the CPWG
launch (tag `cpwg_taoglas`) before using any of them for a decision.
