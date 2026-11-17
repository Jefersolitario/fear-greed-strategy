"""Backtests for the indicators that survive the elimination rule, plus a price-only stand-in for the
Fear & Greed index before February 2018, plus cross-checks of the estimated 2026 MVRV and of CBBI restatement.

Usage: python cycle3.py indicators2.parquet flags2.npz btc_ext.parquet cycle_scripts_dir out.json
"""
import datetime as dt
import json
import sys

import numpy as np
import polars as pl

ind_path, flags_path, ext_path, lib_dir, out_path = sys.argv[1:6]
sys.path.insert(0, lib_dir)
import cyclelib as cl  # noqa: E402

D = dt.date
ind = pl.read_parquet(ind_path).sort("date")
F = dict(np.load(flags_path))
E = pl.read_parquet(ext_path).sort("date")
dates = ind["date"].to_list()
ix = {d: i for i, d in enumerate(dates)}
n = len(dates)
p = ind["price"].to_numpy()
fng = ind["fng"].to_numpy()
mvrv = ind["mvrv"].to_numpy()
cbbi = ind["cbbi"].to_numpy()
out = {}

# ---------- cross-checks against figures published by others ----------
print("MVRV estimate vs published figures (Aug-Nov 2026 is the estimated stretch):")
for d, pub in ((D(2026, 6, 30), "about 1.10 ('around 10% above the realized price')"), (D(2026, 8, 28), "near 1.5"), (D(2026, 10, 8), "1.54"), (D(2026, 11, 3), "1.43 ($1.56T / $1.09T)")):
    print(f"  {d}: mine {mvrv[ix[d]]:.3f} at ${p[ix[d]]:,.0f}   published: {pub}")
print("CBBI in today's file vs what was published at the time:")
for d0, d1, pub in ((D(2025, 1, 1), D(2025, 2, 28), "peak 88 in Jan-Feb 2025"), (D(2025, 3, 25), D(2025, 3, 25), "about 70"), (D(2025, 5, 19), D(2025, 5, 19), "76"),
                    (D(2025, 6, 15), D(2025, 6, 15), "75"), (D(2025, 9, 16), D(2025, 9, 16), "75"), (D(2025, 9, 20), D(2025, 10, 20), "74-75 around the top")):
    seg = cbbi[ix[d0]:ix[d1] + 1]
    print(f"  {d0}..{d1}: today's file max {np.nanmax(seg):.1f}   published then: {pub}")

# ---------- price-only stand-in for Fear & Greed ----------
lr = np.r_[np.nan, np.diff(np.log(p))]
def roll(x, w, f):
    o = np.full(n, np.nan)
    for t in range(w - 1, n):
        o[t] = f(x[t - w + 1:t + 1])
    return o
vol30, vol90, vol365 = roll(lr, 30, np.nanstd), roll(lr, 90, np.nanstd), roll(lr, 365, np.nanstd)
ma30, ma90 = cl._rolling_mean(p, 30), cl._rolling_mean(p, 90)
mx30, mx90 = roll(p, 30, np.max), roll(p, 90, np.max)
ret7 = np.r_[np.full(7, np.nan), np.log(p[7:] / p[:-7])]
ret30 = np.r_[np.full(30, np.nan), np.log(p[30:] / p[:-30])]
X = np.c_[np.ones(n), np.log(p / ma30), np.log(p / ma90), p / mx30 - 1, p / mx90 - 1, ret7, ret30, vol30 / vol365, vol90 / vol365, vol30 / vol90]
have = np.isfinite(fng) & np.isfinite(X).all(axis=1)
d_ord = np.array([d.toordinal() for d in dates])
split = D(2022, 6, 30).toordinal()
tr, te = have & (d_ord <= split), have & (d_ord > split)

