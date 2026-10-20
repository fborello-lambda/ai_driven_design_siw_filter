"""Cuadro 30 x 20 cm para dos placas fabricadas, sin conectores: arriba una mostrando el frente
(F_Cu) y abajo otra mostrando el dorso (B_Cu); debajo, el texto y las curvas simulada
(izquierda) y medida (derecha) de 0 a 4 GHz.

Genera, a escala 1:1 en milímetros:
  cuadro_its_a_band.svg   - archivo completo para láser (capas: guia_marco, corte_bolsillos, grabado)
  cuadro_its_a_band.pdf   - el mismo, en PDF
  cuadro_impresion.pdf    - solo el arte (texto y curvas), sin líneas de corte ni guía: para imprenta
  cuadro_preview.png      - cómo se ve con las placas puestas (cobre dibujado desde los gerbers reales)
  cuadro_cotas.png        - plano con las medidas

Uso:  uv run --with cairosvg python docs/cuadro/make_cuadro.py

Datos de las curvas (los mismos que usan los informes, vía siwfilter.measure):
  simulada: Palace; en 2.72-3.02 GHz la malla fina de la geometría fabricada, fuera de ese
            rango el barrido 0-8 GHz (geometría previa al recorte de 0.3 mm; en la unión las
            dos difieren menos de 1 dB).
  medida:   VNA, placa con los conectores soldados, calibración del instrumento.
Las medidas de la placa salen del paquete de fabricación (docs/final_check/fab/).
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import matplotlib
import numpy as np

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
SIDE = 15.0                       # margen lateral del contenido desde el borde

# ---- placas (gerber Edge_Cuts), sin conectores -----------------------------------
BOARD_W, BOARD_H = 165.78, 45.79  # mm
CLEAR = 0.5                       # holgura del bolsillo por lado
BOARD_GAP = 8.0                   # separación entre la placa del frente y la del dorso

# ---- textos ---------------------------------------------------------------------
TEXT = "it’s a band"
SUBTITLE = "SIW bandpass filter · 2.87 GHz"
FONT = "/usr/share/fonts/truetype/lato/Lato-Light.ttf"
FONT_REG = "/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
TEXT_W = 90.0                     # ancho del texto principal (mm)
SUB_H = 3.4                       # altura de mayúscula del subtítulo (mm)
SUB_GAP = 6.0                     # texto -> subtítulo

# ---- curvas ---------------------------------------------------------------------
PLOT_W, PLOT_H = 76.0, 52.0       # bloque de cada gráfico, con título y rótulos (mm)
F_MAX = 4.0                       # GHz
DB_MIN = -80.0
LABEL_H = 2.2                     # altura de los números de los ejes (mm)
INK, INK2 = "#1a1a1a", "#8a8a8a"  # |S21| y |S11|
MEAS_STEP = 4                     # la medición tiene 10 001 puntos; se dibuja 1 de cada 4

GAP = 13.0                        # placa del dorso -> fila de abajo
OPTICAL_LIFT = 0.0                # el conjunto ya llena el alto: centrado
GERBER_X0 = -31.2003              # origen del gerber: borde izquierdo de la placa (mm)


# ---------------------------------------------------------------------------------
# texto -> contornos
# ---------------------------------------------------------------------------------
def text_path(s: str, *, width: float | None = None, cap: float | None = None, font: str = FONT):
    """Texto como contornos en mm, y hacia abajo, origen arriba a la izquierda del bloque.
    Se fija el ancho total o la altura de mayúscula. Devuelve (path, ancho, alto)."""
    prop = FontProperties(fname=font)
    tp = TextPath((0, 0), s, size=10, prop=prop)
    ext = tp.get_extents()
    if width is not None:
        k = width / ext.width
    else:
        k = cap / TextPath((0, 0), "H", size=10, prop=prop).get_extents().height
    v = np.column_stack([(tp.vertices[:, 0] - ext.x0) * k, -(tp.vertices[:, 1] - ext.y1) * k])
    return MPath(v, tp.codes), ext.width * k, ext.height * k


def place(p: MPath, x: float, y: float) -> MPath:
    return MPath(p.vertices + (x, y), p.codes)


def path_d(p: MPath) -> str:
    out, v, codes, i = [], p.vertices, p.codes, 0
    while i < len(codes):
        c = codes[i]
        if c == MPath.MOVETO:
            out.append("M%.3f,%.3f" % tuple(v[i])); i += 1
        elif c == MPath.LINETO:
            out.append("L%.3f,%.3f" % tuple(v[i])); i += 1
        elif c == MPath.CURVE3:
            out.append("Q%.3f,%.3f %.3f,%.3f" % (*v[i], *v[i + 1])); i += 2
        elif c == MPath.CURVE4:
            out.append("C%.3f,%.3f %.3f,%.3f %.3f,%.3f" % (*v[i], *v[i + 1], *v[i + 2])); i += 3
        else:
            out.append("Z"); i += 1
    return "".join(out)


# ---------------------------------------------------------------------------------
# datos
# ---------------------------------------------------------------------------------
def load_curves():
    from siwfilter import measure as m
    bb = json.load(open(m.DEFAULT_PALACE_BB))
    fine = json.load(open(m.DEFAULT_PALACE))
    fb, ff = np.array(bb["f_ghz"]), np.array(fine["f_ghz"])
    out = (fb < ff[0]) | (fb > ff[-1])
    f_sim = np.concatenate([fb[out & (fb < ff[0])], ff, fb[out & (fb > ff[-1])]])
    sim = {k: np.concatenate([np.array(bb[k])[out & (fb < ff[0])], np.array(fine[k]),
                              np.array(bb[k])[out & (fb > ff[-1])]]) for k in ("s21_db", "s11_db")}
    n = m.load_dataset().dut["SC"]
    k = slice(None, None, MEAS_STEP)   # uno de cada MEAS_STEP puntos: menos tinta, mismos datos
    f_meas = n.f[k] / 1e9
    meas = {"s21_db": 20 * np.log10(np.abs(n.s[k, 1, 0])), "s11_db": 20 * np.log10(np.abs(n.s[k, 0, 0]))}
    return (f_sim, sim), (f_meas, meas)


# ---------------------------------------------------------------------------------
# geometría: una lista de primitivas que dibujan igual el SVG y la vista previa
# ---------------------------------------------------------------------------------
def pocket_outline(x0: float, y0: float) -> list[tuple[float, float]]:
    """Contorno de un bolsillo: la placa (sin conectores) más la holgura."""
    L, R = x0 - CLEAR, x0 + BOARD_W + CLEAR
    T, B = y0 - CLEAR, y0 + BOARD_H + CLEAR
    return [(L, T), (R, T), (R, B), (L, B)]


def plot_block(x0, y0, title, f, d, lw_scale=1.0):
    """Primitivas de un gráfico |S21| / |S11| vs. frecuencia en el bloque (x0, y0, PLOT_W, PLOT_H).
    `lw_scale` afina las curvas densas (la medición tiene 10 001 puntos y mucho ruido abajo)."""
    prims = []
    tp, tw, th = text_path(title, cap=3.0)
    prims.append(("text", place(tp, x0 + (PLOT_W - tw) / 2 + 4, y0), INK))
    ax_l, ax_r = x0 + 9.0, x0 + PLOT_W - 1.0
    ax_t, ax_b = y0 + th + 5.0, y0 + PLOT_H - 6.5
    X = lambda g: ax_l + (ax_r - ax_l) * g / F_MAX            # noqa: E731
    Y = lambda db: ax_t + (ax_b - ax_t) * (-db) / (-DB_MIN)    # noqa: E731
    lw_ax = 0.18
    prims.append(("line", [[(ax_l, ax_t), (ax_l, ax_b), (ax_r, ax_b)]], lw_ax, INK, None))
    for g in range(int(F_MAX) + 1):
        prims.append(("line", [[(X(g), ax_b), (X(g), ax_b + 1.0)]], lw_ax, INK, None))
        p, w, _ = text_path(str(g), cap=LABEL_H)
        prims.append(("text", place(p, X(g) - w / 2, ax_b + 1.8), INK))
    p, w, _ = text_path("GHz", cap=LABEL_H)
    prims.append(("text", place(p, ax_r - w, ax_b + 1.8 + LABEL_H + 1.4), INK))
    for db in range(0, int(DB_MIN) - 1, -20):
        prims.append(("line", [[(ax_l - 1.0, Y(db)), (ax_l, Y(db))]], lw_ax, INK, None))
        p, w, h = text_path(str(db).replace("-", "−"), cap=LABEL_H)
        prims.append(("text", place(p, ax_l - 1.8 - w, Y(db) - h / 2), INK))
    p, w, _ = text_path("dB", cap=LABEL_H)
    prims.append(("text", place(p, ax_l - 1.8 - w, ax_t - LABEL_H - 3.2), INK))
    for key, color, lw in (("s11_db", INK2, 0.22), ("s21_db", INK, 0.30)):
        segs, cur = [], []
        for fi, yi in zip(f, d[key]):
            if fi > F_MAX:
                break
            if yi >= DB_MIN:
                cur.append((X(fi), Y(min(yi, 0.0))))
            elif cur:
                segs.append(cur); cur = []
        if cur:
            segs.append(cur)
        prims.append(("line", [s for s in segs if len(s) > 1], lw * lw_scale, color, None))
    # rótulos directos: S21 cerca del pico de la banda, S11 en la parte de arriba
    for lab, color, gx, db in (("21", INK, 3.42, -25.0), ("11", INK2, 3.55, -8.0)):
        p, w, h = text_path("S", cap=LABEL_H * 1.1, font=FONT_REG)
        q, w2, _ = text_path(lab, cap=LABEL_H * 0.75, font=FONT_REG)
        prims.append(("text", place(p, X(gx), Y(db)), color))
        prims.append(("text", place(q, X(gx) + w + 0.3, Y(db) + h * 0.55), color))
    return prims


def layout():
    main, main_w, main_h = text_path(TEXT, width=TEXT_W)
    sub, sub_w, sub_h = text_path(SUBTITLE, cap=SUB_H)
    pocket_h = BOARD_H + 2 * CLEAR
    total = 2 * pocket_h + BOARD_GAP + GAP + PLOT_H
    top = (FRAME_H - total) / 2 - OPTICAL_LIFT
    bx, by = (FRAME_W - BOARD_W) / 2, top + CLEAR                 # placa del frente
    by2 = by + pocket_h + BOARD_GAP                                # placa del dorso
    row_y = top + 2 * pocket_h + BOARD_GAP + GAP
    text_block = main_h + SUB_GAP + sub_h
    ty = row_y + (PLOT_H - text_block) / 2 + 2.0
    return dict(main=place(main, (FRAME_W - main_w) / 2, ty), main_box=((FRAME_W - main_w) / 2, ty, main_w, main_h),
                sub=place(sub, (FRAME_W - sub_w) / 2, ty + main_h + SUB_GAP),
                sub_box=((FRAME_W - sub_w) / 2, ty + main_h + SUB_GAP, sub_w, sub_h),
                bx=bx, by=by, by2=by2, row_y=row_y, left_x=SIDE, right_x=FRAME_W - SIDE - PLOT_W)


def primitives():
    L = layout()
    (fs, sim), (fm, meas) = load_curves()
    art = [("text", L["main"], INK), ("text", L["sub"], INK)]
    art += plot_block(L["left_x"], L["row_y"], "simulated", fs, sim)
    art += plot_block(L["right_x"], L["row_y"], "measured", fm, meas, lw_scale=0.6)
    return L, art


# ---------------------------------------------------------------------------------
# SVG / PDF
# ---------------------------------------------------------------------------------
def svg_art(art) -> str:
    out = []
    for p in art:
        if p[0] == "text":
            out.append(f'    <path d="{path_d(p[1])}" fill="{p[2]}"/>')
        else:
            _, segs, lw, color, _ = p
            for s in segs:
                pts = " ".join("%.3f,%.3f" % xy for xy in s)
                out.append(f'    <polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{lw}" '
                           f'stroke-linejoin="round" stroke-linecap="round"/>')
    return "\n".join(out)


def write_svg(path: Path, L, art, *, cut: bool = True) -> None:
    polys = "\n".join('    <polygon points="%s"/>' % " ".join("%.3f,%.3f" % xy for xy in pocket_outline(L["bx"], y))
                      for y in (L["by"], L["by2"]))
    guide = cut_layer = ""
    if cut:
        guide = f"""  <g id="guia_marco" fill="none" stroke="#999999" stroke-width="0.2">
    <rect x="0" y="0" width="{FRAME_W}" height="{FRAME_H}"/>
    <rect x="{REBATE}" y="{REBATE}" width="{FRAME_W - 2 * REBATE}" height="{FRAME_H - 2 * REBATE}" stroke-dasharray="2 2"/>
  </g>
