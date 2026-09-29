---
documentclass: IEEEtran
classoption:
  - journal
  - twocolumn
title: >-
  AI-Driven RF Design: An LLM Coding Agent Takes a Substrate Integrated
  Waveguide Filter from Specification to Fabrication
author: "\\vspace{-2em}"
date: 2026
abstract: |
  We report the design of a third-order, 2.87 GHz substrate integrated
  waveguide (SIW) bandpass filter in which a large-language-model coding
  agent wrote and operated the entire toolchain: Chebyshev synthesis,
  parametric geometry, finite-element simulation with the open-source solver
  Palace, Bayesian optimization, and the export of fabrication files (KiCad
  gerbers, a STEP solid and a parametric CST macro). A single engineer set the
  specification, took the topology and fabrication decisions, and ran the
  commercial-solver cross-checks. Over 16 weeks the project accumulated 211
  commits, 119 of them co-authored by the agent. We report three results.
  First, a Gaussian-process optimizer applied to the assembled filter never
  reached a usable match, because the passband width it scores is
  discontinuous in the external coupling. Measuring smooth observables on
  small structures, namely the eigenmode splitting of two coupled cavities
  and the loaded Q of one driven cavity, and then inverting the textbook
  coupling relations converged in about three solves per curve. Second, most
  of the 47 fixes in the history corrected defects that produced plausible
  numbers without raising any error. We classify them and list the guards
  that now catch each class. Third, the fabricated design reaches a simulated
  centre frequency of 2.876 GHz, 182 MHz bandwidth, 1.70 dB insertion loss
  and −11.2 dB worst in-band return loss. This misses the −16 dB and
  143.5 MHz targets; a coupling-matrix fit attributes the gap mainly to
  end-cavity detuning. We also show that the SMA connector is part of the
  tuning, since removing it costs about 5 dB of return loss. A single-cavity
  dual-mode alternative is documented as a negative result. The board has
  been sent to JLCPCB for manufacture, and measured results will be added
  when it arrives.
bibliography: references.bib
csl: ieee-jestpe.csl
link-citations: true
header-includes:
  - \usepackage{graphicx}
  - \usepackage{amsmath}
  - \usepackage{placeins}
  - \usepackage{booktabs}
  - |
    \makeatletter
    \AtBeginDocument{%
      \def\@author{%
        \parbox{\textwidth}{\centering
          Federico Borello\\[2pt]
          {\small Universidad Tecnológica Nacional --- Facultad Regional Buenos Aires,
          Argentina\\ fborello.contact@gmail.com}%
        }%
      }%
    }
    \makeatother
---

```{=latex}
\begin{IEEEkeywords}
Substrate integrated waveguide, bandpass filter, large language models,
AI agents, design automation, Bayesian optimization, finite-element method,
coupling matrix.
\end{IEEEkeywords}
```

# Introduction

Machine learning has been part of microwave CAD for decades. Neural-network
surrogate models [@zhang2000neural], space mapping [@bandler2004space] and
Bayesian optimization [@jones1998efficient; @snoek2012practical] all replace
some of the expensive electromagnetic (EM) solves with a cheaper learned or
coarse model. In each of these approaches the engineer still writes the
geometry scripts, meshing, port setup, objective and export code, and
interprets what the solver returns.

Recent large-language-model (LLM) agents work differently: they write and run
code in a loop, observe the results and revise [@yao2023react;
@yang2024sweagent]. Agent frameworks now exist for RFIC design
[@xing2026rfagent] and RF amplifiers [@lu2026rfampdesigner]. An agent has also
operated CST, ADS and KiCad through their scripting interfaces to design a GNSS
front end [@heinrichs2026prompt]. What these reports leave largely unmeasured
is how the engineering fails when an agent drives it, which matters more than
the successes when one decides how much to trust the numbers.

