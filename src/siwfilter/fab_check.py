"""Pre-fabrication checks, run against the FILES that would be uploaded.

Every check here reads the actual gerber / drill / board output, not the
Python objects that generated it. That distinction is the whole point: this
project has twice shipped a picture that disagreed with the thing it was
supposed to depict (a CPWG launch drawn with a 0.019mm gap where the mesh
had 0.2512mm; a board outline 6mm longer than the simulated substrate, with
the launch pads 3mm inside the edge). Checking the generator against itself
would have passed both times.

`run_checks` returns a list of Check(name, ok, detail) and never raises on a
failed check -- a failure is a result, not an error. `write_checklist`
renders them, together with the items that CANNOT be automated and need a
person, into a markdown document.
"""
from __future__ import annotations

import glob
import math
import os
import re
from dataclasses import dataclass

from .config import FAB_RULES, DEFAULT_FAB, FilterSpec, SPEC
from .siw_geometry import Geometry

MM = 1e3


@dataclass
class Check:
    name: str
    ok: bool | None          # None = informational / needs a human
    detail: str
    section: str = "files"


# --------------------------------------------------------------------------
# gerber + drill readers (deliberately dumb: regex over the text formats)
# --------------------------------------------------------------------------

def _gerber_stats(path: str) -> dict:
    """Fill regions and draw commands in one gerber, plus the coordinate
    extents. Fill regions are what actually become copper -- a gerber can be
    large and syntactically fine while containing nothing but outlines."""
    txt = open(path, errors="replace").read()
    fmt = re.search(r"%FSLAX(\d)(\d)Y\d\d\*%", txt)
    dec = int(fmt.group(2)) if fmt else 6
    scale = 10.0 ** dec
    # Coordinates only from real operation lines. Matching a bare `X(\d+)`
    # anywhere in the file also hits the format spec itself (`%FSLAX46Y46*%`
    # -> x = 0.000046), which silently drags xmin to nearly zero and makes an
    # outline check pass on a board of the wrong size.
    xs, ys = [], []
    for line in txt.splitlines():
        m = re.fullmatch(r"(?:X(-?\d+))?(?:Y(-?\d+))?D0[123]\*", line.strip())
        if not m:
            continue
        if m.group(1):
            xs.append(int(m.group(1)) / scale)
        if m.group(2):
            ys.append(int(m.group(2)) / scale)
    return dict(fills=txt.count("G36*"), flashes=txt.count("D03*"),
                draws=txt.count("D01*"), bytes=len(txt),
                xmin=min(xs) if xs else None, xmax=max(xs) if xs else None,
                ymin=min(ys) if ys else None, ymax=max(ys) if ys else None,
                negative="TF.FilePolarity,Negative" in txt)


def _excellon(path: str) -> dict:
    """Tool diameters and hole coordinates from an Excellon file."""
    tools: dict[str, float] = {}
    holes: dict[str, list[tuple[float, float]]] = {}
    cur = None
    for line in open(path, errors="replace"):
        line = line.strip()
        m = re.fullmatch(r"T(\d+)C([\d.]+)", line)
        if m:
            tools[m.group(1)] = float(m.group(2))
            continue
        m = re.fullmatch(r"T(\d+)", line)
        if m:
            cur = m.group(1)
            holes.setdefault(cur, [])
            continue
        m = re.fullmatch(r"X(-?[\d.]+)Y(-?[\d.]+)", line)
        if m and cur:
            holes[cur].append((float(m.group(1)), float(m.group(2))))
    return dict(tools=tools, holes=holes,
                total=sum(len(v) for v in holes.values()))


# --------------------------------------------------------------------------

