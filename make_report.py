#!/usr/bin/env python
"""Sync the pipeline figures into v1_data/ and (re)compile the IEEE report PDF.

The Python pipeline writes figures to ``output/imgs/`` (see config.py), but the
report (``v1_data/Anteproyecto_Filtro_SIW_287GHz.md``) embeds images by bare
filename from its own directory. This script copies the report's
pipeline-generated figures from ``output/imgs/`` into ``v1_data/`` and then runs
``gen_pdfs.py`` to rebuild the PDF.

Static figures (CST screenshots: above/up/height_and_plane/s11/s21.jpeg) and the
logo live in ``v1_data/`` already and are left untouched.

Run:  uv run python make_report.py            # sync + compile
      uv run python make_report.py --no-build # only copy the figures
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from config import OUTPUT_DIR

_ROOT = os.path.dirname(os.path.abspath(__file__))
V1_DATA = os.path.join(_ROOT, "v1_data")
IMG_DIR = os.path.join(OUTPUT_DIR, "imgs")

# Figures the report embeds that are produced by the Python pipeline.
# (compare_all.png is produced by the ad-hoc L_cav sweep; copied if present.)
REPORT_FIGS = ["layout.png", "compare.png", "compare_all.png"]


def sync_figs() -> list[str]:
    copied = []
    for name in REPORT_FIGS:
        src = os.path.join(IMG_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(V1_DATA, name))
            copied.append(name)
            print(f"  copied {name}")
        else:
            print(f"  (skip {name} — not in output/imgs/, keeping v1_data copy)")
    return copied


def build_pdf() -> int:
    md = "Anteproyecto_Filtro_SIW_287GHz.md"
    print(f"\nCompiling {md} ...")
    # gen_pdfs.py declares its own inline deps (pypandoc, cairosvg) -> run via uv.
    proc = subprocess.run(["uv", "run", "gen_pdfs.py", "--force", md], cwd=V1_DATA)
    return proc.returncode


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true",
                    help="only copy figures, do not compile the PDF")
    args = ap.parse_args()

    print("Syncing report figures output/imgs/ -> v1_data/ :")
    sync_figs()
    if not args.no_build:
        rc = build_pdf()
        sys.exit(rc)
