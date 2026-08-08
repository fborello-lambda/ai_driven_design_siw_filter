"""Progress check: CST (existing result on the pre-SMA-fix optimized design)
vs SMA-v1 (first attempt, oversized pin, near-total reflection) vs the
current best-so-far from the running re-optimization (correctly-sized pin).
Run:  uv run python scripts/sma_progress_plot.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data, out_img, data_path  # noqa: E402

C_CST = "#2ca02c"
C_V1 = "#7f7f7f"
C_NOW = "#d62728"


def _db(x):
    return 20 * np.log10(np.clip(np.abs(x), 1e-6, None))


def _parse_cst_blocks(path: str):
    rows = []
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                rows.append(None)
                continue
            a, b = s.split()
            rows.append((float(a), float(b)))
    data = [r for r in rows if r]
    blk = [[]]
    prev = -1.0
    for fr, v in data:
        if fr < prev - 1e-9:
            blk.append([])
        blk[-1].append((fr, v))
        prev = fr
    return np.array(blk[0]), np.array(blk[1])


def main():
    cst_txt = data_path("docs", "swi_CST_data.txt")
    cst_s11, cst_s21 = _parse_cst_blocks(cst_txt)

    v1 = np.load(out_data("versions/sma-v1.npz"))
    v1_f, v1_s11, v1_s21 = v1["sma_cmp_with_f"], v1["sma_cmp_with_s11"], v1["sma_cmp_with_s21"]

    now_csv = out_data("postpro/optSma_34.40_34.30_13.00_16.00_15.46/port-S.csv")
    d = np.genfromtxt(now_csv, delimiter=",", names=True, deletechars="", replace_space="")
    nm = d.dtype.names
    now_f = d[nm[0]]; o = np.argsort(now_f); now_f = now_f[o]
    now_s11 = d[nm[1]][o]   # already in dB in this csv format
    now_s21 = d[nm[3]][o]

    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), sharex=True)

    ax[0].plot(cst_s11[:, 0], cst_s11[:, 1], "-", color=C_CST, lw=1.6, label="CST (pre-SMA-fix design)")
    ax[0].plot(v1_f, _db(v1_s11), "-", color=C_V1, lw=1.6, label="SMA v1 (oversized pin, broken)")
    ax[0].plot(now_f, now_s11, "-o", ms=3, color=C_NOW, lw=2, label="SMA now (correct pin, re-tuning in progress)")
    ax[0].set_ylabel("|S11| (dB)"); ax[0].set_ylim(-45, 3); ax[0].grid(alpha=.3)
    ax[0].axvline(2.87, color="k", ls=":", lw=.8)
    ax[0].axhline(-16, color="grey", ls="--", lw=.7, alpha=.5)
    ax[0].legend(fontsize=8, loc="lower left")
    ax[0].set_title("Progress: CST vs SMA v1 (broken) vs current re-tune (in progress)")

    ax[1].plot(cst_s21[:, 0], cst_s21[:, 1], "-", color=C_CST, lw=1.6, label="CST")
    ax[1].plot(v1_f, _db(v1_s21), "-", color=C_V1, lw=1.6, label="SMA v1")
    ax[1].plot(now_f, now_s21, "-o", ms=3, color=C_NOW, lw=2, label="SMA now")
    ax[1].set_ylabel("|S21| (dB)"); ax[1].set_xlabel("Frequency (GHz)")
    ax[1].set_xlim(2.5, 3.2); ax[1].set_ylim(-60, 3); ax[1].grid(alpha=.3)
    ax[1].axvline(2.87, color="k", ls=":", lw=.8)
    ax[1].legend(fontsize=8, loc="lower center")

    out = out_img("sma_progress_check.png")
    fig.tight_layout(); fig.savefig(out, dpi=140)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