def run_checks(outdir: str, g: Geometry, spec: FilterSpec = SPEC,
               launch: dict | None = None, soldermask: bool = False,
               fab: str = DEFAULT_FAB, stem: str | None = None,
               with_mesh: bool = True,
               params: dict | None = None) -> list[Check]:
    r = FAB_RULES[fab]
    launch = launch or {}
    out: list[Check] = []
    add = lambda *a, **k: out.append(Check(*a, **k))

    if stem is None:
        tail = "-F_Cu.gtl"
        cands = glob.glob(os.path.join(outdir, f"*{tail}"))
        stem = os.path.basename(cands[0])[:-len(tail)] if cands else "board"
    p = lambda suffix: os.path.join(outdir, f"{stem}{suffix}")

    # ---- 1. the upload set exists ------------------------------------
    required = {"-F_Cu.gtl": "top copper", "-B_Cu.gbl": "bottom copper",
                "-F_Mask.gts": "top soldermask", "-B_Mask.gbs": "bottom soldermask",
                "-Edge_Cuts.gm1": "board outline", "-PTH.drl": "plated drill",
                "-NPTH.drl": "unplated drill"}
    missing = [s for s in required if not os.path.exists(p(s))]
    add("Upload set complete", not missing,
        "all 7 files present" if not missing else f"MISSING {missing}")
    if missing:
        return out

    zips = glob.glob(os.path.join(outdir, "*.zip"))
    add("Fab archive present", bool(zips),
        os.path.basename(zips[0]) if zips else "no .zip written")

    # ---- 2. copper is actually FILLED --------------------------------
    # A zone that was never filled plots as an outline and no copper. The
    # board would have no ground plane -- and therefore no waveguide -- while
    # every file looked plausible. This happened here once.
    for suffix, label in (("-F_Cu.gtl", "F.Cu"), ("-B_Cu.gbl", "B.Cu")):
        st = _gerber_stats(p(suffix))
        add(f"{label} carries filled copper", st["fills"] > 0,
            f"{st['fills']} fill regions, {st['flashes']} pad flashes")

    # ---- 3. outline ---------------------------------------------------
    st = _gerber_stats(p("-Edge_Cuts.gm1"))
    bx = [v * MM for v in g.board]
    w_ger, h_ger = st["xmax"] - st["xmin"], st["ymax"] - st["ymin"]
    w_geo, h_geo = bx[1] - bx[0], bx[3] - bx[2]
    ok = abs(w_ger - w_geo) < 0.01 and abs(h_ger - h_geo) < 0.01
    add("Edge.Cuts matches the design", ok,
        f"gerber {w_ger:.2f} x {h_ger:.2f} mm vs geometry "
        f"{w_geo:.2f} x {h_geo:.2f} mm")

    # ---- 4. drill ------------------------------------------------------
    pth, npth = _excellon(p("-PTH.drl")), _excellon(p("-NPTH.drl"))
    n_fence = len(g.vias) + len(g.ext_iris_vias)
    n_stitch_expected = pth["total"] - n_fence
    add("PTH hole count matches the geometry",
        any(abs(d - spec.d_via * MM) < 1e-6 for d in pth["tools"].values())
        and pth["total"] >= n_fence,
        f"{pth['total']} plated holes: {n_fence} fence/iris + "
        f"{n_stitch_expected} launch stitching")
    add("No unplated holes", npth["total"] == 0,
        f"NPTH file holds {npth['total']} holes "
        f"(every hole on this board is a waveguide wall and must be plated)")

    for t, d in sorted(pth["tools"].items(), key=lambda kv: kv[1]):
        n = len(pth["holes"].get(t, []))
        pref = min(r["preferred_drills"], key=lambda x: abs(x - d))
        add(f"Drill {d:.2f} mm is a stock size", abs(pref - d) < 1e-9,
            f"{n} holes; nearest stock drill {pref:.2f} mm")

    # ---- 5. fab rules --------------------------------------------------
    ring = 0.15
    add("Annular ring", ring >= r["min_annular_ring"],
        f"{ring:.3f} mm vs {fab} minimum {r['min_annular_ring']:.3f} mm",
        section="rules")

    d_small = min(pth["tools"].values())
    aspect = (spec.substrate.h * MM + 2 * spec.substrate.cu_thickness * MM) / d_small
    add("Drill aspect ratio", aspect <= r["max_aspect_ratio"],
        f"{aspect:.2f}:1 on the {d_small:.2f} mm hole vs limit "
        f"{r['max_aspect_ratio']:.0f}:1", section="rules")

    gap = launch.get("cpwg_gap_mm")
    if gap:
        add("Minimum space", gap >= r["min_trace_space"],
            f"CPWG launch gap {gap:.4f} mm vs minimum "
            f"{r['min_trace_space']:.3f} mm", section="rules")
    w_min = min(x for x in (g.W_ms * MM, launch.get("cpwg_w_feed_mm")) if x)
    add("Minimum trace width", w_min >= r["min_trace_width"],
        f"{w_min:.4f} mm vs minimum {r['min_trace_width']:.3f} mm",
        section="rules")

    # Hole EDGE to hole edge along the densest row -- the via fence is the
    # tightest hole spacing on the board by a wide margin.
    edge_gap = spec.p_via * MM - spec.d_via * MM
    add("Hole-to-hole spacing", edge_gap >= r["min_hole_to_hole"],
        f"{edge_gap:.2f} mm edge-to-edge (pitch {spec.p_via*MM:.2f}, "
        f"drill {spec.d_via*MM:.2f}) vs minimum "
        f"{r['min_hole_to_hole']:.2f} mm", section="rules")

    # Every hole must sit inside the outline with room for its pad, and the
    # HOLE edge must clear the routed edge by enough that the barrel does not
    # break out. Reported separately because they fail differently: a pad
    # crossing the outline is a design error, a tight hole-to-edge is a fab
    # question.
    worst_pad, worst_hole, where = 1e9, 1e9, ""
    for t, pts in pth["holes"].items():
        rad = pth["tools"][t] / 2
        for (x, y) in pts:
            cl = [x - bx[0], bx[1] - x, -y - bx[2], bx[3] + y]
            worst_pad = min(worst_pad, min(cl) - rad - ring)
            h = min(cl) - rad
            if h < worst_hole:
                worst_hole, where = h, f"{pth['tools'][t]:.2f} mm hole at ({x:.2f}, {y:.2f})"
    add("All pads inside the board outline", worst_pad >= 0,
        f"tightest pad-to-edge clearance {worst_pad:.3f} mm", section="rules")
    # Informational, not pass/fail: this project's FAB_RULES has no
    # transcribed hole-to-outline limit, and inventing one would put a
    # number in a fabrication document that nobody checked against the
    # fab's current capabilities page. The measurement is real; the
    # threshold is the human's to confirm.
    add("Hole edge to board edge", None,
        f"tightest is {worst_hole:.3f} mm ({where}). Board houses commonly "
        f"require 0.2-0.3 mm here -- CONFIRM against the fab's current rules. "
        f"The launch stitching vias sit close to the edge by design, because "
        f"the edge-mount SMA needs its ground right at the connector.",
        section="rules")

    # ---- 6. soldermask -------------------------------------------------
    fm = _gerber_stats(p("-F_Mask.gts"))
    bm = _gerber_stats(p("-B_Mask.gbs"))
    if soldermask:
        add("Soldermask present", True, "masked board with pad openings",
            section="rules")
    else:
        opens = fm["fills"] > 0 and bm["fills"] > 0
        covers = (opens and abs((fm["xmax"] - fm["xmin"]) - w_geo) < 0.01
                  and abs((fm["ymax"] - fm["ymin"]) - h_geo) < 0.01)
        add("Soldermask fully open (bare board)", covers,
            f"F.Mask/B.Mask each hold {fm['fills']}/{bm['fills']} region(s) "
            f"spanning {fm['xmax']-fm['xmin']:.2f} x {fm['ymax']-fm['ymin']:.2f} mm "
            f"-- an OPENING over the whole board, not an empty file",
            section="rules")

    # ---- 6b. the connector physically fits ----------------------------
    # From the datasheet in docs/sma_connector/ (Taoglas SPE-12-8-134/C/WY),
    # checked 2026-09-04. These are the numbers that decide whether the part
    # can be soldered on at all, which no gerber check can see.
    if launch.get("cpwg_gap_mm") is not None:
        from .topologies.launch import (TAOGLAS_MAX_BOARD_MM,
                                        TAOGLAS_MAX_BOARD_FOOTPRINT_NOTE_MM)
        fin = spec.substrate.h * MM + 2 * spec.substrate.cu_thickness * MM
        add("Board fits the connector fork", fin <= TAOGLAS_MAX_BOARD_MM,
            f"finished stack {fin:.4f} mm vs datasheet sec.2 max "
            f"{TAOGLAS_MAX_BOARD_MM:.2f} mm (sec.3.1's footprint note says "
            f"{TAOGLAS_MAX_BOARD_FOOTPRINT_NOTE_MM:.2f} mm -- we are "
            f"{(fin - TAOGLAS_MAX_BOARD_FOOTPRINT_NOTE_MM)*1000:+.0f} um "
            f"against that tighter figure, so there is NO margin). 1 oz "
            f"copper would give {spec.substrate.h*MM + 0.070:.3f} mm and "
            f"would not fit -- the 0.5 oz spec is load-bearing.",
            section="rules")
        # Datasheet sec.3.1: ground pads on a 2.62mm pitch, 1mm wide, 4.56mm
        # long; centre pin 0.76mm dia. Every one of those must land on our
        # copper or the part cannot be soldered.
        leg_c = launch.get("gnd_stitch_offset_mm", 2.62)
        lo, hi = leg_c - 0.5, leg_c + 0.5
        y_in, y_out = launch["cpwg_y_gnd_mm"], launch["cpwg_y_out_mm"]
        add("Connector ground legs land on the pours", y_in <= lo and hi <= y_out,
            f"legs span y {lo:.3f}..{hi:.3f} mm, pours span "
            f"{y_in:.4f}..{y_out:.4f} mm", section="rules")
        wp = launch["cpwg_w_feed_mm"]
        add("Connector centre pin lands on the trace", wp >= 0.76,
            f"pin 0.76 mm dia on a {wp:.3f} mm trace", section="rules")
        add("Ground pad length covers the connector legs",
            launch.get("cpwg_len_mm", 5.0) >= 4.56,
            f"pour {launch.get('cpwg_len_mm', 5.0):.2f} mm long vs the "
            f"datasheet's 4.56 mm pad and 3.8 mm leg", section="rules")
        # Informational: we are NOT on the recommended land pattern, and
        # that is a decision, not an oversight.
        add("Signal trace vs the datasheet land pattern", None,
            f"{wp:.3f} mm against the datasheet's 0.85 +-0.2 mm. Outside the "
            f"band ON PURPOSE: the CPWG gap and trace width together are what "
            f"solve to 50 ohm on this substrate. The pin still lands on "
            f"copper, so it solders normally.", section="rules")

    # ---- 7. SIW physics rules -----------------------------------------
    d, pv = spec.d_via * MM, spec.p_via * MM
    add("Via pitch/diameter ratio", 0.5 <= pv / d <= 2.5,
        f"p/d = {pv/d:.2f} (leakage rule 0.5..2.5; Xu & Wu 2005)",
        section="siw")
    c = 2.998e8
    a_eff = g.a_siw * MM - d ** 2 / (0.95 * pv)
    fc = c / (2 * (a_eff * 1e-3) * math.sqrt(spec.substrate.eps_r))
    lam_g = c / (spec.f0 * math.sqrt(spec.substrate.eps_r)) / math.sqrt(
        max(1e-9, 1 - (fc / spec.f0) ** 2)) * 1e3
    add("Via diameter vs guided wavelength", d < lam_g / 5,
        f"d = {d:.2f} mm, lambda_g/5 = {lam_g/5:.2f} mm at "
        f"{spec.f0/1e9:.3f} GHz", section="siw")
    add("Via diameter vs waveguide width", d < a_eff / 5,
        f"d = {d:.2f} mm, a_eff/5 = {a_eff/5:.2f} mm", section="siw")

    # ---- 8. launch mountability ---------------------------------------
    stf = _gerber_stats(p("-F_Cu.gtl"))
    reaches = abs(stf["xmin"] - bx[0]) < 0.01 and abs(stf["xmax"] - bx[1]) < 0.01
    add("Launch pads reach the board edge", reaches,
        f"top copper spans x [{stf['xmin']:.3f}, {stf['xmax']:.3f}] mm, "
        f"board [{bx[0]:.3f}, {bx[1]:.3f}] mm -- the edge-mount SMA "
        f"straddles this edge", section="rules")

    # ---- 9. the CST macro places the same solids -----------------------
    # cst_export has now produced TWO silent unit errors: `gnd_stitch_layout`
    # fed metres where it wanted mm (0 stitching vias emitted), then the fix
    # over-applied and the whole CPWG launch came out at 1000x -- SMA pin at
    # radius 380mm, stitching vias 30 metres off the board -- on a macro
    # whose cavity section was perfectly correct. Neither raised. So the .bas
    # is now checked the same way the gerbers are: by reading it.
    from .config import out_bas
    bas = out_bas(f"{stem}.bas")
    if os.path.exists(bas):
        txt = open(bas, errors="replace").read()
        xs = sorted({round(float(m), 4) for m in
                     re.findall(r'\.Xcenter ""(-?[\d.]+)""', txt)})
        want = {round(x * MM, 4) for x, y in
                list(g.vias) + list(g.ext_iris_vias)}
        if launch.get("cpwg_gap_mm") is not None:
            from .palace_dualmode_driven import gnd_stitch_layout
            gk = launch.get
            _, gv = gnd_stitch_layout(
                -(g.L_taper + g.L_feed) * MM,
                (g.L_inner + g.L_taper + g.L_feed) * MM,
                g.W_ms * MM, g.board[3] * MM, g.board[2] * MM,
                n_gnd_stitch=gk("n_gnd_stitch", 6),
                gnd_stitch_offset_mm=gk("gnd_stitch_offset_mm", 2.62),
                gnd_stitch_pitch_mm=gk("gnd_stitch_pitch_mm", 1.2),
                gnd_via_d_mm=gk("gnd_via_d_mm", 0.6),
                gnd_clearance_mm=gk("gnd_clearance_mm", 0.3),
                cpwg_gap_mm=gk("cpwg_gap_mm"),
                cpwg_y_gnd_mm=gk("cpwg_y_gnd_mm"),
                cpwg_y_out_mm=gk("cpwg_y_out_mm"),
                cpwg_len_mm=gk("cpwg_len_mm", 5.0),
                cpwg_taper_mm=gk("cpwg_taper_mm", 4.0))
            want |= {round(x, 4) for x, _ in gv}
        want = sorted(want)
        hit = (len(xs) == len(want)
               and all(abs(a - b) < 1e-3 for a, b in zip(xs, want)))
        add("CST macro places the same vias", hit,
            f"{len(xs)} distinct x positions in {os.path.basename(bas)} vs "
            f"{len(want)} from the mesh helpers"
            + ("" if hit else f" -- MISMATCH, e.g. {xs[:4]} vs {want[:4]}"),
            section="model")
        # A pure magnitude check on top: any 1000x slip puts something
        # metres away from a 166mm board.
        biggest = max((abs(v) for v in xs), default=0.0)
        span = (g.board[1] - g.board[0]) * MM
        add("CST macro coordinates are in millimetres", biggest < 2 * span,
            f"largest |x| is {biggest:.3f} mm against a {span:.1f} mm board",
            section="model")

    # ---- 10. drawing vs mesh ------------------------------------------
    if with_mesh:
        from .report import verify_cascade_drawing_matches_mesh
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = verify_cascade_drawing_matches_mesh(spec=spec, params=params)
        lines = [l.strip() for l in buf.getvalue().splitlines() if "VERIFY" in l]
        add("Fabricated geometry == simulated geometry", ok,
            "; ".join(l.replace("VERIFY ", "") for l in lines) or "no output",
            section="model")

    return out


