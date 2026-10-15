# SIW Bandpass Filter — 2.87 GHz, designed with an LLM coding agent

Companion repository of the paper *AI-Driven RF Design: An LLM Coding Agent
Takes a Substrate Integrated Waveguide Filter from Specification to
Fabrication* ([`docs/paper/ai_driven_rf_design.md`](docs/paper/ai_driven_rf_design.md),
[PDF](docs/paper/ai_driven_rf_design.pdf)). It holds the code, the data and the
history behind every number in the paper, so the workflow can be inspected.

The filter is a 3-cavity substrate integrated waveguide (SIW) bandpass filter
on Rogers RO4350B. An LLM coding agent (Claude Code) wrote and operated the
design tool under one engineer's direction; the board was made by JLCPCB
(RO4350B, ENIG, about USD 120) and measured on a VNA.

## Where the evidence is

| What the paper claims | Where to look |
|---|---|
| The agent did the work, in sessions, over about 16 weeks | `git log`: 200+ commits, `Co-Authored-By` trailers, and the `fix:` commits behind the bug taxonomy |
| The agent kept a project memory and handed state between sessions | [`CLAUDE.md`](CLAUDE.md) and, in the tag `docs-archive-2026-09-29`, the handoff notes, roadmaps and plans (`git show docs-archive-2026-09-29:docs/archive/HANDOFF.md`) |
| One command-line tool covers the whole chain | [`src/siwfilter/`](src/siwfilter/) and `siw --list` (Table I of the paper) |
| Results are reproducible and curated | [`golden/`](golden/): parameters, S-parameters and the command that reproduces each design |
| Calibrate-and-invert replaces black-box search | `siw calibrate`, `siw synth-design`; data in [`docs/paper/data/`](docs/paper/data/) |
| Silent defects were found and fixed | commit messages (`git log --grep '^fix'`), [`CLAUDE.md`](CLAUDE.md) section 7 |
| The board was fabricated and checked | [`docs/final_check/`](docs/final_check/): verdict, fab package and 34 file checks |
| The board was measured, and recalibrated independently | [`measurements/2026-10-14_vna/`](measurements/2026-10-14_vna/), `siw measure` |
| CST cross-check, launch study | [`docs/cst_guide/`](docs/cst_guide/), [`docs/launch_comparison/`](docs/launch_comparison/), [`docs/audit_cst_palace/`](docs/audit_cst_palace/) |

A Spanish project report for a university course covers the same design as a
chronological narrative:
[`docs/paper/Informe_Filtro_SIW_287GHz.md`](docs/paper/Informe_Filtro_SIW_287GHz.md).

## Result in one table

|                          | Target    | Simulated (Palace) | Measured (VNA, soldered) |
|--------------------------|-----------|--------------------|--------------------------|
| Centre frequency         | 2.87 GHz  | 2.876 GHz          | 2.894 GHz                |
| −3 dB bandwidth          | 143.5 MHz | 182 MHz            | 171 MHz                  |
| Peak insertion loss      | —         | 1.7 dB             | 2.0–2.4 dB               |
| Worst in-band S11        | −16 dB    | −11.1 dB           | −5 dB (best min. −17 dB*) |
| First spurious passband  | —         | 4.61 GHz, −3.8 dB  | 4.68 GHz, −4.4 dB        |

The specification is not met. The measured range is the instrument calibration
(2.4 dB) and an independent software recalibration of the raw data (2.0 dB).
\*The calibration standards were a generic SMA short/open/load, so reflections
below about −18 dB are not resolved. Board size is 165.8 × 45.8 mm.

## Quick start

```bash
uv sync      # install
siw          # fast pipeline: synthesis → geometry → layout → CST macro → measurement check
siw --list   # every stage and subcommand
siw measure  # recalibrate the VNA data and compare with the simulations
```

The EM simulations need [Palace](https://awslabs.github.io/palace/), found
through `$PALACE_BIN`, your `$PATH`, or `~/opt/palace/bin/palace`. The
fabricated design is rebuilt with:

```bash
P=l_cav1=33.939,l_cav2=35.503,w_iris=14.416,w_ext=13.96,l_taper=15.738,w_ms=1.6636
siw kicad --topology cascade --N 3 --params $P --launch cpwg   # gerbers, drill, STEP → output/kicad/
siw cst   --topology cascade --N 3 --params $P --launch cpwg   # CST macro → output/bas/
```

A new filter is designed with `siw calibrate --what both --N 3` followed by
`siw synth-design --N 3`; `siw --help` lists the rest.

## License and citation

The code is released under the MIT licence ([`LICENSE`](LICENSE)); use it, change
it and redistribute it, keeping the copyright notice. `docs/paper/ieee-jestpe.csl`
keeps its own licence (CC BY-SA 3.0).

If you use the code, the data or the workflow, please cite the paper. GitHub's
"Cite this repository" button reads [`CITATION.cff`](CITATION.cff); the BibTeX is:

```bibtex
@misc{borello2026aidrivenrf,
  author       = {Borello, Federico},
  title        = {{AI-Driven RF Design}: An {LLM} Coding Agent Takes a Substrate
                  Integrated Waveguide Filter from Specification to Fabrication},
  year         = {2026},
  howpublished = {Preprint; code and data at
                  \url{https://github.com/fborello-lambda/siw_filter}},
  note         = {Replace with the arXiv identifier or journal reference when available}
}
```

## Notes

* The connector is part of the tuning: removing it costs about 5 dB of return
  loss ([`docs/launch_comparison/`](docs/launch_comparison/)).
* Substrate Rogers RO4350B 0.76 mm (εr 3.66), vias 1.5 mm at 3.0 mm pitch,
  Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA (the vendor datasheet is not
  redistributed here).
* `docs/paper/submission/build.py` builds the arXiv and IEEE Access sources
  from the Markdown paper; generated PDFs and archives are not committed.
* Files removed from the working tree during cleanups stay in git history and in
  the tags `docs-archive-2026-09-29` and `archive-2026-10-15`.
