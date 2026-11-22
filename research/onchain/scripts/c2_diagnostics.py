#!/usr/bin/env python
"""C2: post-hoc diagnostics (NOT pre-registered; they explain the pre-registered results, they do not add tests
to the family).

 1. Calibration: distribution of the bootstrap p-values across each family.
 2. Power: smallest slope the tests could detect (80% power at a nominal two-sided 5%), per sample and horizon.
 3. Positive control: the same regression with 2 days of look-ahead (metric of day d used at 00:00 of day d).
 4. Hindsight contrast: revised metrics tested with real-time (as-of commit) values against the same metric rebuilt
    from today's file, on the same days; and the naive long backtest of today's exchange-flow history.
 5. Where the L-sample placebo distribution gets its width: |t| of the shifted signal by shift length.
 6. Nominal rejections per sub-period for every primary test.
 7. Independent recomputation of three headline numbers with pandas + statsmodels.
 8. The 7- and 30-day tests redone on non-overlapping periods (every h-th decision day, all h possible phases).

Usage: python -I scripts/c2_diagnostics.py <data_dir> <results_dir>
"""
import os, sys
import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import HORIZONS, HAC_LAG, SAMPLE, V_METRICS, L_METRICS
from signals import full_signals
from stats import hac_slope, p_two_sided, placebo_shift_tstats
from cmgit import EPOCH

data_dir, res = sys.argv[1:3]
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); lines.append(s)

S = pl.read_csv(os.path.join(res, "summary_tests.csv"), infer_schema_length=None)
load = lambda a, tag: (lambda df: {c: df[c].to_numpy() for c in df.columns})(pl.read_parquet(os.path.join(data_dir, f"{a}_panel_{tag}.parquet")))

P("=== 1. Calibration of the bootstrap p-values (a flat distribution is what a family of true nulls gives) ===")
for s in ("V", "L"):
    p = S.filter(pl.col("sample") == s)["p_boot"].to_numpy()
    P(f"{s}: n={len(p)}  share below 0.01/0.05/0.10/0.25/0.50/0.75: " + " / ".join(f"{(p < q).mean():.3f}" for q in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75)))

P("\n=== 2. Power: minimum detectable slope = 2.8 x HAC s.e. (80% power, nominal two-sided 5%), median over tests ===")
for s in ("V", "L"):
    for a in ("btc", "eth"):
        pan = load(a, s)
        d = pan["date"].astype("datetime64[D]")
        win = (d >= SAMPLE[s]["start"][a]) & (d <= SAMPLE[s]["end"])
        for h in HORIZONS:
            q = S.filter((pl.col("sample") == s) & (pl.col("asset") == a) & (pl.col("h") == h))
            sd_r = np.nanstd(pan[f"r{h}"][win]) * 100
            mde = 2.8 * float(q["se_pct"].median())
            P(f"{s} {a} h={h:2d}: median n {int(q['n'].median())}, sd of the {h}-day return {sd_r:.2f}%, minimum detectable slope {mde:.3f}% per 1 sd of signal "
              f"(= {mde / sd_r:.3f} return-sd; in-sample R2 {100 * (mde / sd_r) ** 2:.2f}%)")

P("\n=== 3. Positive control: 2 days of look-ahead (data of day d known at 00:00 of day d), L-sample metrics, h = 1 ===")
for a in ("btc", "eth"):
    raw = pl.read_parquet(os.path.join(data_dir, f"{a}_final_raw.parquet"))
    rawd = {c: raw[c].to_numpy() for c in raw.columns if c != "date"}
    dates = raw["date"].to_numpy().astype("datetime64[D]")
    fs = full_signals(rawd, metrics=L_METRICS[a], variants={"lvl": ("lvl", 0, 365), "chg7": ("chg", 7, 365)})
    lp = np.log(rawd["PriceUSD"])
    n = len(lp)
    # decision day d (index i): entry price = close of d-1 = lp[i-1]; r1 = lp[i] - lp[i-1]
    r1 = np.full(n, np.nan); r1[1:] = lp[1:] - lp[:-1]
    win = (dates >= SAMPLE["L"]["start"][a]) & (dates <= SAMPLE["L"]["end"])
    for m in L_METRICS[a]:
        for v in ("lvl", "chg7"):
            out = []
            for shift in (2, 1, 0):                       # data through d-2 (feasible), d-1, d (look-ahead)
                s_ = np.full(n, np.nan); s_[shift:] = fs[(m, v)][: n - shift] if shift else fs[(m, v)]
                ok = win & np.isfinite(s_) & np.isfinite(r1)
                b, se = hac_slope(s_[ok], r1[ok], HAC_LAG[1])
                out.append(b / se)
            P(f"{a} {m+'|'+v:18s} t(h=1): feasible d-2 {out[0]:+6.2f} | d-1 {out[1]:+6.2f} | same-day d {out[2]:+7.2f}")

