"""Refined-port diagnostic sweep; not a completed volume/domain convergence study."""
import json
from pathlib import Path
import numpy as np
from siwfilter.config import FilterSpec
from siwfilter.optimize import run_driven
from siwfilter.topologies.cascade import CascadeTopology
p=json.loads(next(Path('golden/cascade_N3').glob('*taoglas.json')).read_text())['params']
p.update(port_mesh_size=.15, audit_path='output/audit_cst_palace/refined_sweep_mesh.json')
r=run_driven(CascadeTopology(),FilterSpec(N=3),p,'audit_refined_sweep',
             2.72,3.02,.005,3.5,.6,6.,device='CPU',np_ranks=4)
Path('output/audit_cst_palace/refined_sweep.json').write_text(json.dumps(r,indent=2,
    default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v)+'\n')
print({k:v for k,v in r.items() if k not in ('f','s11_db','s21_db')},flush=True)
if not r.get('ok'): raise SystemExit(1)
