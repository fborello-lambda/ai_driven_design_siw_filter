---
title: "SIW Bandpass Filter — Project State"
subtitle: "2.87 GHz dual-mode SIW filter on RO4350B"
date: "2026-09-03"
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

> **2026-09-04 update — the board being fabricated is cascade N=3, not the
> dual-mode N=2 below.** Everything from here to "Reproducing this" is the
> dual-mode analysis exactly as measured on 2026-09-03 and is kept as real,
> correct physics — the bandwidth/match trade-off it documents is a genuine
> property of that topology and matters for the paper. But the fabrication
> decision it led to was **revised later the same session**: cascade N=3 is
> closer to spec on every axis (−13.37 dB / 189 MHz vs −10.76 dB / 316.6 MHz,
> at ~1.5× the board length) and was chosen instead. All fabrication
> outputs — CST macro, KiCad gerbers/drill/STEP, a 29-check
> `FAB_CHECKLIST.md`, a real-copper measurement, a PEC regression re-run
> that reproduced the golden to every digit, and the Taoglas datasheet
> verification — were built for **cascade N=3**, in `golden/cascade_N3/`.
> `siw kicad --topology cascade --N 3 --params ... --launch cpwg` reproduces
> all of it. `siw kicad --topology dualmode ...` refuses (dualmode has no
> `_geometry()` for CST/KiCad export) — that gap is real, not yet closed.
>
> **Caveat added 2026-09-06 (CST/Palace audit, `docs/audit_cst_palace/`):
> the −13.37 dB number above is NOT mesh-converged.** The repo's own
> `output/data/mesh_convergence_cascade_N3.json` refines the mesh and gets
> **−9.34 dB** (4 dB worse) with fc/BW/IL essentially unchanged; a separate
> 61-point refined-port sweep lands at a worst in-band S11 ≈ −10.56 dB —
> right around dual-mode's −10.76 dB. The "closer to spec on every axis"
> justification for fabricating cascade N=3 instead of dual-mode rests on a
> non-converged mesh and should be re-run with a real convergence study
> before being cited as settled.

\newpage

# The design

**Dual-mode N=2** — a single square SIW cavity carrying two degenerate
modes, split by an internal floating iris row.

```
a = 57.158   w_iris = 15.304   x_iris = 28.685
y_wall = 9.849   w_ext = 16.352 mm        board 119.0 mm
```

| | measured (PEC) | with real copper | target |
|---|---|---|---|
| Centre frequency | 2.904 GHz | 2.903 | 2.87 |
| Return loss (worst in band) | −10.76 dB | −10.55 | ≤ −16 |
| −3 dB bandwidth | 316.6 MHz | 317.5 | 143.5 |
| Insertion loss | −1.45 dB | −1.77 | — |
| Reflection zeros | 2 (2.787 / 2.897 GHz) | 2 | 2 |

Rounding every dimension to 0.1 mm PCB resolution costs only 0.5 dB
(−10.25 dB, 319 MHz), so the design is not perched on a knife edge.

![The final geometry against the ideal Chebyshev target. The response is
structurally correct — two reflection zeros, one clean passband, low loss —
but the nulls stop around −10 dB where the specification needs −16, and both
zeros sit below the band centre.](pec_optimized_final.png)

\newpage

# The central finding: bandwidth and match are in opposition

The specification asks for a 143.5 MHz band **and** −16 dB return loss. On
this topology those two are in direct conflict, and that is a measured
result, not a tuning failure.

Four one-dimensional scans on the **assembled filter** (not a proxy
structure), every point fine-mesh and verified:

**`w_iris` at w_ext = 15.5 mm** — the mode splitting

| w_iris (mm) | 11.0 | 12.0 | 13.0 | 14.0 |
|---|---|---|---|---|
| bandwidth (MHz) | **145.6** | 164.1 | 200.1 | 237.0 |
| return loss (dB) | −1.75 | −2.09 | −3.36 | −7.06 |

**`w_ext` at w_iris = 15.26 mm** — the launch aperture

| w_ext (mm) | 11.0 | 12.5 | 14.0 | 15.5 | 16.31 |
|---|---|---|---|---|---|
| bandwidth (MHz) | 35.0 | 65.6 | 122.1 | 284.4 | 310 |
| return loss (dB) | −0.75 | −1.18 | −2.81 | −6.86 | **−10.35** |
| passband lobes | 2 | 2 | 2 | 1 | 1 |

**`w_ext` at w_iris = 11 mm**: 120.7 / 127.7 / 145.6 / 166.4 / 366.5 MHz for
13 / 14.5 / 15.5 / 16 / 17.5 mm, return loss never better than −2.20 dB.

