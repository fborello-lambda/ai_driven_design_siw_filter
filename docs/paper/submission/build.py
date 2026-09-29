"""Build the submission sources of the English paper from the Markdown draft.

    uv run python docs/paper/submission/build.py arxiv    # default
    uv run python docs/paper/submission/build.py access

docs/paper/ai_driven_rf_design.md stays the single source. The script converts
its body to LaTeX with pandoc (citations -> \\cite, BibTeX + IEEEtran.bst),
fills a front-matter template, compiles with pdflatex + bibtex, and writes:

  arxiv   standard IEEEtran journal class (arXiv compiles it natively).
          build_arxiv/ holds main.tex, main.bbl, figures, references.bib;
          arxiv_submission.tar.gz is the file to upload.
  access  official IEEE Access template (downloaded into ./template/, not
          committed) -> ai_driven_rf_design_ieee_access.pdf + access.tex.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
MD = PAPER / "ai_driven_rf_design.md"
TPL_URL = ("https://ieeeaccess.ieee.org/wp-content/uploads/2026/05/"
           "ACCESS_latex_template_20260513-1-1.zip")
TPL = HERE / "template"
TARGETS = {
    "arxiv": dict(front="front_matter_arxiv.tex", build=HERE / "build_arxiv",
                  stem="main", pdf=PAPER / "ai_driven_rf_design_arxiv.pdf"),
    "access": dict(front="front_matter_access.tex", build=HERE / "build",
                   stem="access", pdf=PAPER / "ai_driven_rf_design_ieee_access.pdf"),
}

# pdflatex + ieeeaccess.cls: map the Unicode the Markdown uses.
UNICODE = {
    "−": r"\ensuremath{-}", "≤": r"\ensuremath{\le}", "≥": r"\ensuremath{\ge}",
    "×": r"\ensuremath{\times}", "≈": r"\ensuremath{\approx}",
    "µ": r"\ensuremath{\mu}", "Ω": r"\ensuremath{\Omega}",
    "→": r"\ensuremath{\rightarrow}", "δ": r"\ensuremath{\delta}",
    "ε": r"\ensuremath{\varepsilon}", "±": r"\ensuremath{\pm}",
    "⁻": r"\ensuremath{^{-}}", "⁹": r"\ensuremath{^{9}}", "°": r"\ensuremath{^\circ}",
    "…": r"\ldots{}", "–": "--", "—": "---", "’": "'", "“": "``", "”": "''",
    "é": r"\'e", "ó": r"\'o", "á": r"\'a", "í": r"\'i", "ç": r"\c{c}",
}


def fetch_template() -> Path:
    cls = next(TPL.rglob("ieeeaccess.cls"), None)
    if cls:
        return cls.parent
    TPL.mkdir(parents=True, exist_ok=True)
    z = TPL / "template.zip"
    print("downloading IEEE Access template ...")
    subprocess.run(["curl", "-fsSL", "-o", str(z), TPL_URL], check=True)
    zipfile.ZipFile(z).extractall(TPL)
    z.unlink()
    return next(TPL.rglob("ieeeaccess.cls")).parent


def md_body() -> str:
    """Markdown body (no YAML) -> LaTeX, with IEEE-style \\cite."""
    text = MD.read_text()
    body = text.split("\n---\n", 1)[1]              # drop YAML front matter
    # keywords/acknowledgment/references are rebuilt by the template
    body = re.sub(r"```\{=latex\}\n\\begin\{IEEEkeywords\}.*?```\n", "", body, flags=re.S)
    body = body.split("\n# Acknowledgment {-}")[0]
    tex = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "latex", "--natbib", "--wrap=preserve"],
        input=body, capture_output=True, text=True, check=True).stdout
    tex = re.sub(r"\\cite[pt]\{", r"\\cite{", tex)
    tex = tex.replace("\\tightlist\n", "")
    # pandoc's \pandocbounded wrappers are not defined in the IEEE preamble
    tex = re.sub(r"\\pandocbounded\{(.*?)\}\n", r"\1\n", tex)
    for k, v in UNICODE.items():
        tex = tex.replace(k, v)
    # first paragraph of the introduction gets the IEEE drop cap
    tex = re.sub(r"(\\section\{Introduction\}\\label\{[^}]*\}\n\n)(\w)(\w+)",
                 lambda m: f"{m.group(1)}\\PARstart{{{m.group(2)}}}{{{m.group(3)}}}",
                 tex, count=1)
    return tex


def _uni(t: str) -> str:
    for k, v in UNICODE.items():
        t = t.replace(k, v)
    return t


def yaml_meta() -> dict:
    """Title, abstract and keywords from the Markdown's YAML/keywords block."""
    text = MD.read_text()
    yml = text.split("\n---\n", 1)[0]
    title = re.search(r"title: >-\n((?:  .*\n)+)", yml).group(1)
    abstract = re.search(r"abstract: \|\n((?:  .*\n)+)", yml).group(1)
    kw = re.search(r"\\begin\{IEEEkeywords\}\n(.*?)\\end\{IEEEkeywords\}", text, re.S).group(1)
    words = len(abstract.split())
    if not 150 <= words <= 250:
        print(f"WARNING: abstract is {words} words (IEEE Access requires 150-250)")
    kws = sorted({k.strip().rstrip(".") for k in kw.replace("\n", " ").split(",") if k.strip()},
                 key=str.lower)
    return {"title": " ".join(title.split()), "abstract": _uni(" ".join(abstract.split())),
            "keywords": ", ".join(kws) + "."}


