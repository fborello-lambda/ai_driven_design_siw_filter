# Structural-variant exploration (2026-08-25, updated after deadline extension)

Task #31, user request: don't just re-tune existing knobs (task #29 already did
that) -- add genuinely **new structural parameters** to each geometry, verify
DRC (via-to-via spacing) for any new via placement, build a fast S11/S21-near-f0
screen to reject non-starters before full simulation, and run autonomously
against a hard deadline (2026-08-25 21:00 UTC) targeting the 4 best new
geometries besides dual-mode.

## New structural knobs added

Four new layout functions in `geometries.py` (registered in `LAYOUTS`), each a
thin wrapper around its parent that returns the parent unchanged at the
knob's default value (regression-verified: identical tets/ports/board size):

| new geometry | parent | new knob | mechanism |
|---|---|---|---|
| `circular_cross_nvia` | circular_cross | `n_perturb` | cluster of extra vias at each cross-arm tip |
| `circular_cross_ring2` | circular_cross | `ring2_frac`, `ring2_span_deg` | partial inner via arc at `ring2_frac*R` |
| `corner_cut_2corner` | corner_cut | `n_corners` | mirrors the single corner cut to a second corner |
| `rhombic_2diag` | rhombic | `w_iris2_mm` | second tuning-via pair on the feed-axis diagonal |

DRC: every layout still ends in the existing `_dedupe(vias, r)` (uses
`min_via_centre_sep`, JLCPCB hole-to-hole rule) -- no new validator was needed
since all new vias share the uniform via diameter already enforced there.

## Methodology: two-phase triage, both rounds

- **Phase A (screen)**: `screen_at_f0()` on the ultra-coarse mesh -- a
  window-scan of S11/S21 near f0 at the parent's already-known coupling
  params, ~2min/point. Answers "does this even resonate usefully" before
  spending real budget.
- **Phase B (refine)**: for phase-A survivors only, a real Bayesian coupling
  search (`optimize()`, same v17 `score()` used everywhere else this
  session) with the structural knob held fixed -- this is what actually
  tests competitiveness, not just resonance.

## Round 1: fixed w_ext, 14 combinations across 4 geometries

Phase A screened every structural value at the **parent's fixed best
coupling params** (including `w_ext` held constant). Result: **1/14
survived** phase A.

- **`circular_cross_nvia`** (n_perturb=2,3,4,6) and **`circular_cross_ring2`**
  (ring2_frac=0.3-0.7): **0/9 passed**. S11 stuck at a hard ~-4dB ceiling
  regardless of internal perturbation strength -- flat across 9 different
  values, strongly suggesting the limiter is external to the internal split
  mechanism (the fixed `w_ext=20.7` inherited from the parent), not the
  perturbation itself.
- **`rhombic_2diag`** (w_iris2_mm=4,8,12,16): **0/4 passed**, but a clean
  monotonic trade-off: w_iris2=4 gave S11=-19.3dB but S21=-7.0dB, just
  missing the -6.0dB IL floor; larger values made IL progressively worse
  without improving S11 further.
