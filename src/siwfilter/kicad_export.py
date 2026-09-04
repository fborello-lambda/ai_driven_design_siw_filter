"""KiCad board export: write a .kicad_pcb for a landed design.

Emits the board as real KiCad objects -- copper zones for the ground planes
and the CPWG pours, a filled polygon for the tapered feed, and a plated via
for every SIW fence and stitching via -- so `kicad-cli` can then produce
gerbers, drill files, a 3D model and renders without a GUI.

The geometry comes from the SAME helpers the EM mesh uses (`Geometry` from
siw_geometry, `gnd_stitch_layout` from palace_dualmode_driven, and the CPWG
feed outline from layout_plot), because this project has already shipped a
drawing that disagreed with its own mesh. A board file that is generated
from a second, parallel description of the geometry would reintroduce
exactly that failure -- and here it would reach the fab.

Units: KiCad's s-expression format is millimetres, +y DOWN. `Geometry`
stores metres, +y up, so every coordinate is converted once, in `_xy`.
"""
from __future__ import annotations

import os
import subprocess
import uuid

from .config import FilterSpec, SPEC
from .siw_geometry import Geometry

MM = 1e3


def _uuid() -> str:
    return str(uuid.uuid4())


def _xy(x_m: float, y_m: float) -> tuple[float, float]:
    """Geometry (metres, +y up) -> KiCad (mm, +y down), origin shifted so the
    whole board sits in the positive quadrant the way a fab expects."""
    return (x_m * MM, -y_m * MM)


def _via(x_mm: float, y_mm: float, drill: float, pad: float) -> str:
    return (f'  (via (at {x_mm:.4f} {y_mm:.4f}) (size {pad:.4f}) '
            f'(drill {drill:.4f}) (layers "F.Cu" "B.Cu") (net 1) '
            f'(uuid "{_uuid()}"))\n')


def _zone(pts, layer: str, net: int = 1, name: str = "GND") -> str:
    poly = "".join(f"        (xy {x:.4f} {y:.4f})\n" for x, y in pts)
    return (f'  (zone (net {net}) (net_name "{name}") (layer "{layer}")\n'
            f'    (uuid "{_uuid()}") (hatch edge 0.5)\n'
            f'    (connect_pads (clearance 0.2))\n'
            f'    (min_thickness 0.25) (filled_areas_thickness no)\n'
            f'    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))\n'
            f'    (polygon (pts\n{poly}      ))\n  )\n')


def _poly(pts, layer: str) -> str:
    poly = "".join(f"      (xy {x:.4f} {y:.4f})\n" for x, y in pts)
    return (f'  (gr_poly (pts\n{poly}    )\n'
            f'    (stroke (width 0) (type solid)) (fill yes)\n'
            f'    (layer "{layer}") (uuid "{_uuid()}")\n  )\n')


def _edge(pts) -> str:
    out = []
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        out.append(f'  (gr_line (start {x0:.4f} {y0:.4f}) (end {x1:.4f} {y1:.4f})\n'
                   f'    (stroke (width 0.1) (type solid)) (layer "Edge.Cuts")\n'
                   f'    (uuid "{_uuid()}"))\n')
    return "".join(out)


