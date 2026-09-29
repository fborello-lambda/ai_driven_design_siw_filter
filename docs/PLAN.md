# Plan — from here to a fabricated board

Current state: `STATE.md`. Superseded plans: `docs/archive/`.

> **Update 2026-09-23:** the decision below was made — the fabricated board is
> the cascade N=3 with the end cavities trimmed −0.3 mm (`l_cav1` = 33.939 mm).
> Verdict, JLCPCB order notes and the fab package: `final_check/REPORT.md`,
> `final_check/fab/`.

The design work is **done**, in the sense that the design space has been
mapped and the remaining gap is understood rather than mysterious. What is
left is a decision, then fabrication outputs.

---

## The decision that gates everything

The specification cannot be met by this topology. Bandwidth and return loss
are in direct opposition on every geometry parameter (see `STATE.md`, "the
central finding"), and either can be met alone:

| option | bandwidth | return loss | note |
|---|---|---|---|
| **good match** (current design) | 316.6 MHz | **−10.76 dB** | 2.2× the target band |
| good bandwidth | **145.6 MHz** | −1.75 dB | essentially unmatched |
| spec | 143.5 MHz | −16 dB | not reachable together here |

**Decision taken 2026-09-03: the good-match end.** The current design is
that choice, optimised and confirmed.

Three ways forward, in the order I would consider them:

1. **Accept and fabricate.** Write the deviation down explicitly — a
   316.6 MHz, −10.76 dB filter at 2.90 GHz — and order the board. Reasonable
   if the real requirement is "a working S-band cavity filter" rather than
   the literal numbers.
2. **Change the topology.** N=2 dual-mode has one internal coupling and one
   external coupling; that is not enough freedom to place two poles *and*
   match them. A cascade of two single-mode cavities has an extra degree of
   freedom, at roughly 1.5× the board length. The parked cascade N=3 data is
   in `golden/cascade_N3/`.
3. **Relax the specification.** If 5 % FBW is a nice-to-have and return loss
   is the real requirement, the current design already satisfies the
   requirement that matters.

**This is a user decision, not a technical one.** Nothing further should be
optimised until it is made.

> **Decision revised, 2026-09-04: option 2, cascade N=3.** Closer to spec on
> every axis (−13.37 dB / 189 MHz, fine-confirm −14.92 dB / 188 MHz, vs
> dual-mode's −10.76 dB / 316.6 MHz), at ~1.5× the board length (166.4 vs
> 119.0 mm). Steps 2 and 3 below are now DONE for this design — see the
> status block that follows — not merely planned.
>
> **Caveat added 2026-09-06, found during the CST/Palace audit
> (`docs/audit_cst_palace/`): the −13.37 dB S11 above is NOT mesh-converged.**
> `output/data/mesh_convergence_cascade_N3.json` (already in the repo,
> predates this audit) refines the mesh from (3.5, 0.6, 6.0) mm to
> (2.5, 0.45, 6.0) mm and S11w gets **4 dB worse** (−13.37 → −9.34 dB), while
> fc/BW/IL barely move. A separate 61-point sweep with refined ports
> (`docs/audit_cst_palace/AUDITORIA.md` §4) independently lands in the same
> place: worst in-band S11 ≈ −10.56 dB. So cascade N=3's real match is
> probably close to dual-mode's −10.76 dB, not the −13.37 dB this decision
> was made on — the "closer to spec on every axis" claim above needs
> re-checking against a real mesh-convergence study before it's trusted.

---

## Status, 2026-09-04 (cascade N=3, the board actually being ordered)

- PEC regression (121-point sweep, after today's real-copper port rework
  and a board-outline fix): reproduces the golden to every digit —
  fc 2.879 GHz, IL −1.85 dB, BW 189 MHz, S11w −13.37 dB.
- Real copper measured (exterior ground planes only, Palace's
  `Boundaries.Conductivity` is exterior-only so via barrels and the trace
  stay PEC): IL −1.85 → −2.44 dB, S11w −14.92 → −13.82 dB, shape and
  bandwidth unmoved. Recorded in `golden/cascade_N3/...json`.
- CST `.bas` (`siw cst`) and KiCad board + gerbers/drill/STEP/SVG
  (`siw kicad`) both generate from the same `Geometry`/launch objects the
  mesher uses, not a second description of the board.
- `siw kicad --check` runs 29 file-level + connector-fit checks against the
  actual generated gerbers/drill/`.bas` (not the code that wrote them) and
  writes `FAB_CHECKLIST.md`. All 29 pass on the current geometry.
- Taoglas EMPCB.SMAFSTJ.B.HT verified against its real datasheet
  (`docs/sma_connector/`): pin and ground-leg-pitch numbers were already
  exact; the finished board (0.795 mm) fits the connector's 0.8 mm/0.79 mm
  limits with no margin, which is why 0.5 oz copper is a requirement, not a
  preference.
- **Still open**: the deviation from spec itself (table above) is accepted,
  not fixed, and remains what it is — write it into the fab order. No mesh
  convergence study exists for `fc` (see "Later" below — never done, would
  put an error bar on every frequency quoted here, including the +0.31 %
  currently recorded against spec).

---

## Step 1 — Optional: re-polish on real copper (dual-mode only; moot for cascade)

This was scoped for the dual-mode design before the decision was revised.
Cascade N=3's real-copper number is already measured (see the status block
above) at zero extra search cost, so this step does not apply to the board
actually being built. Left here in case dual-mode is ever revisited:

