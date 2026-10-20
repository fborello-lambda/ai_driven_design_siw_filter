"""Cuadro 30 x 20 cm para la placa fabricada: bolsillo con la forma de la placa y texto abajo.

Genera, a escala 1:1 en milímetros:
  cuadro_its_a_band.svg  - archivo de corte/grabado (capas: guia_marco, corte_bolsillo, grabado_texto)
  cuadro_its_a_band.pdf  - el mismo SVG en PDF, para imprenta o láser
  cuadro_preview.png     - cómo se ve con la placa puesta (cobre dibujado desde el gerber real)
  cuadro_cotas.png       - plano con las medidas del bolsillo

Uso:  uv run --with cairosvg python docs/cuadro/make_cuadro.py
Las medidas de la placa salen del paquete de fabricación (docs/final_check/fab/);
las de los conectores SMA son estimadas: medirlas y ajustar SMA_* antes de cortar.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import Circle, PathPatch, Polygon, Rectangle  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from matplotlib.textpath import TextPath  # noqa: E402

HERE = Path(__file__).resolve().parent
FAB_ZIP = HERE.parent / "final_check" / "fab" / "siw_cascade_N3_jlcpcb.zip"

# ---- marco --------------------------------------------------------------------
FRAME_W, FRAME_H = 300.0, 200.0   # mm, apaisado (30 x 20 cm)
REBATE = 5.0                      # lo que tapa el marco en cada borde (solo guía)

# ---- placa (gerber Edge_Cuts) y conectores ------------------------------------
BOARD_W, BOARD_H = 165.78, 45.79  # mm
CLEAR = 0.5                       # holgura del bolsillo por lado
SMA_PROTRUDE = 10.0               # cuánto sobresale cada SMA del borde de la placa (MEDIR)
SMA_WIDTH = 8.0                   # ancho del cuerpo/hexágono del SMA (MEDIR)

# ---- texto ----------------------------------------------------------------------
TEXT = "it’s a band"
FONT = "/usr/share/fonts/truetype/lato/Lato-Light.ttf"
TEXT_W = 100.0                    # ancho del texto (mm)
GAP = 24.0                        # separación placa -> texto (mm)
OPTICAL_LIFT = 6.0                # el conjunto un poco por encima del centro

GERBER_X0 = -31.2003              # origen del gerber: borde izquierdo de la placa (mm)


# ---------------------------------------------------------------------------------
def text_path(s: str, width: float):
    """Texto -> contornos (curvas), escalado a `width` mm, con y hacia abajo (SVG)."""
    tp = TextPath((0, 0), s, size=10, prop=FontProperties(fname=FONT))
    ext = tp.get_extents()
    k = width / ext.width
    verts = [((x - ext.x0) * k, -(y - ext.y1) * k) for x, y in tp.vertices]
    return MPath(verts, tp.codes), ext.height * k


def path_to_svg_d(p: MPath, dx: float, dy: float) -> str:
    out, verts = [], p.vertices
    i = 0
    codes = p.codes
    while i < len(codes):
        c = codes[i]
        x, y = verts[i]
        if c == MPath.MOVETO:
            out.append(f"M{x + dx:.3f},{y + dy:.3f}")
            i += 1
        elif c == MPath.LINETO:
            out.append(f"L{x + dx:.3f},{y + dy:.3f}")
            i += 1
        elif c == MPath.CURVE3:
            (x1, y1), (x2, y2) = verts[i], verts[i + 1]
            out.append(f"Q{x1 + dx:.3f},{y1 + dy:.3f} {x2 + dx:.3f},{y2 + dy:.3f}")
            i += 2
        elif c == MPath.CURVE4:
            (x1, y1), (x2, y2), (x3, y3) = verts[i], verts[i + 1], verts[i + 2]
            out.append(f"C{x1 + dx:.3f},{y1 + dy:.3f} {x2 + dx:.3f},{y2 + dy:.3f} {x3 + dx:.3f},{y3 + dy:.3f}")
            i += 3
        else:  # CLOSEPOLY
            out.append("Z")
            i += 1
    return "".join(out)


def pocket_outline(x0: float, y0: float) -> list[tuple[float, float]]:
    """Contorno del bolsillo: placa + holgura, con las dos muescas de los SMA."""
    L, R = x0 - CLEAR, x0 + BOARD_W + CLEAR
    T, B = y0 - CLEAR, y0 + BOARD_H + CLEAR
    cy, hw = y0 + BOARD_H / 2, SMA_WIDTH / 2 + CLEAR
    return [(L, T), (R, T), (R, cy - hw), (R + SMA_PROTRUDE, cy - hw), (R + SMA_PROTRUDE, cy + hw),
            (R, cy + hw), (R, B), (L, B), (L, cy + hw), (L - SMA_PROTRUDE, cy + hw),
            (L - SMA_PROTRUDE, cy - hw), (L, cy - hw)]


def layout():
    tpath, text_h = text_path(TEXT, TEXT_W)
    group_h = BOARD_H + GAP + text_h
    board_x = (FRAME_W - BOARD_W) / 2
    board_y = (FRAME_H - group_h) / 2 - OPTICAL_LIFT
    text_x = (FRAME_W - TEXT_W) / 2
    text_y = board_y + BOARD_H + GAP
    return tpath, text_h, board_x, board_y, text_x, text_y


# ---------------------------------------------------------------------------------
def write_svg(path: Path) -> None:
    tpath, _, bx, by, tx, ty = layout()
    pts = " ".join(f"{x:.3f},{y:.3f}" for x, y in pocket_outline(bx, by))
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W}mm" height="{FRAME_H}mm" viewBox="0 0 {FRAME_W} {FRAME_H}">
  <!-- Escala 1:1, unidades en mm. Rojo fino = corte; negro relleno = grabado; gris punteado = guía (no cortar). -->
  <g id="guia_marco" fill="none" stroke="#999999" stroke-width="0.2">
    <rect x="0" y="0" width="{FRAME_W}" height="{FRAME_H}"/>
    <rect x="{REBATE}" y="{REBATE}" width="{FRAME_W - 2 * REBATE}" height="{FRAME_H - 2 * REBATE}" stroke-dasharray="2 2"/>
  </g>
  <g id="corte_bolsillo" fill="none" stroke="#ff0000" stroke-width="0.05">
    <polygon points="{pts}"/>
  </g>
  <g id="grabado_texto" fill="#000000" stroke="none">
    <path d="{path_to_svg_d(tpath, tx, ty)}"/>
  </g>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_pdf(svg: Path, pdf: Path) -> None:
    import cairosvg
    cairosvg.svg2pdf(url=str(svg), write_to=str(pdf))


# ---------------------------------------------------------------------------------
def read_gerber_copper():
    """Regiones (polígonos) y pads circulares del F_Cu, más los agujeros del PTH, en mm."""
    with zipfile.ZipFile(FAB_ZIP) as z:
        gtl = z.read("siw_cascade_N3-F_Cu.gtl").decode()
        drl = z.read("siw_cascade_N3-PTH.drl").decode()
    ap, cur, regions, pads, poly, in_region = {}, None, [], [], [], False
    for line in gtl.splitlines():
        if m := re.match(r"%ADD(\d+)C,([\d.]+)\*%", line):
            ap[m.group(1)] = float(m.group(2))
        elif m := re.match(r"D(\d+)\*$", line):
            cur = m.group(1)
        elif line.startswith("G36"):
            in_region, poly = True, []
        elif line.startswith("G37"):
            in_region = False
            regions.append(poly)
        elif m := re.match(r"X(-?\d+)Y(-?\d+)D0([123])\*", line):
            x, y, d = int(m.group(1)) / 1e6, int(m.group(2)) / 1e6, m.group(3)
            if in_region:
                poly.append((x, y))
            elif d == "3":
                pads.append((x, y, ap[cur]))
    tools, tool, holes = {}, None, []
    for line in drl.splitlines():
        if m := re.match(r"T(\d+)C([\d.]+)", line):
            tools[m.group(1)] = float(m.group(2))
        elif m := re.match(r"T(\d+)$", line):
            tool = m.group(1)
        elif m := re.match(r"X(-?[\d.]+)Y(-?[\d.]+)", line):
            holes.append((float(m.group(1)), float(m.group(2)), tools[tool]))
    return regions, pads, holes


def draw_board(ax, bx, by):
    """La placa en coordenadas del cuadro (y hacia abajo)."""
    regions, pads, holes = read_gerber_copper()
    to = lambda x, y: (bx + (x - GERBER_X0), by + BOARD_H / 2 - y)  # noqa: E731
    cy = by + BOARD_H / 2
    gold, sub = "#d6ae62", "#ecedde"
    for side in (-1, 1):   # SMA: cuerpo dorado + rosca
        x_edge = bx if side < 0 else bx + BOARD_W
        x0 = x_edge - SMA_PROTRUDE if side < 0 else x_edge
        ax.add_patch(Rectangle((x0, cy - SMA_WIDTH / 2), SMA_PROTRUDE, SMA_WIDTH, fc=gold, ec="#9c7a35", lw=0.4, zorder=3))
        for k in range(1, 6):
            xx = x0 + k * SMA_PROTRUDE / 6
            ax.plot([xx, xx], [cy - SMA_WIDTH / 2, cy + SMA_WIDTH / 2], color="#b18a43", lw=0.3, zorder=4)
    ax.add_patch(Rectangle((bx, by), BOARD_W, BOARD_H, fc=sub, ec="#c9cbb8", lw=0.4, zorder=3))
    for poly in regions:
        ax.add_patch(Polygon([to(x, y) for x, y in poly], closed=True, fc=gold, ec="none", zorder=4))
    for x, y, d in pads:
        ax.add_patch(Circle(to(x, y), d / 2, fc=gold, ec="none", zorder=4))
    for x, y, d in holes:
        ax.add_patch(Circle(to(x, y), d / 2, fc="#2b2b2b", ec="none", zorder=5))


def figure_base(dpi=200):
    fig = plt.figure(figsize=(FRAME_W / 25.4 * 0.5, FRAME_H / 25.4 * 0.5), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FRAME_W)
    ax.set_ylim(FRAME_H, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def write_preview(path: Path) -> None:
    tpath, _, bx, by, tx, ty = layout()
    fig, ax = figure_base()
    ax.add_patch(Rectangle((0, 0), FRAME_W, FRAME_H, fc="#1c1c1c", ec="none", zorder=0))          # marco
    ax.add_patch(Rectangle((REBATE, REBATE), FRAME_W - 2 * REBATE, FRAME_H - 2 * REBATE,
                           fc="#f4f1ea", ec="none", zorder=1))                                       # fondo
    sh = [(x + 0.8, y + 0.8) for x, y in pocket_outline(bx, by)]
    ax.add_patch(Polygon(sh, closed=True, fc="#00000022", ec="none", zorder=2))                      # sombra
    ax.add_patch(Polygon(pocket_outline(bx, by), closed=True, fc="#d9d4c7", ec="#bdb6a6", lw=0.4, zorder=2))
    draw_board(ax, bx, by)
    ax.add_patch(PathPatch(MPath(tpath.vertices + (tx, ty), tpath.codes), fc="#2a2a2a", ec="none", zorder=6))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def write_dims(path: Path) -> None:
    tpath, text_h, bx, by, tx, ty = layout()
    fig, ax = figure_base(dpi=220)
    ax.add_patch(Rectangle((0, 0), FRAME_W, FRAME_H, fc="white", ec="black", lw=0.6))
    ax.add_patch(Rectangle((REBATE, REBATE), FRAME_W - 2 * REBATE, FRAME_H - 2 * REBATE,
                           fc="none", ec="#999999", lw=0.5, ls=(0, (3, 3))))
    ax.add_patch(Polygon(pocket_outline(bx, by), closed=True, fc="none", ec="red", lw=0.8))
    ax.add_patch(PathPatch(MPath(tpath.vertices + (tx, ty), tpath.codes), fc="black", ec="none"))
    kw = dict(fontsize=5.5, color="#333333", ha="center", va="center")

    def dim(x0, y0, x1, y1, label, off=(0, -2.5), rot=0):
        ax.annotate("", (x0, y0), (x1, y1), arrowprops=dict(arrowstyle="<->", lw=0.5, color="#333333"))
        ax.text((x0 + x1) / 2 + off[0], (y0 + y1) / 2 + off[1], label, rotation=rot, **kw)

    L, R = bx - CLEAR, bx + BOARD_W + CLEAR
    T, B = by - CLEAR, by + BOARD_H + CLEAR
    cy = by + BOARD_H / 2
    dim(L, T - 5, R, T - 5, f"{BOARD_W + 2 * CLEAR:.2f} mm (placa {BOARD_W} + holgura {CLEAR} por lado)")
    dim(L - SMA_PROTRUDE, T - 13, R + SMA_PROTRUDE, T - 13,
        f"{BOARD_W + 2 * CLEAR + 2 * SMA_PROTRUDE:.2f} mm con los SMA")
    dim(R + 18, T, R + 18, B, f"{BOARD_H + 2 * CLEAR:.2f} mm", off=(4, 0), rot=90)
    dim(R + 34, 0, R + 34, T, f"{T:.1f}", off=(4, 0), rot=90)
    dim(0, B - 6, L, B - 6, f"{L:.1f}", off=(0, -2.5))
    dim(tx + TEXT_W / 2, B, tx + TEXT_W / 2, ty, f"{ty - B:.1f}", off=(4, 0), rot=90)
    dim(tx, ty + text_h + 5, tx + TEXT_W, ty + text_h + 5, f"texto {TEXT_W:.0f} x {text_h:.1f} mm", off=(0, 3))
    ax.text(R + 26, cy + 2, f"muesca SMA\n{SMA_PROTRUDE:.0f} x {SMA_WIDTH + 2 * CLEAR:.0f} mm\n(medir el conector)",
            fontsize=5, ha="left", va="center", color="#aa0000")
    ax.text(FRAME_W / 2, FRAME_H - 2.2, "rojo: corte del bolsillo  ·  gris punteado: lo que tapa el marco  ·  medidas en mm",
            fontsize=5, ha="center", color="#666666")
    fig.savefig(path, dpi=220)
    plt.close(fig)


def main() -> None:
    svg = HERE / "cuadro_its_a_band.svg"
    write_svg(svg)
    write_pdf(svg, HERE / "cuadro_its_a_band.pdf")
    write_preview(HERE / "cuadro_preview.png")
    write_dims(HERE / "cuadro_cotas.png")
    _, text_h, bx, by, tx, ty = layout()
    print(f"placa en x={bx:.2f}..{bx + BOARD_W:.2f}, y={by:.2f}..{by + BOARD_H:.2f} mm; "
          f"texto {TEXT_W:.0f} x {text_h:.1f} mm en y={ty:.2f}")


if __name__ == "__main__":
    main()
