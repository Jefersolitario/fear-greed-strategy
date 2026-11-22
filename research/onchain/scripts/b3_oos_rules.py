#!/usr/bin/env python
"""B3: out-of-sample value (PREREG.md E.4, E.5 and the rule part of E.6).

(a) Expanding-window forecast against the expanding historical mean: OOS R2 and Clark-West p, per horizon.
(b) Long-or-flat rule: (direction, threshold) chosen on the training part by net Sharpe, evaluated once on the
    later part, 10 bps per unit of position change, against buy-and-hold and against the best price-only rule
    chosen on the same training days. Stationary-bootstrap intervals; circular-shift placebo.
Days without a usable signal (for example the 2025-06 .. 2026-03 hole of the V-sample) are left out for the rule
and for buy-and-hold alike, so both are measured on exactly the same days.
Writes results/oos_<asset>.csv and results/rules_<asset>.csv.

Usage: python -I scripts/b3_oos_rules.py <data_dir> <out_dir> <asset>
"""
import os, sys, time, zlib
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (SEED, HORIZONS, HAC_LAG, COST, ANN, B_RULE, BLOCK_RULE, MIN_OBS, MIN_TRAIN_OOS, V_METRICS,
                    L_METRICS, PX, SAMPLE, THETAS, DIRS, PRICE_BUILT)
from stats import (expanding_forecast, clark_west, rule_positions, rule_returns, perf, sharpe_rows,
                   stationary_bootstrap_idx)

data_dir, out_dir, asset = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)


def load(tag):
    df = pl.read_parquet(os.path.join(data_dir, f"{asset}_panel_{tag}.parquet"))
    return {c: df[c].to_numpy() for c in df.columns}


def best_rule(sig_cols, rs_train):
    """Pick (column index, q, theta) with the highest net Sharpe on the training days. sig_cols: list of arrays."""
    best = (-np.inf, None)
    for ci, s in enumerate(sig_cols):
        for q in DIRS:
            for th in THETAS:
                net, _ = rule_returns(rule_positions(s, q, th), rs_train, COST)
                sh = perf(net, ANN)["sharpe"]
                if sh > best[0] + 1e-12:
                    best = (sh, (ci, q, th))
    return best


def oos_rows(panel, col, sample, family, metric, variant):
    cfg = SAMPLE[sample]
    d = panel["date"].astype("datetime64[D]")
    win = (d >= cfg["start"][asset]) & (d <= cfg["end"])
    s = panel[col][win]; dd = d[win]
    rows = []
    if np.isfinite(s).sum() < MIN_OBS:
        return rows
    for h in HORIZONS:
        y = panel[f"r{h}"][win]
        ym = np.where(np.isfinite(s), y, np.nan)                 # benchmark sees the same days as the model
        f_mean = expanding_forecast(None, ym, h, MIN_TRAIN_OOS)
        f_sig = expanding_forecast(s[:, None], y, h, MIN_TRAIN_OOS)
        ev = dd >= cfg["split"]
        r2, t, p, n = clark_west(np.where(ev, y, np.nan), f_mean, f_sig, HAC_LAG[h])
        rows.append(dict(sample=sample, asset=asset, family=family, metric=metric, variant=variant, h=h,
                         oos_n=n, oos_first=str(dd[ev & np.isfinite(f_sig) & np.isfinite(y)][0]) if n else "",
                         oos_r2=r2, cw_t=t, cw_p=p))
    return rows


