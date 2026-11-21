"""Download the full history of CoinMarketCap's Crypto Fear and Greed index. Research only: the paper-trading job does not use it.

    python research/fetch_cmc_fng.py

No key is needed: CoinMarketCap's keyless public API serves this index. If the environment variable CMC_API_KEY holds a
key, the keyed API is used instead; the key is sent in a request header and never printed or written to a file.
Under research/data/ the script writes:

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

KEY = os.environ.get("CMC_API_KEY", "").strip()
HOST = os.environ.get("CMC_HOST", "https://pro-api.coinmarketcap.com")   # CMC_HOST: a stand-in server for tests
BASE = HOST + ("" if KEY else "/public-api") + "/v3/fear-and-greed"      # keyless paths are the keyed ones behind /public-api
OUT = pathlib.Path(__file__).resolve().parent / "data"
PAGE = 500                                                              # the most the keyed endpoint returns per call
PAUSE = float(os.environ.get("CMC_PAUSE", "2.5"))                       # seconds between calls
UTC = dt.timezone.utc


def get(path: str, params: dict) -> dict:
    url = f"{BASE}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Accept": "application/json", "User-Agent": "fear-greed-strategy-research"}
    if KEY:
        headers["X-CMC_PRO_API_KEY"] = KEY
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(PAUSE * 2 ** (attempt + 1))                  # the keyless pool is shared by address: back off and try again
                continue
            try:
                message = (json.loads(body).get("status") or {}).get("error_message") or body[:300]
            except ValueError:
                message = body[:300]
            raise RuntimeError(f"HTTP {e.code} from {path}: {message}") from None
    raise RuntimeError(f"no answer from {path}")


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
        pages, entries, start, seen = [], [], 1, set()
        while len(pages) < 80:
            page = get("historical", {"start": start, "limit": PAGE})
            pages.append(page)
            rows = page.get("data") or []
            fresh = [x for x in rows if str(x["timestamp"]) not in seen]
            if not fresh:
                break                                                   # an empty page, or one that only repeats: the history is complete
            seen.update(str(x["timestamp"]) for x in fresh)
            entries.extend(fresh)
            start += len(rows)                                          # by what came back, in case the page is capped below what was asked
            time.sleep(PAUSE)
        if not entries:
            raise RuntimeError(f"the API answered without data: {json.dumps(pages[0])[:300]}")
        latest = get("latest", {})
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
        message = (f"ok {now} ({'with a key' if KEY else 'keyless'}, {len(pages)} calls): {len(ordered)} days from {ordered[0][0]} to {ordered[-1][0]}, {repeats} repeated dates, "
                   f"stamped at {', '.join(hours[:4])}{' ...' if len(hours) > 4 else ''} UTC; latest {json.dumps(latest.get('data'))[:200]}")
        code = 0
    except Exception as e:  # noqa: BLE001  (the status file must say what went wrong, whatever it was)
        message, code = f"failed {now}: {type(e).__name__}: {e}", 1
    (OUT / "cmc_fetch_status.txt").write_text(message + "\n", encoding="utf-8")
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
