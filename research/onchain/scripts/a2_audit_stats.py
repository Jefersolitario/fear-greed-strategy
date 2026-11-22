#!/usr/bin/env python
"""A2: revision and publication-lag statistics per asset x metric from the A1 outputs.

Definitions (fixed before the statistics were computed; see PREREG.md section A):
  real-time date   : a date D whose value first appeared in a commit later than the commit that introduced
                     the column, excluding dates first seen in the first commit after the 2025-06-19 -> 2026-03-26
                     history gap (their first publication was not observed).
  backfilled date  : a date first seen in the commit that introduced the column (or in the post-gap commit).
  revised          : |final - first| > 1e-9 * max(|final|,|first|)   (final = last vintage holding the column)
  material         : |final - first| > 0.10 * local scale, local scale = median |x_t - x_{t-1}| of the final
                     series over the 365 days ending at D (falls back to the full-sample median if zero/NaN)
  publication lag  : commit time of first appearance minus 24:00 UTC of D, in hours.

Usage: python -I scripts/a2_audit_stats.py <pass1_dir> <out_dir>
"""
import os, sys, json
import numpy as np
import pandas as pd
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmgit import EPOCH, ND

pass1, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
GAP_LAST_OLD = np.datetime64("2025-06-19T23:59:59")   # last commit of the pre-rewrite lineage is on this day
MAT_FRAC = 0.10

def q(a, p):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    return float(np.quantile(a, p)) if a.size else float("nan")

