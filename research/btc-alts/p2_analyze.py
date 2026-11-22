"""Part 2 inference from the committed compact tables (no network).

Run:  python p2_analyze.py                 all tables, writes out/p2/summary.json
      python p2_analyze.py --table configs one table (configs, years, split, maxstat, pairs, hindsight, trades, bh,
                                           shock, speed, size)
      BTCALTS_TEST=1 python p2_analyze.py  the same on the synthetic market
Returns are daily PnL on committed gross notional (20 pairs x 2 legs). Net = gross - fee x traded notional
- half-spreads + funding. Annualised with 365 days.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import math
import os
import sys

import numpy as np
import polars as pl

import common as C

TEST = os.environ.get("BTCALTS_TEST") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "out_test" if TEST else "out")
P2 = os.path.join(OUT_ROOT, "p2")
B = 10_000
BLOCK = 30
N_TRIALS = 24          # hourly 8 x 2 timings, 5-minute A 2 x 2, 5-minute B 2 x 2
TAGS = ("1h", "5mA", "5mB")
EULER = 0.5772156649015329


def fmt(x, nd=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"{x:.{nd}f}"


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    from scipy.stats import norm
    return float(norm.ppf(p))


def read_gz(name):
    with gzip.open(os.path.join(P2, name), "rt") as f:
        return list(csv.DictReader(f))


class Data:
    def __init__(self):
        cfg = C.load_config() if TEST else C.Config()
        self.split_date = dt.datetime.fromtimestamp(cfg.split_p2 / 1000, C.UTC).strftime("%Y-%m-%d")
        self.series, self.dates, self.hind = {}, {}, {}
        self.tags = [t for t in TAGS if os.path.exists(os.path.join(P2, f"daily_{t}.csv.gz"))]
        for tag in self.tags:
            rows = read_gz(f"daily_{tag}.csv.gz")
            self.dates[tag] = [r["date"] for r in rows]
            names = sorted({k.split("|")[0] for k in rows[0] if "|" in k and not k.split("|")[0].endswith("_hindsight")})
            for nm in names:
                self.series[nm] = {key: np.array([float(r[f"{nm}|{key}"]) for r in rows]) for key in ("gross", "n1", "n2", "n3", "fund")}
                self.series[nm]["feen"] = self.series[nm]["n1"] + self.series[nm]["n2"] + self.series[nm]["n3"]
            for k in rows[0]:
                if k.endswith("_hindsight|net"):
                    self.hind[k.split("|")[0]] = np.array([float(r[k]) for r in rows])
        self.placebo = {}
        for tag in self.tags:
            for r in read_gz(f"placebo_{tag}.csv.gz"):
                self.placebo.setdefault(r["config"], []).append(r)
        self.rng = np.random.default_rng(C.SEED + 50)

    def tag(self, nm):
        return nm.split("_")[0]

    def net(self, nm, fee=C.TAKER_FEE, hs=None, funding=True):
        """Daily net return. hs: half-spread (or measured cost of crossing) in bps for tiers 1, 2, 3."""
        s = self.series[nm]
        hs = (C.HALF_SPREAD[1], C.HALF_SPREAD[2], C.HALF_SPREAD[3]) if hs is None else hs
        cost = sum((fee + hs[i]) * 1e-4 * s[f"n{i + 1}"] for i in range(3))
        return s["gross"] - cost + (s["fund"] if funding else 0.0)

    def spread_cost(self, nm):
        s = self.series[nm]
        return sum(C.HALF_SPREAD[i + 1] * 1e-4 * s[f"n{i + 1}"] for i in range(3))

    def book_costs(self):
        """Measured cost of crossing today's spot order books for 1,000 and 10,000 USD, bps per side by tier
        (median over coins), from out/s2/depth_summary.json if the depth snapshot has run."""
        path = os.path.join(OUT_ROOT, "s2", "depth_summary.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            d = json.load(f)
        return {k: tuple(d["by_tier"][f"tier{t}"][k] for t in (1, 2, 3)) for k in ("cost_1k_median_bps", "cost_10k_median_bps", "cost_1k_p75_bps", "cost_10k_p75_bps")}

    def boot_idx(self, n):
        """Stationary bootstrap indices, mean block BLOCK days."""
        restart = self.rng.random((B, n)) < 1.0 / BLOCK
        starts = self.rng.integers(0, n, size=(B, n))
        idx = np.empty((B, n), np.int32)
        idx[:, 0] = starts[:, 0]
        for t in range(1, n):
            idx[:, t] = np.where(restart[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
        return idx


def sharpe(x):
    sd = x.std(ddof=1)
    return float(x.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0


def risk(x):
    cum = np.cumsum(x)
    dd = float((cum - np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]).min())
    k = max(1, int(math.floor(0.05 * len(x))))
    es = float(np.sort(x)[:k].mean())
    w5 = float(np.convolve(x, np.ones(5), "valid").min()) if len(x) >= 5 else float("nan")
    return {"es5_bps": es * 1e4, "worst_day_bps": float(x.min() * 1e4), "worst_5d_bps": w5 * 1e4, "max_drawdown_bps": dd * 1e4}


def deflated_sharpe(x, sr_trials, n_trials=N_TRIALS):
    """Bailey and Lopez de Prado (2014). Per-day Sharpe ratios; returns (PSR against 0, DSR, SR0 annualised)."""
    from scipy.stats import kurtosis, skew
    T = len(x)
    sr = x.mean() / x.std(ddof=1)
    g3, g4 = float(skew(x)), float(kurtosis(x, fisher=False))
    v = float(np.var(sr_trials, ddof=1))
    sr0 = math.sqrt(v) * ((1 - EULER) * norm_ppf(1 - 1.0 / n_trials) + EULER * norm_ppf(1 - 1.0 / (n_trials * math.e)))
    den = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr * sr))
    psr = norm_cdf((sr - 0.0) * math.sqrt(T - 1) / den)
    dsr = norm_cdf((sr - sr0) * math.sqrt(T - 1) / den)
    return psr, dsr, sr0 * math.sqrt(365)


def table_configs(D):
    out = {}
    sr_day = {nm: (lambda x: x.mean() / x.std(ddof=1) if x.std(ddof=1) > 0 else 0.0)(D.net(nm)) for nm in D.series}
    trials = np.array(list(sr_day.values()))
    idx_cache = {}
    print("\n## All configurations: annualised return on committed gross notional, % per year. Net = taker 5 bps + half-spread "
          "+ funding. Late = every fill one bar later. p placebo = share of 1,000 random-pair portfolios with at least this net PnL.")
    print("| configuration | timing | gross | net | net 95% (block bootstrap) | Sharpe net | maker-fee case | spot-fee case | "
          "funding | placebo mean net | p placebo | PSR(0) | deflated Sharpe (N=24) | ES 5% day, bps | worst day | worst 5 days | max drawdown |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for nm in sorted(D.series):
        tag = D.tag(nm)
        n = len(D.dates[tag])
        yrs = n / 365.0
        x = D.net(nm)
        g = D.series[nm]["gross"]
        if n not in idx_cache:
            idx_cache[n] = D.boot_idx(n)
        bm = x[idx_cache[n]].mean(axis=1) * 365 * 100
        lo, hi = np.percentile(bm, [2.5, 97.5])
        p_boot = float(np.mean(bm <= 0))
        pl_net = np.array([float(r["net_bps"]) for r in D.placebo[nm]])
        pl_sh = np.array([float(r["sharpe"]) for r in D.placebo[nm]])
        tot = x.sum() * 1e4
        p_plac = float((np.sum(pl_net >= tot) + 1) / (len(pl_net) + 1))
        psr, dsr, sr0 = deflated_sharpe(x, trials)
        rk = risk(x)
        row = {"days": n, "gross_ann_pct": float(g.sum() / yrs * 100), "net_ann_pct": float(x.sum() / yrs * 100),
               "net_ci_ann_pct": [float(lo), float(hi)], "p_boot_mean_le_0": p_boot, "sharpe_net": sharpe(x), "sharpe_gross": sharpe(g),
               "net_maker_ann_pct": float(D.net(nm, fee=C.MAKER_FEE, hs=(0.0, 0.0, 0.0)).sum() / yrs * 100),
               "net_spot_fee_ann_pct": float(D.net(nm, fee=C.SPOT_TAKER_FEE).sum() / yrs * 100),
               "funding_ann_pct": float(D.series[nm]["fund"].sum() / yrs * 100),
               "fee_cost_ann_pct": float(C.TAKER_FEE * 1e-4 * D.series[nm]["feen"].sum() / yrs * 100),
               "spread_cost_ann_pct": float(D.spread_cost(nm).sum() / yrs * 100),
               "share_notional_by_tier": [float(D.series[nm][f"n{i}"].sum() / max(D.series[nm]["feen"].sum(), 1e-12)) for i in (1, 2, 3)],
               "turnover_per_year": float(D.series[nm]["feen"].sum() / yrs),
               "placebo_mean_net_ann_pct": float(pl_net.mean() / 1e4 / yrs * 100), "placebo_mean_sharpe": float(pl_sh.mean()),
               "p_placebo_net": p_plac, "p_placebo_sharpe": float((np.sum(pl_sh >= sharpe(x)) + 1) / (len(pl_sh) + 1)),
               "psr0": psr, "dsr": dsr, "sr0_annualised": sr0, **rk}
        out[nm] = row
        parts = nm.split("_")
        print(f"| {' '.join(parts[:-1])} | {parts[-1]} | {fmt(row['gross_ann_pct'])} | {fmt(row['net_ann_pct'])} | "
              f"[{fmt(lo)}, {fmt(hi)}] | {fmt(row['sharpe_net'], 2)} | {fmt(row['net_maker_ann_pct'])} | {fmt(row['net_spot_fee_ann_pct'])} | "
              f"{fmt(row['funding_ann_pct'], 2)} | {fmt(row['placebo_mean_net_ann_pct'])} | {fmt(p_plac, 3)} | {fmt(psr, 3)} | {fmt(dsr, 3)} | "
              f"{fmt(rk['es5_bps'])} | {fmt(rk['worst_day_bps'])} | {fmt(rk['worst_5d_bps'])} | {fmt(rk['max_drawdown_bps'], 0)} |")
    return out


def table_years(D):
    out = {}
    print("\n## Net PnL by calendar year, % of committed gross notional (taker costs and funding); placebo mean in brackets")
    for tag in D.tags:
        dates = D.dates[tag]
        years = sorted({d[:4] for d in dates})
        yr = np.array([d[:4] for d in dates])
        print(f"\n| configuration ({tag}) | " + " | ".join(years) + " |")
        print("|---|" + "---|" * len(years))
        for nm in sorted(n_ for n_ in D.series if D.tag(n_) == tag):
            x = D.net(nm)
            cells, row = [], {}
            for y in years:
                v = float(x[yr == y].sum() * 100)
                pm = float(np.mean([float(r[f"net_{y}_bps"]) for r in D.placebo[nm]]) / 100)
                row[y] = {"net_pct": v, "placebo_mean_pct": pm, "gross_pct": float(D.series[nm]["gross"][yr == y].sum() * 100)}
                cells.append(f"{fmt(v)} ({fmt(pm)})")
            out[nm] = row
            print(f"| {nm} | " + " | ".join(cells) + " |")
    return out


def table_split(D):
    """Best hourly configuration on the windows before the split date, evaluated once after it."""
    dates = D.dates["1h"]
    early = np.array([d < D.split_date for d in dates])
    hourly = sorted(n_ for n_ in D.series if D.tag(n_) == "1h")
    sel = {nm: sharpe(D.net(nm)[early]) for nm in hourly}
    best = max(sel, key=sel.get)
    x = D.net(best)
    ne, nl = int(early.sum()), int((~early).sum())
    idx = D.boot_idx(nl)
    xl = x[~early]
    bm = xl[idx].mean(axis=1) * 365 * 100
    pe = np.array([float(r["net_evaluation_bps"]) for r in D.placebo[best]])
    out = {"split_date": D.split_date, "best_on_selection": best, "selection_sharpe": sel[best],
           "selection_net_ann_pct": float(x[early].sum() / (ne / 365) * 100), "evaluation_sharpe": sharpe(xl),
           "evaluation_net_ann_pct": float(xl.sum() / (nl / 365) * 100), "evaluation_ci_ann_pct": [float(v) for v in np.percentile(bm, [2.5, 97.5])],
           "evaluation_p_placebo": float((np.sum(pe >= xl.sum() * 1e4) + 1) / (len(pe) + 1)),
           "all_selection_sharpes": sel, "all_evaluation_sharpes": {nm: sharpe(D.net(nm)[~early]) for nm in hourly},
           "all_evaluation_net_ann_pct": {nm: float(D.net(nm)[~early].sum() / (nl / 365) * 100) for nm in hourly}}
    print(f"\n## Split in time (hourly): selection = days before {D.split_date} ({ne} days), evaluation = after ({nl} days)")
    print("| | configuration | Sharpe net | net % per year |")
    print("|---|---|---|---|")
    print(f"| best on selection | {best} | {fmt(out['selection_sharpe'], 2)} | {fmt(out['selection_net_ann_pct'])} |")
    print(f"| the same on evaluation | {best} | {fmt(out['evaluation_sharpe'], 2)} | {fmt(out['evaluation_net_ann_pct'])} "
          f"[{fmt(out['evaluation_ci_ann_pct'][0])}, {fmt(out['evaluation_ci_ann_pct'][1])}], p placebo {fmt(out['evaluation_p_placebo'], 3)} |")
    print("\n| configuration | Sharpe selection | Sharpe evaluation | net % per year, evaluation |")
    print("|---|---|---|---|")
    for nm in hourly:
        print(f"| {nm} | {fmt(sel[nm], 2)} | {fmt(out['all_evaluation_sharpes'][nm], 2)} | {fmt(out['all_evaluation_net_ann_pct'][nm])} |")
    return out


def table_maxstat(D):
    """The best configuration against the best-of-all-configurations placebo (same draw index across configurations)."""
    out = {}
    for tag in D.tags:
        names = sorted(n_ for n_ in D.series if D.tag(n_) == tag)
        real = {nm: sharpe(D.net(nm)) for nm in names}
        real_net = {nm: float(D.net(nm).sum() * 1e4) for nm in names}
        ps = np.array([[float(r["sharpe"]) for r in D.placebo[nm]] for nm in names])
        pn = np.array([[float(r["net_bps"]) for r in D.placebo[nm]] for nm in names])
        best = max(real, key=real.get)
        bestn = max(real_net, key=real_net.get)
        out[tag] = {"best_sharpe_config": best, "best_sharpe": real[best], "placebo_max_sharpe_q50_q95": [float(v) for v in np.percentile(ps.max(axis=0), [50, 95])],
                    "p_max_sharpe": float((np.sum(ps.max(axis=0) >= real[best]) + 1) / (ps.shape[1] + 1)),
                    "best_net_config": bestn, "best_net_bps": real_net[bestn],
                    "p_max_net": float((np.sum(pn.max(axis=0) >= real_net[bestn]) + 1) / (pn.shape[1] + 1)), "n_configs": len(names)}
        o = out[tag]
        print(f"\n## Best of {len(names)} configurations against the best-of-{len(names)} random-pair placebo [{tag}]: best Sharpe "
              f"{fmt(o['best_sharpe'], 2)} ({best}); placebo best-of median {fmt(o['placebo_max_sharpe_q50_q95'][0], 2)}, 95th percentile "
              f"{fmt(o['placebo_max_sharpe_q50_q95'][1], 2)}; p = {fmt(o['p_max_sharpe'], 3)}. Best net PnL {fmt(o['best_net_bps'], 0)} bps ({bestn}), p = {fmt(o['p_max_net'], 3)}")
    return out


def table_pairs(D):
    out = {}
    rows = read_gz("selected_pairs.csv.gz")
    for tag in D.tags:
        for m in ("dist", "coint"):
            agg, wins = {}, set()
            for r in rows:
                if r["bar"] != tag or r["method"] != m:
                    continue
                wins.add(r["window"])
                key = " / ".join(sorted([r["a"].replace("USDT", ""), r["b"].replace("USDT", "")]))
                a = agg.setdefault(key, [0, 0.0, 0.0, 0.0])
                a[0] += 1
                a[1] += float(r["net_bps"]); a[2] += float(r["gross_bps"]); a[3] += float(r["net_late_bps"])
            top = sorted(agg.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:12]
            n_sel = sum(v[0] for v in agg.values())
            pos = sum(1 for v in agg.values() if v[1] > 0)
            out[f"{tag}_{m}"] = {"windows": len(wins), "distinct_pairs": len(agg), "selections": n_sel, "share_pairs_net_positive": pos / max(len(agg), 1),
                                 "top": [{"pair": k, "times_selected": v[0], "net_bps_sum": v[1], "gross_bps_sum": v[2], "net_late_bps_sum": v[3]} for k, v in top]}
            print(f"\n## Pairs selected most often [{tag}, {m}]: {len(agg)} distinct pairs in {len(wins)} windows; "
                  f"{fmt(100 * pos / max(len(agg), 1), 0)}% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.")
            print("| pair | times selected | gross | net | net, one bar late |")
            print("|---|---|---|---|---|")
            for k, v in top:
                print(f"| {k} | {v[0]} | {fmt(v[2], 0)} | {fmt(v[1], 0)} | {fmt(v[3], 0)} |")
    return out


def table_hindsight(D):
    """What naming winners after the fact is worth: hindsight portfolios, and persistence of pair PnL."""
    out = {}
    n = len(D.dates["1h"])
    yrs = n / 365.0
    for m in ("dist", "coint"):
        h = D.hind.get(f"1h_{m}_hindsight")
        if h is not None:
            out[f"hindsight_{m}_net_ann_pct"] = float(h.sum() / yrs * 100)
            out[f"causal_{m}_net_ann_pct"] = float(D.net(f"1h_{m}_e2.0_ontime").sum() / yrs * 100)
    path = os.path.join(P2, "allpairs.parquet")
    if os.path.exists(path):
        ap = pl.read_parquet(path).with_columns([pl.col("a").cast(pl.Utf8), pl.col("b").cast(pl.Utf8)])
        from scipy.stats import spearmanr
        for m in ("dist", "coint"):
            col = f"net_{m}"
            cur = ap.select(["window", "a", "b", col])
            nxt = cur.with_columns((pl.col("window") - 1).alias("window")).rename({col: "next"})
            j = cur.join(nxt, on=["window", "a", "b"], how="inner")
            x, y = j[col].to_numpy().astype(float), j["next"].to_numpy().astype(float)
            w = j["window"].to_numpy()
            rhos, top_next, rest_next = [], [], []
            for k in np.unique(w):
                mk = w == k
                if mk.sum() < 100:
                    continue
                rhos.append(spearmanr(x[mk], y[mk]).statistic)
                thr = np.percentile(x[mk], 90)
                top_next.append(y[mk][x[mk] >= thr].mean())
                rest_next.append(y[mk][x[mk] < thr].mean())
            rhos = np.array(rhos)
            diff = np.array(top_next) - np.array(rest_next)
            bi = D.rng.integers(0, len(rhos), size=(B, len(rhos)))
            out[f"persistence_{m}"] = {"window_pairs": int(len(rhos)), "mean_spearman": float(rhos.mean()),
                                       "spearman_ci": [float(v) for v in np.percentile(rhos[bi].mean(axis=1), [2.5, 97.5])],
                                       "top_decile_next_bps": float(np.mean(top_next)), "rest_next_bps": float(np.mean(rest_next)),
                                       "diff_ci_bps": [float(v) for v in np.percentile(diff[bi].mean(axis=1), [2.5, 97.5])],
                                       "all_pairs_mean_net_bps": float(ap[col].mean()), "all_pairs_share_positive": float((ap[col] > 0).mean())}
    print("\n## Hindsight check (hourly, base rule). Net % per year on committed gross notional")
    print("| method | selected in advance | the 20 best pairs of each window, chosen afterwards |")
    print("|---|---|---|")
    for m in ("dist", "coint"):
        print(f"| {m} | {fmt(out.get(f'causal_{m}_net_ann_pct'))} | {fmt(out.get(f'hindsight_{m}_net_ann_pct'))} |")
    print("\n| method | rank correlation of a pair's net PnL in consecutive windows [95%] | next-window net PnL of this window's top decile, bps | "
          "of the other pairs | difference 95% | mean net PnL of all pairs per window, bps | share of pair-windows with net > 0 |")
    print("|---|---|---|---|---|---|---|")
    for m in ("dist", "coint"):
        p = out.get(f"persistence_{m}")
        if p:
            print(f"| {m} | {fmt(p['mean_spearman'], 3)} [{fmt(p['spearman_ci'][0], 3)}, {fmt(p['spearman_ci'][1], 3)}] | {fmt(p['top_decile_next_bps'])} | "
                  f"{fmt(p['rest_next_bps'])} | [{fmt(p['diff_ci_bps'][0])}, {fmt(p['diff_ci_bps'][1])}] | {fmt(p['all_pairs_mean_net_bps'])} | {fmt(100 * p['all_pairs_share_positive'], 0)}% |")
    return out


def table_trades(D):
    out = {}
    rows = read_gz("trades.csv.gz")
    print("\n## Trades of the selected pairs (base rule). PnL in bps of one leg's notional")
    print("| bar | method | timing | trades | mean gross | mean cost | mean funding | mean net | share net > 0 | closed at 0 / stop / window end / delisted | "
          "median hold, hours | median volume of the thinner leg in the signal bar, USD | 10th percentile | both legs had a perpetual |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for tag in D.tags:
        for m in ("dist", "coint"):
            for tm in ("ontime", "late"):
                tr = [r for r in rows if r["bar"] == tag and r["method"] == m and r["timing"] == tm]
                if not tr:
                    continue
                g = np.array([float(r["gross_bps"]) for r in tr]); c = np.array([float(r["cost_taker_bps"]) for r in tr])
                f = np.array([float(r["funding_bps"]) for r in tr])
                net = g - c + f
                reason = np.array([int(r["exit_reason"]) for r in tr])
                hold = np.array([(dt.datetime.strptime(r["exit_utc"], "%Y-%m-%dT%H:%M:%SZ") - dt.datetime.strptime(r["entry_utc"], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 3600 for r in tr])
                qv = np.array([float(r["min_leg_quote_volume_signal_bar"]) for r in tr])
                both = np.array([r["perp_a"] == "1" and r["perp_b"] == "1" for r in tr])
                o = {"trades": len(tr), "mean_gross": float(g.mean()), "mean_cost": float(c.mean()), "mean_funding": float(f.mean()), "mean_net": float(net.mean()),
                     "hit": float((net > 0).mean()), "exit_cross": float((reason == 1).mean()), "exit_stop": float((reason == 2).mean()),
                     "exit_end": float((reason == 4).mean()), "exit_dead": float((reason == 3).mean()), "median_hold_h": float(np.median(hold)),
                     "median_qv": float(np.median(qv)), "p10_qv": float(np.percentile(qv, 10)), "both_perp": float(both.mean()),
                     "mean_net_stop": float(net[reason == 2].mean()) if (reason == 2).any() else float("nan"),
                     "mean_net_cross": float(net[reason == 1].mean()) if (reason == 1).any() else float("nan"),
                     "mean_net_end": float(net[reason == 4].mean()) if (reason == 4).any() else float("nan")}
                out[f"{tag}_{m}_{tm}"] = o
                print(f"| {tag} | {m} | {tm} | {o['trades']} | {fmt(o['mean_gross'])} | {fmt(o['mean_cost'])} | {fmt(o['mean_funding'], 2)} | {fmt(o['mean_net'])} | "
                      f"{fmt(100 * o['hit'], 0)}% | {fmt(100 * o['exit_cross'], 0)}% / {fmt(100 * o['exit_stop'], 0)}% / {fmt(100 * o['exit_end'], 0)}% / {fmt(100 * o['exit_dead'], 0)}% | "
                      f"{fmt(o['median_hold_h'], 1)} | {fmt(o['median_qv'], 0)} | {fmt(o['p10_qv'], 0)} | {fmt(100 * o['both_perp'], 0)}% |")
    return out


def table_bh(D):
    rows = read_gz("windows.csv.gz")
    out = {}
    print("\n## Cointegration tests per window, Benjamini-Hochberg at 5% over all pairs of the universe")
    print("| bar | windows | pairs per window (median) | pairs passing BH (median, mean, max) | windows with none | selected pairs that pass (mean of 20) |")
    print("|---|---|---|---|---|---|")
    for tag in D.tags:
        w = [r for r in rows if r["bar"] == tag]
        if not w:
            continue
        bh = np.array([float(r["bh_fixed_order"]) for r in w]); pr = np.array([float(r["pairs"]) for r in w])
        bs = np.array([float(r["bh_selected"]) for r in w])
        out[tag] = {"windows": len(w), "median_pairs": float(np.median(pr)), "bh_median": float(np.median(bh)), "bh_mean": float(bh.mean()),
                    "bh_max": float(bh.max()), "windows_with_none": int((bh == 0).sum()), "selected_passing_mean": float(bs.mean())}
        o = out[tag]
        print(f"| {tag} | {o['windows']} | {fmt(o['median_pairs'], 0)} | {fmt(o['bh_median'], 0)}, {fmt(o['bh_mean'], 1)}, {fmt(o['bh_max'], 0)} | {o['windows_with_none']} | {fmt(o['selected_passing_mean'], 1)} |")
    return out


def table_shock(D):
    rows = read_gz("shock_events.csv.gz")
    out = {}
    plc = {}
    for r in rows:
        if r["set"] == "placebo":
            plc.setdefault(int(r["H"]), []).append(r)
    print("\n## Overshoot and reversion after a Bitcoin shock: buy the 10 coins that fell most against beta x Bitcoin, short beta "
          "x Bitcoin, from one to two hours after the shock. Mean per event, bps of the coin leg [95%, bootstrap over weeks]")
    print("| events | hold | n | mean abnormal return of all coins in the shock window | of the 10 picked | gross | net taker | net maker-fee case | "
          "share of events net > 0 | placebo gross (random hours) | p vs placebo | cross-sectional slope of later return on shock-window abnormal return | all coins hedged, gross |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for st in ("A_1min_down", "B_hourly_down", "A_1min_up_mirror", "B_hourly_up_mirror"):
        for H in (4, 24, 72):
            ev = [r for r in rows if r["set"] == st and int(r["H"]) == H]
            if len(ev) < 5:
                continue
            g = np.array([float(r["gross_bps"]) for r in ev])
            net = g - np.array([float(r["cost_taker_bps"]) for r in ev]) + np.array([float(r["funding_bps"]) for r in ev])
            netm = g - np.array([float(r["cost_maker_bps"]) for r in ev]) + np.array([float(r["funding_bps"]) for r in ev])
            sl = np.array([float(r["xs_slope"]) for r in ev]); allc = np.array([float(r["all_coins_hedged_bps"]) for r in ev])
            ar_all = np.array([float(r["mean_ar_all_bps"]) for r in ev]); ar_p = np.array([float(r["mean_ar_picked_bps"]) for r in ev])
            wk = np.array([dt.datetime.strptime(r["utc"], "%Y-%m-%dT%H:%M:%SZ").strftime("%G-%V") for r in ev])
            uw = np.unique(wk)
            groups = [np.flatnonzero(wk == u) for u in uw]

            def boot(v):
                draws = []
                pick = D.rng.integers(0, len(groups), size=(4000, len(groups)))
                for row in pick:
                    ii = np.concatenate([groups[i] for i in row])
                    draws.append(v[ii].mean())
                return [float(x) for x in np.percentile(draws, [2.5, 97.5])]

            pg = np.array([float(r["gross_bps"]) for r in plc.get(H, [])])
            if len(pg):
                pm = pg[D.rng.integers(0, len(pg), size=(5000, len(g)))].mean(axis=1)
                p_pl = float((np.sum(pm >= g.mean()) + 1) / (len(pm) + 1))
            else:
                p_pl = float("nan")
            late_mask = np.array([r["utc"] >= ("2025-01-01" if st.startswith("A") else "2024-01-01") for r in ev])
            o = {"n": len(ev), "weeks": len(uw), "mean_ar_all": float(ar_all.mean()), "mean_ar_picked": float(ar_p.mean()), "gross": float(g.mean()),
                 "gross_ci": boot(g), "net": float(net.mean()), "net_ci": boot(net), "net_maker": float(netm.mean()), "net_maker_ci": boot(netm),
                 "hit_net": float((net > 0).mean()), "placebo_gross_mean": float(pg.mean()) if len(pg) else float("nan"), "p_vs_placebo": p_pl,
                 "slope": float(sl.mean()), "slope_ci": boot(sl), "all_coins": float(allc.mean()), "all_coins_ci": boot(allc),
                 "net_early": float(net[~late_mask].mean()) if (~late_mask).any() else float("nan"), "n_early": int((~late_mask).sum()),
                 "net_late": float(net[late_mask].mean()) if late_mask.any() else float("nan"), "n_late": int(late_mask.sum()),
                 "median_net": float(np.median(net)), "worst_event_net": float(net.min()), "mean_cost_taker": float(np.mean([float(r["cost_taker_bps"]) for r in ev])),
                 "mean_funding": float(np.mean([float(r["funding_bps"]) for r in ev]))}
            out[f"{st}|H{H}"] = o
            print(f"| {st} | {H} h | {o['n']} | {fmt(o['mean_ar_all'])} | {fmt(o['mean_ar_picked'])} | {fmt(o['gross'])} [{fmt(o['gross_ci'][0])}, {fmt(o['gross_ci'][1])}] | "
                  f"{fmt(o['net'])} [{fmt(o['net_ci'][0])}, {fmt(o['net_ci'][1])}] | {fmt(o['net_maker'])} [{fmt(o['net_maker_ci'][0])}, {fmt(o['net_maker_ci'][1])}] | "
                  f"{fmt(100 * o['hit_net'], 0)}% | {fmt(o['placebo_gross_mean'])} | {fmt(p_pl, 3)} | {fmt(o['slope'], 3)} [{fmt(o['slope_ci'][0], 3)}, {fmt(o['slope_ci'][1], 3)}] | "
                  f"{fmt(o['all_coins'])} [{fmt(o['all_coins_ci'][0])}, {fmt(o['all_coins_ci'][1])}] |")
    print("\n| events | hold | net, early part (n) | net, late part (n) | median net | worst event |")
    print("|---|---|---|---|---|---|")
    for k, o in out.items():
        st, H = k.split("|")
        print(f"| {st} | {H[1:]} h | {fmt(o['net_early'])} ({o['n_early']}) | {fmt(o['net_late'])} ({o['n_late']}) | {fmt(o['median_net'])} | {fmt(o['worst_event_net'])} |")
    return out


def table_size(D):
    """Trade size: 1,000 USD per leg as the main case, 10,000 USD as a reference line."""
    out = {}
    bc = D.book_costs()
    rows = read_gz("trades.csv.gz")
    print("\n## Trade size. Share of the signal bar's quote volume (thinner leg) that one leg of the trade would be")
    print("| bar | method | trades | median volume of the thinner leg in the signal bar, USD | 1,000 USD as a share of it (median) | "
          "trades where 1,000 USD is above 1% of it | 10,000 USD as a share (median) | trades where 10,000 USD is above 1% |")
    print("|---|---|---|---|---|---|---|---|")
    for tag in D.tags:
        for m in ("dist", "coint"):
            tr = [r for r in rows if r["bar"] == tag and r["method"] == m and r["timing"] == "ontime"]
            if not tr:
                continue
            qv = np.array([float(r["min_leg_quote_volume_signal_bar"]) for r in tr])
            qv = np.maximum(qv, 1.0)
            o = {"trades": len(tr), "median_qv": float(np.median(qv)), "share_1k_median": float(np.median(1000 / qv)),
                 "over_1pct_1k": float(np.mean(1000 / qv > 0.01)), "share_10k_median": float(np.median(10000 / qv)),
                 "over_1pct_10k": float(np.mean(10000 / qv > 0.01))}
            out[f"participation|{tag}_{m}"] = o
            print(f"| {tag} | {m} | {o['trades']} | {fmt(o['median_qv'], 0)} | {fmt(100 * o['share_1k_median'], 3)}% | {fmt(100 * o['over_1pct_1k'], 1)}% | "
                  f"{fmt(100 * o['share_10k_median'], 2)}% | {fmt(100 * o['over_1pct_10k'], 1)}% |")
    if bc is None:
        print("\n(no order-book snapshot yet: run s2_depth.py)")
        return out
    out["book_costs_bps_per_side"] = bc
    print("\n## Net result when the assumed half-spreads (2 / 5 / 10 bps) are replaced by the measured cost of crossing today's "
          "spot order books (median coin of each tier; bps per side: 1,000 USD " + " / ".join(fmt(x, 1) for x in bc["cost_1k_median_bps"])
          + "; 10,000 USD " + " / ".join(fmt(x, 1) for x in bc["cost_10k_median_bps"]) + "). % per year on committed gross notional")
    print("| configuration | timing | net, assumed costs | net at 1,000 USD per leg (main case) | at 1,000 USD, 75th-percentile coin | "
          "net at 10,000 USD per leg (reference) | at 10,000 USD, 75th-percentile coin |")
    print("|---|---|---|---|---|---|---|")
    for nm in sorted(D.series):
        yrs = len(D.dates[D.tag(nm)]) / 365.0
        vals = {"assumed": float(D.net(nm).sum() / yrs * 100)}
        for k in ("cost_1k_median_bps", "cost_1k_p75_bps", "cost_10k_median_bps", "cost_10k_p75_bps"):
            vals[k] = float(D.net(nm, hs=bc[k]).sum() / yrs * 100)
        out[nm] = vals
        parts = nm.split("_")
        print(f"| {' '.join(parts[:-1])} | {parts[-1]} | {fmt(vals['assumed'])} | {fmt(vals['cost_1k_median_bps'])} | {fmt(vals['cost_1k_p75_bps'])} | "
              f"{fmt(vals['cost_10k_median_bps'])} | {fmt(vals['cost_10k_p75_bps'])} |")
    return out



def table_speed(D):
    """The owner's prior P1: on time against one bar late, hourly against 5-minute bars."""
    out = {}
    print("\n## Speed (prior P1): the same rule filled on time and one bar late; % per year on committed gross notional")
    print("| configuration | gross on time | gross late | net on time | net late | net lost by one bar of delay | Sharpe net on time | Sharpe net late |")
    print("|---|---|---|---|---|---|---|---|")
    for nm in sorted(D.series):
        if not nm.endswith("_ontime"):
            continue
        late = nm[:-7] + "_late"
        n = len(D.dates[D.tag(nm)])
        yrs = n / 365.0
        go, gl = D.series[nm]["gross"].sum() / yrs * 100, D.series[late]["gross"].sum() / yrs * 100
        no, nl = D.net(nm).sum() / yrs * 100, D.net(late).sum() / yrs * 100
        d = D.net(nm) - D.net(late)
        idx = D.boot_idx(n) if n < 500 else None
        out[nm[:-7]] = {"gross_ontime": float(go), "gross_late": float(gl), "net_ontime": float(no), "net_late": float(nl),
                        "sharpe_ontime": sharpe(D.net(nm)), "sharpe_late": sharpe(D.net(late)), "diff_ann_pct": float(d.sum() / yrs * 100)}
        print(f"| {nm[:-7]} | {fmt(go)} | {fmt(gl)} | {fmt(no)} | {fmt(nl)} | {fmt(no - nl)} | {fmt(sharpe(D.net(nm)), 2)} | {fmt(sharpe(D.net(late)), 2)} |")
    return out


TABLES = {"configs": table_configs, "years": table_years, "split": table_split, "maxstat": table_maxstat, "pairs": table_pairs,
          "hindsight": table_hindsight, "trades": table_trades, "bh": table_bh, "shock": table_shock, "speed": table_speed,
          "size": table_size}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", choices=sorted(TABLES), default=None)
    args = ap.parse_args()
    D = Data()
    summary = {}
    for name, fn in TABLES.items():
        if args.table and name != args.table:
            continue
        D.rng = np.random.default_rng(C.SEED + 50 + sorted(TABLES).index(name))
        summary[name] = fn(D)
    if not args.table:
        with open(os.path.join(P2, "summary.json"), "w") as f:
            json.dump(summary, f, indent=1, sort_keys=True, default=C._jsonable)
            f.write("\n")
        print(f"\nwrote {os.path.join(P2, 'summary.json')}")


if __name__ == "__main__":
    sys.exit(main())