def fit_eval(train, test, label):
    b = np.linalg.lstsq(X[train], fng[train], rcond=None)[0]
    px = X @ b
    res = {}
    for th in (20, 10):
        share = float((fng[train] < th).mean())
        cut = float(np.quantile(px[train], share))          # flag the same share of days as the real index did in training
        a, f_ = fng[test] < th, px[test] < cut
        prec = float((a & f_).sum() / max(f_.sum(), 1)); rec = float((a & f_).sum() / max(a.sum(), 1))
        # episode level: real episodes (gap > 14d) with a stand-in day within 7 days, and the reverse
        ti = np.where(test)[0]
        def eps(mask):
            ii = ti[mask]
            if len(ii) == 0:
                return []
            cuts = np.where(np.diff(ii) > 14)[0]
            return list(zip(np.r_[ii[0], ii[cuts + 1]], np.r_[ii[cuts], ii[-1]]))
        ea, ef = eps(a), eps(f_)
        fa = np.where(test & (px < cut))[0]; aa = np.where(test & (fng < th))[0]
        hit_a = sum(1 for s, e in ea if ((fa >= s - 7) & (fa <= e + 7)).any())
        hit_f = sum(1 for s, e in ef if ((aa >= s - 7) & (aa <= e + 7)).any())
        res[th] = dict(cut=cut, precision=prec, recall=rec, real_days=int(a.sum()), standin_days=int(f_.sum()), real_eps=len(ea), real_eps_found=hit_a, standin_eps=len(ef), standin_eps_real=hit_f)
        print(f"  {label} <{th}: corr {np.corrcoef(px[test], fng[test])[0, 1]:.2f} | real days {int(a.sum())}, stand-in days {int(f_.sum())}, precision {prec:.0%}, recall {rec:.0%} | "
              f"real episodes found {hit_a}/{len(ea)}, stand-in episodes that were real {hit_f}/{len(ef)}")
    return b, px, res

print("\nFear & Greed stand-in from price only (momentum, drawdown, volatility):")
_, _, r1 = fit_eval(tr, te, "fit to Jun-2022, test after")
_, _, r2 = fit_eval(te, tr, "fit after Jun-2022, test before")
b, proxy, r3 = fit_eval(have, have, "fit on everything (in-sample)")
out["proxy"] = {"oos_fwd": r1, "oos_back": r2, "in_sample": r3}
cut20, cut10 = r3[20]["cut"], r3[10]["cut"]
proxy_ok = np.isfinite(X).all(axis=1)

# ---------- backtests ----------
def run(mask, start, end=None, label=""):
    i0 = ix[start]; i1 = ix[end] if end else n - 1
    m = np.zeros(n, bool); m[i0:i1 + 1] = mask[i0:i1 + 1]
    close = p[i0:]
    sim = cl.simulate(close, m[i0:])
    met = cl.metrics(sim)
    v = cl.per_buy_value(close)
    allowed = np.zeros(len(close), bool); allowed[:i1 - i0 + 1] = True
    w = np.where(allowed, v, 0.0)
    pk, ck = cl.placebo(m[i0:], w, allowed)
    with np.errstate(divide="ignore", invalid="ignore"):
        rk = pk / (ck * cl.STAKE)
    ok = ck > 0
    p_ret = float((rk[ok] >= rk[0] - 1e-12).mean()) if met["buys"] else None
    base_ret = float(w[allowed].mean() / cl.STAKE)
    eps = 0
    ii = np.where(m)[0]
    if len(ii):
        eps = 1 + int((np.diff(ii) > 90).sum())
    r = dict(label=label, start=str(start), end=str(dates[i1]), buys=met["buys"], put_in=met["put_in"], pnl=met["net_pnl"], ret=met["ret"], sharpe=met["sharpe"],
             max_dd=met["max_dd"], placebo_p_ret=p_ret, every_day_ret=base_ret, episodes=eps)
    return r

def show(r):
    if not r["buys"]:
        print(f"  {r['label']:44s} no buys"); return
    print(f"  {r['label']:44s} buys {r['buys']:4d} in {r['episodes']:2d} eps | PnL ${r['pnl']:>12,.0f} | return {r['ret']:>7.0%} (every-day buyer {r['every_day_ret']:.0%}) | Sharpe {r['sharpe']:.2f} | maxDD ${r['max_dd']:>11,.0f} | placebo p {r['placebo_p_ret']:.2f}")

f20 = cl.lag1(np.zeros(n, bool))  # placeholder
f20 = np.where(np.isfinite(fng), fng < 20, False)       # index stamped D is known before the close of D
f10 = np.where(np.isfinite(fng), fng < 10, False)
GATES = {"no gate": np.ones(n, bool), "MVRV < 1": F["mvrv|lit|cheap"], "Mayer < 0.8": F["mayer|lit|cheap"], "price < 2-year MA": F["ma2y|lit|cheap"],
         "MVRV in lowest 20% of last 4y": F["mvrv_r4y|20|cheap"], "MVRV in lowest 10% of last 4y": F["mvrv_r4y|adapt|cheap"],
         "MVRV within 50% of 4y floor": F["mvrv_floor4y|+50%|cheap"], "CBBI < 15 (today's file, hindsight)": F["cbbi|15/85|cheap"]}
