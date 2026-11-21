"""Download the full history of CoinMarketCap's Crypto Fear and Greed index. Research only: the paper-trading job does not use it.

    CMC_API_KEY=... python research/fetch_cmc_fng.py

The key (a free CoinMarketCap API key) is read from the environment, sent in a request header, and never printed or
written to a file. Under research/data/ the script writes:

    cmc_fng_daily.csv       date (UTC), value, classification, and the timestamp exactly as the API gave it
    cmc_fng_raw.json        the API's answers, untouched, so the parsing can be checked
    cmc_fetch_status.txt    one line saying what happened, also when the download failed
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("CMC_BASE", "https://pro-api.coinmarketcap.com/v3/fear-and-greed")   # CMC_BASE: a stand-in server for tests
OUT = pathlib.Path(__file__).resolve().parent / "data"
PAGE = 500                                                              # the most the endpoint returns per call
UTC = dt.timezone.utc


def get(path: str, params: dict, key: str) -> dict:
    url = f"{BASE}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers={"X-CMC_PRO_API_KEY": key, "Accept": "application/json", "User-Agent": "fear-greed-strategy-research"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            message = (json.loads(body).get("status") or {}).get("error_message") or body[:300]
        except ValueError:
            message = body[:300]
        raise RuntimeError(f"HTTP {e.code} from {path}: {message}") from None


def when(stamp) -> dt.datetime:
    """The API has used both unix seconds (as text) and ISO times."""
    text = str(stamp).strip()
    if text.lstrip("-").isdigit():
        seconds = int(text)
        return dt.datetime.fromtimestamp(seconds / 1000 if seconds > 10**11 else seconds, UTC)
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        key = os.environ.get("CMC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("the secret CMC_API_KEY is empty or not set for this repository")
        pages, entries, start = [], [], 1
        while True:
            page = get("historical", {"start": start, "limit": PAGE}, key)
            pages.append(page)
            rows = page.get("data") or []
            entries.extend(rows)
            if len(rows) < PAGE or start > 20_000:
                break
            start += PAGE
            time.sleep(float(os.environ.get("CMC_PAUSE", "2.5")))                                             # the free plan allows 30 calls a minute
        if not entries:
            raise RuntimeError(f"the API answered without data: {json.dumps(pages[0])[:300]}")
        latest = get("latest", {}, key)
        by_day: dict[dt.date, tuple] = {}
        repeats = 0
        for x in entries:
            t = when(x["timestamp"])
            row = (t.date().isoformat(), int(round(float(x["value"]))), str(x.get("value_classification", "")), str(x["timestamp"]), t.strftime("%H:%M"))
            if t.date() in by_day:
                repeats += 1
                if t <= when(by_day[t.date()][3]):
                    continue                                            # keep the later reading of a day
            by_day[t.date()] = row
        ordered = [by_day[d] for d in sorted(by_day)]
        with open(OUT / "cmc_fng_daily.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(("date", "value", "classification", "api_timestamp", "utc_time"))
            w.writerows(ordered)
        (OUT / "cmc_fng_raw.json").write_text(json.dumps({"fetched_utc": now, "historical_pages": pages, "latest": latest}, indent=1), encoding="utf-8")
        hours = sorted({r[4] for r in ordered})
        message = (f"ok {now}: {len(ordered)} days from {ordered[0][0]} to {ordered[-1][0]}, {repeats} repeated dates, "
                   f"stamped at {', '.join(hours[:4])}{' ...' if len(hours) > 4 else ''} UTC; latest {json.dumps(latest.get('data'))[:200]}")
        code = 0
    except Exception as e:  # noqa: BLE001  (the status file must say what went wrong, whatever it was)
        message, code = f"failed {now}: {type(e).__name__}: {e}", 1
    (OUT / "cmc_fetch_status.txt").write_text(message + "\n", encoding="utf-8")
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
