"""Shared code: paced client for Binance's public market-data API, universe rules, cost constants.

Research only. No API key is used anywhere; every request is an unauthenticated GET of public market data.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import io
import json
import os
import threading
import time
import zipfile

import numpy as np

UTC = dt.timezone.utc
SEC, MIN, HOUR, DAY = 1_000, 60_000, 3_600_000, 86_400_000
SEED = 20261122

# ---- costs, bps per side on traded notional (see PRESPEC.md) -------------------------------------------
TAKER_FEE = 5.0          # perpetual taker (Binance USDS-M regular user 5.0, Hyperliquid base tier 4.5)
MAKER_FEE = 2.0          # perpetual maker (Binance 2.0, Hyperliquid 1.5)
SPOT_TAKER_FEE = 10.0    # spot taker, sensitivity
HALF_SPREAD = {1: 2.0, 2: 5.0, 3: 10.0}   # by liquidity tier

# ---- exclusions (base asset names) -----------------------------------------------------------------------
STABLE_FIAT = {
    "USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "UST", "SUSD", "USDS", "USDSB", "PYUSD", "USD1",
    "USDE", "XUSD", "BFUSD", "RLUSD", "USDX", "EURC", "USDD", "AEUR", "EURI", "EUR", "GBP", "AUD", "TRY",
    "BRL", "RUB", "UAH", "NGN", "ZAR", "BIDR", "IDRT", "BKRW", "BVND", "JPY", "ARS", "MXN", "COP", "CZK",
    "PLN", "RON", "FRAX", "LUSD", "GUSD", "HUSD", "USDJ", "USDN", "VAI", "CUSD", "USDK", "TUSDB", "USDG",
    "USD0", "USDY", "GHO", "CRVUSD", "USDF", "USDTB", "EURT", "EURS",
}
WRAPPED_PEGGED = {
    "WBTC", "WBETH", "BETH", "WETH", "WBNB", "BNSOL", "STETH", "WSTETH", "CBETH", "RETH", "PAXG", "XAUT",
    "BTCB", "RENBTC", "HBTC", "TBTC", "CBBTC", "LBTC", "SOLVBTC", "WEETH", "EETH", "JITOSOL", "MSOL",
    "BBSOL", "WBTCB", "SLISBNB", "ASBNB",
}
DYNAMIC_PEG_SD = 8e-4    # hourly log-return standard deviation below this over 30 days: treated as pegged


PEGGED_GROUP = "TRD_GRP_261"   # Binance permission group carried by every tokenized stock or ETF pair and by no coin


def load_pegged_products() -> set[str]:
    """Pairs that the exchange's own metadata marks as tokenized equities (census in out/s0, see s0_info.py).

    They are pegged products, listed from June 2026, and stay out of the coin universe. Empty if no census.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "s0", "usdt_symbols_info.csv")
    out: set[str] = set()
    if os.path.exists(path):
        import csv
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if PEGGED_GROUP in r.get("permissionSets", ""):
                    out.add(r["symbol"])
    return out


_PEGGED: set[str] | None = None


def pegged_products() -> set[str]:
    global _PEGGED
    if _PEGGED is None:
        _PEGGED = load_pegged_products()
    return _PEGGED


def tier_of_rank(rank: int) -> int:
    return 1 if rank <= 10 else (2 if rank <= 30 else 3)


def ms(y, m, d, h=0, mi=0, s=0) -> int:
    return int(dt.datetime(y, m, d, h, mi, s, tzinfo=UTC).timestamp() * 1000)


