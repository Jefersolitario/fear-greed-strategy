#!/usr/bin/env python
"""B1: build decision-day panels (PREREG.md sections C, D).

For each asset writes
  data/<asset>_final_raw.parquet       last vintage (2026-05-24) daily inputs
  data/<asset>_vintage_signals.parquet as-of signal values per commit and metric (point-in-time)
  data/<asset>_panel_L.parquet         long sample, last vintage, data through d-2
  data/<asset>_panel_L0.parquet        infeasible variant R5: data through d-1
  data/<asset>_panel_V.parquet         vintage sample: file exactly as committed before 00:00 UTC of d
Panel columns: date (decision day d), E (entry price = PriceUSD(d-1)), r1, r7, r30 (forward log returns),
PX_* price baselines, and "<metric>|<variant>" signals.

Usage: python -I scripts/b1_build_panels.py <repo_dir> <vintage_index.tsv> <out_dir>
"""
import os, sys, time, io
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmgit import read_index, BlobReader, EPOCH, ND, LEGACY_NCOMMITS
from signals import full_signals, last_signals, price_baselines, RAW_NEEDED, VARIANTS, PRIMARY
from config import V_METRICS, L_METRICS, HORIZONS, STALE_MAX, PX

repo, index_path, out_dir = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)
TAIL = 1500
dates_all = EPOCH + np.arange(ND).astype("timedelta64[D]")


def parse_needed(data):
    header = data[: data.find(b"\n")].decode().strip().split(",")
    tcol = "time" if "time" in header else "date"
    cols = [tcol] + [c for c in RAW_NEEDED if c in header]
    df = pl.read_csv(io.BytesIO(data), columns=cols, infer_schema_length=0)
    d = df[tcol].str.slice(0, 10).str.to_date().to_numpy().astype("datetime64[D]")
    didx = (d - EPOCH).astype(np.int64)
    out = {c: df[c].cast(pl.Float64, strict=False).to_numpy().astype(np.float64) for c in cols[1:]}
    return didx, out


def to_global(didx, cols):
    g = {}
    for c, v in cols.items():
        a = np.full(ND, np.nan); a[didx] = v; g[c] = a
    return g


rows = read_index(index_path)
rd = BlobReader(repo)
for asset in ("btc", "eth"):
    t0 = time.time()
    commits = [r for r in rows[LEGACY_NCOMMITS:] if r[asset] != "NA"]
    ctime = np.array([r["time"] for r in commits])
    assert np.all(np.diff(ctime.astype("int64")) > 0), "commit times must be strictly increasing"
    # ---------------- last vintage
    didx, cols = parse_needed(rd.read(commits[-1][asset]))
    final = to_global(didx, cols)
    last_idx = int(didx[-1])
    pl.DataFrame({"date": dates_all[: last_idx + 1], **{c: v[: last_idx + 1] for c, v in final.items()}}
                 ).write_parquet(os.path.join(out_dir, f"{asset}_final_raw.parquet"))
    P = final["PriceUSD"]
    lp = np.log(np.where(P > 0, P, np.nan))
    # ---------------- as-of signals per commit
    vm = V_METRICS[asset]
    rec = []
    prev_oid, prev_out = None, None
    for k, r in enumerate(commits):
        oid = r[asset]
        if oid != prev_oid:
            didx_k, cols_k = parse_needed(rd.read(oid))
            end = int(didx_k[-1])
            g = to_global(didx_k, cols_k)
            tail = {c: v[max(0, end - TAIL + 1): end + 1] for c, v in g.items()}
            ls = last_signals(tail, metrics=vm)
            prev_out = [(m, end - off, vals) for m, (off, vals) in ls.items()]
            prev_oid = oid
        for m, last_date, vals in prev_out:
            rec.append((k, m, last_date, *[vals[v] for v in VARIANTS]))
        if k % 400 == 0:
            print(f"{asset} as-of signals: commit {k}/{len(commits)} {r['time_str']} t={time.time()-t0:.0f}s", flush=True)
    vs = pl.DataFrame(rec, schema=["commit_idx", "metric", "last_date_idx"] + list(VARIANTS), orient="row")
    vs = vs.with_columns(pl.Series("commit_time", ctime[vs["commit_idx"].to_numpy()].astype("datetime64[us]")))
    vs.write_parquet(os.path.join(out_dir, f"{asset}_vintage_signals.parquet"))
    # ---------------- decision-day frame
    d = np.arange(ND)
    def at(arr, shift):            # value of a data-date-indexed array at data date d - shift
        out = np.full(ND, np.nan); out[shift:] = arr[: ND - shift]; return out
    E = at(P, 1)                   # entry price for decision day d = close of d-1
    base = {"date": dates_all, "E": E}
    lE = at(lp, 1)
    for h in HORIZONS:
        fwd = np.full(ND, np.nan); fwd[: ND - h] = lE[h:] - lE[: ND - h]
        base[f"r{h}"] = fwd
    px = price_baselines(P)        # indexed by data date t; decision day d sees closes through d-1
    for name in PX:
        base[name] = at(px[name], 1)
    keep = (d <= last_idx + 1)     # last decision day with an entry price: d-1 = last_idx
    # L (data through d-2) and L0 (data through d-1, infeasible)
    full = full_signals({c: final[c] for c in final}, metrics=L_METRICS[asset])
    for tag, shift in (("L", 2), ("L0", 1)):
        fr = dict(base)
        for (m, v), arr in full.items():
            if tag == "L0" and v not in PRIMARY:
                continue
            fr[f"{m}|{v}"] = at(arr, shift)
        pl.DataFrame(fr).filter(pl.Series(keep)).write_parquet(os.path.join(out_dir, f"{asset}_panel_{tag}.parquet"))
    # V: last commit strictly before 00:00 UTC of d
    day_start = dates_all.astype("datetime64[s]")
    kd = np.searchsorted(ctime, day_start, side="left") - 1      # commits with time < day_start
    fr = dict(base)
    fr["asof_commit_idx"] = kd.astype(np.int32)
    for m in vm:
        sub = vs.filter(pl.col("metric") == m)
        ci = sub["commit_idx"].to_numpy(); ld = sub["last_date_idx"].to_numpy()
        lastdate_by_commit = np.full(len(commits), -10**6); lastdate_by_commit[ci] = ld
        ok = (kd >= 0)
        ldd = np.where(ok, lastdate_by_commit[np.maximum(kd, 0)], -10**6)
        fresh = ok & (d - ldd <= STALE_MAX)
        fr[f"{m}|data_age"] = np.where(ok & (ldd > -10**6), d - ldd, -1).astype(np.int32)
        for v in VARIANTS:
            val_by_commit = np.full(len(commits), np.nan); val_by_commit[ci] = sub[v].to_numpy()
            fr[f"{m}|{v}"] = np.where(fresh, val_by_commit[np.maximum(kd, 0)], np.nan)
    pl.DataFrame(fr).filter(pl.Series(keep)).write_parquet(os.path.join(out_dir, f"{asset}_panel_V.parquet"))
    print(f"{asset}: panels written, {time.time()-t0:.0f}s")
rd.close()
