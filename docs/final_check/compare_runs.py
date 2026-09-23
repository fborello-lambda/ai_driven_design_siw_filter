"""Overlay every fine-mesh final-check run (golden + trims) and tabulate them.

Run from the repo root: uv run python docs/final_check/compare_runs.py [best_stem]
Reads output/final_check/final*.json, writes docs/final_check/tuning_comparison.png
and tuning_summary.json. `best_stem` is drawn thick.
"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

B0, B1 = 2.87 - .07175, 2.87 + .07175          # 5 % FBW target band
runs = sorted(Path('output/final_check').glob('final*.json'))
runs = [r for r in runs if not r.stem.endswith('_mesh')]
best = sys.argv[1] if len(sys.argv) > 1 else None
golden = json.loads(Path('golden/cascade_N3/l_cav134.24_l_cav235.5_l_taper15.74_w_ext13.96_w_iris14.42_w_ms1.66_cpwg_taoglas.json').read_text())['params']

rows = []
fig, ax = plt.subplots(figsize=(9, 5))
for i, r in enumerate(runs):
    d = json.loads(r.read_text())
    if not d.get('ok'):
        continue
    f, a, b = map(np.asarray, (d['f'], d['s11_db'], d['s21_db']))
    band = (f >= B0) & (f <= B1)
    p = d.get('params', golden)
    row = {'run': r.stem, 'l_cav1': p['l_cav1'], 'w_iris': p['w_iris'],
           's11w_db': round(float(a[band].max()), 2),
           'ripple_db': round(float(a[(f >= 2.83) & (f <= 2.92)].max()), 2),
           'bw_mhz': round(d['bw'], 1), 'fc_3db_ghz': round(d['fc_3db'], 4),
           'il_db': round(d['il'], 2), 'il_band_db': round(d['il_band'], 2)}
    rows.append(row)
    lab = 'golden' if r.stem == 'final' else r.stem.replace('final_', '')
    thick = r.stem == best
    c = 'k' if r.stem == 'final' else f'C{i}'
    ax.plot(f, a, color=c, lw=2.6 if thick else 1.2, alpha=1 if thick or r.stem == 'final' else .75,
            label=f"{lab}{'  (CHOSEN)' if thick else ''}: worst {row['s11w_db']} dB")
    ax.plot(f, b, color=c, lw=1.6 if thick else .8, ls='--', alpha=.8)
ax.axvspan(B0, B1, color='g', alpha=.08, label='target band (5 % FBW)')
ax.axhline(-16, color='r', lw=.8, ls='--'); ax.text(2.725, -15.3, 'spec -16 dB', color='r', fontsize=8)
ax.set(xlim=(2.72, 3.02), ylim=(-40, 1), xlabel='GHz', ylabel='dB',
       title='Cascade N=3 tuning, fine-mesh Palace (solid |S11|, dashed |S21|)')
ax.legend(fontsize=7.5, loc='lower right'); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig('docs/final_check/tuning_comparison.png', dpi=130)
Path('docs/final_check/tuning_summary.json').write_text(json.dumps(rows, indent=2) + '\n')
for r in rows:
    print(r)
