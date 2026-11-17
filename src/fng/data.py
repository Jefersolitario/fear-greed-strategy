"""Daily inputs: the Fear & Greed index and the BTC/USD UTC daily close.

Three layers, merged in this order and never rewritten:
1. data/inputs_snapshot.csv  frozen history used for the published backtest
2. data/live_daily.csv       days appended by the scheduled job (committed, so the inputs are versioned too)
3. a fresh fetch             only complete UTC days later than the last stored day are appended

A fetched value that disagrees with a stored one stops the run: stored inputs are the record.
"""
from __future__ import annotations

import datetime as dt
import pathlib

import polars as pl

FNG_URL = "https://api.alternative.me/fng/?limit=120&format=json"
COINBASE_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"
SCHEMA = {"date": pl.Date, "fng": pl.Int64, "close": pl.Float64, "close_source": pl.String}
CLOSE_TOLERANCE = 0.015     # venues differ by a few basis points at the close; more than 1.5% means something is wrong
TIMEOUT = 30


def _read(path: pathlib.Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame(schema=SCHEMA)
    return pl.read_csv(path, schema_overrides=SCHEMA).select(list(SCHEMA))


def load_inputs(data_dir: str | pathlib.Path) -> pl.DataFrame:
    d = pathlib.Path(data_dir)
    df = pl.concat([_read(d / "inputs_snapshot.csv"), _read(d / "live_daily.csv")]).sort("date")
    return validate_inputs(df)


def validate_inputs(df: pl.DataFrame) -> pl.DataFrame:
    if df["date"].is_duplicated().any():
        raise ValueError("inputs have duplicate dates")
    gaps = df.filter(pl.col("date").diff().dt.total_days() != 1)
    if gaps.height:
        raise ValueError(f"inputs have a gap before {gaps['date'][0]}")
    if df["close"].is_null().any() or (df["close"] <= 0).any():
        raise ValueError("inputs have a missing or non-positive close")
    f = df.filter(pl.col("fng").is_not_null())
    if ((f["fng"] < 0) | (f["fng"] > 100)).any():
        raise ValueError("Fear & Greed value outside 0-100")
    # The index has a few missing days in its own history. A day without a value is a day
    # without a signal. Live days are only ever appended with both a value and a close (see update_live).
    return df


def fetch_fng(session) -> dict[dt.date, int]:
    r = session.get(FNG_URL, timeout=TIMEOUT)
    r.raise_for_status()
    rows = r.json()["data"]
    out = {dt.datetime.fromtimestamp(int(x["timestamp"]), dt.timezone.utc).date(): int(x["value"]) for x in rows}
    if not out:
        raise RuntimeError("Fear & Greed API returned no rows")
    return out


def _coinbase(session, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    params = {"granularity": 86400, "start": f"{start}T00:00:00Z", "end": f"{end}T00:00:00Z"}
    r = session.get(COINBASE_URL, params=params, timeout=TIMEOUT, headers={"User-Agent": "fear-greed-strategy"})
    r.raise_for_status()
    # rows: [time, low, high, open, close, volume]; time is the start of the UTC day
    return {dt.datetime.fromtimestamp(int(x[0]), dt.timezone.utc).date(): float(x[4]) for x in r.json()}


def _kraken(session, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    since = int(dt.datetime.combine(start, dt.time(), dt.timezone.utc).timestamp()) - 1
    r = session.get(KRAKEN_URL, params={"pair": "XBTUSD", "interval": 1440, "since": since}, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if j.get("error"):
        raise RuntimeError(f"Kraken error: {j['error']}")
    rows = next(v for k, v in j["result"].items() if k != "last")
    # rows: [time, open, high, low, close, vwap, volume, count]
    return {dt.datetime.fromtimestamp(int(x[0]), dt.timezone.utc).date(): float(x[4]) for x in rows}


def fetch_closes(session, start: dt.date, end: dt.date) -> tuple[dict[dt.date, float], str]:
    """Daily closes for start..end inclusive. Coinbase first, Kraken as the fallback."""
    errors = []
    for name, fn in (("coinbase_btcusd", _coinbase), ("kraken_xbtusd", _kraken)):
        try:
            got = {d: c for d, c in fn(session, start, end + dt.timedelta(days=1)).items() if start <= d <= end and c > 0}
            if got:
                return got, name
            errors.append(f"{name}: no rows")
        except Exception as e:  # noqa: BLE001 - try the next venue, report all failures together
            errors.append(f"{name}: {e}")
    raise RuntimeError("no price source answered: " + "; ".join(errors))


def update_live(data_dir: str | pathlib.Path, today_utc: dt.date | None = None, session=None) -> pl.DataFrame:
    """Append every complete UTC day after the last stored one. Returns the full, validated inputs."""
    import requests

    session = session or requests.Session()
    today_utc = today_utc or dt.datetime.now(dt.timezone.utc).date()
    d = pathlib.Path(data_dir)
    have = load_inputs(d)
    last = have["date"].max()
    last_complete = today_utc - dt.timedelta(days=1)          # the close of `today` is not known yet
    if last >= last_complete:
        return have
    overlap_from = last - dt.timedelta(days=5)
    fng = fetch_fng(session)
    closes, source = fetch_closes(session, overlap_from, last_complete)

    # stored days are the record: a fetched value that disagrees stops the run
    for row in have.filter(pl.col("date") >= overlap_from).iter_rows(named=True):
        day = row["date"]
        if day in fng and row["fng"] is not None and fng[day] != row["fng"]:
            raise RuntimeError(f"Fear & Greed for {day} is stored as {row['fng']} but the API now says {fng[day]}")
        if day in closes and abs(closes[day] / row["close"] - 1) > CLOSE_TOLERANCE:
            raise RuntimeError(f"close for {day} is stored as {row['close']:.2f} but {source} says {closes[day]:.2f}")

    new = []
    day = last + dt.timedelta(days=1)
    while day <= last_complete:
        if day not in fng or day not in closes:
            break                                              # never skip a day; the next run catches up
        new.append({"date": day, "fng": fng[day], "close": round(closes[day], 2), "close_source": source})
        day += dt.timedelta(days=1)
    if not new:
        return have
    live = pl.concat([_read(d / "live_daily.csv"), pl.DataFrame(new, schema=SCHEMA)]).sort("date")
    live.write_csv(d / "live_daily.csv")
    return load_inputs(d)