P("\n=== 4. Hindsight contrast for revised metrics (same decision days; HAC t; real-time value vs today's file) ===")
for a in ("btc", "eth"):
    V = load(a, "V")
    raw = pl.read_parquet(os.path.join(data_dir, f"{a}_final_raw.parquet"))
    rawd = {c: raw[c].to_numpy() for c in raw.columns if c != "date"}
    n_raw = raw.height
    d = V["date"].astype("datetime64[D]")
    didx = (d - EPOCH).astype(int)
    mets = ["FlowInExNtv", "FlowOutExNtv", "NetFlowEx"] + (["CapMVRVCur", "CapRealUSD", "AdrActCnt"] if a == "eth" else [])
    fin = full_signals(rawd, metrics=mets, variants={"lvl": ("lvl", 0, 365), "chg7": ("chg", 7, 365)})
    for m in mets:
        for v in ("lvl", "chg7"):
            src = didx - 2
            oks = (src >= 0) & (src < n_raw)
            hind = np.full(len(d), np.nan); hind[oks] = fin[(m, v)][src[oks]]
            real = V[f"{m}|{v}"]
            txt = []
            for h in HORIZONS:
                y = V[f"r{h}"]
                ok = np.isfinite(real) & np.isfinite(hind) & np.isfinite(y) & (d >= SAMPLE["V"]["start"][a])
                br, ser = hac_slope(real[ok], y[ok], HAC_LAG[h]); bh_, seh = hac_slope(hind[ok], y[ok], HAC_LAG[h])
                txt.append(f"h={h}: real-time {br/ser:+.2f} vs today's file {bh_/seh:+.2f}")
            P(f"{a} {m+'|'+v:18s} n={int(ok.sum())}  " + " | ".join(txt))
    # naive long backtest of today's exchange-flow history (hindsight-contaminated: shown only as a warning)
    lp = np.log(rawd["PriceUSD"]); n = len(lp)
    dates = raw["date"].to_numpy().astype("datetime64[D]")
    win = (dates >= SAMPLE["L"]["start"][a]) & (dates <= SAMPLE["L"]["end"])
    fl = full_signals(rawd, metrics=["FlowInExNtv", "FlowOutExNtv", "NetFlowEx"], variants={"lvl": ("lvl", 0, 365), "chg7": ("chg", 7, 365)})
    for (m, v), arr in fl.items():
        txt = []
        for h in HORIZONS:
            s_ = np.full(n, np.nan); s_[2:] = arr[: n - 2]
            y = np.full(n, np.nan); y[1: n - h + 1] = lp[h:] - lp[: n - h]     # ln P[i-1+h] - ln P[i-1]
            ok = win & np.isfinite(s_) & np.isfinite(y)
            b, se = hac_slope(s_[ok], y[ok], HAC_LAG[h])
            txt.append(f"h={h}: t {b/se:+.2f} (p_hac {p_two_sided(b/se):.3f})")
        P(f"{a} NAIVE today's-file backtest {SAMPLE['L']['start'][a]}.. {m+'|'+v:18s} " + " | ".join(txt))

P("\n=== 5. L-sample placebo: |t| of the circularly shifted signal, by shift length (BTC, h = 7) ===")
L = load("btc", "L")
d = L["date"].astype("datetime64[D]")
win = (d >= SAMPLE["L"]["start"]["btc"]) & (d <= SAMPLE["L"]["end"])
for col in ("CapMVRVCur|lvl", "CapRealUSD|chg7", "FeeTotNtv|lvl"):
    ok = win & np.isfinite(L[col]) & np.isfinite(L["r1"])
    s_ = L[col][ok]; y = L["r7"][ok]; nh = int(np.isfinite(y).sum())
    ks, out = placebo_shift_tstats(s_, {7: y[:nh]}, HAC_LAG)
    t = out[7]
    bins = [(90, 365), (365, 730), (730, 1095), (1095, 1460), (1460, 1825), (1825, 2555), (2555, 3650), (3650, 6000)]
    P(f"{col}: actual t {hac_slope(s_[:nh], y[:nh], HAC_LAG[7])[0] / hac_slope(s_[:nh], y[:nh], HAC_LAG[7])[1]:+.2f}; shifts {len(ks)}; share |t|>1.96 {np.mean(np.abs(t) > 1.96):.2f}; "
      + "; ".join(f"{lo}-{hi}d: mean t {t[(ks >= lo) & (ks < hi)].mean():+.2f}, max|t| {np.abs(t[(ks >= lo) & (ks < hi)]).max():.1f}" for lo, hi in bins if ((ks >= lo) & (ks < hi)).any()))

