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
  We report the design, fabrication and measurement of a third-order, 2.87 GHz
  substrate integrated waveguide bandpass filter. A large-language-model
  coding agent wrote and operated the entire toolchain: Chebyshev synthesis,
  parametric geometry, finite-element simulation with the open-source solver
  Palace, Bayesian optimization, and the export of fabrication files. One
  engineer set the specification, took the design decisions and ran the
  commercial-solver cross-checks. Three results stand out. First, a
  Gaussian-process optimizer applied to the assembled filter never reached a
  usable match. This is because the passband width it scores is discontinuous
  in the external coupling. Measuring smooth observables on small structures and
  inverting the coupling relations converged in about three solves per curve.
  Second, most of the 47 fixes in the project history corrected defects that
  produced plausible numbers without raising any error. We classify them and
  list the checks that now catch each class. Third, JLCPCB made the board on
  Rogers RO4350B with ENIG finish for about USD 120. We measured it with a
  vector network analyzer and recalibrated the data independently in software.
  It is centred at 2.894 GHz with 171 MHz bandwidth, 2.0 to 2.4 dB insertion loss and
  one broad reflection minimum near -18 dB. This is the floor of the calibration
  check. The simulation predicted 2.876 GHz, 182 MHz, 1.7 dB and three zeros.
  The measured loss matches an effective unloaded Q of 150 to 185, as expected
  once the copper loss is added to the simulation. The -16 dB specification is
  not met.
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
          Argentina\\ fborello@frba.utn.edu.ar}%
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
coarse model. Learned models are also used to extract coupling matrices from
simulated responses, recently with physics-informed networks that need no
labelled training set [@sallam2026pidnn]. In each of these approaches the engineer still writes the
geometry scripts, the meshing, the port setup, the objective and the export
code. The engineer also interprets what the solver returns.

Recent large-language-model (LLM) agents work differently: they write and run
code in a loop, observe the results and revise [@yao2023react;
@yang2024sweagent]. Agent frameworks now exist for RFIC design
[@xing2026rfagent] and RF amplifiers [@lu2026rfampdesigner]. An agent has also
operated CST, ADS and KiCad through their scripting interfaces to design a GNSS
front end [@heinrichs2026prompt]. Empirical studies of bugs in agentic
frameworks classify failures of the agent software itself
[@zhang2026agenticbugs]. These reports leave one thing largely unmeasured:
how the *engineering* fails when an agent drives it. These failures are
defects in the physical model that the agent writes. They matter more than the
successes when one decides how much to trust the numbers.

This paper reports one complete design effort of that kind. The object is a
classic structure, a three-cavity Chebyshev substrate integrated waveguide
(SIW) filter [@deslandes2003single; @bozzi2011review; @chen2014siwfilter]. We
chose it because its physics is textbook, so every agent-produced number can be
checked against theory. An LLM coding agent (Claude Code [@claudecode])
wrote and ran all of the design software. The author acted as specifier,
reviewer and decision-maker. The project history is preserved in git, and most
claims below map to a commit or a stored result. Some process statistics
survive only in engineering notes written at the time, not in raw logs. One
example is the screen-out rate of the Bayesian search. We flag these where
they appear.

The contributions are:

1. An account of the tool path. A finite-difference time-domain (FDTD) solver
   (openEMS) could not support match tuning, but a finite-element solver
   (Palace) could. A GPU workstation, run through remote agent sessions, had
   memory limits that eventually pushed all production runs onto CPUs
   (Sec. III).
2. A measured explanation of why black-box Gaussian-process (GP) search over
   the assembled filter fails, and of why calibrate-and-invert succeeds
   (Sec. IV).
3. A taxonomy of the silent modelling defects the process produced and
   caught, with the guard that now blocks each class (Sec. V).
4. The fabricated design, and a diagnosis of its deviation from the
   specification by coupling-matrix extraction. This item also covers a
   documented dual-mode negative result, an insertion-loss budget, a launch
   study and the manufacturing path. It ends with the measurement of the
   fabricated board with a vector network analyzer (VNA) (Secs. VI to VIII).

# Filter specification and synthesis

The specification is f0 = 2.87 GHz, 5 % fractional bandwidth (FBW, 143.5 MHz),
0.1 dB Chebyshev ripple and |S11| $\le$ −16 dB in band. The laminate is Rogers
RO4350B, 0.76 mm thick ($\varepsilon_r$ = 3.66, $\tan\delta$ = 0.0037 [@rogers4350b]), with
0.5 oz copper. The fence vias are 1.5 mm in diameter at a 3.0 mm pitch. Their
p/d = 2 ratio is at the edge of the leakage rules of
[@xu2005guided; @deslandes2006accurate]. Smaller vias (0.8 mm at 1.5 mm pitch)
were compared three times under three different objectives and never matched
this choice. The connector is a Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA
[@taoglas_sma].

## Design equations

The low-pass Chebyshev prototype gives $g_1 = g_3 = 1.0316$ and $g_2 = 1.1474$
for $N = 3$ and 0.1 dB ripple [@hong2001microstrip]. The bandpass mapping turns
them into two numbers that the geometry must reproduce: the coupling between
adjacent cavities and the external quality factor of the end cavities:

```{=latex}
\begin{equation}
k_{i,i+1} = \frac{\mathrm{FBW}}{\sqrt{g_i\,g_{i+1}}} = 0.0460 ,
\qquad
Q_e = \frac{g_0\,g_1}{\mathrm{FBW}} = 20.63 .
\label{eq:synth}
\end{equation}
```

We choose the TE10 cutoff near $0.7 f_0$, which sets the equivalent width. The
Cassivi–Wu correction then gives the real width for the finite via fence
[@cassivi2002dispersion]:

```{=latex}
\begin{equation}
a_\mathrm{eff} = \frac{c}{2 f_c \sqrt{\varepsilon_r}} , \quad f_c \approx 0.7 f_0 ,
\qquad
a_\mathrm{siw} = a_\mathrm{eff} + \frac{d^2}{0.95\,p} .
\label{eq:width}
\end{equation}
```

Each cavity length follows from the TE101 resonance condition:

```{=latex}
\begin{equation}
f_{101} = \frac{c}{2\sqrt{\varepsilon_r}}
\sqrt{\frac{1}{a_\mathrm{eff}^{2}} + \frac{1}{L^{2}}} .
\label{eq:te101}
\end{equation}
```

Eq. (\ref{eq:te101}) assumes ideal walls, so the real length is shorter once the
tapers and apertures load the cavity (Sec. VI). The feed is a 50 Ω microstrip
line (Hammerstad [@hammerstad1980accurate]) flared into the SIW by a Deslandes
taper [@deslandes2010design]. At the board edge it becomes a grounded coplanar
waveguide (CPWG) launch sized to the SMA footprint. The launch has a 1.2 mm
trace with 0.2512 mm gaps. Conformal mapping gives 50.0 Ω for these dimensions
[@wadell1991transmission; @simons2001coplanar].

The two couplings are measured, not computed, because closed-form iris formulas
are unreliable for SIW. Two coupled closed cavities split their resonance into
$f_1$ and $f_2$, and a single cavity driven through its apertures has a loaded
quality factor $Q_L$:

```{=latex}
\begin{equation}
k = \frac{f_2^{2} - f_1^{2}}{f_2^{2} + f_1^{2}} ,
\qquad
Q_e = \frac{2}{1/Q_L - 1/Q_u} .
\label{eq:extract}
\end{equation}
```

The coupling-matrix formulation [@cameron2003advanced; @cameron2018microwave]
provides the ideal target response and, later, the diagnostic fit. The
unloaded quality factor $Q_u$ sets the dissipation of a narrowband filter
[@hong2001microstrip]:

```{=latex}
\begin{equation}
\mathrm{IL}_0 \approx \frac{4.343 \sum_i g_i}{\mathrm{FBW}\; Q_u} \ \text{dB}.
\label{eq:il}
\end{equation}
```

# Toolchain and working method

