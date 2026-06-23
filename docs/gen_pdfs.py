#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypandoc-binary>=1.13",
#     "cairosvg>=2.7",
# ]
# ///
"""Regenerate PDFs under the ``entregables/`` folder.

Walks the tree below this script's directory, converts any ``*.svg`` to
``*.pdf`` (when the PDF is missing or older than the SVG) and then
compiles each ``*.md`` to ``*.pdf`` with pandoc + xelatex. Each document
is built from its own directory so relative paths to logos and images
keep working.

Usage:
    # Local: rebuild every .md whose PDF is missing or stale.
    uv run entregables/gen_pdfs.py

    # Rebuild specific files (used by CI to render only what changed).
    uv run entregables/gen_pdfs.py entregables/10_05_26/foda.md

    # Force a full rebuild even if PDFs look up to date.
    uv run entregables/gen_pdfs.py --force

System requirements (xelatex emits the actual PDF):
- Linux   : `sudo apt install texlive-xetex texlive-fonts-recommended`
- macOS   : `brew install --cask mactex-no-gui`
- Windows : install MiKTeX (https://miktex.org/download) or TinyTeX
            (https://yihui.org/tinytex/). Both ship xelatex; MiKTeX
            additionally auto-installs missing LaTeX packages on demand.

Pandoc itself is pulled in as a Python dependency (``pypandoc-binary``),
so there is no separate install step for pandoc.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cairosvg
import pypandoc

ROOT = Path(__file__).resolve().parent


def convert_svgs() -> list[Path]:
    """Convert each ``*.svg`` to ``*.pdf`` if the PDF is missing or older.

    Returns the list of SVG-derived PDFs (used by the staleness check on
    Markdown files: if any logo PDF is newer than a document PDF, that
    document is considered stale).
    """
    svg_pdfs: list[Path] = []
    for svg in ROOT.rglob("*.svg"):
        pdf = svg.with_suffix(".pdf")
        svg_pdfs.append(pdf)
        if pdf.exists() and pdf.stat().st_mtime >= svg.stat().st_mtime:
            continue
        print(f"  svg  {svg.relative_to(ROOT)}  ->  {pdf.name}")
        cairosvg.svg2pdf(
            url=str(svg),
            write_to=str(pdf),
            output_width=400,
        )
    return svg_pdfs


def is_stale(md: Path, svg_pdfs: list[Path]) -> bool:
    """Return True if the .md's PDF is missing or older than its inputs."""
    pdf = md.with_suffix(".pdf")
    if not pdf.exists():
        return True
    pdf_mtime = pdf.stat().st_mtime
    if md.stat().st_mtime > pdf_mtime:
        return True
    return any(p.exists() and p.stat().st_mtime > pdf_mtime for p in svg_pdfs)


def render(md: Path, pandoc: str) -> bool:
    """Compile ``md`` to PDF next to it. Returns True on success."""
    pdf = md.with_suffix(".pdf")
    print(f"  md   {md.relative_to(ROOT)}  ->  {pdf.name}")
    proc = subprocess.run(
        [pandoc, md.name, "-o", pdf.name, "--pdf-engine=xelatex", "--citeproc"],
        cwd=md.parent,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"    [ERROR] pandoc failed:\n{proc.stderr}", file=sys.stderr)
        return False
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Specific .md files to render. Defaults to every .md under "
        "entregables/, skipping ones whose PDF is already up to date.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Render every .md, even if the PDF looks up to date.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    pandoc = pypandoc.get_pandoc_path()
    print(f"Pandoc: {pandoc}\n")

    print("Converting SVGs to PDF (if needed)...")
    svg_pdfs = convert_svgs()

    if args.files:
        targets = [p.resolve() for p in args.files]
        missing = [p for p in targets if not p.exists()]
        if missing:
            for p in missing:
                print(f"  [ERROR] not found: {p}", file=sys.stderr)
            return 2
        skipped = 0
    else:
        all_md = sorted(ROOT.rglob("*.md"))
        if args.force:
            targets = all_md
            skipped = 0
        else:
            targets = [m for m in all_md if is_stale(m, svg_pdfs)]
            skipped = len(all_md) - len(targets)

    if not targets:
        msg = "Nothing to do — all PDFs are up to date."
        if skipped:
            msg += f" ({skipped} file(s) up to date)"
        print(f"\n{msg}")
        return 0

    print(
        f"\nRendering {len(targets)} Markdown file(s)"
        + (f" (skipping {skipped} up to date)" if skipped else "")
        + ":\n"
    )
    ok = sum(render(md, pandoc) for md in targets)

    print(f"\nResult: {ok}/{len(targets)} PDFs generated.")
    return 0 if ok == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