This paper reports one complete design effort of that kind. The object is a
classic structure, a three-cavity Chebyshev SIW filter
[@deslandes2003single; @bozzi2011review; @chen2014siwfilter]. It was chosen
because its physics is textbook, so every agent-produced number can be
checked against theory. An LLM coding agent (Claude Code [@claudecode])
wrote and ran all of the design software. The author acted as specifier,
reviewer and decision-maker. The project history is fully preserved in git,
so every claim below maps to a commit.

The contributions are:

1. An account of the tool path: an FDTD solver (openEMS) that could not
   support match tuning, a finite-element solver (Palace) that could, and a
   GPU workstation run through remote agent sessions whose memory limits
   eventually pushed all production runs onto CPUs (Sec. III).
2. A measured explanation of why black-box Gaussian-process (GP) search over
   the assembled filter fails, and of why calibrate-and-invert succeeds
   (Sec. IV).
3. A taxonomy of the silent modelling defects the process produced and
   caught, with the guard that now blocks each class (Sec. V).
4. The fabricated design, with its deviation from specification diagnosed by
   coupling-matrix extraction. It is accompanied by a documented dual-mode
   negative result, an insertion-loss budget, a launch study and the
   manufacturing path (Secs. VI and VII).

# Filter specification and synthesis

The specification is f0 = 2.87 GHz, 5 % fractional bandwidth (143.5 MHz),
0.1 dB Chebyshev ripple and |S11| ≤ −16 dB in band. The laminate is Rogers
RO4350B, 0.76 mm thick (εr = 3.66, tan δ = 0.0037 [@rogers4350b]), with
0.5 oz copper. The fence vias are 1.5 mm in diameter at a 3.0 mm pitch. Their
p/d = 2 ratio sits at the edge of the leakage rules of
[@xu2005guided; @deslandes2006accurate]. Smaller vias (0.8 mm at 1.5 mm pitch)
were compared three times under three different objectives and never matched
this choice. The connector is a Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA
[@taoglas_sma].

The low-pass prototype gives g1 = g3 = 1.0316 and g2 = 1.1474 for N = 3
[@hong2001microstrip]. The bandpass mapping then gives the design targets:

$$ k_{i,i+1} = \frac{\text{FBW}}{\sqrt{g_i g_{i+1}}} = 0.0460,
\qquad Q_e = \frac{g_0 g_1}{\text{FBW}} = 20.63 . $$

The SIW width follows from a TE10 cutoff near 0.7 f0 through the Cassivi–Wu
correction $a_{\text{siw}} = a_{\text{eff}} + d^2/(0.95p)$
[@cassivi2002dispersion]. The cavity lengths follow from the TE101 resonance.
Each feed is a 50 Ω microstrip line (Hammerstad [@hammerstad1980accurate])
flared into the SIW by a Deslandes taper [@deslandes2010design]. At the board
edge it becomes a grounded coplanar waveguide (CPWG) launch sized to the SMA
footprint: a 1.2 mm trace with 0.2512 mm gaps, which solves to 50.0 Ω by
conformal mapping [@wadell1991transmission; @simons2001coplanar]. The
coupling-matrix formulation [@cameron2003advanced; @cameron2018microwave]
provides both the ideal target response and, later, the diagnostic fit.

# Toolchain and working method

Fig. \ref{fig:flow} shows the flow and the division of labour.
Fig. \ref{fig:timeline} shows how the effort was distributed in time.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_flow.png}
\caption{Design flow. The agent writes and operates every stage through one
command-line tool (\texttt{siw}); the engineer supplies the specification and
the decisions, and runs the commercial-solver cross-checks.}
\label{fig:flow}
\end{figure*}
```

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_timeline.png}
\caption{Commit history by type. P1 was a human-led prototype committed in a
few large commits. From P2 onward the agent drove the work, and fixes (red)
cluster where new physics or a new tool entered the loop.}
\label{fig:timeline}
\end{figure*}
```

## Phase 1: analytic design, openEMS and CST