Fig. \ref{fig:flow} shows the flow and the division of labour.
Fig. \ref{fig:timeline} shows how the effort was spread over time.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_flow.png}
\caption{Design flow. The agent writes and operates every stage through one
command-line tool (\texttt{siw}). The engineer supplies the specification and
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

The first iteration (June 2026) used analytic dimensions. It used the free FDTD
solver openEMS [@liebig2013openems] for calibration and CST Studio Suite 2021
[@cst2021] as the reference. Python generated a parametric CST VBA macro. The
macro builds native solids wrapped in the solver's history list. The analytic cavity
length of 38.23 mm put the CST passband at 2.818 GHz with a 293 MHz band,
3.65 dB insertion loss and only 1.02 dB return loss. The external coupling was
uncalibrated and heavily over-coupled.

openEMS was abandoned for three reasons. First, FDTD resolves the 1.5 mm
cylindrical vias on a staircase grid. This needs at least three cells per
diameter over the whole board. The resonant, high-Q structure also rings down
slowly, so each full-filter run took minutes to tens of minutes. Second, the
ports did not give a trustworthy S11. The lumped port radiated like a point
source instead of launching the microstrip mode. The microstrip port launched
the mode correctly, but its S11 de-embedding was unstable and even returned
|S11| > 1. The passband and S21 were reproduced, but the match could not be
tuned. Matching was the whole remaining problem. Third, openEMS had no
eigenmode solver for the coupling calibration of Sec. IV. The calibration had
to be emulated by reading peak splits off driven sweeps.

Palace [@palace2023] removed all three obstacles. It is an MPI-parallel
finite-element solver built on MFEM [@anderson2021mfem] with gmsh meshes
[@geuzaine2009gmsh]. Its tetrahedral mesh conforms to the vias. Its wave ports
solve the 2D port mode, as CST's do, and are passive by construction. It has an
eigenmode solver. JSON files drive it entirely, which makes it easy for an
agent to operate. A first Palace model reproduced the CST result for the same
geometry and then replaced openEMS in the loop.

## Phase 2 onward: an agent-operated toolchain

From August the agent consolidated three copied optimizer scripts into one
package with a `Topology` interface and a single command-line tool (`siw`).
The tool covers synthesis, layout, eigenmode and driven solves, Bayesian
design, 1-D scans, calibration, comparison figures and CAD export. Every
production number in this paper can be reproduced with that tool. Curated
results are stored in a `golden/` directory together with their S-parameters
and the command that reproduces them. A project brief file (`CLAUDE.md`) acted
as the agent's persistent memory across sessions. Handoff documents carried
the state from one machine to another.

**From the textbook steps to the tool.** Table \ref{tab:pipeline} lists the
steps that a coupled-resonator SIW filter normally takes by hand and the
command that replaces each step. The equations are the classical ones
[@hong2001microstrip; @cassivi2002dispersion; @deslandes2006accurate]. The tool
changes two things. Every step that used to be a hand-fitted curve is now a
measurement with a solver. The chain from specification to gerbers is now one
sequence of commands.

```{=latex}
\begin{table*}[t]
\centering
\footnotesize
\caption{The design steps of an SIW coupled-resonator filter: the textbook way and what the tool does.}
\label{tab:pipeline}
\begin{tabular}{p{0.8cm}p{2.3cm}p{6.6cm}p{6.6cm}}
\hline
 & \textbf{Step} & \textbf{By hand} & \textbf{In the tool} \\
\hline
1 & Synthesis & Chebyshev $g_i$ by recursion; $k_{i,i+1}=\mathrm{FBW}/\sqrt{g_ig_{i+1}}$, $Q_e=g_0g_1/\mathrm{FBW}$; ideal response from the coupling matrix & \texttt{synthesis.py}: targets $k$, $Q_e$ and the ideal \texttt{target.s2p} \\
2 & Waveguide width & $a_\mathrm{eff}=c/(2f_c\sqrt{\varepsilon_r})$ with $f_c\approx0.7f_0$; $a_\mathrm{siw}=a_\mathrm{eff}+d^2/(0.95p)$; via rules on $p/d$ & \texttt{siw\_geometry.py}, from the substrate and via presets in \texttt{config.py}; builds the via fences and the board \\
3 & Cavity length & $f_{101}=\dfrac{c}{2\sqrt{\varepsilon_r}}\sqrt{a_\mathrm{eff}^{-2}+L^{-2}}$ & first guess only; corrected from a driven solve in step 7 \\
4 & Feed & 50\,$\Omega$ microstrip width (Hammerstad), taper (Deslandes), coplanar gap by conformal mapping & \texttt{siw\_geometry.py}, \texttt{launch.py}: taper and the CPWG footprint of the SMA \\
5 & Internal coupling & simulate two coupled cavities, read the split $k=(f_2^2-f_1^2)/(f_2^2+f_1^2)$, fit $w(k)$ & \texttt{siw calibrate --what k}: Palace eigenmode of a closed two-cavity model, polynomial fit, inverted at the target $k$ \\
6 & External coupling & one resonator, $Q_L$ from the $-3$\,dB width or the group delay, $Q_e=2/(1/Q_L-1/Q_u)$ & \texttt{siw calibrate --what qe}: one driven cavity with two apertures, fit of $w_\mathrm{ext}(Q_e)$ \\
7 & Assembly and tuning & simulate the whole filter, change lengths and irises by hand until the reflection zeros are equiripple & \texttt{siw synth-design}: joint $(k,f_c)$ refinement, driven centre-frequency trim, separate middle-cavity correction, pole-shape check \\
8 & Final polish & manual sweeps of one parameter at a time & \texttt{siw design --seed}: local Bayesian search (below) \\
9 & Layout and CAD & CST model drawn by hand; gerbers from a PCB tool & \texttt{siw cst}, \texttt{siw kicad} and 34 file-level checks \\
10 & Verification & VNA measurement and calibration & \texttt{siw measure}: software recalibration and comparison with the simulations \\
\hline
\end{tabular}
\end{table*}
```

**The optimizer.** The search code is our own, written around Palace, not a
package taken from a design tool. A candidate is a set of geometry parameters:
the cavity lengths (mirrored about the centre), the iris widths, the external
aperture and the taper length. The microstrip width stays at its 50 Ω value.
To evaluate a candidate, the code meshes the whole board with gmsh, including
the connectors and the launch. It then writes the Palace configuration and runs
a driven sweep on a coarse mesh. Finally it reads $|S_{11}|$ and $|S_{21}|$. A
fast physics screen at $f_0$ runs first. It rejects candidates that do not
resonate. The rejected ones get a graded penalty, so the surrogate still sees a
gradient. The objective sums these terms. The first is the root-mean-square
error (RMSE) of $|S_{11}|$ against the ideal Chebyshev response (both clipped at
a floor). The others are the shape of $|S_{21}|$, the insertion loss, the
centre-frequency error outside a deadband, a two-sided bandwidth error and the
board length. Three one-sided hinges add the real specification: worst in-band
$S_{11}\le-16$ dB, loss within an allowance over the dielectric floor, and
symmetry. The objective went
through ten revisions (v9–v18). The early ones scored individual points, and
the later ones fitted the whole response. A Gaussian-process surrogate
(scikit-optimize [@skopt; @rasmussen2006gaussian], `gp_hedge` acquisition)
proposes each next candidate. A random seeding phase comes first, and its size
scales with the budget. A patience rule stops the search early on a plateau.
The winner is solved again on a fine mesh, and the result is checked after
every dimension is rounded to the 0.1 mm fabrication resolution. In local mode
(`--seed`, `--span`) the search box is a few millimetres around a calibrated
design. A coarse evaluation takes 6–20 min, so sample efficiency matters more
than throughput. A lock serialises the Palace solves.

**Compute.** To speed up the search, we moved to a workstation with an NVIDIA
GTX 1660 SUPER (6 GB) and ran Palace there with its GPU backend. The author
supervised the long agent sessions remotely through Claude Code's Remote
Control. On the dual-mode model the GPU was 1.24× faster than 4 CPU ranks. The
S-parameters were identical to 10⁻⁹ dB. Disabling MFEM's pooled allocator
(`MFEM_MEMORY=cuda`) removed the first out-of-memory failures. Those failures
had killed every point of an eigenmode sweep. But the card does not have enough
memory for the meshes that matter. It finished a driven solve with 174.6 k
tetrahedra and ran out at 178.4 k, in the error estimator. Only one rank per
card works. The 166 mm cascade exceeds that limit at any adequate mesh density,
so no GPU mesh preset was ever validated for it. The code now caps GPU use at
176 k tetrahedra and falls back to the CPU. We did not try the GPU on the
fine-mesh verification. That verification needs 315 k unknowns and about 5.5 GB
on the CPU. All production runs therefore ran on CPUs with 4 MPI ranks. Four
attempts on a 3.7 GB host failed, three of them explicitly out of memory. The
final runs used a 16 GB host at about 8 s per frequency point. Memory, not
arithmetic, was the binding constraint. A card with more memory would bring the
cascade onto the GPU. So would the half-model and adaptive sweeps of Sec. X.

## Who did what: models and effort

The commit trailers and the agent's session logs record which model was
working and for how long. Table \ref{tab:models} and Fig. \ref{fig:effort}
summarise them. They come from `docs/paper/make_process_stats.py`, which keeps
only counts, with no prompts and no file contents.

```{=latex}
\begin{table*}[t]
\centering
\footnotesize
\caption{Models used, from the session logs and the commit trailers. Turns are
assistant messages in the main thread, plus those of sub-agents. Output tokens
cover both. Fix commits are those whose message starts with \texttt{fix}.
Commit counts are for the history up to commit \texttt{4d570ac}.}
\label{tab:models}
\begin{tabular}{lccccc}
\hline
\textbf{Model} & \textbf{Main-thread dates (2026)} & \textbf{Turns (main + sub-agent)} & \textbf{Output tokens (M)} & \textbf{Commits with trailer} & \textbf{of which fix} \\
\hline
Sonnet 5   & 22 Aug--10 Sep & 9\,287 + 1\,362 & 8.41 & 64 & 16 \\
Opus 5     & 22 Aug--4 Sep  & 3\,673 + 65     & 3.57 & 43 & 14 \\
Fable 5    & 28 Aug         & 48              & 0.06 & 1  & 0 \\
Opus 5.5   & 23--29 Sep     & 922             & 0.73 & 12 & 0 \\
Sonnet 5.5 & 15 Oct         & 424 + 200       & 0.63 & 5  & 0 \\
\hline
\textbf{Total} & & 14\,354 + 1\,627 & 13.39 & 125 & 30 \\
\hline
\end{tabular}
\end{table*}
```

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_effort.png}
\caption{Effort over time. Top: hours per day in which the agent was active,
counting only gaps shorter than 20 min between logged events. Bottom: commits
per day, coloured by the model named in the commit trailer. Grey commits have
no trailer.}
\label{fig:effort}
\end{figure*}
```

What the numbers show:

* *Two models worked side by side.* Sonnet 5 and Opus 5 were both active from
  22 August to early September, with about the same share of commits (64 and
  43) and fixes (16 and 14). Sonnet 5 produced 70 % of the output tokens of
  that period. The logs record the model of every turn but not why it was
  chosen. The later work used Opus 5.5 (23--29 September, the fabrication
  files and the final checks) and Sonnet 5.5 (15 October, the measurement and
  this text). One 48-turn run on Fable 5 on 28 August produced one commit.
* *Sub-agents did a small part.* There were 27 sub-agent runs, 26 on Sonnet
  models and one on Opus 5. They account for 4 % of the output tokens.
* *Effort was concentrated.* The agent was active for 135 hours on 21 days.
  The busiest days, 24, 28 and 31 August, each had 14--15 hours. The engineer
  sent about 500 messages, which is 24 per active day.
* *Most of the work was running things.* The logs hold 4\,393 shell commands
  (3\,816 in the main thread and 577 in sub-agents), 738 file edits, 758 file
  reads and 74 web searches. The agent also called a timer 874 times and a
  monitor 214 times. These calls waited for solver runs that lasted from
  minutes to hours, without holding the conversation.
* *Fixes were a fifth of the history.* 47 of 220 commits are fixes (21 %).
  Of the 125 commits with a trailer, 30 are fixes. The trailer is a lower
  bound for agent work. Of the 198 commits between 22 August and 10 September,
  90 have no trailer. The logs show the agent working on every one of those
  days.
* *Code was rewritten.* The history adds 16.1 k lines of Python and removes 5.9 k,
  including the clean-up of 15 October. A typical commit touches two files. The
  package now has 12.4 k lines.

# Why global Bayesian search failed

The GP worked as intended in one regime: as a local polish around a validated
design. For the dual-mode filter, a 30-evaluation search in a ±2 mm,
5-dimensional box confirmed the landed geometry. Neighbouring probes came back
worse, and the apparent 0.41 dB gain lay inside the measured coarse-mesh noise
floor of 0.64 dB.

Run globally over the assembled cascade, the same machinery never produced a
worst in-band S11 better than −5 dB in more than 60 driven evaluations. The
cause is structural. The objective scores the passband width. That width is
discontinuous in the external aperture $w_{\text{ext}}$. Below a coupling
threshold, only the centre pole clears the −3 dB line, so the band measures one
resonance. Above the threshold, all N poles merge and the width jumps. On the
N = 3 cascade the widths recorded during the search were 16, 22, 36, 65 and
then 215 MHz. The 143.5 MHz target lies inside the jump. We re-measured this
for the paper on the fabricated geometry (Fig. \ref{fig:calib}c, data in the
repository). The width rises 96, 106, 123 MHz for $w_{\text{ext}}$ = 10–12 mm
and jumps to 195 MHz at 13 mm. It then *falls* again, because the end cavities
become over-coupled and the reflection zeros drop from three to one. The target
width is crossed twice. The second crossing, at 16 mm, has one reflection
zero and −4 dB of return loss. A bandwidth-driven search lands there, and so
does the scan's own inversion (15.2 mm). A GP assumes a smooth objective, so it
inherits both the jump and the false solution. The search-health data showed
the same thing. On the cascade, 57–83 % of candidates were screened out, which
left 2–9 informative points per run. On the dual-mode filter, where the search
converged, 34–37 % were screened out and there were about 19 informative
points.

The replacement measures each coupling on the smallest structure that shows it
(Fig. \ref{fig:calib}):

* **Internal coupling.** A closed two-cavity eigenmode solve splits the
  cavity mode into $f_1$ and $f_2$, and $k$ follows from Eq. (\ref{eq:extract}).
  It is smooth in $w_{\text{iris}}$.
* **External Q.** One cavity driven symmetrically through two apertures gives
  the loaded Q, and $Q_e$ follows from Eq. (\ref{eq:extract}). Here
  $Q_u = 1/\tan\delta = 270.3$. The eigenmode Q independently matches this
  value. It is smooth and monotonic in $w_{\text{ext}}$.

We inverted the fitted curves at the synthesis targets, assembled the filter
and made a final driven trim of the centre frequency (fc). This converged in
about three solves per curve. The re-run calibration for this paper inverts to
$w_{\text{iris}}$ = 13.85 mm and $w_{\text{ext}}$ = 13.53 mm. The fabricated
board has 14.42 and 13.96 mm, and its end cavities were trimmed afterwards.
The resulting internal coupling was within 2 % of target. At that checkpoint
the N = 4 centre frequency also landed at 2.870 GHz. The N = 4 design was later
abandoned. Its best return loss was −6.1 dB (Sec. VI). The GP was kept only as
a local polish seeded with the result (`--seed`). The physics that worked is
textbook [@hong2001microstrip; @cameron2018microwave]. The agent's contribution
was to run the calibrations quickly and to diagnose why the black-box route had
failed.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_calib.png}
\caption{(a), (b) The calibration observables are monotonic and invertible
(dotted: synthesis target and inverted width). (c) The $-3$\,dB bandwidth of the
assembled filter, the quantity a black-box objective scores, jumps between 12
and 13\,mm and then falls. Labels: number of reflection zeros. Coarse mesh.}
\label{fig:calib}
\end{figure*}
```