res = []
print("\nA. Real Fear & Greed under 20, Feb 2018 - Nov 2026, with each gate (hold, no exit):")
for k, gm in GATES.items():
    r = run(f20 & gm, D(2018, 2, 1), label=f"F&G<20 & {k}"); r["set"] = "A"; res.append(r); show(r)
print("\nA10. Real Fear & Greed under 10 with each gate:")
for k in ("no gate", "Mayer < 0.8", "price < 2-year MA", "MVRV in lowest 20% of last 4y"):
    r = run(f10 & GATES[k], D(2018, 2, 1), label=f"F&G<10 & {k}"); r["set"] = "A10"; res.append(r); show(r)
print("\nB. Gate alone, $1,000 on every day the gate is on, Jan 2014 - Nov 2026 (covers the 2014-2018 cycle; no Fear & Greed needed):")
for k, gm in GATES.items():
    if k == "no gate":
        continue
    r = run(gm, D(2014, 1, 1), label=k); r["set"] = "B"; res.append(r); show(r)
print("\nB2. Same, buys restricted to the 2014-2018 cycle (Jan 2014 - Jan 2018), value at Nov 2026:")
for k, gm in GATES.items():
    if k == "no gate":
        continue
    r = run(gm, D(2014, 1, 1), D(2018, 1, 31), label=k); r["set"] = "B2"; res.append(r); show(r)
pm20 = proxy_ok & (proxy < cut20)
print("\nC. Stand-in for F&G<20 (price-only), buys Jan 2014 - Jan 2018, value at Nov 2026:")
for k in ("no gate", "MVRV < 1", "Mayer < 0.8", "price < 2-year MA", "MVRV in lowest 20% of last 4y", "MVRV within 50% of 4y floor"):
    r = run(pm20 & GATES[k], D(2014, 1, 1), D(2018, 1, 31), label=f"stand-in<20 & {k}"); r["set"] = "C"; res.append(r); show(r)
print("\nC2. Sanity: stand-in vs real index over the period where both exist (Feb 2018 - Nov 2026):")
for lab, m in (("real F&G<20", f20), ("stand-in<20", pm20)):
    r = run(m, D(2018, 2, 1), label=lab); r["set"] = "C2"; res.append(r); show(r)
print("\nD. Buys valued one cycle later instead of today (2014-2018 buys valued at 31 Jan 2018 would be flattering; show value at the Dec-2018 low):")
i_low18 = ix[D(2018, 12, 15)]
for lab, m in (("stand-in<20, no gate", pm20), ("Mayer < 0.8", GATES["Mayer < 0.8"]), ("price < 2-year MA", GATES["price < 2-year MA"]), ("MVRV < 1", GATES["MVRV < 1"])):
    i0, i1 = ix[D(2014, 1, 1)], ix[D(2018, 1, 31)]
    mm = np.zeros(n, bool); mm[i0:i1 + 1] = m[i0:i1 + 1]
    btc = (cl.STAKE * (1 - cl.COST) / p[mm]).sum(); put = cl.STAKE * mm.sum()
    if put:
        print(f"  {lab:28s} buys {int(mm.sum()):4d}, avg cost ${put / btc:,.0f}; at the Dec-2018 low ($3,185): {btc * p[i_low18] / put - 1:+.0%}; worst point before Jan 2018: {np.min([(cl.STAKE * (1 - cl.COST) / p[i0:t + 1][mm[i0:t + 1]]).sum() * p[t] / (cl.STAKE * mm[i0:t + 1].sum()) - 1 for t in range(i0, i1 + 1) if mm[i0:t + 1].any()]):+.0%}")
out["runs"] = res
print("\nstate now:", dates[-1], f"price ${p[-1]:,.0f}, F&G {fng[-1]:.0f}, stand-in {proxy[-1]:.0f} (cut {cut20:.1f}), MVRV {mvrv[-1]:.2f}, CBBI {cbbi[-1]:.1f}")
print("F&G<20 days since the Oct-2025 high:", int(f20[ix[D(2025, 10, 6)]:].sum()), "| since 1 Aug 2026:", int(f20[ix[D(2026, 8, 1)]:].sum()), "| last 10 days F&G:", [int(x) for x in fng[-10:]])
json.dump(out, open(out_path, "w"), indent=1, default=float)
