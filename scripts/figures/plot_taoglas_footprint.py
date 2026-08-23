import sys
sys.path.insert(0, "/home/ubuntu/siw_filter/src")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Polygon
from siwfilter.config import SPEC, out_img
from siwfilter.palace_dualmode_driven import _dims, _via_layout

a=57.212; w_iris=15.261; x_iris=28.678; y_wall=8.619; w_ext=16.311
d_via=1.5; p_via=3.0; w_ms=1.664
RIN, ROUT = 0.38, 1.2639
OFF, PITCH, CLEAR = 2.62, 1.2, 0.3
RG = 0.3  # stitch via radius (0.6mm dia, JLCPCB-typical) -- NOT the 0.75 SIW fence radius
NST = 3
W, Lt, Lf = _dims(a, w_ms, None, None)
Xf=Lt+Lf; half=a/2; ym=half+3.0; r=d_via/2
X0, X1 = -Xf, a+Xf
y_in = W/2 + CLEAR
h = SPEC.substrate.h*1e3

fig, (axA, axB) = plt.subplots(2, 1, figsize=(12, 9),
                               gridspec_kw={"height_ratios": [1.15, 1]})

def draw(ax, full):
    ax.add_patch(Rectangle((X0,-ym), X1-X0, 2*ym, fc="#eef6e4", ec="0.35", lw=1.2, zorder=0))
    ax.add_patch(Rectangle((0,-half), a, 2*half, fc="#cfe8ff", ec="none", alpha=.5, zorder=1))
    PADM=0.25; y_lo=OFF-RG-PADM; y_hi=OFF+RG+PADM
    for x_edge, sign in ((X0,+1.0),(X1,-1.0)):
        x_first = x_edge + sign*(RG+PADM)
        x_last = x_first + sign*(NST-1)*PITCH
        xa, xb = sorted([x_edge, x_last + sign*(RG+PADM)])
        for sgn in (1,-1):
            ys = sorted([sgn*y_lo, sgn*y_hi])
            ax.add_patch(Rectangle((xa, ys[0]), xb-xa, ys[1]-ys[0],
                                   fc="#f0a30a", ec="#8a5c00", lw=.7, alpha=.9, zorder=2,
                                   label="GND pad" if (full and x_edge==X0 and sgn==1) else None))
    for pts in ([(X0,+W/2),(-Lt,+W/2),(0,+half),(0,-half),(-Lt,-W/2),(X0,-W/2)],
                [(X1,+W/2),(a+Lt,+W/2),(a,+half),(a,-half),(a+Lt,-W/2),(X1,-W/2)]):
        ax.add_patch(Polygon(pts, closed=True, fc="#d9a441", ec="#a06d12", lw=.8, zorder=3))
    vias,_ = _via_layout(a, w_iris, x_iris, w_ext, d_via, p_via, y_wall)
    for x,y in vias:
        ax.add_patch(Circle((x,y), r, fc="#3b3b3b", ec="none", zorder=4))
    for x_edge, sign in ((X0,+1.0),(X1,-1.0)):
        xf = x_edge + sign*(RG+PADM)
        for k in range(NST):
            xv = xf + sign*k*PITCH
            for sgn in (1,-1):
                ax.add_patch(Circle((xv, sgn*OFF), RG, fc="#0b7", ec="#054", lw=.8, zorder=5,
                             label=f"GND stitch via (d=0.6mm) x{NST*4}" if (full and k==0 and sgn==1 and x_edge==X0) else None))
    for xe in (X0, X1):
        ax.add_patch(Circle((xe,0), ROUT, fc="none", ec="#888", ls="--", lw=.9, zorder=6))
        ax.add_patch(Circle((xe,0), RIN, fc="#c00", ec="none", zorder=7,
                     label="SMA pin r=0.38" if (full and xe==X0) else None))

draw(axA, True)
axA.set_xlim(X0-4, X1+4); axA.set_ylim(-ym-3, ym+3); axA.set_aspect("equal")
axA.set_title(f"Dual-mode SIW + Taoglas EMPCB.SMAFSTJ.B.HT  —  board {X1-X0:.1f} x {2*ym:.1f} mm, "
              f"substrate {h:.2f} mm", fontsize=10)
axA.legend(loc="upper right", fontsize=7); axA.grid(alpha=.2)
axA.set_xlabel("x [mm]"); axA.set_ylabel("y [mm]")

draw(axB, False)
axB.set_xlim(X0-3, X0+11); axB.set_ylim(-6.5, 6.5); axB.set_aspect("equal")
axB.set_title("Input connector footprint (zoom)", fontsize=10)
axB.grid(alpha=.25); axB.set_xlabel("x [mm]"); axB.set_ylabel("y [mm]")
for sgn in (1,-1):
    axB.annotate("", xy=(X0+0.8, 0), xytext=(X0+0.8, sgn*OFF),
                 arrowprops=dict(arrowstyle="<->", color="#054", lw=1.1))
    axB.text(X0+1.0, sgn*OFF/2, f"{OFF:.2f} mm\n(leg offset)", color="#054", fontsize=8, va="center")
axB.annotate("", xy=(X0,-W/2), xytext=(X0,+W/2), arrowprops=dict(arrowstyle="<->", color="#a06d12"))
axB.text(X0-2.7, 0, f"W_ms\n{W:.3f}", color="#a06d12", fontsize=8, va="center")

axB.text(X0+4.2, 1.5, f"pad inner edge {OFF-RG-0.25:.2f} mm\n(trace edge {W/2:.3f})\nclearance {OFF-RG-0.25-W/2:.2f} mm = 1.6x h", color="#8a5c00", fontsize=8)
axB.text(X0+0.6, -5.6, f"stitch pitch {PITCH} mm, {NST} vias/pad (12 total)", fontsize=8, color="#054")
axB.text(X0-2.9, 4.6, f"pin r={RIN} (real)\nPTFE r={ROUT}", fontsize=8, color="#c00")
fig.tight_layout()
p = out_img("taoglas_footprint_v3.png"); fig.savefig(p, dpi=150)
print("wrote", p)
