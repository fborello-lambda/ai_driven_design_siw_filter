---
title: "Publishing 'AI-Driven Design for SIW Filters'"
subtitle: "Venue landscape, AI-disclosure requirements, and a recommendation"
date: "2026-09-04"
lang: en
geometry: margin=2.5cm
papersize: a4
fontsize: 11pt
colorlinks: true
toc: true
toc-depth: 2
---

\newpage

# What this paper actually is

Two different papers could be written from this project, and they point at
different venues:

1. **An SIW filter synthesis paper.** Chebyshev coupling-matrix synthesis,
   calibrate-and-invert (measure k/Qe on a small closed structure, invert
   the textbook mapping, assemble and confirm), applied to a dual-mode and
   an inline-cascade SIW cavity filter, with a fabricated board. This is a
   normal RF/microwave paper that happens to have been designed with heavy
   AI assistance.
2. **An agentic-design-automation paper.** An LLM coding agent drove an
   open-source FEM solver (Palace) through a design loop end to end —
   wrote the meshing/optimization code, ran the EM solves, generated the
   fabrication outputs, and in the process produced a documented taxonomy
   of **fifteen-plus silent modelling bugs**, none of which raised an
   error. The filter is the case study; the finding is about the process.

These have different homes. Framing (1) fits classic RF/microwave venues.
Framing (2) fits the newer, smaller world of venues explicitly about
agentic AI and LLM-driven engineering — and that world does **not**
currently include the RF/microwave-specific journals, whose "AI for
microwave filters" scope almost always means *trained ML surrogate
models* (neural networks predicting S-parameters or synthesizing
geometry), not an LLM agent writing and iterating the design code itself.
Picking the wrong framing for a venue is the single biggest fit risk here.

\newpage

# Do these venues even accept AI-assisted work?

Yes — every venue considered below permits it. None forbid AI assistance;
all require **disclosure**, not permission-seeking, and none allow an AI
system to be listed as an author.

