"""Checks of the code against independent references and against a synthetic market with known properties.

Run:  python selfcheck.py            unit checks (ADF against statsmodels, engine against a scalar reference, a
                                     hand-computed trade)
      BTCALTS_TEST=1 python selfcheck.py --synthetic     after running s1_data.py, p1_extract.py, p1_analyze.py,
                                     p2_backtest.py with BTCALTS_TEST=1: asserts that the known lags, spreads
                                     and cointegrated pairs of the synthetic market are recovered
No network.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import sys

import numpy as np

import p2_backtest as P2

HERE = os.path.dirname(os.path.abspath(__file__))


def check_adf():
    import warnings
    warnings.simplefilter("ignore", FutureWarning)
    from statsmodels.tsa.stattools import adfuller, coint
    rng = np.random.default_rng(1)
    worst = 0.0
    for k in range(40):
        n = 400
        e = np.zeros(n)
        phi = rng.uniform(0.7, 1.0)
        for t in range(1, n):
            e[t] = phi * e[t - 1] + rng.normal()
        mine = float(P2.adf_t(e[:, None])[0])
        ref = adfuller(e, maxlag=1, regression="n", autolag=None)[0]
        worst = max(worst, abs(mine - ref))
    assert worst < 1e-8, worst
    # Engle-Granger statistic of formation() against statsmodels.coint
    x = np.cumsum(rng.normal(0, 0.01, (500, 6)), axis=0) + 3.0
    x[:, 1] = 0.8 * x[:, 0] + 0.5 + 0.02 * np.cumsum(rng.normal(0, 0.2, 500)) * 0 + rng.normal(0, 0.01, 500)
    fs = P2.formation(np.exp(x))
    worst2 = 0.0
    for p in range(len(fs["I"])):
        i, j = fs["I"][p], fs["J"][p]
        t1 = coint(x[:, i], x[:, j], trend="c", maxlag=1, autolag=None)[0]
        t2 = coint(x[:, j], x[:, i], trend="c", maxlag=1, autolag=None)[0]
        worst2 = max(worst2, abs(min(t1, t2) - fs["tstat"][p]), abs(t1 - fs["t_fixed"][p]))
    assert worst2 < 1e-6, worst2
    best = int(np.argmin(np.where(fs["valid"], fs["tstat"], np.inf)))
    assert {int(fs["I"][best]), int(fs["J"][best])} == {0, 1}
    print(f"ADF and Engle-Granger statistics match statsmodels (max abs diff {worst:.1e}, {worst2:.1e})")


def ref_pair(z, O, Cc, dead, a, b, entry, F, day, n_days, late, barred=False, stop=4.0):
    """Scalar reference of the pair rule, written separately from the vectorised engine."""
    T = len(z)
    pos, pend_open, pend_close = 0, 0, False
    eA = eB = 1.0
    real = prev = 0.0
    gross, na, nb, fund = (np.zeros(n_days) for _ in range(4))
    for t in range(T):
        d = day[t]
        if t > 0:
            if pos != 0:
                fund[d] += pos * (-F[t, a] * Cc[t - 1, a] / eA + F[t, b] * Cc[t - 1, b] / eB)
            if pend_close:
                ra, rb = O[t, a] / eA, O[t, b] / eB
                real += pos * (ra - rb)
                na[d] += ra
                nb[d] += rb
                pos, pend_close = 0, False
            if pend_open != 0:
                eA, eB = O[t, a], O[t, b]
                pos, pend_open = pend_open, 0
                na[d] += 1.0
                nb[d] += 1.0
        val = real + (pos * (Cc[t, a] / eA - Cc[t, b] / eB) if pos else 0.0)
        gross[d] += val - prev
        prev = val
        zt = (z[t - 1] if t > 0 else 0.0) if late else z[t]
        deadp = bool(dead[t, a] or dead[t, b])
        if t < T - 1:
            stop_hit = (pos == 1 and zt <= -stop) or (pos == -1 and zt >= stop)
            cross = (pos == 1 and zt >= 0) or (pos == -1 and zt <= 0)
            pend_close = bool(stop_hit or cross or (pos != 0 and deadp))
            if stop_hit or deadp:
                barred = True
            if pos == 0 and not barred:
                if entry <= zt < stop:
                    pend_open = -1
                elif -stop < zt <= -entry:
                    pend_open = 1
        elif pos != 0:
            ra, rb = Cc[t, a] / eA, Cc[t, b] / eB
            na[d] += ra
            nb[d] += rb
            pos = 0
    return gross, na, nb, fund


def check_engine():
    rng = np.random.default_rng(2)
    T, n = 300, 8
    lr = rng.normal(0, 0.01, (T, n))
    Cc = np.exp(np.cumsum(lr, axis=0))
    O = np.vstack([np.ones((1, n)), Cc[:-1]]) * np.exp(rng.normal(0, 0.001, (T, n)))
    dead = np.zeros((T, n), bool)
    dead[200:, 3] = True
    Cc[200:, 3] = Cc[199, 3]
    I, J = np.triu_indices(n, 1)
    z = (rng.normal(0, 1, (T, len(I))).cumsum(axis=0) * 0.35).astype(np.float64)
    F = np.zeros((T, n))
    F[::8] = rng.normal(1e-4, 1e-4, (len(range(0, T, 8)), n))
    day = np.arange(T) // 24
    hs = rng.choice([2e-4, 5e-4, 10e-4], n)
    valid = rng.random(len(I)) > 0.2
    worst = 0.0
    n_tr = 0
    for late in (False, True):
        for entry in (1.5, 2.0, 2.5):
            sim = P2.simulate(z, O, Cc, dead, I, J, entry, F, day, int(day[-1] + 1), valid=valid, late=late)
            net = P2.net_of(sim, hs[I], hs[J])
            n_tr += int(sim["n_entry"].sum())
            for p in range(len(I)):
                ref = ref_pair(z[:, p], O, Cc, dead, I[p], J[p], entry, F, day, int(day[-1] + 1), late, barred=not valid[p])
                for key, r in zip(("gross", "na", "nb", "fund"), ref):
                    worst = max(worst, float(np.abs(sim[key][p] - r).max()))
                ref_net = ref[0] - (5e-4 + hs[I[p]]) * ref[1] - (5e-4 + hs[J[p]]) * ref[2] + ref[3]
                worst = max(worst, float(np.abs(net[p] - ref_net).max()))
    assert worst < 1e-10, worst
    assert n_tr > 100
    print(f"vectorised engine equals the scalar reference on {n_tr} trades (max abs diff {worst:.1e})")


def check_hand_trade():
    """One pair, prices chosen by hand: z crosses +2 at bar 2, back through 0 at bar 5."""
    T = 8
    Cc = np.array([[100, 100], [101, 100], [104, 100], [103, 100], [102, 100], [100, 100], [100, 100], [100, 100]], float)
    O = np.array([[100, 100], [100, 100], [101, 100], [104, 100], [103, 100], [102, 100], [100, 100], [100, 100]], float)
    z = np.array([[0.0], [1.0], [2.5], [2.0], [1.0], [-0.1], [0.0], [0.0]])
    dead = np.zeros((T, 2), bool)
    F = np.zeros((T, 2))
    F[4, 0] = 0.001                      # the short leg A receives 10 bps at bar 4
    day = np.zeros(T, np.int64)
    sim = P2.simulate(z, O, Cc, dead, np.array([0]), np.array([1]), 2.0, F, day, 1)
    # signal at close of bar 2 (z=2.5): short A, long B at the open of bar 3 (104, 100).
    # exit signal at close of bar 5 (z=-0.1): cover at the open of bar 6 (100, 100).
    gross = -(100 / 104 - 1.0) + 0.0
    funding = 0.001 * (103 / 104)        # short A receives the rate on its notional at the close of bar 3
    assert abs(sim["gross"][0, 0] - gross) < 1e-12, (sim["gross"], gross)
    assert abs(sim["na"][0, 0] - (1.0 + 100 / 104)) < 1e-12 and abs(sim["nb"][0, 0] - 2.0) < 1e-12
    assert abs(sim["fund"][0, 0] - funding) < 1e-12, (sim["fund"], funding)
    net = P2.net_of(sim, np.array([2e-4]), np.array([5e-4]))[0, 0]
    by_hand = gross - (5e-4 + 2e-4) * (1.0 + 100 / 104) - (5e-4 + 5e-4) * 2.0 + funding
    assert abs(net - by_hand) < 1e-12
    late = P2.simulate(z, O, Cc, dead, np.array([0]), np.array([1]), 2.0, F, day, 1, late=True)
    # one bar late: entry at the open of bar 4 (103, 100), exit at the open of bar 7 (100, 100)
    assert abs(late["gross"][0, 0] - (-(100 / 103 - 1.0))) < 1e-12
    print("hand-computed trade: gross, traded notional, costs and funding as expected (on time and one bar late)")


def check_no_lookahead():
    """Scramble every bar after the decision: the universe, betas, abnormal returns, picks and costs must not move."""
    import common as C
    import fake_binance
    cfg = fake_binance.test_config()
    cl = fake_binance.FakeClient()
    syms = ["BTCUSDT"] + [a + "USDT" for a in cl.w.alts]
    panel = C.build_hourly_panel(cl, syms, cfg.hourly_start, cfg.end, 2, log=lambda *a: None)
    panel["step_ms"] = C.HOUR
    n = panel["close"].shape[0]
    F = np.zeros(panel["close"].shape, np.float32)
    perp = np.zeros(panel["close"].shape, bool)
    rng = np.random.default_rng(3)
    fixed = (4, 5, 6, 8, 9, 13, 14, 17, 18, 19)      # coins, abnormal returns, costs, shock size, beta, rank, volumes
    same = moved = total = 0
    for h in rng.integers(800, n - 100, size=25):
        h = int(h)
        r0, r1 = [], []
        P2.shock_test(panel, F, perp, [("E", h)], "x", False, r0)
        p2 = dict(panel)
        for k in ("open", "close", "qv"):
            a = panel[k].copy()
            a[h + 2:] = a[h + 2:] * rng.uniform(0.5, 2.0, size=a[h + 2:].shape).astype(a.dtype)
            p2[k] = a
        P2.shock_test(p2, F, perp, [("E", h)], "x", False, r1)
        t_day = ((panel["start_ms"] + h * C.HOUR) // C.DAY) * C.DAY
        assert C.rank_at(panel, t_day) == C.rank_at(p2, t_day)
        if not r0:
            continue
        total += 1
        a, b = r0[1], r1[1]                              # the 24-hour rows
        same += all(a[i] == b[i] for i in fixed)
        moved += a[7] != b[7]                            # the outcome does depend on later bars
    assert total >= 15 and same == total and moved == total, (total, same, moved)
    print(f"no look-ahead: ranking, betas, abnormal returns, picks and costs unchanged in {same} of {total} synthetic events when "
          f"every bar after the decision is scrambled (the outcome changed in {moved})")



def check_synthetic():
    out = os.path.join(HERE, "out_test")
    with open(os.path.join(out, "p1", "summary.json")) as f:
        s = json.load(f)
    h = s["half"]["down"]
    # the synthetic coins of ranks 1-10 follow in the same second; the thin ones are seconds late
    assert abs(h["T1|coin_delay_median"]["median"]) <= 1.0, h["T1|coin_delay_median"]
    assert h["T3|coin_delay_median"]["median"] >= 3.0, h["T3|coin_delay_median"]
    ll = s["leadlag"]["random"]
    assert ll["ranks 1-10"]["same second, 0"][0] > 0.9
    assert ll["ranks 31-100"]["+3..+5"][0] + ll["ranks 31-100"]["+6..+10"][0] > 0.6
    sp = s["spread"]
    assert abs(sp["random|post|ranks 1-10"]["median_full_spread_bps"] - 2.0) < 0.2
    assert abs(sp["random|post|ranks 31-100"]["median_full_spread_bps"] - 16.0) < 1.0
    # the three cointegrated pairs are found by the cointegration method in most windows
    hits, wins = 0, set()
    with gzip.open(os.path.join(out, "p2", "selected_pairs.csv.gz"), "rt") as f:
        for r in csv.DictReader(f):
            if r["bar"] == "1h" and r["method"] == "coint":
                wins.add(r["window"])
                if {r["a"], r["b"]} in ({"C03USDT", "C04USDT"}, {"C13USDT", "C14USDT"}, {"C25USDT", "C26USDT"}):
                    hits += 1
    assert hits >= 2 * len(wins), (hits, len(wins))
    print(f"synthetic market: lags, spreads and cointegrated pairs recovered ({hits} of {3 * len(wins)} planted pair-windows selected)")


if __name__ == "__main__":
    if "--synthetic" in sys.argv:
        check_synthetic()
    else:
        check_adf()
        check_engine()
        check_hand_trade()
        check_no_lookahead()