all_rows, events_out = [], []
for asset in ("btc", "eth"):
    commits = pl.read_parquet(os.path.join(pass1, f"{asset}_commits.parquet"))
    ctime = commits["commit_time"].to_numpy().astype("datetime64[s]")
    nc = len(ctime)
    post_gap_commit = int(np.nonzero(ctime > GAP_LAST_OLD)[0][0])
    metrics = pl.read_parquet(os.path.join(pass1, f"{asset}_metrics.parquet"))
    cells = pl.read_parquet(os.path.join(pass1, f"{asset}_cells.parquet"))
    summ = pl.read_parquet(os.path.join(pass1, f"{asset}_commit_metric_summary.parquet"))
    for mrow in metrics.iter_rows(named=True):
        m, intro, lastp = mrow["metric"], mrow["intro_commit"], mrow["last_present_commit"]
        c = cells.filter(pl.col("metric") == m).sort("date_idx")
        d = c["date_idx"].to_numpy(); fc = c["first_commit"].to_numpy()
        fv = c["first_val"].to_numpy(); xv = c["final_val"].to_numpy()
        nchg = c["n_changes"].to_numpy(); fch = c["first_change_commit"].to_numpy(); lch = c["last_change_commit"].to_numpy()
        # local scale of day-to-day changes from the final series
        full = np.full(ND, np.nan); full[d] = xv
        ad = np.abs(np.diff(full, prepend=np.nan))
        glob = np.nanmedian(ad) if np.isfinite(ad).any() else np.nan
        # rolling 365d median of |diff| ending at D
        loc = pd.Series(ad).rolling(365, min_periods=30).median().to_numpy()
        scale = loc[d]
        scale = np.where(~np.isfinite(scale) | (scale <= 0), glob, scale)
        dev = np.abs(xv - fv)
        revised = dev > 1e-9 * np.maximum(np.abs(xv), np.abs(fv))
        with np.errstate(divide="ignore", invalid="ignore"):
            rel_level = np.where(np.abs(xv) > 0, dev / np.abs(xv), np.where(dev > 0, np.inf, 0.0))
            rel_scale = np.where(scale > 0, dev / scale, np.where(dev > 0, np.inf, 0.0))
        material = revised & (rel_scale > MAT_FRAC)
        ever = nchg > 0
        is_backfill = (fc == intro) | ((fc == post_gap_commit) & (d < (np.datetime64("2026-03-24") - EPOCH).astype(int)))
        rt = ~is_backfill
        # publication lag in hours for real-time dates
        day_end = (EPOCH + (d + 1).astype("timedelta64[D]")).astype("datetime64[s]")
        lag_h = (ctime[fc] - day_end).astype("timedelta64[s]").astype(float) / 3600.0
        # timing of revisions (days after first publication), real-time dates that were ever changed
        def delay_days(ci):
            return (ctime[np.maximum(ci, 0)] - ctime[fc]).astype("timedelta64[s]").astype(float) / 86400.0
        sel = rt & ever
        d_first, d_last = delay_days(fch)[sel], delay_days(lch)[sel]
        censored = (lch[sel] == post_gap_commit)  # change first seen right after the history gap: true timing unknown
        row = dict(asset=asset, metric=m,
                   intro_date=str(ctime[intro])[:10], last_present_date=str(ctime[lastp])[:10],
                   in_final_file=bool(lastp == nc - 1),
                   rt_first_date=str(EPOCH + np.timedelta64(int(d[rt].min()), "D"))[:10] if rt.any() else "",
                   rt_last_date=str(EPOCH + np.timedelta64(int(d[rt].max()), "D"))[:10] if rt.any() else "",
                   n_rt=int(rt.sum()), n_backfill=int(is_backfill.sum()),
                   rt_years=float(rt.sum() / 365.25),
                   # ---- real-time dates: first-published vs final
                   rt_share_revised=float(revised[rt].mean()) if rt.any() else np.nan,
                   rt_share_material=float(material[rt].mean()) if rt.any() else np.nan,
                   rt_share_ever_changed=float(ever[rt].mean()) if rt.any() else np.nan,
                   rt_med_rel_level=q(rel_level[rt & revised], 0.5), rt_p95_rel_level=q(rel_level[rt & revised], 0.95),
                   rt_med_rel_dchg=q(rel_scale[rt & revised], 0.5), rt_p95_rel_dchg=q(rel_scale[rt & revised], 0.95),
                   rt_max_rel_level=q(rel_level[rt & revised], 1.0),
                   # ---- timing
                   rev_delay_first_med_d=q(d_first, 0.5), rev_delay_last_med_d=q(d_last, 0.5),
                   rev_delay_last_p90_d=q(d_last, 0.9), rev_delay_last_max_d=q(d_last, 1.0),
                   rev_share_last_after_30d=float((d_last > 30).mean()) if d_last.size else np.nan,
                   rev_share_timing_censored=float(censored.mean()) if censored.size else np.nan,
                   # ---- backfilled history: value when the column first appeared vs final
                   bf_share_revised=float(revised[is_backfill].mean()) if is_backfill.any() else np.nan,
                   bf_share_material=float(material[is_backfill].mean()) if is_backfill.any() else np.nan,
                   bf_med_rel_level=q(rel_level[is_backfill & revised], 0.5),
                   bf_med_rel_dchg=q(rel_scale[is_backfill & revised], 0.5),
                   # ---- publication lag (hours after 24:00 UTC of D)
                   lag_med_h=q(lag_h[rt], 0.5), lag_p90_h=q(lag_h[rt], 0.9), lag_p99_h=q(lag_h[rt], 0.99), lag_max_h=q(lag_h[rt], 1.0),
                   lag_share_le24h=float((lag_h[rt] <= 24).mean()) if rt.any() else np.nan,
                   lag_share_le48h=float((lag_h[rt] <= 48).mean()) if rt.any() else np.nan,
                   n_commits_with_change=int(summ.filter((pl.col("metric") == m) & (pl.col("n_changed") > 0)).height),
                   n_bulk_restatements=int(summ.filter((pl.col("metric") == m) & (pl.col("n_changed") >= 100)).height),
                   n_cells_ever_removed=int((c["n_removed"].to_numpy() > 0).sum()))
        all_rows.append(row)
    # bulk restatement events table
    ev = (summ.filter(pl.col("n_changed") >= 100)
              .join(commits.select("commit_idx", "commit_time", "commit"), on="commit_idx")
              .with_columns(pl.lit(asset).alias("asset"))
              .select("asset", "commit_time", "commit", "metric", "n_changed", "n_changed_recent30").sort("commit_time", "metric"))
    events_out.append(ev)

res = pl.DataFrame(all_rows)
# ---- classification (thresholds fixed in PREREG.md section A before these statistics were looked at)
def classify(r):
    if r["rt_years"] < 3.0:
        return "unusable (under 3y of real-time vintages: cannot be audited)"
    rt_bad = (r["rt_share_material"] or 0) > 0.01
    bf_bad = (r["bf_share_material"] or 0) > 0.01 if r["bf_share_material"] is not None and not np.isnan(r["bf_share_material"]) else False
    if not rt_bad and not bf_bad:
        return "safe"
    return "first-published/vintage only"
res = res.with_columns(pl.struct(res.columns).map_elements(classify, return_dtype=pl.Utf8).alias("class"))
res.write_csv(os.path.join(out_dir, "audit_metric_stats.csv"))
pl.concat(events_out).write_csv(os.path.join(out_dir, "audit_bulk_restatements.csv"))
print(res.group_by("asset", "class").len().sort("asset", "class"))
