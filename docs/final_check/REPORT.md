# Final pre-fab check — cascade N=3 (2026-09-23)

**Verdict: GO, as a prototype that deviates from spec in writing. It is not a
spec-compliant part.** Every model agrees on the passband: fc ≈ 2.872 GHz,
BW ≈ 184 MHz, IL ≈ 2.0 dB. None of them reaches the −16 dB return-loss spec.
The coupling-matrix fit below says why, and the error is small enough that
retuning before we have a measured board isn't worth it.

## 1. Board verification

`siw kicad --topology cascade --N 3 --params <golden> --launch cpwg` was re-run
into a scratch directory and diffed against `output/kicad/`:

- Gerbers (F/B Cu, masks, silk, Edge.Cuts) and PTH/NPTH drill match
  `output/kicad/` **line for line apart from timestamps**. The board being
  uploaded is the one in the golden.
- **33/33 automated file-level checks pass.** The 34th (drawn geometry = meshed
  geometry) was skipped this time to save memory. It passed on 2026-09-06 on the
  same geometry and is still ticked in `output/kicad/FAB_CHECKLIST.md`.
- Items still marked for **manual** confirmation with the fab:
  - Laminate must really be **RO4350B 0.76 mm** (JLCPCB defaults to FR-4, which invalidates the design).
  - **No soldermask**: say so in the order notes.
  - **Hole-to-edge clearance of 0.25 mm** on the launch stitching vias.
  - **0.5 oz copper is load-bearing.** The finished stack is 0.795 mm against the SMA fork's 0.80 mm maximum. 1 oz copper does not fit.

## 2. Final Palace run — did not complete, and why

`run_final.py` combines every audit fix: 0.15 mm coax ports, 9.12 mm air and the
finer 2.5/0.45 mm volume mesh. That gives 315k ND unknowns. **This host has
3.7 GB RAM and no swap.** A comparable run on 2026-09-06 peaked at 5.1 GB.
Four attempts were made:

| attempt | result |
|---|---|
| direct solver, 2 ranks | OOM-killed during setup (3.0 GB peak). The kill also took down the tmux session. |
| direct solver, 1 rank | terminated at the first frequency point |
| AMS iterative, 1 rank, 2.3 GB cgroup cap | OOM at the first solve |
| AMS, GMRES MaxSize 20, 2.55 GB cap | OOM at the first solve |

Adding swap was declined as a system change. **To finish this run, use a
machine with 6 GB of RAM or more, or add swap, then run
`uv run python docs/final_check/run_final.py`.**

The verdict therefore rests on runs that already exist and did complete:

| model | worst in-band S11 | BW | IL |
|---|---|---|---|
| golden (3.5/0.6 mesh, coarse ports) | −13.37 dB | 189 MHz | −1.85 dB |
| finer mesh 2.5/0.45 (`mesh_convergence_cascade_N3.json`) | −9.34 dB | 184 MHz | −2.00 dB |
| **refined ports 0.15 mm, 4.56 mm air** (61 pts, used below) | **−10.56 dB** | **183.7 MHz** | **−2.01 dB** |
| refined ports + 9.12 mm air (spot points only) | −14.8 dB at 2.87 GHz | — | −1.75 dB |

Across the models S11 spans 5 dB, while fc, BW and IL move by less than
10 MHz and 0.3 dB. **The passband is robust. The match is inside the model
uncertainty, and every model puts it short of −16 dB.**

## 3. Analysis: which coupling is off?

`analyze_final.py` fits a lossy N=3 coupling matrix to the refined-port
sweep and compares it with the Chebyshev target. The fit uses four couplings,
the resonator detunings and an unloaded Q.

![fit](analysis.png)

The board is mirror-symmetric, so the headline fit is the **symmetric** one
(rms 1.74 dB; the free fit reaches 1.41 dB with 3 more knobs):

| quantity | fitted vs target |
|---|---|
| external coupling M_S1 = M_3L (Qe) | **+0.4 %**: on target. The launch/taper is right. |
| internal coupling M_12 = M_23 (k) | **−4.8 %**: slightly weak |
| end cavities 1 & 3 | resonate **17 MHz low** |
| middle cavity 2 | −1 MHz: on tune |
| unloaded Q | ≈ 320 |

So the missing return loss is **not** the external-coupling problem suspected
since 2026-08-30. The main error is the two end cavities sitting about 17 MHz
below the middle one. By the project's rule of thumb (~50 MHz per mm), that
means `l_cav1` is about 0.3 mm too long. The internal irises are also roughly
5 % weak, which is about 0.5 mm of `w_iris`. **Not applied.** The finer mesh
moves S11 by 4 dB, which is larger than the effect of either correction. The
measured board should tell us which one to make.

### Fun numbers

- **Group delay** (from Palace's S21 phase): 4.3–7.1 ns across the band,
  4.5 ns at f0.
- **Wi-Fi 2.45 GHz**: −61 dB (Palace broadband sweep). The SIW's TE10 cutoff
  does most of this work, which is why the coupling-matrix model, which has no
  cutoff, predicts only −46 dB.
- **5G n78 at 3.5 GHz**: −39.5 dB (Palace broadband sweep).
- **Spurious passband: 5.8–6.8 GHz at −1.8 dB.** It covers 5.8 GHz Wi-Fi
  (UNII-3) and the bottom of Wi-Fi 6E. It is the known second passband, not a
  fault, but a real application would need a low-pass after the filter. Also
  expect it on the VNA.

## Files

- `run_final.py` is the fine-mesh final check (needs ≥ 6 GB RAM).
- `analyze_final.py` does the coupling-matrix fit, rejection and group delay.
- `refined_sweep.json` is the Palace data analysed (copied from `output/data/postpro/audit_refined_sweep/`).
- `analysis.json` and `analysis.png` are the fit results.
