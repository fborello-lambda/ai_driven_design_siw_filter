"""Overlay CST simulation results, openEMS results, and synthesis target.

Reads:
  - `S ParametersV1.txt` (CST tabular export, two blocks S11/S21, already in dB)
  - `target.s2p`  (scikit-rf Touchstone, synthesis)
  - `openems.s2p` (scikit-rf Touchstone, openEMS FDTD)  -- optional

Usage:
  uv run python compare.py                          # CST + target
  uv run python compare.py --oems openems.s2p       # all three
  uv run python compare.py --no-cst                 # openEMS + target only
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

from config import out_s2p, out_img

PROJ = os.path.dirname(os.path.abspath(__file__))


def _parse_cst_txt(path: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Parse CST tabular S-parameter export (GHz, values already in dB)."""
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
    """Convert linear magnitude to dB (used for .s2p networks only)."""
    return 20.0 * np.log10(np.clip(np.abs(mag_lin), 1e-12, None))


def _metrics(label: str, f: np.ndarray, s11_db: np.ndarray,
             s21_db: np.ndarray, f0: float, f1: float, f2: float) -> None:
    print(f"\n  [{label}]")
    in_band = (f >= f1) & (f <= f2)
    if in_band.any() and s21_db is not None:
        il = -np.max(s21_db[in_band])
        print(f"    insertion loss in passband : {il:.2f} dB")
    if s21_db is not None:
        peak = np.max(s21_db)
        cross = np.where(np.diff((s21_db > peak - 3).astype(int)))[0]
        if len(cross) >= 2:
            bw = (f[cross[-1]] - f[cross[0]]) / 1e6
            fc = (f[cross[-1]] + f[cross[0]]) / 2e9
            print(f"    -3dB centre / BW           : {fc:.3f} GHz / {bw:.0f} MHz")
    if in_band.any() and s11_db is not None:
        rl = -np.max(s11_db[in_band])
        print(f"    return loss in passband    : {rl:.2f} dB")


def compare(cst_path: str | None, target_path: str,
            oems_path: str | None = None, out: str = "compare.png") -> None:
    from config import SPEC
    f0, f1, f2 = SPEC.f0, SPEC.f1, SPEC.f2

    # ---- load data ------------------------------------------------------
    cst = _parse_cst_txt(cst_path) if cst_path and os.path.exists(cst_path) else {}
    tgt = skrf.Network(target_path)
    oems = skrf.Network(oems_path) if oems_path and os.path.exists(oems_path) else None

    colors = {"target": "#d62728", "cst": "#1f77b4", "oems": "#2ca02c"}

    # ---- plot -----------------------------------------------------------
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    for ax_idx, (param, i, j) in enumerate([("S11", 0, 0), ("S21", 1, 0)]):
        ax = axes[ax_idx]

        # Target (dashed red)
        tgt_db = _to_db(tgt.s[:, i, j])
        ax.plot(tgt.f / 1e9, tgt_db, color=colors["target"],
                lw=1.2, ls="--", label="Target (synthesis)")

        # CST (solid blue)
        if param in cst:
            f_c, db_c = cst[param]
            ax.plot(f_c / 1e9, db_c, color=colors["cst"],
                    lw=1.5, label="CST simulation")

        # openEMS (dash-dot green)
        if oems is not None:
            oems_db = _to_db(oems.s[:, i, j])
            ax.plot(oems.f / 1e9, oems_db, color=colors["oems"],
                    lw=1.5, ls="-.", label="openEMS FDTD")

        ax.set_ylabel(f"|{param}| [dB]")
        ax.set_ylim(-60, 5)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)
        ax.axvline(f1 / 1e9, color="0.5", ls=":", lw=0.8)
        ax.axvline(f2 / 1e9, color="0.5", ls=":", lw=0.8)
        ax.axvspan(f1 / 1e9, f2 / 1e9, alpha=0.06, color="green")
        ax.set_title(f"|{param}|", fontsize=10, loc="left")

    axes[-1].set_xlabel("Frequency [GHz]")
    sources = ["Target"]
    if cst: sources.append("CST")
    if oems: sources.append("openEMS")
    fig.suptitle(f"SIW BPF — {' vs '.join(sources)}   "
                 f"(f0={f0/1e9:.3f} GHz, N={SPEC.N}, FBW={SPEC.FBW*100:.0f}%)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"Saved {out}")

    # ---- metrics --------------------------------------------------------
    print(f"\n=== Metrics (target passband {f1/1e9:.3f}–{f2/1e9:.3f} GHz) ===")
    _metrics("Target", tgt.f,
             _to_db(tgt.s[:, 0, 0]), _to_db(tgt.s[:, 1, 0]), f0, f1, f2)
    if "S11" in cst and "S21" in cst:
        _metrics("CST", cst["S11"][0], cst["S11"][1], cst["S21"][1], f0, f1, f2)
    if oems is not None:
        _metrics("openEMS", oems.f,
                 _to_db(oems.s[:, 0, 0]), _to_db(oems.s[:, 1, 0]), f0, f1, f2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cst", default=os.path.join(PROJ, "cst_data", "S ParametersV1.txt"),
                    help="CST tabular export (.txt) — user-provided input in cst_data/")
    ap.add_argument("--no-cst", action="store_true", help="skip CST data")
    ap.add_argument("--target", default=out_s2p("target.s2p"))
    ap.add_argument("--oems", default=out_s2p("openems.s2p"),
                    help="openEMS touchstone output")
    ap.add_argument("--out", default=out_img("compare.png"))
    args = ap.parse_args()

    cst_path = None if args.no_cst else args.cst
    oems_path = args.oems if os.path.exists(args.oems) else None
    if oems_path is None and not args.no_cst:
        print(f"(openems.s2p not found — run openems_sim.py --fast to generate it)")

    compare(cst_path, args.target, oems_path, args.out)
