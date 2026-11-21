"""Signals, lot simulator and statistics.

Conventions (identical in backtest and paper trading)
- Alternative.me's Fear & Greed value stamped day D is published around 00:00 UTC on D.
- A buy decided on D is filled at the UTC close of D (about 24 hours later).
- A rule on CoinMarketCap's index decides day D on the value stamped D-1. CoinMarketCap describes a daily
  value as the one at 12am UTC and does not say when it is published, so the rule waits a full day.
- Filters built from prices use the close of D-1 only.
- Ticket: 1,000 USD per signal day. Cost: 10 bps per side. Cash earns 0%.
- PnL = BTC value + sale proceeds - dollars put in.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TICKET = 1000.0
FEE = 0.001
DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class Rule:
    """One tradable variant."""

    id: str
    name: str
    threshold: int                  # buy when the index is below this (or equal to it when inclusive)
    inclusive: bool = False          # True: an index exactly at the threshold also buys
    price_filter: str | None = None  # None, "below_ma730" or "mayer_below_0.8"
    sell_all_at: int | None = None   # sell everything when the index is at or above this
    index: str = "alt"               # "alt": Alternative.me's value of the day; "cmc": CoinMarketCap's value of the day before


def rolling_mean(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[w - 1:] = (c[w:] - c[:-w]) / w
    return out


def lag1(flag: np.ndarray) -> np.ndarray:
    out = np.zeros(len(flag), dtype=bool)
    out[1:] = flag[:-1]
    return out


def price_filter(close: np.ndarray, kind: str | None) -> np.ndarray:
    """Boolean array, True where the filter allows a buy. Uses closes up to D-1."""
    if kind is None:
        return np.ones(len(close), dtype=bool)
    if kind == "below_ma730":
        ma = rolling_mean(close, 730)
        raw = np.where(np.isnan(ma), False, close < ma)
    elif kind == "mayer_below_0.8":
        ma = rolling_mean(close, 200)
        raw = np.where(np.isnan(ma), False, close < 0.8 * ma)
    else:
        raise ValueError(f"unknown price filter: {kind}")
    return lag1(raw)


def buy_mask(fng: np.ndarray, close: np.ndarray, rule: Rule) -> np.ndarray:
    below = np.where(np.isnan(fng), False, (fng <= rule.threshold) if rule.inclusive else (fng < rule.threshold))
    return below & price_filter(close, rule.price_filter)


def simulate(close: np.ndarray, buy: np.ndarray, sell: np.ndarray | None = None,
             ticket: float = TICKET, fee: float = FEE) -> dict[str, np.ndarray]:
    """Daily loop. Returns cumulative PnL, BTC held, market value and trade count per day."""
    n = len(close)
    btc = proceeds = put_in = 0.0
    cum = np.zeros(n)
    pos = np.zeros(n)
    trades = np.zeros(n, dtype=np.int32)
    bought = np.zeros(n, dtype=bool)
    for t in range(n):
        if sell is not None and sell[t]:
            if btc > 0:                      # nothing is bought on a sell day
                proceeds += btc * close[t] * (1 - fee)
                btc = 0.0
                trades[t] += 1
        elif buy[t]:
            btc += ticket * (1 - fee) / close[t]
            put_in += ticket
            trades[t] += 1
            bought[t] = True
        cum[t] = btc * close[t] + proceeds - put_in
        pos[t] = btc
    return {"cum_pnl": cum, "btc": pos, "value": pos * close, "trades": trades, "bought": bought}


def run_rule(fng: np.ndarray, close: np.ndarray, rule: Rule, active: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Simulate one rule. `active` limits the days on which buys are allowed (used to start paper trading flat)."""
    buy = buy_mask(fng, close, rule)
    if active is not None:
        buy = buy & active
    sell = None
    if rule.sell_all_at is not None:
        sell = np.where(np.isnan(fng), False, fng >= rule.sell_all_at)
        if active is not None:
            sell = sell & active
    return simulate(close, buy, sell)


def stats(daily_pnl: np.ndarray, days_per_year: int = DAYS_PER_YEAR) -> dict[str, float | None]:
    """PnL, Sharpe, Sortino (annualised, zero risk-free rate) and max drawdown of cumulative PnL."""
    d = np.asarray(daily_pnl, dtype=float)
    if len(d) == 0:
        return {"pnl": 0.0, "sharpe": None, "sortino": None, "max_dd": 0.0}
    cum = np.cumsum(d)
    sd = d.std(ddof=1) if len(d) > 1 else 0.0
    down = float(np.sqrt(np.mean(np.minimum(d, 0.0) ** 2)))
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    return {
        "pnl": float(cum[-1]),
        "sharpe": float(d.mean() / sd * np.sqrt(days_per_year)) if sd > 0 else None,
        "sortino": float(d.mean() / down * np.sqrt(days_per_year)) if down > 0 else None,
        "max_dd": float((peak - np.concatenate([[0.0], cum])).max()),
    }


def sharpe_per_dollar(daily_pnl: np.ndarray, value: np.ndarray, days_per_year: int = DAYS_PER_YEAR) -> float | None:
    """Sharpe of the daily return on money at risk: pnl[t] / market value at the close of t-1."""
    prev = np.concatenate([[0.0], value[:-1]])
    r = np.where(prev > 0, daily_pnl / np.where(prev > 0, prev, 1.0), 0.0)[1:]
    if len(r) < 2 or r.std(ddof=1) == 0:
        return None
    return float(r.mean() / r.std(ddof=1) * np.sqrt(days_per_year))


def placebo_p(close: np.ndarray, buy: np.ndarray, ticket: float = TICKET, fee: float = FEE) -> float | None:
    """Hold-only rules: share of circular date-shifts of the buy days that end with at least as much PnL."""
    if not buy.any():
        return None
    value = ticket * (1 - fee) / close * close[-1] - ticket     # end PnL of one buy made on each day
    n = len(close)
    shifted = np.fft.irfft(np.conj(np.fft.rfft(buy.astype(float))) * np.fft.rfft(value), n)
    return float((shifted >= shifted[0] - 1e-6).mean())
