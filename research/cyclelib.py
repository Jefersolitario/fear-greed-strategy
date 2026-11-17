"""Shared library: causal BTC cycle indicators, flags, and the dollar-PnL simulator.

Conventions
-----------
* Every indicator value stamped day D uses data up to and including the UTC close of D.
* Every *flag* stamped day D is the indicator condition evaluated on D-1 (one-day lag),
  i.e. what is knowable before the close of D, when the fill happens.
* Fitted models (power law, S2F) are re-fitted on an expanding window ending at D.
* "lit" thresholds are fixed numbers from the practitioner literature (publication dates in
  LIT_NOTES). "cal17" thresholds are quantiles of the indicator's own distribution over
  2011-01-01..2017-12-31 and are frozen after that date.
"""
import datetime as dt
import numpy as np
import polars as pl

LONG_PATH = "/home/claude/data/btc_long.parquet"
DAILY_PATH = "/home/claude/data/daily_v2.parquet"
OUT = "/home/claude/cycle/out"

GENESIS = dt.date(2009, 1, 3)
HALVINGS = [dt.date(2012, 11, 28), dt.date(2016, 7, 9), dt.date(2020, 5, 11), dt.date(2024, 4, 20)]
CAL_START = dt.date(2011, 1, 1)
CAL_END = dt.date(2017, 12, 31)
ONCHAIN_END = dt.date(2026, 5, 23)
COST = 0.001
STAKE = 1000.0

# name: (column, direction) ; direction +1 means high value = expensive
CONT = {
    "w200": "w200",          # price / 1400-day SMA (200-week MA)
    "mayer": "mayer",        # price / 200-day SMA
    "ma2y": "ma2y",          # price / 730-day SMA
    "dd": "dd",              # price / running ATH - 1
    "plaw": "plaw",          # ln residual from expanding log-log (power-law) fit
    "mvrv": "mvrv",          # market cap / realized cap
    "mvrvz": "mvrvz",        # (MC - RC) / expanding std(MC)
    "puell": "puell",        # issuance USD / 365d mean
    "s2f_fix": "s2f_fix",    # ln(price / PlanB 2019 fixed-coefficient S2F price)
    "s2f_exp": "s2f_exp",    # ln(price / expanding-refit S2F price)
    "comp": "comp",          # own composite: mean expanding percentile of 6 components
}

# literature thresholds: (cheap_below, expensive_above); None = no published level used
LIT = {
    "w200": (1.0, None),
    "mayer": (0.8, 2.4),
    "ma2y": (1.0, 5.0),
    "dd": (-0.70, None),
    "mvrv": (1.0, 3.7),
    "mvrvz": (0.0, 7.0),
    "nupl": (0.0, 0.75),      # identical to MVRV < 1 / MVRV > 4
    "puell": (0.5, 4.0),
}
LIT_NOTES = {
    "w200": "price below 200-week MA = bottom zone; folk rule in wide use by 2018-19; no published top level",
    "mayer": "Trace Mayer; 2.4 top level popularised 2017-18, <0.8 commonly cited as undervalued",
    "ma2y": "Philip Swift '2-Year MA Multiplier' (2019): buy below 2yMA, sell above 5x",
    "dd": "folk rule: prior bears fell 77-85% from ATH; -70% used as 'deep bear'; not a published model",
    "mvrv": "Mahmudov & Puell, Oct 2018 (data to Sep 2018): 1 and 3.7",
    "mvrvz": "MVRV Z-score (Awe & Wonder, 2018-19): green < 0, red > 7",
    "nupl": "Adamant Capital / Glassnode 2019: capitulation < 0, euphoria > 0.75",
    "puell": "David Puell, Apr 2019: 0.5 and 4",
    "pi": "Philip Swift, 2019: 111DMA crosses above 2x350DMA",
    "halv": "Molnar 2026 (in-sample by construction): tops 525-546d after halving, lows 364-406d after top",
}

