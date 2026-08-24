# Geometry exploration baseline -- 2026-08-24

Frozen results from the first geometry-exploration batch (v17 objective,
GPU coarse search + dense CPU confirm, real Taoglas SMA on all four). Kept
here so future optimization runs -- which overwrite `output/data/opt_*_best.json`
-- can still be compared against where this started.

## Result

| design | fc GHz | IL dB | BW MHz | S11 worst (in-band) | board mm | area cm2 |
|---|---|---|---|---|---|---|
| **dual-mode (retuned)** | 2.905 | -1.41 | 320 | **-17.2** | 119.1 | -- |
| corner-cut | 2.880 | -1.26 | 331 | -9.3 | 121.2 | 79.3 |
| circular+cross | 2.829 | -1.81 | 352 | -3.1 | 127.2 | 92.9 |
| rhombic | 2.988 | -5.04 | 318 | -5.2 | 126.1 | 95.8 |
| **target** | 2.870 | -- | 143.5 | <= -16 | -- | -- |

## Honest read

None of the three new geometries beat the dual-mode reference that was
already landed before this session's exploration started. Dual-mode is the
only design meeting the -16 dB return-loss spec, and it is also the
smallest board.

**The shared failure mode**: bandwidth clustered at 318-352 MHz across
ALL FOUR designs, 2.2-2.5x the 143.5 MHz (5% FBW) target, regardless of
cavity shape. That is the signature of something structural in the
external-coupling / aperture geometry, not a per-shape tuning gap -- worth
investigating before spending more budget on new shapes.

**What was NOT explored, and should be next**: every geometry's search box
covered the coupling knobs (`w_iris`, `w_ext`, `y_wall`) only in the range
guessed from a single wideband screen. None of the three new geometries had
a systematic sweep of iris depth or aperture width independent of everything
else -- the Bayesian search conflates them with cavity size (`a`) in one
joint optimization, which is exactly how corner_cut's `w_iris` ended up
railed at its own saturation floor (see the `optimize.py` commit history)
without anyone noticing until the run finished.

See `docs/geometry_exploration/plan_2026-08-24.md` for what runs next.