The first iteration (June 2026) used analytic dimensions, the free FDTD solver
openEMS [@liebig2013openems] for calibration, and CST Studio Suite 2021
[@cst2021] as the reference. Python generated a parametric CST VBA macro that
builds native solids wrapped in the solver's history list. The analytic cavity
length of 38.23 mm put the CST passband at 2.818 GHz with a 293 MHz band,
3.65 dB insertion loss and only 1.02 dB return loss. The external coupling was
uncalibrated and heavily over-coupled.

openEMS was abandoned for three reasons. First, FDTD resolves the 1.5 mm
cylindrical vias on a staircase grid, which needs at least three cells per
diameter over the whole board. The resonant, high-Q structure also rings down
slowly, so each full-filter run took minutes to tens of minutes. Second, the
ports did not give a trustworthy S11. The lumped port radiated like a point
source instead of launching the microstrip mode. The microstrip port launched
the mode correctly, but its S11 de-embedding was unstable and even returned
|S11| > 1. The passband and S21 were reproduced, but the match could not be
tuned, and matching was the whole remaining problem. Third, there was no eigenmode solver for the
coupling calibration of Sec. IV, which had to be emulated by reading peak
splits off driven sweeps.

Palace [@palace2023], an MPI-parallel finite-element solver built on MFEM
[@anderson2021mfem] with gmsh meshes [@geuzaine2009gmsh], removed all three
obstacles. Its tetrahedral mesh conforms to the vias. Its wave ports solve the
2D port mode, as CST's do, and are passive by construction. It has an
eigenmode solver, and it is driven entirely by JSON files, which makes it easy
for an agent to operate. A first Palace model reproduced the CST result for
the same geometry and then replaced openEMS in the loop.

## Phase 2 onward: an agent-operated toolchain

From August the agent consolidated three copied optimizer scripts into one
package with a `Topology` interface and a single command-line tool (`siw`).
The tool covers synthesis, layout, eigenmode and driven solves, Bayesian
design, 1-D scans, calibration, comparison figures and CAD export. Every
production number in this paper is reproducible through that tool, and curated
results are stored in a `golden/` directory together with their S-parameters
and the command that reproduces them. A project brief file (`CLAUDE.md`) acted
as the agent's persistent memory across sessions. Handoff documents carried
the state from one machine to another.

The ML layer is a scikit-optimize GP [@skopt; @rasmussen2006gaussian] with
two fidelities: coarse-mesh evaluations for the search and a fine-mesh
confirmation of the winner. It also has a fast physics screen that rejects
non-resonant candidates before a full solve, a patience-based early stop, and
an objective that went through ten revisions (v9–v18). Later revisions fitted
the whole response to the ideal Chebyshev target instead of scoring
individual points.

**Compute.** To speed up the search, the work moved to a workstation with an
NVIDIA GTX 1660 SUPER (6 GB). Palace ran with its GPU backend on that card,
and the author supervised the long agent sessions remotely through Claude
Code's Remote Control. The GPU was 1.24× faster than 4 CPU ranks on the
dual-mode model, with S-parameters identical to 10⁻⁹ dB. However, 6 GB caps a
model at about 176 k tetrahedra. The 166 mm cascade exceeded that at any
adequate mesh density, and the fine-mesh verification (315 k unknowns,
≈5.5 GB peak) did not fit either. All production runs therefore ended up on
CPUs with 4 MPI ranks. An attempt on a 3.7 GB host was OOM-killed four times;
the final runs used a 16 GB host at about 8 s per frequency point. In short,
memory rather than arithmetic was the binding constraint throughout.

# Why global Bayesian search failed

The GP worked as intended in one regime: as a local polish around a validated
design. For the dual-mode filter, a 30-evaluation search in a ±2 mm,
5-dimensional box confirmed the landed geometry. Neighbouring probes came back
worse, and the apparent 0.41 dB gain lay inside the measured coarse-mesh noise
floor of 0.64 dB.