Q_CHEAP = 0.10
Q_EXP = 0.90


def _rolling_mean(x, w):
    out = np.full(len(x), np.nan)
    c = np.cumsum(np.where(np.isnan(x), 0.0, x))
    nn = np.cumsum(~np.isnan(x))
    for_valid = np.arange(len(x)) >= w - 1
    s = c.copy()
    s[w:] = c[w:] - c[:-w]
    k = nn.copy()
    k[w:] = nn[w:] - nn[:-w]
    ok = for_valid & (k == w)
    out[ok] = s[ok] / w
    return out


def _expanding_ols(x, y, min_n):
    """a_t, b_t of y = a + b x fitted on all valid observations with index <= t."""
    ok = ~(np.isnan(x) | np.isnan(y))
    xz = np.where(ok, x, 0.0)
    yz = np.where(ok, y, 0.0)
    n = np.cumsum(ok).astype(float)
    sx, sy = np.cumsum(xz), np.cumsum(yz)
    sxx, sxy = np.cumsum(xz * xz), np.cumsum(xz * yz)
    den = n * sxx - sx * sx
    with np.errstate(divide="ignore", invalid="ignore"):
        b = (n * sxy - sx * sy) / den
        a = (sy - b * sx) / n
    bad = (n < min_n) | ~ok
    a[bad] = np.nan
    b[bad] = np.nan
    return a, b


def _expanding_pct(x, min_n=365):
    """Share of valid values with index <= t that are <= x[t]."""
    out = np.full(len(x), np.nan)
    ok = ~np.isnan(x)
    for t in range(len(x)):
        if not ok[t]:
            continue
        v = x[: t + 1][ok[: t + 1]]
        if len(v) >= min_n:
            out[t] = np.mean(v <= x[t])
    return out


def _rolling_pct(x, w, min_n=730):
    out = np.full(len(x), np.nan)
    ok = ~np.isnan(x)
    for t in range(len(x)):
        if not ok[t]:
            continue
        lo = max(0, t - w + 1)
        v = x[lo: t + 1][ok[lo: t + 1]]
        if len(v) >= min_n:
            out[t] = np.mean(v <= x[t])
    return out


def _expanding_std(x):
    ok = ~np.isnan(x)
    xz = np.where(ok, x, 0.0)
    n = np.cumsum(ok).astype(float)
    s, ss = np.cumsum(xz), np.cumsum(xz * xz)
    with np.errstate(divide="ignore", invalid="ignore"):
        var = (ss - s * s / n) / (n - 1)
    var[n < 2] = np.nan
    return np.sqrt(np.maximum(var, 0))


def load_long(end_date=None):
    df = pl.read_parquet(LONG_PATH).sort("date")
    if end_date is not None:
        df = df.filter(pl.col("date") <= end_date)
    return df


