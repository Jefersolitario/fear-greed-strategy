"""Command line: build the backtest, advance the paper ledger and publish the results contract.

    python -m fng.cli run                  recompute from stored inputs, write ./results
    python -m fng.cli run --fetch          first append new complete days from the live sources
    python -m fng.cli run --out gs://bucket/fear-greed-strategy     publish somewhere else (needs gcsfs)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import pathlib
import tomllib

import numpy as np
import polars as pl

from . import contract, data
from .engine import DAYS_PER_YEAR, TICKET, Rule, placebo_p, run_rule, sharpe_per_dollar, stats

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_config(path: pathlib.Path) -> dict:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg["backtest_start"] = dt.date.fromisoformat(cfg["backtest_start"])
    cfg["paper_start"] = dt.date.fromisoformat(cfg["paper_start"])
    cfg["rules"] = [dict(r, rule=Rule(id=r["id"], name=r["name"], threshold=r["threshold"], inclusive=r.get("inclusive", False), price_filter=r.get("price_filter"),
                                      sell_all_at=r.get("sell_all_at"), index=r.get("index", "alt"))) for r in cfg["strategy"]]
    for r in cfg["rules"]:
        r["role"] = r.get("role", "portfolio") if r.get("paper", False) else "tested"
        if r["role"] not in ("portfolio", "monitor", "tested"):
            raise ValueError(f"{r['id']}: role must be 'portfolio' or 'monitor'")
        if r["rule"].index not in ("alt", "cmc"):
            raise ValueError(f"{r['id']}: index must be 'alt' or 'cmc'")
        # a rule may have a shorter history than the others (its index started later) and its own paper start
        r["backtest_start"] = max(cfg["backtest_start"], dt.date.fromisoformat(r["backtest_start"])) if "backtest_start" in r else cfg["backtest_start"]
        r["paper_start"] = dt.date.fromisoformat(r["paper_start"]) if "paper_start" in r else cfg["paper_start"]
        if r["paper_start"] < cfg["paper_start"] or r["paper_start"] <= r["backtest_start"]:
            raise ValueError(f"{r['id']}: paper_start must be after its backtest_start and not before the first paper day, {cfg['paper_start']}")
    return cfg


def code_version() -> str:
    """Fingerprint of the rules and the code. It moves only when they change, not when data or results are committed,
    and it does not depend on git history being present (CI checks out a single commit)."""
    h = hashlib.sha1()
    for f in sorted([*ROOT.glob("src/fng/*.py"), ROOT / "strategies.toml"]):
        h.update(f.name.encode() + b"\0" + f.read_bytes())
    return h.hexdigest()[:10]


def daily_rows(dates: list[dt.date], sim: dict[str, np.ndarray], mode: str, keep: np.ndarray) -> pl.DataFrame:
    """Contract rows for the days in `keep`, starting at the first trade. PnL is re-based inside the kept window."""
    idx = np.where(keep)[0]
    traded = np.where(keep & (sim["trades"] > 0))[0]
    if len(traded) == 0:
        return pl.DataFrame(schema=contract.DAILY_SCHEMA)
    idx = idx[idx >= traded[0]]
    cum = sim["cum_pnl"][idx]
    pnl = np.diff(np.concatenate([[0.0], cum]))
    return pl.DataFrame({"date": [dates[i] for i in idx], "mode": [mode] * len(idx), "pnl": pnl,
                         "capital": sim["value"][idx], "n_trades": sim["trades"][idx]}, schema=contract.DAILY_SCHEMA)


def build(inputs: pl.DataFrame, cfg: dict, cmc: pl.DataFrame | None = None) -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
    """Returns {strategy_id: daily table} for the paper-traded rules and the backtest summary for every rule.
    `cmc` holds CoinMarketCap's daily values by date; without it the rules on that index never trade."""
    df = inputs.sort("date")
    dates = df["date"].to_list()
    close = df["close"].to_numpy().astype(float)
    cmc = pl.DataFrame(schema=data.CMC_SCHEMA) if cmc is None else cmc
    day_before = cmc.select((pl.col("date") + pl.duration(days=1)).alias("date"), "cmc")      # the value dated D-1, placed on day D
    index = {"alt": df["fng"].cast(pl.Float64).to_numpy(),
             "cmc": df.select("date").join(day_before, on="date", how="left").sort("date")["cmc"].cast(pl.Float64).to_numpy()}
    d = np.array([x.toordinal() for x in dates])
    daily, rows = {}, []
    for r in cfg["rules"]:
        rule: Rule = r["rule"]
        fng = index[rule.index]
        in_bt = (d >= r["backtest_start"].toordinal()) & (d < r["paper_start"].toordinal())
        in_paper = d >= r["paper_start"].toordinal()
        bt = run_rule(fng, close, rule, active=in_bt)
        t_bt = daily_rows(dates, bt, "backtest", in_bt)
        s = stats(t_bt["pnl"].to_numpy(), DAYS_PER_YEAR)
        buys = int(bt["bought"].sum())
        put_in = buys * TICKET
        hold_only = rule.sell_all_at is None and buys > 0
        rows.append({
            "strategy_id": rule.id, "name": rule.name, "paper_traded": bool(r.get("paper", False)), "role": r["role"],
            "start": t_bt["date"].min(), "end": t_bt["date"].max(), "buys": buys, "put_in": put_in,
            "pnl": s["pnl"], "return_pct": 100 * s["pnl"] / put_in if put_in else None,
            "sharpe": s["sharpe"], "sortino": s["sortino"], "max_dd": s["max_dd"],
            "sharpe_per_dollar": sharpe_per_dollar(t_bt["pnl"].to_numpy(), t_bt["capital"].to_numpy(), DAYS_PER_YEAR),
            "placebo_p": placebo_p(close[in_bt], bt["bought"][in_bt]) if hold_only else None,
        })
        if r.get("paper", False):
            pp = run_rule(fng, close, rule, active=in_paper)       # paper book starts flat on the rule's paper start
            daily[rule.id] = pl.concat([t_bt, daily_rows(dates, pp, "paper", in_paper)])
    return daily, pl.DataFrame(rows)


