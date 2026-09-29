"""Figures for the launch comparison (run run_launch.py ms/cpwg and render.py first).

  sparams.png  S11 + S21 of all three launches on one plot
  renders.png  3D views: whole board + input-launch close-up per launch
  summary.json metrics per launch

`cpwg_sma` is read from the golden (it is exactly the run_launch.py cpwg_sma
run: same fine mesh, 0.15 mm coax ports -- produced by final_check/run_final.py).

Run from the repo root: uv run python docs/launch_comparison/compare.py
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np

from siwfilter.config import FilterSpec
from siwfilter.optimize import _band_ghz, band_edges

sys.path.insert(0, str(Path(__file__).parent))
from run_launch import GOLDEN  # noqa: E402

D = Path('docs/launch_comparison')
R = Path('output/launch_comparison')   # render.py intermediates
LABELS = {
    'ms': 'Microstrip, no connector',
    'cpwg': 'CPWG, no connector',
    'cpwg_sma': 'CPWG + Taoglas SMA (fabricated)',
}
COLORS = {'ms': '#1f77b4', 'cpwg': '#ff7f0e', 'cpwg_sma': '#2ca02c'}


def load(variant: str) -> dict:
    if variant == 'cpwg_sma':
        d = json.loads(Path(GOLDEN.replace('.json', '.s11s21.json')).read_text())
        return {k: np.asarray(d[k]) for k in ('f_ghz', 's11_db', 's21_db')}
    d = json.loads((D / f'{variant}.json').read_text())
    return {'f_ghz': np.asarray(d['f']), 's11_db': np.asarray(d['s11_db']),
            's21_db': np.asarray(d['s21_db'])}


def metrics(r: dict, spec: FilterSpec) -> dict:
    f, s11, s21 = r['f_ghz'], r['s11_db'], r['s21_db']
    b0, b1 = _band_ghz(spec)
    band = (f >= b0) & (f <= b1)
    e = band_edges(f, s21)
    return {'fc_ghz': round(e['fc_3db'], 4), 'bw_mhz': round(e['bw'], 1),
            'il_db': round(float(s21.max()), 2),
            'il_band_db': round(float(s21[band].min()), 2),
            's11w_db': round(float(s11[band].max()), 2)}


def plot_sparams(data: dict, spec: FilterSpec, summary: dict) -> Path:
    b0, b1 = _band_ghz(spec)
    fig, ax = plt.subplots(figsize=(10, 7.2))
    ax.axvspan(b0, b1, color='0.92', zorder=0, label='target band (5 % FBW)')
    ax.axhline(-16, color='0.5', ls=':', lw=1)
    ax.text(2.725, -15.3, 'S11 spec −16 dB',
            color='0.4', fontsize=8)
    for v, r in data.items():
        m = summary[v]
        lab = (f"{LABELS[v]}  —  worst in-band |S11| {m['s11w_db']:.1f} dB, "
               f"BW {m['bw_mhz']:.0f} MHz, IL {m['il_db']:.2f} dB")
        ax.plot(r['f_ghz'], r['s21_db'], color=COLORS[v], lw=2, label=lab)
        ax.plot(r['f_ghz'], r['s11_db'], color=COLORS[v], lw=1.6, ls='--')
    ax.plot([], [], color='k', lw=2, label='S21 (solid)')
    ax.plot([], [], color='k', lw=1.6, ls='--', label='S11 (dashed)')
    ax.set_xlim(2.72, 3.02)
    ax.set_ylim(-40, 1)
    ax.set_xlabel('Frequency (GHz)')
    ax.set_ylabel('|S| (dB)')
    ax.set_title('Cascade N=3 (fabricated geometry) — effect of the feed launch')
    ax.grid(alpha=0.3)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.11), ncol=1, fontsize=9,
              frameon=False)
    fig.tight_layout()
    path = D / 'sparams.png'
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _trim(im: np.ndarray, pad: int = 12) -> np.ndarray:
    ink = im[..., :3].sum(2) < 2.9
    ink[-120:, -200:] = False            # gmsh axis gizmo in the corner
    ys, xs = np.where(ink)
    return im[max(ys.min() - pad, 0):ys.max() + pad, max(xs.min() - pad, 0):xs.max() + pad]


def _launch_crop(im: np.ndarray) -> np.ndarray:
    """Input-launch close-up cut from the high-res render: left board edge,
    centred on the board's mid-line (where the feed runs)."""
    ink = im[..., :3].sum(2) < 2.9
    ink[-200:, -300:] = False
    ys, xs = np.where(ink)
    yc = (ys.min() + ys.max()) // 2
    x0 = xs.min()
    return im[yc - 230:yc + 230, max(x0 - 20, 0):x0 + 700]


def plot_renders() -> Path:
    fig, axes = plt.subplots(3, 2, figsize=(14, 10.5),
                             gridspec_kw={'width_ratios': [2.1, 1]})
    for row, v in zip(axes, LABELS):
        board = _trim(mpimg.imread(R / f'render_{v}_board.png'))
        launch = _launch_crop(mpimg.imread(R / f'render_{v}_hires.png'))
        row[0].imshow(board)
        row[1].imshow(launch)
        row[0].set_ylabel(LABELS[v], fontsize=11, color=COLORS[v], fontweight='bold')
        for a in row:
            a.set_xticks([]); a.set_yticks([])
            for s in a.spines.values():
                s.set_visible(False)
    axes[0][0].set_title('Whole board', fontsize=11)
    axes[0][1].set_title('Input launch (top view)', fontsize=11)
    fig.suptitle('Launch variants — green: copper, brown: RO4350B, yellow: SMA', fontsize=12)
    fig.tight_layout()
    path = D / 'renders.png'
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


if __name__ == '__main__':
    spec = FilterSpec(N=3)
    data = {v: load(v) for v in LABELS if v == 'cpwg_sma' or (D / f'{v}.json').exists()}
    summary = {v: metrics(r, spec) for v, r in data.items()}
    (D / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(json.dumps(summary, indent=1))
    print('wrote', plot_sparams(data, spec, summary))
    print('wrote', plot_renders())
