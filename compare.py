"""Overlay CST simulation results vs the synthesis target.

Reads `S ParametersV1.txt` (CST tabular export, two blocks: S11 then S21,
magnitude in linear scale) and `target.s2p` (scikit-rf Touchstone),
plots |S11| and |S21| in dB on the same axes, and prints key metrics.

Usage:  uv run python compare.py [--cst PATH] [--target PATH]
"""

from __future__ import annotations

import argparse
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import skrf

PROJ = os.path.dirname(os.path.abspath(__file__))


def _parse_cst_txt(path: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Parse CST tabular S-parameter export (GHz, values already in dB).

    Returns {'S11': (freq_hz, db), 'S21': (freq_hz, db)}.
    """
    blocks: dict[str, tuple[list, list]] = {}
    key = None
    freqs: list[float] = []
    vals: list[float] = []

    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            m = re.search(r'S(\d+),(\d+)', line)
            if m and line.startswith('#'):
                if key and freqs:
                    blocks[key] = (np.array(freqs) * 1e9, np.array(vals))
                key = f"S{m.group(1)}{m.group(2)}"
                freqs, vals = [], []
                continue
            if key and not line.startswith('#'):
                parts = line.split()
                if len(parts) == 2:
                    try:
                        freqs.append(float(parts[0]))
                        vals.append(float(parts[1]))
                    except ValueError:
                        pass
    if key and freqs:
        blocks[key] = (np.array(freqs) * 1e9, np.array(vals))
    return blocks


def _to_db(mag_lin: np.ndarray) -> np.ndarray:
    """Convert linear magnitude to dB (used for target.s2p only)."""
    return 20.0 * np.log10(np.clip(np.abs(mag_lin), 1e-12, None))


def compare(cst_path: str, target_path: str, out: str = "compare.png") -> None:
    # ---- load CST results -----------------------------------------------
    cst = _parse_cst_txt(cst_path)
    if not cst:
        raise ValueError(f"Could not parse any S-parameter blocks from {cst_path!r}")

    # ---- load synthesis target ------------------------------------------
    tgt = skrf.Network(target_path)
    f_tgt = tgt.f

    # ---- plot -----------------------------------------------------------
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    colors = {"cst": "#1f77b4", "target": "#d62728"}

    pairs = [("S11", 0), ("S21", 1)]
    for param, idx in pairs:
        ax = axes[idx]
        # CST (values already in dB)
        if param in cst:
            f, db = cst[param]
            ax.plot(f / 1e9, db, color=colors["cst"],
                    lw=1.5, label=f"CST {param}")
        # Target
        tgt_mag = np.abs(tgt.s[:, idx, 0] if idx == 0 else tgt.s[:, 1, 0])
        ax.plot(f_tgt / 1e9, _to_db(tgt_mag), color=colors["target"],
                lw=1.2, ls="--", label=f"Target {param}")

        ax.set_ylabel(f"|{param}| [dB]")
        ax.set_ylim(-60, 5)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)

    axes[-1].set_xlabel("Frequency [GHz]")
    axes[0].set_title("SIW BPF — CST simulation vs synthesis target", fontsize=11)

    # mark passband edges on both
    from config import SPEC
    for ax in axes:
        ax.axvline(SPEC.f1 / 1e9, color="0.5", ls=":", lw=0.8)
        ax.axvline(SPEC.f2 / 1e9, color="0.5", ls=":", lw=0.8)
        ax.axvspan(SPEC.f1 / 1e9, SPEC.f2 / 1e9, alpha=0.06, color="green")

    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"Saved {out}")

    # ---- metrics --------------------------------------------------------
    print("\n=== CST vs target metrics ===")
    from config import SPEC
    f0, f1, f2 = SPEC.f0, SPEC.f1, SPEC.f2

    if "S21" in cst:
        f_c, db_c = cst["S21"]
        in_band = (f_c >= f1) & (f_c <= f2)
        if in_band.any():
            il = -np.max(db_c[in_band])
            print(f"  CST insertion loss (min |S21| in passband) : {il:.2f} dB")
        peak_db = np.max(db_c)
        cross = np.where(np.diff((db_c > peak_db - 3).astype(int)))[0]
        if len(cross) >= 2:
            bw = (f_c[cross[-1]] - f_c[cross[0]]) / 1e6
            fc_est = (f_c[cross[-1]] + f_c[cross[0]]) / 2e9
            print(f"  CST −3dB centre / BW                        : {fc_est:.3f} GHz / {bw:.0f} MHz")

    if "S11" in cst:
        f_c, db_c = cst["S11"]
        in_band = (f_c >= f1) & (f_c <= f2)
        if in_band.any():
            rl = -np.max(db_c[in_band])
            print(f"  CST return loss (best |S11| in passband)    : {rl:.2f} dB")

    print(f"  Target passband                              : {f1/1e9:.3f}–{f2/1e9:.3f} GHz")
    print(f"  Target f0                                    : {f0/1e9:.3f} GHz")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cst", default=os.path.join(PROJ, "S ParametersV1.txt"))
    ap.add_argument("--target", default=os.path.join(PROJ, "target.s2p"))
    ap.add_argument("--out", default=os.path.join(PROJ, "compare.png"))
    args = ap.parse_args()
    compare(args.cst, args.target, args.out)
