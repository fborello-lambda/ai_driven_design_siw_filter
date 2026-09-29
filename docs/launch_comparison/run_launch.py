"""Launch comparison for the fabricated cascade N=3 (trimmed golden).

Same geometry, three launches, same fine mesh as docs/final_check/run_final.py
(2.5/0.45 mm volume mesh, h_air_factor 12, 2.72-3.02 GHz step 5 MHz):

  ms        bare 50-ohm microstrip feed to the board edge, wave port on it, no connector
  cpwg      CPWG launch (gap-matched pour + stitching vias), wave port on it, no connector
  cpwg_sma  CPWG + real Taoglas SMA, coax ports -- the fabricated board (== the golden run)

Wave ports placed directly on a planar line self-normalise to that line's own
impedance, so `ms`/`cpwg` show the filter behind an ideally matched feed; only
`cpwg_sma` sees a true 50-ohm reference.

Run from the repo root: uv run python docs/launch_comparison/run_launch.py <variant> [np]
"""
import json, sys
from pathlib import Path
import numpy as np
from siwfilter.config import FilterSpec
from siwfilter.optimize import run_driven
from siwfilter.topologies.cascade import CascadeTopology

GOLDEN = 'golden/cascade_N3/l_cav133.94_l_cav235.5_l_taper15.74_w_ext13.96_w_iris14.42_w_ms1.66_cpwg_taoglas.json'
VARIANTS = {
    'ms':       dict(with_sma=False, gnd_stitch=False, cpwg_gap_mm=None),
    # wave-port mode 3: modes 1-2 of a bare CPWG face are the ground pours
    # against the bottom plane (S21 ~ -78 dB), not the trace
    'cpwg':     dict(with_sma=False, port_mode=3),
    'cpwg_sma': dict(port_mesh_size=.15),
}

if __name__ == '__main__':
    variant = sys.argv[1]
    np_ranks = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    out = Path('output/launch_comparison'); out.mkdir(parents=True, exist_ok=True)
    p = json.loads(Path(GOLDEN).read_text())['params']
    p.update(VARIANTS[variant])
    port_mode = p.pop('port_mode', 1)
    r = run_driven(CascadeTopology(), FilterSpec(N=3), p, f'launch_{variant}',
                   2.72, 3.02, .005, 2.5, .45, 12., device='CPU', np_ranks=np_ranks,
                   port_mode=port_mode)
    r['params'] = p
    r['variant'] = variant
    Path(f'docs/launch_comparison/{variant}.json').write_text(json.dumps(r, indent=1,
        default=lambda v: v.tolist() if isinstance(v, np.ndarray) else v) + '\n')
    print({k: v for k, v in r.items() if k not in ('f', 's11_db', 's21_db')}, flush=True)
    if not r.get('ok'): raise SystemExit(1)
