"""Part 1 statistics from the committed compact tables (no network).

Run:  python p1_analyze.py                 all tables, writes out/p1/summary.json
      python p1_analyze.py --table trade   one table (events, cr, share, half, catchup, stale, leadlag, fresh,
                                           trade, speed, split, spread)
      BTCALTS_TEST=1 python p1_analyze.py  the same on the synthetic market
One event is one observation: every interval is a bootstrap over events (10,000 draws, fixed seed).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys

import numpy as np
import polars as pl

import common as C

TEST = os.environ.get("BTCALTS_TEST") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "out_test" if TEST else "out")
P1 = os.path.join(OUT_ROOT, "p1")
B = 10_000
LAGS = (-30, -10, -5, -2, -1, 0, 1, 2, 5, 15, 60, 300, 900, 3600)
REPORT_LAGS = (0, 1, 2, 5, 15, 60, 300, 900, 3600)
DELAYS = (1, 2, 5, 60)          # the pre-specified family
ALL_DELAYS = (0, 1, 2, 5, 60)   # 0 s: reference for a faster actor, outside the family
HORIZONS = (30, 300, 1800)
PHI = 0.5
TIERS = (1, 2, 3)
TIER_NAME = {0: "BTC", 1: "ranks 1-10", 2: "ranks 11-30", 3: "ranks 31-100"}


def ln(tau):
    return f"cr_m{-tau}" if tau < 0 else f"cr_{tau}"


def fmt(x, nd=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"{x:.{nd}f}"


def ci(draws, lo=2.5, hi=97.5):
    d = np.asarray(draws, dtype=float)
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return (float("nan"), float("nan"))
    return (float(np.percentile(d, lo)), float(np.percentile(d, hi)))


class Data:
    def __init__(self):
        self.cfg = C.load_config() if TEST else None
        self.events = {}
        with open(os.path.join(OUT_ROOT, "s1", "events.csv")) as f:
            for r in csv.DictReader(f):
                self.events[r["event_id"]] = r
        ec = pl.read_parquet(os.path.join(P1, "event_coin.parquet"))
        self.ec = {c: ec[c].to_numpy() for c in ec.columns}
        self.n = len(self.ec["symbol"])
        self.is_btc = self.ec["symbol"] == "BTCUSDT"
        ev_ids = sorted(set(self.ec["event_id"].tolist()))
        self.ev_index = {e: i for i, e in enumerate(ev_ids)}
        self.ev_ids = ev_ids
        self.ev = np.array([self.ev_index[e] for e in self.ec["event_id"]])
        self.kind_of = np.array([self.events[e]["kind"] for e in ev_ids])
        self.t_of = np.array([int(self.events[e]["s_star_ms"]) for e in ev_ids])
        # Bitcoin's own values per event, broadcast to rows
        self.btc = {}
        bi = np.flatnonzero(self.is_btc)
        for c in self.ec:
            if c.startswith("cr_") or c.startswith("thalf"):
                v = np.full(len(ev_ids), np.nan)
                v[self.ev[bi]] = self.ec[c][bi]
                self.btc[c] = v
        split = (self.cfg.split_p1 if TEST else C.Config().split_p1)
        self.late = self.t_of >= split
        self.rng = np.random.default_rng(C.SEED + 10)

    def events_of(self, kind):
        return np.flatnonzero(self.kind_of == kind)

    def tier_event_mean(self, col, tier, kind):
        """Per event: mean of a column over the coins of a tier (Bitcoin excluded). NaN where empty."""
        ev_list = self.events_of(kind)
        pos = {e: i for i, e in enumerate(ev_list)}
        m = (self.ec["tier"] == tier) & ~self.is_btc & np.isin(self.ev, ev_list)
        v = self.ec[col][m].astype(float)
        e = np.array([pos[x] for x in self.ev[m]])
        ok = np.isfinite(v)
        s = np.bincount(e[ok], weights=v[ok], minlength=len(ev_list))
        n = np.bincount(e[ok], minlength=len(ev_list))
        return np.where(n > 0, s / np.maximum(n, 1), np.nan)

    def boot_idx(self, n):
        return self.rng.integers(0, n, size=(B, n))


def table_events(D):
    out = {}
    print("\n## Events")
    print("| kind | events | 2023 | 2024 | 2025 | 2026 | median BTC 60 s return at trigger (bps) | min | max |")
    print("|---|---|---|---|---|---|---|---|---|")
    for kind in ("down", "up", "random"):
        ev = D.events_of(kind)
        years = [C.iso(t)[:4] for t in D.t_of[ev]]
        b0 = D.btc["cr_0"][ev]
        row = {"n": int(len(ev)), **{y: years.count(y) for y in ("2023", "2024", "2025", "2026")},
               "btc_cr0_median": float(np.nanmedian(b0)) if len(ev) else float("nan"),
               "btc_cr0_min": float(np.nanmin(b0)) if len(ev) else float("nan"),
               "btc_cr0_max": float(np.nanmax(b0)) if len(ev) else float("nan")}
        out[kind] = row
        print(f"| {kind} | {row['n']} | {row['2023']} | {row['2024']} | {row['2025']} | {row['2026']} | "
              f"{fmt(row['btc_cr0_median'])} | {fmt(row['btc_cr0_min'])} | {fmt(row['btc_cr0_max'])} |")
    return out


def group_series(D, kind, tier, col):
    if tier == 0:
        return D.btc[col][D.events_of(kind)]
    return D.tier_event_mean(col, tier, kind)


def table_cr(D):
    out = {}
    for kind in ("down", "up", "random"):
        ev = D.events_of(kind)
        if len(ev) == 0:
            continue
        print(f"\n## Mean cumulative return from t*-60 s, bps [{kind}, n={len(ev)} events; 95% bootstrap interval]")
        print("| lag | " + " | ".join(TIER_NAME[t] for t in (0, 1, 2, 3)) + " |")
        print("|---|---|---|---|---|")
        idx = D.boot_idx(len(ev))
        res = {}
        for tau in LAGS:
            cells = []
            for t in (0, 1, 2, 3):
                v = group_series(D, kind, t, ln(tau))
                m = float(np.nanmean(v))
                lo, hi = ci(np.nanmean(v[idx], axis=1))
                res[f"{TIER_NAME[t]}|{tau}"] = [m, lo, hi]
                cells.append(f"{fmt(m)} [{fmt(lo)}, {fmt(hi)}]")
            print(f"| {tau:+d} s | " + " | ".join(cells) + " |")
        out[kind] = res
    return out


def table_share(D):
    """Share of the +60 min (and +60 s) move completed at each lag."""
    out = {}
    for kind in ("down", "up"):
        ev = D.events_of(kind)
        if len(ev) == 0:
            continue
        idx = D.boot_idx(len(ev))
        for denom, lags in ((3600, REPORT_LAGS), (60, (-30, -10, -5, -2, -1, 0, 1, 2, 5, 15, 60))):
            print(f"\n## Share of the +{denom} s move completed [{kind}, n={len(ev)}]: ratio of event means "
                  f"[95% interval]; then median and IQR of per-event ratios (events with |move| >= 25 bps)")
            print("| lag | " + " | ".join(TIER_NAME[t] for t in (0, 1, 2, 3)) + " |")
            print("|---|---|---|---|---|")
            res = {}
            for tau in lags:
                cells = []
                for t in (0, 1, 2, 3):
                    num = group_series(D, kind, t, ln(tau))
                    den = group_series(D, kind, t, ln(denom))
                    ok = np.isfinite(num) & np.isfinite(den)
                    num0, den0 = np.where(ok, num, 0.0), np.where(ok, den, 0.0)
                    r = num0.sum() / den0.sum()
                    lo, hi = ci(num0[idx].sum(axis=1) / den0[idx].sum(axis=1))
                    big = ok & (np.abs(den) >= 25.0)
                    pe = num[big] / den[big]
                    q = np.percentile(pe, [25, 50, 75]) if big.sum() >= 5 else [np.nan] * 3
                    res[f"{TIER_NAME[t]}|{tau}"] = {"ratio_of_means": float(r), "ci": [lo, hi], "n_big": int(big.sum()),
                                                    "per_event_q25_q50_q75": [float(x) for x in q]}
                    cells.append(f"{fmt(100 * r, 0)}% [{fmt(100 * lo, 0)}, {fmt(100 * hi, 0)}]; "
                                 f"med {fmt(100 * q[1], 0)}% ({fmt(100 * q[0], 0)} to {fmt(100 * q[2], 0)}; n={int(big.sum())})")
                print(f"| {tau:+d} s | " + " | ".join(cells) + " |")
            out[f"{kind}|{denom}"] = res
    return out


def table_half(D):
    """Time at which half of the move is completed, from mean paths and from coin-level times."""
    out = {}
    paths = pl.read_parquet(os.path.join(P1, "paths.parquet"))
    tcols = [c for c in paths.columns if c.startswith("t") and c[1:].lstrip("-").isdigit()]
    grid = np.array([int(c[1:]) for c in tcols])
    for kind in ("down", "up"):
        sub = paths.filter(pl.col("kind") == kind)
        if sub.height == 0:
            continue
        print(f"\n## Seconds after the trigger at which half of the move is done [{kind}] (negative = before the trigger)")
        print("| group | mean path, half of +60 s move [95%] | mean path, half of +60 min move [95%] | "
              "coin-level: median delay to Bitcoin's own half-time of the +60 s move, seconds (IQR over events) |")
        print("|---|---|---|---|")
        res = {}
        for gname, tier in (("BTC", 0), ("T1", 1), ("T2", 2), ("T3", 3)):
            g = sub.filter(pl.col("group") == gname)
            if g.height == 0:
                continue
            P = g.select(tcols).to_numpy().astype(float)
            idx = D.rng.integers(0, len(P), size=(2000, len(P)))

            def half_time(mean_path, target_col):
                tgt = mean_path[target_col]
                frac = mean_path[:target_col + 1] / tgt
                hit = np.flatnonzero(frac >= 0.5)
                return float(grid[hit[0]]) if len(hit) and abs(tgt) > 1e-9 else float("nan")

            cells = []
            for denom in (60, 3600):
                j = int(np.flatnonzero(grid == denom)[0])
                h = half_time(np.nanmean(P, axis=0), j)
                draws = [half_time(np.nanmean(P[i], axis=0), j) for i in idx]
                lo, hi = ci(draws)
                res[f"{gname}|path|{denom}"] = [h, lo, hi]
                cells.append(f"{fmt(h, 0)} [{fmt(lo, 0)}, {fmt(hi, 0)}]")
            if tier == 0:
                cells.append("0 (reference)")
            else:
                ev_list = D.events_of(kind)
                m = (D.ec["tier"] == tier) & ~D.is_btc & np.isin(D.ev, ev_list)
                delay = D.ec["thalf60"][m].astype(float) - D.btc["thalf60"][D.ev[m]]
                e = D.ev[m]
                per_event = np.array([np.nanmedian(delay[e == x]) for x in ev_list if np.isfinite(delay[e == x]).any()])
                q = np.percentile(per_event, [25, 50, 75]) if len(per_event) else [np.nan] * 3
                bi = D.rng.integers(0, max(len(per_event), 1), size=(B, max(len(per_event), 1)))
                lo, hi = ci(np.median(per_event[bi], axis=1)) if len(per_event) else (np.nan, np.nan)
                res[f"{gname}|coin_delay_median"] = {"median": float(q[1]), "iqr": [float(q[0]), float(q[2])],
                                                     "ci_median": [lo, hi], "n_events": int(len(per_event)),
                                                     "share_coin_events_delay_ge_1s": float(np.nanmean(delay[np.isfinite(delay)] >= 1)),
                                                     "share_coin_events_delay_ge_2s": float(np.nanmean(delay[np.isfinite(delay)] >= 2)),
                                                     "share_coin_events_delay_ge_5s": float(np.nanmean(delay[np.isfinite(delay)] >= 5))}
                cells.append(f"{fmt(q[1], 1)} ({fmt(q[0], 1)} to {fmt(q[2], 1)}); 95% of median [{fmt(lo, 1)}, {fmt(hi, 1)}]")
            print(f"| {TIER_NAME[tier]} | " + " | ".join(cells) + " |")
        out[kind] = res
    return out


def table_catchup(D):
    """sum(coin move) / sum(beta * BTC move) at each lag; all coins, and coins that traded in that very second."""
    out = {}
    for kind in ("down", "up"):
        ev_list = D.events_of(kind)
        if len(ev_list) == 0:
            continue
        pos = {e: i for i, e in enumerate(ev_list)}
        idx = D.boot_idx(len(ev_list))
        print(f"\n## Catch-up ratio: coin move / (beta x Bitcoin move) [{kind}, n={len(ev_list)}], all coins [95%]")
        print("| lag | " + " | ".join(TIER_NAME[t] for t in TIERS) + " |")
        print("|---|---|---|---|")
        res = {}
        for tau in LAGS:
            cells = []
            for t in TIERS:
                m = (D.ec["tier"] == t) & ~D.is_btc & np.isin(D.ev, ev_list) & (D.ec["beta"] > 0)
                cr = D.ec[ln(tau)][m].astype(float)
                tgt = D.ec["beta"][m] * D.btc[ln(tau)][D.ev[m]]
                ok = np.isfinite(cr) & np.isfinite(tgt)
                e = np.array([pos[x] for x in D.ev[m]])
                num = np.bincount(e[ok], weights=cr[ok], minlength=len(ev_list))
                den = np.bincount(e[ok], weights=tgt[ok], minlength=len(ev_list))
                r = num.sum() / den.sum()
                lo, hi = ci(num[idx].sum(axis=1) / den[idx].sum(axis=1))
                res[f"{TIER_NAME[t]}|{tau}"] = [float(r), lo, hi]
                cells.append(f"{fmt(r, 2)} [{fmt(lo, 2)}, {fmt(hi, 2)}]")
            print(f"| {tau:+d} s | " + " | ".join(cells) + " |")
        out[kind] = res
    return out


def table_stale(D):
    """How much of the apparent delay is a last-trade price that has not updated."""
    out = {}
    for kind in ("down", "up", "random"):
        ev_list = D.events_of(kind)
        if len(ev_list) == 0:
            continue
        print(f"\n## Trading activity around the trigger [{kind}]")
        print("| tier | share of seconds with a trade (whole window) | traded in the trigger second | traded within 1 s after | "
              "within 2 s | within 5 s | within 15 s | median seconds to first trade after trigger | "
              "catch-up ratio at +1 s, coins that traded in that second | same at +5 s |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        res = {}
        for t in TIERS:
            m = (D.ec["tier"] == t) & ~D.is_btc & np.isin(D.ev, ev_list)
            row = {"share_sec_traded": float(np.nanmean(D.ec["share_sec_traded"][m])),
                   "traded_in_trigger_second": float(np.mean(D.ec["age_0"][m] == 0))}
            for tau in (1, 2, 5, 15):
                a = D.ec[f"age_{tau}"][m]
                row[f"traded_within_{tau}s"] = float(np.mean(a <= tau - 1))
            row["median_fresh_delay"] = float(np.nanmedian(D.ec["fresh_delay"][m]))
            for tau in (1, 5):
                mm = m & (D.ec[f"age_{tau}"] == 0) & (D.ec["beta"] > 0)
                num = D.ec[ln(tau)][mm].astype(float)
                den = D.ec["beta"][mm] * D.btc[ln(tau)][D.ev[mm]]
                ok = np.isfinite(num) & np.isfinite(den)
                row[f"fresh_catchup_{tau}s"] = float(num[ok].sum() / den[ok].sum()) if ok.any() and kind != "random" else float("nan")
            res[TIER_NAME[t]] = row
            print(f"| {TIER_NAME[t]} | {fmt(100 * row['share_sec_traded'], 0)}% | {fmt(100 * row['traded_in_trigger_second'], 0)}% | "
                  + " | ".join(f"{fmt(100 * row[f'traded_within_{tau}s'], 0)}%" for tau in (1, 2, 5, 15))
                  + f" | {fmt(row['median_fresh_delay'], 0)} | {fmt(row['fresh_catchup_1s'], 2)} | {fmt(row['fresh_catchup_5s'], 2)} |")
        out[kind] = res
    return out


def table_leadlag(D):
    out = {}
    xt = pl.read_parquet(os.path.join(P1, "xcorr_tier.parquet"))
    lags = list(range(-60, 61))
    bands = (("coin leads, -60..-1", -60, -1), ("same second, 0", 0, 0), ("+1", 1, 1), ("+2", 2, 2), ("+3..+5", 3, 5),
             ("+6..+10", 6, 10), ("+11..+30", 11, 30), ("+31..+60", 31, 60))
    for kind in ("random", "down", "up"):
        sub = xt.filter(pl.col("kind") == kind)
        if sub.height == 0:
            continue
        print(f"\n## 1-second lead-lag against Bitcoin [{kind} windows]: lagged beta (response of the coin at t+L to "
              f"Bitcoin at t), share of the total by band [95% over windows]; and correlation")
        print("| tier | windows | total lagged beta | " + " | ".join(b[0] for b in bands) + " | corr L=0 | corr L=1 | corr L=2 | corr L=5 | corr L=-1 (control) | corr L=-5 |")
        print("|---|---|---|" + "---|" * (len(bands) + 6))
        res = {}
        for gname, t in (("T1", 1), ("T2", 2), ("T3", 3)):
            g = sub.filter(pl.col("group") == gname)
            if g.height == 0:
                continue
            Bm = g.select([f"b_m{-L}" if L < 0 else f"b_{L}" for L in lags]).to_numpy().astype(float)
            Cm = g.select([f"c_m{-L}" if L < 0 else f"c_{L}" for L in lags]).to_numpy().astype(float)
            idx = D.rng.integers(0, len(Bm), size=(B, len(Bm)))
            mb = np.nanmean(Bm, axis=0)
            tot = mb.sum()
            boot = np.stack([np.nanmean(Bm[i], axis=0) for i in idx[:2000]])
            row = {"n_windows": int(len(Bm)), "total_lagged_beta": float(tot), "corr": {str(L): float(np.nanmean(Cm[:, 60 + L])) for L in lags},
                   "lagged_beta": {str(L): float(mb[60 + L]) for L in lags}}
            cells = []
            for name, a, b in bands:
                sh = mb[60 + a:60 + b + 1].sum() / tot
                lo, hi = ci(boot[:, 60 + a:60 + b + 1].sum(axis=1) / boot.sum(axis=1))
                row[name] = [float(sh), lo, hi]
                cells.append(f"{fmt(100 * sh, 1)}% [{fmt(100 * lo, 1)}, {fmt(100 * hi, 1)}]")
            cc = [fmt(float(np.nanmean(Cm[:, 60 + L])), 3) for L in (0, 1, 2, 5, -1, -5)]
            res[TIER_NAME[t]] = row
            print(f"| {TIER_NAME[t]} | {len(Bm)} | {fmt(tot, 2)} | " + " | ".join(cells) + " | " + " | ".join(cc) + " |")
        out[kind] = res
        if kind != "random":
            print(f"\n## Shock zone only (Bitcoin returns of the two minutes around the trigger) [{kind}]: share of the "
                  f"lagged beta over L=-5..10")
            print("| tier | L<0 | L=0 | L=1 | L=2 | L=3..5 | L=6..10 |")
            print("|---|---|---|---|---|---|---|")
            for gname, t in (("T1", 1), ("T2", 2), ("T3", 3)):
                g = sub.filter(pl.col("group") == gname)
                if g.height == 0:
                    continue
                fine = list(range(-5, 11))
                Z = g.select([f"z_m{-L}" if L < 0 else f"z_{L}" for L in fine]).to_numpy().astype(float)
                mz = np.nanmean(Z, axis=0)
                tot = mz.sum()
                sh = [mz[0:5].sum() / tot, mz[5] / tot, mz[6] / tot, mz[7] / tot, mz[8:11].sum() / tot, mz[11:16].sum() / tot]
                out[f"{kind}|zone|{TIER_NAME[t]}"] = [float(x) for x in sh] + [float(tot)]
                print(f"| {TIER_NAME[t]} | " + " | ".join(f"{fmt(100 * x, 1)}%" for x in sh) + " |")
    return out


def table_fresh(D):
    """Slope of the coin's forward return (from a traded second's VWAP) on Bitcoin's return g seconds earlier."""
    rows = {}
    with gzip.open(os.path.join(P1, "fresh_stats.csv.gz"), "rt") as f:
        for r in csv.DictReader(f):
            key = (r["kind"], r["tier"], int(r["g"]), int(r["h"]), r["subset"])
            rows.setdefault(key, []).append([float(r[k]) for k in ("n", "sx", "sy", "sxx", "sxy", "syy")])
    out = {}
    for kind in ("random", "down", "up"):
        keys = sorted(k for k in rows if k[0] == kind)
        if not keys:
            continue
        print(f"\n## Fresh-price test [{kind} windows]: slope of the coin's return over the next h seconds, measured from the "
              f"VWAP of a second in which it traded, on Bitcoin's return in the second g seconds earlier [95% over windows]")
        print("| tier | subset | h | " + " | ".join(f"g={g}" for g in (1, 2, 3, 5, 10)) + " |")
        print("|---|---|---|---|---|---|---|---|")
        for tier in ("BTC", "T1", "T2", "T3"):
            for sub in ("all", "big"):
                for h in (5, 60):
                    cells = []
                    for g in (1, 2, 3, 5, 10):
                        S = np.array(rows.get((kind, tier, g, h, sub), []))
                        if len(S) == 0:
                            cells.append("n/a")
                            continue

                        def slope(s):
                            n, sx, sy, sxx, sxy = s[0], s[1], s[2], s[3], s[4]
                            den = sxx - sx * sx / n
                            return (sxy - sx * sy / n) / den if den > 0 else np.nan

                        b = slope(S.sum(axis=0))
                        idx = D.rng.integers(0, len(S), size=(2000, len(S)))
                        lo, hi = ci([slope(S[i].sum(axis=0)) for i in idx])
                        out[f"{kind}|{tier}|{sub}|h{h}|g{g}"] = {"slope": float(b), "ci": [lo, hi], "n_obs": float(S[:, 0].sum()),
                                                                 "n_windows": int(len(S))}
                        cells.append(f"{fmt(b, 3)} [{fmt(lo, 3)}, {fmt(hi, 3)}]")
                    print(f"| {tier} | {'all seconds' if sub == 'all' else 'abs(BTC move) >= 5 bps'} | {h} s | " + " | ".join(cells) + " |")
    return out


