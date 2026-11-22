#!/usr/bin/env python
"""A1: walk every committed vintage of csv/<asset>.csv in commit order and record, per (metric, date):
first-published value and commit, number of later changes, first/last change commit, largest deviation
from the first-published value, and the value in the last vintage. Also a per-(commit, metric) summary
and a cell-level change log.

Usage: python -I scripts/a1_vintage_pass.py <repo_dir> <vintage_index.tsv> <out_dir> <asset>
"""
import os, sys, time
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmgit import read_index, BlobReader, parse_vintage, ND, LEGACY_NCOMMITS, EPOCH

repo, index_path, out_dir, asset = sys.argv[1:5]
os.makedirs(out_dir, exist_ok=True)
RTOL = 1e-9  # relative tolerance: differences below this are number-formatting noise, not revisions

rows = read_index(index_path)
commits = [r for r in rows[LEGACY_NCOMMITS:] if r[asset] != "NA"]
nc = len(commits)
ctime = np.array([r["time"] for r in commits])
cday = (ctime.astype("datetime64[D]") - EPOCH).astype(np.int64)

rd = BlobReader(repo)
cur, first_val, first_commit, n_chg, first_chg, last_chg, max_dev, n_removed_cell = {}, {}, {}, {}, {}, {}, {}, {}
intro_commit, last_present = {}, {}
summ = []      # per commit x metric
ev_c, ev_m, ev_d, ev_old, ev_new = [], [], [], [], []
metric_ids = {}
t0 = time.time()
prev_oid = None
for k, r in enumerate(commits):
    oid = r[asset]
    if oid == prev_oid:
        continue
    prev_oid = oid
    didx, cols = parse_vintage(rd.read(oid))
    if np.any(np.diff(didx) <= 0):
        raise RuntimeError(f"non-increasing dates in commit {r['commit']}")
    for m, v in cols.items():
        if m not in cur:
            metric_ids[m] = len(metric_ids)
            cur[m] = np.full(ND, np.nan)
            first_val[m] = np.full(ND, np.nan)
            first_commit[m] = np.full(ND, -1, dtype=np.int32)
            n_chg[m] = np.zeros(ND, dtype=np.int32)
            first_chg[m] = np.full(ND, -1, dtype=np.int32)
            last_chg[m] = np.full(ND, -1, dtype=np.int32)
            max_dev[m] = np.zeros(ND)
            n_removed_cell[m] = np.zeros(ND, dtype=np.int32)
            intro_commit[m] = k
        last_present[m] = k
        new = np.full(ND, np.nan)
        new[didx] = v
        old = cur[m]
        has_new, has_old = ~np.isnan(new), ~np.isnan(old)
        is_first = has_new & (first_commit[m] < 0)
        scale = np.maximum(np.abs(np.nan_to_num(new)), np.abs(np.nan_to_num(old)))
        changed = has_new & has_old & (np.abs(np.nan_to_num(new) - np.nan_to_num(old)) > RTOL * scale)
        removed = has_old & ~has_new
        # first publication
        first_val[m][is_first] = new[is_first]
        first_commit[m][is_first] = k
        # changes
        if changed.any():
            ii = np.nonzero(changed)[0]
            n_chg[m][ii] += 1
            fc = first_chg[m][ii]
            first_chg[m][ii] = np.where(fc < 0, k, fc)
            last_chg[m][ii] = k
            ev_c.append(np.full(ii.size, k, dtype=np.int32)); ev_m.append(np.full(ii.size, metric_ids[m], dtype=np.int16))
            ev_d.append(ii.astype(np.int32)); ev_old.append(old[ii].copy()); ev_new.append(new[ii].copy())
        if removed.any():
            n_removed_cell[m][removed] += 1
        # as-of state: keep last known value where the new file has a hole (tracked via n_removed)
        upd = has_new
        old[upd] = new[upd]
        dev = np.abs(np.nan_to_num(old) - np.nan_to_num(first_val[m]))
        np.maximum(max_dev[m], np.where(first_commit[m] >= 0, dev, 0.0), out=max_dev[m])
        nn = np.nonzero(has_new)[0]
        summ.append((k, m, int(is_first.sum()), int(changed.sum()), int(removed.sum()),
                     int(nn[-1]) if nn.size else -1, int(has_new.sum()),
                     int((changed & (np.arange(ND) >= cday[k] - 30)).sum())))
    if k % 200 == 0:
        print(f"{asset} commit {k}/{nc} {r['time_str']} cols={len(cols)} events={sum(a.size for a in ev_c):,} t={time.time()-t0:.0f}s", flush=True)
rd.close()

# ---- outputs
metrics = sorted(cur, key=lambda m: metric_ids[m])
pl.DataFrame(dict(commit_idx=np.arange(nc, dtype=np.int32), commit=[r["commit"] for r in commits],
                  lineage=[r["lineage"] for r in commits], commit_time=ctime.astype("datetime64[us]"))
             ).write_parquet(os.path.join(out_dir, f"{asset}_commits.parquet"))
pl.DataFrame(summ, schema=["commit_idx", "metric", "n_first", "n_changed", "n_removed", "last_date_idx", "n_nonnull", "n_changed_recent30"],
             orient="row").write_parquet(os.path.join(out_dir, f"{asset}_commit_metric_summary.parquet"))
cells = []
for m in metrics:
    ii = np.nonzero(first_commit[m] >= 0)[0]
    cells.append(pl.DataFrame(dict(
        metric=np.full(ii.size, m), date_idx=ii.astype(np.int32),
        first_commit=first_commit[m][ii], first_val=first_val[m][ii], final_val=cur[m][ii],
        n_changes=n_chg[m][ii], first_change_commit=first_chg[m][ii], last_change_commit=last_chg[m][ii],
        max_abs_dev=max_dev[m][ii], n_removed=n_removed_cell[m][ii])))
pl.concat(cells).write_parquet(os.path.join(out_dir, f"{asset}_cells.parquet"))
pl.DataFrame(dict(metric=metrics, metric_id=[metric_ids[m] for m in metrics],
                  intro_commit=[intro_commit[m] for m in metrics], last_present_commit=[last_present[m] for m in metrics])
             ).write_parquet(os.path.join(out_dir, f"{asset}_metrics.parquet"))
if ev_c:
    pl.DataFrame(dict(commit_idx=np.concatenate(ev_c), metric_id=np.concatenate(ev_m), date_idx=np.concatenate(ev_d),
                      old=np.concatenate(ev_old), new=np.concatenate(ev_new))
                 ).write_parquet(os.path.join(out_dir, f"{asset}_change_events.parquet"), compression="zstd")
print(f"{asset}: {nc} commits, {len(metrics)} metrics, {sum(a.size for a in ev_c):,} cell changes, {time.time()-t0:.0f}s")