- **`corner_cut_2corner`** (n_corners=2, only value tried): **1/1 passed**
  phase A with an excellent screen (S11=-32.3dB). Phase B (18-eval Bayesian
  coupling search + fine/fab-tolerance confirm) converged to
  **score=15.435** (a=60.1, w_iris=12.3, w_ext=20.0mm) -- **worse** than
  corner_cut's own coupling-sweep best (11.65) and dual-mode (9.31).
  Bandwidth stayed pinned at ~505-506MHz across the entire 18-eval search
  regardless of w_ext (vs corner_cut's 223MHz) -- this is a **structural
  over-coupling** problem (the second cut admits too much energy), not a
  tuning problem that more search budget could fix.

## Round 2: vary w_ext jointly with the structural knob

Round 1's flat, w_ext-independent ceiling for the circular_cross family and
rhombic_2diag's near-miss motivated retesting both with `w_ext` freed as a
second grid dimension instead of fixed at the parent's value.

| candidate | grid | phase-A survivors |
|---|---|---|
| `rhombic_2diag` | w_iris2_mm ∈ {1,2,3} × w_ext ∈ {15,19.7,23} (finer, lower values than round 1) | 3/9 |
| `circular_cross_ring2` | ring2_frac ∈ {0.4,0.5,0.6} × w_ext ∈ {14,17,20.7,24} | 0/12 |
| `circular_cross_nvia` | n_perturb ∈ {2,3} × w_ext ∈ {14,17,20.7,24} | 2/8 (both n_perturb=2) |

**circular_cross_ring2 is conclusively eliminated.** Round 1's "hard -4dB
ceiling" hypothesis (external aperture as sole limiter) was **revised, not
confirmed**: varying w_ext freely *can* push S11 well past -4dB (down to
-10dB seen at one point), but only by collapsing S21 to -20 to -50dB in the
same move -- an inverse match/IL trade-off across the whole w_ext range, not
a fixable tuning problem. 0/12 grid points passed both thresholds
simultaneously.

**rhombic_2diag** at finer/lower w_iris2 values did pass phase A (3/9,
vs 0/4 in round 1) -- confirming round 1's monotonic trend continues below
w_iris2=4. But phase B tells a different story: **all three phase-A
survivors scored far worse than both parents on the full v17 score**:

| w_iris2_mm | phase-A screen (S11/S21) | phase-B final score |
|---|---|---|
| 1 | -20.0 / -5.2 dB | **25.58** |
| 2 | -19.6 / -5.7 dB | **23.66** |
| 3 | -10.6 / -5.3 dB | pending (in progress at time of writing) |

This is the same screen-vs-full-score discrepancy already documented for
`corner_cut_2corner`: `screen_at_f0` only asks "does *some* point near f0
look OK", while the full score also penalizes overall bandwidth shape/width
and fc deviation across the fit window. Every rhombic_2diag phase-B search
converged toward `y_wall` near its upper bound (40mm) and BW in the
250-560MHz range -- again an over-coupled/mistuned band shape that the
Bayesian search could not fix within the explored ranges, not a fluke of one
run.

**circular_cross_nvia** looked like the one genuinely new result -- n_perturb=2
passed phase A at two different w_ext values, unlike every other
circular_cross variant. But phase B (a real 4D Bayesian coupling search with
n_perturb=2 fixed) came back **completely empty**: all 8 evaluated points
returned `fc=0` -- no resonance anywhere in the fit window, not just a bad
score. The phase-A pass was a fragile coincidence at the exact
parent-inherited cavity dimensions (a=67, w_iris=16, y_wall=24); moving any
of those even slightly collapses the resonance entirely. The search's own
warm-start point (the un-searched parent defaults) was the only thing that
resonated at all, at **score=20.34** -- confirmed via FINE/FAB-TOLERANCE, and
still far worse than both baselines.

## Round-1+2 verdict: all 4 original structural variants fail

| candidate | best confirmed score | vs corner_cut (11.65) | vs dual-mode (9.31) | failure mode |
|---|---|---|---|---|
| `corner_cut_2corner` | 15.44 | worse | worse | structural over-coupling, BW~505MHz regardless of w_ext |
| `rhombic_2diag` | 23.66 (best of 3: 25.58/23.66/29.65) | worse | worse | over-wide BW (250-560MHz), y_wall pinned at range boundary |
| `circular_cross_ring2` | -- (eliminated, 0/12) | n/a | n/a | inverse match/IL trade-off across the whole w_ext range |
| `circular_cross_nvia` | 20.34 (parent defaults; search found nothing better) | worse | worse | phase-A pass was a fragile coincidence, collapses under any real coupling search |

**None of the four beats its own parent, let alone dual-mode.** Each adds a
coupling *path* (extra vias, inner ring, second corner cut, second diagonal
iris) without fixing the underlying bandwidth/Q mismatch -- they mostly just
relocate where the over-coupling happens. A literature search (see below)
confirms this isn't a search-budget problem: no published dual-mode SIW
design offers a shortcut around EM-tuning either.

## Literature search: no closed-form shortcut exists

Dispatched a search for published SIW dual-mode designs with more
predictable perturbation-to-coupling equations, and for treatments of the
taper/launch problem for a non-flat-wall cavity. Result: **no closed-form
k(perturbation) equation exists in the accessible literature** -- every
dual-mode SIW paper found (hexagonal source-load coupling, slot-line
perturbation, interdigital mixed coupling) extracts k the same way this
project does: simulate, split the degenerate pair, `k=(f2^2-f1^2)/(f2^2+f1^2)`.
Two promising papers (the hexagonal-cavity source-load paper, PMC4032748;
a 2024 combined magnetic-electric perturbation paper) were access-blocked
(recaptcha / 403) beyond their abstracts. The taper/non-flat-wall launch
question is unaddressed in every paper found -- likely because published
designs use rectangular or hexagonal cavities with flat walls to feed into,
sidestepping the problem this project's circular/rhombic cavities actually
have. **Conclusion: pursuing a "more predictable" alternative topology is not
worthwhile; the taper-launch fix remains the most concrete untested lever,
precisely because the literature is silent on it, not because it's
validated.**

## New geometry: `circular_cross_taper` -- testing the launch-fix hypothesis directly

Implemented in `geometries.py`: circular_cross with a short FLAT launch
facet at each feed aperture (parameter `wf_mm`, the facet's extra half-height
beyond the w_ext gap edge) replacing the tangent point the plain circular
fence feeds through -- giving the Deslandes taper an actual wall to flare
onto (`TAPER_TO_WALL["circular_cross_taper"] = True`). `wf_mm<=0` delegates
straight to `circular_cross` (regression-verified byte-identical via list).
A short horizontal via row closes the step between the flat facet and where
the circular fence naturally resumes. DRC-clean (2.67mm min separation vs
2.0mm required at wf_mm=8) and meshes cleanly (ports=(1,1), 142k-172k tets,
under GPU_MAX_TETS) -- registered in `LAYOUTS`, `GPU_MESH_PRESETS`,
`SCREEN_MESH_PRESETS`, and `_SPACES` (same coupling box as
circular_cross_ring2/nvia).

Phase-A screen at the parent's known coupling params (a=67, w_iris=16,
y_wall=24, w_ext=20.7), sweeping `wf_mm`:

