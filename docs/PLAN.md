# Plan — from here to a fabricated board

Current state: `STATE.md`. Superseded plans: `docs/archive/`.

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

---

## Step 1 — Optional: re-polish on real copper

```bash
siw design --topology dualmode --N 2 \
    --seed a=57.158,w_iris=15.304,x_iris=28.685,y_wall=9.849,w_ext=16.352 \
    --span 2 --patience 14 --evals 12 --w-bw 0 --real-metal --device CPU --np 4
```

**Probably not worth it.** Real copper shifts the design by 0.32 dB of
insertion loss and 0.21 dB of return loss without changing its shape, which
is close to the coarse-mesh noise floor; twelve evaluations cost about
6.5 hours. The alternative is to accept the PEC-optimised geometry with the
copper penalty applied — the numbers are already measured and in the golden
entry.

Do **not** pass `--enig`: it implies ENIG + soldermask + silkscreen, all of
which are unresolvable at this mesh density and destroy the response.

---

## Step 2 — Fabrication outputs

- CST `.bas` export (`cst_export.py`) and a visual check in CST.
- Gerbers, with the **soldermask opened over the feed** (judgement call, see
  `STATE.md` — not a simulated result).
- JLCPCB DRC re-check against `config.py`'s recorded capabilities.
- ENIG finish, vias open/unfilled (tenting is not measurable and is
  electrically irrelevant at this via size).

---

## Step 3 — Order the board

Only once the decision above is written down. Do not ship a board that
silently misses spec.

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