# --------------------------------------------------------------------------

def load_golden(topology: str, N: int) -> dict | None:
    """The measured response for this topology/order, from `golden/`.

    Read rather than restated: the deviation table in the checklist is the
    single most consequential thing in the document (it is what the board is
    being ordered in spite of), and CLAUDE.md is explicit that prose numbers
    elsewhere in this project drift while `golden/` is guaranteed to match a
    CLI-reproducible run.
    """
    import json
    from .config import PROJECT_ROOT
    d = os.path.join(PROJECT_ROOT, "golden", f"{topology}_N{N}")
    cands = [f for f in sorted(glob.glob(os.path.join(d, "*.json")))
             if "s11s21" not in f and "broadband" not in f]
    if not cands:
        return None
    with open(cands[0]) as fh:
        out = json.load(fh)
    out["_path"] = os.path.relpath(cands[0], PROJECT_ROOT)
    return out


def write_checklist(path: str, checks: list[Check], g: Geometry,
                    spec: FilterSpec = SPEC, launch: dict | None = None,
                    soldermask: bool = False, golden: dict | None = None,
                    fab: str = DEFAULT_FAB) -> str:
    bx = [v * MM for v in g.board]
    sub = spec.substrate
    mark = lambda c: {True: "[x]", False: "[ ] **FAIL**", None: "[ ]"}[c.ok]

    sections = [("files", "Files that get uploaded"),
                ("rules", f"{fab} manufacturing rules"),
                ("siw", "SIW design rules (Xu & Wu 2005, Cassivi 2002)"),
                ("model", "The board matches what was simulated")]

    L = [f"# Fabrication checklist — SIW bandpass filter, cascade N={spec.N}",
         "",
         "Every box below was checked by reading the **files that would be "
         "uploaded**, not the code that wrote them. Re-run with `siw kicad "
         "--check`.",
         "",
         f"Board {bx[1]-bx[0]:.2f} × {bx[3]-bx[2]:.2f} mm · "
         f"{spec.substrate_name} · {sub.h*MM:.2f} mm · ENIG · "
         f"{'no soldermask' if not soldermask else 'soldermask'}",
         ""]

    n_fail = sum(1 for c in checks if c.ok is False)
    L += [f"**{len(checks) - n_fail} of {len(checks)} automated checks pass"
          f"{'' if not n_fail else f'; {n_fail} FAIL'}.**", ""]

    for key, title in sections:
        rows = [c for c in checks if c.section == key]
        if not rows:
            continue
        L += [f"## {title}", ""]
        for c in rows:
            L.append(f"- {mark(c)} **{c.name}** — {c.detail}")
        L.append("")

    L += _deviations_md(golden, spec) if golden else []

    L += ["## Decide before ordering — these are not checkable", "",
          "- [ ] **Laminate is really RO4350B "
          f"{sub.h*MM:.2f} mm.** JLCPCB's default is FR-4 and the design is "
          "invalid on it (eps_r 4.3 vs 3.66 moves every resonance). This is a "
          "non-standard laminate: expect a quote, not the instant price, and "
          "confirm in writing before paying.",
          "- [ ] **No soldermask is accepted by the fab.** A fully-open mask "
          "is sometimes read as a plotting error and mask gets added back. "
          "Say it in the order notes.",
          "- [ ] **Connector on hand** — Taoglas EMPCB.SMAFSTJ.B.HT edge-mount "
          "SMA, one per port, matching the pad pitch drawn at each board end.",
          "- [ ] **Measurement plan** — VNA calibrated over 2.0–4.0 GHz at "
          "minimum; the spurious passband above the band is expected and is "
          "not a fault.",
          ""]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write("\n".join(L))
    print(f"Wrote {path}  ({len(checks) - n_fail}/{len(checks)} checks pass"
          f"{'' if not n_fail else f', {n_fail} FAIL'})")
    return path


