"""Stage 2 (Part 1): 1-second windows around the Bitcoin events for the point-in-time top 100, reduced to
compact tables. Raw 1-second data stays in the cache directory and is never committed.

Inputs : out/s1/events.csv, out/s1/event_universe.csv.gz   (from s1_data.py)
Outputs: out/p1/event_coin.parquet   one row per event and coin (event study, staleness, trade legs)
         out/p1/paths.parquet        mean cumulative return path per event and tier
         out/p1/xcorr_symbol.parquet lagged betas per symbol, averaged over the windows of each kind
         out/p1/xcorr_tier.parquet   mean cross-correlation and lagged beta, lags -60..60, per window and tier
         out/p1/fresh_stats.csv.gz   sufficient statistics of the fresh-price regressions
         out/p1/manifest.json
Run: python p1_extract.py     |     BTCALTS_TEST=1 python p1_extract.py
"""
from __future__ import annotations

import csv
import gzip
import os
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import polars as pl

import common as C
from common import SEC

TEST = os.environ.get("BTCALTS_TEST") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "out_test" if TEST else "out")
OUT = os.path.join(OUT_ROOT, "p1")
CACHE = os.environ.get("BTCALTS_CACHE", os.path.join(HERE, "cache_test" if TEST else "cache"))
BUDGET_MIN = float(os.environ.get("BTCALTS_BUDGET_MIN", "270"))

LAGS = (-30, -10, -5, -2, -1, 0, 1, 2, 5, 15, 60, 300, 900, 3600)
AGE_LAGS = (0, 1, 2, 5, 15, 60)
DELAYS = (0, 1, 2, 5, 60)     # 0 s is the reference for an actor faster than the owner
HORIZONS = (30, 300, 1800)
GRID = list(range(-60, 61)) + list(range(65, 301, 5)) + list(range(330, 3601, 30))
XC_FINE = list(range(-5, 11))
FRESH_G = (1, 2, 3, 5, 10)
FRESH_H = (5, 60)
BIG_X = 5.0      # bps: a "large" one-second Bitcoin move for the fresh-price regressions


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def lag_name(tau: int) -> str:
    return f"cr_m{-tau}" if tau < 0 else f"cr_{tau}"


# ---- download ---------------------------------------------------------------------------------------------
def download_event(client, cfg, ev, symbols, workers):
    """Raw 1-second arrays [n_coins, N] for one event. Coins that fail are dropped and counted."""
    n = cfg.pre_s + cfg.post_s + 1
    t0 = ev["s_star_ms"] - cfg.pre_s * SEC

    def one(sym):
        try:
            return C.fetch_1s_window(client, sym, t0, n)
        except C.Refused:
            raise
        except Exception as e:  # noqa: BLE001  (a coin that fails is skipped, the run goes on)
            return repr(e)

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, symbols))
    keep, failed = [], []
    for s, w in zip(symbols, res):
        if isinstance(w, dict) and w["n_bars"] > 0:
            keep.append((s, w))
        else:
            failed.append(s)
    if not keep:
        return None, failed
    raw = {"symbols": np.array([s for s, _ in keep])}
    close = np.stack([w["close"] for _, w in keep])
    qv = np.stack([w["quote_volume"] for _, w in keep])
    bv = np.stack([w["volume"] for _, w in keep])
    tbq = np.stack([w["taker_buy_quote"] for _, w in keep])
    tbb = np.stack([w["taker_buy_base"] for _, w in keep])
    sq, sb = qv - tbq, bv - tbb
    sq[sb <= 1e-12 * np.maximum(bv, 1e-300)] = 0.0
    sb[sb <= 1e-12 * np.maximum(bv, 1e-300)] = 0.0
    raw["close"] = close.astype(np.float32)
    raw["bq"], raw["bb"] = tbq.astype(np.float32), tbb.astype(np.float32)
    raw["sq"], raw["sb"] = sq.astype(np.float32), sb.astype(np.float32)
    raw["n"] = np.minimum(np.stack([w["n_trades"] for _, w in keep]), 65535).astype(np.uint16)
    return raw, failed