Two further search failures came from the parameterization itself, not from
the search. The via fences were first generated by filtering a fixed grid, so
the iris width was *quantized*. The whole cascade search box spanned about two
distinct geometries. The GP was tuning a knob that did nothing
(Fig. \ref{fig:quant}). In addition, N $\ge$ 4 had a single shared iris width
and could not express the required k = [0.0415, 0.0329, 0.0415].

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_quantization.png}
\caption{Via-fence quantization. (a) With the fixed grid, requesting an iris of
6 mm or 9 mm placed exactly the same vias (dashed: requested edge, $w/2$). (b) With
the fix the iris arms start at $w/2$ and every requested width gives a different
mesh. (c) Opening actually meshed versus requested width: steps of about 6 mm
before, a straight line after. Six requested widths fell on only three geometries.}
\label{fig:quant}
\end{figure*}
```

# Silent defects: a taxonomy

As of 15 Oct 2026 (up to commit `4d570ac`) the history holds 220 commits, 125 of
them with an agent co-author trailer, and 47 labelled *fix*. Most of the fixes
corrected defects that never raised an error. The solver converged and the plot
looked reasonable, but the number was wrong. Table \ref{tab:bugs} groups
representative cases. Three rules paid off repeatedly. First, if a fix does not change
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

Two cases changed the course of the project. In the first, a real SMA coax
launch replaced the ideal port. The optimized microstrip width of 2.26 mm then
turned out to be a 41 Ω line. The optimizer had exploited a port that
normalizes to whatever it sits on. The true 50 Ω width is 1.664 mm. The first
coax model also used a full-size 0.82 mm pin, which is thicker than the 0.76 mm
board. It returned −0.2 dB S11. That was real physics, not a bug
(Fig. \ref{fig:sma}). In the second, an independent audit against CST showed
that the −13.37 dB return loss was a coarse-mesh artefact. We had used that
value to choose the cascade over the dual-mode design. The converged value is
about −10.7 dB. The decision survived, but the justification had to be
rewritten.

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
it to 2.982 and 3.077 GHz, a slope of about −37 MHz/mm. Palace models the
loading by the tapers and external apertures, which the analytic formula
ignores. With Palace the cavities shortened to about 34.4 mm. Calibrate-and-invert
then gave unequal cavities, 34.24/35.50/34.24 mm. The fine-mesh coupling fit
found the end cavities about 17 MHz low, so a −0.3 mm trim
(33.94/35.50/33.94 mm) was chosen. A −0.6 mm trim gained only 0.07 dB and cost
0.4 dB of band-edge loss. The measured sensitivity at the end cavities was
about 27 MHz/mm, roughly half the 50 MHz/mm rule of thumb.

**Board size.** We also explored the design space for a smaller board
(Figs. \ref{fig:layouts} and \ref{fig:designs}). The candidates were a
single-cavity dual-mode N = 2 filter (119 mm), the N = 3 cascade (166 mm) and
an N = 4 cascade (211 mm). We also tried three other single-cavity shapes:
corner-cut, circular-cross and rhombic. None came closer to the specification
than the dual-mode cavity (best S11 −6 to −9 dB). We closed the compact N = 4
made from two dual-mode cavities, after five mechanisms and a joint GP search
all stopped at two of four poles. The five mechanisms were offset apertures,
near-corner coupling, top-copper slots, discrete posts and quad-mode cavities.
A four-cavity single-mode cascade works, but it needs 180–206 mm.

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
the assembled filter show that bandwidth and match are *opposed* on every
geometry parameter of this topology. At $w_{\text{iris}}$ = 11 mm the band is
145.6 MHz (4.94 % FBW), but the return loss is −1.75 dB. The pad-only launch
used earlier reached −17.7 dB. That launch was not the one fabricated. N = 2
has only one internal and one external coupling. This is not enough freedom
to place two poles and also match them. The cascade has an extra degree of
freedom at 1.4× the length, and it won the head-to-head comparison.

# The fabricated design

The chosen geometry is $l_{\text{cav1}}$ = 33.939, $l_{\text{cav2}}$ = 35.503, $w_{\text{iris}}$ = 14.416,
$w_{\text{ext}}$ = 13.96, $l_{\text{taper}}$ = 15.738 and $w_{\text{ms}}$ = 1.6636 mm.
The board is 165.78 × 45.79 mm. Fig. \ref{fig:final} shows the fine-mesh result
(2.5/0.45 mm volume mesh, 0.15 mm coax ports, 9.12 mm air, 61 points).
The result is fc 2.876 GHz, −3 dB bandwidth 182.3 MHz and worst in-band
$|S_{11}|$ −11.15 dB. Insertion loss is 1.70 dB at the peak and 2.58 dB at the
band edge. Table \ref{tab:comparison} (Sec. VIII) sets it against the
specification, CST and the measurements.

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
refined sweep of the untrimmed board (Fig. \ref{fig:cmfit}) puts the external
coupling on target (+0.4 %), which exonerates the launch. It finds the internal
coupling 4.8 % weak and the end cavities 17 MHz low. The trim reduces the
detuning. The same fit on the fabricated geometry gives the end cavities 11 MHz
low. It gives the internal coupling 8 % weak and the external coupling 4.5 %
weak ($Q_e$ 22.6 against 20.6). The worst in-band point sits at the upper band
edge. There the equiripple region ends near 2.935 GHz, against a target edge of
2.942 GHz. Adding +0.6 mm of $w_{\text{iris}}$ on top of the trim widened the
band without helping. Adding +0.4 mm of $w_{\text{ext}}$ on top of both was
strongly harmful, and also pulled the end cavities down. No isolated
$w_{\text{ext}}$ trial was run. A coordinated local move remains open.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_coupling_fit.png}
\caption{Lossy coupling-matrix fit used to diagnose the return-loss gap.
Untrimmed board: external Q on target, $k$ 4.8\,\% weak, end cavities 17\,MHz low.}
\label{fig:cmfit}
\end{figure}
```

