#!/usr/bin/env python
"""A6: direction, size and date of the main restatements (today's value against the first-published value),
for the real-time dates defined in a2. Usage: python -I scripts/a6_restatement_direction.py <pass1_dir> <out_txt>"""
import os, sys
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmgit import EPOCH

pass1, out_txt = sys.argv[1:3]
GAP_LAST_OLD = np.datetime64("2025-06-19T23:59:59")
lines = []
for a, mets in (("btc", ["FlowInExNtv", "FlowOutExNtv", "FlowTfrFromExCnt"]),
                ("eth", ["CapMVRVCur", "CapRealUSD", "SplyCur", "CapMrktCurUSD", "IssTotNtv", "NVTAdj", "AdrActCnt", "FlowInExNtv", "FlowOutExNtv"])):
    c = pl.read_parquet(os.path.join(pass1, f"{a}_cells.parquet"))
    cm = pl.read_parquet(os.path.join(pass1, f"{a}_commits.parquet"))
    mt = pl.read_parquet(os.path.join(pass1, f"{a}_metrics.parquet"))
    ct = cm["commit_time"].to_numpy().astype("datetime64[s]")
    post_gap = int(np.nonzero(ct > GAP_LAST_OLD)[0][0])
    for m in mets:
        intro = mt.filter(pl.col("metric") == m)["intro_commit"][0]
        x = c.filter(pl.col("metric") == m)
        d, fc = x["date_idx"].to_numpy(), x["first_commit"].to_numpy()
        rt = ~((fc == intro) | ((fc == post_gap) & (d < (np.datetime64("2026-03-24") - EPOCH).astype(int))))
        fv, xv = x["first_val"].to_numpy()[rt], x["final_val"].to_numpy()[rt]
        lc, dd = x["last_change_commit"].to_numpy()[rt], d[rt]
        rev = (np.abs(xv - fv) > 1e-9 * np.maximum(np.abs(xv), np.abs(fv))) & (fv != 0)
        ratio = xv[rev] / fv[rev] - 1
        dates = EPOCH + dd[rev].astype("timedelta64[D]")
        vals, cnt = np.unique(ct[lc[rev]].astype("datetime64[D]"), return_counts=True)
        top = sorted(zip(cnt, vals), reverse=True)[:3]
        lines.append(f"{a} {m}: {int(rev.sum())} of {int(rt.sum())} real-time days revised; data dates {dates.min()} .. {dates.max()}; "
                     f"today's value / first-published - 1: median {100*np.median(ratio):+.2f}%, 5th pct {100*np.quantile(ratio, .05):+.2f}%, "
                     f"95th pct {100*np.quantile(ratio, .95):+.2f}%, share revised upward {np.mean(ratio > 0):.2f}; "
                     f"commit of the last change (days affected): " + ", ".join(f"{v} ({int(n)})" for n, v in top))
# vendor-stated completion time (column AssetEODCompletionTime, first-published value), real-time dates
for a in ("btc", "eth"):
    c = pl.read_parquet(os.path.join(pass1, f"{a}_cells.parquet")).filter(pl.col("metric") == "AssetEODCompletionTime")
    mt = pl.read_parquet(os.path.join(pass1, f"{a}_metrics.parquet"))
    cm = pl.read_parquet(os.path.join(pass1, f"{a}_commits.parquet"))
    ct = cm["commit_time"].to_numpy().astype("datetime64[s]")
    intro = mt.filter(pl.col("metric") == "AssetEODCompletionTime")["intro_commit"][0]
    post_gap = int(np.nonzero(ct > GAP_LAST_OLD)[0][0])
    d, fc, fv = c["date_idx"].to_numpy(), c["first_commit"].to_numpy(), c["first_val"].to_numpy()
    rt = ~((fc == intro) | ((fc == post_gap) & (d < (np.datetime64("2026-03-24") - EPOCH).astype(int))))
    day_end = (EPOCH + (d[rt] + 1).astype("timedelta64[D]")).astype("datetime64[s]").astype("int64")
    h = (fv[rt] - day_end) / 3600.0
    lines.append(f"{a} vendor-stated completion of the daily metrics (AssetEODCompletionTime as first published), hours after 24:00 UTC of the data day: "
                 f"n {int(rt.sum())}, median {np.median(h):.2f}, 90th pct {np.quantile(h, .9):.2f}, 99th pct {np.quantile(h, .99):.2f}, max {h.max():.1f}")
open(out_txt, "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