# ---- features ---------------------------------------------------------------------------------------------
def next_index(cond: np.ndarray) -> np.ndarray:
    """For each row and position k: the smallest index >= k where cond is True (N if none)."""
    n = cond.shape[1]
    idx = np.where(cond, np.arange(n)[None, :], n)
    return np.minimum.accumulate(idx[:, ::-1], axis=1)[:, ::-1]


def take(a: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """a[i, idx[i]] with NaN where idx is out of range."""
    n = a.shape[1]
    ok = (idx >= 0) & (idx < n)
    out = np.full(a.shape[0], np.nan)
    rows = np.flatnonzero(ok)
    out[rows] = a[rows, idx[rows]]
    return out


def features(cfg, ev, uni, raw):
    """All per-event statistics. `uni` maps symbol -> (rank, tier, beta, qv30)."""
    warnings.simplefilter("ignore", RuntimeWarning)
    syms = [str(s) for s in raw["symbols"]]
    if "BTCUSDT" not in syms:
        return None
    ib = syms.index("BTCUSDT")
    nc, N = raw["close"].shape
    ks, kref = cfg.pre_s, cfg.pre_s - 60
    close = raw["close"].astype(np.float64)
    bq, bb = raw["bq"].astype(np.float64), raw["bb"].astype(np.float64)
    sq, sb = raw["sq"].astype(np.float64), raw["sb"].astype(np.float64)
    ntr = raw["n"].astype(np.int64)
    qv, bv = bq + sq, bb + sb
    traded = (ntr > 0) & (bv > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        vwap = np.where(bv > 0, qv / bv, np.nan)
        buy = np.where(bb > 0, bq / bb, np.nan)
        sell = np.where(sb > 0, sq / sb, np.nan)
        lc = np.log(close)
    cr_all = (lc - lc[:, [kref]]) * 1e4                       # cumulative log return from t* - 60 s, bps
    rank = np.array([uni[s][0] for s in syms])
    tier = np.array([uni[s][1] for s in syms])
    beta = np.array([uni[s][2] for s in syms])
    qv30 = np.array([uni[s][3] for s in syms])
    is_btc = np.arange(nc) == ib

    cols = {"event_id": [ev["event_id"]] * nc, "kind": [ev["kind"]] * nc, "symbol": syms,
            "rank": rank.astype(np.int32), "tier": tier.astype(np.int32), "beta": beta, "qv30": qv30,
            "share_sec_traded": traded.mean(axis=1), "n_trades_pre60": ntr[:, kref + 1:ks + 1].sum(axis=1),
            "qv_pre60": qv[:, kref + 1:ks + 1].sum(axis=1), "n_trades_post60": ntr[:, ks + 1:ks + 61].sum(axis=1),
            "qv_post60": qv[:, ks + 1:ks + 61].sum(axis=1), "qv_post5": qv[:, ks + 1:ks + 6].sum(axis=1)}
    for tau in LAGS:
        cols[lag_name(tau)] = cr_all[:, ks + tau]
    # staleness: seconds since the last traded second, at each lag
    last = np.where(traded, np.arange(N)[None, :], -1)
    last = np.maximum.accumulate(last, axis=1)
    for tau in AGE_LAGS:
        la = last[:, ks + tau]
        cols[f"age_{tau}"] = np.where(la >= 0, ks + tau - la, np.nan)
    nxt = next_index(traded)
    nxt_buy = next_index(bb > 0)
    nxt_sell = next_index(sb > 0)
    f = nxt[:, ks + 1]
    cols["fresh_delay"] = np.where(f < N, f - ks, np.nan)
    cols["fresh_cr"] = (np.log(take(vwap, f)) - lc[:, kref]) * 1e4
    # time at which half of the move to +60 s / +3600 s is done (seconds relative to the trigger)
    for name, kt in (("thalf60", ks + 60), ("thalf3600", ks + 3600)):
        target = cr_all[:, kt]
        frac = cr_all[:, kref:kt + 1] / target[:, None]
        hit = frac >= 0.5
        first = np.where(hit.any(axis=1), hit.argmax(axis=1) + kref - ks, np.nan).astype(np.float64)
        first[~(np.abs(target) >= 10.0)] = np.nan
        cols[name] = first
    # effective spread proxy: taker-buy VWAP minus taker-sell VWAP in seconds that have both
    es = np.where((bb > 0) & (sb > 0), (buy - sell) / ((buy + sell) / 2) * 1e4, np.nan)
    for name, a, b in (("pre", 0, kref), ("shock", kref, ks + 60), ("post", ks + 60, N)):
        cols[f"es_{name}"] = np.nanmedian(es[:, a:b], axis=1)
        cols[f"n2_{name}"] = (~np.isnan(es[:, a:b])).sum(axis=1)

    # trade legs (events only)
    btc_vwap = np.where(np.isnan(vwap[ib]), close[ib], vwap[ib])
    btc_buy = np.where(np.isnan(buy[ib]), btc_vwap, buy[ib])
    btc_sell = np.where(np.isnan(sell[ib]), btc_vwap, sell[ib])
    do_trades = ev["kind"] in ("down", "up")
    for d in DELAYS:
        k0 = ks + d + 1
        e = nxt[:, k0].copy()
        e[e > ks + d + 60] = N
        cols[f"edelay_{d}"] = np.where(e < N, e - (ks + d), np.nan) if do_trades else np.full(nc, np.nan)
        cols[f"qv5_{d}"] = qv[:, k0:k0 + 5].sum(axis=1) if do_trades else np.full(nc, np.nan)
        if ev["kind"] == "down":      # short: sell at taker-sell VWAP, buy back at taker-buy VWAP
            ee = nxt_sell[:, k0].copy()
        else:                          # long (mirror): buy at taker-buy VWAP, sell at taker-sell VWAP
            ee = nxt_buy[:, k0].copy()
        ee[ee > ks + d + 60] = N
        cols[f"xdelay_{d}"] = np.where(ee < N, ee - (ks + d), np.nan) if do_trades else np.full(nc, np.nan)
        for H in HORIZONS:
            if not do_trades:
                for nm in ("r_vwap", "rb_vwap", "r_exec", "rb_exec"):
                    cols[f"{nm}_{d}_{H}"] = np.full(nc, np.nan)
                continue
            ok = e < N
            x = np.where(ok, nxt[np.arange(nc), np.minimum(e + H, N - 1)], N)
            p_e = take(vwap, np.where(ok, e, -1))
            p_x = np.where(x < N, take(vwap, x), close[:, N - 1])
            cols[f"r_vwap_{d}_{H}"] = np.where(ok, np.log(p_x / p_e) * 1e4, np.nan)
            xb = np.minimum(x, N - 1)
            cols[f"rb_vwap_{d}_{H}"] = np.where(ok, np.log(btc_vwap[xb] / btc_vwap[np.minimum(e, N - 1)]) * 1e4, np.nan)
            ok2 = ee < N
            if ev["kind"] == "down":
                x2 = np.where(ok2, nxt_buy[np.arange(nc), np.minimum(ee + H, N - 1)], N)
                p_e2 = take(sell, np.where(ok2, ee, -1))
                p_x2 = np.where(x2 < N, take(buy, x2), np.nan)
                hb = np.log(btc_sell[np.minimum(x2, N - 1)] / btc_buy[np.minimum(ee, N - 1)]) * 1e4
            else:
                x2 = np.where(ok2, nxt_sell[np.arange(nc), np.minimum(ee + H, N - 1)], N)
                p_e2 = take(buy, np.where(ok2, ee, -1))
                p_x2 = np.where(x2 < N, take(sell, x2), np.nan)
                hb = np.log(btc_buy[np.minimum(x2, N - 1)] / btc_sell[np.minimum(ee, N - 1)]) * 1e4
            good = ok2 & (x2 < N)
            cols[f"r_exec_{d}_{H}"] = np.where(good, np.log(p_x2 / p_e2) * 1e4, np.nan)
            cols[f"rb_exec_{d}_{H}"] = np.where(good, hb, np.nan)

    # mean path per tier group
    groups = {"BTC": is_btc, "T1": (tier == 1) & ~is_btc, "T2": tier == 2, "T3": tier == 3}
    gi = np.array(GRID) + ks
    paths = []
    for g, m in groups.items():
        if m.any():
            paths.append((ev["event_id"], ev["kind"], g, int(m.sum()), np.nanmean(cr_all[np.ix_(m, gi)], axis=0)))

    # 1-second lead-lag: coin return at t+L against Bitcoin return at t
    r = np.diff(lc, axis=1)
    r[np.isnan(r)] = 0.0
    r = r - r.mean(axis=1, keepdims=True)
    rb = r[ib]
    M = r.shape[1]
    a0, a1 = 60, M - 60
    sbb = (rb[a0:a1] ** 2).sum()
    num = np.stack([(r[:, a0 + L:a1 + L] * rb[None, a0:a1]).sum(axis=1) for L in range(-60, 61)], axis=1)
    saa = (r[:, a0:a1] ** 2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        lbeta = num / sbb
        corr = num / np.sqrt(saa[:, None] * sbb)
        z0, z1 = ks - 60, ks + 60             # shock zone: Bitcoin returns of the two minutes around the trigger
        sbz = (rb[z0:z1] ** 2).sum()
        zb = np.stack([(r[:, z0 + L:z1 + L] * rb[None, z0:z1]).sum(axis=1) / sbz for L in XC_FINE], axis=1)
    xc = {"event_id": [ev["event_id"]] * nc, "kind": [ev["kind"]] * nc, "symbol": syms, "tier": tier.astype(np.int32),
          "rank": rank.astype(np.int32), "corr0": corr[:, 60], "sd_1s_bps": np.sqrt(saa / (a1 - a0)) * 1e4,
          "share_sec_traded": traded.mean(axis=1), "lb_m60_m31": lbeta[:, 0:30].sum(axis=1),
          "lb_m30_m6": lbeta[:, 30:55].sum(axis=1), "lb_11_30": lbeta[:, 71:91].sum(axis=1),
          "lb_31_60": lbeta[:, 91:121].sum(axis=1)}
    for i, L in enumerate(XC_FINE):
        xc[f"lb_{L}" if L >= 0 else f"lb_m{-L}"] = lbeta[:, 60 + L]
        xc[f"zb_{L}" if L >= 0 else f"zb_m{-L}"] = zb[:, i]
    xt = []
    for g, m in groups.items():
        if g != "BTC" and m.any():
            xt.append((ev["event_id"], ev["kind"], g, int(m.sum()), np.nanmean(corr[m], axis=0), np.nanmean(lbeta[m], axis=0),
                       np.nanmean(zb[m], axis=0)))

    # fresh-price regressions: coin return from the VWAP of a traded second to the close h seconds later,
    # on Bitcoin's return in the single second g seconds before
    rb_bps = np.concatenate([[0.0], np.diff(lc[ib])]) * 1e4      # rb_bps[k]: Bitcoin log return in second k
    lv = np.log(vwap)
    t0, t1 = 70, N - 61
    fresh = []
    for g_ in FRESH_G:
        x = rb_bps[t0 - g_:t1 - g_]
        for h in FRESH_H:
            y = (lc[:, t0 + h:t1 + h] - lv[:, t0:t1]) * 1e4
            ok = traded[:, t0:t1] & ~np.isnan(y)
            for sub, mask in (("all", ok), ("big", ok & (np.abs(x)[None, :] >= BIG_X))):
                xx = np.where(mask, x[None, :], 0.0)
                yy = np.where(mask, y, 0.0)
                for gname in ("BTC", "T1", "T2", "T3"):       # BTC on itself: its own continuation, the benchmark
                    m = groups[gname]
                    if not m.any():
                        continue
                    fresh.append((ev["event_id"], ev["kind"], gname, g_, h, sub, int(mask[m].sum()), xx[m].sum(),
                                  yy[m].sum(), (xx[m] ** 2).sum(), (xx[m] * yy[m]).sum(), (yy[m] ** 2).sum()))
    return cols, paths, xc, xt, fresh


# ---- main -------------------------------------------------------------------------------------------------
def read_inputs():
    s1 = os.path.join(OUT_ROOT, "s1")
    events = []
    with open(os.path.join(s1, "events.csv")) as f:
        for r in csv.DictReader(f):
            events.append({"event_id": r["event_id"], "kind": r["kind"], "s_star_ms": int(r["s_star_ms"])})
    uni = {}
    with gzip.open(os.path.join(s1, "event_universe.csv.gz"), "rt") as f:
        for r in csv.DictReader(f):
            uni.setdefault(r["event_id"], {})[r["symbol"]] = (int(r["rank"]), int(r["tier"]), float(r["beta"]), float(r["qv30"]))
    return events, uni


def rounded(a, nd=2):
    return np.round(np.asarray(a, dtype=np.float64), nd).astype(np.float32)


def main():
    cfg = C.load_config()
    client = C.make_client(cfg)
    events, uni = read_inputs()
    os.makedirs(OUT, exist_ok=True)
    raw_dir = os.path.join(CACHE, "raw1s")
    os.makedirs(raw_dir, exist_ok=True)
    order = np.random.default_rng(C.SEED + 2).permutation(len(events))
    t_start = time.time()
    workers = 4 if cfg.test else 12
    tables, paths, xcs, xts, fresh = [], [], [], [], []
    done, skipped, failed_coins, refused = 0, [], {}, None
    for n_done, i in enumerate(order):
        ev = events[i]
        path = os.path.join(raw_dir, ev["event_id"] + ".npz")
        raw = None
        if os.path.exists(path):
            z = np.load(path, allow_pickle=False)
            raw = {k: z[k] for k in z.files}
        elif refused is None and (time.time() - t_start) / 60 < BUDGET_MIN:
            syms = sorted(set(uni[ev["event_id"]]) | {"BTCUSDT"})
            try:
                raw, failed = download_event(client, cfg, ev, syms, workers)
            except C.Refused as e:
                refused = repr(e)
                log("REFUSED, stopping downloads:", refused)
                raw = None
            else:
                if failed:
                    failed_coins[ev["event_id"]] = failed
                if raw is not None:
                    np.savez_compressed(path, **raw)
        if raw is None:
            skipped.append(ev["event_id"])
            continue
        u = dict(uni[ev["event_id"]])
        u.setdefault("BTCUSDT", (1, 1, 1.0, float("nan")))
        out = features(cfg, ev, u, raw)
        if out is None:
            skipped.append(ev["event_id"])
            continue
        tables.append(out[0]); paths.extend(out[1]); xcs.append(out[2]); xts.extend(out[3]); fresh.extend(out[4])
        done += 1
        if done % 10 == 0 or done == 1:
            st = getattr(client, "stats", {})
            log(f"events {done}/{len(events)} ({n_done + 1} visited), {(time.time() - t_start) / 60:.1f} min, "
                f"calls {st.get('calls')}, max used weight {st.get('max_used_weight_1m')}")

    if not tables:
        log("no events processed")
        C.write_json(os.path.join(OUT, "manifest.json"), {"events_done": 0, "refused": refused, "meta": C.run_meta(client)})
        return 1

    # ---- assemble compact tables (bps columns rounded to 0.1 bp, which is far below any effect of interest) ----
    def cat(dicts, k):
        v0 = dicts[0][k]
        if isinstance(v0, list):
            return [x for d in dicts for x in d[k]]
        return np.concatenate([np.asarray(d[k]) for d in dicts])

    ec = {}
    for k in tables[0]:
        v = cat(tables, k)
        if isinstance(v, list) or v.dtype.kind in "iu":
            ec[k] = v
        elif k == "beta":
            ec[k] = rounded(v, 4)
        elif k in ("qv30", "qv_pre60", "qv_post60", "qv_post5") or k.startswith("qv5_"):
            ec[k] = np.round(v).astype(np.float64)
        elif k == "share_sec_traded":
            ec[k] = rounded(v, 3)
        else:
            ec[k] = rounded(v, 1)
    pl.DataFrame(ec).write_parquet(os.path.join(OUT, "event_coin.parquet"), compression="zstd", compression_level=19)

    pm = np.stack([p[4] for p in paths])
    pd_ = {"event_id": [p[0] for p in paths], "kind": [p[1] for p in paths], "group": [p[2] for p in paths],
           "n_coins": np.array([p[3] for p in paths], dtype=np.int32)}
    for j, g in enumerate(GRID):
        pd_[f"t{g}"] = rounded(pm[:, j], 1)
    pl.DataFrame(pd_).write_parquet(os.path.join(OUT, "paths.parquet"), compression="zstd", compression_level=19)

    # lead-lag per symbol, averaged over the windows of each kind
    xc_all = {k: cat(xcs, k) for k in xcs[0]}
    num_cols = [k for k in xc_all if k not in ("event_id", "kind", "symbol")]
    xdf = pl.DataFrame({k: (v if isinstance(v, list) else np.asarray(v, dtype=np.float64)) for k, v in xc_all.items()})
    xsym = (xdf.group_by(["kind", "symbol"]).agg([pl.len().alias("n_windows")] + [pl.col(c).mean() for c in num_cols])
            .sort(["kind", "rank"]))
    xsym = xsym.with_columns([pl.col(c).round(5).cast(pl.Float32) for c in num_cols])
    xsym.write_parquet(os.path.join(OUT, "xcorr_symbol.parquet"), compression="zstd", compression_level=19)

    xtd = {"event_id": [x[0] for x in xts], "kind": [x[1] for x in xts], "group": [x[2] for x in xts],
           "n_coins": np.array([x[3] for x in xts], dtype=np.int32)}
    cm = np.stack([x[4] for x in xts]); bm = np.stack([x[5] for x in xts]); zm = np.stack([x[6] for x in xts])
    for j, L in enumerate(range(-60, 61)):
        nm = f"m{-L}" if L < 0 else f"{L}"
        xtd[f"c_{nm}"] = rounded(cm[:, j], 4)
        xtd[f"b_{nm}"] = rounded(bm[:, j], 4)
    for j, L in enumerate(XC_FINE):
        xtd[f"z_m{-L}" if L < 0 else f"z_{L}"] = rounded(zm[:, j], 4)
    pl.DataFrame(xtd).write_parquet(os.path.join(OUT, "xcorr_tier.parquet"), compression="zstd", compression_level=19)

    with gzip.open(os.path.join(OUT, "fresh_stats.csv.gz"), "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_id", "kind", "tier", "g", "h", "subset", "n", "sx", "sy", "sxx", "sxy", "syy"])
        for r in fresh:
            w.writerow(list(r[:7]) + [f"{v:.6g}" for v in r[7:]])
    sizes = {fn: os.path.getsize(os.path.join(OUT, fn)) for fn in sorted(os.listdir(OUT))}
    C.write_json(os.path.join(OUT, "manifest.json"), {
        "events_total": len(events), "events_done": done, "events_skipped": skipped, "failed_coins": failed_coins,
        "refused": refused, "minutes": (time.time() - t_start) / 60, "file_sizes": sizes, "lags": LAGS,
        "delays": DELAYS, "horizons": HORIZONS, "grid": GRID, "meta": C.run_meta(client)})
    log("done", done, "events;", "skipped", len(skipped), "; sizes", sizes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
