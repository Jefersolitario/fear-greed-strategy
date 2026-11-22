"""Stage 1: endpoint probe, Bitcoin shock events (Bitcoin data only), hourly panel, point-in-time universes.

Outputs (committed): out/s1/*.  The hourly panel itself goes to the cache directory, not to git.
Run: python s1_data.py            (in the workflow)
     BTCALTS_TEST=1 python s1_data.py   (synthetic market, no network)
"""
from __future__ import annotations

import csv
import gzip
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import common as C
from common import DAY, HOUR, MIN, SEC

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out_test" if os.environ.get("BTCALTS_TEST") == "1" else "out", "s1")
CACHE = os.environ.get("BTCALTS_CACHE", os.path.join(HERE, "cache_test" if os.environ.get("BTCALTS_TEST") == "1" else "cache"))
TWO_H = 2 * HOUR


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def write_csv(path, header, rows, gz=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    opener = (lambda p: gzip.open(p, "wt", newline="")) if gz else (lambda p: open(p, "w", newline=""))
    with opener(path) as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ---- 1. probe ---------------------------------------------------------------------------------------------
def probe(client, cfg) -> dict:
    res = {}
    if cfg.test:
        return {"test": True}
    try:
        t = client.get("/api/v3/time", weight=1)
        res["time"] = {"ok": True, "serverTime": t.get("serverTime")}
    except Exception as e:  # noqa: BLE001
        res["time"] = {"ok": False, "error": repr(e)}
    for name, sym, t0 in (("klines_1s_btc_2023", "BTCUSDT", C.ms(2023, 1, 3)),
                          ("klines_1s_ach_2023", "ACHUSDT", C.ms(2023, 1, 3)),
                          ("klines_1s_btc_2026", "BTCUSDT", C.ms(2026, 11, 1))):
        try:
            rows = client.klines(sym, "1s", t0, t0 + 999 * SEC)
            k = C.klines_to_arrays(rows or [])
            res[name] = {"ok": rows is not None, "rows": len(rows or []),
                         "zero_volume_rows": int((k["quote_volume"] == 0).sum()),
                         "first_open_time": int(k["open_time"][0]) if len(rows or []) else None,
                         "sample": (rows or [None])[0]}
        except Exception as e:  # noqa: BLE001
            res[name] = {"ok": False, "error": repr(e)}
    for name, path in (("bulk_spot_klines", "/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip"),
                       ("bulk_funding", "/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2023-01.zip"),
                       ("bulk_futures_klines", "/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2023-01.zip")):
        try:
            blob = client.bulk(path)
            info = {"ok": blob is not None, "bytes": len(blob) if blob else 0}
            if blob:
                info["head"] = C.unzip_single_csv(blob)[:300]
            res[name] = info
        except Exception as e:  # noqa: BLE001
            res[name] = {"ok": False, "error": repr(e)}
    return res


# ---- 2. symbols -------------------------------------------------------------------------------------------
def usdt_symbols(client):
    info = client.exchange_info()
    limits = info.get("rateLimits", [])
    syms = [s for s in info["symbols"] if s.get("quoteAsset") == "USDT"]
    bases = {s["baseAsset"] for s in syms}
    table = []
    for s in sorted(syms, key=lambda x: x["symbol"]):
        table.append({"symbol": s["symbol"], "base": s["baseAsset"], "status": s.get("status", ""),
                      "excluded": C.exclusion_reason(s["baseAsset"], bases)})
    return table, limits, len(info["symbols"])


# ---- 3. Bitcoin events ------------------------------------------------------------------------------------
def btc_minutes(client, cfg):
    start = cfg.p1_start - MIN
    n_m = (cfg.end - start) // MIN
    hi = np.full(n_m, np.nan)
    lo = np.full(n_m, np.nan)
    cl = np.full(n_m, np.nan)

    def one(k0):
        a = start + k0 * MIN
        b = start + (min(k0 + 1000, n_m) - 1) * MIN
        k = C.klines_to_arrays(client.klines("BTCUSDT", "1m", a, b) or [])
        idx = ((k["open_time"] - start) // MIN).astype(np.int64)
        ok = (idx >= 0) & (idx < n_m)
        hi[idx[ok]] = k["high"][ok]
        lo[idx[ok]] = k["low"][ok]
        cl[idx[ok]] = k["close"][ok]

    with ThreadPoolExecutor(cfg.workers) as ex:
        list(ex.map(one, range(0, n_m, 1000)))
    return start, hi, lo, cl


def btc_triggers(client, cfg, start, hi, lo):
    """All seconds with |rolling 60 s return| >= the smallest theta, inside the screened minutes."""
    th = cfg.theta_grid[0]
    with np.errstate(invalid="ignore"):
        cand = np.zeros(len(hi), bool)
        cand[1:] = (lo[1:] <= (1 - th) * hi[:-1]) | (hi[1:] >= (1 + th) * lo[:-1])
    idx = np.flatnonzero(cand)
    runs = []
    if len(idx):
        brk = np.flatnonzero(np.diff(idx) > 1)
        starts = np.concatenate([[idx[0]], idx[brk + 1]])
        ends = np.concatenate([idx[brk], [idx[-1]]])
        runs = list(zip(starts.tolist(), ends.tolist()))
    log(f"  candidate minutes: {len(idx)} in {len(runs)} runs (theta_min {th:.4f})")

    def one(run):
        ma, mb = run
        t0 = start + ma * MIN - 60 * SEC
        n = (mb - ma + 1) * 60 + 60
        w = C.fetch_1s_window(client, "BTCUSDT", t0, n)
        c = w["close"]
        r = c[60:] / c[:-60] - 1.0
        ts = t0 + (np.arange(n)[60:]) * SEC
        keep = np.abs(r) >= th
        return ts[keep], r[keep], c[:-60][keep], c[60:][keep]

    with ThreadPoolExecutor(cfg.workers) as ex:
        parts = list(ex.map(one, runs))
    if not parts:
        z = np.zeros(0)
        return z.astype(np.int64), z, z, z, len(idx)
    ts = np.concatenate([p[0] for p in parts])
    o = np.argsort(ts, kind="stable")
    return (ts[o], np.concatenate([p[1] for p in parts])[o], np.concatenate([p[2] for p in parts])[o],
            np.concatenate([p[3] for p in parts])[o], len(idx))


def first_of_clusters(ts: np.ndarray, gap: int = TWO_H) -> np.ndarray:
    """Indices of triggers with no earlier trigger within `gap` (sorted ts)."""
    if len(ts) == 0:
        return np.zeros(0, np.int64)
    return np.flatnonzero(np.concatenate([[True], np.diff(ts) >= gap]))


def choose_theta(counts: dict[float, int]) -> float:
    inside = [th for th, n in counts.items() if 50 <= n <= 150]
    pool = inside if inside else list(counts)
    return max(pool, key=lambda th: (-abs(counts[th] - 100), th))


# ---- main -------------------------------------------------------------------------------------------------
def main():
    cfg = C.load_config()
    client = C.make_client(cfg)
    os.makedirs(OUT, exist_ok=True)
    log("config", cfg)

    log("1. probe")
    pr = probe(client, cfg)
    C.write_json(os.path.join(OUT, "probe.json"), pr)
    for k, v in pr.items():
        log("  ", k, {kk: vv for kk, vv in v.items() if kk not in ("sample", "head")} if isinstance(v, dict) else v)

    log("2. symbols")
    table, limits, n_all = usdt_symbols(client)
    for lim in limits:
        if lim.get("rateLimitType") == "REQUEST_WEIGHT" and lim.get("interval") == "MINUTE" and not cfg.test:
            client.published_limit = int(lim["limit"]) // int(lim.get("intervalNum", 1))
            budget = min(cfg.weight_budget_per_min, client.published_limit // 2)
            client.pacer = C.Pacer(budget)
            log(f"  published limit {client.published_limit} weight/min, pacing at {budget}")
    keep = [r["symbol"] for r in table if not r["excluded"]]
    by_status = {}
    for r in table:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    log(f"  {n_all} symbols in exchangeInfo, {len(table)} quoted in USDT {by_status}, {len(keep)} kept by name")

    log("3. Bitcoin events")
    start, hi, lo, cl = btc_minutes(client, cfg)
    log(f"  1m bars: {int((~np.isnan(cl)).sum())} of {len(cl)}")
    ts, r60, ref, px, n_cand = btc_triggers(client, cfg, start, hi, lo)
    inp = (ts >= cfg.p1_start + 60 * SEC) & (ts < cfg.end - cfg.post_s * SEC - SEC)
    ts, r60, ref, px = ts[inp], r60[inp], ref[inp], px[inp]
    write_csv(os.path.join(OUT, "btc_triggers.csv.gz"), ["s_star_ms", "r60", "ref_price", "price"],
              [(int(a), f"{b:.6f}", f"{c:.2f}", f"{d:.2f}") for a, b, c, d in zip(ts, r60, ref, px)], gz=True)
    grid_rows, counts = [], {}
    events_by = {}
    for th in cfg.theta_grid:
        for kind, mask in (("down", r60 <= -th), ("up", r60 >= th)):
            t_k = ts[mask]
            first = first_of_clusters(t_k)
            ev_idx = np.flatnonzero(mask)[first]
            events_by[(th, kind)] = ev_idx
            years = {}
            for t in ts[ev_idx]:
                y = C.iso(t)[:4]
                years[y] = years.get(y, 0) + 1
            grid_rows.append([f"{th:.4f}", kind, int(mask.sum()), len(ev_idx),
                              " ".join(f"{y}:{n}" for y, n in sorted(years.items()))])
            if kind == "down":
                counts[th] = len(ev_idx)
    theta = choose_theta(counts)
    write_csv(os.path.join(OUT, "btc_event_grid.csv"), ["theta", "kind", "trigger_seconds", "events", "by_year"], grid_rows)
    for row in grid_rows:
        log("  ", row)
    log(f"  chosen theta = {theta:.4f} ({counts[theta]} down events)")

    events = []
    for kind, tag in (("down", "D"), ("up", "U")):
        for n, i in enumerate(events_by[(theta, kind)]):
            events.append({"event_id": f"{tag}{n + 1:04d}", "kind": kind, "s_star_ms": int(ts[i]), "r60": float(r60[i]),
                           "btc_ref": float(ref[i]), "btc_px": float(px[i])})
    rng = np.random.default_rng(C.SEED + 1)
    rnd, lo_t, hi_t = [], cfg.p1_start + TWO_H, cfg.end - cfg.post_s * SEC - TWO_H
    tries = 0
    while len(rnd) < cfg.n_random and tries < 100000:
        tries += 1
        t = int(rng.integers(lo_t // SEC, hi_t // SEC)) * SEC
        j = np.searchsorted(ts, t)
        near = (j < len(ts) and ts[j] - t < TWO_H) or (j > 0 and t - ts[j - 1] < TWO_H)
        if near or any(abs(t - u) < TWO_H for u in rnd):
            continue
        rnd.append(t)
    for n, t in enumerate(sorted(rnd)):
        events.append({"event_id": f"R{n + 1:04d}", "kind": "random", "s_star_ms": int(t), "r60": float("nan"),
                       "btc_ref": float("nan"), "btc_px": float("nan")})
    log(f"  events: {sum(e['kind'] == 'down' for e in events)} down, {sum(e['kind'] == 'up' for e in events)} up, "
        f"{len(rnd)} random")

    log("4. hourly panel")
    panel_path = os.path.join(CACHE, "hourly_panel.npz")
    panel = None
    if os.path.exists(panel_path):
        panel = C.load_panel(panel_path)
        want_h = (cfg.end - cfg.hourly_start) // HOUR
        if panel["start_ms"] != cfg.hourly_start or panel["n_hours"] != want_h or set(panel["symbols"]) != set(keep):
            log("  cached panel does not match this run, downloading again")
            panel = None
        else:
            log("  using cached panel")
    if panel is None:
        panel = C.build_hourly_panel(client, keep, cfg.hourly_start, cfg.end, cfg.workers, log)
        C.save_panel(panel, panel_path)
    digest = C.panel_digest(panel)
    log(f"  panel {panel['close'].shape}, sha256 {digest[:16]}, gap bars filled {panel.get('filled', 'n/a')}")
    first_bar, last_bar, n_bars = {}, {}, {}
    for j, s in enumerate(panel["symbols"]):
        have = np.flatnonzero(~np.isnan(panel["close"][:, j]))
        n_bars[s] = len(have)
        first_bar[s] = C.iso(panel["start_ms"] + have[0] * HOUR) if len(have) else ""
        last_bar[s] = C.iso(panel["start_ms"] + have[-1] * HOUR) if len(have) else ""
    write_csv(os.path.join(OUT, "symbols.csv"), ["symbol", "base", "status", "excluded", "hourly_bars", "first_bar", "last_bar"],
              [[r["symbol"], r["base"], r["status"], r["excluded"], n_bars.get(r["symbol"], ""),
                first_bar.get(r["symbol"], ""), last_bar.get(r["symbol"], "")] for r in table])

    log("5. point-in-time universes")
    dyn = {}
    ev_rows = []
    for e in events:
        d0 = (e["s_star_ms"] // DAY) * DAY
        ranks = C.rank_at(panel, d0, dyn)[:cfg.top_n]
        syms = [r["symbol"] for r in ranks]
        betas = C.beta_at(panel, syms, e["s_star_ms"] - 60 * SEC)
        e["n_universe"] = len(ranks)
        for r in ranks:
            ev_rows.append([e["event_id"], r["symbol"], r["rank"], C.tier_of_rank(r["rank"]), f"{r['qv30']:.0f}",
                            f"{betas[r['symbol']]:.4f}", f"{r['sd_hourly']:.6f}"])
    write_csv(os.path.join(OUT, "event_universe.csv.gz"), ["event_id", "symbol", "rank", "tier", "qv30", "beta", "sd_hourly"],
              ev_rows, gz=True)
    write_csv(os.path.join(OUT, "events.csv"), ["event_id", "kind", "s_star_ms", "utc", "r60", "btc_ref", "btc_px", "n_universe"],
              [[e["event_id"], e["kind"], e["s_star_ms"], C.iso(e["s_star_ms"]), f"{e['r60']:.6f}", f"{e['btc_ref']:.2f}",
                f"{e['btc_px']:.2f}", e["n_universe"]] for e in events])
    f_rows = []
    n_win = (cfg.end - cfg.first_T) // (cfg.trading_days * DAY)
    form_h = cfg.formation_days * 24
    col = {s: j for j, s in enumerate(panel["symbols"])}
    for k in range(int(n_win)):
        T = cfg.first_T + k * cfg.trading_days * DAY
        i1 = (T - panel["start_ms"]) // HOUR
        for r in C.rank_at(panel, T, dyn)[:cfg.top_n]:
            complete = not np.isnan(panel["close"][i1 - form_h:i1, col[r["symbol"]]]).any()
            f_rows.append([k, C.iso(T)[:10], r["symbol"], r["rank"], f"{r['qv30']:.0f}", int(complete)])
    write_csv(os.path.join(OUT, "formation_universe.csv.gz"), ["window", "T", "symbol", "rank", "qv30", "complete_formation"],
              f_rows, gz=True)
    log(f"  {len(ev_rows)} event-coin rows, {len(f_rows)} formation rows over {int(n_win)} windows; "
        f"dynamic peg exclusions: {sorted(dyn)}")

    log("6. current quoted spreads (one snapshot)")
    spread_summary = {}
    try:
        bt = client.book_ticker() or []
        now_rank = {r["symbol"]: r["rank"] for r in C.rank_at(panel, cfg.end, None)}
        rows = []
        for b in bt:
            s = b["symbol"]
            if s not in now_rank:
                continue
            bid, ask = float(b["bidPrice"]), float(b["askPrice"])
            if bid <= 0 or ask <= 0:
                continue
            rows.append([s, now_rank[s], C.tier_of_rank(now_rank[s]) if now_rank[s] <= 100 else 4, b["bidPrice"], b["askPrice"],
                         f"{(ask - bid) / ((ask + bid) / 2) * 1e4:.3f}"])
        rows.sort(key=lambda r: r[1])
        write_csv(os.path.join(OUT, "spread_snapshot.csv"), ["symbol", "rank", "tier", "bid", "ask", "spread_bps"], rows)
        for t in (1, 2, 3):
            v = [float(r[5]) for r in rows if r[2] == t]
            if v:
                spread_summary[f"tier{t}"] = {"n": len(v), "median_full_spread_bps": float(np.median(v)),
                                              "mean_full_spread_bps": float(np.mean(v))}
        log("  ", spread_summary)
    except Exception as e:  # noqa: BLE001
        spread_summary = {"error": repr(e)}
        log("  bookTicker failed:", repr(e))

    C.write_json(os.path.join(OUT, "manifest.json"), {
        "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in vars(cfg).items()},
        "end_utc": C.iso(cfg.end), "theta": theta, "event_counts": {str(k): v for k, v in counts.items()},
        "n_events": {k: sum(e["kind"] == k for e in events) for k in ("down", "up", "random")},
        "candidate_minutes": n_cand, "symbols_in_exchange_info": n_all, "usdt_symbols": len(table),
        "usdt_by_status": by_status, "kept_by_name": len(keep), "rate_limits": limits,
        "panel_sha256": digest, "panel_shape": list(panel["close"].shape), "dynamic_peg_exclusions": sorted(dyn),
        "spread_snapshot": spread_summary, "meta": C.run_meta(client)})
    log("done", client.stats)


if __name__ == "__main__":
    sys.exit(main())