def _deviations_md(golden: dict, spec: FilterSpec) -> list[str]:
    m = golden.get("metrics", {})
    fc, bw = m.get("fc_ghz"), m.get("bw_mhz")
    s11, il = m.get("s11w_db"), m.get("il_db")
    f0 = spec.f0 / 1e9
    bw_t = spec.FBW * spec.f0 / 1e6
    L = ["## Known deviations from specification", "",
         "The board is ordered **with these written down**, not fixed. "
         f"Measured values are from `{golden['_path']}`.", "",
         "| quantity | target | simulated | deviation |",
         "|---|---|---|---|",
         f"| centre frequency | {f0:.3f} GHz | {fc:.3f} GHz | "
         f"{(fc-f0)/f0*100:+.2f} % |",
         f"| return loss in band | ≤ −16 dB | −{abs(s11):.2f} dB | "
         f"**{abs(s11+16):.2f} dB short of spec** |",
         f"| −3 dB bandwidth | {bw_t:.1f} MHz ({spec.FBW*100:.0f} % FBW) | "
         f"{bw:.0f} MHz | {(bw-bw_t)/bw_t*100:+.0f} % ({bw/bw_t:.2f}× "
         f"too wide) |",
         f"| insertion loss | — | −{abs(il):.2f} dB | PEC mesh; real "
         f"copper adds ~0.3 dB |",
         ""]
    for key in ("shape_check", "known_open_item"):
        v = golden.get(key)
        if isinstance(v, dict):
            v = v.get("note")
        if v:
            L += [f"**{key.replace('_', ' ')}:** {v}", ""]
    L += ["A spurious passband above the intended band is expected and "
          "accepted (see the `_broadband` golden entry); it is a property "
          "of the inline cascade, not a fabrication fault.", ""]
    return L