def trade_pnls(D, kind, d, H, price="assumed", hedged=False, tier=None, laggards=True):
    """Per-event mean PnL in bps of the pre-specified trade. Returns (pnl per event, trades per event)."""
    ev_list = D.events_of(kind)
    pos = {e: i for i, e in enumerate(ev_list)}
    sign = -1.0 if kind == "down" else 1.0           # short after a down shock, long after an up shock
    m = ~D.is_btc & np.isin(D.ev, ev_list) & (D.ec["beta"] > 0)
    if tier is not None:
        m &= D.ec["tier"] == tier
    b = D.btc[f"cr_{d}"][D.ev]
    moved = D.ec[f"cr_{d}"].astype(float)
    target = PHI * D.ec["beta"] * b
    lag = (b * sign > 0) & (moved * sign < target * sign) if True else None
    # down: b<0, laggard if moved > target (less negative). up: b>0, laggard if moved < target.
    if kind == "down":
        lag = (b < 0) & (moved > target)
    else:
        lag = (b > 0) & (moved < target)
    m &= lag if laggards else ~lag & np.isfinite(moved) & np.isfinite(b)
    beta = D.ec["beta"].astype(float)
    hs = np.array([C.HALF_SPREAD[int(t)] for t in D.ec["tier"]])
    if price == "exec":
        r = D.ec[f"r_exec_{d}_{H}"].astype(float)
        rb = D.ec[f"rb_exec_{d}_{H}"].astype(float)
        pnl = sign * r - 2 * C.TAKER_FEE
        if hedged:
            pnl = sign * (r - beta * rb) - 2 * C.TAKER_FEE * (1 + beta)
    else:
        r = D.ec[f"r_vwap_{d}_{H}"].astype(float)
        rb = D.ec[f"rb_vwap_{d}_{H}"].astype(float)
        pnl = sign * r
        if hedged:
            pnl = sign * (r - beta * rb)
        if price == "assumed":
            pnl = pnl - 2 * (C.TAKER_FEE + hs)
            if hedged:
                pnl = pnl - 2 * beta * (C.TAKER_FEE + C.HALF_SPREAD[1])
    ok = m & np.isfinite(pnl)
    e = np.array([pos[x] for x in D.ev[ok]], dtype=int)
    s = np.bincount(e, weights=pnl[ok], minlength=len(ev_list))
    n = np.bincount(e, minlength=len(ev_list))
    return np.where(n > 0, s / np.maximum(n, 1), np.nan), n


