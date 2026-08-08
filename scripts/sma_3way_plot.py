"""Final 3-way comparison: old (mismatch-blind) optimum + real connector,
new re-tuned optimum without connector (idealized reference), new re-tuned
optimum WITH the real connector (the actual answer)."""
from __future__ import annotations

import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data, out_img  # noqa: E402

C_OLD = "#7f7f7f"    # gray: old design + connector
C_NEW_IDEAL = "#1f77b4"  # blue: new design, idealized port (no connector)
C_NEW_SMA = "#d62728"    # red: new design + connector (the answer)


def _db(x):
    return 20 * np.log10(np.clip(np.abs(x), 1e-6, None))


def main():
    d = np.load(out_data("sma_3way.npz"))
    old_f, old_s11, old_s21 = d["old_with_sma_f"], d["old_with_sma_s11"], d["old_with_sma_s21"]
    new0_f, new0_s11, new0_s21 = d["new_no_sma_f"], d["new_no_sma_s11"], d["new_no_sma_s21"]

    fine_csv = out_data("postpro/optSmaF_32.81_33.86_12.99_16.53_15.72/port-S.csv")
    fd = np.genfromtxt(fine_csv, delimiter=",", names=True, deletechars="", replace_space="")
    nm = fd.dtype.names
    new_sma_f = fd[nm[0]]
    new_sma_s11 = fd[nm[1]]   # already dB
    new_sma_s21 = fd[nm[3]]   # already dB

    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), sharex=True)

    ax[0].plot(old_f, _db(old_s11), "-", color=C_OLD, lw=1.8,
              label="Old optimum + connector (mismatch-blind design)")
    ax[0].plot(new0_f, _db(new0_s11), "-", color=C_NEW_IDEAL, lw=1.8,
              label="New optimum, idealized port (no connector)")
    ax[0].plot(new_sma_f, new_sma_s11, "-", color=C_NEW_SMA, lw=2.2,
              label="New optimum + connector (real-world result)")
    ax[0].set_ylabel("|S11| (dB)"); ax[0].set_ylim(-40, 3); ax[0].grid(alpha=.3)
    ax[0].axvline(2.87, color="k", ls=":", lw=.8)
    ax[0].axhline(-16, color="grey", ls="--", lw=.7, alpha=.5)
    ax[0].legend(fontsize=8, loc="lower left")
    ax[0].set_title("Final check: old design vs re-tuned design, with and without the real SMA connector")

    ax[1].plot(old_f, _db(old_s21), "-", color=C_OLD, lw=1.8, label="Old + connector")
    ax[1].plot(new0_f, _db(new0_s21), "-", color=C_NEW_IDEAL, lw=1.8, label="New, idealized port")
    ax[1].plot(new_sma_f, new_sma_s21, "-", color=C_NEW_SMA, lw=2.2, label="New + connector")
    ax[1].set_ylabel("|S21| (dB)"); ax[1].set_xlabel("Frequency (GHz)")
    ax[1].set_xlim(2.65, 3.05); ax[1].set_ylim(-40, 3); ax[1].grid(alpha=.3)
    ax[1].axvline(2.87, color="k", ls=":", lw=.8)
    ax[1].legend(fontsize=8, loc="lower center")

    out = out_img("sma_3way_final.png")
    fig.tight_layout(); fig.savefig(out, dpi=140)
    print(f"wrote {out}")

    band = (2.80, 2.94)
    for name, f, s11 in (("old+connector", old_f, _db(old_s11)),
                         ("new,no connector", new0_f, _db(new0_s11)),
                         ("new+connector", new_sma_f, new_sma_s11)):
        m = (f >= band[0]) & (f <= band[1])
        worst = s11[m].max() if m.any() else float("nan")
        print(f"  {name}: worst in-band S11 [{band[0]}-{band[1]}] = {worst:.1f} dB")


if __name__ == "__main__":
    main()
