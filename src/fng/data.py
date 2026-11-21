"""Daily inputs: the two Fear & Greed indexes and the BTC/USD UTC daily close.

Three layers, merged in this order and never rewritten:
1. data/inputs_snapshot.csv  frozen history used for the published backtest
2. data/live_daily.csv       days appended by the scheduled job (committed, so the inputs are versioned too)
3. a fresh fetch             only complete UTC days later than the last stored day are appended

CoinMarketCap's index is kept the same way in data/cmc_snapshot.csv and data/cmc_live.csv. It is read one day
late on purpose: the rule on it decides day D on the value dated D-1, so a day is appended only when that
value is on file.

A fetched value that disagrees with a stored one stops the run: stored inputs are the record.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import time

import polars as pl

FNG_URL = "https://api.alternative.me/fng/?limit=120&format=json"
COINBASE_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"
CMC_URL = "https://pro-api.coinmarketcap.com/public-api/v3/fear-and-greed/historical"   # keyless
CMC_URL_KEYED = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/historical"        # used when CMC_API_KEY is set
SCHEMA = {"date": pl.Date, "fng": pl.Int64, "close": pl.Float64, "close_source": pl.String}
CMC_SCHEMA = {"date": pl.Date, "cmc": pl.Int64}
STALL_DAYS = 3              # complete days that may stay unappended before the run fails instead of waiting
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


def _read_cmc(path: pathlib.Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame(schema=CMC_SCHEMA)
    return pl.read_csv(path, schema_overrides=CMC_SCHEMA).select(list(CMC_SCHEMA))


def load_cmc(data_dir: str | pathlib.Path) -> pl.DataFrame:
    """CoinMarketCap's daily Fear and Greed values by the date they are stamped with: one row per day, no gaps."""
    d = pathlib.Path(data_dir)
    df = pl.concat([_read_cmc(d / "cmc_snapshot.csv"), _read_cmc(d / "cmc_live.csv")]).sort("date")
    if df["date"].is_duplicated().any():
        raise ValueError("CoinMarketCap values have duplicate dates")
    gaps = df.filter(pl.col("date").diff().dt.total_days() != 1)
    if gaps.height:
        raise ValueError(f"CoinMarketCap values have a gap before {gaps['date'][0]}")
    if df["cmc"].is_null().any() or ((df["cmc"] < 0) | (df["cmc"] > 100)).any():
        raise ValueError("CoinMarketCap value missing or outside 0-100")
    return df


def _cmc_day(stamp) -> dt.date:
    """The API has given the time as unix seconds in text and as an ISO time."""
    text = str(stamp).strip()
    if text.isdigit():
        return dt.datetime.fromtimestamp(int(text), dt.timezone.utc).date()
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(dt.timezone.utc).date()


def fetch_cmc(session, limit: int = 90) -> dict[dt.date, int]:
    """The newest daily values of CoinMarketCap's index. Keyless by default; a key in CMC_API_KEY is used if there is one."""
    key = os.environ.get("CMC_API_KEY", "").strip()
    headers = {"Accept": "application/json", "User-Agent": "fear-greed-strategy"}
    if key:
        headers["X-CMC_PRO_API_KEY"] = key
    for attempt in range(4):
        r = session.get(CMC_URL_KEYED if key else CMC_URL, params={"start": 1, "limit": limit}, headers=headers, timeout=TIMEOUT)
        if getattr(r, "status_code", 200) in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(5 * 2 ** attempt)                       # the keyless pool is shared by address: back off and try again
            continue
        r.raise_for_status()
        break
    out = {_cmc_day(x["timestamp"]): int(round(float(x["value"]))) for x in (r.json().get("data") or [])}
    if not out:
        raise RuntimeError("CoinMarketCap returned no Fear and Greed rows")
    return out


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
    cmc_have = load_cmc(d)
    cmc_stored = dict(zip(cmc_have["date"].to_list(), cmc_have["cmc"].to_list()))
    cmc = fetch_cmc(session)

    # stored days are the record: a fetched value that disagrees stops the run
    for row in have.filter(pl.col("date") >= overlap_from).iter_rows(named=True):
        day = row["date"]
        if day in fng and row["fng"] is not None and fng[day] != row["fng"]:
            raise RuntimeError(f"Fear & Greed for {day} is stored as {row['fng']} but the API now says {fng[day]}")
        if day in closes and abs(closes[day] / row["close"] - 1) > CLOSE_TOLERANCE:
            raise RuntimeError(f"close for {day} is stored as {row['close']:.2f} but {source} says {closes[day]:.2f}")
    for day, value in cmc_stored.items():
        if day >= overlap_from and day in cmc and cmc[day] != value:
            raise RuntimeError(f"CoinMarketCap's index for {day} is stored as {value} but the API now says {cmc[day]}")

    cmc_known = set(cmc) | set(cmc_stored)
    cmc_last = max(cmc_stored) if cmc_stored else None
    new, new_cmc, missing = [], [], ""
    day = last + dt.timedelta(days=1)
    while day <= last_complete:
        before = day - dt.timedelta(days=1)
        # every CoinMarketCap value up to the day before must be on file or fetched: the rule on it decides `day` on that value
        backlog = [] if cmc_last is None else [cmc_last + dt.timedelta(days=k) for k in range(1, (before - cmc_last).days + 1)]
        if day not in fng or day not in closes or before not in cmc_known or any(x not in cmc for x in backlog):
            missing = ("Alternative.me's index" if day not in fng else "the close" if day not in closes else "CoinMarketCap's index for the day before")
            break                                              # never skip a day; the next run catches up
        new.append({"date": day, "fng": fng[day], "close": round(closes[day], 2), "close_source": source})
        new_cmc += [{"date": x, "cmc": cmc[x]} for x in backlog]
        cmc_last = before if backlog else cmc_last
        day += dt.timedelta(days=1)
    if not new:
        if (last_complete - last).days >= STALL_DAYS:
            raise RuntimeError(f"no day has been appended since {last}: {missing} is missing for {last + dt.timedelta(days=1)}")
        return have
    if new_cmc:
        pl.concat([_read_cmc(d / "cmc_live.csv"), pl.DataFrame(new_cmc, schema=CMC_SCHEMA)]).sort("date").write_csv(d / "cmc_live.csv")
    live = pl.concat([_read(d / "live_daily.csv"), pl.DataFrame(new, schema=SCHEMA)]).sort("date")
    live.write_csv(d / "live_daily.csv")
    return load_inputs(d)
