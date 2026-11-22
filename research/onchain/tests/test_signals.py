"""full_signals (rolling, whole history) and last_signals (as-of, last value) must agree.
Run: .venv/bin/python -I tests/test_signals.py"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from signals import full_signals, last_signals, METRICS, VARIANTS, RAW_NEEDED

rng = np.random.default_rng(1)
n = 2600
raw = {}
for c in RAW_NEEDED:
    x = np.exp(np.cumsum(rng.normal(0, 0.05, n)) + rng.normal(0, 0.2, n)) * 1000
    x[rng.random(n) < 0.01] = np.nan          # holes
    raw[c] = x
raw["FeeTotNtv"][rng.random(n) < 0.02] = 0.0  # zeros
full = full_signals(raw)
worst, checked = 0.0, 0
for cut in (1500, 1777, 2100, 2599):
    tail = {c: v[: cut + 1][-1500:] for c, v in raw.items()}
    last = last_signals(tail)
    for m, (off, vals) in last.items():
        t = cut - off
        for v, val in vals.items():
            f = full[(m, v)][t]
            if np.isnan(f) and np.isnan(val):
                continue
            assert np.isfinite(f) and np.isfinite(val), (m, v, cut, f, val)
            worst = max(worst, abs(f - val)); checked += 1
assert worst < 1e-8, worst
print(f"OK: {checked} (metric, variant, date) values agree, max abs diff {worst:.2e}")
