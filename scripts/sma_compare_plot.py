"""Combined |S11|/|S21| comparison: Palace with vs without the SMA coax
launch, plus the CST result on the same (optimized) design and the Chebyshev
synthesis target. Answers the professor's question with real S-parameter data
instead of an idealized microstrip port.

Run:  uv run python scripts/sma_compare_plot.py
Reads output/data/sma_compare.npz (from scripts/sma_compare_run.py),
docs/swi_CST_data.txt, output/s2p/target.s2p.
Writes output/imgs/sma_connector_compare.png
"""
from __future__ import annotations

import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import skrf as rf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data, out_img, out_s2p, data_path  # noqa: E402

# fixed categorical colors, reused from report.py's established convention
C_TARGET = "#808080"   # gray, dotted — synthesis target (neutral reference)
C_CST = "#2ca02c"      # green — CST (same hue meaning as report.py)
C_NOSMA = "#1f77b4"    # blue — Palace, idealized microstrip port (baseline)
C_SMA = "#d62728"      # red — Palace, real SMA coax launch (the new result)


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
    npz_path = out_data("sma_compare.npz")
    if not os.path.exists(npz_path):
        print(f"missing {npz_path} -- run scripts/sma_compare_run.py first")
        return 1
    d = np.load(npz_path)

    have_without = "sma_cmp_without_f" in d
    have_with = "sma_cmp_with_f" in d
    if not (have_without or have_with):
        print("npz has neither run's data")
        return 1

    tgt = rf.Network(out_s2p("target.s2p"))
    cst_txt = data_path("docs", "swi_CST_data.txt")
    have_cst = os.path.exists(cst_txt)
    if have_cst:
        cst_s11, cst_s21 = _parse_cst_blocks(cst_txt)

    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), sharex=True)

    ax[0].plot(tgt.f / 1e9, _db(tgt.s[:, 0, 0]), ":", color=C_TARGET, lw=1.5,
              label="Chebyshev target (synthesis)")
    if have_cst:
        ax[0].plot(cst_s11[:, 0], cst_s11[:, 1], "-", color=C_CST, lw=1.6,
                  label="CST (optimized design)")
    if have_without:
        ax[0].plot(d["sma_cmp_without_f"], _db(d["sma_cmp_without_s11"]), "-",
                  color=C_NOSMA, lw=1.8, label="Palace, microstrip port (no connector)")
    if have_with:
        ax[0].plot(d["sma_cmp_with_f"], _db(d["sma_cmp_with_s11"]), "-",
                  color=C_SMA, lw=2, label="Palace, SMA coax launch")
    ax[0].set_ylabel("|S11| (dB)"); ax[0].set_ylim(-40, 3); ax[0].grid(alpha=.3)
    ax[0].axvline(2.87, color="k", ls=":", lw=.8)
    ax[0].axhline(-16, color="grey", ls="--", lw=.7, alpha=.5)
    ax[0].legend(fontsize=8, loc="lower left")
    ax[0].set_title("Effect of a real SMA coax launch vs an idealized microstrip port")

    ax[1].plot(tgt.f / 1e9, _db(tgt.s[:, 1, 0]), ":", color=C_TARGET, lw=1.5,
              label="Chebyshev target")
    if have_cst:
        ax[1].plot(cst_s21[:, 0], cst_s21[:, 1], "-", color=C_CST, lw=1.6, label="CST")
    if have_without:
        ax[1].plot(d["sma_cmp_without_f"], _db(d["sma_cmp_without_s21"]), "-",
                  color=C_NOSMA, lw=1.8, label="Palace, no connector")
    if have_with:
        ax[1].plot(d["sma_cmp_with_f"], _db(d["sma_cmp_with_s21"]), "-",
                  color=C_SMA, lw=2, label="Palace, SMA coax launch")
    ax[1].set_ylabel("|S21| (dB)"); ax[1].set_xlabel("Frequency (GHz)")
    ax[1].set_xlim(2.5, 3.2); ax[1].set_ylim(-60, 3); ax[1].grid(alpha=.3)
    ax[1].axvline(2.87, color="k", ls=":", lw=.8)
    ax[1].legend(fontsize=8, loc="lower center")

    out = out_img("sma_connector_compare.png")
    fig.tight_layout(); fig.savefig(out, dpi=140)
    print(f"wrote {out}")

    # quick numeric summary
    if have_without and have_with:
        band = (2.80, 2.94)
        for name, f, s11 in (("no-connector", d["sma_cmp_without_f"], d["sma_cmp_without_s11"]),
                             ("SMA launch", d["sma_cmp_with_f"], d["sma_cmp_with_s11"])):
            m = (f >= band[0]) & (f <= band[1])
            worst = _db(s11[m]).max() if m.any() else float("nan")
            print(f"  {name}: worst in-band S11 [{band[0]}-{band[1]} GHz] = {worst:.1f} dB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