def acknowledgment() -> str:
    text = MD.read_text()
    ack = text.split("# Acknowledgment {-}", 1)[1].split("```{=latex}")[0]
    ack = re.sub(r"\s*\[@[^\]]+\]", r"~\\cite{ieee_ai_policy}", ack.strip())
    for k, v in UNICODE.items():
        ack = ack.replace(k, v)
    return ack


def main(target: str = "arxiv") -> None:
    cfg = TARGETS[target]
    build, stem = cfg["build"], cfg["stem"]
    if build.exists():
        shutil.rmtree(build)
    if target == "access":
        tpl = fetch_template()
        shutil.copytree(tpl, build, ignore=shutil.ignore_patterns("access.*", "*.png"))
        for f in ("logo.png", "notaglinelogo.png", "bullet.png"):
            if (tpl / f).exists():
                shutil.copy2(tpl / f, build / f)
    else:
        build.mkdir(parents=True)
    shutil.copytree(PAPER / "figures", build / "figures",
                    ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    shutil.copy2(PAPER / "references.bib", build / "references.bib")

    front = (HERE / cfg["front"]).read_text()
    meta = yaml_meta()
    front = (front.replace("%%TITLE%%", meta["title"])
                  .replace("%%ABSTRACT%%", meta["abstract"])
                  .replace("%%KEYWORDS%%", meta["keywords"]))
    preamble, back = front.split("%%BODY%%")
    tex = (preamble + md_body()
           + "\n\\section*{Acknowledgment}\n" + acknowledgment() + "\n\n"
           + back)
    (build / f"{stem}.tex").write_text(tex)

    def run(*cmd):
        return subprocess.run(cmd, cwd=build, capture_output=True, text=True,
                              errors="replace")
    run("pdflatex", "-interaction=nonstopmode", f"{stem}.tex")
    run("bibtex", stem)
    run("pdflatex", "-interaction=nonstopmode", f"{stem}.tex")
    run("pdflatex", "-interaction=nonstopmode", f"{stem}.tex")
    log = (build / f"{stem}.log").read_text(errors="replace")
    errs = [ln for ln in log.splitlines() if ln.startswith("!")]
    undef = sorted(set(re.findall(r"Citation `([^']+)' .*undefined", log)))
    missing_glyph = sorted(set(re.findall(r"Missing character: There is no (\S+)", log)))
    if errs:
        print("LaTeX errors:\n  " + "\n  ".join(errs[:10]))
    if undef:
        print("undefined citations:", undef)
    if missing_glyph:
        print("missing glyphs:", missing_glyph)
    pdf = build / f"{stem}.pdf"
    if not pdf.exists():
        raise SystemExit("no PDF produced; see " + str(build / f"{stem}.log"))
    shutil.copy2(pdf, cfg["pdf"])
    pages = re.search(r"Output written on \S+ \((\d+) pages", log)
    print(f"wrote {cfg['pdf']} ({pages.group(1) if pages else '?'} pages)")
    if target == "arxiv":
        tar = HERE / "arxiv_submission.tar.gz"
        files = [f"{stem}.tex", f"{stem}.bbl", "references.bib", "figures"]
        subprocess.run(["tar", "czf", str(tar), *files], cwd=build, check=True)
        print(f"wrote {tar}")
    else:
        shutil.copy2(build / f"{stem}.tex", HERE / f"{stem}.tex")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "arxiv")
