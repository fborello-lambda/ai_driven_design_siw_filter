"""Finalize deliverables: regenerate palace.s2p from the final baked sim,
build the combined comparison figure, copy it into v2_data. Run after final sim."""
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import skrf as rf, shutil
from config import out_data, out_img, out_s2p

# --- 1) palace.s2p from postpro/final (S22=S11, S12=S21; drop non-physical) ---
d = np.genfromtxt(out_data("postpro/final/port-S.csv"), delimiter=",", names=True,
                  deletechars="", replace_space="")
nm = d.dtype.names; f = d[nm[0]]; o = np.argsort(f); f = f[o]
s11 = 10**(d[nm[1]][o]/20)*np.exp(1j*np.deg2rad(d[nm[2]][o]))
s21 = 10**(d[nm[3]][o]/20)*np.exp(1j*np.deg2rad(d[nm[4]][o]))
keep = (np.abs(s11) <= 1.001) & (np.abs(s21) <= 1.001)
f, s11, s21 = f[keep], s11[keep], s21[keep]
S = np.zeros((len(f), 2, 2), dtype=complex)
S[:, 0, 0] = s11; S[:, 1, 0] = s21; S[:, 0, 1] = s21; S[:, 1, 1] = s11
net = rf.Network(frequency=rf.Frequency.from_f(f*1e9, unit="hz"), s=S, z0=50, name="SIW_BPF_Palace")
net.write_touchstone(out_s2p("palace.s2p").replace(".s2p", ""))
print("palace.s2p:", len(f), "pts")

# --- 2) load comparison sources ---
def db(x): return 20*np.log10(np.clip(np.abs(x), 1e-6, None))
tgt = rf.Network(out_s2p("target.s2p"))
oem = rf.Network(out_s2p("openems.s2p"))
# CST 1st iteration: two stacked blocks (S11 then S21) in "S Parameters.txt"
rows = []
for line in open("S Parameters.txt"):
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

# --- 3) combined figure ---
fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), sharex=True)
# S11
ax[0].plot(tgt.f/1e9, db(tgt.s[:, 0, 0]), ":", color="gray", lw=1.5, label="Objetivo (síntesis)")
ax[0].plot(cst_s11[:, 0], cst_s11[:, 1], "-", color="#2ca02c", lw=1.5, label="CST 1ra iter. (L=38.2)")
ax[0].plot(oem.f/1e9, db(oem.s[:, 0, 0]), "-", color="#ff7f0e", lw=1.3, alpha=.8, label="openEMS (L=38.2)")
ax[0].plot(f, db(s11), "-", color="#1f77b4", lw=2, label="Palace final (L=34.4, w_ext=16)")
ax[0].set_ylabel("|S11| (dB)"); ax[0].set_ylim(-40, 3); ax[0].grid(alpha=.3)
ax[0].axvline(2.87, color="k", ls=":", lw=.8); ax[0].axhline(-16, color="grey", ls="--", lw=.7, alpha=.5)
ax[0].legend(fontsize=8, loc="lower left"); ax[0].set_title("Comparación de métodos — |S11| y |S21|")
# S21
ax[1].plot(tgt.f/1e9, db(tgt.s[:, 1, 0]), ":", color="gray", lw=1.5, label="Objetivo (síntesis)")
ax[1].plot(cst_s21[:, 0], cst_s21[:, 1], "-", color="#2ca02c", lw=1.5, label="CST 1ra iter.")
ax[1].plot(oem.f/1e9, db(oem.s[:, 1, 0]), "-", color="#ff7f0e", lw=1.3, alpha=.8, label="openEMS")
ax[1].plot(f, db(s21), "-", color="#d62728", lw=2, label="Palace final")
ax[1].set_ylabel("|S21| (dB)"); ax[1].set_xlabel("Frecuencia (GHz)")
ax[1].set_xlim(2.0, 3.6); ax[1].set_ylim(-60, 3); ax[1].grid(alpha=.3)
ax[1].axvline(2.87, color="k", ls=":", lw=.8); ax[1].legend(fontsize=8, loc="lower center")
o = out_img("compare_final.png"); fig.tight_layout(); fig.savefig(o, dpi=140); print("WROTE", o)
shutil.copy2(o, "v2_data/compare_final.png"); print("copied to v2_data/")