```bash
siw design --topology dualmode --N 2 \
    --seed a=57.158,w_iris=15.304,x_iris=28.685,y_wall=9.849,w_ext=16.352 \
    --span 2 --patience 14 --evals 12 --w-bw 0 --real-metal --device CPU --np 4
```

Real copper shifts that design by 0.32 dB of insertion loss and 0.21 dB of
return loss without changing its shape, close to the coarse-mesh noise
floor; twelve evaluations cost about 6.5 hours. Do **not** pass `--enig`: it
implies ENIG + soldermask + silkscreen, all unresolvable at this mesh
density and destroy the response.

---

## Step 2 — Fabrication outputs — DONE for cascade N=3

```bash
siw kicad --topology cascade --N 3 \
    --params l_cav1=33.939,l_cav2=35.503,w_iris=14.416,w_ext=13.96,l_taper=15.738,w_ms=1.6636 \
    --launch cpwg
```

- [x] CST `.bas` export (`siw cst`) — StoreParameter'd, real Taoglas SMA
  coax stubs + coaxial ports. Visual check in CST is still the human's to
  do; the generator-side unit bugs found while checking it are fixed.
- [x] Gerbers with the soldermask **fully open** (the decision made, not
  opened only over the feed as this step used to say — see
  `FAB_NOTES.md`'s explanation of how "no mask" is expressed in gerber).
- [x] JLCPCB DRC re-check against `config.py`'s `FAB_RULES`, plus five
  connector-fit checks against the real Taoglas datasheet — `siw kicad
  --check`, 29/29 passing, `FAB_CHECKLIST.md`.
- [x] ENIG finish, vias open/unfilled — stated in `FAB_NOTES.md`.

---

## Step 3 — Order the board

Only once the decision above is written down. Do not ship a board that
silently misses spec. For cascade N=3 the deviation is on record in
`FAB_CHECKLIST.md`'s "Known deviations from specification" table, sourced
from `golden/cascade_N3/`.

---

## Later

- **Paper** — "AI-Driven Design for SIW Filters". The strongest material is
  already collected, and most of it is negative or methodological:
  - a *structural* obstacle to black-box optimisation — an objective term
    that is discontinuous in the external coupling, plus the discovery that
    the objective's own bandwidth weight steered every search away from the
    best design;
  - **fifteen silent modelling bugs**, none of which raised an error;
  - the calibrate-and-invert failure with its mechanism (a dual-mode
    cavity's two resonators are two modes of one cavity, so no proxy can
    isolate one);
  - the bandwidth/match opposition as a measured property of the topology;
  - the limits of thin-layer modelling at practical mesh densities.
- **Mesh convergence study** for `fc` — never done; would put an error bar
  on every frequency in this project.

---

## Do not redo

- **The fabrication stack study.** Soldermask, silkscreen and ENIG are
  unresolvable at this mesh density; the measured "penalties" scale with
  layer *thinness*, which is the signature of sliver elements, not physics.
  Re-running them produces the same meaningless numbers.
- **Volumetric lossy-conductor vias.** Same problem, and the hollow-barrel
  geometry is gated on them, which is why tented-vs-open is unanswerable.
- **Calibrate-and-invert on dual-mode.** The Qe proxy measures a different
  structure (3.01 GHz vs the design's 2.89 GHz); proxy loaded-Q 8.29 against
  the assembled filter's 8.66 proves it. Two coupled resonators cannot share
  the loaded Q of one.
- **Compact N=4 dual-mode cascade** — five mechanisms plus a joint search all
  hit the same ceiling. Raw data in `docs/geometry_exploration/`.
- **Lossy-conductor boundary conditions on internal surfaces** — Palace's
  `Conductivity` BC is exterior-only. It works correctly on the exterior
  ground planes, which is why the real-copper result is trustworthy.
- **A second launch definition.** There is one, in `topologies/launch.py`,
  plus an explicitly-named pad-only alternative. Forking it caused three
  separate bugs.
