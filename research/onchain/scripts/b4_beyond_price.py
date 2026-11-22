#!/usr/bin/env python
"""B4: does the on-chain signal add anything beyond price? (PREREG.md E.6 i-ii)

(i)  Joint regression r(d,h) = a + b*s(d) + c'PX(d) + e, PX = the four price-only baselines
     (7- and 30-day momentum, drawdown from the running high, price z-score; all trailing-standardised).
     Newey-West t of b, and a placebo in which only the on-chain signal is circularly shifted.
(ii) Expanding-window forecasts: price-only model against price + signal: incremental OOS R2 and Clark-West p;
     also the price-only model against the historical mean.
Writes results/beyond_price_<asset>.csv.

Usage: python -I scripts/b4_beyond_price.py <data_dir> <out_dir> <asset>
"""
import os, sys, time
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import HORIZONS, HAC_LAG, MIN_OBS, MIN_TRAIN_OOS, V_METRICS, L_METRICS, PX, SAMPLE, PRICE_BUILT
from stats import hac_slope, hac_partial, p_two_sided, placebo_shift_tstats, expanding_forecast, clark_west

data_dir, out_dir, asset = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)


def load(tag):
    df = pl.read_parquet(os.path.join(data_dir, f"{asset}_panel_{tag}.parquet"))
    return {c: df[c].to_numpy() for c in df.columns}


t0 = time.time()
out = []
for sample, mets in (("V", V_METRICS[asset]), ("L", L_METRICS[asset])):
    panel = load(sample)
    cfg = SAMPLE[sample]
    d = panel["date"].astype("datetime64[D]")
    win = (d >= cfg["start"][asset]) & (d <= cfg["end"])
    C_all = np.column_stack([panel[c] for c in PX])
    for m in mets:
        for v in ("lvl", "chg7"):
            s_all = panel[f"{m}|{v}"]
            ok = win & np.isfinite(s_all) & np.isfinite(panel["r1"]) & np.isfinite(C_all).all(axis=1)
            n = int(ok.sum())
            if n < MIN_OBS:
                continue
            s = s_all[ok]; C = C_all[ok]; dd = d[ok]
            r = {h: panel[f"r{h}"][ok] for h in HORIZONS}
            nh = {h: int(np.isfinite(r[h]).sum()) for h in HORIZONS}
            _, plc = placebo_shift_tstats(s, {h: r[h][: nh[h]] for h in HORIZONS}, HAC_LAG, C=C)
            # how much of the signal is explained by the price baselines
            Z = np.column_stack([np.ones(n), C])
            res = s - Z @ np.linalg.lstsq(Z, s, rcond=None)[0]
            r2_sig_on_px = 1.0 - res.var() / s.var()
            # full-grid arrays for the expanding forecasts
            sg = s_all[win]; Cg = C_all[win]; dg = d[win]
            for h in HORIZONS:
                y = r[h][: nh[h]]; x = s[: nh[h]]; Cc = C[: nh[h]]
                b, se = hac_partial(x, y, Cc, HAC_LAG[h])
                bu, seu = hac_slope(x, y, HAC_LAG[h])
                t = b / se
                tk = plc[h]
                yg = panel[f"r{h}"][win]
                ym = np.where(np.isfinite(sg), yg, np.nan)            # same days for all three forecasts
                f_mean = expanding_forecast(None, ym, h, MIN_TRAIN_OOS)
                f_px = expanding_forecast(Cg, ym, h, MIN_TRAIN_OOS)
                f_aug = expanding_forecast(np.column_stack([Cg, sg]), yg, h, MIN_TRAIN_OOS)
                ev = dg >= cfg["split"]
                ye = np.where(ev & np.isfinite(f_aug), yg, np.nan)
                r2_inc, cw_t, cw_p, n_oos = clark_west(ye, f_px, f_aug, HAC_LAG[h])
                r2_px, cwp_t, cwp_p, _ = clark_west(ye, f_mean, f_px, HAC_LAG[h])
                r2_aug, _, cwa_p, _ = clark_west(ye, f_mean, f_aug, HAC_LAG[h])
                out.append(dict(sample=sample, asset=asset, metric=m, variant=v, h=h, n=nh[h],
                                price_built=m in PRICE_BUILT, r2_signal_on_price=float(r2_sig_on_px),
                                b_uni_pct=100 * bu, t_uni=bu / seu,
                                b_joint_pct=100 * b, t_joint=t, p_joint_hac=float(p_two_sided(t)),
                                placebo_p_joint=float((1 + (np.abs(tk) >= abs(t)).sum()) / (len(tk) + 1)),
                                oos_n=n_oos, oos_r2_price_vs_mean=r2_px, cw_p_price_vs_mean=cwp_p,
                                oos_r2_aug_vs_mean=r2_aug, cw_p_aug_vs_mean=cwa_p,
                                oos_r2_incremental=r2_inc, cw_t_incremental=cw_t, cw_p_incremental=cw_p))
        print(f"{asset} {sample} {m} t={time.time()-t0:.0f}s", flush=True)
pl.DataFrame(out, infer_schema_length=None).write_csv(os.path.join(out_dir, f"beyond_price_{asset}.csv"))
print(f"{asset}: {len(out)} rows, {time.time()-t0:.0f}s")
