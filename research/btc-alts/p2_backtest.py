"""Stage 3 (Part 2): walk-forward pair trading after costs, on hourly bars and on 5-minute bars, with random-pair
placebo portfolios, plus the pre-specified test of overshoot and reversion after a Bitcoin shock.

Inputs : hourly panel (cache, or downloaded again), out/s1/events.csv, out/s1/symbols.csv
Outputs: out/p2/daily.csv.gz            daily portfolio PnL components for every configuration
         out/p2/windows.csv.gz          per window and configuration
         out/p2/selected_pairs.csv.gz   the pairs chosen in each window
         out/p2/trades.csv.gz           trades of the selected pairs (base rule)
         out/p2/placebo.csv.gz          per placebo draw and configuration: PnL by year, Sharpe
         out/p2/placebo_mean_daily.csv.gz
         out/p2/allpairs.parquet        every pair of every hourly window: selection ranks and base-rule PnL
         out/p2/shock_events.csv.gz     the shock-reversion test, per event
         out/p2/manifest.json
Run: python p2_backtest.py     |     BTCALTS_TEST=1 python p2_backtest.py
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
from common import DAY, HOUR, MIN

TEST = os.environ.get("BTCALTS_TEST") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "out_test" if TEST else "out")
OUT = os.path.join(OUT_ROOT, "p2")
CACHE = os.environ.get("BTCALTS_CACHE", os.path.join(HERE, "cache_test" if TEST else "cache"))

STOP = 4.0
ENTRIES = (2.0, 1.5, 2.5)
R_PLACEBO = 1000
FORM_BARS, TRADE_BARS = 1440, 720
M5 = 5 * MIN
M5_DAYS = 20 if TEST else 365
M5_TOP = 30
B_FORM_DAYS, B_TRADE_DAYS = (6, 3) if TEST else (60, 30)   # 5-minute test B: calendar windows of the hourly test
SHOCK_H = (4, 24, 72)
SHOCK_N = 10
THETA_H_GRID = (0.02, 0.025, 0.03, 0.04, 0.05)
N_PLACEBO_HOURS = 200 if TEST else 1000


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---- statistics -------------------------------------------------------------------------------------------
def adf_t(E: np.ndarray) -> np.ndarray:
    """ADF t-statistic with one lag and no constant, for each column of E (rows are time)."""
    dE = np.diff(E, axis=0)
    y, u1, u2 = dE[1:], E[1:-1], dE[:-1]
    s11, s12, s22 = (u1 * u1).sum(0), (u1 * u2).sum(0), (u2 * u2).sum(0)
    s1y, s2y, syy = (u1 * y).sum(0), (u2 * y).sum(0), (y * y).sum(0)
    det = s11 * s22 - s12 * s12
    with np.errstate(divide="ignore", invalid="ignore"):
        g = (s22 * s1y - s12 * s2y) / det
        ph = (s11 * s2y - s12 * s1y) / det
        rss = syy - g * s1y - ph * s2y
        se = np.sqrt(rss / (y.shape[0] - 2) * s22 / det)
        return g / se


def bh_count(p: np.ndarray, q: float = 0.05) -> int:
    """Number of rejections of Benjamini-Hochberg at level q."""
    p = np.sort(p[np.isfinite(p)])
    m = len(p)
    if m == 0:
        return 0
    ok = np.flatnonzero(p <= q * np.arange(1, m + 1) / m)
    return int(ok[-1] + 1) if len(ok) else 0


def eg_pvalues(t: np.ndarray) -> np.ndarray:
    from statsmodels.tsa.adfvalues import mackinnonp
    return np.array([mackinnonp(float(x), regression="c", N=2) if np.isfinite(x) else np.nan for x in t])


def formation(Cf: np.ndarray):
    """Selection statistics for every pair of the universe from formation closes Cf [bars, n]."""
    n = Cf.shape[1]
    I, J = np.triu_indices(n, 1)
    Af = Cf / Cf[0]
    G = Af.T @ Af
    sq = np.diag(G)
    ssd = sq[I] + sq[J] - 2 * G[I, J]
    mu = Af.mean(0)
    cov = np.cov(Af, rowvar=False, ddof=1)
    sd_d = np.sqrt(np.maximum(cov[I, I] + cov[J, J] - 2 * cov[I, J], 1e-30))
    R = Cf[1:] / Cf[:-1] - 1.0
    cr = np.cov(R, rowvar=False, ddof=1)
    sd_ret = np.sqrt(np.maximum(cr[I, I] + cr[J, J] - 2 * cr[I, J], 1e-30))
    X = np.log(Cf)
    mx = X.mean(0)
    Xc = X - mx
    S = Xc.T @ Xc
    b_ij = S[I, J] / S[J, J]
    b_ji = S[I, J] / S[I, I]
    t_ij = adf_t(Xc[:, I] - b_ij * Xc[:, J])
    t_ji = adf_t(Xc[:, J] - b_ji * Xc[:, I])
    use = t_ij <= t_ji
    A = np.where(use, I, J)
    B = np.where(use, J, I)
    beta = np.where(use, b_ij, b_ji)
    tstat = np.where(use, t_ij, t_ji)
    sd_e = (Xc[:, A] - beta * Xc[:, B]).std(axis=0, ddof=1)
    valid = (beta > 0) & np.isfinite(tstat) & (sd_e > 0)
    return {"I": I, "J": J, "ssd": ssd, "mu_d": mu[I] - mu[J], "sd_d": sd_d, "sd_ret": sd_ret, "base": Cf[0],
            "A": A, "B": B, "beta": beta, "alpha": mx[A] - beta * mx[B], "sd_e": sd_e, "tstat": tstat, "valid": valid,
            "t_fixed": t_ij}


# ---- engine -----------------------------------------------------------------------------------------------
def simulate(z, O, Cc, dead, A, B, entry, F, day, n_days, valid=None, late=False, logm=None, qv=None,
             perp=None, stop=STOP):
    """Vectorised pair simulation over one trading window. One unit of notional per leg.

    z [T, P] z-score at each bar close; O, Cc [T, n] opens and closes (forward-filled); dead [T, n] marks bars
    without a price. Signals at the close of bar t are filled at the open of bar t+1 (t+2 when late).
    Position +1 = long A, short B (entered when z <= -entry); -1 the reverse.
    Returns daily arrays [P, n_days]: gross PnL, traded notional of leg A and of leg B (fees and half-spreads
    are applied to these afterwards, by the liquidity tier of each leg), funding; and counters.
    """
    Tn, P = z.shape
    pos = np.zeros(P, np.int8)
    barred = np.zeros(P, bool) if valid is None else ~valid
    pend_open = np.zeros(P, np.int8)
    pend_close = np.zeros(P, bool)
    reason = np.zeros(P, np.int8)
    eA, eB = np.ones(P), np.ones(P)
    real, prev_val = np.zeros(P), np.zeros(P)
    gross, fund = np.zeros((P, n_days)), np.zeros((P, n_days))
    na, nb = np.zeros((P, n_days)), np.zeros((P, n_days))
    n_entry, n_stop, bars_in = np.zeros(P, np.int32), np.zeros(P, np.int32), np.zeros(P, np.int32)
    zz = np.vstack([np.zeros((1, P), z.dtype), z[:-1]]) if late else z
    f_any = (F != 0).any(axis=1)
    do_log = logm is not None and logm.any()
    trades, cur = [], {}
    sig_shift = 2 if late else 1          # bars between the signal bar and the fill bar
    for t in range(Tn):
        d = day[t]
        if t > 0:
            oa, ob = O[t, A], O[t, B]
            if f_any[t]:
                held = pos != 0
                if held.any():
                    fp = pos * (-F[t, A] * (Cc[t - 1, A] / eA) + F[t, B] * (Cc[t - 1, B] / eB))
                    fp = np.where(held, fp, 0.0)
                    fund[:, d] += fp
                    if do_log:
                        for p in np.flatnonzero(held & logm):
                            cur[p]["funding"] += float(fp[p])
            if pend_close.any():
                cn = pend_close
                ra, rb = oa / eA, ob / eB
                pnl = pos * (ra - rb)
                real[cn] += pnl[cn]
                na[cn, d] += ra[cn]
                nb[cn, d] += rb[cn]
                if do_log:
                    for p in np.flatnonzero(cn & logm):
                        tr = cur.pop(p)
                        tr.update(t_exit=t, reason=int(reason[p]), gross=float(pnl[p]), exit_a=float(ra[p]), exit_b=float(rb[p]))
                        trades.append(tr)
                pos[cn] = 0
                pend_close = np.zeros(P, bool)
            on = pend_open != 0
            if on.any():
                eA[on], eB[on] = oa[on], ob[on]
                pos[on] = pend_open[on]
                na[on, d] += 1.0
                nb[on, d] += 1.0
                n_entry[on] += 1
                if do_log:
                    ts = t - sig_shift
                    for p in np.flatnonzero(on & logm):
                        cur[p] = {"pair": int(p), "t_entry": t, "dir": int(pos[p]), "z_signal": float(z[ts, p]), "funding": 0.0,
                                  "qv_min": float(min(qv[ts, A[p]], qv[ts, B[p]])) if qv is not None else float("nan"),
                                  "perp_a": bool(perp[t, A[p]]) if perp is not None else False,
                                  "perp_b": bool(perp[t, B[p]]) if perp is not None else False}
                pend_open = np.zeros(P, np.int8)
        ca, cb = Cc[t, A], Cc[t, B]
        mtm = np.where(pos != 0, pos * (ca / eA - cb / eB), 0.0)
        val = real + mtm
        gross[:, d] += val - prev_val
        prev_val = val
        bars_in += pos != 0
        zt = zz[t]
        deadp = dead[t, A] | dead[t, B]
        if t < Tn - 1:
            lg, sh = pos == 1, pos == -1
            with np.errstate(invalid="ignore"):
                stop_hit = (lg & (zt <= -stop)) | (sh & (zt >= stop))
                cross = (lg & (zt >= 0)) | (sh & (zt <= 0))
                force = (pos != 0) & deadp
                pend_close = stop_hit | cross | force
                reason = np.where(force, 3, np.where(stop_hit, 2, np.where(cross, 1, reason))).astype(np.int8)
                barred |= stop_hit | deadp
                n_stop += stop_hit
                flat = (pos == 0) & ~barred
                pend_open = np.where(flat & (zt >= entry) & (zt < stop), -1,
                                     np.where(flat & (zt <= -entry) & (zt > -stop), 1, 0)).astype(np.int8)
        else:
            held = pos != 0
            if held.any():
                ra, rb = ca / eA, cb / eB
                na[held, d] += ra[held]
                nb[held, d] += rb[held]
                if do_log:
                    pnl = pos * (ra - rb)
                    for p in np.flatnonzero(held & logm):
                        tr = cur.pop(p)
                        tr.update(t_exit=t, reason=4, gross=float(pnl[p]), exit_a=float(ra[p]), exit_b=float(rb[p]))
                        trades.append(tr)
                pos[:] = 0
    return {"gross": gross, "na": na, "nb": nb, "fund": fund, "n_entry": n_entry, "n_stop": n_stop,
            "bars_in": bars_in, "trades": trades}


def net_of(sim, hsA, hsB, fee_bps=C.TAKER_FEE):
    """Net PnL per pair and day: gross - (fee + half-spread of the leg's tier) x traded notional + funding."""
    f = fee_bps * 1e-4
    return sim["gross"] - (f + hsA)[:, None] * sim["na"] - (f + hsB)[:, None] * sim["nb"] + sim["fund"]


# ---- funding ----------------------------------------------------------------------------------------------
def month_range(t0, t1):
    """'YYYY-MM' strings of the months that overlap [t0, t1)."""
    import datetime as dt
    a = dt.datetime.fromtimestamp(t0 / 1000, C.UTC)
    b = dt.datetime.fromtimestamp((t1 - 1) / 1000, C.UTC)
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def parse_funding_csv(text):
    ts, rs = [], []
    lines = text.strip().splitlines()
    if not lines:
        return ts, rs
    head = lines[0].split(",")
    it, ir, start = 0, len(head) - 1, 0
    if not head[0].strip().lstrip("-").replace(".", "").isdigit():
        names = [h.strip().lower() for h in head]
        it = next((i for i, h in enumerate(names) if h in ("calc_time", "fundingtime", "funding_time")), 0)
        ir = next((i for i, h in enumerate(names) if h in ("last_funding_rate", "fundingrate", "funding_rate")), len(head) - 1)
        start = 1
    for ln in lines[start:]:
        c = ln.split(",")
        try:
            ts.append(int(float(c[it])))
            rs.append(float(c[ir]))
        except (ValueError, IndexError):
            continue
    return ts, rs


def load_funding(client, needed: dict[str, set], path: str):
    """Funding history from Binance's bulk files for the (spot symbol, month) pairs in `needed`.

    Returns {symbol: {"t": ms array, "r": rates, "months": [..], "perp": name}} and a status dict.
    """
    import json
    key = sorted((s, sorted(m)) for s, m in needed.items())
    digest = __import__("hashlib").sha256(json.dumps(key).encode()).hexdigest()
    if os.path.exists(path):
        z = np.load(path, allow_pickle=False)
        if str(z["digest"]) == digest:
            out = {}
            for s in [str(x) for x in z["symbols"]]:
                out[s] = {"t": z[f"t_{s}"], "r": z[f"r_{s}"], "months": [str(x) for x in z[f"m_{s}"]], "perp": str(z[f"p_{s}"])}
            return out, {"source": "cache", "symbols_with_funding": len(out), "status": str(z["status"])}
    out, status, head_seen = {}, "ok", [None]

    def fetch(perp, month):
        blob = client.bulk(f"/data/futures/um/monthly/fundingRate/{perp}/{perp}-fundingRate-{month}.zip")
        if blob is None:
            return None
        try:
            text = C.unzip_single_csv(blob)
        except Exception:  # noqa: BLE001  (a damaged archive counts as a missing month)
            return None
        if head_seen[0] is None:
            head_seen[0] = text[:200]
        return parse_funding_csv(text)

    def one(sym):
        months = sorted(needed[sym])
        base = C.base_of(sym)
        for perp in (sym, "1000" + sym, "1000000" + sym, "1M" + sym):
            got = None
            for m in months[::-1][:3]:            # a perpetual listed late may miss the earliest months
                got = fetch(perp, m)
                if got is not None:
                    break
            if got is None:
                continue
            ts, rs, ok_months = [], [], []
            for m in months:
                g = fetch(perp, m)
                if g is None:
                    continue
                ts.extend(g[0]); rs.extend(g[1]); ok_months.append(m)
            return sym, {"t": np.array(ts, np.int64), "r": np.array(rs, np.float64), "months": ok_months, "perp": perp}
        return sym, None

    try:
        first = client.bulk("/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2023-01.zip")
        if first is None and not TEST:
            status = "probe file missing"
        with ThreadPoolExecutor(8) as ex:
            for sym, rec in ex.map(one, sorted(needed)):
                if rec is not None and len(rec["t"]):
                    out[sym] = rec
    except C.Refused as e:
        status = f"refused: {e!r}"
        out = {}
    save = {"digest": np.array(digest), "symbols": np.array(sorted(out)), "status": np.array(status)}
    for s, rec in out.items():
        save[f"t_{s}"], save[f"r_{s}"] = rec["t"], rec["r"]
        save[f"m_{s}"], save[f"p_{s}"] = np.array(rec["months"]), np.array(rec["perp"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, **save)
    return out, {"source": "download", "symbols_with_funding": len(out), "status": status, "sample_head": head_seen[0]}


def funding_matrix(fund, panel):
    """F [bars, symbols]: funding rate paid by longs at the bar that opens at the funding time (0 elsewhere);
    perp [bars, symbols]: True where a funding file exists for that month (the perpetual was listed)."""
    import datetime as dt
    n, step, start = panel["close"].shape[0], panel["step_ms"], panel["start_ms"]
    F = np.zeros(panel["close"].shape, np.float32)
    perp = np.zeros(panel["close"].shape, bool)
    col = {s: j for j, s in enumerate(panel["symbols"])}
    for s, rec in fund.items():
        if s not in col:
            continue
        idx = np.round((rec["t"] - start) / step).astype(np.int64)
        ok = (idx >= 0) & (idx < n)
        F[idx[ok], col[s]] = rec["r"][ok]
        for m in rec["months"]:
            y, mo = int(m[:4]), int(m[5:7])
            a = C.ms(y, mo, 1)
            b = C.ms(y + (mo == 12), mo % 12 + 1, 1)
            ia, ib = max(0, (a - start) // step), min(n, (b - start) // step)
            if ib > ia:
                perp[ia:ib, col[s]] = True
    return F, perp


# ---- walk-forward -------------------------------------------------------------------------------------------
def ffill_window(Ct, Ot, last_close):
    """Forward-fill closes inside the trading window (seeded with the last formation close); opens that are
    missing take the previous close. Returns filled closes, filled opens and the mask of missing bars."""
    dead = np.isnan(Ct)
    Cc = Ct.copy()
    prev = last_close.copy()
    for t in range(Cc.shape[0]):
        m = np.isnan(Cc[t])
        Cc[t, m] = prev[m]
        prev = Cc[t]
    Oc = Ot.copy()
    mo = np.isnan(Oc)
    shifted = np.vstack([last_close[None, :], Cc[:-1]])
    Oc[mo] = shifted[mo]
    return Cc, Oc, dead


def greedy_disjoint(order, A, B, n_pairs):
    """The best-ranked pairs such that no coin appears twice."""
    used, out = set(), []
    for p in order:
        a, b = int(A[p]), int(B[p])
        if a in used or b in used:
            continue
        out.append(int(p))
        used.update((a, b))
        if len(out) == n_pairs:
            break
    return np.array(out, np.int64)


def run_walkforward(tag, panel, rank_panel, F, perp, Ts, top_n, n_pairs, cfg, entries, results,
                    FORM_BARS=FORM_BARS, TRADE_BARS=TRADE_BARS):
    """One test (bar size and window lengths). Appends to `results` (daily components, windows, selected pairs,
    trades, placebo, all pairs)."""
    step, start = panel["step_ms"], panel["start_ms"]
    col = {s: j for j, s in enumerate(panel["symbols"])}
    D0 = Ts[0] // DAY
    n_days_total = int((Ts[-1] + TRADE_BARS * step - 1) // DAY - D0 + 1)
    methods = ("dist", "coint")
    cfgs = []
    for m in methods:
        for e in entries:
            cfgs.append((m, f"e{e}", e, False, False))
        if 2.0 in entries and tag == "1h":
            cfgs.append((m, "vol", 2.0, True, False))
            # POST HOC diagnostic, added after the first results showed that one coin can be in all 20 selected pairs:
            # the same rule with each coin in at most one pair. Not part of the pre-specified family.
            cfgs.append((m, "e2.0div", 2.0, False, True))
    names = [f"{tag}_{m}_{v}_{tm}" for (m, v, _, _, _) in cfgs for tm in ("ontime", "late")]
    daily = {nm: {k: np.zeros(n_days_total) for k in ("gross", "n1", "n2", "n3", "fund")} for nm in names}
    plac = {nm: np.zeros((R_PLACEBO, n_days_total), np.float32) for nm in names}
    plac_g = {nm: np.zeros((R_PLACEBO, n_days_total), np.float32) for nm in names}
    hind = {f"{tag}_{m}": np.zeros(n_days_total) for m in methods}
    seed_off = {"1h": 100, "5mA": 20000, "5mB": 40000}[tag]
    for k, T in enumerate(Ts):
        iT = int((T - start) // step)
        ranks = C.rank_at(rank_panel, T)[:top_n]
        syms = [r["symbol"] for r in ranks if r["symbol"] in col]
        rk = {r["symbol"]: r["rank"] for r in ranks}
        cols = np.array([col[s] for s in syms])
        Cf_all = panel["close"][iT - FORM_BARS:iT, cols].astype(np.float64)
        ok = ~np.isnan(Cf_all).any(axis=0)
        syms = [s for s, o in zip(syms, ok) if o]
        cols = cols[ok]
        n = len(syms)
        if n < 5:
            log(f"  [{tag}] window {k}: only {n} coins, skipped")
            continue
        Cf = Cf_all[:, ok]
        fs = formation(Cf)
        P = len(fs["I"])
        Ct = panel["close"][iT:iT + TRADE_BARS, cols].astype(np.float64)
        Ot = panel["open"][iT:iT + TRADE_BARS, cols].astype(np.float64)
        Cc, Oc, dead = ffill_window(Ct, Ot, Cf[-1])
        qv = np.nan_to_num(panel["qv"][iT:iT + TRADE_BARS, cols].astype(np.float64))
        Fw = F[iT:iT + TRADE_BARS, cols].astype(np.float64)
        pw = perp[iT:iT + TRADE_BARS, cols]
        bar_t = T + np.arange(TRADE_BARS) * step
        day = (bar_t // DAY - T // DAY).astype(np.int64)
        n_days = int(day[-1] + 1)
        off = int(T // DAY - D0)
        tier = np.array([C.tier_of_rank(rk[s]) for s in syms])
        hs = np.array([C.HALF_SPREAD[int(t_)] * 1e-4 for t_ in tier])
        # z-scores
        At = Cc / fs["base"]
        z_d = ((At[:, fs["I"]] - At[:, fs["J"]]) - fs["mu_d"]) / fs["sd_d"]
        Xt = np.log(Cc)
        with np.errstate(divide="ignore", invalid="ignore"):
            z_c = (Xt[:, fs["A"]] - fs["beta"] * Xt[:, fs["B"]] - fs["alpha"]) / fs["sd_e"]
        legs = {"dist": (fs["I"], fs["J"], z_d, None), "coint": (fs["A"], fs["B"], z_c, fs["valid"])}
        # selection
        sel = {"dist": np.argsort(fs["ssd"], kind="stable")[:n_pairs]}
        tv = np.where(fs["valid"], fs["tstat"], np.inf)
        sel["coint"] = np.argsort(tv, kind="stable")[:n_pairs]
        sel["coint"] = sel["coint"][np.isfinite(tv[sel["coint"]])]
        p_fixed = eg_pvalues(fs["t_fixed"])
        bh_all = bh_count(p_fixed)
        p_sel = eg_pvalues(fs["tstat"][sel["coint"]])
        thr = 0.05 * bh_all / max(P, 1)
        bh_sel = int((p_sel <= thr).sum()) if bh_all else 0
        rng = {m: np.random.default_rng(C.SEED + seed_off + (0 if m == "dist" else 5000) + k) for m in methods}
        draw = {}
        for m in methods:
            pool = np.arange(P) if m == "dist" else np.flatnonzero(fs["valid"])
            kk = min(n_pairs, len(pool))
            pick = rng[m].random((R_PLACEBO, len(pool))).argpartition(kk - 1, axis=1)[:, :kk]
            draw[m] = pool[pick]
        sel_div, draw_div = {}, {}
        if tag == "1h":
            pidx = np.full((n, n), -1, np.int64)
            pidx[fs["I"], fs["J"]] = np.arange(P)
            pidx[fs["J"], fs["I"]] = np.arange(P)
            for m in methods:
                order = np.argsort(fs["ssd"], kind="stable") if m == "dist" else np.argsort(tv, kind="stable")
                if m == "coint":
                    order = order[np.isfinite(tv[order])]
                sel_div[m] = greedy_disjoint(order, fs["I"], fs["J"], n_pairs)
                rr = np.random.default_rng(C.SEED + 60000 + (0 if m == "dist" else 5000) + k)
                dd = np.zeros((R_PLACEBO, n_pairs), np.int64)
                for r_ in range(R_PLACEBO):
                    perm = rr.permutation(n)
                    cand = pidx[perm[0:2 * (n // 2):2], perm[1:2 * (n // 2):2]]
                    if m == "coint":
                        cand = cand[fs["valid"][cand]]
                    dd[r_] = np.resize(cand[:n_pairs], n_pairs)
                draw_div[m] = dd
        wrow = {"bar": tag, "window": k, "T": C.iso(T), "n_universe": n, "pairs": P, "coint_valid": int(fs["valid"].sum()),
                "bh_fixed_order": bh_all, "bh_selected": bh_sel, "min_eg_p_selected": float(np.nanmin(p_sel)) if len(p_sel) else float("nan")}
        base_net, div_net = {}, {}
        for (m, v, e, vol, div) in cfgs:
            A_, B_, z_, valid_ = legs[m]
            pick = sel_div[m] if div else sel[m]
            logm = np.zeros(P, bool)
            logm[pick] = True
            for tm in ("ontime", "late"):
                nm = f"{tag}_{m}_{v}_{tm}"
                want_log = v in ("e2.0", "e2.0div")
                sim = simulate(z_, Oc, Cc, dead, A_, B_, e, Fw, day, n_days, valid=valid_,
                               late=(tm == "late"), logm=logm if want_log else None, qv=qv, perp=pw)
                net = net_of(sim, hs[A_], hs[B_])
                w = np.ones(len(pick))
                if vol:
                    inv = 1.0 / fs["sd_ret"][pick]
                    w = inv / inv.mean()
                for key in ("gross", "fund"):
                    daily[nm][key][off:off + n_days] += (sim[key][pick] * w[:, None]).sum(0) / (2 * n_pairs)
                tA, tB = tier[A_[pick]], tier[B_[pick]]
                for t_ in (1, 2, 3):      # traded notional by liquidity tier of the leg, so any cost can be applied later
                    nt = (sim["na"][pick] * (w * (tA == t_))[:, None]).sum(0) + (sim["nb"][pick] * (w * (tB == t_))[:, None]).sum(0)
                    daily[nm][f"n{t_}"][off:off + n_days] += nt / (2 * n_pairs)
                # placebo: 20 random pairs of the same universe (disjoint ones for the diversified variant), same rule, same costs
                di = draw_div[m] if div else draw[m]
                if vol:
                    inv = 1.0 / fs["sd_ret"][di]
                    wd = inv / inv.mean(axis=1, keepdims=True)
                    plac[nm][:, off:off + n_days] += (net[di] * wd[:, :, None]).sum(1) / (2 * n_pairs)
                    plac_g[nm][:, off:off + n_days] += (sim["gross"][di] * wd[:, :, None]).sum(1) / (2 * n_pairs)
                else:
                    plac[nm][:, off:off + n_days] += net[di].sum(1) / (2 * n_pairs)
                    plac_g[nm][:, off:off + n_days] += sim["gross"][di].sum(1) / (2 * n_pairs)
                wrow[f"{nm}|gross"] = float((sim["gross"][pick] * w[:, None]).sum() / (2 * n_pairs))
                wrow[f"{nm}|net"] = float((net[pick] * w[:, None]).sum() / (2 * n_pairs))
                wrow[f"{nm}|entries"] = int(sim["n_entry"][pick].sum())
                wrow[f"{nm}|stops"] = int(sim["n_stop"][pick].sum())
                if v == "e2.0div":
                    div_net[(m, tm)] = (net.sum(1), sim["gross"].sum(1), sim["n_entry"])
                if v == "e2.0":
                    base_net[(m, tm)] = (net.sum(1), sim["gross"].sum(1), sim["n_entry"])
                    if tm == "ontime":
                        # hindsight: the 20 pairs with the best realised net PnL in this window
                        pool = np.arange(P) if valid_ is None else np.flatnonzero(valid_)
                        best = pool[np.argsort(-net.sum(1)[pool], kind="stable")[:n_pairs]]
                        hind[f"{tag}_{m}"][off:off + n_days] += net[best].sum(0) / (2 * n_pairs)
                if want_log:
                    for tr in sim["trades"]:
                        p = tr["pair"]
                        cost = ((C.TAKER_FEE * 1e-4 + hs[A_[p]]) * (1.0 + tr["exit_a"])
                                + (C.TAKER_FEE * 1e-4 + hs[B_[p]]) * (1.0 + tr["exit_b"]))
                        results["trades"].append([
                            tag, k, m + ("_div" if div else ""), tm, syms[A_[p]], syms[B_[p]], C.iso(bar_t[tr["t_entry"]]),
                            C.iso(bar_t[tr["t_exit"]]), tr["dir"], f"{tr['z_signal']:.3f}", tr["reason"], f"{tr['gross'] * 1e4:.2f}",
                            f"{cost * 1e4:.2f}",
                            f"{tr['funding'] * 1e4:.3f}", f"{tr['qv_min']:.0f}", int(tr["perp_a"]), int(tr["perp_b"]),
                            rk[syms[A_[p]]], rk[syms[B_[p]]]])
        results["windows"].append(wrow)
        for m in methods:
            A_, B_, _, _ = legs[m]
            stat = fs["ssd"] if m == "dist" else fs["tstat"]
            for label, picks, nets in ((m, sel[m], base_net), (m + "_div", sel_div.get(m, []), div_net)):
                for r_, p in enumerate(picks):
                    results["selected"].append([
                        tag, k, C.iso(T)[:10], label, r_ + 1, syms[A_[p]], syms[B_[p]], rk[syms[A_[p]]], rk[syms[B_[p]]],
                        f"{stat[p]:.6g}", f"{fs['beta'][p]:.4f}" if m == "coint" else "", f"{fs['sd_ret'][p]:.6f}",
                        f"{nets[(m, 'ontime')][1][p] * 1e4:.2f}", f"{nets[(m, 'ontime')][0][p] * 1e4:.2f}",
                        f"{nets[(m, 'late')][0][p] * 1e4:.2f}", int(nets[(m, 'ontime')][2][p])])
        if tag == "1h":
            order_d = np.empty(P, np.int32)
            order_d[np.argsort(fs["ssd"], kind="stable")] = np.arange(P)
            order_c = np.empty(P, np.int32)
            order_c[np.argsort(tv, kind="stable")] = np.arange(P)
            order_c[~fs["valid"]] = -1
            results["allpairs"].append({
                "window": np.full(P, k, np.int16), "a": [syms[i] for i in fs["I"]], "b": [syms[j] for j in fs["J"]],
                "ssd_rank": order_d.astype(np.int16), "eg_rank": order_c.astype(np.int16),
                "net_dist": np.round(base_net[("dist", "ontime")][0] * 1e4, 0).astype(np.float32),
                "net_coint": np.round(base_net[("coint", "ontime")][0] * 1e4, 0).astype(np.float32)})
        if k % 5 == 0 or k == len(Ts) - 1:
            log(f"  [{tag}] window {k + 1}/{len(Ts)} {C.iso(T)[:10]}: {n} coins, {P} pairs, BH {bh_all}, "
                f"dist net {wrow[f'{tag}_dist_e2.0_ontime|net'] * 1e4:.1f} bps, coint net {wrow[f'{tag}_coint_e2.0_ontime|net'] * 1e4:.1f} bps")
    results["daily"][tag] = {"D0": int(D0), "n_days": n_days_total, "series": daily, "hindsight": hind}
    results["placebo"][tag] = {"net": plac, "gross": plac_g}


# ---- shock-reversion test -----------------------------------------------------------------------------------
def shock_test(panel, F, events, label, mirror, rows):
    """events: list of (id, hour index of the shock bar). Appends one row per event and horizon."""
    start = panel["start_ms"]
    col = {s: j for j, s in enumerate(panel["symbols"])}
    jb = col["BTCUSDT"]
    cl, op = panel["close"], panel["open"]
    n = cl.shape[0]
    Fz = F
    for eid, h in events:
        if h - 1 < 721 or h + 2 + max(SHOCK_H) >= n:
            continue
        t_bar = start + h * HOUR
        ranks = C.rank_at(panel, (t_bar // DAY) * DAY)[:100]
        syms = [r["symbol"] for r in ranks if r["symbol"] != "BTCUSDT"]
        rk = {r["symbol"]: r["rank"] for r in ranks}
        betas = C.beta_at(panel, syms, t_bar)
        cols = np.array([col[s] for s in syms])
        beta = np.array([betas[s] for s in syms])
        with np.errstate(divide="ignore", invalid="ignore"):
            ar = (np.log(cl[h + 1, cols].astype(np.float64)) - np.log(cl[h - 1, cols].astype(np.float64))
                  - beta * (np.log(float(cl[h + 1, jb])) - np.log(float(cl[h - 1, jb]))))
        e_px = op[h + 2, cols].astype(np.float64)
        ok = np.isfinite(ar) & np.isfinite(beta) & (beta > 0) & np.isfinite(e_px)
        if ok.sum() < 30:
            continue
        idx = np.flatnonzero(ok)
        order = idx[np.argsort(ar[idx] if not mirror else -ar[idx], kind="stable")]
        pick = order[:SHOCK_N]
        sgn = -1.0 if mirror else 1.0
        btc_e = float(op[h + 2, jb])
        for H in SHOCK_H:
            x = op[h + 2 + H, cols].astype(np.float64)
            # a coin that stops trading is closed at its last close
            last = np.array([cl[:h + 2 + H, c][~np.isnan(cl[:h + 2 + H, c])][-1] if np.isnan(x[i]) else x[i]
                             for i, c in enumerate(cols)])
            btc_x = float(op[h + 2 + H, jb])
            pr = (last / e_px - 1.0) - beta * (btc_x / btc_e - 1.0)
            fa = Fz[h + 3:h + 2 + H + 1, :][:, cols].astype(np.float64).sum(0)     # funding stamps in (entry, exit]
            fb = float(Fz[h + 3:h + 2 + H + 1, jb].astype(np.float64).sum())
            fund = sgn * (-fa + beta * fb)
            hs = np.array([C.HALF_SPREAD[C.tier_of_rank(rk[s])] for s in syms])
            cost = 2 * (C.TAKER_FEE + hs) + 2 * beta * (C.TAKER_FEE + C.HALF_SPREAD[1])
            cost_maker = 2 * C.MAKER_FEE * (1 + beta)
            xs, ys = ar[idx], pr[idx]
            slope = float(((xs - xs.mean()) * (ys - ys.mean())).sum() / ((xs - xs.mean()) ** 2).sum())
            qv_dec = np.nan_to_num(panel["qv"][h + 1, cols].astype(np.float64))      # volume of the bar that ends at the decision
            rows.append([label, eid, C.iso(t_bar), H, int(ok.sum()), f"{np.mean(ar[idx]) * 1e4:.2f}", f"{np.mean(ar[pick]) * 1e4:.2f}",
                         f"{sgn * np.mean(pr[pick]) * 1e4:.2f}", f"{np.mean(cost[pick]):.2f}", f"{np.mean(cost_maker[pick]):.2f}",
                         f"{np.mean(fund[pick]) * 1e4:.3f}", f"{slope:.4f}", f"{np.mean(pr[idx]) * 1e4:.2f}",
                         f"{(float(cl[h + 1, jb]) / float(cl[h - 1, jb]) - 1) * 1e4:.1f}", f"{np.mean(beta[pick]):.3f}",
                         f"{(btc_x / btc_e - 1.0) * 1e4:.1f}", f"{np.mean(last[pick] / e_px[pick] - 1.0) * 1e4:.1f}",
                         f"{np.mean([rk[syms[i]] for i in pick]):.1f}", f"{np.median(qv_dec[pick]):.0f}", f"{np.min(qv_dec[pick]):.0f}",
                         f"{np.mean(last[idx] / e_px[idx] - 1.0) * 1e4:.1f}", f"{np.mean(beta[idx]):.3f}"])


# ---- main ---------------------------------------------------------------------------------------------------
def write_gz(path, header, rows):
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    warnings.simplefilter("ignore", RuntimeWarning)
    cfg = C.load_config()
    client = C.make_client(cfg)
    os.makedirs(OUT, exist_ok=True)
    t_run = time.time()

    # hourly panel: cache, or the same download as stage 1
    ppath = os.path.join(CACHE, "hourly_panel.npz")
    keep = []
    with open(os.path.join(OUT_ROOT, "s1", "symbols.csv")) as f:
        for r in csv.DictReader(f):
            if not r["excluded"]:
                keep.append(r["symbol"])
    panel = None
    if os.path.exists(ppath):
        panel = C.load_panel(ppath)
        if panel["start_ms"] != cfg.hourly_start or panel["n_hours"] != (cfg.end - cfg.hourly_start) // HOUR or set(panel["symbols"]) != set(keep):
            panel = None
    if panel is None:
        log("hourly panel not in cache: downloading")
        panel = C.build_hourly_panel(client, keep, cfg.hourly_start, cfg.end, cfg.workers, log)
        C.save_panel(panel, ppath)
    panel["step_ms"] = HOUR
    digest = C.panel_digest(panel)
    log(f"hourly panel {panel['close'].shape} sha256 {digest[:16]}")

    # windows
    n_win = int((cfg.end - cfg.first_T) // (TRADE_BARS * HOUR))
    Ts_h = [cfg.first_T + k * TRADE_BARS * HOUR for k in range(n_win)]
    m5_start = cfg.end - M5_DAYS * DAY
    # 5-minute test A: the same number of bars as the hourly test (5 days formation, 2.5 days trading)
    first_T5 = m5_start + FORM_BARS * M5
    n_win5 = int((cfg.end - first_T5) // (TRADE_BARS * M5))
    Ts_5 = [first_T5 + k * TRADE_BARS * M5 for k in range(n_win5)]
    # 5-minute test B: the same calendar windows as the hourly test (60 days formation, 30 days trading), ending at the data end
    FB, TB = B_FORM_DAYS * 288, B_TRADE_DAYS * 288
    n_winB = int((cfg.end - m5_start - FB * M5) // (TB * M5))
    Ts_B = [cfg.end - (n_winB - k) * TB * M5 for k in range(n_winB)]
    log(f"{n_win} hourly windows from {C.iso(Ts_h[0])[:10]}; 5-minute A: {n_win5} windows from {C.iso(Ts_5[0])}; "
        f"5-minute B: {n_winB} windows from {C.iso(Ts_B[0]) if Ts_B else 'n/a'}")

    # 5-minute panel for the coins that are ever in the top 30 at a formation end
    need5 = set()
    for T in Ts_5 + Ts_B:
        need5 |= {r["symbol"] for r in C.rank_at(panel, T)[:M5_TOP]}
    need5 = sorted(need5)
    p5path = os.path.join(CACHE, "panel_5m.npz")
    panel5 = None
    if os.path.exists(p5path):
        panel5 = C.load_panel(p5path)
        if panel5["start_ms"] != m5_start or panel5["symbols"] != need5 or panel5["n_hours"] != (cfg.end - m5_start) // M5:
            panel5 = None
    if panel5 is None:
        log(f"5-minute panel: downloading {len(need5)} symbols")
        panel5 = C.build_panel(client, need5, "5m", M5, m5_start, cfg.end, cfg.workers, 72, log)
        C.save_panel(panel5, p5path)
    panel5["step_ms"] = M5
    log(f"5-minute panel {panel5['close'].shape}, gap bars filled {panel5.get('filled', 'n/a')}")

    # events for the shock test
    ev_a, ev_up = [], []
    with open(os.path.join(OUT_ROOT, "s1", "events.csv")) as f:
        for r in csv.DictReader(f):
            h = int((int(r["s_star_ms"]) - panel["start_ms"]) // HOUR)
            if r["kind"] == "down":
                ev_a.append((r["event_id"], h))
            elif r["kind"] == "up":
                ev_up.append((r["event_id"], h))
    jb = panel["symbols"].index("BTCUSDT")
    cb = panel["close"][:, jb].astype(np.float64)
    rb = np.concatenate([[np.nan], cb[1:] / cb[:-1] - 1.0])
    counts, ev_b_by = {}, {}
    for th in THETA_H_GRID:
        trig = np.flatnonzero(rb <= -th)
        trig = trig[trig >= 722]
        first = trig[np.concatenate([[True], np.diff(trig) >= 24])] if len(trig) else trig
        counts[th], ev_b_by[th] = len(first), first
    inside = [th for th, n_ in counts.items() if 50 <= n_ <= 150]
    pool = inside if inside else list(counts)
    theta_h = max(pool, key=lambda th: (-abs(counts[th] - 100), th))
    ev_b = [(f"H{i + 1:04d}", int(h)) for i, h in enumerate(ev_b_by[theta_h])]
    trig_up = np.flatnonzero(rb >= theta_h)
    trig_up = trig_up[trig_up >= 722]
    first_up = trig_up[np.concatenate([[True], np.diff(trig_up) >= 24])] if len(trig_up) else trig_up
    ev_b_up = [(f"HU{i + 1:04d}", int(h)) for i, h in enumerate(first_up)]
    log(f"shock test: {len(ev_a)} one-minute down events, hourly theta {theta_h} -> {len(ev_b)} events {counts}")
    rngp = np.random.default_rng(C.SEED + 3)
    all_h = np.array(sorted([h for _, h in ev_a] + [h for _, h in ev_b]))
    plc = []
    lo_h = max(722, int((cfg.p1_start - panel["start_ms"]) // HOUR) if False else 722)
    while len(plc) < N_PLACEBO_HOURS:
        h = int(rngp.integers(lo_h, panel["close"].shape[0] - 80))
        j = np.searchsorted(all_h, h)
        if (j < len(all_h) and all_h[j] - h < 24) or (j > 0 and h - all_h[j - 1] < 24):
            continue
        plc.append((f"P{len(plc) + 1:04d}", h))

    # funding: months in which a symbol is in a universe, plus the months of the shock events
    needed: dict[str, set] = {}

    def need(sym, t0, t1):
        needed.setdefault(sym, set()).update(month_range(t0, t1))

    for T in Ts_h:
        for r in C.rank_at(panel, T)[:cfg.top_n]:
            need(r["symbol"], T, T + TRADE_BARS * HOUR)
    for T in Ts_5:
        for r in C.rank_at(panel, T)[:M5_TOP]:
            need(r["symbol"], T, T + TRADE_BARS * M5)
    for T in Ts_B:
        for r in C.rank_at(panel, T)[:M5_TOP]:
            need(r["symbol"], T, T + TB * M5)
    for _, h in ev_a + ev_b + ev_up + ev_b_up + plc:
        t = panel["start_ms"] + h * HOUR
        if h < 722 or h + 80 >= panel["close"].shape[0]:
            continue
        for r in C.rank_at(panel, (t // DAY) * DAY)[:100]:
            need(r["symbol"], t, t + 80 * HOUR)
        need("BTCUSDT", t, t + 80 * HOUR)
    fund, fstat = load_funding(client, needed, os.path.join(CACHE, "funding.npz"))
    log(f"funding: {fstat}")
    F, perp = funding_matrix(fund, panel)
    F5, perp5 = funding_matrix(fund, panel5)

    results = {"daily": {}, "placebo": {}, "windows": [], "selected": [], "trades": [], "allpairs": []}
    log("hourly walk-forward")
    run_walkforward("1h", panel, panel, F, perp, Ts_h, cfg.top_n, cfg.n_pairs, cfg, ENTRIES, results)
    log("5-minute walk-forward A (same number of bars)")
    run_walkforward("5mA", panel5, panel, F5, perp5, Ts_5, M5_TOP, cfg.n_pairs, cfg, (2.0,), results)
    if Ts_B:
        log("5-minute walk-forward B (same calendar windows)")
        run_walkforward("5mB", panel5, panel, F5, perp5, Ts_B, M5_TOP, cfg.n_pairs, cfg, (2.0,), results, FB, TB)

    log("shock-reversion test")
    srows = []
    shock_test(panel, F, ev_a, "A_1min_down", False, srows)
    shock_test(panel, F, ev_b, "B_hourly_down", False, srows)
    shock_test(panel, F, plc, "placebo", False, srows)
    shock_test(panel, F, ev_up, "A_1min_up_mirror", True, srows)
    shock_test(panel, F, ev_b_up, "B_hourly_up_mirror", True, srows)
    write_gz(os.path.join(OUT, "shock_events.csv.gz"),
             ["set", "event_id", "utc", "H", "n_coins", "mean_ar_all_bps", "mean_ar_picked_bps", "gross_bps", "cost_taker_bps",
              "cost_maker_bps", "funding_bps", "xs_slope", "all_coins_hedged_bps", "btc_shock_bps", "mean_beta_picked",
              "btc_hold_return_bps", "picked_unhedged_bps", "mean_liq_rank_picked", "median_hourly_volume_picked_usd",
              "min_hourly_volume_picked_usd", "all_coins_unhedged_bps", "mean_beta_all"], srows)

    # ---- outputs ----
    import datetime as dt
    for tag, d in results["daily"].items():
        dates = [(dt.datetime.fromtimestamp((d["D0"] + i) * 86400, C.UTC)).strftime("%Y-%m-%d") for i in range(d["n_days"])]
        header = ["date"]
        colsd = []
        for nm, comp in d["series"].items():
            for key in ("gross", "n1", "n2", "n3", "fund"):
                header.append(f"{nm}|{key}")
                colsd.append(comp[key])
        for nm, v in d["hindsight"].items():
            header.append(f"{nm}_hindsight|net")
            colsd.append(v)
        write_gz(os.path.join(OUT, f"daily_{tag}.csv.gz"), header,
                 [[dates[i]] + [f"{c[i]:.8g}" for c in colsd] for i in range(d["n_days"])])
        # placebo summaries
        years = np.array([int(x[:4]) for x in dates])
        prow, mrow_h, mcols = [], ["date"], []
        for nm in d["series"]:
            pn = results["placebo"][tag]["net"][nm].astype(np.float64)
            pg = results["placebo"][tag]["gross"][nm].astype(np.float64)
            sd = pn.std(axis=1, ddof=1)
            sharpe = np.where(sd > 0, pn.mean(axis=1) / sd * np.sqrt(365), 0.0)
            split_day = (cfg.split_p2 // DAY) - d["D0"]
            for r_ in range(pn.shape[0]):
                prow.append([nm, r_, f"{pn[r_].sum() * 1e4:.2f}", f"{pg[r_].sum() * 1e4:.2f}", f"{sharpe[r_]:.4f}",
                             f"{pn[r_, :max(split_day, 0)].sum() * 1e4:.2f}", f"{pn[r_, max(split_day, 0):].sum() * 1e4:.2f}"]
                            + [f"{pn[r_, years == y].sum() * 1e4:.2f}" for y in sorted(set(years.tolist()))])
            mrow_h += [f"{nm}|net", f"{nm}|gross"]
            mcols += [pn.mean(axis=0), pg.mean(axis=0)]
        write_gz(os.path.join(OUT, f"placebo_{tag}.csv.gz"),
                 ["config", "draw", "net_bps", "gross_bps", "sharpe", "net_selection_bps", "net_evaluation_bps"]
                 + [f"net_{y}_bps" for y in sorted(set(years.tolist()))], prow)
        write_gz(os.path.join(OUT, f"placebo_mean_daily_{tag}.csv.gz"), mrow_h,
                 [[dates[i]] + [f"{c[i]:.8g}" for c in mcols] for i in range(d["n_days"])])
    wkeys = []
    for w in results["windows"]:
        for kk in w:
            if kk not in wkeys:
                wkeys.append(kk)
    write_gz(os.path.join(OUT, "windows.csv.gz"), wkeys, [[w.get(kk, "") for kk in wkeys] for w in results["windows"]])
    write_gz(os.path.join(OUT, "selected_pairs.csv.gz"),
             ["bar", "window", "T", "method", "rank_in_selection", "a", "b", "liq_rank_a", "liq_rank_b", "stat", "beta",
              "sd_ret", "gross_bps", "net_bps", "net_late_bps", "entries"], results["selected"])
    write_gz(os.path.join(OUT, "trades.csv.gz"),
             ["bar", "window", "method", "timing", "a", "b", "entry_utc", "exit_utc", "dir", "z_signal", "exit_reason",
              "gross_bps", "cost_taker_bps", "funding_bps", "min_leg_quote_volume_signal_bar", "perp_a", "perp_b",
              "liq_rank_a", "liq_rank_b"], results["trades"])
    if results["allpairs"]:
        ap = {}
        for key in results["allpairs"][0]:
            v0 = results["allpairs"][0][key]
            ap[key] = [x for d_ in results["allpairs"] for x in d_[key]] if isinstance(v0, list) else np.concatenate([d_[key] for d_ in results["allpairs"]])
        df = pl.DataFrame(ap).with_columns([pl.col("a").cast(pl.Categorical), pl.col("b").cast(pl.Categorical)])
        df.write_parquet(os.path.join(OUT, "allpairs.parquet"), compression="zstd", compression_level=19)
    sizes = {fn: os.path.getsize(os.path.join(OUT, fn)) for fn in sorted(os.listdir(OUT))}
    C.write_json(os.path.join(OUT, "manifest.json"), {
        "panel_sha256": digest, "hourly_windows": n_win, "five_minute_windows_A": n_win5, "five_minute_windows_B": n_winB,
        "five_minute_symbols": len(need5),
        "five_minute_start": C.iso(m5_start), "funding": fstat, "funding_symbols": sorted(fund),
        "funding_perp_names": {s: fund[s]["perp"] for s in sorted(fund) if fund[s]["perp"] != s},
        "symbols_needing_funding": len(needed), "theta_hourly": theta_h, "hourly_shock_counts": {str(k): v for k, v in counts.items()},
        "shock_events": {"A": len(ev_a), "B": len(ev_b), "placebo": len(plc), "A_up": len(ev_up), "B_up": len(ev_b_up)},
        "placebo_draws": R_PLACEBO, "entries": ENTRIES, "stop": STOP, "file_sizes": sizes,
        "minutes": (time.time() - t_run) / 60, "meta": C.run_meta(client)})
    log("done", sizes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
