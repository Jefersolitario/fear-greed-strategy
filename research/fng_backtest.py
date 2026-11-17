"""Backtest: buy $1,000 of BTC on every day the Crypto Fear & Greed Index reads under a threshold.
Runs the whole study twice: threshold 20 and threshold 10.

Usage:  python fng_backtest.py daily.parquet build_data.py out_dir

Conventions
  * Index value stamped day D is published ~00:00 UTC on D, so it is known all of day D.
  * Buys fill at the UTC close of day D (up to 24h after publication: no look-ahead).
  * Index-based exits fill at the close of the day the reading is published.
  * Per-lot take-profit fills at the target (resting limit); stops and time exits at the close.
  * 200-day-average exit: cross-down seen at close t-1, sold at close t.
  * 10 bps cost on every buy and sell. Sale proceeds sit in cash at 0%.
  * PnL_t = BTC value + cumulative sale proceeds - cumulative dollars put in.
  * Sharpe / Sortino: daily $ PnL changes from the first buy, annualised with sqrt(365), rf = 0.
    "tw" versions: daily return on the BTC actually held (time-weighted), flat days = 0.
"""
import json
import sys
from datetime import datetime, timezone

import numpy as np
import polars as pl
from scipy.optimize import brentq

DATA, BUILD_SRC, OUT_DIR = sys.argv[1], sys.argv[2], sys.argv[3]
THRESHOLDS, TICKET, FEE, ANN = (20, 10), 1000.0, 0.0010, 365

raw = pl.read_parquet(DATA).filter(pl.col("close").is_not_null()).sort("date")
dates = raw["date"].to_numpy()
dstr = [str(d)[:10] for d in dates]
px = raw["close"].to_numpy().astype(float)
fng_raw = raw["fng"].to_numpy().astype(float)  # nan on the 4 days the publisher skipped
fng_ff = raw["fng"].fill_null(strategy="forward").to_numpy().astype(float)
yrs = raw["date"].dt.year().to_numpy()
N = len(px)
inv_px = (1 - FEE) / px
sma200 = raw.select(pl.col("close").rolling_mean(200)).to_series().to_numpy()

EXITS = [  # id, label, rule, param
    ("hold", "Hold, never sell", None, None),
    ("trim_05", "Trim 0.5% of holdings a day while index is 80+", "fng_trim", (80, 0.005)),
    ("trim_1", "Trim 1% a day while index is 80+", "fng_trim", (80, 0.01)),
    ("trim_2", "Trim 2% a day while index is 80+", "fng_trim", (80, 0.02)),
    ("sell80", "Sell everything when index hits 80", "fng_all", 80),
    ("sell90", "Sell everything when index hits 90", "fng_all", 90),
    ("tp100", "Sell each lot at +100%", "tp", 1.0),
    ("tp200", "Sell each lot at +200%", "tp", 2.0),
    ("time365", "Sell each lot after 365 days", "time", 365),
    ("time730", "Sell each lot after 730 days", "time", 730),
    ("sl30", "Stop each lot out at −30%", "sl", 0.30),
    ("sma200", "Sell everything when price breaks its 200‑day average", "sma_cross", None),
]
HOLDS = [("h1", "Next day", 1), ("h30", "30 days", 30), ("h60", "60 days", 60), ("h90", "90 days", 90)]
WINDOWS = [("p2018_2020", "2018-2020", "2018-02-01", "2020-12-31"), ("p2021_2023", "2021-2023", "2021-01-01", "2023-12-31"),
           ("p2024_2026", "2024-2026", "2024-01-01", dstr[-1]), ("p2021_2026", "2021-2026", "2021-01-01", dstr[-1]),
           ("full", "Full sample", dstr[0], dstr[-1])]


def signals(th):
    daily = np.nan_to_num(fng_raw, nan=999) < th
    prev = np.r_[np.nan, fng_ff[:-1]]
    episode = daily & ~(prev < th)  # first day of each spell under the threshold
    weekly = np.zeros(N, bool)  # at most one buy per 7 days while under it
    last = -10**9
    for t in range(N):
        if daily[t] and t - last >= 7:
            weekly[t] = True
            last = t
    return daily, weekly, episode