def write_kicad_pcb(g: Geometry, path: str, launch: dict | None = None,
                    spec: FilterSpec = SPEC, soldermask: bool = True) -> str:
    """Write a .kicad_pcb for `g`. `launch` adds the CPWG pours + stitch vias."""
    from .palace_dualmode_driven import gnd_stitch_layout
    from .layout_plot import _cpwg_feed_polys

    sub = spec.substrate
    xmin, xmax, ymin, ymax = g.board
    d_via = spec.d_via * MM
    # Annular ring: JLCPCB's minimum is 0.13mm; 0.15 gives margin.
    pad = d_via + 2 * 0.15

    s = ['(kicad_pcb (version 20241229) (generator "siwfilter") '
         '(generator_version "9.0")\n',
         '  (general (thickness %.3f) (legacy_teardrops no))\n' % (sub.h * MM),
         '  (paper "A3")\n',
         '  (layers\n'
         '    (0 "F.Cu" signal)\n    (2 "B.Cu" signal)\n'
         '    (9 "F.Adhes" user)\n    (11 "F.Paste" user)\n'
         '    (13 "F.SilkS" user)\n    (15 "F.Mask" user)\n'
         '    (16 "B.Mask" user)\n    (44 "Edge.Cuts" user)\n'
         '    (46 "Cmts.User" user)\n  )\n',
         '  (setup (pad_to_mask_clearance 0)\n'
         '    (grid_origin 0 0)\n  )\n',
         '  (net 0 "")\n  (net 1 "GND")\n  (net 2 "RF")\n']

    # ---- board outline -------------------------------------------------
    b = [_xy(xmin, ymin), _xy(xmax, ymin), _xy(xmax, ymax), _xy(xmin, ymax)]
    s.append(_edge(b))

    # ---- ground planes: bottom solid, top over the cavity section only --
    #
    # Emitted as FILLED POLYGONS, not KiCad zones. Zones only become copper
    # after an interactive "fill all", which kicad-cli cannot do -- exporting
    # gerbers from unfilled zones yields plotted outlines and NO copper
    # (verified: 0 G36/G37 fill blocks in B.Cu, 3.3kB file). A board made
    # from those would have no ground planes and therefore no SIW cavity at
    # all. gr_poly is plotted unconditionally.
    s.append(_poly(b, "B.Cu"))
    top = [_xy(0.0, ymin), _xy(g.L_inner, ymin),
           _xy(g.L_inner, ymax), _xy(0.0, ymax)]
    s.append(_poly(top, "F.Cu"))

    # ---- the RF trace: CPWG-tapered feed when a launch is given ---------
    if launch and launch.get("cpwg_gap_mm") is not None:
        feeds = _cpwg_feed_polys(g, launch)
        for poly in feeds:
            s.append(_poly([_xy(x, y) for x, y in poly], "F.Cu"))
    else:
        for poly in g.feed_polys:
            s.append(_poly([_xy(x, y) for x, y in poly], "F.Cu"))
    for poly in g.taper_polys:
        s.append(_poly([_xy(x, y) for x, y in poly], "F.Cu"))

    # ---- SIW fence + external-iris vias --------------------------------
    n_fence = 0
    for (x, y) in list(g.vias) + list(g.ext_iris_vias):
        px, py = _xy(x, y)
        s.append(_via(px, py, d_via, pad))
        n_fence += 1

    # ---- CPWG pours + stitching vias -----------------------------------
    n_stitch = 0
    if launch and launch.get("cpwg_gap_mm") is not None:
        Lt, Lf, W, Li = g.L_taper, g.L_feed, g.W_ms, g.L_inner
        polys, vias = gnd_stitch_layout(
            -(Lt + Lf) * MM, (Li + Lt + Lf) * MM, W * MM,
            ymax * MM, ymin * MM,
            n_gnd_stitch=launch.get("n_gnd_stitch", 6),
            gnd_stitch_offset_mm=launch.get("gnd_stitch_offset_mm", 2.62),
            gnd_stitch_pitch_mm=launch.get("gnd_stitch_pitch_mm", 1.2),
            gnd_via_d_mm=launch.get("gnd_via_d_mm", 0.6),
            gnd_clearance_mm=launch.get("gnd_clearance_mm", 0.3),
            cpwg_gap_mm=launch.get("cpwg_gap_mm"),
            cpwg_y_gnd_mm=launch.get("cpwg_y_gnd_mm"),
            cpwg_y_out_mm=launch.get("cpwg_y_out_mm"),
            cpwg_len_mm=launch.get("cpwg_len_mm", 5.0),
            cpwg_taper_mm=launch.get("cpwg_taper_mm", 4.0))
        for poly in polys:
            s.append(_poly([(x, -y) for x, y in poly], "F.Cu"))
        dg = launch.get("gnd_via_d_mm", 0.6)
        for (x, y) in vias:
            s.append(_via(x, -y, dg, dg + 0.3))
            n_stitch += 1

    # ---- soldermask opening over the whole board, if asked for ----------
    if not soldermask:
        for layer in ("F.Mask", "B.Mask"):
            s.append(_poly(b, layer))

    s.append(")\n")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write("".join(s))
    print(f"Wrote {path}  ({n_fence} fence vias, {n_stitch} stitch vias, "
          f"board {(xmax-xmin)*MM:.1f} x {(ymax-ymin)*MM:.1f} mm, "
          f"soldermask={'yes' if soldermask else 'OPEN (none)'})")
    return path


