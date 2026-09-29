"""Build every figure the two papers use, from data in the repo.

Run from the repo root:  uv run python docs/paper/figures/make_figures.py

Generated here: fig_timeline, fig_flow, fig_designs, fig_layouts, fig_calib
(the last needs the `siw calibrate` + `siw scan` outputs in output/data).
Copied here from where the evidence lives: the rest (see COPIES).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
G = ROOT / "golden"

GOLDEN = {
    "Dual-mode N=2 (1 cavity)":
        G / "dualmode_N2/a57.16_wiris15.30_xiris28.68_ywall9.85_wext16.35_cpwg_taoglas.s11s21.json",
    "Cascade N=3 (fabricated)":
        G / "cascade_N3/l_cav133.94_l_cav235.5_l_taper15.74_w_ext13.96_w_iris14.42_w_ms1.66_cpwg_taoglas.s11s21.json",
    "Cascade N=4":
        G / "cascade_N4/l_cav134.33_l_cav235.3_l_taper17.42_w_ext13.74_w_iris115.6_w_iris213.04_w_ms1.66_cpwg_taoglas.s11s21.json",
}
BOARD_MM = {"Dual-mode N=2 (1 cavity)": 119.0, "Cascade N=3 (fabricated)": 165.8,
            "Cascade N=4": 211.0}
COLORS = ["#1f77b4", "#2ca02c", "#d62728"]
BAND = (2.87 - 0.07175, 2.87 + 0.07175)

COPIES = {
    "fig_quantization.png": "docs/dualmode_cavity/via_continuity_bugfix.png",
    "fig_final_trim.png": "docs/final_check/trim_comparison.png",
    "fig_coupling_fit.png": "docs/final_check/analysis.png",
    "fig_launch_sparams.png": "docs/launch_comparison/sparams.png",
    "fig_launch_renders.png": "docs/launch_comparison/renders.png",
    "fig_sma_v1.png": "docs/sma_connector/v1_broken_pin.png",
}

# Project phases for the timeline (dates from git history).
PHASES = [
    ("2026-06-07", "2026-06-23", "analytic + openEMS\n+ CST v1/v2"),
    ("2026-08-22", "2026-08-23", "Palace, SMA,\nunified CLI"),
    ("2026-08-23", "2026-08-29", "GP searches: geometry\nvariants, N=4 (closed)"),
    ("2026-08-30", "2026-09-03", "calibrate-and-invert"),
    ("2026-09-04", "2026-09-07", "fab files,\nCST audit"),
    ("2026-09-23", "2026-09-29", "fine-mesh final,\nJLCPCB"),
]


def _save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / name)


def fig_timeline():
    log = subprocess.run(["git", "log", "b06bf63", "--format=%ad|%s", "--date=short"],
                         cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    kinds = {"feat": "feature", "fix": "fix", "revert": "fix", "docs": "docs / results",
             "data": "docs / results", "results": "docs / results"}
    per_day = collections.defaultdict(collections.Counter)
    for line in log:
        d, s = line.split("|", 1)
        k = s.split(":")[0].split("(")[0].strip().lower()
        per_day[dt.date.fromisoformat(d)][kinds.get(k, "other")] += 1
    days = sorted(per_day)
    cats = ["feature", "fix", "docs / results", "other"]
    cols = {"feature": "#1f77b4", "fix": "#d62728", "docs / results": "#7f7f7f",
            "other": "#bcbd22"}
    # broken x axis: June prototype | Aug-Sep agent-driven work
    spans = [(dt.date(2026, 6, 5), dt.date(2026, 6, 25)),
             (dt.date(2026, 8, 20), dt.date(2026, 10, 1))]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), sharey=True,
                             gridspec_kw={"width_ratios": [1, 2.4], "wspace": 0.04})
    ymax = max(sum(per_day[d].values()) for d in days)
    for ax, (lo, hi) in zip(axes, spans):
        ds = [d for d in days if lo <= d <= hi]
        bottom = np.zeros(len(ds))
        for c in cats:
            v = np.array([per_day[d][c] for d in ds], float)
            ax.bar(ds, v, bottom=bottom, color=cols[c], width=0.8, label=c)
            bottom += v
        for i, (a0, b0, lab) in enumerate(PHASES, start=1):
            a0, b0 = dt.date.fromisoformat(a0), dt.date.fromisoformat(b0)
            if lo <= a0 <= hi:
                ax.axvspan(a0 - dt.timedelta(0.5), b0 + dt.timedelta(0.5),
                           color="0.9" if i % 2 else "0.95", zorder=0)
                ax.text(a0 + (b0 - a0) / 2, ymax * 1.03, f"P{i}", ha="center",
                        fontsize=9, fontweight="bold")
        ax.set_xlim(lo, hi)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xticks([lo + dt.timedelta(d) for d in range(2, (hi - lo).days - 1, 7)])
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.tick_params(axis="x", labelsize=8)
    axes[1].spines["left"].set_visible(False)
    axes[1].tick_params(axis="y", left=False)
    axes[0].set_ylim(0, ymax * 1.15)
    axes[0].set_ylabel("commits / day")
    axes[0].legend(loc="center", fontsize=8, ncol=1, frameon=False)
    legend = "   ".join(f"P{i}: {lab.replace(chr(10), ' ')}"
                        for i, (_, _, lab) in enumerate(PHASES, start=1))
    fig.text(0.5, -0.1, legend, ha="center", fontsize=7.5, wrap=True)
    fig.suptitle(f"Project history: {len(log)} commits, "
                 f"{days[0]:%d %b} – {days[-1]:%d %b %Y}", fontsize=10)
    _save(fig, "fig_timeline.png")


def fig_flow():
    boxes = [
        ("Specification\nf0, FBW, ripple,\nsubstrate, vias", 0),
        ("Chebyshev synthesis\ng-values → k, Qe\ncoupling matrix", 1),
        ("SIW geometry\nvia fences, irises,\ntaper, CPWG launch", 2),
        ("EM calibration\n(Palace eigenmode /\nsingle-cavity driven)", 3),
        ("Invert → assemble\n→ driven confirm\n(+ local GP polish)", 4),
        ("Fab outputs\nKiCad gerbers, STEP,\nCST macro, 34 checks", 5),
    ]
    fig, ax = plt.subplots(figsize=(12, 3.4))
    ax.set_xlim(-0.2, 6.1); ax.set_ylim(-1.35, 1.1); ax.axis("off")
    for text, i in boxes:
        ax.add_patch(FancyBboxPatch((i + 0.02, -0.45), 0.84, 1.0,
                     boxstyle="round,pad=0.03", fc="#e8f0fa", ec="#1f4e79", lw=1.2))
        ax.text(i + 0.44, 0.05, text, ha="center", va="center", fontsize=8.2)
        if i < 5:
            ax.annotate("", xy=(i + 1.0, 0.05), xytext=(i + 0.88, 0.05),
                        arrowprops=dict(arrowstyle="-|>", color="#1f4e79"))
    ax.add_patch(FancyBboxPatch((0.02, -1.25), 5.84, 0.5, boxstyle="round,pad=0.03",
                 fc="#fdf2e3", ec="#b36b00", lw=1.2))
    ax.text(2.94, -1.0, "LLM coding agent (Claude Code): writes and runs every stage "
            "through the `siw` CLI, reads solver logs, diagnoses, commits to git.\n"
            "Human: specification, topology and fab decisions, CST GUI runs, "
            "sanity challenges, ordering.", ha="center", va="center", fontsize=8.2)
    _save(fig, "fig_flow.png")


def _band_edges(f, s21):
    thr = s21.max() - 3
    idx = np.flatnonzero(s21 >= thr)
    return f[idx[0]], f[idx[-1]]


def fig_designs():
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharex=True)
    for (name, path), c in zip(GOLDEN.items(), COLORS):
        d = json.loads(path.read_text())
        f, s11, s21 = (np.asarray(d[k]) for k in ("f_ghz", "s11_db", "s21_db"))
        band = (f >= BAND[0]) & (f <= BAND[1])
        lab = f"{name}: worst in-band |S11| {s11[band].max():.1f} dB, board {BOARD_MM[name]:.0f} mm"
        axes[0].plot(f, s21, color=c, lw=1.8, label=lab)
        axes[1].plot(f, s11, color=c, lw=1.8)
    for ax, t in zip(axes, ("|S21| (dB)", "|S11| (dB)")):
        ax.axvspan(*BAND, color="#2ca02c", alpha=0.08)
        ax.axhline(-16, color="0.5", ls=":", lw=1)
        ax.set_ylabel(t); ax.set_xlabel("Frequency (GHz)")
        ax.set_xlim(2.6, 3.15); ax.set_ylim(-40, 1); ax.grid(alpha=0.3)
    fig.legend(loc="lower center", ncol=1, fontsize=8.5, frameon=False,
               bbox_to_anchor=(0.5, -0.13))
    _save(fig, "fig_designs.png")


def _crop_title(img, top_frac=0.09):
    return img[int(img.shape[0] * top_frac):]


def fig_layouts():
    imgs = ROOT / "output/imgs"
    a = imgs / "layout_dualmode_N2_2d.png"
    b = imgs / "layout_cascade_N3_2d.png"
    if not (a.exists() and b.exists()):
        print("skip fig_layouts: run `siw layout` for both designs first")
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 3.6),
                             gridspec_kw={"width_ratios": [1, 1.55]})
    for ax, p, t in zip(axes, (a, b), ("(a) Dual-mode N=2, 119 mm",
                                        "(b) Cascade N=3 (fabricated), 166 mm")):
        ax.imshow(_crop_title(mpimg.imread(p)))
        ax.set_title(t, fontsize=10); ax.axis("off")
    _save(fig, "fig_layouts.png")


def fig_calib():
    """Smooth calibration observables vs the discontinuous assembled-filter
    bandwidth -- the reason calibrate-and-invert replaced global GP search."""
    cal = ROOT / "output/data/calibration_cascade_N3.json"
    scan = sorted((ROOT / "output/data").glob("scan_cascade_N3*w_ext*.json"))
    if not cal.exists() or not scan:
        print("skip fig_calib: needs siw calibrate + siw scan outputs")
        return
    c = json.loads(cal.read_text())
    s = json.loads(scan[-1].read_text())
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    k = c["k"]["points"]; q = c["qe"]["points"]
    axes[0].plot([p["w_iris"] for p in k], [p["k"] for p in k], "o-")
    axes[0].axhline(c["k"].get("target", 0.0461), color="0.5", ls=":")
    axes[0].set_xlabel("w_iris (mm)"); axes[0].set_ylabel("k")
    axes[0].set_title("(a) internal coupling, 2-cavity eigenmode", fontsize=9)
    axes[1].plot([p["w_ext"] for p in q], [p["Qe"] for p in q], "o-", color="#ff7f0e")
    axes[1].axhline(c["qe"].get("target", 20.63), color="0.5", ls=":")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("w_ext (mm)"); axes[1].set_ylabel("Qe")
    axes[1].set_title("(b) external Q, one driven cavity", fontsize=9)
    pts = s["points"]
    x = [p["value"] for p in pts]; bw = [p["bw"] for p in pts]
    lobes = [p.get("n_lobes", 1) for p in pts]
    axes[2].plot(x, bw, "o-", color="#d62728")
    for xi, yi, n in zip(x, bw, lobes):
        if n > 1:
            axes[2].annotate("split", (xi, yi), fontsize=7, xytext=(3, 3),
                             textcoords="offset points")
    axes[2].axhline(143.5, color="0.5", ls=":")
    axes[2].set_xlabel("w_ext (mm)"); axes[2].set_ylabel("−3 dB bandwidth (MHz)")
    axes[2].set_title("(c) assembled N=3 filter", fontsize=9)
    for ax in axes:
        ax.grid(alpha=0.3)
    _save(fig, "fig_calib.png")


def copies():
    for dst, src in COPIES.items():
        p = ROOT / src
        if p.exists():
            shutil.copy2(p, OUT / dst)
            print("copied", src, "->", dst)
        elif not (OUT / dst).exists():
            print("MISSING", src)


if __name__ == "__main__":
    copies()
    fig_timeline()
    fig_flow()
    fig_designs()
    fig_layouts()
    fig_calib()