def simulate(buy_mask, rule=None, param=None, lag_buy=0):
    lots_u, lots_px, lots_t = [], [], []
    contributed, proceeds, units = np.zeros(N), np.zeros(N), np.zeros(N)
    flows, c, p, n_sells = [], 0.0, 0.0, 0
    bm = buy_mask if lag_buy == 0 else np.r_[np.zeros(lag_buy, bool), buy_mask[:-lag_buy]]
    for t in range(N):
        price = px[t]
        if lots_u:
            frac = 0.0
            if rule == "fng_all" and fng_ff[t] >= param:
                frac = 1.0
            elif rule == "fng_trim" and fng_ff[t] >= param[0]:
                frac = param[1]
            elif rule == "sma_cross" and t >= 2 and not np.isnan(sma200[t - 2]) \
                    and px[t - 2] >= sma200[t - 2] and px[t - 1] < sma200[t - 1]:
                frac = 1.0
            if frac > 0:
                got = sum(lots_u) * frac * price * (1 - FEE)
                p += got; flows.append((t, got)); n_sells += 1
                if frac >= 1.0:
                    lots_u, lots_px, lots_t = [], [], []
                else:
                    lots_u = [u * (1 - frac) for u in lots_u]
            if rule in ("tp", "sl", "time"):
                ku, kp, kt = [], [], []
                for u, bp, bt in zip(lots_u, lots_px, lots_t):
                    fill = None
                    if rule == "tp" and price >= bp * (1 + param):
                        fill = bp * (1 + param)
                    elif rule == "sl" and price <= bp * (1 - param):
                        fill = price
                    elif rule == "time" and t - bt >= param:
                        fill = price
                    if fill is None:
                        ku.append(u); kp.append(bp); kt.append(bt)
                    else:
                        got = u * fill * (1 - FEE)
                        p += got; flows.append((t, got)); n_sells += 1
                lots_u, lots_px, lots_t = ku, kp, kt
        if bm[t]:
            lots_u.append(TICKET * (1 - FEE) / price); lots_px.append(price); lots_t.append(t)
            c += TICKET; flows.append((t, -TICKET))
        contributed[t], proceeds[t], units[t] = c, p, sum(lots_u)
    value = units * px
    return dict(contributed=contributed, proceeds=proceeds, units=units, value=value,
                pnl=value + proceeds - contributed, flows=flows, n_buys=int(bm.sum()), n_sells=n_sells)


def xirr(flows, terminal):
    cf = list(flows) + [(N - 1, terminal)]
    t0 = cf[0][0]
    f = lambda r: sum(a / (1 + r) ** ((t - t0) / 365.0) for t, a in cf)
    try:
        return brentq(f, -0.95, 20)
    except ValueError:
        return float("nan")


def metrics(sim):
    pnl = sim["pnl"]
    first = int(np.argmax(sim["contributed"] > 0))
    d = np.diff(pnl[first:])
    sharpe = d.mean() / d.std(ddof=1) * np.sqrt(ANN)
    sortino = d.mean() / np.sqrt(np.mean(np.minimum(d, 0.0) ** 2)) * np.sqrt(ANN)
    seg = pnl[first:]
    dd = seg - np.maximum.accumulate(seg)
    i_tr = int(np.argmin(dd)); i_pk = int(np.argmax(seg[: i_tr + 1]))
    r = np.where(sim["units"][:-1] > 0, px[1:] / px[:-1] - 1, 0.0)[first:]
    nav = np.cumprod(1 + r)
    nav_dd = nav / np.maximum.accumulate(nav) - 1
    j_tr = int(np.argmin(nav_dd)); j_pk = int(np.argmax(nav[: j_tr + 1]))
    uw = pnl / np.where(sim["contributed"] > 0, sim["contributed"], np.nan)
    i_uw = int(np.nanargmin(uw))
    return dict(
        buys=sim["n_buys"], sells=sim["n_sells"],
        invested=float(sim["contributed"][-1]), banked=float(sim["proceeds"][-1]),
        btc_left=float(sim["units"][-1]), end_value=float(sim["value"][-1] + sim["proceeds"][-1]),
        pnl=float(pnl[-1]), roi_pct=float(pnl[-1] / sim["contributed"][-1] * 100),
        irr_pct=float(xirr(sim["flows"], sim["value"][-1]) * 100),
        sharpe=float(sharpe), sortino=float(sortino),
        sharpe_tw=float(r.mean() / r.std(ddof=1) * np.sqrt(ANN)),
        sortino_tw=float(r.mean() / np.sqrt(np.mean(np.minimum(r, 0) ** 2)) * np.sqrt(ANN)),
        max_dd_usd=float(dd.min()), dd_peak=dstr[first + i_pk], dd_trough=dstr[first + i_tr],
        max_dd_pct=float(dd.min() / (sim["contributed"][first + i_pk] + seg[i_pk]) * 100),
        max_dd_tw_pct=float(nav_dd.min() * 100), dd_tw_peak=dstr[first + 1 + j_pk], dd_tw_trough=dstr[first + 1 + j_tr],
        worst_underwater_pct=float(uw[i_uw] * 100), worst_underwater_date=dstr[i_uw],
        peak_pnl=float(pnl.max()), peak_pnl_date=dstr[int(np.argmax(pnl))],
        in_market_pct=float((sim["units"][first:] > 0).mean() * 100),
    )