def summarize(D, v):
    v = v[np.isfinite(v)]
    if len(v) < 3:
        return {"n": int(len(v)), "mean": float("nan"), "ci": [float("nan")] * 2, "t": float("nan"), "p_boot": float("nan")}
    idx = D.rng.integers(0, len(v), size=(B, len(v)))
    bm = v[idx].mean(axis=1)
    lo, hi = ci(bm)
    t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))
    p = 2 * min(np.mean(bm <= 0), np.mean(bm >= 0))
    return {"n": int(len(v)), "mean": float(v.mean()), "ci": [lo, hi], "t": float(t), "p_boot": float(max(p, 1.0 / B)),
            "median": float(np.median(v)), "hit": float(np.mean(v > 0))}


def table_trade(D):
    out = {}
    for kind in ("down", "up"):
        if len(D.events_of(kind)) == 0:
            continue
        side = "sell laggards, buy back" if kind == "down" else "buy laggards, sell (mirror)"
        print(f"\n## Trading the lag [{kind} events: {side}]. Mean PnL per event in bps, laggards = moved less than "
              f"{PHI:.0%} of beta x Bitcoin's move at the decision. 24 cells; p is Bonferroni-adjusted x24 where marked adj.")
        print("| delay | horizon | hedge | events with a trade | trades per event | gross (VWAP) | net of assumed costs [95%] | "
              "p adj | net, executable proxy [95%] | laggard minus non-laggard, gross [95%] |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for d in DELAYS:
            for H in HORIZONS:
                for hedged in (False, True):
                    g, n = trade_pnls(D, kind, d, H, "gross", hedged)
                    a, _ = trade_pnls(D, kind, d, H, "assumed", hedged)
                    x, _ = trade_pnls(D, kind, d, H, "exec", hedged)
                    c, _ = trade_pnls(D, kind, d, H, "gross", hedged, laggards=False)
                    sg, sa, sx, sd = summarize(D, g), summarize(D, a), summarize(D, x), summarize(D, g - c)
                    key = f"{kind}|d{d}|H{H}|{'hedged' if hedged else 'outright'}"
                    out[key] = {"gross": sg, "net_assumed": sa, "net_exec": sx, "lag_minus_nonlag_gross": sd,
                                "events_with_trade": int((n > 0).sum()), "trades_per_event": float(n[n > 0].mean()) if (n > 0).any() else 0.0,
                                "p_bonferroni_24": float(min(1.0, sa["p_boot"] * 24)) if np.isfinite(sa["p_boot"]) else float("nan")}
                    print(f"| {d} s | {H} s | {'BTC' if hedged else 'none'} | {out[key]['events_with_trade']} | "
                          f"{fmt(out[key]['trades_per_event'], 1)} | {fmt(sg['mean'])} | {fmt(sa['mean'])} [{fmt(sa['ci'][0])}, {fmt(sa['ci'][1])}] | "
                          f"{fmt(out[key]['p_bonferroni_24'], 3)} | {fmt(sx['mean'])} [{fmt(sx['ci'][0])}, {fmt(sx['ci'][1])}] | "
                          f"{fmt(sd['mean'])} [{fmt(sd['ci'][0])}, {fmt(sd['ci'][1])}] |")
        print(f"\n### By tier [{kind}], outright, net of assumed costs (mean bps per event [95%]; events; median USD traded in "
              f"the 5 s after the decision per laggard)")
        print("| delay | horizon | " + " | ".join(TIER_NAME[t] for t in TIERS) + " |")
        print("|---|---|---|---|---|")
        for d in DELAYS:
            for H in HORIZONS:
                cells = []
                for t in TIERS:
                    a, n = trade_pnls(D, kind, d, H, "assumed", False, tier=t)
                    g, _ = trade_pnls(D, kind, d, H, "gross", False, tier=t)
                    sa, sg = summarize(D, a), summarize(D, g)
                    ev_list = D.events_of(kind)
                    m = ~D.is_btc & np.isin(D.ev, ev_list) & (D.ec["beta"] > 0) & (D.ec["tier"] == t)
                    b = D.btc[f"cr_{d}"][D.ev]
                    tgt = PHI * D.ec["beta"] * b
                    lagm = m & (((b < 0) & (D.ec[f"cr_{d}"] > tgt)) if kind == "down" else ((b > 0) & (D.ec[f"cr_{d}"] < tgt)))
                    cap = float(np.nanmedian(D.ec[f"qv5_{d}"][lagm])) if lagm.any() else float("nan")
                    out[f"{kind}|d{d}|H{H}|tier{t}"] = {"net_assumed": sa, "gross": sg, "median_qv5_usd": cap,
                                                         "laggard_share": float(lagm.sum() / max(m.sum(), 1))}
                    cells.append(f"{fmt(sa['mean'])} [{fmt(sa['ci'][0])}, {fmt(sa['ci'][1])}]; gross {fmt(sg['mean'])}; n={sa['n']}; "
                                 f"${fmt(cap, 0)}; laggards {fmt(100 * lagm.sum() / max(m.sum(), 1), 0)}%")
                print(f"| {d} s | {H} s | " + " | ".join(cells) + " |")
    return out


def table_speed(D):
    """The owner's prior P1: net PnL of the lag rule against the reaction delay, in one table."""
    out = {}
    for kind in ("down", "up"):
        if len(D.events_of(kind)) == 0:
            continue
        print(f"\n## Decay with speed [{kind} events]: mean PnL per event in bps by reaction delay. The 0 s row is a "
              f"reference for a faster actor; the owner's bot reacts in about 1 to 2 s.")
        print("| delay | events with a trade | laggards per event | gross 30 s | net 30 s [95%] | net 5 min [95%] | net 30 min [95%] | "
              "hedged net 30 s [95%] | hedged net 5 min [95%] | executable-proxy net 30 s [95%] |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for d in ALL_DELAYS:
            row = {}
            g, n = trade_pnls(D, kind, d, 30, "gross", False)
            row["events_with_trade"] = int((n > 0).sum())
            row["laggards_per_event"] = float(n[n > 0].mean()) if (n > 0).any() else 0.0
            row["gross_30"] = summarize(D, g)
            cells = [f"{d} s", str(row["events_with_trade"]), fmt(row["laggards_per_event"], 1), fmt(row["gross_30"]["mean"])]
            for H, hedged, price in ((30, False, "assumed"), (300, False, "assumed"), (1800, False, "assumed"),
                                     (30, True, "assumed"), (300, True, "assumed"), (30, False, "exec")):
                a, _ = trade_pnls(D, kind, d, H, price, hedged)
                sm = summarize(D, a)
                row[f"{price}_{'hedged' if hedged else 'outright'}_{H}"] = sm
                cells.append(f"{fmt(sm['mean'])} [{fmt(sm['ci'][0])}, {fmt(sm['ci'][1])}]")
            out[f"{kind}|d{d}"] = row
            print("| " + " | ".join(cells) + " |")
    return out



def table_split(D):
    """Choose the best cell on the early events, evaluate it once on the late events."""
    out = {}
    for kind in ("down", "up"):
        ev = D.events_of(kind)
        if len(ev) == 0:
            continue
        late = D.late[ev]
        best, best_key = -np.inf, None
        cells = {}
        for d in DELAYS:
            for H in HORIZONS:
                for hedged in (False, True):
                    a, _ = trade_pnls(D, kind, d, H, "assumed", hedged)
                    cells[(d, H, hedged)] = a
                    early = a[~late]
                    early = early[np.isfinite(early)]
                    if len(early) >= 5 and early.mean() > best:
                        best, best_key = early.mean(), (d, H, hedged)
        if best_key is None:
            continue
        a = cells[best_key]
        se, sl = summarize(D, a[~late]), summarize(D, a[late])
        g, _ = trade_pnls(D, kind, best_key[0], best_key[1], "gross", best_key[2])
        out[kind] = {"best_cell": {"delay": best_key[0], "horizon": best_key[1], "hedged": best_key[2]},
                     "selection": se, "evaluation": sl, "evaluation_gross": summarize(D, g[late])}
        print(f"\n## Split in time [{kind}]: best cell on the early events is delay {best_key[0]} s, horizon {best_key[1]} s, "
              f"{'hedged' if best_key[2] else 'outright'}")
        print("| sample | events with a trade | mean net PnL per event, bps [95%] | t | share of events > 0 |")
        print("|---|---|---|---|---|")
        print(f"| selection (early) | {se['n']} | {fmt(se['mean'])} [{fmt(se['ci'][0])}, {fmt(se['ci'][1])}] | {fmt(se['t'], 2)} | {fmt(100 * se.get('hit', np.nan), 0)}% |")
        print(f"| evaluation (late) | {sl['n']} | {fmt(sl['mean'])} [{fmt(sl['ci'][0])}, {fmt(sl['ci'][1])}] | {fmt(sl['t'], 2)} | {fmt(100 * sl.get('hit', np.nan), 0)}% |")
    return out


def table_spread(D):
    out = {}
    print("\n## Effective spread proxy: taker-buy VWAP minus taker-sell VWAP within one second, bps (median over coins "
          "and windows of the per-window median); the assumed half-spreads are 2 / 5 / 10 bps, i.e. full 4 / 10 / 20")
    print("| windows | segment | BTC | " + " | ".join(TIER_NAME[t] for t in TIERS) + " |")
    print("|---|---|---|---|---|---|")
    for kind in ("random", "down", "up"):
        ev_list = D.events_of(kind)
        if len(ev_list) == 0:
            continue
        for seg in ("pre", "shock", "post"):
            cells = []
            for t in (0, 1, 2, 3):
                m = np.isin(D.ev, ev_list) & (D.is_btc if t == 0 else ((D.ec["tier"] == t) & ~D.is_btc))
                v = D.ec[f"es_{seg}"][m].astype(float)
                med = float(np.nanmedian(v)) if np.isfinite(v).any() else float("nan")
                out[f"{kind}|{seg}|{TIER_NAME[t]}"] = {"median_full_spread_bps": med, "mean": float(np.nanmean(v)) if np.isfinite(v).any() else float("nan"),
                                                       "share_with_estimate": float(np.mean(np.isfinite(v)))}
                cells.append(f"{fmt(med, 2)} ({fmt(100 * np.mean(np.isfinite(v)), 0)}% with estimate)")
            print(f"| {kind} | {seg} | " + " | ".join(cells) + " |")
    return out


TABLES = {"events": table_events, "cr": table_cr, "share": table_share, "half": table_half, "catchup": table_catchup,
          "stale": table_stale, "leadlag": table_leadlag, "fresh": table_fresh, "trade": table_trade, "speed": table_speed,
          "split": table_split, "spread": table_spread}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", choices=sorted(TABLES), default=None)
    args = ap.parse_args()
    D = Data()
    summary = {}
    for name, fn in TABLES.items():
        if args.table and name != args.table:
            continue
        D.rng = np.random.default_rng(C.SEED + 10 + sorted(TABLES).index(name))   # each table has its own fixed seed
        summary[name] = fn(D)
    if not args.table:
        with open(os.path.join(P1, "summary.json"), "w") as f:
            json.dump(summary, f, indent=1, sort_keys=True, default=C._jsonable)
            f.write("\n")
        print(f"\nwrote {os.path.join(P1, 'summary.json')}")


if __name__ == "__main__":
    sys.exit(main())
