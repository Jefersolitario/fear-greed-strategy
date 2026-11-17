"""Top-3 surviving cycle filters: backtest since 2013 (filter alone) and since Feb 2018 (with Fear & Greed < 20).

Rules: the filter is read on day D-1; $1,000 is bought at the UTC close of day D; 10 bps cost; hold, no exit.
Usage: python cycle4.py indicators2.parquet flags2.npz cycle_scripts_dir out_dir
"""
import datetime as dt
import json
import sys

import numpy as np
import polars as pl

ind_path, flags_path, lib_dir, out_dir = sys.argv[1:5]
sys.path.insert(0, lib_dir)
import cyclelib as cl  # noqa: E402

D = dt.date
ind = pl.read_parquet(ind_path).sort("date")
F = dict(np.load(flags_path))
dates = ind["date"].to_list()
ix = {d: i for i, d in enumerate(dates)}
n = len(dates)
p = ind["price"].to_numpy()
fng = ind["fng"].to_numpy()
f20 = np.where(np.isfinite(fng), fng < 20, False)
FILTERS = {"mvrv20": ("MVRV in lowest 20% of last 4 years", F["mvrv_r4y|20|cheap"]),
           "mayer": ("Mayer multiple below 0.8", F["mayer|lit|cheap"]),
           "ma2y": ("Price below 2-year average", F["ma2y|lit|cheap"])}
CYCLES = [("2013-14", D(2013, 1, 1), D(2014, 6, 30)), ("2014-16 bear", D(2014, 7, 1), D(2016, 12, 31)), ("2018-19 bear", D(2018, 1, 1), D(2019, 12, 31)),
          ("2020 crash", D(2020, 1, 1), D(2020, 12, 31)), ("2022-23 bear", D(2021, 12, 1), D(2023, 12, 31)), ("2025-26", D(2025, 10, 6), dates[-1])]


def run(mask, start, label):
    i0 = ix[start]
    m = mask[i0:].copy()
    close = p[i0:]
    sim = cl.simulate(close, m)
    met = cl.metrics(sim)
    pnl = sim["pnl"]
    first = sim["first"]
    # account value, drawdown of cumulative PnL
    btc = np.cumsum(np.where(m, cl.STAKE * (1 - cl.COST) / close, 0.0))
    val = btc * close
    path = pnl[first:]
    peak = np.maximum.accumulate(path)
    j = int(np.argmax(peak - path)); jp = int(np.argmax(path[:j + 1]))
    dd = float(peak[j] - path[j])
    dd_pct = dd / val[first + jp]
    # per dollar at risk: daily return on the BTC already held
    r = close[first + 1:] / close[first:-1] - 1
    sh_d = float(r.mean() / r.std(ddof=1) * np.sqrt(365))
    dn = np.sqrt(np.mean(np.minimum(r, 0) ** 2)); so_d = float(r.mean() / dn * np.sqrt(365))
    # same money spread evenly over every day of the window, and the date-shift placebo
    v = cl.per_buy_value(close)
    allowed = np.ones(len(close), bool)
    pk, ck = cl.placebo(m, v, allowed)
    rk = pk / (ck * cl.STAKE)
    even_ret = float(v.mean() / cl.STAKE)
    cyc = {}
    for name, a, b in CYCLES:
        if b < start:
            continue
        s = np.zeros(len(close), bool); s[max(ix[a] - i0, 0):ix[b] - i0 + 1] = True
        k = m & s
        if k.any():
            cyc[name] = dict(buys=int(k.sum()), avg_cost=float(k.sum() * cl.STAKE / (cl.STAKE * (1 - cl.COST) / close[k]).sum()),
                             first=str(dates[i0 + int(np.argmax(k))]), last=str(dates[i0 + len(k) - 1 - int(np.argmax(k[::-1]))]))
    out = dict(label=label, start=str(dates[i0 + first]), buys=met["buys"], put_in=met["put_in"], pnl=met["net_pnl"], ret=met["ret"],
               sharpe=met["sharpe"], sortino=met["sortino"], sharpe_per_dollar=sh_d, sortino_per_dollar=so_d,
               max_dd=dd, max_dd_pct=float(dd_pct), dd_peak=str(dates[i0 + first + jp]), dd_trough=str(dates[i0 + first + j]),
               even_ret=even_ret, even_pnl=even_ret * met["put_in"], placebo_p=float((rk >= rk[0] - 1e-12).mean()),
               avg_cost=float(met["put_in"] / btc[-1]), on_now=bool(m[-1]), cycles=cyc)
    return out, pnl