**`y_wall` at w_iris = 11 mm**: 147.1 / 146.7 / 153.6 / 169.1 MHz for
7.5 / 9.5 / 11 / 13 mm, return loss −1.77 to −2.27 dB — nearly inert.

**Bandwidth alone is solvable.** At `w_iris = 11 mm` the filter measures
145.6 MHz against a 143.5 MHz target — FBW 4.94 % against 5 %. The band was
never "stuck"; it spans 35–366 MHz across the geometries scanned. What
cannot be done is reaching that bandwidth *and* a usable match: return loss
improves monotonically in whichever direction widens the band, on every
parameter, with no interior optimum.

**The project has chosen the good-match end** (2026-09-03). The best return
loss this structure produces anywhere is −10.76 dB.

A 30-evaluation local Bayesian search over a 5-dimensional ±2 mm box
**confirmed** this geometry rather than improving it: neighbouring probes
came back worse, the search spent its last evaluations resampling one point,
and the 0.41 dB apparent gain over the previous best sits inside the
measured coarse-mesh noise floor (re-sampling one geometry within 0.2 mm
moved it 0.64 dB).

\newpage

# What the fabrication stack costs

**Real copper: −0.32 dB insertion loss, −0.21 dB return loss.** Centre
frequency, bandwidth and pole structure all unchanged. This is the one
trustworthy fabrication number, measured at the final geometry with the
exterior ground planes modelled as lossy copper via a surface-impedance
boundary condition.

**Soldermask, silkscreen and ENIG cannot be modelled at this mesh density**
and are excluded. This was established by a one-factor-at-a-time ladder,
each cell adding exactly one ingredient to the idealised baseline:

| ingredient | thickness | ΔIL vs PEC | return loss | reflection zeros |
|---|---|---|---|---|
| copper (boundary condition, no geometry) | — | −0.32 | −10.55 | 2 (ok) |
| soldermask | 20 µm | −2.54 | −0.98 | 3 |
| silkscreen | 12 µm | −4.02 | −0.54 | 0 |
| ENIG | 4.5 µm | −7.19 | −0.18 | 0 |

The damage scales monotonically with **thinness**, across two dielectrics
and a conductor whose material properties have nothing in common. No
physical mechanism does that; unresolved sliver elements do. Each layer
spans the whole board inside a mesh whose finest cell is 200 µm, and adding
one raises the degree-of-freedom count by only about 3 % — they are
represented by a handful of cells with aspect ratios of 50:1 to 270:1.
Resolving a 4.5 µm layer honestly would need roughly 1 µm cells, a
thousand-fold local refinement.

The numbers in that table are therefore **not** fabrication penalties. They
are the signature of a model outside its validity, and they are kept in the
figure precisely so nobody re-adds those layers expecting meaning.

![Idealised metal versus real copper (solid) — the real result. The three
thin layers (dotted) are shown only to record why they are
excluded.](fab_variant_comparison_cpwg.png)

## Consequences for the fabrication decisions

| Choice | Decision | Basis |
|---|---|---|
| Finish | ENIG | board is unsoldered and exposed; gold/nickel is a real corrosion barrier. RF effect negligible — the plating sits on the *air* side of the ground planes, so cavity fields see copper first |
| Soldermask over the feed | **open it** | engineering judgement, **not** simulation: a 20 µm eps_r 3.8 film across the 0.2512 mm coplanar gap perturbs a launch that is already the weakest part of the design |
| Silkscreen | free choice | not measurable here; physically negligible |
| Vias tented vs open | **unanswerable** | the hollow-barrel geometry only exists together with a volumetric conductor model that is itself unresolvable |

The earlier pad-only-launch fabrication study is **superseded** — its cells
ran through the same unresolved-layer path. Its one figure that survives
scrutiny is "+0.37 dB from real copper", close to today's properly measured
0.32 dB.

\newpage

# What is true right now

## Solid

- The geometry above is a **local optimum for return loss** under the CPWG
  launch, confirmed by a 30-evaluation search rather than assumed.
- It is **robust to PCB tolerances**: 0.1 mm rounding costs 0.5 dB.
- **Real copper costs 0.32 dB** and does not disturb the response shape.
- The drawn geometry **matches the meshed geometry**. `siw stackup --verify`
  is no longer a CLI command (removed 2026-09-03); the same comparison now
  runs as one of the 29 checks in `siw kicad --check` (cascade) or directly
  via `report.verify_drawing_matches_mesh()` (dualmode) — ground-stitch vias
  (16), fence vias (78), the 10-vertex feed outline including the CPWG pad
  taper, and the coplanar gap, all passing.

