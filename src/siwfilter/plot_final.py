"""Plot the tuned Palace full-filter S11/S21 (siw_final) vs the synthesis target.

Run: uv run python plot_final.py
"""
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .config import out_data, out_img

p = np.genfromtxt(out_data("postpro/siw_final/port-S.csv"), delimiter=",",
                  names=True, deletechars="", replace_space="")
f, s11, s21 = p[p.dtype.names[0]], p[p.dtype.names[1]], p[p.dtype.names[3]]

# target.s2p (synthesis) if available
tgt = None
for cand in ("output/s2p/target.s2p", "cst_data/target.s2p"):
    try:
        import skrf as rf
        tgt = rf.Network(cand); break
    except Exception:
        pass

fig, ax = plt.subplots(figsize=(9, 5.5))
ax.plot(f, s21, "-o", color="#d62728", ms=4, label="|S21| Palace (tuned)")
ax.plot(f, s11, "-o", color="#1f77b4", ms=4, label="|S11| Palace (tuned)")
if tgt is not None:
    ft = tgt.f / 1e9
    ax.plot(ft, 20*np.log10(abs(tgt.s[:, 1, 0])), "--", color="#d62728", alpha=.5, label="|S21| target")
    ax.plot(ft, 20*np.log10(abs(tgt.s[:, 0, 0])), "--", color="#1f77b4", alpha=.5, label="|S11| target")
ax.axvline(2.87, color="k", ls=":", lw=1, label="f0=2.87 GHz")
ax.axhline(-16, color="grey", ls="--", lw=.8, alpha=.6)
ax.set_xlim(f.min(), f.max()); ax.set_ylim(-40, 2)
ax.set_xlabel("Frequency (GHz)"); ax.set_ylabel("dB")
ax.set_title("Tuned SIW filter — Palace FEM (L_cav=37.0, w_iris=12.0, w_ext=16.0)")
ax.grid(alpha=.3); ax.legend(loc="lower right", fontsize=8)
out = out_img("palace_final.png"); fig.tight_layout(); fig.savefig(out, dpi=130)
print("WROTE", out)

ip = int(np.argmax(s21)); fc = f[ip]; pk = s21[ip]
thr = pk - 3; inb = s21 >= thr
bw = (f[inb].max() - f[inb].min()) * 1000 if inb.any() else 0
print(f"center fc        = {fc:.3f} GHz (target 2.87)")
print(f"S21 peak (IL)    = {pk:.2f} dB")
print(f"-3dB bandwidth   ~ {bw:.0f} MHz (target ~145)")
print(f"S11 min in band  = {s11[inb].min():.2f} dB" if inb.any() else "")
print(f"S11 worst in band= {s11[inb].max():.2f} dB" if inb.any() else "")