def rule_row(panel, col, sample, family, metric, variant, rng):
    cfg = SAMPLE[sample]
    d = panel["date"].astype("datetime64[D]")
    win = (d >= cfg["start"][asset]) & (d <= cfg["end"])
    ok = win & np.isfinite(panel[col]) & np.isfinite(panel["r1"])
    if ok.sum() < MIN_OBS:
        return None
    s = panel[col][ok]; dd = d[ok]
    rs = np.expm1(panel["r1"][ok])
    px = [panel[c][ok] for c in PX]
    tr = dd < cfg["split"]; te = ~tr
    if tr.sum() < 250 or te.sum() < 250:
        return None
    # ---- choose on the training part
    sh_tr, (_, q, th) = best_rule([s[tr]], rs[tr])
    shp_tr, (pci, pq, pth) = best_rule([p[tr] for p in px], rs[tr])
    bh_tr = perf(rule_returns(np.ones(tr.sum()), rs[tr], COST)[0], ANN)
    # ---- evaluate once on the later part
    pos = rule_positions(s[te], q, th)
    net, turn = rule_returns(pos, rs[te], COST)
    bh_net, _ = rule_returns(np.ones(te.sum()), rs[te], COST)
    ppos = rule_positions(px[pci][te], pq, pth)
    pnet, pturn = rule_returns(ppos, rs[te], COST)
    P, Bh, Pp = perf(net, ANN), perf(bh_net, ANN), perf(pnet, ANN)
    # ---- stationary bootstrap of the Sharpe differences (same resampled days for all three series)
    idx = stationary_bootstrap_idx(int(te.sum()), B_RULE, BLOCK_RULE, rng)
    sr, sb, sp = sharpe_rows(net[idx], ANN), sharpe_rows(bh_net[idx], ANN), sharpe_rows(pnet[idx], ANN)
    d_bh, d_px = sr - sb, sr - sp
    # ---- placebo: same (q, theta), signal circularly shifted over the whole usable sample
    n = len(s)
    ks = np.arange(90, n - 90 + 1, 7)
    plc = np.empty(len(ks))
    for i, k in enumerate(ks):
        nk, _ = rule_returns(rule_positions(np.roll(s, k)[te], q, th), rs[te], COST)
        plc[i] = perf(nk, ANN)["sharpe"]
    return dict(sample=sample, asset=asset, family=family, metric=metric, variant=variant,
                price_built=metric in PRICE_BUILT,
                train_first=str(dd[tr][0]), train_last=str(dd[tr][-1]), train_n=int(tr.sum()),
                test_first=str(dd[te][0]), test_last=str(dd[te][-1]), test_n=int(te.sum()),
                rule_dir=int(q), rule_theta=float(th),
                train_sharpe=sh_tr, train_sharpe_bh=bh_tr["sharpe"],
                test_cagr=P["cagr"], test_sharpe=P["sharpe"], test_maxdd=P["maxdd"], test_vol=P["vol"],
                test_time_in_market=float(pos.mean()), test_trades=float(turn.sum()),
                bh_cagr=Bh["cagr"], bh_sharpe=Bh["sharpe"], bh_maxdd=Bh["maxdd"], bh_vol=Bh["vol"],
                dsharpe_vs_bh=P["sharpe"] - Bh["sharpe"],
                dsharpe_vs_bh_lo=float(np.quantile(d_bh, 0.025)), dsharpe_vs_bh_hi=float(np.quantile(d_bh, 0.975)),
                dsharpe_vs_bh_p=float((1 + (d_bh <= 0).sum()) / (B_RULE + 1)),
                placebo_sharpe_median=float(np.median(plc)), placebo_sharpe_q95=float(np.quantile(plc, 0.95)),
                placebo_p=float((1 + (plc >= P["sharpe"]).sum()) / (len(plc) + 1)), placebo_n=int(len(plc)),
                px_rule=f"{PX[pci]} dir={pq:+d} theta={pth:+.1f}", px_train_sharpe=shp_tr,
                px_test_cagr=Pp["cagr"], px_test_sharpe=Pp["sharpe"], px_test_maxdd=Pp["maxdd"],
                px_test_time_in_market=float(ppos.mean()), px_test_trades=float(pturn.sum()),
                dsharpe_vs_px=P["sharpe"] - Pp["sharpe"],
                dsharpe_vs_px_lo=float(np.quantile(d_px, 0.025)), dsharpe_vs_px_hi=float(np.quantile(d_px, 0.975)),
                dsharpe_vs_px_p=float((1 + (d_px <= 0).sum()) / (B_RULE + 1)))


t0 = time.time()
panels = {tag: load(tag) for tag in ("V", "L")}
oos, rules = [], []
for sample, mets in (("V", V_METRICS[asset]), ("L", L_METRICS[asset])):
    units = [(f"{m}|{v}", "primary", m, v) for m in mets for v in ("lvl", "chg7")] + [(c, "price_baseline", c, "px") for c in PX]
    for col, fam, m, v in units:
        oos.extend(oos_rows(panels[sample], col, sample, fam, m, v))
        rng = np.random.default_rng([SEED, 3, zlib.crc32(f"{sample}|{asset}|{col}".encode())])
        r = rule_row(panels[sample], col, sample, fam, m, v, rng)
        if r is not None:
            rules.append(r)
    print(f"{asset} {sample} done t={time.time()-t0:.0f}s", flush=True)
pl.DataFrame(oos, infer_schema_length=None).write_csv(os.path.join(out_dir, f"oos_{asset}.csv"))
pl.DataFrame(rules, infer_schema_length=None).write_csv(os.path.join(out_dir, f"rules_{asset}.csv"))
print(f"{asset}: {len(oos)} OOS rows, {len(rules)} rule rows, {time.time()-t0:.0f}s")