Run globally over the assembled cascade, the same machinery never produced a
worst in-band S11 better than −5 dB in more than 60 driven evaluations. The
cause is structural. The objective scores the passband width, and that width
is discontinuous in the external aperture w_ext. Below a coupling threshold
only the centre pole clears the −3 dB line, so the band measures one
resonance. Above the threshold all N poles merge and the width jumps. On the
N = 3 cascade the measured widths were 16, 22, 36, 65 and then 215 MHz, with
the 143.5 MHz target inside the jump. A GP assumes a smooth objective, so it
inherits the discontinuity. The search-health data showed the same thing:
57–83 % of cascade candidates were screened out, leaving 2–9 informative
points per run, against 34–37 % and about 19 informative points on the
dual-mode filter, where the search converged.

The replacement measures each coupling on the smallest structure that exhibits
it (Fig. \ref{fig:calib}):

* **Internal coupling.** A closed two-cavity eigenmode solve splits the
  cavity mode into f1 and f2, and $k = (f_2^2 - f_1^2)/(f_2^2 + f_1^2)$
  [@hong2001microstrip]. This is smooth in w_iris.
* **External Q.** One cavity driven symmetrically through two apertures gives
  the loaded Q, and $Q_e = 2/(1/Q_L - 1/Q_u)$. Here Qu = 1/tan δ = 270.3,
  independently matched by the eigenmode Q. This is smooth and monotonic in
  w_ext.

Inverting the fitted curves at the synthesis targets, assembling the filter
and making a final driven fc trim converged in about three solves per curve.
The resulting internal coupling was within 2 % of target, and the N = 4 centre
frequency landed at exactly 2.870 GHz. The GP was kept only as a local polish
seeded with the result (`--seed`). The physics that worked is textbook
[@hong2001microstrip; @cameron2018microwave]. What the agent contributed was
running the calibrations quickly, and diagnosing why the black-box route had
failed.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_calib.png}
\caption{(a), (b) The calibration observables are smooth and invertible.
(c) The bandwidth of the assembled filter, the quantity a black-box objective
scores, jumps as the poles merge.}
\label{fig:calib}
\end{figure*}
```

Two further search failures were caused by the parameterization itself rather
than by the search. The via fences were first generated by filtering a fixed
grid, so the iris width was *quantized*. The whole cascade search box spanned
about two distinct geometries, and the GP was tuning a knob that did nothing
(Fig. \ref{fig:quant}). In addition, N ≥ 4 had a single shared iris width and
could not express the required k = [0.0415, 0.0329, 0.0415].

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_quantization.png}
\caption{Via-fence quantization. Filtering a fixed pitch grid collapsed
different iris widths onto identical meshes. Segment-wise placement makes
the geometry continuous in its parameters.}
\label{fig:quant}
\end{figure}
```

# Silent defects: a taxonomy

The history contains 47 commits labelled *fix*. Most corrected defects that
never raised an error: the solver converged and the plot looked reasonable,
but the number was wrong. Table \ref{tab:bugs} groups representative cases.
Three rules paid for themselves repeatedly. First, if a fix does not change
the number, the diagnosis was wrong. Second, after two wrong inferences, stop
inferring and run a one-factor ladder. Third, check every result against what
physics allows: insertion loss cannot beat a lossless model, the pole count
must equal N, and a lossy stack cannot cost 27 dB.