res = {"since2013": {}, "since2018": {}}
curves = {"date": dates[ix[D(2013, 1, 1)]:]}
print("=== Filter alone, $1,000 on every day the filter is on, 1 Jan 2013 - 14 Nov 2026, hold ===")
for k, (lab, m) in FILTERS.items():
    r, pnl = run(m, D(2013, 1, 1), lab)
    res["since2013"][k] = r; curves[f"a_{k}"] = pnl
    print(f"{lab}\n  buys {r['buys']} (first {r['start']}), in ${r['put_in']:,.0f}, PnL ${r['pnl']:,.0f}, return {r['ret']:.0%}, avg cost ${r['avg_cost']:,.0f}\n"
          f"  Sharpe {r['sharpe']:.2f} / Sortino {r['sortino']:.2f} on dollar PnL; per dollar at risk {r['sharpe_per_dollar']:.2f} / {r['sortino_per_dollar']:.2f}\n"
          f"  max DD ${r['max_dd']:,.0f} ({r['max_dd_pct']:.0%} of account value) {r['dd_peak']} -> {r['dd_trough']}\n"
          f"  same money spread evenly: return {r['even_ret']:.0%} (PnL ${r['even_pnl']:,.0f}); placebo p {r['placebo_p']:.2f}; on now: {r['on_now']}")
    for c, d in r["cycles"].items():
        print(f"     {c:13s} {d['buys']:4d} buys {d['first']} .. {d['last']}  avg cost ${d['avg_cost']:,.0f}")
r, pnl = run(np.ones(n, bool), D(2013, 1, 1), "Buy every day")
res["since2013"]["every"] = r
print(f"Buy every day: buys {r['buys']}, PnL ${r['pnl']:,.0f}, return {r['ret']:.0%}, Sharpe {r['sharpe']:.2f} (per $ {r['sharpe_per_dollar']:.2f}), max DD ${r['max_dd']:,.0f} ({r['max_dd_pct']:.0%})")

i18 = ix[D(2018, 2, 1)]
c18 = {"date": dates[i18:]}
print("\n=== Fear & Greed under 20 AND filter, 1 Feb 2018 - 14 Nov 2026, hold ===")
for k, (lab, m) in {"none": ("Fear & Greed under 20, no filter", np.ones(n, bool)), **FILTERS}.items():
    r, pnl = run(f20 & m, D(2018, 2, 1), lab)
    res["since2018"][k] = r; c18[f"b_{k}"] = pnl
    print(f"{lab}\n  buys {r['buys']}, in ${r['put_in']:,.0f}, PnL ${r['pnl']:,.0f}, return {r['ret']:.0%}, avg cost ${r['avg_cost']:,.0f} | Sharpe {r['sharpe']:.2f} / Sortino {r['sortino']:.2f} (per $ {r['sharpe_per_dollar']:.2f}) | "
          f"max DD ${r['max_dd']:,.0f} ({r['max_dd_pct']:.0%}) {r['dd_peak']} -> {r['dd_trough']} | even-spend {r['even_ret']:.0%} | p {r['placebo_p']:.2f}")
    print("     " + "; ".join(f"{c}: {d['buys']} @ ${d['avg_cost']:,.0f}" for c, d in r["cycles"].items()))

pl.DataFrame(curves).write_parquet(f"{out_dir}/curves_2013.parquet")
pl.DataFrame(c18).write_parquet(f"{out_dir}/curves_2018.parquet")
json.dump(res, open(f"{out_dir}/top3.json", "w"), indent=1)
# overlap between the three filters since 2013
i0 = ix[D(2013, 1, 1)]
a, b, c = (FILTERS[k][1][i0:] for k in ("mvrv20", "mayer", "ma2y"))
print(f"\noverlap since 2013: days on  mvrv20 {a.sum()}, mayer {b.sum()}, ma2y {c.sum()}; all three {(a & b & c).sum()}; any {(a | b | c).sum()}; "
      f"mayer inside ma2y {(b & c).sum() / b.sum():.0%}; mvrv20 inside ma2y {(a & c).sum() / a.sum():.0%}")
r, _ = run(FILTERS["mvrv20"][1] & FILTERS["mayer"][1] & FILTERS["ma2y"][1], D(2013, 1, 1), "all three on")
print(f"all three on together: buys {r['buys']}, return {r['ret']:.0%}, PnL ${r['pnl']:,.0f}, even-spend {r['even_ret']:.0%}, p {r['placebo_p']:.2f}, max DD ${r['max_dd']:,.0f}")
r, _ = run(f20 & FILTERS["mvrv20"][1] & FILTERS["mayer"][1] & FILTERS["ma2y"][1], D(2018, 2, 1), "F&G<20 and all three")
print(f"F&G<20 and all three: buys {r['buys']}, return {r['ret']:.0%}, PnL ${r['pnl']:,.0f}, Sharpe {r['sharpe']:.2f}, max DD ${r['max_dd']:,.0f}, p {r['placebo_p']:.2f}; cycles " + "; ".join(f"{c}: {d['buys']} @ ${d['avg_cost']:,.0f}" for c, d in r["cycles"].items()))