def placebo(idx, s):
    """p-value: share of circular shifts of the buy pattern that end with at least as much BTC."""
    inv = inv_px[idx]
    actual = (TICKET * inv[s]).sum()
    plac = np.array([(TICKET * inv[np.roll(s, k)]).sum() for k in range(1, len(s))])
    return float((plac >= actual).mean()), float(actual)


def run(th):
    """The whole study for one buy threshold. Every row carries the threshold it belongs to."""
    sig_daily, sig_weekly, sig_episode = signals(th)
    sims = {i: simulate(sig_daily, rule, param) for i, _, rule, param in EXITS}
    res = {i: metrics(s) for i, s in sims.items()}
    hold = res["hold"]
    rules_rows = [dict(threshold=th, id=i, rule=lab, **{k: res[i][k] for k in (
        "pnl", "roi_pct", "irr_pct", "sharpe", "sortino", "sharpe_tw", "sortino_tw", "max_dd_usd", "max_dd_tw_pct", "banked", "btc_left", "sells", "in_market_pct")},
        kept_pct=res[i]["pnl"] / hold["pnl"] * 100) for i, lab, _, _ in EXITS]

    # how a "hit" is counted
    entries_rows = []
    for i, lab, mask in [("daily", f"Every day under {th}", sig_daily),
                         ("weekly", f"At most one buy a week while under {th}", sig_weekly),
                         ("spell", f"First day of each spell under {th}", sig_episode)]:
        m = metrics(simulate(mask))
        entries_rows.append(dict(threshold=th, id=i, entry=lab, **{k: m[k] for k in (
            "buys", "invested", "pnl", "roi_pct", "irr_pct", "max_dd_usd", "worst_underwater_pct")}))

    # benchmark: the same budget spread evenly over every day
    n_sig = int(sig_daily.sum()); budget = n_sig * TICKET; per_day = budget / N
    dca_units = np.cumsum(per_day * inv_px)
    dca_pnl = dca_units * px - per_day * np.arange(1, N + 1)
    dd = np.diff(dca_pnl)

    # signal vs even spending vs placebo, inside each window
    period_rows = []
    for pid, lab, a, b in WINDOWS:
        idx = np.where((dates >= np.datetime64(a)) & (dates <= np.datetime64(b)))[0]
        s = sig_daily[idx]; n = int(s.sum())
        if n == 0:
            continue
        u_sig = (TICKET * inv_px[idx][s]).sum(); u_dca = (n * TICKET / len(idx) * inv_px[idx]).sum()
        p, _ = placebo(idx, s)
        period_rows.append(dict(threshold=th, id=pid, period=lab, buys=n, signal_avg_cost=float(n * TICKET / u_sig),
                                even_avg_cost=float(n * TICKET / u_dca),
                                cheaper_pct=float((1 - (n * TICKET / u_sig) / (n * TICKET / u_dca)) * 100),
                                more_btc_pct=float((u_sig / u_dca - 1) * 100), placebo_p=p, placebo_pct=p * 100))
    full = next(r for r in period_rows if r["id"] == "full")
    since21 = next((r for r in period_rows if r["id"] == "p2021_2026"), None)

    # forward returns after a buy day vs any day
    fwd_rows = []
    for h in (30, 90, 180, 365):
        f = np.full(N, np.nan); f[:-h] = px[h:] / px[:-h] - 1
        a = f[sig_daily]; a = a[np.isfinite(a)]; al = f[np.isfinite(f)]
        fwd_rows.append(dict(threshold=th, horizon=f"{h} days", days=h, signal_days=int(len(a)),
                             signal_median_pct=float(np.median(a) * 100), any_median_pct=float(np.median(al) * 100),
                             signal_mean_pct=float(a.mean() * 100), any_mean_pct=float(al.mean() * 100),
                             signal_up_pct=float((a > 0).mean() * 100), any_up_pct=float((al > 0).mean() * 100)))
    f180 = next(r for r in fwd_rows if r["days"] == 180)

    # cohorts by purchase year
    cohort_rows = []
    for y in np.unique(yrs[sig_daily]):
        m = sig_daily & (yrs == y); u = (TICKET * inv_px[m]).sum(); k = int(m.sum())
        cohort_rows.append(dict(threshold=th, year=str(int(y)), buys=k, invested=k * TICKET, avg_cost=float(k * TICKET / u),
                                pnl=float(u * px[-1] - k * TICKET), roi_pct=float((u * px[-1] / (k * TICKET) - 1) * 100),
                                share_of_pnl_pct=float((u * px[-1] - k * TICKET) / hold["pnl"] * 100)))

    def cohort_pnl(lo, hi):
        m = sig_daily & (yrs >= lo) & (yrs <= hi); u = (TICKET * inv_px[m]).sum()
        return float(u * px[-1] - m.sum() * TICKET), int(m.sum())

    early_pnl, early_n = cohort_pnl(2018, 2020)
    late_pnl, late_n = cohort_pnl(2024, 2026)
    roll90 = np.convolve(sig_daily.astype(int), np.ones(90, int), "full")[:N]
    by_year = {int(y): int((sig_daily & (yrs == y)).sum()) for y in np.unique(yrs)}
    busiest_year = max(by_year, key=by_year.get)
    sens = [metrics(simulate(sig_daily, lag_buy=lag))["pnl"] for lag in (1, 2)] + \
           [metrics(simulate(np.r_[sig_daily[1:], False]))["pnl"]]
    i_ath = int(np.argmax(px))
    g80 = np.where(fng_ff >= 80)[0]
    weekly = next(r for r in entries_rows if r["id"] == "weekly")
    last_buy = int(np.where(sig_daily)[0][-1])

    headline = dict(
        threshold=th, start=dstr[0], end=dstr[-1], days=N, last_close=float(px[-1]), last_index=float(fng_ff[-1]),
        buys=hold["buys"], invested=hold["invested"], end_value=hold["end_value"], pnl=hold["pnl"],
        roi_pct=hold["roi_pct"], irr_pct=hold["irr_pct"], btc_held=hold["btc_left"],
        avg_cost=float(hold["invested"] / hold["btc_left"]),
        sharpe=hold["sharpe"], sortino=hold["sortino"], sharpe_tw=hold["sharpe_tw"], sortino_tw=hold["sortino_tw"],
        max_dd_usd=hold["max_dd_usd"], max_dd_pct=hold["max_dd_pct"], dd_peak=hold["dd_peak"], dd_trough=hold["dd_trough"],
        max_dd_tw_pct=hold["max_dd_tw_pct"], dd_tw_peak=hold["dd_tw_peak"], dd_tw_trough=hold["dd_tw_trough"],
        peak_pnl=hold["peak_pnl"], peak_pnl_date=hold["peak_pnl_date"],
        worst_underwater_pct=hold["worst_underwater_pct"], worst_underwater_date=hold["worst_underwater_date"],
        first_buy=dstr[int(np.argmax(sig_daily))], last_buy=dstr[last_buy], last_buy_close=float(px[last_buy]),
        even_pnl=float(dca_pnl[-1]), even_roi_pct=float(dca_pnl[-1] / budget * 100), even_avg_cost=float(budget / dca_units[-1]),
        even_sharpe=float(dd.mean() / dd.std(ddof=1) * np.sqrt(ANN)),
        more_btc_than_even_pct=full["more_btc_pct"], cheaper_than_even_pct=full["cheaper_pct"],
        placebo_p=full["placebo_p"], placebo_pct=full["placebo_pct"],
        cheaper_since_2021_pct=None if since21 is None else since21["cheaper_pct"],
        placebo_since_2021_pct=None if since21 is None else since21["placebo_pct"],
        pnl_2018_2020=early_pnl, buys_2018_2020=early_n, share_pnl_2018_2020_pct=float(early_pnl / hold["pnl"] * 100),
        pnl_2024_2026=late_pnl, buys_2024_2026=late_n, invested_2024_2026=late_n * TICKET,
        max_buys_90d=int(roll90.max()), max_buys_90d_end=dstr[int(np.argmax(roll90))],
        busiest_year=str(busiest_year), busiest_year_buys=by_year[busiest_year],
        years_with_buys=sum(1 for v in by_year.values() if v > 0), years_in_sample=len(by_year),
        timing_sensitivity_pct=float(max(abs(s / hold["pnl"] - 1) for s in sens) * 100),
        weekly_buys=weekly["buys"], weekly_invested=weekly["invested"], weekly_roi_pct=weekly["roi_pct"],
        ath_date=dstr[i_ath], ath_close=float(px[i_ath]), index_at_ath=float(fng_ff[i_ath]),
        last_day_index_80=dstr[g80[-1]], first_80_date=dstr[g80[0]], first_80_close=float(px[g80[0]]),
        median_180d_after_signal_pct=f180["signal_median_pct"], median_180d_any_day_pct=f180["any_median_pct"],
        up_180d_after_signal_pct=f180["signal_up_pct"], up_180d_any_day_pct=f180["any_up_pct"],
        exits_tested=len(rules_rows) - 1,
        exits_beating_hold=sum(1 for r in rules_rows if r["id"] != "hold" and r["pnl"] > hold["pnl"]),
        exits_smaller_drawdown=sum(1 for r in rules_rows if r["id"] != "hold" and r["max_dd_usd"] > hold["max_dd_usd"]),
        best_exit_kept_pct=float(max(r["kept_pct"] for r in rules_rows if r["id"] != "hold")),
        fee_bps=FEE * 1e4, ticket=TICKET,
    )
    # fixed holding periods: every lot is sold at the close h days after it was bought
    buy_idx = np.where(sig_daily)[0]
    gaps = np.diff(buy_idx)
    episodes = int(1 + (gaps > 14).sum())  # runs of buy days separated by more than two weeks
    hold_rows, hold_cols = [], {}
    ep_start = np.r_[0, np.where(gaps > 14)[0] + 1]; ep_end = np.r_[ep_start[1:], len(buy_idx)]
    for hid, lab, h in HOLDS:
        sim = simulate(sig_daily, "time", h)
        m = metrics(sim)
        closed = buy_idx[buy_idx + h <= N - 1]
        ret = px[closed + h] * (1 - FEE) ** 2 / px[closed] - 1  # per lot, after both fees
        open_lots = np.cumsum(sig_daily.astype(int)) - np.cumsum(np.r_[np.zeros(h, int), sig_daily[:-h].astype(int)])
        # placebo: the same buy pattern shifted in time, lots still open at the end marked at the last close
        ret_all = px[np.minimum(np.arange(N) + h, N - 1)] * (1 - FEE) ** 2 / px - 1
        actual = (TICKET * ret_all[sig_daily]).sum()
        plac = np.array([(TICKET * ret_all[np.roll(sig_daily, k)]).sum() for k in range(1, N)])
        hold_rows.append(dict(
            threshold=th, id=hid, hold=lab, days=h, buy_days=int(sig_daily.sum()), episodes=episodes,
            trades=int(len(closed)), open_at_end=int(len(buy_idx) - len(closed)),
            pnl=m["pnl"], sharpe=m["sharpe"], sortino=m["sortino"], sharpe_tw=m["sharpe_tw"], max_dd_usd=m["max_dd_usd"],
            dd_peak=m["dd_peak"], dd_trough=m["dd_trough"],
            # one outcome per episode: the average trade of the lots bought in it (episodes still open are left out)
            episodes_closed=int(sum(1 for a, b in zip(ep_start, ep_end) if buy_idx[b - 1] + h <= N - 1)),
            episodes_won=int(sum(1 for a, b in zip(ep_start, ep_end) if buy_idx[b - 1] + h <= N - 1
                                 and (px[buy_idx[a:b] + h] * (1 - FEE) ** 2 / px[buy_idx[a:b]] - 1).mean() > 0)),
            won_pct=float((ret > 0).mean() * 100), avg_trade_pct=float(ret.mean() * 100), median_trade_pct=float(np.median(ret) * 100),
            worst_trade_pct=float(ret.min() * 100), best_trade_pct=float(ret.max() * 100),
            most_at_risk=float(open_lots.max() * TICKET), pnl_on_most_at_risk_pct=float(m["pnl"] / (open_lots.max() * TICKET) * 100),
            in_market_pct=m["in_market_pct"], any_day_avg_pct=float(ret_all[: N - h].mean() * 100),
            placebo_p=float((plac >= actual).mean()), placebo_pct=float((plac >= actual).mean() * 100)))
        hold_cols[f"{hid}_{th}"] = sim["pnl"]
    hold_rows.append(dict(threshold=th, id="hold", hold="Never sell", days=None, buy_days=int(sig_daily.sum()), episodes=episodes,
                          trades=0, open_at_end=int(sig_daily.sum()), pnl=hold["pnl"], sharpe=hold["sharpe"], sortino=hold["sortino"],
                          sharpe_tw=hold["sharpe_tw"], episodes_closed=None, episodes_won=None, max_dd_usd=hold["max_dd_usd"], dd_peak=hold["dd_peak"], dd_trough=hold["dd_trough"],
                          won_pct=None, avg_trade_pct=None, median_trade_pct=None, worst_trade_pct=None, best_trade_pct=None,
                          most_at_risk=hold["invested"], pnl_on_most_at_risk_pct=hold["roi_pct"], in_market_pct=100.0,
                          any_day_avg_pct=None, placebo_p=full["placebo_p"], placebo_pct=full["placebo_pct"]))
    hold_cols[f"buy{th}"] = sig_daily.astype(int)

    cols = {f"buy{th}": sig_daily.astype(int), f"invested{th}": sims["hold"]["contributed"], f"hold{th}": sims["hold"]["pnl"],
            f"trim{th}": sims["trim_1"]["pnl"], f"sell{th}": sims["sell80"]["pnl"], f"even{th}": dca_pnl}
    return dict(headline=[headline], rules=rules_rows, entries=entries_rows, periods=period_rows,
                forward=fwd_rows, cohorts=cohort_rows, holds=hold_rows), cols, hold_cols