| wf_mm | S11 | S21 | pass |
|---|---|---|---|
| 1.0  | **-15.08 dB** | -1.72 dB | yes |
| 2.0  | -14.84 dB | -1.76 dB | yes |
| 3.0  | -14.33 dB | -1.87 dB | yes |
| 4.0  | -12.68 dB | -1.84 dB | yes |
| 6.0  | -10.53 dB | -2.18 dB | yes |
| 8.0  | -10.06 dB | -2.05 dB | yes |
| 14.0 | -8.05 dB  | -2.46 dB | no |

This is the first result across the entire structural exploration (both
rounds) to **break circular_cross's hard ~-4dB match ceiling** -- confirming
the coupling-sweep doc's taper-less-launch hypothesis was correct. The trend
is monotonic and clean once swept finely: smaller facets are strictly
better, with diminishing returns as wf_mm -> 0 (a bigger facet perturbs the
circle's shape more, degrading the degenerate-mode balance). wf_mm=1.0 is
the chosen fixed point for phase B -- the gains from 8->4->3->2->1mm shrink
each step (+2.6, +1.65, +0.5, +0.24 dB), suggesting the curve is
approaching its asymptote, so going smaller than the tested range is
unlikely to matter and phase B's coupling search matters more now.

Phase B (full v17 score, `optimize()` with wf_mm=1.0 fixed, 18-eval budget)
result: **coarse=16.116, FINE=16.636, FAB-TOLERANCE=17.157**
(a=67.8, w_iris=21.4, y_wall=29.1, w_ext=24.3). Same screen-vs-full-score gap
as `corner_cut_2corner`: the taper facet genuinely fixed the match (S11 down
to -15dB from a -4dB ceiling), but the joint 4D search got stuck over-coupled
the entire run -- every one of the 18 evaluated points landed BW=270-540MHz
(vs the ~143.5MHz target), except the single point that hit w_ext=14 (the
box floor), which flipped all the way to BW=45MHz (too narrow, IL=-4.31,
screened as a failure) rather than landing near the target in between. The
GP never got a gradient toward that middle region because both directions
away from it look equally bad in score terms from a joint search's
perspective. **17.16 is still worse than `corner_cut` (11.65) and dual-mode
(9.31)**, though clearly better than every other structural variant's
confirmed phase-B result except `corner_cut_2corner`'s 15.44.

## Follow-up: coupling-only sweep for circular_cross_taper

Same rationale as task #28/29's original coupling-sweep tool: a joint search
trades cavity size against coupling and can walk straight past a narrow
target region sitting between two differently-bad regimes. Launched a fixed-
cavity (`a=67.8, wf_mm=1.0`) grid sweep directly over `w_iris` (12/16/20),
`w_ext` (10/12/14/16/18/20 -- finer resolution bracketing the 14mm point that
flipped to BW=45), and `y_wall` (15/22/29) -- 54 points, screened first with
`screen_at_f0` before any full coarse eval, same tool (`sweep_coupling.py`)
used for the original three geometries, pointed at `GeometryTopology
("circular_cross_taper")` directly (not registered in `REGISTRY`, since none
of the structural variants are).

*(Result pending -- this document will be updated with the sweep's best
point and whether it beats corner_cut/dual-mode.)*

## Investigated, deferred: top-copper "corner leak" outside the via fence

User question (2026-08-26): is a leak from the microstrip feed itself (no
ground-via stitching flanking the trace) contributing to circular_cross/
rhombic's problems? The bare-feed region checked out fine (standard
single-sided microstrip over a continuous bottom ground, nothing to fix
there). But investigating it surfaced a DIFFERENT, real issue: the top
copper ground plane inside the cavity's x/y bounding box is solid PEC
across the ENTIRE box, not just the actual via-fence footprint -- for a
circle inscribed in its bounding square that leaves ~21% of the box area
(the four corners between the arc and the square) as top+bottom PEC with NO
via wall isolating it from the rest of the board; for a diamond (rhombic)
inscribed in its bounding rectangle it's a full 50%. This tracks with
rhombic scoring worse than circular_cross all session.

Attempted fix: reclassify those corner faces by an actual point-in-circle/
point-in-diamond test (`CAVITY_SHAPE` + `in_cavity_shape()`) instead of the
existing x/y bounding-box test. **Confirmed by direct gmsh probe to be a
no-op**: the cavity's entire top surface collapses to a small handful of
already-merged topological faces (11 total for circular_cross, one of them
covering the whole cavity top) during the boolean cut/fragment step, and
face classification happens per-FACE (by centroid), not per-point --
identical PEC/absorbing face counts (78/18) before and after. Splitting the
corner out for real needs an actual geometric cut (a curve along the circle/
diamond boundary, added before meshing) so it becomes its own face, not a
classification-time tweak. Reverted the ineffective version rather than
leave dead code in the tree.

This is a legitimate open question -- and it's also a fabrication-model
question, not purely a bug: whether a real board should have copper relief
in those corners is a design choice this project hasn't made either way.
Deferred as a follow-up requiring real CAD work, not attempted further
under this deadline.
