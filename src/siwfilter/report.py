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

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
