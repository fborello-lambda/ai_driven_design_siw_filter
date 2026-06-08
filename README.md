# SIW Bandpass Filter

Parametric design, simulation, and CST export of a **Substrate Integrated
Waveguide (SIW) bandpass filter**.

- **Topology:** inline inductive-iris coupled SIW cavities (each cavity resonates
  in TE101), Chebyshev response, configurable order *N* and ripple.
- **Default spec:** f0 = 2.87 GHz (S-band), N = 3, FBW = 5 %, ripple = 0.1 dB,
  substrate **AD250C** (εr = 2.50, tanδ = 0.0013, h = 1.524 mm), via Ø 0.8 mm,
  pitch 1.5 mm.
- **Final deliverable:** a native, parametric 3D solid model for **CST Studio
  Suite 2021**, generated from a Python-written `.bas` VBA macro. openEMS is used
  as a fast FDTD pre-check.

See [`CLAUDE.md`](CLAUDE.md) for the full project brief, design-equation
cookbook, and references.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) (project is in uv project mode)
- Python 3.12
- The **openEMS C++ core** built and installed at `/home/fd/opt/openEMS`
  (needed only for the EM simulation / calibration modules, not the synthesis).

## Setup

The Python deps and the CSXCAD/openEMS bindings are installed into the project
venv. If starting from a fresh clone:

```bash
uv sync                       # PyPI deps (numpy, scipy, scikit-rf, matplotlib, ...)

# openEMS/CSXCAD Python bindings (build against the pre-built C++ core)
export CSXCAD_INSTALL_PATH=/home/fd/opt/openEMS
export OPENEMS_INSTALL_PATH=/home/fd/opt/openEMS
uv add /home/fd/openEMS-Project/CSXCAD/python
uv add /home/fd/openEMS-Project/openEMS/python
```

The native `.so` libraries must be on the runtime library path for any module
that touches openEMS:

```bash
export LD_LIBRARY_PATH=$HOME/opt/openEMS/lib:$LD_LIBRARY_PATH
```

(This line is persisted in `~/.zshrc` / `~/.bashrc`, so new terminals get it
automatically.) Verify the bindings import:

```bash
uv run python -c "from CSXCAD import ContinuousStructure; from openEMS import openEMS; print('openEMS OK')"
```

## Usage

Run any module with `uv run python <module>.py` from the project root. The
synthesis and layout modules are **pure Python** and need no `LD_LIBRARY_PATH`.

```bash
uv run python config.py        # show resolved spec + substrate, kappa(f0)
uv run python synthesis.py     # Chebyshev g/k/Qe -> target.s2p + target_response.png
uv run python siw_geometry.py  # physical SIW dimensions + design-rule checks
uv run python layout_plot.py   # top-view drawing -> layout.png + via_coords.csv
```

### Outputs

| File | Produced by | Description |
|------|-------------|-------------|
| `target.s2p`          | `synthesis.py`   | Ideal target S-params (Touchstone; importable into CST) |
| `target_response.png` | `synthesis.py`   | Ideal \|S11\|/\|S21\| vs frequency |
| `layout.png`          | `layout_plot.py` | 2D top-view of the geometry |
| `via_coords.csv`      | `layout_plot.py` | All via centres (mm) |

## Configuration

All tunable numbers live in **`config.py`** — it is the single source of truth.
Edit `FilterSpec` (f0, FBW, N, ripple, d_via, p_via) or pick another preset from
the `SUBSTRATES` dict (set `DEFAULT_SUBSTRATE`). Available stock:

| Preset | εr | tanδ | h |
|--------|-----|------|---|
| `RO4350B_1.52mm` | 3.66 | 0.0037 | 1.52 mm |
| `RO4350B_0.76mm` | 3.66 | 0.0037 | 0.76 mm |
| `RO4350B_0.25mm` | 3.66 | 0.0037 | 0.25 mm |
| `RO4350B_0.10mm` | 3.36 | 0.0037 | 0.10 mm |
| `AD250C_1.524mm` *(default)* | 2.50 | 0.0013 | 1.524 mm |

Dielectric loss for openEMS/CST is set from `tanδ` via
`kappa = 2·π·f0·ε0·εr·tanδ` (`Substrate.kappa()`).

## Module overview

| Module | Status | Purpose |
|--------|--------|---------|
| `config.py`       | ✅ | Spec dataclasses + substrate presets (single source of truth) |
| `synthesis.py`    | ✅ | Chebyshev g-values, coupling matrix, target S-params |
| `siw_geometry.py` | ✅ | Filter spec → physical SIW dimensions (analytical first pass) |
| `layout_plot.py`  | ✅ | 2D top-view drawing + via-coordinate CSV |
| `calibrate.py`    | ⬜ | EM iris-width↔k and Qe↔taper sweeps (authoritative coupling) |
| `openems_sim.py`  | ⬜ | Build 3D model in CSXCAD, run FDTD, extract S-params |
| `cst_export.py`   | ⬜ | Generate parametric `siw_filter.bas` VBA macro (primary deliverable) |
| `compare.py`      | ⬜ | Overlay target vs openEMS (vs CST) responses |

> **Note on iris widths:** the values in `siw_geometry.py` / `layout.png` come
> from an analytical **placeholder** map and are *not* trustworthy. The
> authoritative iris widths and taper (external Q) come from the EM calibration
> in `calibrate.py` (see `CLAUDE.md` §6). This is the #1 source of first-design
> failure for SIW filters.
