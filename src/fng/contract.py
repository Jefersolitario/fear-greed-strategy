"""The results contract every strategy publishes, so one dashboard can read them all.

Layout under a results root (a folder, gs://bucket/prefix, s3://..., anything fsspec can open):

    index.json                      {"contract_version": 1, "source": ..., "strategies": [ids], "updated_utc": ...}
    backtest_summary.parquet        one row per tested variant
    <strategy_id>/manifest.json     id, name, market, currency, days_per_year, inception dates, code version
    <strategy_id>/daily.parquet     one row per UTC day

daily.parquet columns
    date      Date      UTC day
    mode      String    "backtest", "paper" or "live"
    pnl       Float64   that day's PnL in the manifest currency (not cumulative, not a return)
    capital   Float64   market value of open positions at the close (money at risk); may be null
    n_trades  Int32     fills that day

Daily PnL is the unit because it adds up across strategies and re-bases to any date range.
The dashboard computes every statistic from `pnl`; a strategy never reports its own Sharpe.
"""
from __future__ import annotations

import io
import json

import fsspec
import polars as pl

CONTRACT_VERSION = 1
MODES = ("backtest", "paper", "live")
DAILY_SCHEMA = {"date": pl.Date, "mode": pl.String, "pnl": pl.Float64, "capital": pl.Float64, "n_trades": pl.Int32}
MANIFEST_KEYS = ("id", "name", "market", "currency", "days_per_year", "backtest_start", "paper_start", "description")


def validate_daily(df: pl.DataFrame) -> pl.DataFrame:
    missing = [c for c in DAILY_SCHEMA if c not in df.columns]
    if missing:
        raise ValueError(f"daily table is missing columns: {missing}")
    df = df.select([pl.col(c).cast(t) for c, t in DAILY_SCHEMA.items()]).sort("date")
    if df["date"].is_duplicated().any():
        raise ValueError("daily table has more than one row for a date")
    if df["pnl"].is_null().any() or not df["pnl"].is_finite().all():
        raise ValueError("daily table has missing or non-finite pnl")
    bad = set(df["mode"].unique()) - set(MODES)
    if bad:
        raise ValueError(f"unknown mode values: {bad}")
    return df


def validate_manifest(m: dict) -> dict:
    missing = [k for k in MANIFEST_KEYS if k not in m]
    if missing:
        raise ValueError(f"manifest is missing keys: {missing}")
    return m


def _join(root: str, *parts: str) -> str:
    return "/".join([root.rstrip("/"), *parts])


def write_bytes(uri: str, data: bytes) -> None:
    fs, path = fsspec.core.url_to_fs(uri)
    parent = path.rsplit("/", 1)[0]
    if parent:
        fs.makedirs(parent, exist_ok=True)
    with fs.open(path, "wb") as f:
        f.write(data)


def read_bytes(uri: str) -> bytes | None:
    fs, path = fsspec.core.url_to_fs(uri)
    if not fs.exists(path):
        return None
    with fs.open(path, "rb") as f:
        return f.read()


def write_parquet(uri: str, df: pl.DataFrame) -> None:
    buf = io.BytesIO()
    df.write_parquet(buf)
    write_bytes(uri, buf.getvalue())


def read_parquet(uri: str) -> pl.DataFrame | None:
    raw = read_bytes(uri)
    return None if raw is None else pl.read_parquet(io.BytesIO(raw))


def write_json(uri: str, obj: dict) -> None:
    write_bytes(uri, (json.dumps(obj, indent=2, default=str) + "\n").encode())


def check_append_only(old: pl.DataFrame | None, new: pl.DataFrame, tol: float = 0.01) -> None:
    """Published history must not change: every date already published keeps its mode and its PnL."""
    if old is None or old.height == 0:
        return
    j = old.select("date", pl.col("mode").alias("mode_old"), pl.col("pnl").alias("pnl_old")).join(new, on="date", how="left")
    gone = j.filter(pl.col("pnl").is_null())
    if gone.height:
        raise RuntimeError(f"{gone.height} published days would disappear, first {gone['date'][0]}")
    # a backtest row may become nothing else; a paper row must stay exactly as published
    changed = j.filter(((pl.col("pnl") - pl.col("pnl_old")).abs() > tol) | (pl.col("mode") != pl.col("mode_old")))
    if changed.height:
        raise RuntimeError(f"{changed.height} published days would change, first {changed['date'][0]}: "
                           f"{changed['pnl_old'][0]:.2f} -> {changed['pnl'][0]:.2f}. Re-run with --allow-restate only if this is intended.")


def publish_strategy(root: str, manifest: dict, daily: pl.DataFrame, allow_restate: bool = False) -> None:
    validate_manifest(manifest)
    daily = validate_daily(daily)
    uri = _join(root, manifest["id"], "daily.parquet")
    if not allow_restate:
        check_append_only(read_parquet(uri), daily)
    write_parquet(uri, daily)
    write_json(_join(root, manifest["id"], "manifest.json"), manifest)


def prune_removed(root: str, keep: list[str], allow_restate: bool = False) -> list[str]:
    """Delete the folders of strategies that were published before and are no longer in the portfolio.

    A strategy that already has paper or live days is only removed on purpose (--allow-restate):
    dropping it takes a real record out of the published results.
    """
    raw = read_bytes(_join(root, "index.json"))
    if raw is None:
        return []
    gone = [s for s in json.loads(raw).get("strategies", []) if s not in keep]
    fs, path = fsspec.core.url_to_fs(root)
    for sid in gone:
        old = read_parquet(_join(root, sid, "daily.parquet"))
        if old is not None and (old["mode"] != "backtest").any() and not allow_restate:
            raise RuntimeError(f"{sid} has paper or live days; removing it needs --allow-restate")
        folder = path.rstrip("/") + "/" + sid
        if fs.exists(folder):
            fs.rm(folder, recursive=True)
    return gone


def publish_index(root: str, source: str, strategy_ids: list[str], summary: pl.DataFrame, updated_utc: str, data_through: str) -> None:
    write_parquet(_join(root, "backtest_summary.parquet"), summary)
    write_json(_join(root, "index.json"), {"contract_version": CONTRACT_VERSION, "source": source, "strategies": strategy_ids,
                                           "updated_utc": updated_utc, "data_through": data_through})
