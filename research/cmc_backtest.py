"""The sell-at-80 rules on CoinMarketCap's Fear and Greed index, next to Alternative.me's, over the days both exist.

    python research/cmc_backtest.py [path to cmc_fng_daily.csv]

Every book starts flat on the first day CoinMarketCap has a value. Same engine, ticket and costs as the published strategies.
Three ways to read the index on day D (the buy or sale is always filled at the UTC close of D):

    alt        Alternative.me's value dated D, published around 00:00 UTC on D. This is the published strategy's convention.
    cmc_same   CoinMarketCap's value dated D. Usable only if that value is fixed before the close of D.
    cmc_next   CoinMarketCap's value dated D-1. Always usable: the day it describes is over.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import polars as pl

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fng import data, engine  # noqa: E402

RULES = [engine.Rule("le10_sell80", "10 or lower, sell all at 80", 10, inclusive=True, sell_all_at=80),
         engine.Rule("le15_sell80", "15 or lower, sell all at 80", 15, inclusive=True, sell_all_at=80)]


def episodes(dates: list, flags: np.ndarray, close: np.ndarray, gap: int = 3) -> list[dict]:
    """Runs of buy days no more than `gap` days apart."""
    out, run = [], []
    for i in np.flatnonzero(flags):
        if run and (dates[i] - dates[run[-1]]).days > gap:
            out.append(run); run = []
        run.append(int(i))
    if run:
        out.append(run)
    return [{"from": str(dates[r[0]]), "to": str(dates[r[-1]]), "buys": len(r), "avg_price": round(float(len(r) / np.sum(1 / close[r])), 0)} for r in out]


def one(name: str, index: np.ndarray, close: np.ndarray, dates: list, rule: engine.Rule) -> dict:
    sim = engine.run_rule(index, close, rule)
    pnl = np.diff(np.concatenate([[0.0], sim["cum_pnl"]]))
    st = engine.stats(pnl)
    sold = np.flatnonzero((sim["trades"] > 0) & ~sim["bought"])
    put_in = float(sim["bought"].sum() * engine.TICKET)
    open_buys = int(sim["bought"][sold[-1] + 1:].sum()) if len(sold) else int(sim["bought"].sum())
    return {"index": name, "rule": rule.id, "buy_days": int(sim["bought"].sum()), "put_in": put_in,
            "sales": [{"date": str(dates[i]), "price": round(float(close[i]), 0)} for i in sold],
            "pnl": round(st["pnl"], 0), "pnl_pct_of_put_in": round(100 * st["pnl"] / put_in, 1) if put_in else None,
            "sharpe": None if st["sharpe"] is None else round(st["sharpe"], 2), "sortino": None if st["sortino"] is None else round(st["sortino"], 2),
            "sharpe_per_dollar": (lambda v: None if v is None else round(v, 2))(engine.sharpe_per_dollar(pnl, sim["value"])),
            "max_dd": round(st["max_dd"], 0), "max_at_risk": round(float(sim["value"].max()), 0),
            "open_lots": open_buys, "open_value": round(float(sim["value"][-1]), 0),
            "open_avg_cost": round(float(open_buys * engine.TICKET * (1 - engine.FEE) / sim["btc"][-1]), 0) if sim["btc"][-1] > 0 else None,
            "episodes": episodes(dates, sim["bought"], close)}


def main() -> int:
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "cmc_snapshot.csv"
    raw = pl.read_csv(path, schema_overrides={"date": pl.Date})
    cmc = raw.select("date", pl.col("cmc" if "cmc" in raw.columns else "value").cast(pl.Float64).alias("cmc")).unique("date").sort("date")
    inputs = data.load_inputs(ROOT / "data").select("date", "fng", "close")
    first = cmc["date"].min()
    df = inputs.filter(pl.col("date") >= first).join(cmc, on="date", how="left").sort("date")
    dates, close = df["date"].to_list(), df["close"].to_numpy().astype(float)
    alt = df["fng"].cast(pl.Float64).to_numpy()
    same = df["cmc"].to_numpy().astype(float)                           # NaN where CoinMarketCap has no value: no signal that day
    nxt = np.concatenate([[np.nan], same[:-1]])
    both = ~np.isnan(same) & ~np.isnan(alt)
    report = {"window": [str(dates[0]), str(dates[-1])], "days": len(dates), "cmc_missing_days": int(np.isnan(same).sum()),
              "btc_first_close": round(float(close[0]), 0), "btc_last_close": round(float(close[-1]), 0),
              "correlation": round(float(np.corrcoef(same[both], alt[both])[0, 1]), 3), "mean_cmc_minus_alt": round(float((same[both] - alt[both]).mean()), 1),
              "min": {"cmc": [float(np.nanmin(same)), str(dates[int(np.nanargmin(same))])], "alt": [float(np.nanmin(alt)), str(dates[int(np.nanargmin(alt))])]},
              "max": {"cmc": [float(np.nanmax(same)), str(dates[int(np.nanargmax(same))])], "alt": [float(np.nanmax(alt)), str(dates[int(np.nanargmax(alt))])]},
              "days_at_or_below": {str(k): {"cmc": int((same <= k).sum()), "alt": int((alt <= k).sum()), "both": int(((same <= k) & (alt <= k)).sum())} for k in (10, 15, 20)},
              "days_at_or_above_80": {"cmc": int((same >= 80).sum()), "alt": int((alt >= 80).sum())},
              "runs": [one(n, x, close, dates, r) for r in RULES for n, x in (("alt", alt), ("cmc_same", same), ("cmc_next", nxt))]}
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}, indent=1))
    for r in report["runs"]:
        print(json.dumps({k: v for k, v in r.items() if k != "episodes"}))
        print("   episodes:", "; ".join(f"{e['from']}..{e['to']} x{e['buys']} @{e['avg_price']:.0f}" for e in r["episodes"]) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