def compute_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """All indicator values as of the close of each day. Purely backward-looking."""
    dates = df["date"].to_list()
    n = len(dates)
    p = df["PriceUSD"].to_numpy().astype(float)
    mc = df["CapMrktCurUSD"].to_numpy().astype(float).copy()
    mv = df["CapMVRVCur"].to_numpy().astype(float).copy()
    sply = df["SplyCur"].to_numpy().astype(float).copy()
    iss_usd = df["IssTotUSD"].to_numpy().astype(float).copy()

    # ---- on-chain extension after the last Coin Metrics day (approximation, flagged) ----
    have = ~np.isnan(mv)
    last = int(np.max(np.where(have)[0])) if have.any() else -1
    approx = np.zeros(n, dtype=bool)
    if 0 <= last < n - 1:
        approx[last + 1:] = True
        rp_last = p[last] / mv[last]                      # realized price frozen at last known value
        k = np.arange(1, n - last)
        sply[last + 1:] = sply[last] + 450.0 * k           # 144 blocks x 3.125 BTC
        iss_usd[last + 1:] = 450.0 * p[last + 1:]
        mc[last + 1:] = sply[last + 1:] * p[last + 1:]
        mv[last + 1:] = p[last + 1:] / rp_last

    out = {"date": dates, "price": p, "onchain_approx": approx}

    # ---- price-only ----
    ma200 = _rolling_mean(p, 200)
    ma730 = _rolling_mean(p, 730)
    ma1400 = _rolling_mean(p, 1400)
    ma111 = _rolling_mean(p, 111)
    ma350 = _rolling_mean(p, 350)
    out["ma200d"] = ma200
    out["ma2y_line"] = ma730
    out["ma200w"] = ma1400
    out["mayer"] = p / ma200
    out["ma2y"] = p / ma730
    out["w200"] = p / ma1400
    out["pi"] = ma111 / (2.0 * ma350)
    ath = np.maximum.accumulate(p)
    out["dd"] = p / ath - 1.0

    # power law: ln P = a + b ln(days since genesis), expanding refit
    tdays = np.array([(d - GENESIS).days for d in dates], dtype=float)
    x, y = np.log(tdays), np.log(p)
    a, b = _expanding_ols(x, y, 365)
    fit = a + b * x
    out["plaw_fit_price"] = np.exp(fit)
    out["plaw_b"] = b
    out["plaw"] = y - fit
    # rainbow-style: percentile of today's residual among residuals of all past days under today's fit
    plp = np.full(n, np.nan)
    for t in range(n):
        if np.isnan(a[t]):
            continue
        r = y[: t + 1] - (a[t] + b[t] * x[: t + 1])
        plp[t] = np.mean(r <= r[-1])
    out["plaw_pct"] = plp

    # halving clock
    hs = np.full(n, np.nan)
    for i, d in enumerate(dates):
        prev = [h for h in HALVINGS if h <= d]
        if prev:
            hs[i] = (d - prev[-1]).days
    out["halv"] = hs

    # ---- on-chain ----
    rc = mc / mv
    out["mvrv"] = mv
    out["realized_price"] = p / mv
    out["mvrvz"] = (mc - rc) / _expanding_std(mc)
    out["nupl"] = 1.0 - 1.0 / mv
    out["puell"] = iss_usd / _rolling_mean(iss_usd, 365)

    flow = np.full(n, np.nan)
    flow[365:] = sply[365:] - sply[:-365]
    sf = sply / flow
    out["sf"] = sf
    lsf, lmc = np.log(sf), np.log(mc)
    s2f_fix_price = np.exp(14.6) * sf ** 3.3 / sply       # PlanB, 22 Mar 2019
    out["s2f_fix_price"] = s2f_fix_price
    out["s2f_fix"] = np.log(p / s2f_fix_price)
    a2, b2 = _expanding_ols(lsf, lmc, 365)
    s2f_exp_price = np.exp(a2 + b2 * lsf) / sply
    out["s2f_exp_price"] = s2f_exp_price
    out["s2f_exp_b"] = b2
    out["s2f_exp"] = np.log(p / s2f_exp_price)

    # ---- own composite (CBBI-like, but causal): mean expanding percentile of 6 components ----
    comps = [out["mayer"], out["ma2y"], out["mvrv"], out["puell"], out["plaw"], out["dd"]]
    ranks = np.vstack([_expanding_pct(c) for c in comps])
    comp = np.where(np.isnan(ranks).any(axis=0), np.nan, ranks.mean(axis=0))
    out["comp"] = comp

    # ---- adaptive variants: rolling 4-year percentile rank ----
    out["mvrv_r4y"] = _rolling_pct(out["mvrv"], 1460)
    out["mayer_r4y"] = _rolling_pct(out["mayer"], 1460)

    return pl.DataFrame(out)


def lag1(flag):
    f = np.asarray(flag, dtype=bool)
    out = np.zeros(len(f), dtype=bool)
    out[1:] = f[:-1]
    return out


