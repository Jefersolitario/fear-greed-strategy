#!/usr/bin/env python
"""C1: panel integrity checks (no return predictability is evaluated here).
 1. data age at decision time in the V-sample
 2. V-sample (as-of commit) vs L-style (last vintage, d-2) signals: must be identical for never-revised metrics;
    the size of the gap for revised metrics shows how much hindsight the current file carries.
 3. usable observations per signal.
Usage: python -I scripts/c1_check_panels.py <data_dir> <out_txt>
"""
import os, sys
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signals import full_signals, PRIMARY
from config import V_METRICS, L_METRICS, SAMPLE
from cmgit import EPOCH

data_dir, out_txt = sys.argv[1:3]
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); lines.append(s)

for asset in ("btc", "eth"):
    V = pl.read_parquet(os.path.join(data_dir, f"{asset}_panel_V.parquet"))
    raw = pl.read_parquet(os.path.join(data_dir, f"{asset}_final_raw.parquet"))
    d = V["date"].to_numpy().astype("datetime64[D]")
    inV = (d >= SAMPLE["V"]["start"][asset]) & (d <= SAMPLE["V"]["end"])
    P(f"===== {asset}: V-sample decision days {d[inV][0]} .. {d[inV][-1]} ({inV.sum()} calendar days)")
    # 1. data age
    age = V["TxCnt|data_age"].to_numpy()[inV]
    vals, cnt = np.unique(np.clip(age, -1, 12), return_counts=True)
    P("  data age of TxCnt at decision time (days; 2 = normal, >9 = dropped as stale, 12 = 12 or more):",
      ", ".join(f"{v}:{c}" for v, c in zip(vals, cnt)))
    # 2. as-of vs last-vintage signals (same d-2 convention), for all V metrics that still exist in the last vintage
    rawd = {c: raw[c].to_numpy() for c in raw.columns if c != "date"}
    n_raw = raw.height
    fin = full_signals(rawd, metrics=V_METRICS[asset], variants={"lvl": ("lvl", 0, 365), "chg7": ("chg", 7, 365)})
    didx = (d - EPOCH).astype(int)
    P("  as-of (V) signal vs the same signal rebuilt from today's file, on days with normal data age (2):")
    P("    metric|variant                 n     share|diff|>1e-6  share|diff|>0.25sd  mean|diff|   corr")
    for m in V_METRICS[asset]:
        for v in PRIMARY:
            if (m, v) not in fin:
                continue
            f = fin[(m, v)]
            src = didx - 2
            ok_src = (src >= 0) & (src < n_raw)
            fv = np.full(len(d), np.nan); fv[ok_src] = f[src[ok_src]]
            a = V[f"{m}|{v}"].to_numpy()
            ok = inV & np.isfinite(a) & np.isfinite(fv) & (V[f"{m}|data_age"].to_numpy() == 2)
            if ok.sum() < 30:
                P(f"    {m+'|'+v:28s} {ok.sum():5d}   (not in today's file or too few common days)")
                continue
            diff = np.abs(a[ok] - fv[ok])
            P(f"    {m+'|'+v:28s} {ok.sum():5d}   {np.mean(diff > 1e-6):8.4f}          {np.mean(diff > 0.25):8.4f}        {diff.mean():8.4f}  {np.corrcoef(a[ok], fv[ok])[0,1]:7.4f}")
    # 3. usable observations
    for tag in ("V", "L"):
        Pn = pl.read_parquet(os.path.join(data_dir, f"{asset}_panel_{tag}.parquet"))
        dd = Pn["date"].to_numpy().astype("datetime64[D]")
        ins = (dd >= SAMPLE[tag]["start"][asset]) & (dd <= SAMPLE[tag]["end"])
        mets = V_METRICS[asset] if tag == "V" else L_METRICS[asset]
        P(f"  usable observations in the {tag}-sample (signal and 1-day return present): first .. last, n")
        for m in mets:
            a = Pn[f"{m}|lvl"].to_numpy(); r = Pn["r1"].to_numpy()
            ok = ins & np.isfinite(a) & np.isfinite(r)
            P(f"    {m:16s} {dd[ok][0] if ok.any() else '-'} .. {dd[ok][-1] if ok.any() else '-'}  n={ok.sum()}")
open(out_txt, "w").write("\n".join(lines) + "\n")