# The five gerbers JLCPCB requires for a 2-layer board, plus silkscreen so
# the set is complete even when (as here) it is empty. Named explicitly
# rather than left to kicad-cli's default so that adding a layer to the
# board file cannot silently change what gets sent to the fab.
JLCPCB_LAYERS = "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,Edge.Cuts"


def run_kicad_cli(pcb: str, outdir: str) -> dict:
    """Drive kicad-cli for the fabrication + review outputs. Returns what
    actually succeeded -- a missing tool or a failed step is reported, never
    silently skipped."""
    os.makedirs(outdir, exist_ok=True)
    done: dict[str, str] = {}
    jobs = [
        # --no-x2: JLCPCB's CAM reads plain RS-274X most reliably.
        # Protel extensions (.GTL/.GBL/.GTS/.GBS/.GM1) are kicad-cli's
        # default and are what their uploader auto-recognises, so they are
        # deliberately NOT disabled.
        ("gerbers", ["pcb", "export", "gerbers", "--output", outdir,
                     "--layers", JLCPCB_LAYERS, "--no-x2", "--no-netlist", pcb]),
        # --excellon-separate-th splits PTH from NPTH. Every hole on this
        # board is plated (the via fence IS the SIW wall), so the NPTH file
        # comes out empty -- which is itself the check that nothing ended up
        # unplated by accident.
        ("drill",   ["pcb", "export", "drill", "--output", outdir,
                     "--format", "excellon", "--excellon-units", "mm",
                     "--drill-origin", "absolute", "--excellon-separate-th",
                     "--generate-map", "--map-format", "pdf",
                     "--generate-report", "--report-path",
                     os.path.join(outdir, "drill_report.txt"), pcb]),
        # --exclude-drawing-sheet: without it the SVG carries KiCad's page
        # frame and its grid labels, which read as stray magenta lines and a
        # floating "3" next to the launch -- easy to mistake for board
        # artwork. Nothing of the sort is in the gerbers (they are plotted
        # without --include-border-title), but a review picture that shows
        # phantom copper is worse than no picture.
        ("svg",     ["pcb", "export", "svg", "--output",
                     os.path.join(outdir, "board.svg"), "--page-size-mode", "2",
                     "--exclude-drawing-sheet", "--fit-page-to-board",
                     "--layers", "F.Cu,B.Cu,Edge.Cuts", pcb]),
        ("svg_top", ["pcb", "export", "svg", "--output",
                     os.path.join(outdir, "top.svg"), "--page-size-mode", "2",
                     "--exclude-drawing-sheet", "--fit-page-to-board",
                     "--layers", "F.Cu,Edge.Cuts", pcb]),
        ("svg_bot", ["pcb", "export", "svg", "--output",
                     os.path.join(outdir, "bottom.svg"), "--page-size-mode", "2",
                     "--exclude-drawing-sheet", "--fit-page-to-board", "--mirror",
                     "--layers", "B.Cu,Edge.Cuts", pcb]),
        ("step",    ["pcb", "export", "step", "--output",
                     os.path.join(outdir, "board.step"), pcb]),
    ]
    for name, argv in jobs:
        r = subprocess.run(["kicad-cli", *argv], capture_output=True, text=True)
        if r.returncode == 0:
            done[name] = "ok"
        else:
            done[name] = f"FAILED: {(r.stderr or r.stdout).strip()[:160]}"
        print(f"  kicad-cli {name}: {done[name]}")
    return done


