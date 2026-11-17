"""Audit, part C: how much do the conclusions move when an assumption moves?  Reuses the second-method ledger."""
import sys, importlib.util
import numpy as np

sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2]]
spec = importlib.util.spec_from_file_location("a", sys.argv[0].replace("audit_sens.py", "audit_calc.py"))
import io, contextlib
a = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(a)
N, px, f, val, T = a.N, a.px, a.f, a.val, a.T
b20, b10, b10i = val < 20, val < 10, val <= 10
s80 = a.next_true(f >= 80)
def h(n): e = np.arange(N) + n; return np.where(e <= N - 1, e, N)
def row(tag, pnl, buy, lag=0):
    s = a.stats(pnl, buy, lag); print(f"  {tag:46s} PnL {s['pnl']:>12,.0f}  Sharpe {s['sharpe']:5.2f}  Sortino {s['sortino']:5.2f}  maxDD {s['max_dd_usd']:>12,.0f}")

print("1. trading cost per side")
for fee in (0.0, 0.001, 0.0025, 0.005):
    print(f" {fee * 1e4:.0f} bps")
    row("under 20, hold", a.ledger(b20, fee=fee)[0], b20)
    row("under 10, hold", a.ledger(b10, fee=fee)[0], b10)
    row("under 10, sell at 80", a.ledger(b10, s80, fee=fee)[0], b10)
    row("under 10, sell after 60 days", a.ledger(b10, h(60), fee=fee)[0], b10)
    row("under 10, sell next day", a.ledger(b10, h(1), fee=fee)[0], b10)

print("\n2. when the buy is filled (index published about 00:00 UTC on day D)")
for tag, mask, lag in (("at publication (close of D-1)", lambda m: np.r_[m[1:], False], 0), ("close of D (as published)", lambda m: m, 0), ("close of D+1", lambda m: m, 1)):
    print(" " + tag)
    for lab, m in (("under 20", b20), ("under 10", b10)):
        mm = mask(m)
        row(lab + ", hold", a.ledger(mm, lag=lag)[0], mm, lag)
        # the ledger looks the exit up by the actual purchase day, so the same table serves every fill convention
        row(lab + ", sell at 80", a.ledger(mm, a.next_true(f >= 80), lag=lag)[0], mm, lag)

print("\n3. 'at 10': strictly under 10 against 10 or under")
for lab, m in (("under 10", b10), ("10 or under", b10i)):
    print(f" {lab}: {int(m.sum())} buys")
    row("hold", a.ledger(m)[0], m); row("sell at 80", a.ledger(m, s80)[0], m); row("sell after 60 days", a.ledger(m, h(60))[0], m)

print("\n4. idle cash earning 3% a year instead of nothing (only matters for rules that sell)")
for lab, m in (("under 20", b20), ("under 10", b10)):
    row(lab + ", sell at 80, cash at 0%", a.ledger(m, s80)[0], m)
    row(lab + ", sell at 80, cash at 3%", a.ledger(m, s80, cash_rate=0.03)[0], m)

print("\n5. Sharpe conventions, under 20 hold and under 10 sell-at-80")
dts = np.array(a.dates, dtype="datetime64[D]")
for lab, m, e in (("under 20, hold", b20, None), ("under 10, hold", b10, None), ("under 10, sell at 80", b10, s80)):
    pnl = a.ledger(m, e)[0]; first = int(np.argmax(m)); d = np.diff(pnl[first:])
    mon = dts[first:].astype("datetime64[M]"); ends = np.r_[np.where(mon[1:] != mon[:-1])[0], len(mon) - 1]
    md = np.diff(pnl[first:][ends])
    r = np.where(a.ledger(m, e)[2][:-1] > 0, px[1:] / px[:-1] - 1, 0.0)[first:]
    print(f"  {lab:24s} daily $ x sqrt365 {d.mean() / d.std(ddof=1) * np.sqrt(365):.2f} | daily $ x sqrt252 {d.mean() / d.std(ddof=1) * np.sqrt(252):.2f} | "
          f"monthly $ x sqrt12 {md.mean() / md.std(ddof=1) * np.sqrt(12):.2f} | daily return on BTC held {r.mean() / r.std(ddof=1) * np.sqrt(365):.2f}")
    # second half only: is the dollar Sharpe really dominated by the late, large position?
    half = len(d) // 2
    print(f"  {'':24s} share of total daily-PnL variance from the last 2 years: {np.sum((d[-730:] - d.mean()) ** 2) / np.sum((d - d.mean()) ** 2) * 100:.0f}%")