"""
        cut_layer = f"""  <g id="corte_bolsillos" fill="none" stroke="#ff0000" stroke-width="0.05">
{polys}
  </g>
"""
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W}mm" height="{FRAME_H}mm" viewBox="0 0 {FRAME_W} {FRAME_H}">
  <!-- Escala 1:1, unidades en mm. Rojo fino = corte; negro/gris = grabado o impresión; gris punteado = guía (no cortar). -->
{guide}{cut_layer}  <g id="grabado">
{svg_art(art)}
  </g>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_pdf(svg: Path, pdf: Path) -> None:
    import cairosvg
    cairosvg.svg2pdf(url=str(svg), write_to=str(pdf))


# ---------------------------------------------------------------------------------
# vista previa y cotas (matplotlib, mismas primitivas)
# ---------------------------------------------------------------------------------
def read_gerber_copper(layer: str = "F_Cu"):
    """Regiones (polígonos) y pads circulares de una capa de cobre, más los agujeros del PTH, en mm."""
    name = {"F_Cu": "siw_cascade_N3-F_Cu.gtl", "B_Cu": "siw_cascade_N3-B_Cu.gbl"}[layer]
    with zipfile.ZipFile(FAB_ZIP) as z:
        gtl = z.read(name).decode()
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


def draw_board(ax, bx, by, layer: str = "F_Cu"):
    """Una placa vista desde su cara `layer`. El dorso se ve dada vuelta sobre el eje largo
    (espejo en y); como la placa es simétrica, la vista no cambia, pero queda bien orientada."""
    regions, pads, holes = read_gerber_copper(layer)
    sgn = -1 if layer == "F_Cu" else 1
    to = lambda x, y: (bx + (x - GERBER_X0), by + BOARD_H / 2 + sgn * y)  # noqa: E731
    gold, sub = "#d6ae62", "#ecedde"
    ax.add_patch(Rectangle((bx, by), BOARD_W, BOARD_H, fc=sub, ec="#c9cbb8", lw=0.4, zorder=3))
    for poly in regions:
        ax.add_patch(Polygon([to(x, y) for x, y in poly], closed=True, fc=gold, ec="none", zorder=4))
    for x, y, d in pads:
        ax.add_patch(Circle(to(x, y), d / 2, fc=gold, ec="none", zorder=4))
    for x, y, d in holes:
        ax.add_patch(Circle(to(x, y), d / 2, fc="#2b2b2b", ec="none", zorder=5))


SCALE = 0.5                     # figura a media escala: 1 mm = 0.5 * 72 / 25.4 pt
PT_PER_MM = SCALE * 72 / 25.4


def figure_base(dpi=200):
    fig = plt.figure(figsize=(FRAME_W / 25.4 * SCALE, FRAME_H / 25.4 * SCALE), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FRAME_W)
    ax.set_ylim(FRAME_H, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def draw_art(ax, art, z=6):
    for p in art:
        if p[0] == "text":
            ax.add_patch(PathPatch(p[1], fc=p[2], ec="none", zorder=z))
        else:
            _, segs, lw, color, _ = p
            for s in segs:
                a = np.asarray(s)
                ax.plot(a[:, 0], a[:, 1], color=color, lw=lw * PT_PER_MM, solid_joinstyle="round", zorder=z)


def write_preview(path: Path, L, art) -> None:
    fig, ax = figure_base(dpi=240)
    ax.add_patch(Rectangle((0, 0), FRAME_W, FRAME_H, fc="#1c1c1c", ec="none", zorder=0))
    ax.add_patch(Rectangle((REBATE, REBATE), FRAME_W - 2 * REBATE, FRAME_H - 2 * REBATE, fc="#f4f1ea", ec="none", zorder=1))
    for y, layer in ((L["by"], "F_Cu"), (L["by2"], "B_Cu")):
        sh = [(x + 0.8, yy + 0.8) for x, yy in pocket_outline(L["bx"], y)]
        ax.add_patch(Polygon(sh, closed=True, fc="#00000022", ec="none", zorder=2))
        ax.add_patch(Polygon(pocket_outline(L["bx"], y), closed=True, fc="#d9d4c7", ec="#bdb6a6", lw=0.4, zorder=2))
        draw_board(ax, L["bx"], y, layer)
    draw_art(ax, art)
    fig.savefig(path, dpi=240)
    plt.close(fig)


def write_dims(path: Path, L, art) -> None:
    fig, ax = figure_base(dpi=220)
    ax.add_patch(Rectangle((0, 0), FRAME_W, FRAME_H, fc="white", ec="black", lw=0.6))
    ax.add_patch(Rectangle((REBATE, REBATE), FRAME_W - 2 * REBATE, FRAME_H - 2 * REBATE,
                           fc="none", ec="#999999", lw=0.5, ls=(0, (3, 3))))
    for y in (L["by"], L["by2"]):
        ax.add_patch(Polygon(pocket_outline(L["bx"], y), closed=True, fc="none", ec="red", lw=0.8))
    draw_art(ax, art, z=3)
    blue = "#0b5394"
    kw = dict(fontsize=5.0, color=blue, ha="center", va="center")

    def dim(x0, y0, x1, y1, label, off=(0, -2.5), rot=0):
        ax.annotate("", (x0, y0), (x1, y1), arrowprops=dict(arrowstyle="<->", lw=0.5, color=blue))
        ax.text((x0 + x1) / 2 + off[0], (y0 + y1) / 2 + off[1], label, rotation=rot, **kw)

    bx = L["bx"]
    Lx, R = bx - CLEAR, bx + BOARD_W + CLEAR
    T1, B1 = L["by"] - CLEAR, L["by"] + BOARD_H + CLEAR
    T2, B2 = L["by2"] - CLEAR, L["by2"] + BOARD_H + CLEAR
    dim(Lx, (T1 + B1) / 2, R, (T1 + B1) / 2, f"{BOARD_W + 2 * CLEAR:.2f} (placa {BOARD_W} + holgura {CLEAR} por lado)")
    ax.text((Lx + R) / 2, (T1 + B1) / 2 + 4, "frente (F_Cu)", fontsize=5, ha="center", color="#aa0000")
    ax.text((Lx + R) / 2, (T2 + B2) / 2, "dorso (B_Cu)", fontsize=5, ha="center", color="#aa0000")
    xr = R + 12
    dim(xr, 0, xr, T1, f"{T1:.1f}", off=(3.5, 0), rot=90)
    dim(xr, T1, xr, B1, f"{B1 - T1:.2f}", off=(3.5, 0), rot=90)
    dim(xr, B1, xr, T2, f"{T2 - B1:.1f}", off=(3.5, 0), rot=90)
    dim(xr, T2, xr, B2, f"{B2 - T2:.2f}", off=(3.5, 0), rot=90)
    dim(xr, B2, xr, L["row_y"], f"{L['row_y'] - B2:.1f}", off=(3.5, 0), rot=90)
    dim(0, (T2 + B2) / 2 + 8, Lx, (T2 + B2) / 2 + 8, f"{Lx:.1f}")
    for key in ("left_x", "right_x"):
        x = L[key]
        ax.add_patch(Rectangle((x, L["row_y"]), PLOT_W, PLOT_H, fc="none", ec=blue, lw=0.4, ls=(0, (2, 2))))
        ax.text(x + PLOT_W / 2, L["row_y"] + PLOT_H + 2.5, f"gráfico {PLOT_W:.0f} x {PLOT_H:.0f}", **kw)
    mx, my, mw, mh = L["main_box"]
    dim(mx, my - 3.0, mx + mw, my - 3.0, f"texto {mw:.0f}", off=(0, -2.0))
    ax.text(FRAME_W / 2, FRAME_H - 2.2, "rojo: corte de los bolsillos  ·  gris punteado: lo que tapa el marco  ·  azul: cotas (mm)",
            fontsize=4.6, ha="center", color="#666666")
    fig.savefig(path, dpi=220)
    plt.close(fig)


def main() -> None:
    L, art = primitives()
    svg = HERE / "cuadro_its_a_band.svg"
    write_svg(svg, L, art)
    write_pdf(svg, HERE / "cuadro_its_a_band.pdf")
    tmp = HERE / "_impresion.svg"
    write_svg(tmp, L, art, cut=False)
    write_pdf(tmp, HERE / "cuadro_impresion.pdf")
    tmp.unlink()
    write_preview(HERE / "cuadro_preview.png", L, art)
    write_dims(HERE / "cuadro_cotas.png", L, art)
    print(f"placas x={L['bx']:.2f}..{L['bx'] + BOARD_W:.2f}; frente y={L['by']:.2f}, dorso y={L['by2']:.2f} mm; "
          f"fila de gráficos y={L['row_y']:.1f}..{L['row_y'] + PLOT_H:.1f} mm")


if __name__ == "__main__":
    main()
