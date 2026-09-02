#!/usr/bin/env python
"""Report stage: regenerate the comparison figures and (re)compile the IEEE PDF.

Consolidates what used to be three ad-hoc scripts:
  - make_report.py : sync pipeline figures into the report folder + build PDF
  - _finalize.py   : regenerate palace.s2p from the final driven solve and the
                     combined synthesis/CST-1st/openEMS/Palace comparison figure
  - _cst_v2.py     : parse the returned CST run (final optimized design) and
                     overlay it against Palace + target

Every path resolves under the project root via ``config`` (``data_path`` /
``out_*``), so the stage works regardless of the current working directory.

Run:
    uv run python -m siwfilter.report                 # all available steps + PDF
    uv run python -m siwfilter.report --no-build      # figures only, skip PDF
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

import json

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import skrf as rf

from .config import OUTPUT_DIR, data_path, out_s2p, out_img

REPORT_DIR = data_path("docs")
REPORT_MD = "Anteproyecto_Filtro_SIW_287GHz.md"
IMG_DIR = os.path.join(OUTPUT_DIR, "imgs")

# Pipeline-produced figures the report embeds by bare filename.
REPORT_FIGS = ["compare.png", "compare_all.png"]


def _db(x):
    return 20 * np.log10(np.clip(np.abs(x), 1e-6, None))


def _parse_cst_blocks(path: str):
    """Parse a CST tabular export with two stacked blocks (S11 then S21, dB)."""
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


def finalize_palace_s2p() -> bool:
    """Write output/s2p/palace.s2p from the final driven solve (if present)."""
    csv = OUTPUT_DIR + "/data/postpro/final/port-S.csv"
    if not os.path.exists(csv):
        print(f"  (skip palace.s2p — {csv} not found; run the final driven solve first)")
        return False
    d = np.genfromtxt(csv, delimiter=",", names=True, deletechars="", replace_space="")
    nm = d.dtype.names
    f = d[nm[0]]
    o = np.argsort(f)
    f = f[o]
    s11 = 10 ** (d[nm[1]][o] / 20) * np.exp(1j * np.deg2rad(d[nm[2]][o]))
    s21 = 10 ** (d[nm[3]][o] / 20) * np.exp(1j * np.deg2rad(d[nm[4]][o]))
    keep = (np.abs(s11) <= 1.001) & (np.abs(s21) <= 1.001)
    f, s11, s21 = f[keep], s11[keep], s21[keep]
    S = np.zeros((len(f), 2, 2), dtype=complex)
    S[:, 0, 0] = s11; S[:, 1, 0] = s21; S[:, 0, 1] = s21; S[:, 1, 1] = s11
    net = rf.Network(frequency=rf.Frequency.from_f(f * 1e9, unit="hz"), s=S, z0=50,
                     name="SIW_BPF_Palace")
    net.write_touchstone(out_s2p("palace.s2p").replace(".s2p", ""))
    print(f"  palace.s2p: {len(f)} pts")
    return True


def build_compare_final() -> bool:
    """Combined figure: synthesis target + CST 1st iter + openEMS + Palace final."""
    cst_txt = data_path("S Parameters.txt")
    needed = [out_s2p("target.s2p"), out_s2p("openems.s2p"), out_s2p("palace.s2p"), cst_txt]
    if not all(os.path.exists(p) for p in needed):
        print("  (skip compare_final.png — missing one of target/openems/palace/CST 1st)")
        return False
    tgt = rf.Network(out_s2p("target.s2p"))
    oem = rf.Network(out_s2p("openems.s2p"))
    pal = rf.Network(out_s2p("palace.s2p"))
    cst_s11, cst_s21 = _parse_cst_blocks(cst_txt)

    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), sharex=True)
    ax[0].plot(tgt.f / 1e9, _db(tgt.s[:, 0, 0]), ":", color="gray", lw=1.5, label="Objetivo (sintesis)")
    ax[0].plot(cst_s11[:, 0], cst_s11[:, 1], "-", color="#2ca02c", lw=1.5, label="CST 1ra iter. (L=38.2)")
    ax[0].plot(oem.f / 1e9, _db(oem.s[:, 0, 0]), "-", color="#ff7f0e", lw=1.3, alpha=.8, label="openEMS (L=38.2)")
    ax[0].plot(pal.f / 1e9, _db(pal.s[:, 0, 0]), "-", color="#1f77b4", lw=2, label="Palace final (L=34.4, w_ext=16)")
    ax[0].set_ylabel("|S11| (dB)"); ax[0].set_ylim(-40, 3); ax[0].grid(alpha=.3)
    ax[0].axvline(2.87, color="k", ls=":", lw=.8); ax[0].axhline(-16, color="grey", ls="--", lw=.7, alpha=.5)
    ax[0].legend(fontsize=8, loc="lower left"); ax[0].set_title("Comparacion de metodos - |S11| y |S21|")
    ax[1].plot(tgt.f / 1e9, _db(tgt.s[:, 1, 0]), ":", color="gray", lw=1.5, label="Objetivo (sintesis)")
    ax[1].plot(cst_s21[:, 0], cst_s21[:, 1], "-", color="#2ca02c", lw=1.5, label="CST 1ra iter.")
    ax[1].plot(oem.f / 1e9, _db(oem.s[:, 1, 0]), "-", color="#ff7f0e", lw=1.3, alpha=.8, label="openEMS")
    ax[1].plot(pal.f / 1e9, _db(pal.s[:, 1, 0]), "-", color="#d62728", lw=2, label="Palace final")
    ax[1].set_ylabel("|S21| (dB)"); ax[1].set_xlabel("Frecuencia (GHz)")
    ax[1].set_xlim(2.0, 3.6); ax[1].set_ylim(-60, 3); ax[1].grid(alpha=.3)
    ax[1].axvline(2.87, color="k", ls=":", lw=.8); ax[1].legend(fontsize=8, loc="lower center")
    out = out_img("compare_final.png")
    fig.tight_layout(); fig.savefig(out, dpi=140)
    shutil.copy2(out, os.path.join(REPORT_DIR, "compare_final.png"))
    print(f"  compare_final.png -> {REPORT_DIR}")
    return True


def build_cst_v2_compare() -> bool:
    """Overlay the returned CST run (final design) vs Palace + target."""
    cst_txt = os.path.join(REPORT_DIR, "swi_CST_data.txt")
    if not all(os.path.exists(p) for p in (cst_txt, out_s2p("palace.s2p"), out_s2p("target.s2p"))):
        print("  (skip compare_cst_v2.png — missing CST V2 data / palace / target)")
        return False
    cst_s11, cst_s21 = _parse_cst_blocks(cst_txt)
    tgt = rf.Network(out_s2p("target.s2p"))
    pal = rf.Network(out_s2p("palace.s2p"))

    f, s11, s21 = cst_s11[:, 0], cst_s11[:, 1], cst_s21[:, 1]
    peak = s21.max(); above = f[s21 >= peak - 3]
    fc = 0.5 * (above.min() + above.max()); bw3 = (above.max() - above.min()) * 1e3
    print(f"  CST V2: center(-3dB)={fc:.4f} GHz, BW(-3dB)={bw3:.0f} MHz, peak S21={peak:.2f} dB")

    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), sharex=True)
    ax[0].plot(tgt.f / 1e9, _db(tgt.s[:, 0, 0]), ":", color="gray", lw=1.5, label="Objetivo (sintesis)")
    ax[0].plot(pal.f / 1e9, _db(pal.s[:, 0, 0]), "-", color="#1f77b4", lw=1.6, alpha=.8, label="Palace final")
    ax[0].plot(cst_s11[:, 0], cst_s11[:, 1], "-", color="#d62728", lw=2, label="CST V2 (mismas dims)")
    ax[0].set_ylabel("|S11| (dB)"); ax[0].set_ylim(-40, 3); ax[0].grid(alpha=.3)
    ax[0].axvline(2.87, color="k", ls=":", lw=.8); ax[0].axhline(-16, color="grey", ls="--", lw=.7, alpha=.5)
    ax[0].legend(fontsize=8, loc="lower left")
    ax[0].set_title("Verificacion CST V2 vs Palace (diseno optimizado: L_cav=34.4, w_ext=16, w_iris=13)")
    ax[1].plot(tgt.f / 1e9, _db(tgt.s[:, 1, 0]), ":", color="gray", lw=1.5, label="Objetivo (sintesis)")
    ax[1].plot(pal.f / 1e9, _db(pal.s[:, 1, 0]), "-", color="#1f77b4", lw=1.6, alpha=.8, label="Palace final")
    ax[1].plot(cst_s21[:, 0], cst_s21[:, 1], "-", color="#d62728", lw=2, label="CST V2")
    ax[1].set_ylabel("|S21| (dB)"); ax[1].set_xlabel("Frecuencia (GHz)")
    ax[1].set_xlim(2.0, 3.6); ax[1].set_ylim(-60, 3); ax[1].grid(alpha=.3)
    ax[1].axvline(2.87, color="k", ls=":", lw=.8); ax[1].legend(fontsize=8, loc="lower center")
    out = os.path.join(REPORT_DIR, "compare_cst_v2.png")
    fig.tight_layout(); fig.savefig(out, dpi=140)
    print(f"  compare_cst_v2.png -> {REPORT_DIR}")
    return True


def build_design_comparison(golden_paths: list[str], f0_ghz: float = 2.87,
                            fbw: float = 0.05, spec_db: float = -16.0,
                            out_name: str = "design_comparison",
                            labels: list[str] | None = None) -> bool:
    """Fabrication-decision comparison across an arbitrary list of golden
    design entries (golden/<topology_N>/<stem>.json, each needing its
    companion <stem>.s11s21.json for the raw sweep).

    Two figures: (1) S11/S21 for every design on IDENTICAL x/y axes -- the
    earlier ad-hoc version of this plot mixed a leftover narrow sweep window
    for one design against a proper wide one for the others, which made the
    designs look qualitatively different rather than letting the real
    performance gap show; (2) board footprints drawn to true relative scale,
    since each topology's own layout plot auto-scales its own figure and so
    never shows which design is actually bigger.
    """
    from .config import FilterSpec
    from .topologies import REGISTRY

    entries = []
    for i, p in enumerate(golden_paths):
        stem = p[:-len(".json")] if p.endswith(".json") else p
        s11s21_path = stem + ".s11s21.json"
        if not (os.path.exists(p) and os.path.exists(s11s21_path)):
            print(f"  (skip {p} -- missing golden json or companion .s11s21.json)")
            continue
        d = json.load(open(p))
        sd = json.load(open(s11s21_path))
        m = d.get("metrics", {})
        # Whether a design is "landed" vs "best known" isn't reliably
        # inferable from the golden schema (the landed dualmode N=2 entry
        # still carries its own known_open_item, the bandwidth gap) -- let
        # the caller supply labels; default to a bare topology/N tag.
        title = labels[i] if labels and i < len(labels) else f"{d.get('topology', '?')} N={d.get('N', '?')}"
        board_mm = m.get("board_length_mm")
        if board_mm is None:
            try:
                topo_obj = REGISTRY[d["topology"]]
                spec = FilterSpec(N=d["N"])
                board_mm = topo_obj.board_length_mm(spec, **d["params"])
            except Exception:
                board_mm = float("nan")
        entries.append(dict(title=title, f=sd["f_ghz"], s11=sd["s11_db"], s21=sd["s21_db"],
                            s11w=m.get("s11w_db", float("nan")), board_mm=board_mm))
    if not entries:
        print("  (skip design comparison -- no valid golden entries)")
        return False

    colors = plt.cm.tab10.colors
    xlim = (min(min(e["f"]) for e in entries), max(max(e["f"]) for e in entries))

    fig, axes = plt.subplots(len(entries), 2, figsize=(12, 3 * len(entries)), sharex=True,
                             squeeze=False)
    for row, e in enumerate(entries):
        color = colors[row % len(colors)]
        ax21, ax11 = axes[row]
        for ax in (ax21, ax11):
            ax.axvspan(f0_ghz * (1 - fbw / 2), f0_ghz * (1 + fbw / 2), color="green", alpha=0.08)
            ax.axhline(spec_db, color="gray", ls=":", lw=1)
            ax.set_xlim(*xlim); ax.set_ylim(-40, 2); ax.grid(alpha=0.3)
        ax21.plot(e["f"], e["s21"], color=color, lw=1.6)
        ax21.set_ylabel("|S21| (dB)")
        ax21.set_title(f"{e['title']}  --  S11w={e['s11w']:.1f}dB  board={e['board_mm']:.0f}mm",
                       loc="left", fontsize=10)
        ax11.plot(e["f"], e["s11"], color=color, lw=1.6)
        ax11.set_ylabel("|S11| (dB)")
    axes[-1][0].set_xlabel("Frequency (GHz)")
    axes[-1][1].set_xlabel("Frequency (GHz)")
    fig.suptitle(f"Design comparison, same axes/window "
                f"(green={fbw * 100:.0f}% FBW target, dotted={spec_db:.0f}dB spec)")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out1 = out_img(f"{out_name}_sparams.png")
    fig.savefig(out1, dpi=140)
    plt.close(fig)
    shutil.copy2(out1, os.path.join(REPORT_DIR, f"{out_name}_sparams.png"))
    print(f"  {out_name}_sparams.png -> {REPORT_DIR}")

    fig2, ax2 = plt.subplots(figsize=(12, 1.2 + 1.6 * len(entries)))
    y0, gap, h = 0.0, 18.0, 12.0
    maxlen = max(e["board_mm"] for e in entries)
    for row, e in enumerate(entries):
        color = colors[row % len(colors)]
        ax2.add_patch(Rectangle((0, y0), e["board_mm"], h, fill=True, fc=color, alpha=0.25,
                                ec=color, lw=1.5))
        ax2.text(e["board_mm"] + 0.02 * maxlen, y0 + h / 2,
                 f"{e['title']}\n{e['board_mm']:.0f}mm, S11w={e['s11w']:.1f}dB",
                 va="center", fontsize=9)
        y0 += gap
    ax2.set_xlim(0, maxlen * 1.5)
    ax2.set_ylim(-6, y0)
    ax2.set_yticks([])
    ax2.set_xlabel("Board length (mm)")
    ax2.set_title("Board footprint, true relative scale")
    ax2.grid(axis="x", alpha=0.3)
    fig2.tight_layout()
    out2 = out_img(f"{out_name}_board_scale.png")
    fig2.savefig(out2, dpi=140)
    plt.close(fig2)
    shutil.copy2(out2, os.path.join(REPORT_DIR, f"{out_name}_board_scale.png"))
    print(f"  {out_name}_board_scale.png -> {REPORT_DIR}")
    return True


# Fabrication variants of ONE design: default set and their plot styling.
# Unlike build_design_comparison (different designs, stacked per-design
# subplots), these are the SAME geometry under different fabrication stacks,
# so they belong on one shared pair of axes to be comparable at a glance.
FAB_VARIANTS = [
    ("pec_optimized",  "1. PEC (as optimized)",             "black",      "-",  2.2),
    ("cu_silk_tented", "2. Cu+ENIG+mask+silk, vias tented", "tab:red",    "-",  1.6),
    ("cu_silk_open",   "3. Cu+ENIG+mask+silk, vias open",   "tab:orange", "--", 1.6),
    ("cu_nosilk",      "4. Cu+ENIG+mask, no silkscreen",    "tab:blue",   "-.", 1.6),
]


def build_fab_variant_comparison(result_json: str | None = None,
                                 f0_ghz: float = 2.87, fbw: float = 0.05,
                                 spec_db: float = -16.0,
                                 out_name: str = "fab_variant_comparison",
                                 variants: list | None = None) -> bool:
    """One overlay of every fabrication variant + the ideal Chebyshev target.

    Reads the incremental result JSON produced by the variant sweep, so it can
    be run while cells are still solving -- variants that have not landed yet
    are skipped rather than failing. Also writes the plotted curves and the
    metrics table back out as JSON, so the figure's underlying data is kept
    alongside it instead of living only inside a PNG.
    """
    from .config import out_data
    path = result_json or out_data("four_variants_result.json")
    if not os.path.exists(path):
        print(f"  (skip fab variants -- no {path})")
        return False
    data = json.load(open(path))
    variants = variants or FAB_VARIANTS

    fig, (ax21, ax11) = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
    rows, saved, n = [], {}, 0
    for key, label, colour, ls, lw in variants:
        e = data.get(key)
        if not e:
            print(f"  (pending: {label})")
            continue
        f, s11, s21 = e["f_ghz"], e["s11_db"], e["s21_db"]
        ax21.plot(f, s21, label=label, color=colour, ls=ls, lw=lw)
        ax11.plot(f, s11, label=label, color=colour, ls=ls, lw=lw)
        m = e["metrics"]
        rows.append((label, m.get("fc_3db", m.get("fc")), m.get("il"),
                     m.get("bw"), m.get("s11w")))
        saved[key] = {"label": label, "f_ghz": f, "s11_db": s11, "s21_db": s21,
                      "metrics": m, "params": e.get("params")}
        n += 1

    tgt = out_s2p("target.s2p")
    if os.path.exists(tgt):
        nw = rf.Network(tgt)
        ft = nw.f / 1e9
        t21 = _db(nw.s[:, 1, 0]); t11 = _db(nw.s[:, 0, 0])
        ax21.plot(ft, t21, label="ideal Chebyshev", color="gray", ls=":", lw=2.2)
        ax11.plot(ft, t11, label="ideal Chebyshev", color="gray", ls=":", lw=2.2)
        saved["ideal_chebyshev"] = {"label": "ideal Chebyshev",
                                    "f_ghz": list(ft), "s11_db": list(t11),
                                    "s21_db": list(t21)}

    for ax in (ax21, ax11):
        ax.axvspan(f0_ghz * (1 - fbw / 2), f0_ghz * (1 + fbw / 2), color="green", alpha=0.07)
        ax.grid(alpha=0.3)
    ax11.axhline(spec_db, color="gray", ls="--", lw=0.8)
    ax21.set_ylabel("|S21| (dB)"); ax21.set_ylim(-40, 3)
    ax11.set_ylabel("|S11| (dB)"); ax11.set_ylim(-40, 3)
    ax11.set_xlabel("Frequency (GHz)")
    ax21.legend(fontsize=8, loc="lower right")
    ax21.set_title(f"Fabrication variants vs ideal target ({n}/{len(variants)} available)")
    fig.tight_layout()
    img = out_img(f"{out_name}.png")
    fig.savefig(img, dpi=140)
    plt.close(fig)
    shutil.copy2(img, os.path.join(REPORT_DIR, f"{out_name}.png"))
    print(f"  {out_name}.png -> {REPORT_DIR}")

    datap = out_data(f"{out_name}_plotdata.json")
    json.dump(saved, open(datap, "w"), indent=2)
    print(f"  wrote {datap}")

    if rows:
        print(f"\n{'variant':38s} {'fc(GHz)':>8s} {'IL(dB)':>7s} {'BW(MHz)':>8s} {'S11w(dB)':>9s}")
        for label, fc, il, bw, s11w in rows:
            print(f"{label:38s} {fc:8.3f} {il:7.2f} {bw:8.0f} {s11w:9.2f}")
        if len(rows) >= 2:
            b = rows[0]
            print("\ndeltas vs the PEC reference:")
            for label, fc, il, bw, s11w in rows[1:]:
                print(f"  {label:36s} dIL={il - b[2]:+.2f}dB  dS11w={s11w - b[4]:+.2f}dB  "
                      f"dBW={bw - b[3]:+.0f}MHz  dfc={(fc - b[1]) * 1000:+.0f}MHz")
    return n > 0


def build_stackup_view(spec=None, out_name: str = "stackup",
                       mask_open_over_feed: bool = None) -> bool:
    """Cross-section of the real fabrication stack at the feed.

    Vertical scale is deliberately NON-linear (each layer gets comparable
    drawing height with its true thickness labelled): the substrate is
    760um while ENIG is 4.5um, so a true-to-scale drawing would render every
    finish layer as an invisible hairline. Draws both the masked feed and
    the mask-opened feed side by side, which is the actual fabrication
    decision this project has to make.
    """
    from .config import FilterSpec
    from .topologies.dualmode import JLCPCB_ENIG, JLCPCB_SOLDERMASK, JLCPCB_SILKSCREEN
    spec = spec or FilterSpec(N=2)
    sub = spec.substrate
    t_cu = sub.cu_thickness * 1e6

    # (label, thickness_um, colour, hatch)
    base = [
        (f"Rogers {sub.name.split('_')[0]}  eps_r={sub.eps_r}, tan_d={sub.tan_d}",
         sub.h * 1e6, "#c8b28a", None),
        (f"copper {t_cu:.1f}um ({sub.cu_oz}oz)  5.96e7 S/m", t_cu, "#b87333", None),
        (f"ENIG {JLCPCB_ENIG['enig_um']}um Ni-P  "
         f"{JLCPCB_ENIG['enig_conductivity_sm']:.2e} S/m", JLCPCB_ENIG["enig_um"],
         "#d4c47a", "//"),
    ]
    masked = base + [
        (f"soldermask {JLCPCB_SOLDERMASK['soldermask_um']}um  "
         f"eps_r={JLCPCB_SOLDERMASK['soldermask_eps_r']}",
         JLCPCB_SOLDERMASK["soldermask_um"], "#1b6b3a", None),
        (f"silkscreen {JLCPCB_SILKSCREEN['silkscreen_um']}um  "
         f"eps_r={JLCPCB_SILKSCREEN['silkscreen_eps_r']}",
         JLCPCB_SILKSCREEN["silkscreen_um"], "#f2f2f2", None),
    ]
    opened = base + [("(soldermask OPENED over the feed -- bare ENIG to air)",
                      0.0, None, None)]

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))
    for ax, (title, stack) in zip(axes, [
            ("Feed COVERED by soldermask\n(measured: S11w -12.5dB)", masked),
            ("Feed soldermask OPENED\n(recommended -- to be confirmed)", opened)]):
        y = 0.0
        for label, t_um, colour, hatch in stack:
            if colour is None:
                ax.text(0.5, y + 0.25, label, ha="center", va="bottom",
                        fontsize=9, style="italic", color="#555")
                continue
            h = 1.6 if t_um > 100 else 0.75      # non-linear: see docstring
            ax.add_patch(Rectangle((0, y), 1.0, h, facecolor=colour,
                                   edgecolor="black", lw=1.0, hatch=hatch))
            ax.text(1.04, y + h / 2, label, va="center", fontsize=8.5)
            y += h
        ax.add_patch(Rectangle((0, -0.75), 1.0, 0.75, facecolor="#b87333",
                               edgecolor="black", lw=1.0))
        ax.text(1.04, -0.375, f"bottom ground copper {t_cu:.1f}um", va="center", fontsize=8.5)
        ax.set_xlim(0, 2.6); ax.set_ylim(-1.1, y + 0.7)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=10)
    fig.suptitle("Fabrication stackup at the feed (vertical scale non-linear; "
                 "true thicknesses labelled)", fontsize=11)
    fig.tight_layout()
    img = out_img(f"{out_name}.png")
    fig.savefig(img, dpi=140)
    plt.close(fig)
    shutil.copy2(img, os.path.join(REPORT_DIR, f"{out_name}.png"))
    print(f"  {out_name}.png -> {REPORT_DIR}")
    return True


def build_stackup_topview(spec=None, out_name: str = "stackup_topview",
                          params: dict | None = None) -> bool:
    """TOP view of the board showing where each fabrication layer actually
    sits: soldermask + silkscreen coverage, the recommended mask OPENING
    over the CPWG feed / SMA launch, and the bare-ENIG copper it exposes.

    Reuses palace_dualmode_driven's pure-geometry helpers (the same ones the
    mesh builder and the existing layout drawing call), so the picture can
    not drift from what is simulated.
    """
    from matplotlib.patches import Circle, Polygon, Rectangle
    from .config import FilterSpec
    from .palace_dualmode_driven import _dims, _via_layout, feed_trace_poly
    from .topologies.dualmode import (A_SIW_MM, JLCPCB_SOLDERMASK,
                                      JLCPCB_SILKSCREEN, JLCPCB_ENIG)
    spec = spec or FilterSpec(N=2)
    p = params or dict(a=57.21, w_iris=15.26, x_iris=28.68, y_wall=8.62, w_ext=16.31)
    a = p["a"]
    W, Lt, Lf = _dims(a, None, None, None)
    Xf = Lt + Lf
    half = a / 2.0
    r = spec.d_via * 1e3 / 2.0
    final, x_iris = _via_layout(a, p["w_iris"], p["x_iris"], p["w_ext"],
                                spec.d_via * 1e3, spec.p_via * 1e3, p["y_wall"])
    ym = half + 3.0
    trace_in = feed_trace_poly(-Xf, -Lt, 0.0, W, -half, half)
    trace_out = feed_trace_poly(a + Xf, a + Lt, a, W, -half, half)

    fig, axes = plt.subplots(2, 1, figsize=(13, 8.5), sharex=True)
    for ax, open_mask in zip(axes, (False, True)):
        # board + soldermask coverage
        ax.add_patch(Rectangle((-Xf, -ym), a + 2 * Xf, 2 * ym, fc="#c8b28a",
                               ec="0.3", lw=1.0, zorder=0))
        if open_mask:
            # mask everywhere EXCEPT the two feed windows
            ax.add_patch(Rectangle((-Lt, -ym), a + 2 * Lt, 2 * ym, fc="#1b6b3a",
                                   ec="none", alpha=0.45, zorder=1))
            for x0 in (-Xf, a + Lt):
                ax.add_patch(Rectangle((x0, -ym), Xf - Lt, 2 * ym, fc="none",
                                       ec="#b00", lw=1.6, ls="--", zorder=4))
            ax.text(-Xf + (Xf - Lt) / 2, ym * 0.72, "MASK\nOPENING", ha="center",
                    va="center", fontsize=8, color="#b00", weight="bold", zorder=5)
            ax.text(a + Lt + (Xf - Lt) / 2, ym * 0.72, "MASK\nOPENING", ha="center",
                    va="center", fontsize=8, color="#b00", weight="bold", zorder=5)
        else:
            ax.add_patch(Rectangle((-Xf, -ym), a + 2 * Xf, 2 * ym, fc="#1b6b3a",
                                   ec="none", alpha=0.45, zorder=1))
        # cavity + copper
        ax.add_patch(Rectangle((0.0, -half), a, 2 * half, fc="#cfe8ff",
                               ec="0.4", alpha=0.45, zorder=2))
        for poly in (trace_in, trace_out):
            ax.add_patch(Polygon(poly, closed=True, fc="#d9a441", ec="#a06d12",
                                 lw=0.8, alpha=0.95, zorder=3))
        for (x, y) in final:
            internal = abs(x - x_iris) < 1e-6
            ax.add_patch(Circle((x, y), r, fc=("#b00" if internal else "#444"),
                                ec="none", zorder=4))
        # add_patch does NOT update the data limits, so without explicit
        # limits matplotlib keeps its default 0..1 x-range and the whole
        # board collapses to a sliver.
        ax.set_xlim(-Xf - 3, a + Xf + 3)
        ax.set_ylim(-ym - 2, ym + 7)
        ax.set_aspect("equal")
        ax.set_ylabel("y [mm]")
        ttl = ("SOLDERMASK OPENED over the feed  (recommended: exposes bare ENIG "
               "at the launch, where the detuning originates)"
               if open_mask else
               "SOLDERMASK + SILKSCREEN over the WHOLE board  "
               "(measured: S11w -12.5dB, misses the -16dB spec)")
        ax.set_title(ttl, fontsize=9.5)
    axes[-1].set_xlabel("x [mm]")
    fig.suptitle(
        f"Top view with fabrication stack -- green = soldermask "
        f"({JLCPCB_SOLDERMASK['soldermask_um']:.0f}um) + silkscreen "
        f"({JLCPCB_SILKSCREEN['silkscreen_um']:.0f}um);  gold = copper + ENIG "
        f"({JLCPCB_ENIG['enig_um']}um);  red vias = internal iris", fontsize=10)
    fig.tight_layout()
    img = out_img(f"{out_name}.png")
    fig.savefig(img, dpi=140)
    plt.close(fig)
    shutil.copy2(img, os.path.join(REPORT_DIR, f"{out_name}.png"))
    print(f"  {out_name}.png -> {REPORT_DIR}")
    return True


def sync_figs() -> list[str]:
    """Copy pipeline figures from output/imgs/ into the report folder."""
    copied = []
    for name in REPORT_FIGS:
        src = os.path.join(IMG_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(REPORT_DIR, name))
            copied.append(name)
            print(f"  copied {name}")
        else:
            print(f"  (skip {name} — not in output/imgs/, keeping report-folder copy)")
    return copied


def build_pdf() -> int:
    """Compile the report Markdown to PDF via the folder's gen_pdfs.py."""
    print(f"\nCompiling {REPORT_MD} ...")
    proc = subprocess.run(["uv", "run", "gen_pdfs.py", "--force", REPORT_MD], cwd=REPORT_DIR)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate report figures and PDF.")
    ap.add_argument("--no-build", action="store_true", help="figures only, skip the PDF")
    args = ap.parse_args(argv)

    print("Report stage:")
    finalize_palace_s2p()
    build_compare_final()
    build_cst_v2_compare()
    sync_figs()
    if args.no_build:
        return 0
    return build_pdf()


if __name__ == "__main__":
    sys.exit(main())