out = {k: [] for k in ("headline", "rules", "entries", "periods", "forward", "cohorts", "holds")}
curve, hold_curve = {}, {}
for th in THRESHOLDS:
    rows_by_set, cols, hcols = run(th)
    for k, v in rows_by_set.items():
        out[k] += v
    curve.update(cols)
    hold_curve.update(hcols)

# hold return by buy threshold
thr_rows = []
for tv in (10, 15, 20, 25, 30):
    mk = np.nan_to_num(fng_raw, nan=999) < tv
    u = (TICKET * inv_px[mk]).sum()
    thr_rows.append(dict(threshold=tv, buys=int(mk.sum()), avg_cost=float(mk.sum() * TICKET / u),
                         roi_pct=float((u * px[-1] / (mk.sum() * TICKET) - 1) * 100)))

curve_rows = []
for t in range(N):
    r = dict(date=dstr[t], close=round(float(px[t]), 2), index=None if np.isnan(fng_raw[t]) else int(fng_raw[t]))
    for k, v in curve.items():
        r[k] = int(v[t]) if k.startswith("buy") else round(float(v[t]))
    curve_rows.append(r)

hold_curve_rows = []
for t in range(N):
    r = dict(date=dstr[t], close=round(float(px[t]), 2), index=None if np.isnan(fng_raw[t]) else int(fng_raw[t]))
    for k, v in hold_curve.items():
        r[k] = int(v[t]) if k.startswith("buy") else round(float(v[t]))
    hold_curve_rows.append(r)


