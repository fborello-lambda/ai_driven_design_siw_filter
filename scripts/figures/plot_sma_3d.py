import sys; sys.path.insert(0, "/home/ubuntu/siw_filter/src")
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from siwfilter.config import SPEC, VIA_PRESETS, out_img
from siwfilter.palace_dualmode_driven import _dims

RIN, ROUT, SLEN, GRND = 0.38, 1.2639, 6.0, 1.5
OFF, PITCH, NST = 2.62, VIA_PRESETS["gnd_stitch"]["p_mm"], 3
RG = VIA_PRESETS["gnd_stitch"]["d_mm"]/2
h = SPEC.substrate.h*1e3
W, Lt, Lf = _dims(57.212, 1.664, None, None)
X0 = -(Lt+Lf); XC0 = X0-SLEN; XEND = X0+9
PADM = 0.25

def box(ax, x0,x1, y0,y1, z0,z1, **kw):
    v = np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                  [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]])
    f = [[0,1,2,3],[4,5,6,7],[0,1,5,4],[2,3,7,6],[1,2,6,5],[0,3,7,4]]
    ax.add_collection3d(Poly3DCollection([v[i] for i in f], **kw))

def cyl_x(ax, xa, xb, yc, zc, r, n=28, **kw):
    t = np.linspace(0, 2*np.pi, n)
    y, z = yc+r*np.cos(t), zc+r*np.sin(t)
    quads = [[(xa,y[i],z[i]),(xb,y[i],z[i]),(xb,y[i+1],z[i+1]),(xa,y[i+1],z[i+1])]
             for i in range(n-1)]
    ax.add_collection3d(Poly3DCollection(quads, **kw))

def cyl_z(ax, xc, yc, z0, z1, r, n=18, **kw):
    t = np.linspace(0, 2*np.pi, n)
    x, y = xc+r*np.cos(t), yc+r*np.sin(t)
    quads = [[(x[i],y[i],z0),(x[i+1],y[i+1],z0),(x[i+1],y[i+1],z1),(x[i],y[i],z1)]
             for i in range(n-1)]
    ax.add_collection3d(Poly3DCollection(quads, **kw))

fig = plt.figure(figsize=(15, 6.5))
for k, (elev, azim, ttl) in enumerate([(26, -62, "isometric"), (62, -90, "top-down (pads + stitch vias)")]):
    ax = fig.add_subplot(1, 2, k+1, projection="3d")
    ym = 6.0
    # substrate + bottom ground
    box(ax, X0, XEND, -ym, ym, 0, h, facecolor="none", edgecolor="#4b7ea8", alpha=.9, lw=1.0)
    ax.plot([X0,XEND,XEND,X0,X0], [-ym,-ym,ym,ym,-ym], [0,0,0,0,0],
            color="#b87333", lw=1.8, label="bottom GND")
    # microstrip trace
    box(ax, X0, XEND, -W/2, W/2, h, h+0.14, facecolor="#e8b93c", edgecolor="#7a5000", alpha=1, lw=.5)
    # GND pads + stitch vias
    xf = X0 + RG+PADM; xl = xf + (NST-1)*PITCH
    for sgn in (1,-1):
        box(ax, X0, xl+RG+PADM, sgn*(OFF-RG-PADM), sgn*(OFF+RG+PADM), h, h+0.14,
            facecolor="#f0a30a", edgecolor="#7a5000", alpha=1, lw=.5)
        for i in range(NST):
            cyl_z(ax, xf+i*PITCH, sgn*OFF, -0.08, h+0.14, RG, facecolor="#0b7", edgecolor="#054", alpha=1, lw=.3)
    # coax: PTFE shell (transparent) + pin
    cyl_x(ax, XC0, X0, 0, h, ROUT, facecolor="#cccccc", edgecolor="#999", alpha=.30, lw=.25)
    cyl_x(ax, XC0, X0, 0, h, RIN, facecolor="#cc0000", edgecolor="#800", alpha=1.0, lw=.3)
    # ground-contact clip segment (shell meets bottom plane at the edge)
    cyl_x(ax, X0-GRND, X0, 0, h, ROUT, facecolor="#8899aa", edgecolor="#556", alpha=.55, lw=.3)
    # port plane
    t = np.linspace(0, 2*np.pi, 40)
    ax.plot(np.full_like(t, XC0), ROUT*np.cos(t), h+ROUT*np.sin(t), color="#0a0", lw=2.2)
    ax.plot(np.full_like(t, XC0), RIN*np.cos(t), h+RIN*np.sin(t), color="#0a0", lw=1.4)
    ax.set_xlim(XC0-1, XEND); ax.set_ylim(-ym, ym); ax.set_zlim(-2.0, 3.0)
    ax.set_box_aspect((XEND-XC0+1, 2*ym, 5))
    ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("x [mm]", fontsize=8); ax.set_ylabel("y [mm]", fontsize=8)
    ax.set_zlabel("z [mm]", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(ttl, fontsize=10)
fig.suptitle("Taoglas EMPCB.SMAFSTJ.B.HT launch on the dual-mode SIW board — "
             "red pin r=0.38, grey PTFE r=1.264, green stitch vias d=0.6 (3/pad), "
             "green ring = wave port", fontsize=10)
fig.tight_layout()
p = out_img("sma_3d_zoom3.png"); fig.savefig(p, dpi=150); print("wrote", p)
