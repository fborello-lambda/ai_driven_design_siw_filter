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

from siwfilter import palette as P

P.apply()

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
COLORS = [P.AZURE, P.TURQUOISE, P.PINK]
BAND = (2.87 - 0.07175, 2.87 + 0.07175)

COPIES = {
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
    ("2026-10-14", "2026-10-15", "VNA measurement,\npapers, cleanup"),
]


def _save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / name)


def fig_timeline():
    log = subprocess.run(["git", "log", "--format=%ad|%s", "--date=short"],
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
    cols = {"feature": P.AZURE, "fix": P.PINK, "docs / results": P.SLATE,
            "other": P.GOLD}
    # broken x axis: June prototype | Aug-Sep agent-driven work
    spans = [(dt.date(2026, 6, 5), dt.date(2026, 6, 25)),
             (dt.date(2026, 8, 20), dt.date(2026, 9, 9)),
             (dt.date(2026, 9, 21), dt.date(2026, 10, 17))]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True,
                             gridspec_kw={"width_ratios": [1, 1.4, 1.4], "wspace": 0.04})
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
    for ax in axes[1:]:
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", left=False)
    axes[0].set_ylim(0, ymax * 1.15)
    axes[0].set_ylabel("commits / day")
    axes[0].legend(loc="center", fontsize=8, ncol=1, frameon=False)
    legend = "   ".join(f"P{i}: {lab.replace(chr(10), ' ')}"
                        for i, (_, _, lab) in enumerate(PHASES, start=1))
    fig.text(0.5, -0.14, legend, ha="center", fontsize=7, wrap=True)
    fig.suptitle(f"Project history: {len(log)} commits, "
                 f"{days[0]:%d %b} – {days[-1]:%d %b %Y}", fontsize=10)
    _save(fig, "fig_timeline.png")


