"""Final pre-fab Palace check of cascade N=3: every audit fix combined.

Refined coax ports (0.15 mm), 9.12 mm air over the feeds (h_air_factor=12,
the domain-converged choice from RETROSPECTIVA_2026-09-07), and the finer
volume mesh (2.5/0.45 mm) from mesh_convergence_cascade_N3.json.
Needs >= 6 GB RAM (315k ND unknowns, ~5 GB peak); OOMs on a 3.7 GB host.
Run from the repo root: uv run python docs/final_check/run_final.py [np] [dl_cav1_mm]
(dl_cav1_mm: optional trim of both end cavities, e.g. -0.3 -- REPORT.md sec.3.)
"""
import json, sys
from pathlib import Path
import numpy as np
from siwfilter.config import FilterSpec
from siwfilter.optimize import run_driven
from siwfilter.topologies.cascade import CascadeTopology

out = Path('output/final_check'); out.mkdir(parents=True, exist_ok=True)
p = json.loads(next(Path('golden/cascade_N3').glob('*taoglas.json')).read_text())['params']
np_ranks = int(sys.argv[1]) if len(sys.argv) > 1 else 2
dl = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
stem = 'final' if dl == 0 else f'final_lcav1{dl:+.2f}'
p['l_cav1'] = round(p['l_cav1'] + dl, 4)
p.update(port_mesh_size=.15, audit_path=str(out / f'{stem}_mesh.json'))
r = run_driven(CascadeTopology(), FilterSpec(N=3), p, stem.replace('final', 'final_check'),
               2.72, 3.02, .005, 2.5, .45, 12., device='CPU', np_ranks=np_ranks)
r['params'] = p
(out / f'{stem}.json').write_text(json.dumps(r, indent=2,
    default=lambda v: v.tolist() if isinstance(v, np.ndarray) else v) + '\n')
print({k: v for k, v in r.items() if k not in ('f', 's11_db', 's21_db')}, flush=True)
if not r.get('ok'): raise SystemExit(1)