def cal_quantiles(ind: pl.DataFrame, col, qs):
    sub = ind.filter((pl.col("date") >= CAL_START) & (pl.col("date") <= CAL_END))[col].to_numpy()
    sub = sub[~np.isnan(sub)]
    return {q: float(np.quantile(sub, q)) for q in qs}


def halving_flags(hs, kind):
    if kind == "lit":      # Molnar-style windows, in-sample by construction
        exp = (hs >= 500) & (hs <= 570)
        cheap = (hs >= 850) & (hs <= 1000)
    else:                  # cal17: 2013/2017 tops at day 371/526, 2015 low at day 777
        exp = (hs >= 340) & (hs <= 560)
        cheap = (hs >= 690) & (hs <= 870)
    return np.nan_to_num(cheap, nan=0).astype(bool), np.nan_to_num(exp, nan=0).astype(bool)


def build_flags(ind: pl.DataFrame):
    """Returns dict name -> dict(cheap=bool array or None, exp=bool array or None, meta) ; all lagged one day."""
    g = {c: ind[c].to_numpy() for c in ind.columns if c not in ("date",)}
    flags, thr = {}, {}

    def lt(x, v):
        return np.where(np.isnan(x), False, x < v)

    def gt(x, v):
        return np.where(np.isnan(x), False, x > v)

    # literature thresholds
    for k, (c, e) in LIT.items():
        x = g[k]
        flags[f"{k}|lit"] = dict(cheap=lag1(lt(x, c)) if c is not None else None,
                                 exp=lag1(gt(x, e)) if e is not None else None)
        thr[f"{k}|lit"] = dict(cheap_below=c, exp_above=e, source=LIT_NOTES[k])
    flags["pi|lit"] = dict(cheap=None, exp=lag1(gt(g["pi"], 1.0) | (g["pi"] == 1.0)))
    thr["pi|lit"] = dict(cheap_below=None, exp_above=1.0, source=LIT_NOTES["pi"])
    ch, ex = halving_flags(g["halv"], "lit")
    flags["halv|lit"] = dict(cheap=ch, exp=ex)       # calendar: known in advance, no lag needed
    thr["halv|lit"] = dict(cheap_window=[850, 1000], exp_window=[500, 570], source=LIT_NOTES["halv"])
    ch, ex = halving_flags(g["halv"], "cal17")
    flags["halv|cal17"] = dict(cheap=ch, exp=ex)
    thr["halv|cal17"] = dict(cheap_window=[690, 870], exp_window=[340, 560],
                             source="2013/2017 tops at day 371/526 and 2015 low at day 777 after halving, padded; n=2 tops, 1 low")

    # thresholds calibrated on 2011-01-01..2017-12-31 only (10th / 90th percentile)
    for k in CONT:
        q = cal_quantiles(ind, k, [Q_CHEAP, Q_EXP])
        flags[f"{k}|cal17"] = dict(cheap=lag1(lt(g[k], q[Q_CHEAP])), exp=lag1(gt(g[k], q[Q_EXP])))
        thr[f"{k}|cal17"] = dict(cheap_below=q[Q_CHEAP], exp_above=q[Q_EXP],
                                 source="10th/90th percentile of 2011-01-01..2017-12-31 values")

    # fully adaptive: expanding / rolling percentile, levels fixed a priori at 10% / 90%
    for k in ("plaw_pct", "mvrv_r4y", "mayer_r4y"):
        flags[f"{k}|adapt"] = dict(cheap=lag1(lt(g[k], 0.10)), exp=lag1(gt(g[k], 0.90)))
        thr[f"{k}|adapt"] = dict(cheap_below=0.10, exp_above=0.90,
                                 source="percentile rank within own trailing history (expanding for plaw_pct, 4y rolling otherwise); 10/90 fixed a priori")
    return flags, thr


