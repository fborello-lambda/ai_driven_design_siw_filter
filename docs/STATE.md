---
title: "SIW Bandpass Filter — Project State"
subtitle: "2.87 GHz dual-mode SIW filter on RO4350B"
date: "2026-09-02"
lang: en
geometry: margin=2.5cm
papersize: a4
fontsize: 11pt
colorlinks: true
toc: true
toc-depth: 2
---

\newpage

# The goal

A Substrate Integrated Waveguide (SIW) bandpass filter:

| Parameter | Target |
|---|---|
| Centre frequency | 2.87 GHz |
| Bandwidth | 143.5 MHz (5 % FBW) |
| Return loss | at most −16 dB in band |
| Response | Chebyshev, 0.1 dB ripple |
| Substrate | Rogers RO4350B, 0.76 mm, 0.5 oz copper (17.5 µm) |
| Vias | Ø1.5 mm, 3.0 mm pitch |
| Connector | Taoglas EMPCB.SMAFSTJ.B.HT, CPWG launch |

For what to do next, see `PLAN.md`. Superseded documents are in
`docs/archive/`.

\newpage

# The design we are building

**Dual-mode N=2** — a single square SIW cavity carrying two degenerate
modes, split by an internal floating iris row.

Geometry: `a = 57.21`, `w_iris = 15.26`, `x_iris = 28.68`,
`y_wall = 8.62`, `w_ext = 16.31` mm.

## Why this one, and not a cascade

Three candidates were compared head to head on identical axes:

| | dual-mode N=2 | cascade N=3 | cascade N=4 |
|---|---|---|---|
| Return loss | **−17.7 dB** | −14.9 dB | −6.1 dB |
| Insertion loss | **−1.42 dB** | −1.85 dB | −2.7 dB |
| Board length | **119 mm** | 172 mm | 211 mm |
| Spurious to 8 GHz | **clean** | 2nd passband nearly as strong as the main one | same problem |

![Dual-mode N=2 versus the two cascade designs, same axes. The dual-mode
response has the deepest return-loss nulls; the cascades were rejected
mainly for their spurious passbands, visible in the broadband
check.](design_comparison_sparams.png)

![Board footprint at true relative scale. The dual-mode design is roughly
half the length of the N=4 cascade.](design_comparison_board_scale.png)

The cascade designs are **parked, not abandoned** — they are a real
comparative result, and their spurious passbands are the reason they were
not chosen.

\newpage

# The fabrication stack

The board is modelled with its real manufacturing layers, not as idealised
metal: lossy copper, ENIG finish, soldermask, silkscreen, and filled or
open via barrels are all genuine geometry and materials.

![Fabrication stack at the feed. Vertical scale is non-linear so the thin
finish layers remain visible; true thicknesses are labelled. Left: feed
covered by soldermask. Right: soldermask opened over the feed, the
recommended option.](stackup.png)

![Top view showing where each layer sits, including the impedance-matched
CPWG launch (0.2512 mm gap, 6 stitch vias per side) and the pad taper into
the 50 Ω microstrip. The bottom panel zooms on the launch, where the
coplanar gap is sub-pixel at board scale.](stackup_topview.png)

## What the stack costs

![Idealised PEC metal versus the real fabrication stack, with the ideal
Chebyshev target for reference. Note these runs used the earlier pad-only
launch — the mechanisms hold, the absolute numbers are being
re-measured.](fab_variant_comparison.png)

| Variant | fc (GHz) | IL (dB) | BW (MHz) | Return loss (dB) |
|---|---|---|---|---|
| PEC (idealised) | 2.911 | −1.42 | 318 | −17.69 |
| Real stack, vias tented | 2.909 | −1.79 | 298 | −12.48 |
| Real stack, vias open | 2.909 | −1.79 | 298 | −12.47 |
| Real stack, no silkscreen | 2.907 | −1.79 | 297 | −12.50 |

Three findings, each measured:

1. **Return loss is the fabrication penalty.** The dielectric stack over the
   feed detunes the launch by roughly 5 dB. Insertion loss is a side issue.
2. **Real copper costs about 0.37 dB of insertion loss** that a
   perfect-conductor model omits entirely.
3. **Via tenting and silkscreen are electrically irrelevant** — all three
   real-stack variants agree to within 0.03 dB, below solver noise. Do not
   pay for via filling on RF grounds.

\newpage

# What is true right now

## Solid

- The dual-mode geometry meets the return-loss target **under an idealised
  model** (PEC metal, pad-only launch): −17.7 dB, 2 reflection zeros, clean
  to 8 GHz.
- The fabrication stack is modelled for real, and its cost is quantified
  above.

## Not true yet

- **Bandwidth is about 2× the specification** (about 300 MHz against 143.5 MHz).
  This is the oldest open problem, and no fabrication choice affects it. It
  requires the cavity coupling to be re-derived, not a launch adjustment.
- **Nothing has been optimised under the CPWG launch.** It was merged into
  the dual-mode model on 2026-09-02; every dual-mode measurement predating
  that used the pad-only launch and is archived in
  `golden/dualmode_N2/archive_padonly_launch/`.
- **No board has been ordered.** No CST export, no gerbers, no DRC check.

\newpage

# Building this document

Pandoc-compatible with YAML front matter and relative image paths.

```bash
cd docs && uv run gen_pdfs.py --force STATE.md   # needs xelatex
```

`xelatex` is not installed on the development machine, so the PDF has to be
built where a LaTeX toolchain exists. Any pandoc target works without it,
for example a single self-contained HTML file with the figures embedded:

```bash
pandoc STATE.md -o state.html --standalone --embed-resources --toc
```

# How to reproduce these figures

```bash
siw stackup --verify      # stack cross-section and top view, plus a check
                          # that the drawing matches the meshed geometry
siw compare-designs       # dual-mode versus the cascade designs
siw compare-fab-variants  # idealised metal versus the real stack
siw layout --topology dualmode --N 2 \
    --params a=57.21,w_iris=15.26,x_iris=28.68,y_wall=8.62,w_ext=16.31
```

# The one habit that matters

**Seven silent bugs were found in this project's own model.** Not one raised
an error; every one produced plausible numbers that were wrong:

- a layer was added to the mesh but never given a material, so its faces
  carried no boundary condition — the solver warned, computed anyway, and
  returned *less* loss than a lossless conductor;
- a figure was drawn from a different preset than the mesh used, so
  published pictures showed a launch that had never been simulated;
- an adapter silently dropped feature data, so two fabrication studies ran
  with the feature switched off.

Each was caught by checking a number against physics, never by the code
failing. **Before trusting any result, check it against what physics says it
should be.** Insertion loss cannot beat a lossless model. Pole count must
match the filter order. A hole far below its cutoff frequency cannot
radiate.

Guards now in the code:

- `_driven_config` raises if a mesh domain has no material;
- the mesh builder reports any unclassified exterior face;
- `siw stackup --verify` compares the drawing against the meshed geometry
  vertex by vertex.
