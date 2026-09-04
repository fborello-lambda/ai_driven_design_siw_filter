# Fabrication notes -- SIW bandpass filter

Board            166.38 x 45.79 mm, 2 layers
Material         Rogers RO4350B_0.76mm (eps_r 3.66, tan_d 0.0037)
                 NOT FR-4. The design is only valid on this laminate.
Thickness        0.76 mm (dielectric), finished ~0.83 mm
Copper           0.5 oz (17.5 um) both sides, outer only
Surface finish   ENIG
Soldermask       NONE -- bare finish over the whole board
Silkscreen       none
Via holes        1.50 mm finished, PLATED THROUGH, 102 of them
                 plus the launch stitching vias (0.60 mm)
Via treatment    open / unfilled, NOT tented
Min annular ring 0.15 mm (pad 1.80 mm on a 1.50 mm hole)
Min trace        1.2000 mm
Min space        0.2512 mm  (the CPWG launch gap)
Edge             routed to Edge.Cuts, no bevel, no castellation.
                 The board ENDS at the launch pads on both short edges --
                 the edge-mount SMA straddles that edge. No margin there.
Electrical test  yes

## Soldermask, explicitly

There is NO soldermask on this board.
The F.Mask/B.Mask gerbers are NOT empty files -- an empty mask gerber means
"mask everywhere, no openings", which is the opposite of what is wanted.
They each contain ONE board-sized polygon, i.e. an opening over the entire
board, which is how "no soldermask" is expressed in gerber.
Say so in the order notes as well: fabs sometimes treat a fully-open mask
as a plotting mistake and add mask back.

## Why the copper looks unusual

This is a substrate-integrated waveguide, not a normal PCB. The top and
bottom copper are the waveguide walls, the dense via rows are its side
walls, and the gaps in those rows are the coupling irises. Nothing is
missing and nothing needs to be filled or teardropped. Do not apply
copper-balancing, do not add thieving, do not adjust the via pattern.
