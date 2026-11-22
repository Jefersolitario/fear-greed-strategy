#!/usr/bin/env python
"""C3: post-hoc look at the best-ranked signals of the verified (V) family. NOT pre-registered.
 1. BH-adjusted q-values of the out-of-sample (Clark-West) p-values in the V family.
 2. Placebo distribution of the out-of-sample R2 itself (signal circularly shifted, same expanding-window forecast).
 3. The same signal under the robustness variants and on the other asset.
Usage: python -I scripts/c3_lead_check.py <data_dir> <results_dir>
"""
import os, sys
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import HAC_LAG, SAMPLE, MIN_TRAIN_OOS
from stats import expanding_forecast, clark_west, bh_adjust

data_dir, res = sys.argv[1:3]
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); lines.append(s)

S = pl.read_csv(os.path.join(res, "summary_tests.csv"), infer_schema_length=None)
V = S.filter(pl.col("sample") == "V")
P("=== 1. V family: BH-adjusted q of the Clark-West p-values (204 tests) ===")
q = bh_adjust(V["cw_p"].to_numpy()); qi = bh_adjust(V["cw_p_incremental"].to_numpy())
V = V.with_columns(pl.Series("q_cw", q), pl.Series("q_cw_incremental", qi))
for r in V.sort("cw_p").head(5).iter_rows(named=True):
    P(f"  {r['asset']} {r['metric']}|{r['variant']} h={r['h']}: OOS R2 {100*r['oos_r2']:.2f}% CW p {r['cw_p']:.4f} q {r['q_cw']:.3f} | vs price-only: R2 {100*r['oos_r2_incremental']:.2f}% CW p {r['cw_p_incremental']:.4f} q {r['q_cw_incremental']:.3f} | in-sample p_boot {r['p_boot']:.4f} (q in family {r['q_boot_family']:.2f})")

P("\n=== 2. Placebo for the out-of-sample R2 (signal circularly shifted by 90, 97, ... days) ===")
def placebo_oos(asset, col, h):
    df = pl.read_parquet(os.path.join(data_dir, f"{asset}_panel_V.parquet"))
    d = df["date"].to_numpy().astype("datetime64[D]")
    cfg = SAMPLE["V"]
    win = (d >= cfg["start"][asset]) & (d <= cfg["end"])
    s = df[col].to_numpy()[win]; y = df[f"r{h}"].to_numpy()[win]; dd = d[win]
    ev = dd >= cfg["split"]
    def r2_of(sig):
        ym = np.where(np.isfinite(sig), y, np.nan)
        f0 = expanding_forecast(None, ym, h, MIN_TRAIN_OOS); f1 = expanding_forecast(sig[:, None], y, h, MIN_TRAIN_OOS)
        return clark_west(np.where(ev, y, np.nan), f0, f1, HAC_LAG[h])[0]
    actual = r2_of(s)
    ok = np.nonzero(np.isfinite(s))[0]              # shift only within the days that have a signal
    vals = s[ok]
    out = []
    for k in range(90, len(vals) - 90 + 1, 7):
        sh = np.full(len(s), np.nan); sh[ok] = np.roll(vals, k)
        out.append(r2_of(sh))
    out = np.array(out)
    return actual, out
for asset, col, h in (("btc", "SplyActPct1yr|chg7", 1), ("btc", "SplyActPct1yr|chg7", 7), ("btc", "TxTfrValAdjUSD|chg7", 30)):
    a, o = placebo_oos(asset, col, h)
    P(f"  {asset} {col} h={h}: actual OOS R2 {100*a:.2f}%; placebo median {100*np.median(o):.2f}%, 95th pct {100*np.quantile(o, 0.95):.2f}%, max {100*o.max():.2f}%; "
      f"placebo p {(1 + (o >= a).sum()) / (len(o) + 1):.4f} ({len(o)} shifts); Bonferroni x204 = {min(1.0, 204 * (1 + (o >= a).sum()) / (len(o) + 1)):.2f}")

P("\n=== 3. The same metric under the other transforms and on ETH (V-sample, HAC t) ===")
reg = pl.concat([pl.read_csv(os.path.join(res, f"regressions_{a}.csv"), infer_schema_length=None) for a in ("btc", "eth")], how="diagonal_relaxed")
x = reg.filter((pl.col("sample") == "V") & (pl.col("metric") == "SplyActPct1yr") & (pl.col("note") == "")).sort("asset", "variant", "h")
for r in x.iter_rows(named=True):
    P(f"  {r['asset']} SplyActPct1yr|{r['variant']:10s} h={r['h']:2d} n={r['n']} b={r['b_pct_per_sd']:+.3f}% t={r['t_hac']:+.2f} p_hac={r['p_hac']:.3f}" + (f" p_boot={r['p_boot']:.3f}" if r['p_boot'] is not None else ""))
open(os.path.join(res, "lead_check.txt"), "w").write("\n".join(lines) + "\n")