**Is the insertion loss (IL) what we should expect?** Yes, to within the
measurement uncertainty. A hand calculation shows this. It needs only a few
numbers. It also shows how much the real cavity length and the real copper
change the answer.

*Step 1: the loss formula.* The unloaded Q, $Q_u$, is the quality factor of one
cavity on its own, without the external circuit. It says how much energy the
cavity stores compared with what it loses in each cycle, so a higher $Q_u$ means
a lower insertion loss. It sets the loss of a narrowband filter,
Eq. (\ref{eq:il}). For $N=3$ the sum of the prototype elements is
$\sum g_i = 3.21$, and the design bandwidth is FBW = 0.05, so

```{=latex}
\begin{equation}
\mathrm{IL}_0 \approx \frac{4.343 \times 3.21}{0.05\, Q_u} = \frac{279}{Q_u}\ \text{dB}.
\label{eq:il279}
\end{equation}
```

*Step 2: the Q of one cavity.* The dielectric and the copper act in series,

```{=latex}
\begin{equation}
\frac{1}{Q_u} = \frac{1}{Q_d} + \frac{1}{Q_c} ,
\qquad Q_d = \frac{1}{\tan\delta} = 270 .
\label{eq:qu}
\end{equation}
```

The dielectric alone gives $279/270 = 1.03$ dB. For the copper we use the
conductor $Q$ of a TE$_{101}$ cavity [@pozar2012microwave],

```{=latex}
\begin{equation}
Q_c = \frac{(kaL)^3\, b\,\eta}{2\pi^2 R_s}\;
\frac{1}{2a^3b + 2bL^3 + a^3L + aL^3},
\label{eq:qc}
\end{equation}
```

with $k = 2\pi f\sqrt{\varepsilon_r}/c$ and $\eta = 377/\sqrt{\varepsilon_r}$.
The effective width is $a = 39.0$ mm (Sec. II) and the substrate height is
$b = 0.76$ mm. The cavity length is $L$. The surface resistance of copper at
2.87 GHz is $R_s = 14$ m$\Omega$ (skin depth $\delta = 1.23$ $\mu$m). The
fabricated end and middle cavities, 33.9 mm and 35.5 mm long, give
$Q_c$ = 519 and 547, so $Q_c$ is about 530--540 and we use 540. Copper alone
then costs $279/540 = 0.52$ dB. The two together give $Q_u = 180$ and 1.55 dB.

*Step 3: from the cavities to the board.* Palace models the walls as perfect
conductors, so its 1.70 dB contains the dielectric but no copper. It is
0.67 dB above the 1.03 dB of the formula. The simulated board also has about
60 mm of 50 Ω feed line, the SMA transition, radiation from the open
microstrip sections and the mismatch between the reflection zeros. The formula
contains none of them. We did not separate these terms. Only the feed line is
easy to estimate. On this laminate a 50 Ω line loses 1.5 dB/m in the
dielectric and 1.5 dB/m in smooth copper. So 60 mm cost 0.09 dB in each.

*Step 4: add the copper to the simulation.* The copper is an extra term, so
the expected loss is $1.70 + 0.52 + 0.09 = 2.3$ dB (Table \ref{tab:lossbudget}).
Real foil is rough. The Hammerstad factor $K = 1 + \tfrac{2}{\pi}\arctan\!\big(1.4(\Delta/\delta)^2\big)$
multiplies the conductor loss. For an rms roughness $\Delta$ of 0.5, 1 and 2
$\mu$m it is 1.14, 1.47 and 1.83. The total then becomes 2.4, 2.6 and 2.8 dB.
The measured 2.0--2.4 dB (±0.3 dB) is at or below the smooth-copper value, so
there is no unexplained loss. The data cannot tell smooth copper from a
roughness of up to about 1 $\mu$m rms.

```{=latex}
\begin{table}[t]
\centering
\caption{Insertion-loss budget at 2.87\,GHz (dB), from Eqs. (\ref{eq:il279})--(\ref{eq:qc}).}
\label{tab:lossbudget}
\begin{tabular}{p{0.74\columnwidth}c}
\hline
Cavity dielectric ($Q_d = 270$) & 1.03 \\
Feed lines, SMA launch, radiation, mismatch (rest of the Palace result) & 0.67 \\
\textbf{Palace, perfect-conductor walls} & \textbf{1.70} \\
Copper in the cavities ($Q_c \approx 540$) & $+0.52$ \\
Copper in the feed lines (about 60\,mm) & $+0.09$ \\
\textbf{Expected, smooth copper} & \textbf{2.3} \\
Same, rms roughness 0.5 / 1 / 2\,$\mu$m & 2.4 / 2.6 / 2.8 \\
\textbf{Measured (Sec.~VIII)} & \textbf{2.0--2.4} \\
\hline
\end{tabular}
\end{table}
```

The first version of this budget was written before the board was measured and
gave 2.1--2.3 dB. It used the simulated 6.3 % bandwidth in the loss formula
instead of the 5 % of the prototype, which the $g_i$ belong to. It also used a
copper term of 0.4 dB. With the corrected terms, the dielectric part moves from
0.8 to 1.0 dB, the copper part from 0.4 to 0.5 dB, and the total from 2.2 to
2.3 dB. The 0.52 dB for copper agrees with two other estimates. The
coupling-matrix model adds 0.55 dB when $Q_u$ falls from 270 to 180. An
exterior-face copper model in Palace adds 0.59 dB. This is a lower bound,
because the internal trace and ground sheets stay ideal there.

**How the real length and the copper move the answer.**

* *Cavity length.* $Q_c$ grows with the size of the cavity: 519 at 33.9 mm,
  593 at the analytic 38.2 mm of Phase 1. The trimmed cavities therefore lose
  about 0.07 dB more than the analytic ones would. A length tolerance of
  $\pm0.1$ mm moves the centre frequency by 2.7 MHz (27 MHz/mm) but $Q_c$ by
  only 0.3 %, so it does not change the loss.
* *Board length.* Each 10 mm of 50 Ω feed line costs 0.03 dB in smooth copper.
  The 165.8 mm board carries about 60 mm of feed line, so the feeds cost 0.2 dB
  of the total.
* *Copper roughness.* Doubling the conductor loss ($K$ = 2) would add 0.6 dB.
  The measurement suggests that it is lower.
* *Bandwidth.* The loss scales as $1/\mathrm{FBW}$: for the same $Q_u$, a 10 %
  filter would lose half as much as this 5 % one.
* *Laminate.* The loss scales with $\tan\delta$: a 10 % change in $\tan\delta$
  moves the dielectric part by 0.1 dB. The band edges lose more than the
  centre (2.58 dB in Palace) because the group delay peaks there.

A 1.52 mm RO4350B board only reaches IL $\approx$ 1.3 dB, because $Q_d$ still
dominates. RT/duroid 5880 ($\tan\delta$ $\approx$ 0.0009) at 1.52 mm would
bring it to about 0.5 dB.

**Cross-solver check.** CST Frequency Domain, run from the generated macro,
agreed with Palace on fc (2.876 vs. 2.875 GHz) and IL (1.80 vs. 1.85 dB) on the
untrimmed board. Getting there took ten debugging steps on the macro and the
solver setup. Seven of them were actual fixes. We also built a coax-only
control model, to separate port problems from filter problems. In Table
\ref{tab:comparison} the CST run gives 2.878 GHz, 180 MHz and 1.80 dB. Palace
gives 2.876 GHz, 182 MHz and 1.70 dB on the fabricated geometry. The CST
geometry is the untrimmed one. The time-domain solver was never made fully
stable.

**The connector is part of the design.** Figs. \ref{fig:launch} and \ref{fig:renders} compare
three launches on the same geometry: a bare microstrip feed, the CPWG launch
without a connector, and the CPWG launch with the SMA. Without the connector
only one reflection zero remains, and the worst in-band S11 is −6.3 dB
(microstrip) or −5.1 dB (CPWG), against −11.1 dB with it. The filter was
tuned with the connector's reactance in place. The bare CPWG port also shows
a port-modelling trap. Its first two Palace modes belong to the ground pours
(S21 $\approx$ −78 dB). The signal mode is mode 3.

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
gerbers, the drill files and a STEP solid. It also runs 34 automated
file-level checks [@jlcpcb_caps]. The checks include drawn-versus-meshed
geometry and CST-versus-mesh via positions. JLCPCB stocks RO4350B 0.76 mm but
offers only 1 oz outer copper. That leaves the finished thickness at about
0.84 mm at the pads. The SMA fork slot is 0.81 ± 0.1 mm, so the fit is
marginal. It can be fixed by removing 15–20 µm of copper under the connector
legs. In practice the author did this with a nail file until the connector
seated in the slot. The gerbers carry the no-mask requirement, and the order
notes state it. The boards were ordered from JLCPCB on Rogers RO4350B with an
electroless nickel immersion gold (ENIG) finish. The order cost about USD 120,
laminate surcharge included. We chose ENIG because the unmasked copper is
exposed and ENIG is a durable barrier. We assumed that the plating, which sits
on the air side of the copper, does not touch the cavity fields. The
measurement cannot exclude it on the feed lines (Sec. VIII).

# Measured results {#sec:vna}

## Setup and calibration