def fig_effort():
    """Agent-active hours per day (session logs) and commits per day by model (trailers)."""
    st = json.load(open(ROOT / "docs/paper/data/process_stats.json"))
    hours = {dt.date.fromisoformat(k): v for k, v in st.get("sessions", {}).get("active_hours_per_day", {}).items()}
    per_day = {dt.date.fromisoformat(k): v for k, v in st["per_day"].items()}
    models = ["Sonnet 5", "Opus 5", "Fable 5", "Opus 5.5", "Sonnet 5.5"]
    cols = {"Sonnet 5": P.AZURE, "Opus 5": P.ORANGE, "Fable 5": P.TURQUOISE, "Opus 5.5": P.VIOLET,
            "Sonnet 5.5": P.PINK, "no trailer": P.LILAC}
    spans = [(dt.date(2026, 6, 5), dt.date(2026, 6, 25)), (dt.date(2026, 8, 20), dt.date(2026, 9, 11)),
             (dt.date(2026, 9, 21), dt.date(2026, 10, 17))]
    fig, axes = plt.subplots(2, 3, figsize=(11, 4.6), sharey="row", sharex="col",
                             gridspec_kw={"width_ratios": [1, 1.4, 1.4], "wspace": 0.04, "hspace": 0.12})
    for j, (lo, hi) in enumerate(spans):
        a = axes[0, j]
        ds = [d for d in sorted(hours) if lo <= d <= hi]
        a.bar(ds, [hours[d] for d in ds], color=P.NAVY, width=0.8)
        b = axes[1, j]
        ds = [d for d in sorted(per_day) if lo <= d <= hi]
        bottom = np.zeros(len(ds))
        for m in models + ["no trailer"]:
            if m == "no trailer":
                # commits with a trailer are split by model; commits without one are the remainder
                v = np.array([per_day[d]["all"] - per_day[d]["agent"] for d in ds], float)
            else:
                v = np.array([per_day[d]["models"].get(m, 0) for d in ds], float)
            b.bar(ds, v, bottom=bottom, color=cols[m], width=0.8, label=m)
            bottom += v
        for a_ in (a, b):
            a_.set_xlim(lo, hi)
            a_.spines[["top", "right"]].set_visible(False)
            if j:
                a_.spines["left"].set_visible(False)
                a_.tick_params(axis="y", left=False)
        b.set_xticks([lo + dt.timedelta(d) for d in range(2, (hi - lo).days - 1, 7)])
        b.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        b.tick_params(axis="x", labelsize=8)
    axes[0, 0].set_ylabel("agent-active\nhours / day")
    axes[1, 0].set_ylabel("commits / day")
    axes[1, 0].legend(loc="upper left", fontsize=7.5, frameon=False)
    axes[0, 0].text(0.5, 0.5, "no session logs\n(prototype)", transform=axes[0, 0].transAxes, ha="center",
                    va="center", fontsize=8, color="0.5")
    tot = st.get("sessions", {}).get("active_hours")
    fig.suptitle(f"Effort: {tot:.0f} agent-active hours (gaps over "
                 f"{st['sessions']['idle_gap_minutes']} min excluded), {st['commits']} commits, "
                 f"{st['with_agent_trailer']} with an agent trailer", fontsize=10)
    _save(fig, "fig_effort.png")


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
                     boxstyle="round,pad=0.03", fc="#e6f0f9", ec=P.AZURE, lw=1.2))
        ax.text(i + 0.44, 0.05, text, ha="center", va="center", fontsize=8.2)
        if i < 5:
            ax.annotate("", xy=(i + 1.0, 0.05), xytext=(i + 0.88, 0.05),
                        arrowprops=dict(arrowstyle="-|>", color=P.AZURE))
    ax.add_patch(FancyBboxPatch((0.02, -1.25), 5.84, 0.5, boxstyle="round,pad=0.03",
                 fc="#fbeee3", ec=P.ORANGE, lw=1.2))
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
        ax.axvspan(*BAND, color=P.TURQUOISE, alpha=0.10)
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
    bandwidth -- the reason calibrate-and-invert replaced global GP search.
    Data: docs/paper/data/ (copied from `siw calibrate` / `siw scan` outputs)."""
    data = OUT.parent / "data"
    for name in ("calibration_cascade_N3.json", "scan_cascade_N3_w_ext.json"):
        src = ROOT / "output/data" / name
        if src.exists():
            data.mkdir(exist_ok=True)
            shutil.copy2(src, data / name)
    cal, scan = data / "calibration_cascade_N3.json", data / "scan_cascade_N3_w_ext.json"
    if not (cal.exists() and scan.exists()):
        print("skip fig_calib: needs siw calibrate + siw scan outputs")
        return
    c = json.loads(cal.read_text())
    s = json.loads(scan.read_text())
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    kp = sorted((float(w), v["k"]) for w, v in c["k"]["points"].items() if v.get("ok"))
    qp = sorted((float(w), v["Qe"]) for w, v in c["qe"]["points"].items() if v.get("ok"))
    inv = c.get("inverted_geometry", {})
    axes[0].plot(*zip(*kp), "o-")
    axes[0].axhline(c["targets"]["k"], color="0.5", ls=":")
    if "w_iris" in inv:
        axes[0].axvline(inv["w_iris"], color="0.5", ls=":")
    axes[0].set_xlabel(r"$w_{\mathrm{iris}}$ (mm)"); axes[0].set_ylabel("k")
    axes[0].set_title("(a) internal coupling, 2-cavity eigenmode", fontsize=9)
    axes[1].plot(*zip(*qp), "o-", color=P.ORANGE)
    axes[1].axhline(c["targets"]["Qe"], color="0.5", ls=":")
    if "w_ext" in inv:
        axes[1].axvline(inv["w_ext"], color="0.5", ls=":")
    axes[1].set_yscale("log")
    axes[1].set_xlabel(r"$w_{\mathrm{ext}}$ (mm)"); axes[1].set_ylabel(r"$Q_e$")
    axes[1].set_title("(b) external Q, one driven cavity", fontsize=9)
    pts = sorted((float(w), v) for w, v in s["points"].items() if v.get("ok"))
    x = [w for w, _ in pts]; bw = [v["bw"] for _, v in pts]
    axes[2].plot(x, bw, "o-", color=P.PINK)
    for xi, (_, v) in zip(x, pts):
        axes[2].annotate(f"{v['poles']}", (xi, v["bw"]), fontsize=7,
                         xytext=(0, 5), textcoords="offset points", ha="center")
    axes[2].axhline(143.5, color="0.5", ls=":")
    axes[2].set_xlabel(r"$w_{\mathrm{ext}}$ (mm)"); axes[2].set_ylabel("−3 dB bandwidth (MHz)")
    axes[2].set_title("(c) assembled N=3 filter (labels: reflection zeros)", fontsize=9)
    for ax in axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    _save(fig, "fig_calib.png")


def fig_setup():
    """Measurement photos (metadata-free JPEGs in measurements/) as one figure."""
    from PIL import Image
    ph = ROOT / "measurements/2026-10-14_vna/photos"
    need = ["dut_connected.jpg", "bench_setup.jpg", "vna_cal_setup.jpg"]
    if not all((ph / n).exists() for n in need):
        print("skip fig_setup: photos missing")
        return
    a, b, c = (Image.open(ph / n).convert("RGB") for n in need)
    # bench photo: keep the board, cables and VNA ports; drop the instrument screen (its
    # markers belong to an earlier sweep, not to the saved files)
    b = b.crop((0, 0, b.width, round(b.height * 0.60)))
    W, H, gap = 1500, 600, 12
    b = b.resize((round(b.width * H / b.height), H), Image.LANCZOS)
    cw = W - b.width - gap
    c = c.resize((cw, round(c.height * cw / c.width)), Image.LANCZOS)
    canvas = Image.new("RGB", (W, a.height + gap + H), "white")
    canvas.paste(a, (0, 0))
    canvas.paste(b, (0, a.height + gap))
    canvas.paste(c, (b.width + gap, a.height + gap + max(0, (H - c.height) // 2)))
    canvas.save(OUT / "fig_setup.jpg", "JPEG", quality=85, optimize=True)   # fresh image: no EXIF
    print("wrote", OUT / "fig_setup.jpg")


def fig_quantization():
    """Via-row quantization bug (fixed in the cascade mesh builders), redrawn so it is readable.

    Old rule: the iris arms were the vias of a FIXED grid with |y| > w/2 (grid step 3.06 mm for
    a_siw = 39.79 mm, p = 3 mm), so the opening only changed when w/2 crossed a grid point. New
    rule: the arms span exactly [w/2, half-width] with the pitch adjusted. Numbers are
    reproduced from the construction rule (the old code no longer exists in the tree).
    """
    a_siw, p, d = 39.79, 3.0, 1.5
    half = a_siw / 2
    n_grid = int(round(a_siw / p))
    grid = np.linspace(-half, half, n_grid + 1)
    grid_pos = grid[grid > 0]

    def before(w):
        return grid_pos[grid_pos > w / 2]

    def after(w):
        n = max(1, int(round((half - w / 2) / p)))
        return np.linspace(w / 2, half, n + 1)

    txt = {
        "en": dict(a="(a) Before: fixed grid", b="(b) After: arms placed from w/2",
                   c="(c) Opening of the iris in the mesh", x="y from the filter axis (mm)",
                   row="requested w = {w:g} mm", cx="requested iris width w (mm)",
                   cy="width actually meshed (mm)", old="before (fixed grid)", new="after (fix)",
                   note="6 and 9 mm:\nsame mesh", note2="12 and 15 mm:\nsame mesh", note3="18 and 21 mm:\nsame mesh",
                   edge="requested edge w/2"),
        "es": dict(a="(a) Antes: grilla fija", b="(b) Después: brazos desde w/2",
                   c="(c) Abertura del iris en la malla", x="y desde el eje del filtro (mm)",
                   row="w pedido = {w:g} mm", cx="ancho de iris pedido w (mm)",
                   cy="ancho realmente mallado (mm)", old="antes (grilla fija)", new="después (corrección)",
                   note="6 y 9 mm:\nmisma malla", note2="12 y 15 mm:\nmisma malla", note3="18 y 21 mm:\nmisma malla",
                   edge="borde pedido w/2"),
    }
    for lang, t in txt.items():
        fig, ax = plt.subplots(1, 3, figsize=(13, 3.8), gridspec_kw={"width_ratios": [1.2, 1.2, 1]})
        for a, fn, title in ((ax[0], before, t["a"]), (ax[1], after, t["b"])):
            for row, (w, col) in enumerate(((6, P.AZURE), (9, P.PINK))):
                y0 = 4.0 - 4.0 * row
                for y in fn(w):
                    a.add_patch(plt.Circle((y, y0), d / 2, color=col, alpha=0.85))
                a.plot([w / 2, w / 2], [y0 - 1.6, y0 + 1.6], "k--", lw=0.9)
                a.text(0.2, y0 + 2.0, t["row"].format(w=w), ha="left", va="center", fontsize=8, color=col)
            a.set_xlim(0, half + 1.2); a.set_ylim(-2.0, 6.6); a.set_aspect("equal")
            a.set_yticks([]); a.set_xlabel(t["x"]); a.set_title(title, fontsize=10)
            for sp in ("top", "right", "left"):
                a.spines[sp].set_visible(False)
        ax[0].plot([], [], "k--", lw=0.9, label=t["edge"]); ax[0].legend(fontsize=7.5, loc="lower right", frameon=False)
        w = np.linspace(4, 22, 400)
        eff = [2 * before(x)[0] if len(before(x)) else np.nan for x in w]
        ax[2].plot(w, w, color=P.TURQUOISE, lw=2, label=t["new"])
        ax[2].plot(w, eff, color=P.ORANGE, lw=2, label=t["old"])
        for (w1, w2), lab in (((6, 9), t["note"]), ((12, 15), t["note2"]), ((18, 21), t["note3"])):
            e = 2 * before(w1)[0]
            ax[2].plot([w1, w2], [e, e], "o-", color="k", ms=4, lw=0.8)
            ax[2].text((w1 + w2) / 2, e + 0.6, lab, ha="center", va="bottom", fontsize=7)
        ax[2].set(xlabel=t["cx"], ylabel=t["cy"], title=t["c"])
        ax[2].grid(alpha=0.3); ax[2].legend(fontsize=8, loc="lower right")
        fig.tight_layout()
        name = "fig_quantization.png" if lang == "en" else "fig_quantizacion_es.png"
        _save(fig, name)


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
    fig_effort()
    fig_flow()
    fig_designs()
    fig_layouts()
    fig_calib()
    fig_setup()
    fig_quantization()