def iso(t_ms: int) -> str:
    return dt.datetime.fromtimestamp(int(t_ms) / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def exclusion_reason(base: str, all_bases: set[str]) -> str:
    """Name-based exclusions. Empty string means the pair is kept."""
    if base in STABLE_FIAT:
        return "stable_or_fiat"
    if base in WRAPPED_PEGGED:
        return "wrapped_or_pegged"
    if base.endswith("DOWN") and len(base) > 4:
        return "leveraged"
    if base.endswith("UP") and len(base) > 2 and (base[:-2] + "DOWN") in all_bases:
        return "leveraged"
    if base.endswith("BULL") and (base[:-4] + "BEAR") in all_bases:
        return "leveraged"
    if base.endswith("BEAR") and (base[:-4] + "BULL") in all_bases:
        return "leveraged"
    return ""


# ---- configuration ----------------------------------------------------------------------------------------
@dataclasses.dataclass
class Config:
    p1_start: int = ms(2023, 1, 1)             # Part 1 period start
    hourly_start: int = ms(2021, 1, 1)         # Part 2 hourly data start
    first_T: int = ms(2021, 3, 2)              # first formation end / trading start
    split_p1: int = ms(2025, 1, 1)             # Part 1: selection before, evaluation from
    split_p2: int = ms(2024, 1, 1)             # Part 2: windows starting before are selection
    end: int = ms(2026, 11, 22)                # data end, pinned: the last complete UTC day before the first run
    theta_grid: tuple = (0.0040, 0.0050, 0.0060, 0.0075, 0.0100, 0.0125, 0.0150)
    n_random: int = 100
    pre_s: int = 120
    post_s: int = 3600
    formation_days: int = 60
    trading_days: int = 30
    top_n: int = 100
    n_pairs: int = 20
    weight_budget_per_min: int = 3000          # half of the published 6000 request weight per minute
    workers: int = 8
    test: bool = False

    def with_end(self, now_ms: int | None = None) -> "Config":
        if self.end:
            return self
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        return dataclasses.replace(self, end=(now_ms // DAY) * DAY)


def load_config() -> Config:
    """Real configuration, or a tiny synthetic one when BTCALTS_TEST=1 (local tests, no network)."""
    if os.environ.get("BTCALTS_TEST") == "1":
        import fake_binance  # local synthetic market, never used in the workflows
        return fake_binance.test_config()
    cfg = Config()
    fixed_end = os.environ.get("BTCALTS_END_MS")   # pin the data end so that reruns use the same sample
    if fixed_end:
        cfg = dataclasses.replace(cfg, end=int(fixed_end))
    return cfg.with_end()


def make_client(cfg: Config):
    if cfg.test:
        import fake_binance
        return fake_binance.FakeClient()
    return BinanceClient(weight_budget_per_min=cfg.weight_budget_per_min)


# ---- paced client -----------------------------------------------------------------------------------------
class Refused(RuntimeError):
    """The endpoint refused us (403, 451, 418 or persistent 429). We record it and do not work around it."""


class Pacer:
    """Token bucket in request-weight units, shared by all threads."""

    def __init__(self, weight_per_min: float):
        self.rate = weight_per_min / 60.0
        self.capacity = max(20.0, weight_per_min / 12.0)   # at most 5 seconds of burst
        self.tokens = self.capacity
        self.t = time.monotonic()
        self.lock = threading.Lock()
        self.pause_until = 0.0

    def acquire(self, weight: float) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                if now < self.pause_until:
                    wait = self.pause_until - now
                else:
                    self.tokens = min(self.capacity, self.tokens + (now - self.t) * self.rate)
                    self.t = now
                    if self.tokens >= weight:
                        self.tokens -= weight
                        return
                    wait = (weight - self.tokens) / self.rate
            time.sleep(min(max(wait, 0.01), 5.0))

    def pause(self, seconds: float) -> None:
        with self.lock:
            self.pause_until = max(self.pause_until, time.monotonic() + seconds)
            self.tokens = 0.0


class BinanceClient:
    BASE = "https://data-api.binance.vision"
    BULK = "https://data.binance.vision"
    UA = "btc-alts-research/1.0 (public market data study; GitHub Actions; python-requests)"

    def __init__(self, weight_budget_per_min: int = 3000, published_limit: int = 6000):
        import requests
        self._requests = requests
        self.pacer = Pacer(weight_budget_per_min)
        self.bulk_pacer = Pacer(1200)          # bulk host: at most 20 small files per second
        self.published_limit = published_limit
        self.local = threading.local()
        self.lock = threading.Lock()
        self.stats = {"calls": 0, "weight": 0, "status": {}, "max_used_weight_1m": 0, "retries": 0,
                      "bulk_calls": 0, "bulk_status": {}}
        self.refused: dict[str, str] = {}

    def _session(self):
        s = getattr(self.local, "s", None)
        if s is None:
            s = self._requests.Session()
            s.headers.update({"User-Agent": self.UA, "Accept": "application/json"})
            self.local.s = s
        return s

    def _count(self, key: str, status) -> None:
        with self.lock:
            d = self.stats[key]
            d[str(status)] = d.get(str(status), 0) + 1

    def get(self, path: str, params: dict | None = None, weight: int = 2):
        """GET a public endpoint. Returns parsed JSON, or None for an unknown symbol (HTTP 400)."""
        if path in self.refused:
            raise Refused(f"{path}: {self.refused[path]}")
        url = self.BASE + path
        n429 = 0
        for attempt in range(8):
            self.pacer.acquire(weight)
            try:
                r = self._session().get(url, params=params, timeout=30)
            except self._requests.RequestException as e:   # network error: back off and retry
                with self.lock:
                    self.stats["retries"] += 1
                time.sleep(min(2 ** attempt, 30))
                last = repr(e)
                continue
            with self.lock:
                self.stats["calls"] += 1
                self.stats["weight"] += weight
            self._count("status", r.status_code)
            used = r.headers.get("x-mbx-used-weight-1m")
            if used is not None:
                used = int(used)
                with self.lock:
                    self.stats["max_used_weight_1m"] = max(self.stats["max_used_weight_1m"], used)
                if used > 0.75 * self.published_limit:      # someone else on this IP, or we are too fast
                    self.pacer.pause(20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 400:
                return None
            if r.status_code in (429, 418):
                retry_after = float(r.headers.get("Retry-After", "60"))
                n429 += 1
                if r.status_code == 418 or n429 >= 3:
                    self.refused[path] = f"HTTP {r.status_code} (rate limit), Retry-After {retry_after}"
                    raise Refused(f"{path}: {self.refused[path]}")
                self.pacer.pause(retry_after + 1)
                continue
            if r.status_code in (403, 451):
                self.refused[path] = f"HTTP {r.status_code}"
                raise Refused(f"{path}: HTTP {r.status_code}")
            last = f"HTTP {r.status_code}"
            with self.lock:
                self.stats["retries"] += 1
            time.sleep(min(2 ** attempt, 30))
        raise RuntimeError(f"{path} {params}: gave up after retries ({last})")

    # -- endpoints --
    def exchange_info(self):
        return self.get("/api/v3/exchangeInfo", weight=20)

    def book_ticker(self):
        return self.get("/api/v3/ticker/bookTicker", weight=4)

    def ticker_24hr(self):
        return self.get("/api/v3/ticker/24hr", weight=80)

    def depth(self, symbol: str, limit: int = 100):
        """Order book snapshot (bids and asks as [price, quantity] strings)."""
        return self.get("/api/v3/depth", {"symbol": symbol, "limit": limit}, weight=5 if limit <= 100 else 25)

    def klines(self, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int = 1000):
        """Bars with open time in [start_ms, end_ms] (the bar that opens at end_ms is included)."""
        return self.get("/api/v3/klines", {"symbol": symbol, "interval": interval, "startTime": int(start_ms),
                                           "endTime": int(end_ms), "limit": limit}, weight=2)

    def bulk(self, rel_path: str):
        """GET a file from the bulk host. Returns bytes, or None when the file does not exist (404)."""
        if "bulk" in self.refused:
            raise Refused(self.refused["bulk"])
        url = self.BULK + rel_path
        n403 = 0
        for attempt in range(6):
            self.bulk_pacer.acquire(1)
            try:
                r = self._session().get(url, timeout=60)
            except self._requests.RequestException as e:
                time.sleep(min(2 ** attempt, 30))
                last = repr(e)
                continue
            with self.lock:
                self.stats["bulk_calls"] += 1
            self._count("bulk_status", r.status_code)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return None
            if r.status_code in (403, 451, 429, 418):
                n403 += 1
                if n403 >= 2:
                    self.refused["bulk"] = f"bulk host: HTTP {r.status_code}"
                    raise Refused(self.refused["bulk"])
                time.sleep(10)
                continue
            last = f"HTTP {r.status_code}"
            time.sleep(min(2 ** attempt, 30))
        raise RuntimeError(f"{url}: gave up after retries ({last})")


# ---- kline helpers ----------------------------------------------------------------------------------------
KCOLS = ("open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "n_trades",
         "taker_buy_base", "taker_buy_quote")


def klines_to_arrays(rows) -> dict[str, np.ndarray]:
    """Binance kline rows -> dict of numpy arrays (float64, open_time int64)."""
    if not rows:
        return {"open_time": np.zeros(0, np.int64), **{k: np.zeros(0) for k in
                ("open", "high", "low", "close", "volume", "quote_volume", "n_trades", "taker_buy_base",
                 "taker_buy_quote")}}
    a = np.array([r[:11] for r in rows], dtype=np.float64)
    return {"open_time": a[:, 0].astype(np.int64), "open": a[:, 1], "high": a[:, 2], "low": a[:, 3],
            "close": a[:, 4], "volume": a[:, 5], "quote_volume": a[:, 7], "n_trades": a[:, 8],
            "taker_buy_base": a[:, 9], "taker_buy_quote": a[:, 10]}


def fetch_klines_range(client, symbol: str, interval: str, step_ms: int, start_ms: int, end_ms: int):
    """All bars with open time in [start_ms, end_ms), paging forward from the first available bar."""
    rows, cur, last_ms = [], start_ms, end_ms - step_ms
    while cur <= last_ms:
        page = client.klines(symbol, interval, cur, last_ms)
        if not page:
            break
        rows.extend(page)
        nxt = int(page[-1][0]) + step_ms
        if nxt <= cur or len(page) < 1000:
            break
        cur = nxt
    return klines_to_arrays(rows)


def fetch_1s_window(client, symbol: str, start_ms: int, n_seconds: int) -> dict[str, np.ndarray] | None:
    """1-second bars on the full grid start_ms + 1000*k, k < n_seconds.

    close is forward-filled over seconds without a bar (NaN before the first bar); volumes are zero there.
    Returns None for an unknown symbol.
    """
    rows = []
    for k0 in range(0, n_seconds, 1000):
        a = start_ms + k0 * SEC
        b = start_ms + (min(k0 + 1000, n_seconds) - 1) * SEC
        page = client.klines(symbol, "1s", a, b)
        if page is None:
            return None
        rows.extend(page)
    k = klines_to_arrays(rows)
    idx = ((k["open_time"] - start_ms) // SEC).astype(np.int64)
    ok = (idx >= 0) & (idx < n_seconds)
    idx = idx[ok]
    out = {}
    close = np.full(n_seconds, np.nan)
    close[idx] = k["close"][ok]
    have = ~np.isnan(close)
    last = np.where(have, np.arange(n_seconds), -1)
    np.maximum.accumulate(last, out=last)
    out["close"] = np.where(last >= 0, close[np.maximum(last, 0)], np.nan)
    for name in ("quote_volume", "volume", "taker_buy_quote", "taker_buy_base", "n_trades"):
        v = np.zeros(n_seconds)
        v[idx] = k[name][ok]
        out[name] = v
    out["n_bars"] = int(have.sum())
    return out


# ---- hourly panel ---------------------------------------------------------------------------------------
def build_panel(client, symbols: list[str], interval: str, step_ms: int, start_ms: int, end_ms: int,
                workers: int = 8, max_gap: int = 6, log=print):
    """Open, close and quote volume for the symbols on the bar grid [start_ms, end_ms).

    NaN where the pair has no bar. Gaps of at most max_gap bars inside a listing are filled with the last
    close (zero volume); longer gaps stay missing.
    """
    from concurrent.futures import ThreadPoolExecutor
    n_h = (end_ms - start_ms) // step_ms
    op = np.full((n_h, len(symbols)), np.nan, np.float32)
    cl = np.full((n_h, len(symbols)), np.nan, np.float32)
    qv = np.full((n_h, len(symbols)), np.nan, np.float32)
    done = [0]

    def one(j):
        k = fetch_klines_range(client, symbols[j], interval, step_ms, start_ms, end_ms)
        idx = ((k["open_time"] - start_ms) // step_ms).astype(np.int64)
        ok = (idx >= 0) & (idx < n_h)
        op[idx[ok], j] = k["open"][ok]
        cl[idx[ok], j] = k["close"][ok]
        qv[idx[ok], j] = k["quote_volume"][ok]
        done[0] += 1
        if done[0] % 50 == 0:
            log(f"  {interval}: {done[0]}/{len(symbols)} symbols")
        return int(ok.sum())

    with ThreadPoolExecutor(workers) as ex:
        counts = list(ex.map(one, range(len(symbols))))
    filled = fill_short_gaps(op, cl, qv, max_gap=max_gap)
    return {"symbols": list(symbols), "start_ms": int(start_ms), "step_ms": int(step_ms), "n_hours": int(n_h),
            "open": op, "close": cl, "qv": qv, "bars": counts, "filled": filled}


def build_hourly_panel(client, symbols: list[str], start_ms: int, end_ms: int, workers: int = 8, log=print):
    return build_panel(client, symbols, "1h", HOUR, start_ms, end_ms, workers, 6, log)


def fill_short_gaps(op, cl, qv, max_gap: int = 6) -> int:
    """Forward-fill gaps of at most max_gap bars between two existing bars. In place. Returns bars filled."""
    n_h, n_s = cl.shape
    total = 0
    for j in range(n_s):
        have = ~np.isnan(cl[:, j])
        if not have.any():
            continue
        pos = np.flatnonzero(have)
        gaps = np.diff(pos)
        for a, g in zip(pos[:-1][gaps > 1], gaps[gaps > 1]):
            if g - 1 <= max_gap:
                cl[a + 1:a + g, j] = cl[a, j]
                op[a + 1:a + g, j] = cl[a, j]
                qv[a + 1:a + g, j] = 0.0
                total += int(g - 1)
    return total


def save_panel(panel: dict, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, symbols=np.array(panel["symbols"]), start_ms=np.int64(panel["start_ms"]),
                        step_ms=np.int64(panel.get("step_ms", HOUR)), open=panel["open"], close=panel["close"],
                        qv=panel["qv"])
    return panel_digest(panel)


def load_panel(path: str) -> dict:
    z = np.load(path, allow_pickle=False)
    return {"symbols": [str(s) for s in z["symbols"]], "start_ms": int(z["start_ms"]),
            "step_ms": int(z["step_ms"]) if "step_ms" in z.files else HOUR,
            "n_hours": int(z["close"].shape[0]), "open": z["open"], "close": z["close"], "qv": z["qv"]}


def panel_digest(panel: dict) -> str:
    h = hashlib.sha256()
    h.update(",".join(panel["symbols"]).encode())
    for k in ("open", "close", "qv"):
        h.update(np.ascontiguousarray(np.nan_to_num(panel[k], nan=-1.0)).tobytes())
    return h.hexdigest()


# ---- point-in-time universe and beta ----------------------------------------------------------------------
def base_of(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def rank_at(panel: dict, t_ms: int, keep_reason: dict[str, str] | None = None):
    """Liquidity ranking as of the hour boundary at or before t_ms, from data strictly before it.

    Returns a list of dicts (symbol, rank, qv30, sd_hourly) sorted by rank, after exclusions.
    Uses only bars with open time < that hour boundary.
    """
    i1 = int((t_ms - panel["start_ms"]) // HOUR)
    i0 = i1 - 720
    if i0 < 0:
        raise ValueError("ranking needs 30 days of history")
    cl = panel["close"][i0:i1].astype(np.float64)
    qv = panel["qv"][i0:i1].astype(np.float64)
    syms = panel["symbols"]
    bases = {base_of(s) for s in syms}
    qv30 = np.nansum(qv, axis=0)
    active = ~np.isnan(cl[-24:]).all(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.diff(np.log(cl), axis=0)
    n_ret = (~np.isnan(lr)).sum(axis=0)
    sd = np.full(len(syms), np.nan)
    okc = n_ret >= 24
    sd[okc] = np.nanstd(lr[:, okc], axis=0)
    rows = []
    for j in np.argsort(-qv30, kind="stable"):
        s = syms[j]
        if not active[j] or qv30[j] <= 0:
            continue
        if exclusion_reason(base_of(s), bases) or s in pegged_products():
            continue
        if not np.isnan(sd[j]) and sd[j] < DYNAMIC_PEG_SD:
            if keep_reason is not None:
                keep_reason[s] = "dynamic_peg"
            continue
        rows.append({"symbol": s, "rank": len(rows) + 1, "qv30": float(qv30[j]), "sd_hourly": float(sd[j])})
    return rows


def beta_at(panel: dict, symbols: list[str], t_ms: int, ref: str = "BTCUSDT", window: int = 720, min_obs: int = 360):
    """Trailing hourly beta to Bitcoin from bars that closed before the hour that contains t_ms."""
    i1 = int((t_ms - panel["start_ms"]) // HOUR)
    i0 = max(i1 - window - 1, 0)
    col = {s: j for j, s in enumerate(panel["symbols"])}
    with np.errstate(divide="ignore", invalid="ignore"):
        x = np.diff(np.log(panel["close"][i0:i1, col[ref]].astype(np.float64)))
        out = {}
        for s in symbols:
            y = np.diff(np.log(panel["close"][i0:i1, col[s]].astype(np.float64)))
            ok = ~(np.isnan(x) | np.isnan(y))
            if ok.sum() < min_obs:
                out[s] = float("nan")
                continue
            xc = x[ok] - x[ok].mean()
            out[s] = float((xc * (y[ok] - y[ok].mean())).sum() / (xc * xc).sum())
    return out


# ---- small utilities --------------------------------------------------------------------------------------
def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=_jsonable)
        f.write("\n")


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def unzip_single_csv(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return z.read(z.namelist()[0]).decode()


def run_meta(client=None) -> dict:
    import platform
    meta = {"utc": dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "python": platform.python_version(),
            "numpy": np.__version__, "git_sha": os.environ.get("GITHUB_SHA", ""),
            "run_id": os.environ.get("GITHUB_RUN_ID", "")}
    if client is not None and hasattr(client, "stats"):
        meta["api_stats"] = client.stats
        meta["refused"] = getattr(client, "refused", {})
    return meta