```{=latex}
\begin{table*}[t]
\centering
\caption{Representative silent defects, how they were caught, and the guard added}
\label{tab:bugs}
\footnotesize
\begin{tabular}{p{2.3cm}p{6.2cm}p{4.2cm}p{3.6cm}}
\toprule
\textbf{Class} & \textbf{Defect (effect)} & \textbf{Caught by} & \textbf{Guard now in code}\\
\midrule
Parameterization & Iris width quantized by grid filtering (search box $\approx$2 geometries); single iris width for $N\ge4$ (spec unreachable); stale via defaults 0.8/1.5\,mm & Scan showing identical meshes; coupling targets & Continuous via segments; per-iris parameters \\
Measurement / metric & Bandwidth taken first-to-last crossing, bridging two disjoint lobes; sweep window narrower than the band (fc reported = window centre, 48\,MHz error charged nothing); truncated $Q_e$ points giving an inversion outside its own bracket & Identical fc across evaluations; physics sanity & \texttt{n\_lobes}, \texttt{band\_truncated}, bracket check \\
Mode selection & Eigenmode pair = smallest gap picked a higher-order cluster: $k=0.0028$ instead of $0.0583$ (21$\times$) & Inspecting the raw eigenvalue list & Window around $f_0$, then the two lowest modes \\
Mesh / boundary tagging & SMA end-cap classified by centroid swallowed the PTFE annulus at $r_{in}\ge0.3773$\,mm (S21 $=-79.5$\,dB); faces left with no boundary condition (IL better than lossless); a domain with no material & Bisection over pin radius; IL $>$ lossless & Face-extent test; unclassified-face report; domain-coverage guard \\
Model validity & Wave port on the trace self-normalizes, so $W_{ms}$ was tuned to a 41\,$\Omega$ line; surface-impedance BC applied to internal two-sided sheets ($-7.8$\,dB IL on copper); 4.5--20\,$\mu$m layers meshed as slivers & Real coax launch; Palace warning; one-factor ladder & Real SMA model; exterior-only conductivity; thin layers excluded \\
Plumbing & Adapter dropped soldermask/via-conductivity before the solver (two studies ran with the feature off); N=3 and N=4 results overwrote each other (shared tag); cached curve reused under a retuned label & Result unchanged by a real change & Order in every tag; geometry fingerprint on caches \\
Export & CST macro wrote the launch at 1000$\times$ (6\,m coax, vias 30\,m off-board), twice; taper dropped; coax without shield; PEC end caps on open walls & Cross-check of \texttt{.bas} vs mesh & 34 file-level fab checks incl.\ magnitude test \\
Agent process & VBA properties guessed by name analogy; edits from a parallel agent absorbed unreviewed; comment overclaims; a process declared dead by a flawed \texttt{ps} filter & CST errors; adversarial self-review & Only properties seen in a real run; reviewed diffs \\
Convergence & Selection metric (S11 $-13.37$\,dB) from a non-converged mesh; refined model gives $-10.7$\,dB & CST/Palace audit & Fine-mesh final check \\
\bottomrule
\end{tabular}
\end{table*}
```

