#!/usr/bin/env python
"""A5: compact audit table (markdown) from audit/audit_metric_stats.csv.
Usage: python -I scripts/a5_audit_table.py <audit_dir>
"""
import os, sys
import polars as pl

audit = sys.argv[1]
r = pl.read_csv(os.path.join(audit, "audit_metric_stats.csv"))
CUR = ["AdrActCnt", "AdrBalCnt", "TxCnt", "TxTfrCnt", "FeeTotNtv", "HashRate", "BlkCnt", "IssTotNtv", "IssTotUSD", "SplyCur",
       "SplyExpFut10yr", "CapMrktCurUSD", "CapMrktEstUSD", "CapMVRVCur", "FlowInExNtv", "FlowOutExNtv", "FlowInExUSD",
       "FlowOutExUSD", "SplyExNtv", "SplyExUSD", "volume_reported_spot_usd_1d", "PriceUSD", "PriceBTC", "ROI30d", "ROI1yr"]
OLD = ["CapRealUSD", "NVTAdj", "NVTAdj90", "TxTfrValAdjUSD", "SplyActPct1yr", "VelCur1yr", "FlowTfrFromExCnt", "RevUSD", "DiffMean"]

def pct(x, nd=1):
    return "-" if x is None or x != x else f"{100 * x:.{nd}f}%"
def num(x, nd=2):
    return "-" if x is None or x != x else (f"{x:.0f}" if abs(x) >= 100 else f"{x:.{nd}f}")
def short(c):
    return {"safe": "safe", "first-published/vintage only": "first-published only"}.get(c, "unusable (too few vintages)")

lines = []
for a in ("btc", "eth"):
    lines.append(f"\n### {a.upper()}\n")
    lines.append("| metric | in free file 2026-05 | class | real-time days | days revised | materially revised | median revision (% of level) | median revision (x typical daily change) | median days until last revision | revisions landing >30 d late | backfilled history materially revised | lag median (h) | lag p99 (h) | published within 24 h |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for grp in (CUR, OLD):
        for m in grp:
            q = r.filter((pl.col("asset") == a) & (pl.col("metric") == m))
            if q.height == 0:
                continue
            x = q.row(0, named=True)
            if a == "eth" and m == "HashRate":
                note = "unusable (ended at the Merge, 2022-09)"
            else:
                note = short(x["class"])
            lines.append(f"| {m} | {'yes' if x['in_final_file'] else 'no (dropped after 2025-06)'} | {note} | {x['n_rt']} | {pct(x['rt_share_revised'])} | {pct(x['rt_share_material'])} | "
                         f"{pct(x['rt_med_rel_level'], 2)} | {num(x['rt_med_rel_dchg'])} | {num(x['rev_delay_last_med_d'], 0)} | {pct(x['rev_share_last_after_30d'], 0)} | "
                         f"{pct(x['bf_share_material'])} | {num(x['lag_med_h'], 1)} | {num(x['lag_p99_h'], 1)} | {pct(x['lag_share_le24h'])} |")
cls = r.group_by("asset", "class").len().sort("asset", "class")
lines.append("\n### All columns ever published for the two assets, by class\n")
lines.append("| asset | class | number of columns |\n|---|---|---|")
for row in cls.iter_rows():
    lines.append(f"| {row[0]} | {row[1]} | {row[2]} |")
open(os.path.join(audit, "audit_table.md"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
