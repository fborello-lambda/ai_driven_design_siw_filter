"""Final pre-fab Palace check of cascade N=3: every audit fix combined.

Refined coax ports (0.15 mm), 9.12 mm air over the feeds (h_air_factor=12,
the domain-converged choice from RETROSPECTIVA_2026-09-07), and the finer
volume mesh (2.5/0.45 mm) from mesh_convergence_cascade_N3.json.
Needs >= 6 GB RAM (315k ND unknowns, ~5 GB peak); OOMs on a 3.7 GB host.
Run from the repo root: uv run python docs/final_check/run_final.py [np]
"""
import json, sys
from pathlib import Path
import numpy as np
from siwfilter.config import FilterSpec
from siwfilter.optimize import run_driven
from siwfilter.topologies.cascade import CascadeTopology

out = Path('output/final_check'); out.mkdir(parents=True, exist_ok=True)
p = json.loads(next(Path('golden/cascade_N3').glob('*taoglas.json')).read_text())['params']
p.update(port_mesh_size=.15, audit_path=str(out / 'final_mesh.json'))
np_ranks = int(sys.argv[1]) if len(sys.argv) > 1 else 2
r = run_driven(CascadeTopology(), FilterSpec(N=3), p, 'final_check',
               2.72, 3.02, .005, 2.5, .45, 12., device='CPU', np_ranks=np_ranks)
(out / 'final.json').write_text(json.dumps(r, indent=2,
    default=lambda v: v.tolist() if isinstance(v, np.ndarray) else v) + '\n')
print({k: v for k, v in r.items() if k not in ('f', 's11_db', 's21_db')}, flush=True)
if not r.get('ok'): raise SystemExit(1)
