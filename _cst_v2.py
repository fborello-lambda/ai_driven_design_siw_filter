"""Parse v2_data CST result (swi_CST_data.txt, final optimized design),
overlay vs Palace + target, print band metrics, write compare_cst_v2.png."""
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import skrf as rf
from config import out_s2p

def db(x): return 20*np.log10(np.clip(np.abs(x), 1e-6, None))

# --- parse CST txt: two stacked blocks (already in dB) ---
rows = []
for line in open("v2_data/swi_CST_data.txt"):
    s = line.strip()
    if not s or s.startswith("#"):
        rows.append(None); continue
    a, b = s.split(); rows.append((float(a), float(b)))
data = [r for r in rows if r]
blk = [[]]; prev = -1
for fr, v in data:
    if fr < prev - 1e-9: blk.append([])
    blk[-1].append((fr, v)); prev = fr
cst_s11 = np.array(blk[0]); cst_s21 = np.array(blk[1])

# --- references ---
tgt = rf.Network(out_s2p("target.s2p"))
pal = rf.Network(out_s2p("palace.s2p"))

# --- CST band metrics ---
f = cst_s11[:, 0]; s11 = cst_s11[:, 1]; s21 = cst_s21[:, 1]
# -3 dB band on S21
peak = s21.max(); above = f[s21 >= peak - 3]
f_lo, f_hi = above.min(), above.max()
bw3 = (f_hi - f_lo) * 1e3; fc = 0.5 * (f_lo + f_hi)
# in-band (synthesis band 2.7975-2.9425) S11 worst + S21 min
band = (f >= 2.7975) & (f <= 2.9425)
s11_worst = s11[band].max(); s21_min = s21[band].min()
print(f"CST V2 final: center(-3dB) = {fc:.4f} GHz, BW(-3dB) = {bw3:.0f} MHz")
print(f"  in-band (2.7975-2.9425): worst S11 = {s11_worst:.2f} dB, min S21 = {s21_min:.2f} dB")
print(f"  marker peak S21 = {peak:.2f} dB")

# --- figure: CST V2 vs Palace vs target ---
fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), sharex=True)
ax[0].plot(tgt.f/1e9, db(tgt.s[:, 0, 0]), ":", color="gray", lw=1.5, label="Objetivo (sintesis)")
ax[0].plot(pal.f/1e9, db(pal.s[:, 0, 0]), "-", color="#1f77b4", lw=1.6, alpha=.8, label="Palace final")
ax[0].plot(cst_s11[:, 0], cst_s11[:, 1], "-", color="#d62728", lw=2, label="CST V2 (mismas dims)")
ax[0].set_ylabel("|S11| (dB)"); ax[0].set_ylim(-40, 3); ax[0].grid(alpha=.3)
ax[0].axvline(2.87, color="k", ls=":", lw=.8); ax[0].axhline(-16, color="grey", ls="--", lw=.7, alpha=.5)
ax[0].legend(fontsize=8, loc="lower left")
ax[0].set_title("Verificacion CST V2 vs Palace (diseno optimizado: L_cav=34.4, w_ext=16, w_iris=13)")
ax[1].plot(tgt.f/1e9, db(tgt.s[:, 1, 0]), ":", color="gray", lw=1.5, label="Objetivo (sintesis)")
ax[1].plot(pal.f/1e9, db(pal.s[:, 1, 0]), "-", color="#1f77b4", lw=1.6, alpha=.8, label="Palace final")
ax[1].plot(cst_s21[:, 0], cst_s21[:, 1], "-", color="#d62728", lw=2, label="CST V2")
ax[1].set_ylabel("|S21| (dB)"); ax[1].set_xlabel("Frecuencia (GHz)")
ax[1].set_xlim(2.0, 3.6); ax[1].set_ylim(-60, 3); ax[1].grid(alpha=.3)
ax[1].axvline(2.87, color="k", ls=":", lw=.8); ax[1].legend(fontsize=8, loc="lower center")
fig.tight_layout(); fig.savefig("v2_data/compare_cst_v2.png", dpi=140)
print("WROTE v2_data/compare_cst_v2.png")
