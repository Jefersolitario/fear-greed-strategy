"""Audit, part B: recompute the published results by a second method.

The backtest script walks day by day keeping a list of open lots. This file never does that: for every lot it works
out the exit day directly, then builds the daily position, cash and PnL from cumulative sums. Results are compared
with the JSON files the dashboard reads.

Usage: python audit_calc.py daily_v2.parquet out_dir_with_json
"""
import json
import sys

import numpy as np
import polars as pl

raw = pl.read_parquet(sys.argv[1]).filter(pl.col("close").is_not_null()).sort("date")
OUT = sys.argv[2]
px = raw["close"].to_numpy().astype(float)
f_raw = raw["fng"].to_numpy().astype(float)
f = raw["fng"].fill_null(strategy="forward").to_numpy().astype(float)
dates = [str(x)[:10] for x in raw["date"].to_numpy()]
N, T = len(px), 1000.0
val = np.nan_to_num(f_raw, nan=999.0)
sma = np.full(N, np.nan); cs = np.cumsum(px); sma[199:] = (cs[199:] - np.r_[0, cs[:-200]]) / 200


def next_true(flag):
    """nxt[t] = first s > t with flag[s], else N."""
    nxt = np.full(N, N); last = N
    for t in range(N - 1, -1, -1):
        nxt[t] = last
        if flag[t]: last = t
    return nxt


def ledger(buy, exit_idx=None, exit_px=None, fee=0.001, lag=0, cash_rate=0.0):
    """Daily PnL from per-lot entry/exit days. exit_idx[t] is the sale day of a lot bought on t (N = never)."""
    b = np.where(buy)[0] + lag
    b = b[b < N]
    units = np.zeros(N); units[b] = T * (1 - fee) / px[b]
    e = np.full(N, N) if exit_idx is None else exit_idx
    pos_delta = units.copy(); cash_in = np.zeros(N)
    for t in b:
        if e[t] < N:
            pos_delta[e[t]] -= units[t]
            cash_in[e[t]] += units[t] * (px[e[t]] if exit_px is None else exit_px[t]) * (1 - fee)
    pos = np.cumsum(pos_delta)
    if cash_rate:
        cash = np.zeros(N); c = 0.0
        for t in range(N):
            c = c * (1 + cash_rate / 365) + cash_in[t]; cash[t] = c
    else:
        cash = np.cumsum(cash_in)
    put_in = np.cumsum(np.isin(np.arange(N), b) * T)
    return pos * px + cash - put_in, put_in, pos


def trim_ledger(buy, level, rate, fee=0.001):
    u = c = k = 0.0; pnl = np.zeros(N)
    for t in range(N):
        if u > 0 and f[t] >= level:
            c += u * rate * px[t] * (1 - fee); u *= 1 - rate
        if buy[t]:
            u += T * (1 - fee) / px[t]; k += T
        pnl[t] = u * px[t] + c - k
    return pnl


def stats(pnl, buy, lag=0):
    first = int(np.argmax(buy)) + lag
    d = np.diff(pnl[first:])
    seg = pnl[first:]; dd = seg - np.maximum.accumulate(seg)
    return dict(pnl=pnl[-1], sharpe=d.mean() / d.std(ddof=1) * np.sqrt(365),
                sortino=d.mean() / np.sqrt(np.mean(np.minimum(d, 0) ** 2)) * np.sqrt(365), max_dd_usd=dd.min())


def exits_for(buy, rule):
    """exit day (and fill price where it is not the close) for a lot bought on each day."""
    idx = np.arange(N)
    if rule == "hold": return None, None
    if rule in ("sell80", "sell90"): return next_true(f >= int(rule[4:])), None
    if rule.startswith("time") or rule.startswith("h"):
        h = int(rule.replace("time", "").replace("h", "")); e = idx + h
        return np.where(e <= N - 1, e, N), None
    if rule == "sma200":
        flag = np.zeros(N, bool)
        for t in range(2, N):
            flag[t] = (not np.isnan(sma[t - 2])) and px[t - 2] >= sma[t - 2] and px[t - 1] < sma[t - 1]
        return next_true(flag), None
    e = np.full(N, N); fill = np.full(N, np.nan)
    for t in np.where(buy)[0]:
        if rule.startswith("tp"):
            tgt = px[t] * (1 + int(rule[2:]) / 100); hit = np.where(px[t + 1:] >= tgt)[0]
            if len(hit): e[t] = t + 1 + hit[0]; fill[t] = tgt
        elif rule == "sl30":
            hit = np.where(px[t + 1:] <= px[t] * 0.7)[0]
            if len(hit): e[t] = t + 1 + hit[0]; fill[t] = px[e[t]]
    return e, fill