def zip_for_fab(outdir: str, zip_path: str) -> str:
    """Zip the gerbers + drill files exactly as JLCPCB's uploader wants them:
    a flat archive, no directory, nothing else in it."""
    import zipfile
    keep = (".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gm1",
            ".drl", ".txt")
    files = sorted(f for f in os.listdir(outdir)
                   if f.lower().endswith(keep) and f != "drill_report.txt")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(outdir, f), arcname=f)
    print(f"Wrote {zip_path}  ({len(files)} files)")
    for f in files:
        print(f"    {f}")
    return zip_path


def write_fab_notes(path: str, g: Geometry, spec: FilterSpec = SPEC,
                    soldermask: bool = False, launch: dict | None = None) -> str:
    """The order-form values a fab cannot infer from the gerbers."""
    sub = spec.substrate
    xmin, xmax, ymin, ymax = g.board
    d = spec.d_via * MM
    launch = launch or {}
    # Narrowest copper and narrowest gap actually on the board, measured from
    # the same launch dict the mesher uses -- not quoted from memory.
    gap = launch.get("cpwg_gap_mm")
    dg = launch.get("gnd_via_d_mm", 0.6)
    min_trace = min(x for x in (g.W_ms * MM, launch.get("cpwg_w_feed_mm")) if x)
    min_space = gap if gap else min_trace
    txt = f"""# Fabrication notes -- SIW bandpass filter

Board            {(xmax-xmin)*MM:.2f} x {(ymax-ymin)*MM:.2f} mm, 2 layers
Material         Rogers {spec.substrate_name} (eps_r {sub.eps_r}, tan_d {sub.tan_d})
                 NOT FR-4. The design is only valid on this laminate.
Thickness        {sub.h*MM:.2f} mm (dielectric), finished ~{sub.h*MM + 0.07:.2f} mm
Copper           0.5 oz (17.5 um) both sides, outer only
Surface finish   ENIG
Soldermask       {"green, both sides" if soldermask else
                  "NONE -- bare finish over the whole board"}
Silkscreen       none
Via holes        {d:.2f} mm finished, PLATED THROUGH, {len(g.vias)+len(g.ext_iris_vias)} of them
                 plus the launch stitching vias ({dg:.2f} mm)
Via treatment    open / unfilled, NOT tented
Min annular ring 0.15 mm (pad {d + 0.30:.2f} mm on a {d:.2f} mm hole)
Min trace        {min_trace:.4f} mm
Min space        {min_space:.4f} mm  (the CPWG launch gap)
Edge             routed to Edge.Cuts, no bevel, no castellation.
                 The board ENDS at the launch pads on both short edges --
                 the edge-mount SMA straddles that edge. No margin there.
Electrical test  yes

## Soldermask, explicitly

{"Soldermask is present." if soldermask else '''There is NO soldermask on this board.
The F.Mask/B.Mask gerbers are NOT empty files -- an empty mask gerber means
"mask everywhere, no openings", which is the opposite of what is wanted.
They each contain ONE board-sized polygon, i.e. an opening over the entire
board, which is how "no soldermask" is expressed in gerber.
Say so in the order notes as well: fabs sometimes treat a fully-open mask
as a plotting mistake and add mask back.'''}

## Why the copper looks unusual

This is a substrate-integrated waveguide, not a normal PCB. The top and
bottom copper are the waveguide walls, the dense via rows are its side
walls, and the gaps in those rows are the coupling irises. Nothing is
missing and nothing needs to be filled or teardropped. Do not apply
copper-balancing, do not add thieving, do not adjust the via pattern.
"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write(txt)
    print(f"Wrote {path}")
    return path