def rnd(rows):
    return [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]


meta = [
    {"label": "fng_backtest.py", "value": open(__file__).read(), "type": "code", "lang": "python"},
    {"label": "build_data.py (builds the daily input table)", "value": open(BUILD_SRC).read(), "type": "code", "lang": "python"},
    {"label": "build_data_v2.py (corrects the closes after 23 May 2026 to midnight UTC)", "value": open(BUILD_SRC.replace("build_data.py", "build_data_v2.py")).read(), "type": "code", "lang": "python"},
    {"label": "Index source", "value": "Alternative.me Crypto Fear & Greed Index, daily, 2018-02-01 onward (two public GitHub copies, identical on their 1,864 overlapping days)"},
    {"label": "Price source", "value": "Coin Metrics community data (PriceUSD, daily UTC close) to 2026-05-23; after that the BTCUSDT 4-hour candle that closes at midnight UTC (the file labels it 00:00 of the next day, because its timestamps run four hours ahead of UTC from 8 May 2025)"},
    {"label": "Run at (UTC)", "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")},
]
files = dict(thresholds=thr_rows, curve=curve_rows, hold_curve=hold_curve_rows, **out)
for name, rows in files.items():
    json.dump({"rows": rnd(rows), "meta": meta}, open(f"{OUT_DIR}/{name}.json", "w"), allow_nan=False, separators=(",", ":"))

for h in rnd(out["headline"]):
    print(json.dumps(h, indent=1))
for name in ("rules", "entries", "thresholds", "periods", "forward", "cohorts"):
    print("\n" + name); [print(" ", r) for r in rnd(files[name])]