def main(argv: list[str] | None = None, session=None, today_utc: dt.date | None = None) -> int:
    """`session` and `today_utc` stand in for the live sources and the clock in tests."""
    ap = argparse.ArgumentParser(prog="fng")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="recompute and publish")
    run.add_argument("--fetch", action="store_true", help="append new complete days from the live sources first")
    run.add_argument("--data", default=str(ROOT / "data"))
    run.add_argument("--config", default=str(ROOT / "strategies.toml"))
    run.add_argument("--out", default=str(ROOT / "results"), help="results root: a folder or any fsspec URI")
    run.add_argument("--allow-restate", action="store_true", help="permit changes to already published days")
    a = ap.parse_args(argv)

    cfg = load_config(pathlib.Path(a.config))
    inputs = data.update_live(a.data, today_utc=today_utc, session=session) if a.fetch else data.load_inputs(a.data)
    daily, summary = build(inputs, cfg, data.load_cmc(a.data))
    version = code_version()
    through = contract.published_through(a.out)                    # what was public before this run
    for r in cfg["rules"]:
        if not r.get("paper", False):
            continue
        rule: Rule = r["rule"]
        manifest = {"id": rule.id, "name": rule.name, "market": "BTC-USD spot", "currency": "USD", "days_per_year": DAYS_PER_YEAR,
                    "backtest_start": r["backtest_start"], "paper_start": r["paper_start"], "description": r.get("description", ""),
                    "ticket_usd": TICKET, "code_version": version, "source_repo": cfg["source"], "role": r["role"],
                    "index": "CoinMarketCap Fear and Greed, value of the day before" if rule.index == "cmc" else "Alternative.me Fear & Greed, value of the day"}
        contract.publish_strategy(a.out, manifest, daily[rule.id], allow_restate=a.allow_restate, through=through)
    for sid in contract.prune_removed(a.out, list(daily), allow_restate=a.allow_restate):
        print(f"{sid}: no longer in the portfolio, published files removed")
    contract.publish_index(a.out, cfg["source"], list(daily), summary,
                           updated_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), data_through=str(inputs["date"].max()))
    with pl.Config(tbl_rows=20, tbl_cols=12, float_precision=2):
        print(summary.select("strategy_id", "paper_traded", "buys", "pnl", "return_pct", "sharpe", "sortino", "max_dd", "placebo_p"))
    for k, t in daily.items():
        p = t.filter(pl.col("mode") == "paper")
        print(f"{k}: {t.height} days published, {p.height} of them paper ({int(p['n_trades'].sum())} paper fills), through {t['date'].max()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