The board (Fig. \ref{fig:setup}) was measured with a Keysight FieldFox N9917A
handheld vector network analyzer (18 GHz), from 100 MHz to 5 GHz with 10 001
points, 10 kHz IF bandwidth and −15 dBm source power. The instrument was
calibrated at the ends of the two test cables in full two-port SOLR
(short-open-load-reciprocal) mode with a generic SMA kit. The short, open and
load were connected on each port. Both cables end in SMA plugs and cannot mate
with each other, so the thru was a female-female SMA adapter of unknown length
and loss; SOLR is meant for exactly that (the R stands for a reciprocal,
unknown thru). Isolation was omitted. The generic
standards are not a characterised vendor kit; the instrument was set to the
definitions of the 3.5 mm 85033D/E kit, the nearest it offers, so the true
offset delays, open capacitance and load return loss are unknown. The
cables end in SMA plugs that mate directly with the board's jacks, so the
reference plane is the connector face, as in the simulations. Four states of
the same board were saved: connectors soldered, or seated against the board
without solder, each with the instrument calibration applied and without it.
The raw open, short, match and thru were saved as well, at the same plane.

```{=latex}
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_setup.jpg}
\caption{Measurement setup. Top: the fabricated board with its connectors
and test cables (no soldermask, ENIG finish). Bottom left: bench setup with
the VNA. Bottom right: the instrument's calibration screen (3.5 mm 85033D/E
definitions selected, full two-port SOLR with unknown thru).}
\label{fig:setup}
\end{figure}
```

**Software recalibration.** The raw standards allow a second, independent
correction. We solved the eight-term error model in software, with a one-port
short-open-load calibration on each port and the unknown-thru step for the
transmission terms [@ferrero1992unknownthru], using scikit-rf
[@arsenovic2022scikitrf], and applied it to the two uncalibrated boards.

*How it works, in short.* The analyzer does not see the board directly:
between its receivers and each connector face sit cables, the switch and the
instrument's own electronics. That path is modelled at each port as an
*error box*, an unknown two-port (the eight-term model, seven independent
terms per frequency). Calibrating means measuring known standards to solve for
the two boxes; correcting means removing them from the filter measurement.
Per frequency, in three steps:

1. *One port at a time (SOL).* At port 1 the measured reflection
   $\Gamma_m$ and the true $\Gamma$ are related by
   $$ \Gamma_m = e_{00} + \frac{e_{10}e_{01}\,\Gamma}{1 - e_{11}\Gamma}, $$
   with $e_{00}$ the directivity, $e_{11}$ the source match and $e_{10}e_{01}$
   the reflection tracking. Multiplying out the denominator makes it linear,
   $\Gamma_m = e_{00} + \Gamma\,\Gamma_m\,e_{11} - \Gamma\,\Delta_e$ with
   $\Delta_e = e_{00}e_{11} - e_{10}e_{01}$, and the three standards of known
   $\Gamma$ (short $\approx -1$, open $\approx +1$, load $\approx 0$) give a
   $3\times3$ system. Port 2 gives $e_{33}$, $e_{22}$ and $e_{23}e_{32}$ the
   same way.
2. *Transmission from the unknown thru.* One term is left, the transmission
   tracking $e_{10}e_{32}$ that links the two boxes. Classic SOLT takes it from
   a zero-length thru, which does not exist here because the female-female
   adapter has a length and loss we do not know. The unknown-thru method
   [@ferrero1992unknownthru] only uses that the adapter is reciprocal,
   $S_{21} = S_{12}$. With the boxes of step 1 known, that condition gives
   $$ (e_{10}e_{32})^2 = e_{10}e_{01}\; e_{23}e_{32}\;
      \frac{S_{21,m}}{S_{12,m}}, $$
   where $S_{21,m}$ and $S_{12,m}$ are the adapter's measured transmissions.
   The root has two solutions of opposite sign; at each frequency we keep the
   one that leaves the corrected adapter's phase closer to an ideal thru
   (within $\pm 90^\circ$). The sign only changes the phase of $S_{21}$, not
   the magnitude we report.
3. *Correction.* With both boxes known, each filter measurement is converted
   to transfer parameters $T$, in which a cascade is a product:
   $T_m = T_A\,T_{\text{DUT}}\,T_B$, so
   $T_{\text{DUT}} = T_A^{-1}\,T_m\,T_B^{-1}$, then back to $S$.

The instrument's switch terms were not measured, so the switch is assumed
matched, as isolation is assumed negligible. The
open and short follow the definitions the instrument was set to: a model of the
85033D/E (about 30 ps offset delay and 49 fF fringing capacitance; typical
values, not read from the instrument). The result agrees with the instrument-corrected files to a mean $|\Delta\Gamma|$ of
0.03 for $S_{11}$ and 0.04 for $S_{22}$, and to 0.17 dB for $S_{21}$, over
2.6–3.2 GHz (Fig. \ref{fig:calcheck}). Replacing the kit model by ideal
$+1/-1/0$ standards changes the magnitudes by less than 0.03 dB ($S_{21}$) and
0.09 dB ($S_{11}$) and only moves the reference plane.