## Not true, and now understood

- **Return loss misses spec**: −10.76 dB against −16 dB.
- **Bandwidth misses spec**: 316.6 MHz against 143.5 MHz.
- These are **one trade, not two faults**. Either can be met alone; neither
  can be met together on this topology. Meeting the bandwidth costs the
  match entirely (−1.75 dB at 145.6 MHz).
- **The fabrication stack is unquantified** beyond copper, and cannot be
  quantified without a mesh this machine cannot build.
- **No board has been ordered.** No CST export, no gerbers, no DRC check.

\newpage

# The one habit that matters

**Fifteen silent bugs have now been found in this project's own model.** Not
one raised an error; every one produced plausible numbers that were wrong.
Today added four, and the last of them took three attempts to diagnose:

- an objective term that silently steered every search *away* from the best
  design, because `optimize()` never forwarded the weights it accepted;
- a "bandwidth curve" that was really the width of one of two disjoint
  passbands at three of its four points, so inverting it aimed the search at
  a discontinuity;
- an exterior-face flag hardcoded `True`, correct for a bare board and wrong
  the moment layers sit above it;
- thin fabrication layers meshing as slivers and destroying the response.

Three lessons, each paid for today:

1. **If a fix does not change the number, the diagnosis was wrong.** Two
   confident explanations of the −29 dB stack failure were falsified this
   way, each in one re-run.
2. **After two wrong inferences, stop inferring.** The one-factor ladder
   settled in four solves what argument had failed to settle twice — and it
   immediately exonerated the leading suspect.
3. **A correct mechanism aimed at the wrong component is still wrong.** The
   skin-depth arithmetic was right; it was applied to the vias, which were
   fine, instead of to the layers, which were not.

**Before trusting any result, check it against what physics says it should
be.** Insertion loss cannot beat a lossless model. A lossy stack cannot cost
27 dB. Pole count must match the filter order. A hole far below cutoff
cannot radiate.

Guards now in the code:

- `_driven_config` raises if a mesh domain has no material;
- the mesh builder reports any unclassified exterior face, and raises on an
  empty mesh instead of handing Palace something valid-looking but empty;
- `band_edges` reports `n_lobes`, so a split response can never again be
  read as a narrow one;
- `siw scan` excludes split points from its inversion and says why;
- the fabrication runner flags any variant whose loss beats the lossless
  reference, or is more than 6 dB worse, or shows near-total reflection, or
  reports zero reflection zeros;
- the drawing-vs-mesh comparison (`report.verify_drawing_matches_mesh` /
  `verify_cascade_drawing_matches_mesh`, folded into `siw kicad --check`)
  compares the drawing against the meshed geometry vertex by vertex.

\newpage

# Reproducing this

```bash
# the design
siw design --topology dualmode --N 2 \
    --seed a=57.21,w_iris=15.26,x_iris=28.68,y_wall=8.62,w_ext=16.31 \
    --span 2 --patience 14 --evals 30 --w-bw 0 --device CPU --np 8

# the fabrication study
siw compare-fab-variants --run \
    --params a=57.158,w_iris=15.304,x_iris=28.685,y_wall=9.849,w_ext=16.352 \
    --N 2 --device CPU --np 4

# the trade-off scans
siw scan --topology dualmode --N 2 \
    --params a=57.21,x_iris=28.68,y_wall=8.62,w_ext=15.5 \
    --scan 'w_iris=11,12,13,14' --device CPU --np 8

# artifacts
siw layout --topology dualmode --N 2 \
    --params a=57.158,w_iris=15.304,x_iris=28.685,y_wall=9.849,w_ext=16.352

# fabrication outputs for the topology actually being sent to fab (see the
# 2026-09-04 update above) -- cascade N=3, not this dual-mode design
siw kicad --topology cascade --N 3 \
    --params l_cav1=34.239,l_cav2=35.503,w_iris=14.416,w_ext=13.96,l_taper=15.738,w_ms=1.6636 \
    --launch cpwg
```

**Resource limits, learned the hard way:** fabrication-stack solves need
`--np 4` on this 15 GB machine — eight ranks are killed mid-sweep by the OOM
killer — and cost about 32 minutes each.

## Building this document

```bash
cd docs && uv run gen_pdfs.py --force STATE.md   # needs xelatex
pandoc STATE.md -o state.html --standalone --embed-resources --toc
```