| Publisher | Authorship | Disclosure required | Where |
|---|---|---|---|
| **IEEE** (LAD, IMS, IMFW, JSTEAP) | AI cannot be an author | Yes, in Acknowledgments: name the tool, name the sections, briefly explain how it was used. Grammar/editing-only use is exempt. | [IEEE generative-AI policy](https://casrai.org/dictionary/term/ieee-generative-ai-policy), [IEEE RAS guidelines](https://www.ieee-ras.org/publications/guidelines-for-generative-ai-usage/) |
| **Wiley** (IJRFMiCAE) | AI cannot be an author | Yes, full disclosure in a dedicated appendix; author takes full responsibility for the content. | [Wiley generative-AI author guidelines](https://onlinelibrary.wiley.com/pb-assets/assets/15405885/Generative%20AI%20Policy_September%202023-1695231878293.pdf) |
| **MDPI** (Electronics) | AI cannot be an author | Yes, disclosure statement in Acknowledgments naming the tool, plus a Materials-and-Methods description of specifically how it was used. A vague "ChatGPT improved this manuscript" does not meet their standard. | [MDPI generative-AI authorship policy](https://casrai.org/guides/mdpi-generative-ai-authorship-policy) |

Separately and unconditionally: using AI to fabricate or manipulate data,
figures, or results is a research-integrity violation, independent of the
disclosure question. Nothing here is at risk on that front — every number
in this project traces to a real Palace solve or a real gerber/drill file,
and the whole point of the bug taxonomy is that errors were *found and
fixed*, not hidden.

**Practical takeaway for this specific paper**: because the paper's
subject is AI-driven design, the disclosure isn't a compliance footnote —
it's the paper's own methods section. Be specific about what the agent did
(wrote the meshing/optimization/export code, ran the EM solves, found and
fixed the bugs described in the results, drafted portions of the text)
rather than a blanket statement. That specificity is exactly what MDPI and
IEEE both say separates an adequate disclosure from an inadequate one.

\newpage

# Venue options, by framing

## Framing 1 — RF/microwave synthesis paper

| Venue | Type | Fit | Deadline (from today, 2026-09-04) |
|---|---|---|---|
| **Int'l J. of RF and Microwave CAE** (Wiley) | Journal, rolling | Exactly on-topic (CAD/EDA for RF/microwave); no deadline pressure | rolling |
| **MDPI Electronics** | Journal, rolling, open access | Broad enough, has run ML-for-microwave-filter themes before | rolling |
| **IEEE MTT-S IMS 2027** (San Antonio, May 2027) | Flagship conference | Best prestige match; this cycle explicitly expanded scope for AI/ML-driven RF design | **Jan 6, 2027** — reachable |
| **IEEE JSTEAP** "AI for EM/Antennas/Microwave Circuits" special issue | Journal special issue | Ideal scope on paper | this cycle's deadline (Dec 15, 2025) already passed; watch for the next call |
| **IEEE MTT-S IMFW** (Filter Workshop, 3-page format) | Workshop | Filter-specific audience, short-paper format suits a methods/negative-result piece | this cycle's (Oct 1, 2025) passed; annual, next around Oct 2026 for IMFW 2027 |
| **EuMC / EuMW** (London, Oct 2026) | Flagship conference | Good fit | this cycle's deadline (Mar 27, 2026) already passed |

## Framing 2 — agentic-AI / LLM-driven design-automation paper

| Venue | Type | Fit | Deadline (from today) |
|---|---|---|---|
| **IEEE LAD** ("LLM-Aided Design", `iclad.ai`, IEEE CEDA) | Conference, IEEEXplore | **Best topical match found.** LAD 2026's own stated theme was "agentic optimization and scaling inference-time methods" — a near-exact description of the calibrate-and-invert + local-GP loop this project ran. | LAD 2026 already ran (deadline Mar 2, 2026; conference Jul 30–31, 2026, Stanford). **LAD 2027 not yet posted** — watch `iclad.ai`; historical pattern suggests a spring 2027 deadline. |
| **arXiv** (`eess.SY` or `cs.AI`) | Preprint, no review | Where the closest comparable paper currently lives (see below) | immediate, no deadline |
| **IEEE Access** | Journal, rolling, open access | Broad enough to accept an agentic-AI-methods paper even without a novel trained model; fast review | rolling |
| **IEEE CAI** ("Agents for Science and Engineering" session) | Conference special session | Direct topical fit | CAI 2026 already ran (May 2026, Granada); watch for CAI 2027 |

**A directly comparable prior work**: [*From Prompt to Prototype: Towards a
Frontier LLM Driven RF Engineering Workflow*](https://arxiv.org/abs/2608.31006)
(arXiv:2608.31006, Aug 2026) — an LLM agent operating CST Studio Suite,
Keysight ADS, and KiCad via their scripting interfaces to design a
GNSS antenna system (patch, SAW prefilter, two-stage LNA) end to end in
about two hours. Same category of contribution as this project's, currently
only on arXiv with no venue attached — a sign this specific niche
(agentic LLM + real EM/CAD tools, not a trained surrogate) does not yet
have a single settled home. Worth citing as related work either way.

\newpage

# Recommendation

If the point of the paper is genuinely "an AI coding agent drove an
open-source solver through a design loop and the process itself is the
finding" (framing 2 — the approach actually followed: Palace, not CST, as
the solver of record; AI writing and iterating code, not a trained
surrogate model):

1. **Post to arXiv now.** Establishes priority immediately, costs nothing,
   and is where the one directly comparable paper already lives.
2. **Target IEEE LAD 2027** when its CFP opens (watch `iclad.ai`). This is
   the venue whose own stated interests (agentic optimization,
   inference-time scaling, LLM-driven design tools) match the actual
   contribution most closely of everything found.
3. **IEEE Access** is the fastest realistic peer-reviewed option if IEEE
   credit is wanted sooner than LAD 2027's cycle allows — it doesn't
   require a novel ML model, just a real methods contribution, which this
   has (the bug taxonomy, the calibrate-and-invert method, the fabricated
   result).

If instead the paper should foreground the filter-synthesis contribution
and the fabricated result, with the AI-driven process as a secondary
disclosure rather than the headline: **IJRFMiCAE or MDPI Electronics**
now (rolling, no deadline pressure), with **IMS 2027** (Jan 6, 2027) as a
stretch target for the flagship conference. Nothing prevents submitting
both a framing-2 preprint/LAD paper and a framing-1 journal paper from the
same underlying work, provided each stands on its own contribution and
neither double-publishes the same claims as new.

\newpage

# Sources

- [IEEE generative-AI author-disclosure policy](https://casrai.org/dictionary/term/ieee-generative-ai-policy)
- [IEEE RAS guidelines for generative AI usage](https://www.ieee-ras.org/publications/guidelines-for-generative-ai-usage/)
- [MDPI's generative-AI authorship policy](https://casrai.org/guides/mdpi-generative-ai-authorship-policy)
- [Wiley generative-AI guidelines for authors (PDF)](https://onlinelibrary.wiley.com/pb-assets/assets/15405885/Generative%20AI%20Policy_September%202023-1695231878293.pdf)
- [IEEE LAD 2026 call for papers](https://www.sigarch.org/call-contributions/2nd-ieee-international-conference-on-llm-aided-design-lad-2026/)
- [ICLAD / LAD conference series](https://iclad.ai/)
- [From Prompt to Prototype (arXiv:2608.31006)](https://arxiv.org/abs/2608.31006)
- [IEEE MTT-S IMS 2027 call for papers](https://ims-ieee.org/sites/ims/files/ims2027-call-for-papers_30july2026.pdf)
- [IMFW 2026 call for papers](https://www.microwavejournal.com/articles/44233-imfw-2026-call-for-papers)
- [EuMW 2026 call for papers](https://www.eumw.eu/wp-content/uploads/2026/02/4997_eumw2026_call_for_papers-07.pdf)
- [IEEE JSTEAP AI special issue call](https://ieeeaps.org/call-for-papers-ai-for-electromagnetics-antennas-propagation-communication-channels-and-microwave-circuits)
- [International Journal of RF and Microwave CAE (Wiley)](https://onlinelibrary.wiley.com/journal/ijmce)
- [IEEE CAI 2026](https://ieeecai2026.org/)

## Building this document

```bash
cd docs/paper && pandoc --pdf-engine=xelatex PUBLICATION_VENUES.md -o PUBLICATION_VENUES.pdf
```