*Comparison with TOSM.* Classic TOSM (thru-open-short-match, Keysight's SOLT)
uses the same standards and is identical in steps 1 and 3; only step 2
changes. TOSM declares the thru ideal and of zero length
($S_{11} = S_{22} = 0$, $S_{21} = S_{12} = 1$), and with that assumption the
thru measurement gives the transmission term directly:
$$ S_{21,m} = \frac{e_{10}e_{32}}{1 - e_{11}\,e_{22}'}
   \;\Rightarrow\; e_{10}e_{32} = S_{21,m}\,(1 - e_{11}\,e_{22}'), $$
$$ e_{22}' = \frac{S_{11,m} - e_{00}}{S_{11,m}\,e_{11} - \Delta_e}, $$
where $e_{22}'$ is the port-2 load match seen from port 1 through the thru,
found by inverting the step-1 equation (12-term model; the reverse direction is
analogous). With an unknown thru, by contrast, $S_{21,m}$ and $S_{12,m}$ share
the same denominator, and their ratio cancels it together with the adapter's
own transmission; this is why UOSM (SOLR) does not need to know the thru and
TOSM does. If the thru is not ideal, TOSM loads its loss, phase and mismatch
into the error terms.

To size that discrepancy we calibrated the same raw files both ways, with the
same standard definitions (Table \ref{tab:tosm}). TOSM changes the
transmission term by $+0.33$ dB and $-3.4^\circ$ at 2.87 GHz and, by
construction, leaves the corrected adapter at 0 dB and $0^\circ$; with the
unknown thru the adapter reads $+0.27$ dB and $-3.1^\circ$, and the instrument
reads it at $+0.18$ dB and $-2.2^\circ$. On the soldered board TOSM raises the
insertion loss from 2.04 to 2.39 dB, narrows the band by 2.3 MHz and moves
$f_c$ by 2 MHz; the worst in-band $S_{11}$ barely changes, and the best one
deepens by 4 dB, because in TOSM $e_{22}'$ comes from the thru's $S_{11}$ and
declaring the adapter's reflection zero ($-22$ dB after the unknown-thru
correction) moves that reflection into $e_{22}'$. That the TOSM loss matches the
instrument's (2.38 dB) is a coincidence: the instrument did not treat the
adapter as ideal, as its $+0.18$ dB reading shows, and over the rest of the band
TOSM is no closer to the instrument in transmission (mean $\Delta S_{21}$
$+0.14$ against $+0.17$ dB) and further in reflection (mean $|\Delta\Gamma|$
0.041 against 0.030). The difference between the two methods, about 0.35 dB in
insertion loss, is of the order of the 0.3 dB uncertainty assigned to $S_{21}$
below.

<!-- BEGIN siw-table:tosm -->
```{=latex}
\begin{table*}[t]
\centering
\footnotesize
\setlength{\tabcolsep}{6pt}
\caption{Software calibration of the same raw files with an unknown thru (the reported one) and with TOSM, which declares the female-female adapter an ideal zero-length thru. Soldered board; the last column is the instrument's own calibration (SOLR, unknown thru). The adapter row is the thru itself after correction, at 2.87\,GHz. Mean differences over 2.6--3.2\,GHz.}
\label{tab:tosm}
\begin{tabular}{lccc}
\hline
 & \textbf{Unknown thru} & \textbf{TOSM} & \textbf{Instrument} \\
\hline
$e_{10}e_{32}$ at 2.87\,GHz & $-$12.04 dB $\angle$81.7$^\circ$ & $-$11.71 dB $\angle$78.3$^\circ$ & -- \\
Corrected adapter $S_{21}$ & +0.27 dB $\angle$$-$3.1$^\circ$ & 0 dB $\angle$0$^\circ$ (by definition) & +0.18 dB $\angle$$-$2.2$^\circ$ \\
$f_c$ (GHz) & 2.8945 & 2.8926 & 2.8943 \\
BW (MHz) & 172.5 & 170.2 & 171.2 \\
Peak IL (dB) & 2.04 & 2.39 & 2.38 \\
Best $S_{11}$ (dB) & $-$18.8 & $-$22.8 & $-$16.8 \\
Worst in-band $S_{11}$ (dB) & $-$4.6 & $-$4.5 & $-$5.3 \\
Mean $\Delta S_{21}$ vs.\ instrument (dB) & +0.17 & +0.14 & -- \\
Mean $|\Delta\Gamma|$ $S_{11}$ vs.\ instrument & 0.030 & 0.041 & -- \\
\hline
\end{tabular}
\end{table*}
```
<!-- END siw-table:tosm -->

Both corrections assume the same standard definitions, so their agreement
checks the implementation and the saved raw files, not the standards. The
offsets and the open's capacitance mostly move the reference plane, and the
test above bounds their effect on the magnitudes. The adapter itself shows
it: corrected with the 85033D/E definitions it has less than 1 ps of delay,
and with ideal standards $-64$ ps; the reference plane moves by about 32 ps per
port with the assumed definitions, while the magnitudes change by less than
0.09 dB. The load is different: a
general-purpose SMA load with a 25 dB return loss, which we did not measure,
would leave a directivity error of 0.056, comparable to the dips we want to
read. The check thru sets an empirical bound. After the instrument calibration
it returns +0.18 dB in $S_{21}$ and −18.4 dB in $S_{11}$ at worst over
2.6–3.2 GHz, and the software calibration applied to the raw thru gives
+0.26 dB and −17.6 dB. A passive thru cannot have gain, so both corrections are
optimistic in $S_{21}$, and we take its uncertainty as about 0.3 dB. Reflections
below about −18 dB are not resolved; the worst in-band $S_{11}$ is good to about
±2 dB.

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_calibration_check.png}
\caption{Soldered board: raw measurement, instrument calibration and
software calibration. The software result uses only the raw open, short,
match and thru files.}
\label{fig:calcheck}
\end{figure*}
```

## Comparison with simulation

Table \ref{tab:comparison} compares the specification, both simulators and the
four corrected measurements, all processed by the same code (`siw measure`).
Fig. \ref{fig:measvsim} shows the curves.

*How $f_c$ and the bandwidth are read.* One definition is used throughout the
paper and for every source. On each curve we take the maximum of $|S_{21}|$
and draw a line 3 dB below it. The two crossings of that line on either side of
the peak, linearly interpolated between sweep points, are the band edges $f_1$
and $f_2$. The bandwidth is $f_2 - f_1$, and the centre frequency is their
midpoint, $f_c = (f_1 + f_2)/2$, not the frequency of the maximum. With ripple
in the passband the maximum sits on one of the poles and can be well off
centre: in Palace the maximum is at 2.860 GHz and $f_c$ = 2.876 GHz; on the
soldered board the two coincide at 2.894 GHz. Only the crossings bounding the
contiguous region around the peak count, so a band split in two is not
reported as one wide band. Fig. \ref{fig:qzoom} shows the construction on the
curves.

<!-- BEGIN siw-table:comparison -->
```{=latex}
\begin{table*}[t]
\centering
\footnotesize
\setlength{\tabcolsep}{4pt}
\caption{Fabricated cascade N=3 filter: specification, simulation and measurement. Every column is processed with the same code: $f_c$ is the midpoint of the two crossings 3\,dB below the peak $S_{21}$, and the bandwidth their distance. In-band is $2.870\pm1.4\%$\,GHz (the specified 5\,\% band). CST is the pre-trim geometry. Palace in-band figures are for the fabricated geometry; its $S_{21}$ at 2.45/3.5\,GHz and spur are from the pre-trim 0--8\,GHz sweep. The spur is the largest $S_{21}$ between 3.6 and 5.0\,GHz. Measured columns: VNA = instrument calibration, SW = software recalibration of the raw files (Sec.~VIII); S = connectors soldered, U = unsoldered, C = calibrated. $Q_L$ and the effective $Q_u$ are defined in Sec.~IX. The specified bandwidth is the 0.1\,dB ripple bandwidth; the specification $Q_L$ is that of the ideal prototype at $-3$\,dB (199\,MHz), not $1/\mathrm{FBW} = 20$.}
\label{tab:comparison}
\begin{tabular}{lccccccc}
\hline
 & \textbf{Spec.} & \textbf{CST} & \textbf{Palace} & \textbf{VNA SC} & \textbf{VNA UC} & \textbf{SW S} & \textbf{SW U} \\
\hline
Centre frequency (GHz) & 2.870 & 2.878 & 2.876 & 2.894 & 2.898 & 2.895 & 2.898 \\
$-3$\,dB bandwidth (MHz) & 143.5 & 180 & 182 & 171 & 172 & 172 & 174 \\
Fractional bandwidth (\%) & 5.0 & 6.2 & 6.3 & 5.9 & 5.9 & 6.0 & 6.0 \\
Loaded $Q_L = f_c/\mathrm{BW}$ & 14.4 & 16.0 & 15.8 & 16.9 & 16.9 & 16.8 & 16.7 \\
Effective $Q_u$ (from IL) & -- & 173 & 179 & 138 & 136 & 159 & 155 \\
Peak $S_{21}$ (dB) & -- & $-$1.80 & $-$1.70 & $-$2.38 & $-$2.41 & $-$2.04 & $-$2.08 \\
Worst in-band $S_{21}$ (dB) & -- & $-$3.76 & $-$2.58 & $-$7.14 & $-$7.62 & $-$6.79 & $-$7.26 \\
Worst in-band $S_{11}$ (dB) & $\le -16$ & $-$6.9 & $-$11.1 & $-$5.3 & $-$4.8 & $-$4.6 & $-$4.1 \\
Worst in-band $S_{22}$ (dB) & -- & $-$6.9 & -- & $-$5.2 & $-$4.5 & $-$5.0 & $-$4.3 \\
Best $S_{11}$ (dB @ GHz) & -- & $-$17.3 @ 2.877 & $-$35.4 @ 2.850 & $-$16.8 @ 2.899 & $-$17.1 @ 2.884 & $-$18.8 @ 2.881 & $-$20.1 @ 2.873 \\
$S_{11}$ zeros $<-10$\,dB & -- & 1 & 3 & 1 & 1 & 1 & 1 \\
$S_{21}$ at 2.45\,GHz (dB) & -- & $-$60.7 & $-$60.9 & $-$45.6 & $-$45.8 & $-$44.9 & $-$45.0 \\
$S_{21}$ at 3.5\,GHz (dB) & -- & $-$39.3 & $-$39.5 & $-$43.3 & $-$43.5 & $-$41.6 & $-$42.3 \\
Strongest spur (dB @ GHz) & -- & $-$2.5 @ 4.63 & $-$3.8 @ 4.61 & $-$4.4 @ 4.68 & $-$4.2 @ 4.68 & $-$4.5 @ 4.68 & $-$4.4 @ 4.68 \\
\hline
\end{tabular}
\end{table*}
```
<!-- END siw-table:comparison -->

```{=latex}
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_measured_vs_sim.png}
\caption{Measured and simulated response. (a, b) The fabricated board
(instrument and software calibration, soldered and unsoldered) against Palace
and CST. (c) Wideband transmission: the spurious passbands at 4.4--4.9\,GHz
appear in the measurement at the simulated frequencies.}
\label{fig:measvsim}
\end{figure*}
```

*Centre frequency and bandwidth.* The measured band is centred at 2.894 GHz
(soldered) and 2.898 GHz (unsoldered), against 2.876 GHz in Palace and 2.870 GHz
in the specification. The +18 MHz (0.6 %) offset to the simulation corresponds
to an effective permittivity about 1.3 % below the 3.66 used for design. This
is well inside the spread between a laminate's design and process values. We
did not test this. The −3 dB bandwidth is 171–174 MHz, 4–6 % below Palace.

*Insertion loss.* The peak $S_{21}$ is −2.38 and −2.41 dB with the instrument
calibration and −2.04 and −2.08 dB with the software one. So the loss is
2.0–2.4 dB, within the 0.3 dB uncertainty above. Palace gives 1.70 dB. The
budget of Sec. VII expects 2.3 dB for smooth copper. The first version of the
budget, written before the measurement, gave 2.1–2.3 dB. The measurement is
therefore at or just below the expectation. The next subsection turns the loss
into a quality factor. A second route is the forward model of the fitted
coupling matrix. It can read the measured loss as an effective unloaded Q. We
kept the Palace-fitted couplings and varied only $Q_u$. The model gives 1.1 dB
and three reflection zeros at $Q_u$ = 270. It gives 1.7 dB and two zeros at
180, and 2.3 dB and one zero at 130 (Fig. \ref{fig:measvsim}b shows one). Read straight
off the model, the measured 2.0–2.4 dB means $Q_u$ of about 125–150. The matrix
has no launch. Palace shows 0.4 dB more than the matrix at $Q_u$ = 229, and
removing that gives 150–185. We do not separate copper roughness, via-fence
leakage, solder joints, the connector and the ENIG finish on the feed lines.

*Return loss.* The trace shows one broad minimum with a shoulder. It is
$-17$ dB at best with the instrument calibration ($-19$ to $-20$ dB with the
software one). The worst in-band $S_{11}$ is −5 dB. The three simulated zeros
are at −23 to −35 dB. This is below the −18 dB floor of the calibration check,
so the measurement cannot confirm them one by one. The matrix model says that
this much loss merges them into one. That is what the trace looks like. The
24 MHz offset from the specified band adds to the in-band figure. The ports
differ slightly: the best $S_{22}$ is −21 dB against −17 dB for $S_{11}$ on the
soldered board. This is within the calibration floor.

*Soldering.* Soldering the connectors changes the calibrated result by
3 MHz in centre frequency, 0.03 dB in insertion loss and 0.5 dB in worst
in-band $S_{11}$. At 2.9 GHz the contact of the seated connector is adequate.
The fork-slot fit discussed in Sec. VII did not become a problem.

*Out of band.* The first spurious passband appears at 4.68 GHz and −4.4 dB,
against 4.61 GHz and −3.8 dB in Palace and 4.63 GHz and −2.5 dB in CST. Above
the passband the measurement stays within a few dB of Palace. At 3.7 GHz it is
−45.6 dB against −44.2 dB. At 4.0 GHz it is −41.2 dB against −41.7 dB. At
3.5 GHz it is −43.0 dB against −39.5 dB. Below the passband the simulated
rejection keeps falling (−61 dB at 2.45 GHz, −92 dB at 2.0 GHz). The measured
rejection levels off at −44 to −48 dB between 2.2 and 2.5 GHz, and is −55 dB
at 2.0 GHz. This is well above the instrument floor (below −70 dB). It points
to coupling around the filter (open feed regions, cables) or leakage through
the via fence. The models do not contain these paths.

## Effect of the launch

Table \ref{tab:launch} adds the measured board to the launch simulations of
Sec. VII.

<!-- BEGIN siw-table:launch -->
```{=latex}
\begin{table}[t]
\centering
\scriptsize
\setlength{\tabcolsep}{2.5pt}
\caption{Effect of the launch on the same filter geometry. The first three rows are Palace simulations (the ports of the two connector-less variants sit on the planar line and normalise to its own impedance, so they show the filter behind an ideally matched feed). The last two rows are the fabricated board (instrument calibration). $S_{21}$ is the peak and $S_{11}$ the worst value in the specified band.}
\label{tab:launch}
\begin{tabular}{lcccc}
\hline
\textbf{Launch} & $f_c$ (GHz) & \textbf{BW (MHz)} & $S_{21}$ (dB) & $S_{11}$ (dB) \\
\hline
Microstrip, no conn. & 2.897 & 205 & $-$1.87 & $-$6.3 \\
CPWG, no conn. & 2.875 & 164 & $-$2.21 & $-$5.1 \\
CPWG + SMA, sim. & 2.876 & 182 & $-$1.70 & $-$11.1 \\
CPWG + SMA, sold. & 2.894 & 171 & $-$2.38 & $-$5.3 \\
CPWG + SMA, unsold. & 2.898 & 172 & $-$2.41 & $-$4.8 \\
\hline
\end{tabular}
\end{table}
```
<!-- END siw-table:launch -->

The simulations without a connector use ports that normalise to the planar
line. They cannot be compared in absolute terms with a measured board, which has
a connector and a real 50 Ω reference. They show that the connector's
reactance is part of the tuning. The measurement shows that the board with its
connector agrees with the connector simulation in centre frequency,
bandwidth and spurious bands, and not in return loss.

All figures in this section are regenerated from the files in
`measurements/2026-10-14_vna/` by `siw measure --paper`.

# Quality factor: loaded and unloaded Q {#sec:q}

```{=latex}
\begin{figure*}[!t]
\centering
\includegraphics[width=0.85\textwidth]{figures/fig_q_zoom.png}
\caption{Loaded Q read from $|S_{21}|$. The dotted line is 3\,dB below each
curve's peak and runs edge to edge; the arrow marks the bandwidth and the box
gives $Q_L = f_c/\mathrm{BW}$.}
\label{fig:qzoom}
\vspace{0.6em}
\includegraphics[width=0.72\textwidth]{figures/fig_q_comparison.png}
\caption{Quality factors of the four sources against theory (hatched bars).
(a) Loaded Q: the comparable value is the ideal prototype at $-3$\,dB (14.4),
not $1/\mathrm{FBW}$ (20, ripple band). (b) Effective $Q_u$ solved from the
insertion loss, against the dielectric limit (270) and dielectric plus smooth
copper (180).}
\label{fig:qcomp}
\end{figure*}
```

Two quality factors summarise the response. The **loaded Q** of the filter,
$Q_L = f_c/\mathrm{BW}_{-3\,\mathrm{dB}}$, says how narrow the passband is with
the ports attached. We read it straight off $|S_{21}|$: the dotted line in Fig.
\ref{fig:qzoom} sits 3 dB below each curve's peak, and its ends are the band
edges. The **unloaded Q** $Q_u$ measures each resonator's own loss and sets the
insertion loss (Eq. \ref{eq:il}). The two $Q$ rows of Table
\ref{tab:comparison} and Fig. \ref{fig:qcomp} come from the same code
(`siw measure`) for all four sources.

In the full filter the two play different roles:

- $Q_L$ is set by the couplings ($k$ and $Q_e$). It defines the bandwidth and
  barely depends on $Q_u$ as long as $Q_u \gg Q_L$.
- $Q_u$ does not change the bandwidth, but it sets the insertion loss.
  Writing Eq. \ref{eq:il} in terms of the loaded Q of the ripple band,
  $Q_{L,\text{ripple}} = 1/\mathrm{FBW}$,
  $$ \mathrm{IL}_0 \approx 4.343 \sum_i g_i \, \frac{Q_{L,\text{ripple}}}{Q_u}\ \text{dB}. $$
  The narrower the filter (higher $Q_L$) or the lossier each resonator
  (lower $Q_u$), the higher the loss.

*Theoretical loaded Q.* The specified 5 % is the 0.1 dB *ripple* bandwidth,
143.5 MHz, whose $Q$ is $1/\mathrm{FBW} = 20$. At $-3$ dB the ideal third-order
Chebyshev prototype is
$\cosh\!\big(\tfrac{1}{N}\operatorname{arccosh}\sqrt{(10^{0.3}-1)/(10^{0.01}-1)}\big)
= 1.39$ times wider: 199 MHz, or $Q_L = 14.4$. That is the value to compare
with, because every bandwidth in this paper is a $-3$ dB one. Palace gives
15.8, CST 16.0 and the board 16.9 (16.8 with the software calibration).
Against that reference the $-3$ dB band is not wider than designed but
9 % (Palace) to 14 % (board) narrower, consistent with the internal coupling
the matrix fit finds slightly below target ($k_{12} = 0.042$ in Palace and 0.044
on the board, against 0.046). Earlier comparisons against 143.5 MHz mix the
two bandwidth definitions.

*Effective $Q_u$.* We solve Eq. \ref{eq:il} for $Q_u$ with the measured peak
loss. The FBW in that equation is the ripple one, so the measured $-3$ dB FBW is
divided by 1.39. On the ideal lossy prototype the procedure returns 270 for
$Q_u = 270$ and 181 for 180. Because all loss (mismatch, launch, radiation,
connector) is charged to the resonators, the result is an *effective* $Q_u$,
a lower bound on the resonator's own. Palace gives 179 and CST 173. Both
simulations have perfectly conducting walls, whose ceiling is the dielectric,
$Q_d = 270$; the gap is the mismatch and launch terms of the loss budget
(Table \ref{tab:lossbudget}). The board gives 138 with the instrument
calibration and 159 with the software one, inside the 130–185 range the
coupling-matrix forward model gave in Sec. VIII. The board sits at
0.77–0.89 of Palace; that is what copper, the ENIG finish and the real
connector add, none of which the simulations contain. The smooth-copper
reference, $1/Q_u = 1/Q_d + 1/Q_c$ with $Q_c \approx 540$, gives 180 for the
resonator alone.

*A second estimate, from the group delay.* Eq. \ref{eq:il} needs the
$g$-values and the bandwidth. A second estimate needs neither. In the time
$\tau_0$ that a signal spends in the filter, the stored energy decays by the
factor $\exp(-\omega_0\tau_0/Q_u)$, which is $4.343\,\omega_0\tau_0/Q_u$ dB.
Setting this equal to the dissipated loss gives

```{=latex}
\begin{equation}
Q_u = \frac{4.343\,\omega_0\,\tau_0}{L_\mathrm{diss}},
\qquad
L_\mathrm{diss} = -10\log_{10}\frac{|S_{21}|^2}{1-|S_{11}|^2}.
\label{eq:qdelay}
\end{equation}
```

Here $\tau_0$ is the group delay of $S_{21}$ at the transmission peak (the
phase slope over a 10 MHz aperture), and $L_\mathrm{diss}$ is the power that
is neither reflected nor transmitted. On the ideal lossy prototype, Eq.
\ref{eq:qdelay} returns 270 for $Q_u = 270$ and 180 for 180. Eq. \ref{eq:il}
returns 277 and 187. Palace gives 222 and the board 156 (instrument
calibration) and 183 (software calibration), Fig. \ref{fig:qdelay}. The two
estimators charge the feed lines differently. Eq. \ref{eq:il} puts all the loss
on the resonators, so it is a lower bound on their $Q_u$. Eq. \ref{eq:qdelay}
also counts the delay of the feed lines and the launch as stored energy, so it
reads higher. For Palace, whose cavities have exactly $Q_u = 270$, they give
179 and 222. They agree on the main point: the board is 11 to 30 % below
Palace. Adding smooth copper in series to the Palace value gives
$1/(1/222 + 1/540) \approx 158$, which is where the board lies (156 to 183).

```{=latex}
\begin{figure*}[!t]
\centering
\includegraphics[width=0.78\textwidth]{figures/fig_q_delay.png}
\caption{Effective unloaded $Q$ from the group delay. (a) Group delay of
$S_{21}$ for Palace and the soldered board. (b) $Q_u$ from Eq. (\ref{eq:qdelay}).
The grey bar is the Palace value with smooth copper added in series.}
\label{fig:qdelay}
\end{figure*}
```

```{=latex}
\FloatBarrier
```

# Discussion: gaps and room to improve

**What was AI-driven, and what was not.** The agent wrote about 12 k lines
of design code. It launched and monitored the Palace eigenmode and driven
solves, read solver logs, and localized most of the defects in
Table \ref{tab:bugs}. It also produced the fabrication
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

Each was caught by a physics check, a solver error or a human question. This
argues for keeping those checks in the loop.

**Gaps.**

* One board and one measurement session: no spread across boards, and the
  S21 scale is uncertain by about 0.3 dB (Sec. VIII).
* The calibration standards were a generic SMA short, open and load, not a
  characterised kit. The calibrated thru returns −18 dB, so reflection zeros
  deeper than that are not resolved, and the worst in-band return loss is
  good to about ±2 dB.
* The specification is not met: the board measures −5 dB worst in-band return
  loss against −16 dB (simulated: −11.1 dB), and 171 MHz bandwidth against
  143.5 MHz.
* S11 varied by about 5 dB across mesh and port models, while fc, bandwidth
  and IL moved by less than 10 MHz and 0.3 dB. The measurement then differed
  from Palace by +18 MHz in fc, 0.3–0.7 dB in IL and 6 dB in S11, so the
  model uncertainty was not conservative.
* Qe is calibrated with a dielectric-only Qu and is slightly over-estimated.
* Conductor loss is modelled only on exterior faces. Thin fabrication layers
  (mask, ENIG) could not be resolved.
* Spurious passbands start at 4.4 GHz (−4 dB, confirmed by the measurement) and
  need a low-pass filter in a real system.
* The measured loss is not apportioned between copper roughness, via-fence
  leakage, solder joints, connector and ENIG on the feed lines. The low-side
  rejection floor of about −46 dB (simulated: −61 dB) points to coupling around
  the filter that no model contains.
* There is no controlled comparison against an engineer working without the
  agent, and no accounting of cost. The session logs give tokens and active
  time (Table \ref{tab:models}) but not the engineer's own time.
* This is a single case study: one engineer, one model family, one filter
  topology. It shows what can happen, not how often.
* The taxonomy is self-reported by the same engineer–agent pair that made the
  mistakes. Git corroborates that each fix happened, but not the
  classification. It also lists only caught defects. The physics checks may
  still miss a comparable class of error.
* The code has no regression test suite. Its safety net is the physics
  sanity checks and the automated fabrication checks.

**Improvements.**

* A coordinated local correction of $w_{\text{ext}}$, $l_{\text{cav1}}$ and
  $w_{\text{iris}}$, driven by the coupling-matrix fit, and a re-centring of the
  band. The +24 MHz offset from 2.870 GHz is of the order of 0.5–1 mm of cavity
  length. The sensitivity is 27 MHz/mm measured at the end cavities, and about
  46 MHz/mm for the ideal cavity.
* Fitting the coupling matrix to the measurement needs a model of the launch.
  With the plain matrix the fit is ill-conditioned ($Q_u$ between 57 and 85 for
  two nearly identical curves), so we read the loss through the forward model.
* Adaptive frequency sweeps and y-symmetric half-models, for about half the
  memory and 5–10× fewer solves, which would bring the cascade within GPU limits.
* A GPU with more memory.
* A lower-loss or thicker laminate.
* Space-mapping or surrogate models [@bandler2004space] trained on the
  calibration data.
* Repeating the measurement with a characterised SMA calibration kit, or with
  on-board thru-reflect-line standards, to resolve the zeros.
* Making the physics sanity checks a mandatory step of the agent loop rather
  than a habit.

# The human part: how the text was written and what it means

## How this text was written

The paper was written in a conversation, in many short rounds, and the engineer
was never a passive reader. Each round had the same shape. The engineer asked
for something or objected to something. The agent drafted or revised. Sub-agents
that start without the conversation then reviewed the result and listed errors,
and the engineer decided which findings to accept. Tables and figures of
measured results are regenerated by `siw measure --paper`, so the numbers in the
text can always be checked against code. Table \ref{tab:prompts} lists some of
the engineer's prompts. They are paraphrased and corrected for grammar, so they
show the process and are not literal quotes.

```{=latex}
\begin{table*}[t]
\centering
\footnotesize
\caption{Examples of the engineer's prompts (paraphrased) and what each one changed.}
\label{tab:prompts}
\begin{tabular}{p{0.7cm}p{7.8cm}p{7.4cm}}
\hline
\textbf{\#} & \textbf{Prompt (paraphrased)} & \textbf{What changed} \\
\hline
1 & ``Reorganize the information we have, remove what is irrelevant, and write a paper called \emph{AI-Driven RF Design}.'' & Repository cleanup (deleted files stay in git tags) and the first full draft. \\
2 & ``Say that we started with openEMS and why it did not work for us, then moved to Palace. Mention the GPU with remote control, and the Python scripts for the optimization. We ended up running on the CPU. Recognize the gaps, and reference every paper we used.'' & Phase 1 and 2 sections, the compute paragraph, the gaps list and the bibliography. \\
3 & ``I would prefer a venue that is not very restrictive in peer review. I do not mind if it is rejected. Check that LLM-written papers are accepted.'' & The arXiv and IEEE Access build targets, and a plain statement of LLM authorship. \\
4 & ``Run several reviewers on the paper, and analyze extremely carefully whether it is safe to make the repository public.'' & Corrections to claims in the text, and an audit of the git history and metadata before release. \\
5 & ``The calibration kit was not a vendor kit. It was a generic SMA short, open and load.'' & Text, README and code documentation corrected, and the $-18$ dB floor caveat added. \\
6 & ``Explain how the pipeline works: the equations that are needed, the traditional steps, and how the tool solves each one. Explain the optimizer too, since we wrote it around Palace. If needed, show the equations as display equations.'' & Table \ref{tab:pipeline}, the optimizer paragraph and the display equations. \\
7 & ``Should we add today's commits? The paper is old. Some passages are hard to read, so simplify the wording. I do not know if simple technical English is acceptable in a paper, but I want it easy to follow.'' & Updated history statistics and timeline, and a plain-language editing pass. \\
8 & ``Is it easy to get the $Q$ of the filter from the plots? Is the insertion loss an expected number? We got 1.7 dB in the simulation. Show how the real length and the copper change it, with an easy calculation.'' & Sec. VII loss budget and Sec. IX. \\
9 & ``I do not understand why we need $Q_u$ or what it represents. Can we get it from Palace instead of CST?'' & A plain explanation of $Q_u$, and the raw Palace run stored with its phase, so that the Palace value could be computed. \\
\hline
\end{tabular}
\end{table*}
```

The agent also made mistakes in the text itself. It described the calibration
standards as a vendor kit when they were a generic SMA kit (prompt 5). It
wrote that the out-of-band rejection was a flat 45 dB, which is wrong: it is
44--48 dB between 2.2 and 2.5 GHz, where the simulation gives 61 dB. The
second error was found in review. Both were corrected before release. This
agrees with the failure modes of Sec. X: the agent is confident, and the
checks have to come from outside.

## What the engineer did that the agent did not

The physics that finally worked is classical, and most of the software was the
agent's. It is still worth listing what the agent did not do, because a reader
would otherwise credit it to the agent.

* *The idea of a coplanar-waveguide (CPWG) feed.* It came from a class that the
  author attended, not from the agent.
* *The physical work.* The SMA connector did not fit the board until the
  author filed the copper under its legs with a nail file (Sec. VII). No
  simulation could do that.
* *The measurement.* The author made sure that the VNA was used calibrated, and
  that the calibration was checked with a thru.
* *Reading.* The author checked the papers, the references and whether the
  equations looked right. Most of this was needed in the prototype period.
  After that the process went smoothly.
* *Free range.* The author also let the agent try other geometries that use
  other propagation modes. It was a blind search: without a physical idea of
  why a mode should help, the agent only explored (Sec. VI).

The simulation and optimization loop was the opposite. It is raw computation.
It was easy to implement and to improve with the idea of an agentic loop: the
agent runs a solve, reads the result, changes the model and runs again, and no
human has to be in that loop.

## Reflections and concerns

These are the author's views, offered with the evidence of one project.

**Knowledge is no longer the scarce thing.** The author's view is that AI has
solved the problem of scarce knowledge. It reduces the time, and if it is
guided correctly it does a better job than the author would have done alone.
The coupled-resonator theory, the solver input format and the fabrication file
formats were all things the agent knew or found in minutes. What it did not do
was choose the problem, bring an idea from outside the text, or touch the board.

**What is scarce now is money and the willingness to try new things.** A
simulation costs nothing but time, so the agent could try as many as it liked.
The board cost about USD 120 and gave one measurement, and it was the only
physical iteration of the project. The loop that the agent can run alone stops
where the physical world begins. The second shortage is willingness: the
agent tries whatever it is pointed at, and deciding to point it at an
unfamiliar solver, a new topology or a new kind of board is still a human choice.

**The gap between doing and knowing.** What one can do with an agent grows
faster than what one understands. In this project the gap was real. A working
filter exists whose code the author did not write line by line, and Table
\ref{tab:bugs} shows that the numbers can look right and be wrong. The defence
was to check the result against physics, which is knowledge, not production.

**Where the value goes.** If production becomes instant, the value does not
disappear. It moves to judgment and taste: choosing which thing to do, and
seeing when the answer is wrong. In this project that meant the specification,
the topology, the stopping decision and the doubts that a confident
explanation did not remove.

**Accountability.** The agent does not want anything and is not answerable for
its results. The author is, and says so in the acknowledgment [@ieee_ai_policy].

# Conclusion

An LLM coding agent took an SIW bandpass filter from specification to
fabrication files, with one engineer supervising. The board was then
manufactured and measured. Two things decided the design outcome. The first was
to replace black-box search over a discontinuous objective with calibration of
smooth observables on small structures. The second was to catch a long series
of silent defects with physics checks. The measurement confirms the
simulations where the physics is simple. The spurious bands fall at the
predicted frequencies, and the centre frequency is within 1 % of the
specification. The measurement also shows what the simulations did not
capture: 0.3 to 0.7 dB more loss than Palace. This is about the 0.6 dB of
copper loss that the perfect-conductor walls leave out (Sec. VII). In the
matrix model this loss merges the three reflection zeros into one. So the
worst in-band return loss is 5 dB, not the simulated 11 dB and not the
specified 16 dB. The generic calibration standards limit the reading of the
zeros themselves (floor about −18 dB), not the 5 dB. The independent software
recalibration agrees with the instrument's on average within 0.2 dB in
$S_{21}$ (up to 1 dB on the steep band edges). So this conclusion does not rest
on one calibration. The code, data and scripts that produced every number are
in the repository. `siw measure` reproduces the measured columns of
Table \ref{tab:comparison}. The agent made the computation cheap. The idea of
the feed, the connector, the calibration and the decisions on what to trust
stayed with the engineer (Sec. XI).

# Acknowledgment {-}

The design software, simulations, figures and a first draft of this text
were produced with Claude Code (Anthropic) under the author's direction. The
models were Claude Sonnet 5 and 5.5, Opus 5 and 5.5, and Fable 5. Sec. III
describes this work. The author reviewed all results and text and takes full responsibility for them
[@ieee_ai_policy]. The complete history and data are available in the
project repository.

```{=latex}
\FloatBarrier
```

# References {-}

::: {#refs}
:::
