# Where this project stands — 2026-09-02

One page. What exists, what is true, what is not yet true.
For the plan, see `PLAN.md`. Superseded documents are in `docs/archive/`.

---

## The goal

A Substrate Integrated Waveguide bandpass filter:

| | |
|---|---|
| Centre frequency | 2.87 GHz |
| Bandwidth | 143.5 MHz (5 % FBW) |
| Return loss | ≤ −16 dB in band |
| Response | Chebyshev, 0.1 dB ripple |
| Substrate | Rogers RO4350B, 0.76 mm, 0.5 oz copper (17.5 µm) |
| Vias | Ø1.5 mm, 3.0 mm pitch |
| Connector | Taoglas EMPCB.SMAFSTJ.B.HT, CPWG launch |

---

## The design we are building

**Dual-mode N=2** — a single square SIW cavity carrying two degenerate
modes, split by an internal floating iris row. Chosen over the alternatives
after a head-to-head comparison:

| | dual-mode N=2 | cascade N=3 | cascade N=4 |
|---|---|---|---|
| Return loss | **−17.7 dB** | −14.9 dB | −6.1 dB |
| Insertion loss | **−1.42 dB** | −1.85 dB | −2.7 dB |
| Board length | **119 mm** | 172 mm | 211 mm |
| Spurious to 8 GHz | **clean** | 2nd passband nearly as strong as the main one | same problem |

Geometry: `a=57.21, w_iris=15.26, x_iris=28.68, y_wall=8.62, w_ext=16.31` mm.

The cascade designs are **parked, not abandoned** — they are a real
comparative result, and their spurious passbands are the reason they were
not chosen.

---

## What is actually true right now

### Solid
- The dual-mode geometry above meets return-loss spec **under an idealised
  model** (PEC metal, pad-only launch): −17.7 dB, 2 poles, clean to 8 GHz.
- The fabrication stack is modelled for real: lossy copper, ENIG, soldermask,
  silkscreen, and filled-vs-open vias are all genuine geometry/materials, not
  approximations.
- Three fabrication findings, each measured:
  1. **Return loss is the fabrication penalty** — the dielectric stack over
     the feed detunes the launch by ~5 dB. Insertion loss is a side issue.
  2. **Real copper costs ~0.37 dB of insertion loss** that a PEC model omits.
  3. **Via tenting and silkscreen are electrically irrelevant** (< 0.03 dB).
     Do not pay for via filling on RF grounds.

### Not true yet
- **Bandwidth is ~2× the spec** (≈300 MHz vs 143.5 MHz). This is the oldest
  open problem and no fabrication choice affects it. It needs the cavity
  coupling re-derived, not a launch tweak.
- **Nothing has been optimised under the CPWG launch.** It was merged into
  dual-mode on 2026-09-02; every dual-mode number predating that used the
  pad-only launch and is archived accordingly.
- **No board has been ordered.** No CST export, no gerbers, no DRC check.

---

## How to look at it

```bash
siw stackup --verify        # fabrication stack, top view + cross-section,
                            # and a check that the drawing matches the mesh
siw compare-designs         # dual-mode vs cascade, same axes
siw compare-fab-variants    # PEC vs the real fabrication stack
siw layout --topology dualmode --N 2 --params a=57.21,w_iris=15.26,x_iris=28.68,y_wall=8.62,w_ext=16.31
```

---

## The one habit that matters

**Seven silent bugs were found in this project's own model.** Not one raised
an error; every one produced plausible numbers that were wrong. Examples:

- a layer was added to the mesh but never given a material, so its faces had
  no boundary condition — the solver warned, then computed anyway, and
  returned *less* loss than a lossless conductor;
- a figure was drawn from a different preset than the mesh used, so published
  pictures showed a launch that had never been simulated;
- an adapter silently dropped feature data, so two fabrication studies ran
  with the feature switched off.

Each was caught by checking a number against physics, never by the code
failing. So: **before trusting any result, check it against what physics
says it should be.** Insertion loss cannot beat a lossless model. Pole count
must match the filter order. A sub-cutoff hole cannot radiate.

Standing guards now in the code: `_driven_config` raises if a mesh domain
has no material; the mesh builder reports any unclassified exterior face;
`siw stackup --verify` compares the drawing against the meshed geometry
vertex by vertex.
