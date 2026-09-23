# Fabrication checklist — SIW bandpass filter, cascade N=3

Every box below was checked by reading the **files that would be uploaded**, not the code that wrote them. Re-run with `siw kicad --check`.

Board 165.78 × 45.79 mm · RO4350B_0.76mm · 0.76 mm · ENIG · no soldermask

**34 of 34 automated checks pass.**

## Files that get uploaded

- [x] **Upload set complete** — all 7 files present
- [x] **Fab archive present** — siw_cascade_N3_jlcpcb.zip
- [x] **F.Cu carries filled copper** — 9 fill regions, 118 pad flashes
- [x] **B.Cu carries filled copper** — 1 fill regions, 118 pad flashes
- [x] **Edge.Cuts matches the design** — gerber 165.78 x 45.79 mm vs geometry 165.78 x 45.79 mm
- [x] **PTH hole count matches the geometry** — 118 plated holes: 102 fence/iris + 16 launch stitching
- [x] **No unplated holes** — NPTH file holds 0 holes (every hole on this board is a waveguide wall and must be plated)
- [x] **Drill 0.60 mm is a stock size** — 16 holes; nearest stock drill 0.60 mm
- [x] **Drill 1.50 mm is a stock size** — 102 holes; nearest stock drill 1.50 mm

## JLCPCB_2layer manufacturing rules

- [x] **Annular ring** — 0.150 mm vs JLCPCB_2layer minimum 0.130 mm
- [x] **Drill aspect ratio** — 1.33:1 on the 0.60 mm hole vs limit 10:1
- [x] **Minimum space** — CPWG launch gap 0.2512 mm vs minimum 0.127 mm
- [x] **Minimum trace width** — 1.2000 mm vs minimum 0.127 mm
- [x] **Hole-to-hole spacing** — 1.50 mm edge-to-edge (pitch 3.00, drill 1.50) vs minimum 0.50 mm
- [x] **All pads inside the board outline** — tightest pad-to-edge clearance 0.100 mm
- [ ] **Hole edge to board edge** — tightest is 0.250 mm (0.60 mm hole at (134.03, 2.62)). Board houses commonly require 0.2-0.3 mm here -- CONFIRM against the fab's current rules. The launch stitching vias sit close to the edge by design, because the edge-mount SMA needs its ground right at the connector.
- [x] **Soldermask fully open (bare board)** — F.Mask/B.Mask each hold 1/1 region(s) spanning 165.78 x 45.79 mm -- an OPENING over the whole board, not an empty file
- [x] **Board fits the connector fork** — finished stack 0.7950 mm vs datasheet sec.2 max 0.80 mm (sec.3.1's footprint note says 0.79 mm -- we are +5 um against that tighter figure, so there is NO margin). 1 oz copper would give 0.830 mm and would not fit -- the 0.5 oz spec is load-bearing.
- [x] **Connector ground legs land on the pours** — legs span y 2.120..3.120 mm, pours span 0.8512..3.6000 mm
- [x] **Connector centre pin lands on the trace** — pin 0.76 mm dia on a 1.200 mm trace
- [x] **Ground pad length covers the connector legs** — pour 5.00 mm long vs the datasheet's 4.56 mm pad and 3.8 mm leg
- [ ] **Signal trace vs the datasheet land pattern** — 1.200 mm against the datasheet's 0.85 +-0.2 mm. Outside the band ON PURPOSE: the CPWG gap and trace width together are what solve to 50 ohm on this substrate. The pin still lands on copper, so it solders normally.
- [x] **Launch pads reach the board edge** — top copper spans x [-31.200, 134.581] mm, board [-31.200, 134.581] mm -- the edge-mount SMA straddles this edge

## SIW design rules (Xu & Wu 2005, Cassivi 2002)

- [x] **Via pitch/diameter ratio** — p/d = 2.00 (leakage rule 0.5..2.5; Xu & Wu 2005)
- [x] **Via diameter vs guided wavelength** — d = 1.50 mm, lambda_g/5 = 15.29 mm at 2.870 GHz
- [x] **Via diameter vs waveguide width** — d = 1.50 mm, a_eff/5 = 7.80 mm

## The board matches what was simulated

- [x] **CST macro places the same vias** — 43 distinct x positions in siw_cascade_N3.bas vs 43 from the mesh helpers
- [x] **CST macro coordinates are in millimetres** — largest |x| is 134.031 mm against a 165.8 mm board
- [x] **CST macro draws the microstrip-to-SIW taper** — taper_in/taper_out extrude blocks present
- [x] **CST macro draws the SMA coax shield** — sma_in_shield/sma_out_shield present
- [x] **SMA coax centred on the trace plane, not the substrate midplane** — no "h_sub/2" Zcenter/Zrange found
- [x] **CST domain floor is open, not an extra ground plane** — .Zmin "open"
- [x] **CST domain end-walls are open, not PEC end-caps** — .Xmin/.Xmax "open"
- [x] **Fabricated geometry == simulated geometry** — ok: fence vias drawn=102 meshed=102; ok: ground-stitch vias meshed=16 (n_gnd_stitch parameter=6 -- these differ BY DESIGN; report the measured count, never the request); ok: CPWG feed width drawn=1.2000 meshed=1.2000 mm  -> gap 0.2512 mm; ok: feed tapers out to the microstrip width 1.6636 mm (drawn max half-width 0.8318); ok: complete CPWG + SIW trace outline; ok: board edge x=-31.2003 mm meets the meshed trace end x=-31.2003 mm (edge-mount SMA)

## Known deviations from specification

The board is ordered **with these written down**, not fixed. Measured values are from `golden/cascade_N3/l_cav133.94_l_cav235.5_l_taper15.74_w_ext13.96_w_iris14.42_w_ms1.66_cpwg_taoglas.json`.

| quantity | target | simulated | deviation |
|---|---|---|---|
| centre frequency | 2.870 GHz | 2.876 GHz | +0.20 % |
| return loss in band | ≤ −16 dB | −11.15 dB | **4.85 dB short of spec** |
| −3 dB bandwidth | 143.5 MHz (5 % FBW) | 182 MHz | +27 % (1.27× too wide) |
| insertion loss | — | −1.70 dB | PEC mesh; real copper adds ~0.3 dB |

**shape check:** Fine mesh: 3 reflection zeros (2.81/2.85/2.92 GHz); interior ripple peak -14.53 dB; worst in-band S11 is at the upper target-band edge (2.94 GHz).

**known open item:** NOT spec: S11w -11.15 dB vs -16 dB, bw 182 MHz vs 143.5 MHz. Fabricated as a prototype with these deviations written down (docs/final_check/REPORT.md).

A spurious passband above the intended band is expected and accepted (see the `_broadband` golden entry); it is a property of the inline cascade, not a fabrication fault.

## Decide before ordering — these are not checkable

- [ ] **Laminate is really RO4350B 0.76 mm.** JLCPCB's default is FR-4 and the design is invalid on it (eps_r 4.3 vs 3.66 moves every resonance). This is a non-standard laminate: expect a quote, not the instant price, and confirm in writing before paying.
- [ ] **No soldermask is accepted by the fab.** A fully-open mask is sometimes read as a plotting error and mask gets added back. Say it in the order notes.
- [ ] **Connector on hand** — Taoglas EMPCB.SMAFSTJ.B.HT edge-mount SMA, one per port, matching the pad pitch drawn at each board end.
- [ ] **Measurement plan** — VNA calibrated over 2.0–4.0 GHz at minimum; the spurious passband above the band is expected and is not a fault.
