#!/usr/bin/env python
"""B2: in-sample predictive regressions (PREREG.md E.1-E.3, E.8, robustness R1-R5).

For every (sample, asset, metric, transform, horizon):
  OLS slope, Newey-West t, normal p; bootstrap p under the null (primary and price-baseline families);
  circular-shift placebo; slope and t per sub-period.
Writes results/regressions_<asset>.csv.

Usage: python -I scripts/b2_regressions.py <data_dir> <out_dir> <asset>
"""
import os, sys, time, zlib
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (SEED, HORIZONS, HAC_LAG, B_REG, BLOCK_REG, MIN_OBS, V_METRICS, L_METRICS, PX, SAMPLE,
                    PRICE_BUILT)
from stats import hac_slope, p_two_sided, boot_null_tstats, placebo_shift_tstats

data_dir, out_dir, asset = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)

ROBUST = {"R1_z180": ["lvl_z180", "chg7_z180"], "R2_z730": ["lvl_z730", "chg7_z730"], "R3_chg1": ["chg1"],
          "R4_chg30": ["chg30"]}


def load(tag):
    df = pl.read_parquet(os.path.join(data_dir, f"{asset}_panel_{tag}.parquet"))
    return {c: df[c].to_numpy() for c in df.columns}


def run_unit(panel, col, sample, family, metric, variant, do_boot, do_placebo):
    cfg = SAMPLE[sample]
    d = panel["date"].astype("datetime64[D]")
    s_all = panel[col]
    win = (d >= cfg["start"][asset]) & (d <= cfg["end"])
    ok = win & np.isfinite(s_all) & np.isfinite(panel["r1"])
    n = int(ok.sum())
    rows = []
    if n < MIN_OBS:
        for h in HORIZONS:
            rows.append(dict(sample=sample, asset=asset, family=family, metric=metric, variant=variant, h=h, n=n,
                             note="insufficient data"))
        return rows
    s = s_all[ok]; dd = d[ok]
    r = {h: panel[f"r{h}"][ok] for h in HORIZONS}
    nh = {h: int(np.isfinite(r[h]).sum()) for h in HORIZONS}
    for h in HORIZONS:                                   # valid rows must be a prefix (returns missing only at the end)
        assert np.isfinite(r[h][: nh[h]]).all(), (col, h)
    seed = [SEED, zlib.crc32(f"{sample}|{asset}|{col}".encode())]
    boot = info = None
    if do_boot:
        boot, info = boot_null_tstats(s, r[1], HORIZONS, HAC_LAG, B_REG, BLOCK_REG, np.random.default_rng(seed))
    plc = None
    if do_placebo:
        ks, plc = placebo_shift_tstats(s, {h: r[h][: nh[h]] for h in HORIZONS}, HAC_LAG)
    for h in HORIZONS:
        y = r[h][: nh[h]]; x = s[: nh[h]]
        b, se = hac_slope(x, y, HAC_LAG[h])
        t = b / se
        row = dict(sample=sample, asset=asset, family=family, metric=metric, variant=variant, h=h, n=nh[h],
                   first=str(dd[0]), last=str(dd[nh[h] - 1]), price_built=metric in PRICE_BUILT,
                   b_pct_per_sd=100.0 * b, se_pct=100.0 * se, t_hac=t, p_hac=float(p_two_sided(t)),
                   r2_insample=float(np.corrcoef(x, y)[0, 1] ** 2), note="")
        if boot is not None:
            tb = boot[h]
            row.update(p_boot=float((1 + (np.abs(tb) >= abs(t)).sum()) / (len(tb) + 1)),
                       boot_t_q025=float(np.quantile(tb, 0.025)), boot_t_q50=float(np.median(tb)),
                       boot_t_q975=float(np.quantile(tb, 0.975)), ar1_rho=info["rho"], feedback_r2=info["feedback_r2"])
        if plc is not None:
            tk = plc[h]
            row.update(placebo_p=float((1 + (np.abs(tk) >= abs(t)).sum()) / (len(tk) + 1)),
                       placebo_share_abs_t_gt_1p96=float((np.abs(tk) > 1.96).mean()), placebo_n_shifts=int(len(tk)))
        for i, (name, lo, hi) in enumerate(cfg["subperiods"], 1):
            dsub = dd[: nh[h]]
            m = np.ones(nh[h], bool)
            if lo is not None: m &= dsub >= lo
            if hi is not None: m &= dsub <= hi
            row[f"sub{i}_name"] = name; row[f"sub{i}_n"] = int(m.sum())
            if m.sum() >= 120 and np.std(x[m]) > 0:
                bs, ses = hac_slope(x[m], y[m], HAC_LAG[h])
                row[f"sub{i}_b_pct"] = 100.0 * bs; row[f"sub{i}_t"] = bs / ses
            else:
                row[f"sub{i}_b_pct"] = np.nan; row[f"sub{i}_t"] = np.nan
        rows.append(row)
    return rows


t0 = time.time()
out = []
panels = {tag: load(tag) for tag in ("V", "L", "L0")}
units = []
for sample, mets in (("V", V_METRICS[asset]), ("L", L_METRICS[asset])):
    for m in mets:
        for v in ("lvl", "chg7"):
            units.append((sample, sample, f"{m}|{v}", "primary", m, v, True, True))
        for fam, vs in ROBUST.items():
            for v in vs:
                units.append((sample, sample, f"{m}|{v}", fam, m, v, False, False))
    for px in PX:
        units.append((sample, sample, px, "price_baseline", px, "px", True, True))
for m in L_METRICS[asset]:
    for v in ("lvl", "chg7"):
        units.append(("L0", "L", f"{m}|{v}", "R5_lookahead_1d", m, v, False, False))
for i, (ptag, sample, col, fam, m, v, do_boot, do_plc) in enumerate(units):
    out.extend(run_unit(panels[ptag], col, sample, fam, m, v, do_boot, do_plc))
    if do_boot:
        print(f"{asset} {i+1}/{len(units)} {sample} {col} {fam} t={time.time()-t0:.0f}s", flush=True)
df = pl.DataFrame(out, infer_schema_length=None)
df.write_csv(os.path.join(out_dir, f"regressions_{asset}.csv"))
print(f"{asset}: {df.height} rows, {time.time()-t0:.0f}s")