def load(name):
    return json.load(open(f"{OUT}/{name}.json"))["rows"]


worst = 0.0
def cmp(tag, mine, theirs, keys=("pnl", "sharpe", "sortino", "max_dd_usd")):
    global worst
    diffs = []
    for k in keys:
        a, b = mine[k], theirs[k]
        rel = abs(a - b) / max(1.0, abs(b))
        worst = max(worst, rel); diffs.append(f"{k} {a:,.2f} vs {b:,.2f}")
    ok = all(abs(mine[k] - theirs[k]) <= max(0.01, 1e-6 * abs(theirs[k])) for k in keys)
    print(f"  {'OK ' if ok else 'DIFF'} {tag:28s} " + " | ".join(diffs))
    return ok


all_ok = True
rules = {(r["threshold"], r["id"]): r for r in load("rules")}
holds = {(r["threshold"], r["id"]): r for r in load("holds")}
entries = {(r["threshold"], r["id"]): r for r in load("entries")}
curve = load("curve"); hcurve = load("hold_curve")
for th in (20, 10):
    buy = val < th
    print(f"\n== buy under {th}: {int(buy.sum())} buy days")
    for rule in ("hold", "sell80", "sell90", "tp100", "tp200", "time365", "time730", "sl30", "sma200"):
        e, fill = exits_for(buy, rule)
        pnl, _, _ = ledger(buy, e, fill)
        all_ok &= cmp(rule, stats(pnl, buy), rules[(th, rule)])
        if rule in ("hold", "sell80"):
            col = ("hold" if rule == "hold" else "sell") + str(th)
            all_ok &= (m := max(abs(round(float(p)) - r[col]) for p, r in zip(pnl, curve))) <= 1
            print(f"       daily curve '{col}': largest difference from the published curve ${m}")
    for rid, rate in (("trim_05", 0.005), ("trim_1", 0.01), ("trim_2", 0.02)):
        all_ok &= cmp(rid, stats(trim_ledger(buy, 80, rate), buy), rules[(th, rid)])
    for h in (1, 30, 60, 90):
        e, _ = exits_for(buy, f"h{h}")
        pnl, _, pos = ledger(buy, e)
        all_ok &= cmp(f"sell after {h}d", stats(pnl, buy), holds[(th, f"h{h}")])
        m = max(abs(round(float(p)) - r[f"h{h}_{th}"]) for p, r in zip(pnl, hcurve))
        open_lots = np.cumsum(buy.astype(int)) - np.cumsum(np.r_[np.zeros(h, int), buy[:-h].astype(int)])
        print(f"       daily curve: largest difference ${m}; most at risk ${open_lots.max() * T:,.0f} vs published ${holds[(th, f'h{h}')]['most_at_risk']:,.0f}")
    # the two other ways of counting a signal, masks rebuilt here
    wk = np.zeros(N, bool); last = -10**9
    for t in np.where(buy)[0]:
        if t - last >= 7: wk[t] = True; last = t
    prev = np.r_[False, (f < th)[:-1]]
    sp = buy & ~prev
    for rid, mask in (("weekly", wk), ("spell", sp)):
        pnl, _, _ = ledger(mask)
        all_ok &= cmp(f"count: {rid} ({int(mask.sum())} buys)", stats(pnl, mask), entries[(th, rid)], keys=("pnl", "max_dd_usd"))
        all_ok &= int(mask.sum()) == entries[(th, rid)]["buys"]
print(f"\nALL MATCH: {all_ok}; largest relative difference {worst:.2e}")
