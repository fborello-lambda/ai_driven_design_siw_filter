"""Fun analysis of the final Palace sweep: what is the filter *actually* doing?

1. Fit a lossy N=3 coupling matrix (M_S1, M_12, M_23, M_3L, three resonator
   detunings, one unloaded Q) to the simulated |S11|/|S21| and compare it with
   the Chebyshev synthesis target. This names the coupling responsible for the
   missing return loss instead of guessing from the curve shape.
2. Rejection of real neighbours: 2.45 GHz Wi-Fi, 3.5 GHz 5G n78 (edge of the
   sweep permitting), plus the fitted model's prediction where Palace didn't go.
Run from the repo root: uv run python docs/final_check/analyze_final.py [final.json]
"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from siwfilter import palette as P
P.apply()
from scipy.optimize import least_squares
from siwfilter.config import FilterSpec
from siwfilter.synthesis import chebyshev_g, coupling_matrix

src = Path(sys.argv[1] if len(sys.argv) > 1 else 'output/final_check/final.json')
d = json.loads(src.read_text())
f = np.asarray(d.get('f', d.get('f_ghz')), float)
s11, s21 = np.asarray(d['s11_db']), np.asarray(d['s21_db'])
spec = FilterSpec(N=3)
f0, FBW = spec.f0 / 1e9, spec.FBW
M0 = coupling_matrix(chebyshev_g(3, spec.ripple_db), FBW)


def model(x, fg):
    """|S| in dB for x = [mS1, m12, m23, m3L, d1, d2, d3, 1/Qu, f0 shift]."""
    ms1, m12, m23, m3l, d1, d2, d3, iq, df = x
    M = np.zeros((5, 5))
    for (i, j), m in {(0, 1): ms1, (1, 2): m12, (2, 3): m23, (3, 4): m3l}.items():
        M[i, j] = M[j, i] = m
    M[1, 1], M[2, 2], M[3, 3] = d1, d2, d3
    W = np.diag([0, 1, 1, 1, 0.]); R = np.diag([1, 0, 0, 0, 1.])
    G = np.diag([0, 1, 1, 1, 0.]) * iq / FBW
    fc = f0 + df
    a, b = [], []
    for fi in fg:
        A = M + (fi / fc - fc / fi) / FBW * W - 1j * R - 1j * G
        Ai = np.linalg.inv(A)
        a.append(1 + 2j * Ai[0, 0]); b.append(-2j * Ai[4, 0])
    db = lambda v: 20 * np.log10(np.maximum(np.abs(v), 1e-9))
    return db(np.array(a)), db(np.array(b))


def resid(x8):
    # Common detuning of all three resonators IS a centre-frequency shift, so
    # fitting a separate f0 shift too is degenerate -- pin it at zero.
    m11, m21 = model([*x8, 0.0], f)
    # S11 matters most in-band; clip deep nulls so a -40 dB vs -30 dB zero
    # doesn't dominate the fit.
    return np.r_[np.maximum(m11, -30) - np.maximum(s11, -30), 0.5 * (m21 - s21)]


x0 = [M0[0, 1], M0[1, 2], M0[2, 3], M0[3, 4], 0, 0, 0, 1 / 270, 0.0]
lo = [0.3, 0.3, 0.3, 0.3, -2, -2, -2, 0]; hi = [3, 3, 3, 3, 2, 2, 2, .05]
best = min((least_squares(resid, np.clip(np.r_[x0[:4], s, x0[7]], lo, hi), bounds=(lo, hi))
            for s in ([0, 0, 0], [.3, 0, -.3], [-.3, 0, .3])), key=lambda r: r.cost)
x = np.r_[best.x, 0.0]
rms = float(np.sqrt(np.mean(best.fun ** 2)))

# The board is mirror-symmetric, so also fit a mirror-symmetric matrix
# (M_S1=M_3L, M_12=M_23, d1=d3): 3 fewer knobs, and |S| magnitudes of a
# reciprocal 2-port cannot tell the input end from the output end anyway.
def resid_sym(y):
    return resid([y[0], y[1], y[1], y[0], y[2], y[3], y[2], y[4]])


sym = min((least_squares(resid_sym, [x0[0], x0[1], s, 0, 1 / 270],
                         bounds=([.3, .3, -2, -2, 0], [3, 3, 2, 2, .05])) for s in (-.3, 0, .3)),
          key=lambda r: r.cost)
ys = sym.x

ideal = {'M_S1': M0[0, 1], 'M_12': M0[1, 2], 'M_23': M0[2, 3], 'M_3L': M0[3, 4]}
fit = dict(zip(['M_S1', 'M_12', 'M_23', 'M_3L'], x[:4]))
qe = lambda m: 1 / (FBW * m * m)
table = {k: {'target': float(ideal[k]), 'fitted': float(fit[k]),
             'err_pct': float(100 * (fit[k] / ideal[k] - 1))} for k in ideal}
table['Qe_in'] = {'target': qe(ideal['M_S1']), 'fitted': qe(fit['M_S1'])}
table['Qe_out'] = {'target': qe(ideal['M_3L']), 'fitted': qe(fit['M_3L'])}
table['k12'] = {'target': FBW * ideal['M_12'], 'fitted': FBW * fit['M_12']}
table['k23'] = {'target': FBW * ideal['M_23'], 'fitted': FBW * fit['M_23']}
# M_ii = -(2/FBW) * df/f0  =>  resonator shift df = -M_ii * FBW * f0 / 2
detune_mhz = [float(-v * FBW * f0 / 2 * 1000) for v in x[4:7]]
res = {'source': str(src), 'fit_rms_db': rms, 'couplings': table,
       'resonator_detune_mhz': detune_mhz, 'Qu_fitted': float(1 / x[7]) if x[7] > 0 else None,
       'centre_shift_mhz': float(np.mean(detune_mhz)),
       'symmetric_fit': {'fit_rms_db': float(np.sqrt(np.mean(sym.fun ** 2))),
                         'M_ext_err_pct': float(100 * (ys[0] / M0[0, 1] - 1)),
                         'M_int_err_pct': float(100 * (ys[1] / M0[1, 2] - 1)),
                         'end_cavity_detune_mhz': float(-ys[2] * FBW * f0 / 2 * 1000),
                         'mid_cavity_detune_mhz': float(-ys[3] * FBW * f0 / 2 * 1000),
                         'Qu': float(1 / ys[4]) if ys[4] > 0 else None}}

# Interferers: measured if inside the sweep, else model-extrapolated.
fx = np.linspace(2.2, 3.8, 1601)
m11x, m21x = model(x, fx)
_, t21x = model([*x0[:7], 1 / 270, 0], fx)
rej = {}
for name, fr in {'WiFi_2.45GHz': 2.45, '5G_n78_3.5GHz': 3.5}.items():
    inside = f.min() <= fr <= f.max()
    rej[name] = {'s21_db': float(np.interp(fr, f, s21) if inside else np.interp(fr, fx, m21x)),
                 'source': 'Palace' if inside else 'fitted-matrix extrapolation'}
res['rejection'] = rej

# Group delay from the fitted model (Palace gives magnitude only).
ph = []
for fi in fx:
    ms1, m12, m23, m3l, d1, d2, d3, iq, df = x
    M = np.zeros((5, 5))
    for (i, j), m in {(0, 1): ms1, (1, 2): m12, (2, 3): m23, (3, 4): m3l}.items():
        M[i, j] = M[j, i] = m
    M[1, 1], M[2, 2], M[3, 3] = d1, d2, d3
    fc = f0 + df
    A = M + (fi / fc - fc / fi) / FBW * np.diag([0, 1, 1, 1, 0.]) - 1j * np.diag([1, 0, 0, 0, 1.]) \
        - 1j * np.diag([0, 1, 1, 1, 0.]) * iq / FBW
    ph.append(-2j * np.linalg.inv(A)[4, 0])
gd = -np.gradient(np.unwrap(np.angle(ph)), 2 * np.pi * fx * 1e9) * 1e9
band = (fx > f0 - FBW * f0 / 2) & (fx < f0 + FBW * f0 / 2)
res['group_delay_ns'] = {'centre': float(np.interp(f0, fx, gd)), 'max_in_band': float(gd[band].max()),
                         'min_in_band': float(gd[band].min())}

out = src.parent
(out / 'analysis.json').write_text(json.dumps(res, indent=2) + '\n')

fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
ax[0].plot(f, s11, P.AZURE, lw=2, label='Palace |S11|'); ax[0].plot(f, s21, P.ORANGE, lw=2, label='Palace |S21|')
ax[0].plot(fx, m11x, color=P.AZURE, ls='--', lw=1, label='fitted matrix'); ax[0].plot(fx, m21x, color=P.ORANGE, ls='--', lw=1)
ax[0].plot(fx, t21x, 'k:', lw=1, label='Chebyshev target (Qu=270)')
ax[0].plot(fx, model([*x0[:7], 1 / 270, 0], fx)[0], 'k:', lw=1)
ax[0].axhline(-16, color='r', lw=.8, ls='--'); ax[0].text(2.23, -15, 'spec -16 dB', color='r', fontsize=8)
for nm, fr in (('Wi-Fi', 2.45), ('5G n78', 3.5)):
    ax[0].axvline(fr, color='gray', lw=.6); ax[0].text(fr + .01, -8, nm, fontsize=8, color='gray')
ax[0].set(xlim=(2.2, 3.8), ylim=(-60, 2), xlabel='GHz', ylabel='dB', title='Final check: Palace vs fitted coupling matrix')
ax[0].legend(fontsize=8, loc='lower left'); ax[0].grid(alpha=.3)
names = ['M_S1', 'M_12', 'M_23', 'M_3L']
sf = res['symmetric_fit']
xb = np.arange(4)
ax[1].bar(xb - .2, [table[n]['err_pct'] for n in names], .4, color=P.SLATE, label=f'free fit (rms {rms:.2f} dB)')
ax[1].bar(xb + .2, [sf['M_ext_err_pct'], sf['M_int_err_pct'], sf['M_int_err_pct'], sf['M_ext_err_pct']], .4,
          color=P.AZURE, label=f"mirror-symmetric fit (rms {sf['fit_rms_db']:.2f} dB)")
ax[1].set_xticks(xb, names); ax[1].axhline(0, color='k', lw=.8); ax[1].legend(fontsize=8)
ax[1].set(ylabel='fitted vs Chebyshev target (%)',
          title=f"Which coupling is off?  sym. fit: end cavities {sf['end_cavity_detune_mhz']:+.0f} MHz")
ax[1].grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(out / 'analysis.png', dpi=130)
print(json.dumps(res, indent=2))
