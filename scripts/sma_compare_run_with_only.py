"""Re-run only the with_sma case (ring-topology fix applied) and merge into
the existing sma_compare.npz, which already has valid sma_cmp_without data."""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from siwfilter.config import out_data  # noqa: E402
sys.path.insert(0, os.path.dirname(__file__))
from sma_compare_run import run_one  # noqa: E402

r = run_one(with_sma=True)
print("with ok:", r["ok"])
if not r["ok"]:
    raise SystemExit(1)

npz_path = out_data("sma_compare.npz")
old = dict(np.load(npz_path)) if os.path.exists(npz_path) else {}
old["sma_cmp_with_f"] = r["f"]
old["sma_cmp_with_s11"] = r["s11"]
old["sma_cmp_with_s21"] = r["s21"]
np.savez(npz_path, **old)
print(f"merged -> {npz_path} keys: {list(old.keys())}")