P("\n=== 6. Nominal rejections (|t_HAC| > 1.96) per sub-period, all primary tests ===")
for s in ("V", "L"):
    q = S.filter(pl.col("sample") == s)
    names = [q[f"sub{i}_name"][0] for i in (1, 2, 3)]
    P(f"{s}: " + "; ".join(f"{nm}: {int((q[f'sub{i}_t'].abs() > 1.96).sum())} of {int(q[f'sub{i}_t'].is_not_null().sum())}" for i, nm in zip((1, 2, 3), names))
      + f"; whole sample: {int((q['t_hac'].abs() > 1.96).sum())} of {q.height}")

P("\n=== 7. Independent recomputation (pandas rolling + statsmodels HAC) of three headline numbers ===")
raw = pd.read_parquet(os.path.join(data_dir, "btc_final_raw.parquet"))
raw.index = pd.to_datetime(raw.pop("date"))
raw = raw.where(raw > 0)                       # non-positive inputs to a log are missing, as in the pipeline
px = np.log(raw["PriceUSD"])
def zs(x, W=365):
    return ((x - x.rolling(W, min_periods=300).mean()) / x.rolling(W, min_periods=300).std()).clip(-4, 4)
for name, y_ in (("CapMVRVCur|lvl", np.log(raw["CapMVRVCur"])), ("CapRealUSD|chg7", np.log(raw["CapMrktCurUSD"] / raw["CapMVRVCur"]).diff(7)),
                 ("FeeTotNtv|lvl", np.log(raw["FeeTotNtv"].rolling(7, min_periods=5).mean()))):
    sig = zs(y_)
    for h in ((7,) if "chg7" in name else (7, 30) if "Fee" in name else (7,)):
        df = pd.DataFrame({"s": sig.shift(2), "r": px.shift(-(h - 1)) - px.shift(1)}).loc["2012-01-01":"2026-05-23"].dropna()
        fit = sm.OLS(df["r"], sm.add_constant(df["s"])).fit(cov_type="HAC", cov_kwds=dict(maxlags=HAC_LAG[h], use_correction=False))
        ref = S.filter((pl.col("sample") == "L") & (pl.col("asset") == "btc") & (pl.col("metric") == name.split("|")[0]) & (pl.col("variant") == name.split("|")[1]) & (pl.col("h") == h))
        P(f"L btc {name} h={h}: independent b {100*fit.params['s']:.4f}% t {fit.tvalues['s']:.3f} n {len(df)} | pipeline b {ref['b_pct_per_sd'][0]:.4f}% t {ref['t_hac'][0]:.3f} n {ref['n'][0]}")

P("\n=== 8. Non-overlapping periods: every h-th decision day, heteroskedasticity-robust (White) t, median over the h phases ===")
for s_ in ("V", "L"):
    for a in ("btc", "eth"):
        pan = load(a, s_)
        d = pan["date"].astype("datetime64[D]")
        win = (d >= SAMPLE[s_]["start"][a]) & (d <= SAMPLE[s_]["end"])
        mets = V_METRICS[a] if s_ == "V" else L_METRICS[a]
        for h in (7, 30):
            tmed, nmed = [], []
            for m in mets:
                for v in ("lvl", "chg7"):
                    x_all, y_all = pan[f"{m}|{v}"], pan[f"r{h}"]
                    ts, ns = [], []
                    pos = np.nonzero(win)[0]
                    for ph in range(h):
                        idx = pos[ph::h]
                        ok = np.isfinite(x_all[idx]) & np.isfinite(y_all[idx])
                        if ok.sum() < 30:
                            continue
                        b, se = hac_slope(x_all[idx][ok], y_all[idx][ok], 0)     # lag 0 = White s.e.
                        ts.append(b / se); ns.append(int(ok.sum()))
                    if ts:
                        tmed.append(np.median(ts)); nmed.append(np.median(ns))
            tmed = np.array(tmed)
            P(f"{s_} {a} h={h:2d}: {len(tmed)} signals; median number of non-overlapping periods {int(np.median(nmed))}; "
              f"signals with median |t| > 1.96: {int((np.abs(tmed) > 1.96).sum())}; largest median |t| {np.abs(tmed).max():.2f}")
open(os.path.join(res, "diagnostics.txt"), "w").write("\n".join(lines) + "\n")