Two cases changed the course of the project. In the first, when a real SMA
coax launch replaced the ideal port, the optimized microstrip width of
2.26 mm turned out to be a 41 Ω line. The optimizer had exploited a port that
normalizes to whatever it sits on, and the true 50 Ω width is 1.664 mm. The
first coax model also used a full-size 0.82 mm pin, which is thicker than the
0.76 mm board, and returned −0.2 dB S11. That was real physics, not a bug
(Fig. \ref{fig:sma}). In the second, an independent audit against CST showed
that the −13.37 dB return loss used to choose the cascade over the dual-mode
design was a coarse-mesh artefact. The converged value is about −10.7 dB. The
decision survived, but the justification had to be rewritten.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_sma_v1.png}
\caption{First real-connector model. An ideal port hid a 41\,$\Omega$ feed,
and a cable-size pin larger than the board shorts the launch.}
\label{fig:sma}
\end{figure}
```

# Topologies, lengths and the dual-mode negative result

**Cavity lengths.** The analytic 38.23 mm cavity placed the band at
2.82–2.905 GHz (openEMS/CST). An openEMS sweep to 35.93 mm and 33.64 mm moved
it to 2.982 and 3.077 GHz, a slope of about −37 MHz/mm. Palace, which models
the loading by the tapers and external apertures that the analytic formula
ignores, shortened the cavities to about 34.4 mm. Calibrate-and-invert then
gave unequal cavities, 34.24/35.50/34.24 mm. The fine-mesh coupling fit found
the end cavities about 17 MHz low, and a −0.3 mm trim (33.94/35.50/33.94 mm)
was chosen. A −0.6 mm trim gained only 0.07 dB and cost 0.4 dB of band-edge
loss. The measured sensitivity at the end cavities was about 27 MHz/mm,
roughly half the 50 MHz/mm rule of thumb.

**Board size.** The design space was also explored for a smaller board
(Figs. \ref{fig:layouts} and \ref{fig:designs}). The candidates were a
single-cavity dual-mode N = 2 filter (119 mm), the N = 3 cascade (166 mm) and
an N = 4 cascade (211 mm). Three other single-cavity shapes were tried:
corner-cut, circular-cross and rhombic. None came closer to the specification
than the dual-mode cavity (best S11 −6 to −9 dB). A compact N = 4 made from
two dual-mode cavities was closed after five mechanisms plus a joint GP search
all stopped at two of four poles: offset apertures, near-corner coupling,
top-copper slots, discrete posts and quad-mode cavities. A four-cavity
single-mode cascade works, but it needs 180–206 mm.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_layouts.png}
\caption{(a) Dual-mode N=2: one square cavity whose TE$_{102}$/TE$_{201}$
pair is split by a floating via row. (b) The fabricated N=3 cascade, with
external apertures in red and the CPWG/SMA footprints at the board edges.}
\label{fig:layouts}
\end{figure*}
```

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_designs.png}
\caption{Best designs of each topology under the same CPWG + SMA launch
(Palace). The N=3 curve is the fine-mesh final. The other two are the
production mesh.}
\label{fig:designs}
\end{figure*}
```

**Dual-mode N = 2.** A single square SIW cavity, a = 57.16 mm, carries a
degenerate TE102/TE201 pair. A floating internal via row splits the pair and
couples it [@shen2009dualmode; @xu2014hexagonal]. Under the matched CPWG launch
its best response is fc 2.904 GHz, 316.6 MHz bandwidth, −10.76 dB return loss
and 1.45 dB insertion loss. Real copper adds 0.32 dB. One-dimensional scans on
the assembled filter show that, on this topology, bandwidth and match are
*opposed* on every geometry parameter. At w_iris = 11 mm the band is 145.6 MHz
(4.94 % FBW), but the return loss is −1.75 dB. The pad-only launch used
earlier reached −17.7 dB, but that launch was not the one fabricated. N = 2
has only one internal and one external coupling, which is not enough freedom
to place two poles and also match them. The cascade has an extra degree of
freedom at 1.4× the length, and it won the head-to-head comparison.

# The fabricated design

The chosen geometry is l_cav1 = 33.939, l_cav2 = 35.503, w_iris = 14.416,
w_ext = 13.96, l_taper = 15.738 and w_ms = 1.6636 mm, on a
165.78 × 45.79 mm board. Table \ref{tab:final} and Fig. \ref{fig:final}
summarise the fine-mesh result (2.5/0.45 mm volume mesh, 0.15 mm coax ports,
9.12 mm air, 61 points).

```{=latex}
\begin{table}[t]
\centering
\caption{Fabricated design: simulated (fine mesh) vs.\ specification}
\label{tab:final}
\begin{tabular}{lcc}
\toprule
 & \textbf{Target} & \textbf{Simulated}\\
\midrule
Centre frequency & 2.870 GHz & 2.876 GHz\\
$-3$\,dB bandwidth & 143.5 MHz & 182.3 MHz\\
Worst in-band $|S_{11}|$ & $-16$ dB & $-11.15$ dB\\
Insertion loss, peak / worst in band & --- & 1.70 / 2.58 dB\\
Rejection at 2.45 / 3.5 GHz & --- & 61 / 39.5 dB\\
Measured & \multicolumn{2}{c}{\emph{pending (Sec.\ VIII)}}\\
\bottomrule
\end{tabular}
\end{table}
```

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_final_trim.png}
\caption{Fine-mesh final check. The $-0.3$\,mm end-cavity trim lifts the
interior ripple from $-11.2$ to $-14.5$\,dB. The worst point stays at the
2.94\,GHz band edge.}
\label{fig:final}
\end{figure}
```

