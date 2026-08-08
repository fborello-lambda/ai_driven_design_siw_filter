# SMA connector modeling — findings and status

Branch `sma_conn`. Answers a question raised after a presentation: the SIW
filter had only ever been simulated with an idealized wave/lumped port
sitting directly on the microstrip trace. That kind of port self-normalizes
to whatever the local trace impedance happens to be, so it can't reveal
whether the trace is actually 50 ohm, or what a real SMA launch does to the
response. This work adds a real 3D coax launch to the Palace driven model
(`src/siwfilter/palace_driven.py`, `build_mesh(..., with_sma=True)`) and
re-tunes the filter against it.

## v1 — first attempt, and what it found

![v1: broken result](v1_broken_pin.png)

First pass modeled the coax launch at full SMA/RG-401 body size (pin radius
0.82 mm, PTFE OD 2.73 mm — the standard cable dimensions). Two things came
out of it:

1. **The idealized-port methodology was hiding a real problem.** Computing
   the actual microstrip impedance for the existing design (`W_ms = 2.26 mm`
   on 0.76 mm RO4350B) gives ≈41 Ω, not 50 Ω — `W_ms` had been tuned to
   2.26 mm specifically because it "looked" better matched against the
   self-normalizing port, not because it's a real 50 Ω line. True 50 Ω width
   for this substrate/thickness is 1.664 mm.
2. **The full-size pin made it much worse than that alone would explain.**
   With the coax launch attached, worst-case in-band S11 came out at
   **-0.2 dB** — essentially total reflection, far beyond what a ~41→50 Ω
   mismatch predicts on its own. Root cause: a pin radius of 0.82 mm is
   *larger than the board itself* (0.76 mm thick). Bisection showed this
   reproduces even on a bare 50 Ω line with no filter at all, and confirmed
   it's genuine physics, not a bug — real connectors for boards this thin
   use a proportionally thinner launch pin for exactly this reason.

Reproduce: `uv run python scripts/sma_compare_run.py` (baseline vs. v1
connector), `scripts/sma_compare_plot.py` for the figure.

## Connector geometry, and the bugs along the way

`build_mesh(with_sma=True)` bolts a coax stub (pin + PTFE + grounded shell)
onto each feed end, beyond the existing board edge — the SIW/taper/feed
pipeline itself is untouched. Getting this right took a few rounds:

![connector geometry](geometry.png)

- **Ring-severing bug (fixed).** The shell needs a ground path to the
  board's bottom plane, which means clipping some of the PTFE cylinder to
  z≥0. Doing this over the *whole* stub length severs the coax ring into a
  simply-connected "C" cross-section wherever the pin radius exceeds the
  board thickness (both the pin and shell hit z<0 at the bottom angle) — a
  simply-connected port cross-section has no TEM mode, only evanescent
  higher modes, which is a second, independent way to get catastrophic
  S11. Fixed by clipping only a short (~1.5 mm) ground-contact segment right
  at the board edge, leaving the port face and most of the stub a proper
  unbroken ring. Verified against Palace's own `examples/coaxial` (finds
  clean TEM, Z=50.0Ω on an unclipped ring) before and after.
- **Oversized pin (fixed, see v1 above).** Not a code bug — a genuine
  physical mismatch from using full cable-size dimensions on a thin board.

## Key files

- `src/siwfilter/palace_driven.py` — `build_mesh(with_sma=True, ...)`: the
  coax launch geometry, bolted onto the existing feed.
- `scripts/sma_compare_run.py`, `sma_compare_run_with_only.py`,
  `sma_compare_plot.py` — v1 discovery (with/without connector on the old
  design).
- `output/data/versions/sma-v1.json` — machine-readable manifest of the v1
  finding (params, numbers, what changed).

## Status

v1 established that the idealized-port methodology was hiding a real
mismatch, and that a naively-sized (full cable-spec) connector makes it
look far worse than it is. Next: size the connector to the board, re-tune
the filter against the real connector model. See git log for the v2 update
to this doc.
