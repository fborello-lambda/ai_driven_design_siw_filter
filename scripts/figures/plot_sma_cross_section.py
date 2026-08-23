import sys; sys.path.insert(0, "/home/ubuntu/siw_filter/src")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Wedge
from siwfilter.config import SPEC, out_img
from siwfilter.palace_dualmode_driven import _dims

RIN, ROUT, SLEN = 0.38, 1.2639, 6.0
h = SPEC.substrate.h*1e3
W, Lt, Lf = _dims(57.212, 1.664, None, None)
X0 = -(Lt+Lf); XC0 = X0 - SLEN
GRND = min(1.5, 0.4*SLEN)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

# ---- side view (x-z) through y=0 ----
ax1.add_patch(Rectangle((X0, 0), 14, h, fc="#cfe8ff", ec="0.4", label="substrate (RO4350B 0.76mm)"))
ax1.plot([X0, X0+14], [0,0], color="#b87333", lw=3, label="bottom GND plane")
ax1.plot([X0, X0+14], [h,h], color="#d9a441", lw=2.5, label="microstrip trace (z=h)")
# PTFE (clipped to z>=0 only in the ground-contact segment near the edge)
ax1.add_patch(Rectangle((XC0, h-ROUT), SLEN, 2*ROUT, fc="#e8e8e8", ec="#888", hatch="//",
                        label=f"PTFE dielectric (r={ROUT})"))
ax1.add_patch(Rectangle((X0-GRND, 0), GRND, h+ROUT, fc="#d0d0d0", ec="#666", alpha=.6))
ax1.add_patch(Rectangle((XC0, h-RIN), SLEN, 2*RIN, fc="#c00", ec="none", label=f"pin (r={RIN})"))
ax1.axvline(XC0, color="#080", ls="--", lw=1.6, label="WAVE PORT plane")
ax1.axvline(X0, color="0.3", ls=":", lw=1.2)
ax1.text(X0+0.2, -1.6, "board edge", fontsize=8, color="0.3")
ax1.text(XC0+SLEN/2, h+ROUT+0.35, f"coax stub {SLEN} mm", ha="center", fontsize=8)
ax1.annotate("", xy=(X0-GRND, -0.9), xytext=(X0, -0.9), arrowprops=dict(arrowstyle="<->", color="#444"))
ax1.text(X0-GRND/2, -1.35, f"GND clip {GRND}mm", ha="center", fontsize=7.5, color="#444")
ax1.set_xlim(XC0-1.5, X0+9); ax1.set_ylim(-2.2, 3.2); ax1.set_aspect("equal")
ax1.set_xlabel("x [mm]"); ax1.set_ylabel("z [mm]")
ax1.set_title("SMA launch — side view (x-z, y=0)", fontsize=10)
ax1.legend(fontsize=7, loc="upper right"); ax1.grid(alpha=.25)

# ---- port cross-section (y-z) at x=XC0 ----
ax2.add_patch(Circle((0, h), ROUT, fc="#e8e8e8", ec="#888", hatch="//", lw=1.2))
ax2.add_patch(Circle((0, h), RIN, fc="#c00", ec="#600", lw=1.2))
ax2.annotate("", xy=(0, h), xytext=(RIN, h), arrowprops=dict(arrowstyle="<->", color="w", lw=1.4))
ax2.text(RIN*0.35, h+0.13, f"{RIN}", color="w", fontsize=9, weight="bold")
ax2.annotate("", xy=(0, h), xytext=(0, h+ROUT), arrowprops=dict(arrowstyle="<->", color="#333"))
ax2.text(0.06, h+ROUT*0.55, f"{ROUT}", fontsize=9)
ax2.plot([RIN, ROUT], [h, h], color="#080", lw=2.2, marker="o", ms=4,
         label="VoltagePath (pin->shell)")
z0 = (60/2.08**0.5)*__import__("math").log(ROUT/RIN)
ax2.set_xlim(-1.9, 1.9); ax2.set_ylim(h-1.9, h+1.9); ax2.set_aspect("equal")
ax2.set_xlabel("y [mm]"); ax2.set_ylabel("z [mm]")
ax2.set_title(f"Port cross-section at x={XC0:.2f} mm  —  unbroken annulus, Z0={z0:.1f}$\\Omega$", fontsize=10)
ax2.legend(fontsize=8, loc="lower right"); ax2.grid(alpha=.25)
fig.tight_layout()
p = out_img("sma_cross_section.png"); fig.savefig(p, dpi=150); print("wrote", p)
