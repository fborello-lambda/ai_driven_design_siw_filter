"""Reproduce short diagnostic solves; these do not establish full-band convergence.
Run from the repository root: .venv/bin/python docs/audit_cst_palace/run_mesh_checks.py
"""
import json
from pathlib import Path
import numpy as np
from siwfilter.config import FilterSpec
from siwfilter.optimize import run_driven
from siwfilter.topologies.cascade import CascadeTopology

out = Path('output/audit_cst_palace')
out.mkdir(parents=True, exist_ok=True)
golden = next(Path('golden/cascade_N3').glob('*taoglas.json'))
params = json.loads(golden.read_text())['params']
experiments = [('baseline', None, 6.), ('ports_015', .15, 6.),
               ('ports_008', .08, 6.), ('air_12', .15, 12.)]
results = {}
for label, size, hair in experiments:
    p = dict(params, audit_path=str(out / f'{label}_mesh.json'))
    if size is not None:
        p['port_mesh_size'] = size
    r = run_driven(CascadeTopology(), FilterSpec(N=3), p, f'audit_{label}',
                   2.80, 2.94, .07, 3.5, .6, hair, device='CPU', np_ranks=4)
    results[label] = r
    (out / 'diagnostic_solves.json').write_text(json.dumps(results, indent=2,
        default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x) + '\n')
    print(label, {k:v for k,v in r.items() if k in ('ok','err','f','s11_db','s21_db')}, flush=True)
    if not r.get('ok'):
        raise SystemExit(f'{label} failed: {r}')