**Why it misses the specification.** A lossy N = 3 coupling-matrix fit to the
refined sweep (Fig. \ref{fig:cmfit}) puts the external coupling on target
(+0.4 %), which exonerates the launch. It finds the internal coupling 4.8 %
weak and the end cavities 17 MHz low. The trim halves the detuning, but the
worst in-band point sits at the upper band edge, where the equiripple region
ends near 2.935 GHz against a target edge of 2.942 GHz. Single-knob trims
either widened the band without helping (+0.6 mm w_iris) or were strongly
harmful (+0.4 mm w_ext, which also pulls the end cavities down). A coordinated
local move remains open.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_coupling_fit.png}
\caption{Lossy coupling-matrix fit used to diagnose the return-loss gap:
external Q on target, $k$ 4.8\,\% weak, end cavities 17\,MHz low.}
\label{fig:cmfit}
\end{figure}
```

**Why the insertion loss is high.** For a narrowband filter,
IL$_0 \approx 4.343\sum g_i/(\text{FBW}\,Q_u)$ [@hong2001microstrip]. The loss
is therefore set by the unloaded Q. RO4350B limits the dielectric Q to
$Q_d = 1/\tan\delta = 270$. For a TE101 cavity 0.76 mm high, the conductor Q
is about $Q_c \approx 540$ with smooth copper [@pozar2012microwave]. Together
they give $Q_u \approx 180$, and the fitted value was 229–320. At 5 % FBW this
predicts 1.2–1.55 dB of dissipation. The −11 dB in-band mismatch adds
0.35 dB. The simulated 1.70 dB peak is therefore close to the physical floor
of this laminate, thickness and bandwidth, not a design error. Each loss
mechanism points to an improvement:

* Qd is fixed by the laminate: tan δ = 0.0037 is high for a filter.
* Qc scales with the substrate height, and 0.76 mm is thin.
* The loss scales as 1/FBW, so a narrow band costs more.
* The band edges lose more (2.58 dB) because the group delay peaks there.

Real copper added 0.59 dB in the conductor-loss model. A 1.52 mm RO4350B
board only reaches IL ≈ 1.3 dB, because Qd still dominates. RT/duroid 5880
(tan δ ≈ 0.0009) at 1.52 mm would bring it to about 0.5 dB.

**Cross-solver check.** CST Frequency Domain, run from the generated macro,
agreed with Palace on fc (2.876 vs. 2.875 GHz) and IL (1.80 vs. 1.85 dB).
Getting there took ten fixes to the macro and solver setup, and a coax-only
control model to separate port problems from filter problems. The bandwidth
agreed less well: 129.6 MHz in CST against 150 MHz in Palace at the reference
mesh. The time-domain solver was never made fully stable.

**The connector is part of the design.** Figs. \ref{fig:launch} and \ref{fig:renders} compare
three launches on the same geometry: a bare microstrip feed, the CPWG launch
without a connector, and the CPWG launch with the SMA. Without the connector
only one reflection zero remains, and the worst in-band S11 is −6.3 dB
(microstrip) or −5.1 dB (CPWG), against −11.2 dB with it. The filter was
tuned with the connector's reactance in place. The bare CPWG port also shows
a port-modelling trap: its first two Palace modes belong to the ground pours
(S21 ≈ −78 dB), and the signal mode is mode 3.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_launch_sparams.png}
\caption{Same geometry, three launches. Removing the SMA costs
$\approx$5\,dB of return loss because the design was tuned with it in place.}
\label{fig:launch}
\end{figure}
```

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.9\textwidth]{figures/fig_launch_renders.png}
\caption{Palace models of the three launches: whole board and input-launch
close-up. Green: copper; brown: RO4350B; yellow: SMA connector.}
\label{fig:renders}
\end{figure*}
```

**Manufacturing.** The same command-line tool writes the KiCad board, the
gerbers, the drill files, a STEP solid, and 34 automated file-level checks
[@jlcpcb_caps]. The checks include drawn-versus-meshed geometry and
CST-versus-mesh via positions. JLCPCB stocks RO4350B 0.76 mm but offers only
1 oz outer copper. That leaves the finished thickness at about 0.84 mm at the
pads, against the SMA fork slot of 0.81 ± 0.1 mm, which is marginal and can be
fixed by scraping 15–20 µm of copper under the connector legs. The no-mask
requirement is carried by the gerbers and stated in the order notes. The
board has been ordered.

# Measured results

*[Pending — the boards are in manufacture at JLCPCB. This section will report
a two-port VNA measurement: |S11|, |S21| and group delay over 2.5–3.3 GHz and
0.1–8 GHz, overlaid on the fine-mesh simulation and the CST result. It will
include the measured fc, bandwidth, insertion loss and return loss, the
spread across boards, and a re-fit of the coupling matrix to the measurement.
Planned de-embedding: SMA-to-SMA through-line if fabricated, otherwise the
connector is left in the reference plane, as it is in the simulation.]*

# Discussion: gaps and room to improve

**What was AI-driven, and what was not.** The agent wrote about 11.5 k lines
of design code, launched and monitored the Palace eigenmode and driven solves, read solver logs, localized
most of the defects in Table \ref{tab:bugs}, and produced the fabrication
files. The engineer chose the specification, topology, laminate and vias,
decided when to stop tuning, ran every CST check, and more than once rejected
a confident but wrong explanation. The design physics that finally worked is
classical. The acceleration came from automation and diagnosis, not from new
electromagnetics. Stating this plainly is more useful than overclaiming.

**Agent failure modes observed.**

* Confident misdiagnoses: two wrong explanations of one stack failure were
  each falsified by a single re-run.
* APIs guessed by analogy: VBA properties that do not exist.
* Documentation drift: headline numbers kept in prose after the code had
  changed. The repository's status files had to be rewritten several times.
* Unreviewed edits from a parallel agent absorbed into a commit.
* Premature optimism about untested geometries.

Each was caught by a physics check, a solver error or a human question, which
argues for keeping those checks in the loop.

**Gaps.**

* No measurement yet.
* The specification is not met: −11.2 dB against −16 dB, and 182 MHz against
  143.5 MHz.
* S11 varies by about 5 dB across mesh and port models, while fc, bandwidth
  and IL are robust. The match is therefore inside the model uncertainty.
* Qe is calibrated with a dielectric-only Qu and is slightly over-estimated.
* Conductor loss is modelled only on exterior faces. Thin fabrication layers
  (mask, ENIG) could not be resolved.
* A spurious passband at 5.8–6.8 GHz needs a low-pass filter in a real
  system.
* There is no controlled comparison against an engineer working without the
  agent, and no accounting of tokens or cost.

**Improvements.**

* A coordinated local correction of w_ext, l_cav1 and w_iris, driven by the
  coupling-matrix fit.
* Adaptive frequency sweeps and y-symmetric half-models, for roughly 2× memory
  and 5–10× fewer solves, which would bring the cascade within GPU limits.
* A GPU with more memory.
* A lower-loss or thicker laminate.
* Space-mapping or surrogate models [@bandler2004space] trained on the
  calibration data.
* Making the physics sanity checks a mandatory step of the agent loop rather
  than a habit.

# Conclusion

An LLM coding agent took an SIW bandpass filter from specification to
fabrication files, with one engineer supervising. Two things decided the
outcome. The first was replacing black-box search over a discontinuous
objective with calibration of smooth observables on small structures. The
second was catching a long series of silent defects with physics checks. The
fabricated N = 3 filter is centred within 6 MHz of target with 1.7 dB loss,
close to its laminate's floor. It misses the return-loss and bandwidth
specification for reasons the coupling-matrix fit identifies. Measurements
will close the loop.

# Acknowledgment {-}

The design software, simulations, figures and a first draft of this text
were produced with Claude Code (Anthropic; Claude Sonnet 5, Opus 5 and 5.5,
Fable 5) under the author's direction, as described in Sec. III. The author
reviewed all results and text and takes full responsibility for them
[@ieee_ai_policy]. The complete history and data are available in the
project repository.

```{=latex}
\FloatBarrier
```

# References {-}

::: {#refs}
:::
