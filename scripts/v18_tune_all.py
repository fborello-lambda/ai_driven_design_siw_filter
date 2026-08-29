"""v18: tune all four filters against the user's acceptance spec
(symmetric response, S11 ~ -16dB, IL ~ dielectric floor + ~1dB), using the
new v18 objective (S11/IL/symmetry hinge terms, commit cf6827f) and the
widened coupling search boxes (commit 9d48f18) that can actually reach the
narrow-bandwidth region.

Runs sequentially so each has the machine to itself; GPU is used where a
topology has a validated preset (dualmode does; cascade falls back to CPU
np=4 automatically inside run_driven).
"""
import json
import sys

from siwfilter.config import FilterSpec
from siwfilter.optimize import optimize
from siwfilter.topologies.dualmode import DualModeTopology
from siwfilter.topologies.cascade import CascadeTopology

RUNS = [
    ("dualmode_N2", DualModeTopology(), 2, 40),
    ("cascade_N3",  CascadeTopology(),  3, 36),
    ("cascade_N4",  CascadeTopology(),  4, 30),
]

only = sys.argv[1] if len(sys.argv) > 1 else None

for name, topo, N, budget in RUNS:
    if only and only != name:
        continue
    spec = FilterSpec(N=N)
    print(f"\n=== {name}: N={N}, budget={budget} ===", flush=True)
    try:
        optimize(topo, spec, budget=budget, device="auto", np_ranks=1,
                 log_name=f"v18_{name}_log.csv",
                 best_json_name=f"v18_{name}_best.json")
        print(f"=== {name} DONE ===", flush=True)
    except Exception as e:
        print(f"=== {name} FAILED: {type(e).__name__}: {e} ===", flush=True)

print("V18_ALL_DONE", flush=True)
