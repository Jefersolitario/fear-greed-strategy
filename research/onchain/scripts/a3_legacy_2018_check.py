#!/usr/bin/env python
"""A3: deep-history check. Compare the July-2018 vintage (old schema) with the 2020-01-24 vintage and with the
last vintage for the columns that can be mapped by name. Shows whether the history that existed before the daily
commits began (2020-01-24) had already been restated once.

Usage: python -I scripts/a3_legacy_2018_check.py <repo_dir> <vintage_index.tsv> <out_csv>
"""
import os, sys
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmgit import read_index, BlobReader, parse_vintage, ND

repo, index_path, out_csv = sys.argv[1:4]
rows = read_index(index_path)
MAP = {"activeAddresses": "AdrActCnt", "txCount": "TxCnt", "paymentCount": "TxTfrCnt", "blockCount": "BlkCnt",
       "fees": "FeeTotNtv", "generatedCoins": "IssTotNtv", "price(USD)": "PriceUSD", "marketcap(USD)": "CapMrktCurUSD",
       "averageDifficulty": "DiffMean", "adjustedTxVolume(USD)": "TxTfrValAdjUSD", "txVolume(USD)": "TxTfrValUSD"}
rd = BlobReader(repo)
legacy, v2020, last = rows[3], rows[4], rows[-1]
out = []
for asset in ("btc", "eth"):
    def load(r):
        data = rd.read(r[asset])
        if r is legacy:  # 2018 files carry a trailing comma on data lines: drop it before parsing
            data = b"\n".join(l[:-1] if l.endswith(b",") else l for l in data.split(b"\n"))
        didx, cols = parse_vintage(data)
        full = {}
        for c, v in cols.items():
            a = np.full(ND, np.nan); a[didx] = v; full[c] = a
        return full
    L, V, F = load(legacy), load(v2020), load(last)
    for old, new in MAP.items():
        if old not in L:
            continue
        for label, T in (("2020-01-24 vintage", V), ("last vintage 2026-05-24", F)):
            if new not in T:
                continue
            a, b = L[old], T[new]
            both = ~np.isnan(a) & ~np.isnan(b)
            # ignore the very early years where counts are tiny: compare from 2012-01-01 (btc) / 2016-01-01 (eth)
            start = (np.datetime64("2012-01-01" if asset == "btc" else "2016-01-01") - np.datetime64("2009-01-01")).astype(int)
            both[:start] = False
            if both.sum() == 0:
                continue
            rel = np.abs(a[both] - b[both]) / np.maximum(np.abs(b[both]), 1e-300)
            out.append(dict(asset=asset, legacy_column=old, column=new, compared_with=label, n_dates=int(both.sum()),
                            share_differs_gt_1e9=float((rel > 1e-9).mean()), share_differs_gt_1pct=float((rel > 0.01).mean()),
                            share_differs_gt_10pct=float((rel > 0.10).mean()), median_rel_diff=float(np.median(rel)),
                            p95_rel_diff=float(np.quantile(rel, 0.95))))
rd.close()
df = pl.DataFrame(out)
df.write_csv(out_csv)
with pl.Config(tbl_rows=100, tbl_cols=20, tbl_width_chars=220, fmt_str_lengths=40):
    print("legacy vintage:", legacy["time_str"], legacy["commit"])
    print(df)