print("\n6. fixed holding periods under 10: mean against median trade (after costs), and the any-day comparison")
idx = np.where(b10)[0]
for n in (1, 30, 60, 90):
    ok = idx[idx + n <= N - 1]; ret = px[ok + n] * 0.999 ** 2 / px[ok] - 1
    al = px[n:] * 0.999 ** 2 / px[:-n] - 1
    print(f"  {n:3d} days: trades mean {ret.mean() * 100:6.2f}%  median {np.median(ret) * 100:6.2f}%   any day mean {al.mean() * 100:6.2f}%  median {np.median(al) * 100:6.2f}%   "
          f"won {np.mean(ret > 0) * 100:.0f}% vs {np.mean(al > 0) * 100:.0f}%")
# per-episode view for 60 days: one number per separate episode
gaps = np.diff(idx); starts = np.r_[0, np.where(gaps > 14)[0] + 1]; ends = np.r_[starts[1:], len(idx)]
print("  60-day result by episode (first buy, lots, mean trade):", [(a.dates[idx[s]], int(e - s), f"{np.mean(px[idx[s:e] + 60] * 0.999 ** 2 / px[idx[s:e]] - 1) * 100:+.0f}%") for s, e in zip(starts, ends)])
print("  sell-at-80 by episode:", [(a.dates[idx[s]], int(e - s), ("open" if s80[idx[s]] >= N else a.dates[s80[idx[s]]]),
      f"{np.mean(px[np.minimum(s80[idx[s:e]], N - 1)] * 0.999 ** 2 / px[idx[s:e]] - 1) * 100:+.0f}%") for s, e in zip(starts, ends)])

print("\n7. the same rules judged per dollar at risk (daily return on the BTC held, zero on flat days) rather than on dollar PnL")
def tw(m, e=None, trim=None):
    if trim:
        u = 0.0; pos = np.zeros(N)
        for t in range(N):
            if u > 0 and f[t] >= 80: u *= 1 - trim
            if m[t]: u += T * 0.999 / px[t]
            pos[t] = u
    else:
        pos = a.ledger(m, e)[2]
    first = int(np.argmax(m)); held = pos[:-1][first:] > 1e-12
    r = np.where(pos[:-1] > 1e-12, px[1:] / px[:-1] - 1, 0.0)[first:]
    ri = r[held]
    return (r.mean() / r.std(ddof=1) * np.sqrt(365), r.mean() / np.sqrt(np.mean(np.minimum(r, 0) ** 2)) * np.sqrt(365), held.mean() * 100,
            ri.mean() / ri.std(ddof=1) * np.sqrt(365), ri.mean() * 365 * 100)
for lab, m in (("under 20", b20), ("under 10", b10)):
    for tag, e, trim in (("hold", None, None), ("trim 1% a day at 80+", None, 0.01), ("sell at 80", s80, None), ("sell after 365 days", h(365), None), ("sell after 60 days", h(60), None)):
        sh, so, inm, shi, mu = tw(m, e, trim)
        d = np.diff((a.trim_ledger(m, 80, trim) if trim else a.ledger(m, e)[0])[int(np.argmax(m)):])
        print(f"  {lab}, {tag:22s} dollar Sharpe {d.mean() / d.std(ddof=1) * np.sqrt(365):5.2f} | per-dollar Sharpe {sh:5.2f}  Sortino {so:5.2f} | in the market {inm:3.0f}% of days | "
              f"Sharpe on in-market days only {shi:5.2f}, mean return {mu:4.0f}%/yr")
