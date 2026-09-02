# Plan — from here to a fabricated board

Current state: `STATE.md`. Superseded plans: `docs/archive/`.

Two things stand between the design and a board worth ordering:

1. **Bandwidth is ~2× spec** (about 300 MHz vs 143.5 MHz) — a cavity-coupling
   problem, unaffected by any fabrication choice.
2. **Nothing has been optimised under the CPWG launch**, which is now what
   dual-mode actually simulates.

Step 1 addresses both at once.

---

## Step 1 — Re-optimise under the CPWG launch  ← *next*

Two stages, because PEC solves are cheaper than full-stack ones and there is
no reason to pay for the fabrication mesh while the search is still coarse.

**1a. Global search, PEC metal**
```bash
siw design --topology dualmode --N 2 --evals 45 --patience 14 --np 8
```
All five geometry parameters move (`a, w_iris, x_iris, y_wall, w_ext`).
Bandwidth is already a two-sided term in `score()` (`w_bw=3.0`), so it is
targeted, not merely reported.

**RESULT of 1a (2026-09-02): the search failed, and the CPWG launch hurt.**

The global search early-stopped after 15 of 45 evals -- 14 consecutive
evals with no improvement -- and never beat the geometry it was seeded
with. Fine confirm of that geometry under CPWG + PEC:
`fc=2.901 GHz, S11w=-10.35 dB, BW=310 MHz, IL=-1.46 dB`.

The same geometry measured **-17.7 dB** under the pad-only launch, so the
CPWG launch costs about **7 dB of return loss** on this cavity. That launch
was solved to 50 ohm for the *cascade*, not for dual-mode. Porting it over
made things worse, not better.

Two conclusions:

1. Black-box search is the wrong tool here -- a GP that cannot beat a free
   seed in 14 attempts indicates a mis-centred box, the same signature the
   cascade showed before calibrate-and-invert rescued it.
2. The launch itself needs matching to the dual-mode cavity, not adopting
   wholesale from another topology.

**1b. Fabrication-stack comparison at FIXED 1a geometry -- BLOCKED**

The `pec` cell completed (numbers above). Both real-stack cells failed:
gmsh could not recover the boundary mesh and produced an empty mesh
(`nodes=0 tets=0`), so Palace had nothing to solve.

The identical stack meshed fine (77-80k nodes) under the pad-only launch in
the earlier fabrication study, so this is specific to **CPWG + thin fab
layers**: the 4.5 um ENIG and 12 um silkscreen prisms spanning the 0.2512 mm
coplanar gap are extreme-aspect-ratio slivers.

Separately, a **gmsh state leak** turned one failure into two -- after the
failed mesh gmsh stayed initialised ("Gmsh has already been initialized /
I'm busy!"), poisoning the next build in the same process. Worth fixing on
its own: one mesh failure silently corrupts everything after it.

**1b-old (still valid).** The equivalent study under the pad-only launch DID
complete, and its mechanism-level findings carry over: return loss is the
dominant fabrication penalty, real copper costs about 0.37 dB of insertion
loss, and via tenting and silkscreen are electrically irrelevant (<0.03 dB).
See `golden/dualmode_N2/archive_padonly_launch/`.

**1b-superseded. Original fixed-geometry comparison plan**

Take 1a's winning geometry unchanged and evaluate it three ways. This
isolates what the fabrication stack costs *this* geometry, before any
re-tuning is allowed to mask it:

| Cell | Metal | Stack | Vias |
|---|---|---|---|
| `pec` | PEC (idealised) | none | — |
| `real_tented` | real copper + ENIG | soldermask + silkscreen | filled + capped |
| `real_open` | real copper + ENIG | soldermask + silkscreen | open plated barrel |

Same geometry in all three, so any difference is the stack alone. Expect
return loss to drop (the stack detunes the launch) and insertion loss to
rise about 0.4 dB (real copper). Tented versus open should be negligible;
it was under the pad-only launch, and the via hole is far below its cutoff.

**1c. Polish, full fabrication stack**
```bash
siw design --topology dualmode --N 2 --seed <1a best> --span 2 \
           --patience 14 --evals 30 --np 8 --enig --real-metal
```

**1d. Regenerate every artifact**

New goldens tagged `cpwg_taoglas`, then `siw compare-designs`,
`siw compare-fab-variants`, `siw layout` and `siw stackup --verify`, then
update STATE.md and rebuild the PDFs.
`--enig` applies real copper + ENIG + soldermask + silkscreen + open vias to
every evaluation. `fixed_extras()` keeps these out of the search box — they
are conditions, not dimensions — so 1a and 1b stay comparable.

**Done when:** return loss at most −16 dB **and** bandwidth within about 10 % of
143.5 MHz, both under the full stack, with 2 reflection zeros.

**If bandwidth stalls** (it has resisted several searches before): stop
searching and calibrate. Measure `k12(w_iris)` and `Qe(w_ext)` on small
structures, invert for the 5 % FBW targets (`k12 about 0.069`, `Qe about 16.9`), and
assemble. This is the method that worked for the cascade after black-box
search failed; the failure mode is that bandwidth is *discontinuous* in the
external coupling, which a smooth-function optimiser cannot model.

**Check every result before believing it.** Insertion loss can never beat
the PEC reference. Pole count must be 2. See `STATE.md`, "the one habit that
matters".

---

## Step 2 — Lock the fabrication spec

Mostly decided already; confirm the one open item.

| Choice | Decision | Basis |
|---|---|---|
| Finish | **ENIG** | board is unsoldered and exposed; gold/nickel is a real corrosion barrier, OSP is a pre-solder film |
| Vias | **open, unfilled** | measured < 0.03 dB difference; do not pay for filling |
| Silkscreen | **free choice** | electrically irrelevant |
| Soldermask over the feed | **open it — to be confirmed** | reasoned from mechanism; the confirming run was cancelled and never completed |

Run the remaining confirmation:
```bash
siw sweep --topology dualmode --N 2 --params <final geometry> --real-metal --enig
# versus the same geometry with the mask opening over the feed
```

---

## Step 3 — Produce fabrication outputs

- CST `.bas` export (`cst_export.py`) and a visual check in CST.
- Gerbers with the soldermask opening per Step 2.
- JLCPCB DRC re-check against `config.py`'s recorded capabilities.
- Save the final design as a golden entry tagged `cpwg_taoglas`.

---

## Step 4 — Order the board

Only once Step 1's acceptance criteria are met, or the deviation is
explicitly accepted and written down. Do not ship a board that silently
misses spec.

---

## Later

- **Paper** — "AI-Driven Design for SIW Filters". The strongest material is
  already collected: black-box optimisation failing on a *structural*
  obstacle (a discontinuous objective) rather than a tuning one; the
  seven-bug taxonomy of silent modelling failures; and honest negative
  results (the N=4 compact cavity, the via-fill null with its stated
  mechanism).
- **Mesh convergence study** for `fc` — never done; would put an error bar
  on every frequency reported.

---

## Do not redo

- **Compact N=4 dual-mode cascade** — five structurally different mechanisms
  plus a joint search all hit the same ceiling. Raw data in
  `docs/geometry_exploration/`.
- **Lossy-conductor boundary conditions on internal surfaces** — Palace's
  `Conductivity` BC is exterior-only. Use a volumetric conductor domain
  instead; the boundary-tag approach silently produces invalid results.
- **A second launch definition.** There is one, in `topologies/launch.py`.
  Forking it caused three separate bugs. If a genuinely different launch is
  ever needed, add a new named dict and tag its results distinctly.