# ------------------------------------------------------------------ simulator
def simulate(close, buy, sell_frac=None, stake=STAKE, cost=COST):
    """Daily loop. On a day with sell_frac>0 nothing is bought. Returns dict of arrays + scalars."""
    n = len(close)
    if sell_frac is None:
        sell_frac = np.zeros(n)
    btc = 0.0
    proceeds = 0.0
    put = 0.0
    basis = 0.0
    pnl = np.zeros(n)
    risk = np.zeros(n)
    nbuy = 0
    nsell = 0
    first = -1
    for t in range(n):
        f = sell_frac[t]
        if f > 0:
            if btc > 0:
                q = btc * f
                proceeds += q * close[t] * (1 - cost)
                btc -= q
                basis *= (1 - f)
                nsell += 1
        elif buy[t]:
            btc += stake * (1 - cost) / close[t]
            put += stake
            basis += stake
            nbuy += 1
            if first < 0:
                first = t
        pnl[t] = btc * close[t] + proceeds - put
        risk[t] = basis
    return dict(pnl=pnl, risk=risk, nbuy=nbuy, nsell=nsell, put=put, first=first,
                btc_end=btc, proceeds=proceeds)


def metrics(sim):
    pnl, first = sim["pnl"], sim["first"]
    if first < 0:
        return dict(buys=0, sell_days=0, put_in=0.0, net_pnl=0.0, ret=None, sharpe=None, sortino=None,
                    max_dd=0.0, max_at_risk=0.0, btc_value_end=0.0, proceeds=0.0)
    path = pnl[first:]
    d = np.diff(np.concatenate([[0.0], path]))
    sd = d.std(ddof=1)
    dn = np.sqrt(np.mean(np.minimum(d, 0.0) ** 2))
    peak = np.maximum.accumulate(np.concatenate([[0.0], path]))
    dd = (peak - np.concatenate([[0.0], path])).max()
    return dict(buys=int(sim["nbuy"]), sell_days=int(sim["nsell"]), put_in=float(sim["put"]),
                net_pnl=float(pnl[-1]), ret=float(pnl[-1] / sim["put"]),
                sharpe=float(d.mean() / sd * np.sqrt(365)) if sd > 0 else None,
                sortino=float(d.mean() / dn * np.sqrt(365)) if dn > 0 else None,
                max_dd=float(dd), max_at_risk=float(sim["risk"].max()),
                btc_value_end=float(pnl[-1] - sim["proceeds"] + sim["put"]), proceeds=float(sim["proceeds"]))


def per_buy_value(close, sell_frac=None, stake=STAKE, cost=COST):
    """Terminal net PnL of a single $stake buy made at each day's close (lots are independent).
    Days with sell_frac>0 cannot be bought (value 0)."""
    n = len(close)
    if sell_frac is None:
        sell_frac = np.zeros(n)
    # U[t] = terminal $ value per BTC held coming into day t (before day-t selling)
    U = np.zeros(n + 1)
    U[n] = close[-1]
    for t in range(n - 1, -1, -1):
        f = sell_frac[t]
        U[t] = f * close[t] * (1 - cost) + (1 - f) * U[t + 1]
    v = stake * (1 - cost) / close * U[1:] - stake
    v[sell_frac > 0] = 0.0
    return v


def placebo(buy_mask, weight_value, weight_count):
    """All circular shifts of buy_mask. weight_value[d] = PnL of a buy on d if allowed (0 if not allowed);
    weight_count[d] = 1 if a buy on d is allowed. Returns (pnl_k, nbuys_k) for k = 0..n-1 (k=0 is actual)."""
    n = len(buy_mask)
    m = buy_mask.astype(float)
    fm = np.fft.rfft(m)
    pnl = np.fft.irfft(np.conj(fm) * np.fft.rfft(weight_value), n)
    cnt = np.fft.irfft(np.conj(fm) * np.fft.rfft(weight_count.astype(float)), n)
    return pnl, np.rint(cnt)
