"""Synthetic market for local tests (BTCALTS_TEST=1). Never used in the workflows, never touches the network.

The synthetic world has known properties so that the pipeline can be checked against them:
  - coins C01..C10 follow Bitcoin in the same second, C11..C20 one second late, C21..C35 three seconds late;
  - liquid coins trade every second, illiquid ones in about one second out of five (stale last-trade prices);
  - hourly prices contain three truly cointegrated pairs (C03/C04, C13/C14, C25/C26);
  - a stablecoin, a pegged token missing from the static list, a wrapped token, leveraged tokens, a delisted
    coin, a late listing and a coin with gaps exercise the universe rules.
"""
from __future__ import annotations

import io
import zipfile
import zlib

import numpy as np

from common import DAY, HOUR, MIN, SEC, Config, ms

END = ms(2026, 3, 1)
P1_DAYS = 3
P1_START = END - P1_DAYS * DAY
H_DAYS = 200
H_START = END - H_DAYS * DAY
N_ALT = 35


def test_config() -> Config:
    return Config(p1_start=P1_START, hourly_start=H_START, first_T=H_START + 60 * DAY,
                  split_p1=P1_START + 36 * HOUR, split_p2=H_START + 120 * DAY, end=END, n_random=10,
                  n_pairs=5, workers=4, test=True)


def _f(x) -> str:
    return f"{x:.10g}"


class World:
    def __init__(self):
        rng = np.random.default_rng(7)
        n_s = P1_DAYS * 86400
        self.n_s = n_s
        r = rng.normal(0.0, 1.5e-4, n_s)
        times = np.sort(rng.choice(np.arange(3600, n_s - 4000), size=30, replace=False))
        self.shocks = []
        for k, t in enumerate(times):
            size = rng.uniform(0.006, 0.02) * (1 if k % 2 else -1)
            dur = int(rng.integers(5, 20))
            r[t:t + dur] += size / dur
            self.shocks.append((int(t), float(size), dur))
        n_h = H_DAYS * 24
        self.n_h = n_h
        n_h_pre = n_h - P1_DAYS * 24
        rh = rng.normal(0.0, 0.006, n_h_pre)
        logp_pre = np.log(100_000.0) + np.cumsum(rh)
        self.btc_logp_1s = logp_pre[-1] + np.cumsum(r)            # log price at the end of each second
        self.btc_prev = logp_pre[-1]
        logp_h_p1 = self.btc_logp_1s.reshape(-1, 3600)[:, -1]
        self.btc_logp_h = np.concatenate([logp_pre, logp_h_p1])  # hourly closes
        # alt definitions
        self.alts = [f"C{i:02d}" for i in range(1, N_ALT + 1)] + ["JUP", "NEW", "GAP", "OLD"]
        self.beta = {a: float(0.8 + 0.8 * rng.random()) for a in self.alts}
        self.lag = {a: (0 if i < 10 else (1 if i < 20 else 3)) for i, a in enumerate(self.alts)}
        self.ptrade = {a: (1.0 if i < 10 else (0.7 if i < 20 else 0.2)) for i, a in enumerate(self.alts)}
        self.hs = {a: (1e-4 if i < 10 else (4e-4 if i < 20 else 8e-4)) for i, a in enumerate(self.alts)}
        self.vol_usd = {a: 5e8 / (i + 2) for i, a in enumerate(self.alts)}   # hourly quote volume level
        # hourly alt log prices
        bh = self.btc_logp_h - self.btc_logp_h[0]
        self.alt_logp_h = {}
        idio = {a: np.cumsum(rng.normal(0.0, 0.004, n_h)) for a in self.alts}
        for a, b in (("C03", "C04"), ("C13", "C14"), ("C25", "C26")):
            ar = np.zeros(n_h)
            e = rng.normal(0.0, 0.003, n_h)
            for t in range(1, n_h):
                ar[t] = 0.97 * ar[t - 1] + e[t]
            idio[b] = idio[a] + ar
            self.beta[b] = self.beta[a]
        for i, a in enumerate(self.alts):
            self.alt_logp_h[a] = np.log(1.0 + 3.0 * i) + self.beta[a] * bh + idio[a]
        self.alt_qv_h = {a: self.vol_usd[a] * np.exp(rng.normal(0.0, 0.5, n_h)) for a in self.alts}
        self.listed = {a: (0, n_h) for a in self.alts}
        self.listed["OLD"] = (0, 150 * 24)
        self.listed["NEW"] = (170 * 24, n_h)
        self.gaps = {"GAP": [(100 * 24, 100 * 24 + 3), (120 * 24, 120 * 24 + 30)]}
        self.specials = {"USDC": 1.0, "PEG": 1.0, "WBTC": None, "BTCUP": 20.0, "BTCDOWN": 5.0}
        self.rng_seed = 11
        self._alt_1s = {}

    # ---- 1-second alt series, generated on first use ----
    def alt_1s(self, a: str):
        if a in self._alt_1s:
            return self._alt_1s[a]
        idx = self.alts.index(a)
        rng = np.random.default_rng(1000 + idx)
        n_s = self.n_s
        b = self.btc_logp_1s - self.btc_prev
        L = self.lag[a]
        bl = np.concatenate([np.zeros(L), b[:n_s - L]]) if L else b
        mid = np.exp(np.log(1.0 + 3.0 * idx) + self.beta[a] * bl + np.cumsum(rng.normal(0.0, 1e-4, n_s)))
        q = 1.0 - np.sqrt(1.0 - self.ptrade[a])
        buy = rng.random(n_s) < q
        sell = rng.random(n_s) < q
        last_is_buy = np.where(buy & sell, rng.random(n_s) < 0.5, buy)
        hs = self.hs[a]
        px = np.where(last_is_buy, mid * (1 + hs), mid * (1 - hs))
        traded = buy | sell
        pos = np.where(traded, np.arange(n_s), -1)
        np.maximum.accumulate(pos, out=pos)
        close = np.where(pos >= 0, px[np.maximum(pos, 0)], mid[0])
        d = {"mid": mid.astype(np.float64), "buy": buy, "sell": sell, "close": close, "size": self.vol_usd[a] / 3600.0}
        self._alt_1s[a] = d
        return d


_WORLD = None


def world() -> World:
    global _WORLD
    if _WORLD is None:
        _WORLD = World()
    return _WORLD


class FakeClient:
    def __init__(self):
        self.w = world()
        self.stats = {"calls": 0, "weight": 0, "status": {}, "max_used_weight_1m": 0, "retries": 0,
                      "bulk_calls": 0, "bulk_status": {}}
        self.refused = {}

    # ---- metadata ----
    def exchange_info(self):
        w = self.w
        syms = [{"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT"}]
        for a in w.alts + list(w.specials):
            syms.append({"symbol": a + "USDT", "status": "BREAK" if a == "OLD" else "TRADING", "baseAsset": a,
                         "quoteAsset": "USDT"})
        syms.append({"symbol": "ETHBTC", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "BTC"})
        return {"rateLimits": [{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1,
                                "limit": 6000}], "symbols": syms}

    def book_ticker(self):
        out = [{"symbol": "BTCUSDT", "bidPrice": "100000.00", "askPrice": "100000.01", "bidQty": "1", "askQty": "1"}]
        for a in self.w.alts:
            hs = self.w.hs[a]
            out.append({"symbol": a + "USDT", "bidPrice": _f(1 - hs), "askPrice": _f(1 + hs), "bidQty": "1",
                        "askQty": "1"})
        return out

    def ticker_24hr(self):
        return [{"symbol": a + "USDT", "quoteVolume": _f(self.w.vol_usd[a] * 24)} for a in self.w.alts]

    # ---- klines ----
    def klines(self, symbol, interval, start_ms, end_ms, limit=1000):
        self.stats["calls"] += 1
        base = symbol[:-4]
        if interval == "1s":
            return self._k1s(base, start_ms, end_ms, limit)
        if interval == "1m":
            return self._k1m(base, start_ms, end_ms, limit)
        if interval == "1h":
            return self._k1h(base, start_ms, end_ms, limit)
        raise ValueError(interval)

    def _k1s(self, base, start_ms, end_ms, limit):
        w = self.w
        a = max(0, -(-(start_ms - P1_START) // SEC))
        b = min(w.n_s - 1, (end_ms - P1_START) // SEC, a + limit - 1)
        if b < a:
            return []
        s = np.arange(a, b + 1)
        ot = P1_START + s * SEC
        if base == "BTC":
            c = np.exp(w.btc_logp_1s[s])
            o = np.exp(np.concatenate([[w.btc_prev], w.btc_logp_1s])[s])
            qv = np.full(len(s), 5e5)
            n = np.full(len(s), 20)
            tbq = np.where(c >= o, 0.6, 0.4) * qv
            return [[int(ot[i]), _f(o[i]), _f(max(o[i], c[i])), _f(min(o[i], c[i])), _f(c[i]), _f(qv[i] / c[i]),
                     int(ot[i] + 999), _f(qv[i]), int(n[i]), _f(tbq[i] / c[i]), _f(tbq[i]), "0"]
                    for i in range(len(s))]
        if base not in w.alts:
            return None
        lo, hi = w.listed[base]
        if hi < w.n_h:          # delisted before the 1-second period
            return []
        d = w.alt_1s(base)
        hs, size = w.hs[base], d["size"]
        rows = []
        for i, k in enumerate(s):
            c = d["close"][k]
            bq = size if d["buy"][k] else 0.0
            sq = size if d["sell"][k] else 0.0
            pb, ps = d["mid"][k] * (1 + hs), d["mid"][k] * (1 - hs)
            vol = bq / pb + sq / ps
            o = d["close"][k - 1] if k > 0 else c
            rows.append([int(ot[i]), _f(o), _f(max(o, c)), _f(min(o, c)), _f(c), _f(vol), int(ot[i] + 999),
                         _f(bq + sq), int(d["buy"][k]) + int(d["sell"][k]), _f(bq / pb), _f(bq), "0"])
        return rows

    def _k1m(self, base, start_ms, end_ms, limit):
        if base != "BTC":
            raise ValueError("fake 1m bars exist for BTC only")
        w = self.w
        n_m = w.n_s // 60
        a = max(0, -(-(start_ms - P1_START) // MIN))
        b = min(n_m - 1, (end_ms - P1_START) // MIN, a + limit - 1)
        if b < a:
            return []
        lp = np.concatenate([[w.btc_prev], w.btc_logp_1s])
        rows = []
        for m in range(a, b + 1):
            seg = np.exp(lp[m * 60:m * 60 + 61])      # previous close, then 60 closes
            ot = P1_START + m * MIN
            rows.append([int(ot), _f(seg[0]), _f(seg.max()), _f(seg.min()), _f(seg[-1]), "1", int(ot + MIN - 1),
                         _f(3e7), 1200, "0.5", _f(1.5e7), "0"])
        return rows

    def _k1h(self, base, start_ms, end_ms, limit):
        w = self.w
        a = max(0, -(-(start_ms - H_START) // HOUR))
        b = min(w.n_h - 1, (end_ms - H_START) // HOUR)
        if base == "BTC":
            logp, qv, lo, hi, gaps = w.btc_logp_h, np.full(w.n_h, 2e9), 0, w.n_h, []
        elif base in w.alts:
            logp, qv = w.alt_logp_h[base], w.alt_qv_h[base]
            (lo, hi), gaps = w.listed[base], w.gaps.get(base, [])
        elif base in w.specials:
            rng = np.random.default_rng(zlib.crc32(base.encode()) % 1000)
            lo, hi, gaps = 0, w.n_h, []
            if base == "WBTC":
                logp = w.btc_logp_h + rng.normal(0, 2e-4, w.n_h)
            elif base in ("USDC", "PEG"):
                logp = rng.normal(0, 1e-4, w.n_h)
            else:
                logp = np.log(w.specials[base]) + (3 if base == "BTCUP" else -3) * (w.btc_logp_h - w.btc_logp_h[0])
            qv = np.full(w.n_h, 3e8 if base in ("USDC", "PEG") else 1e7)
        else:
            return None
        rows = []
        for h in range(max(a, lo), min(b, hi - 1) + 1):
            if any(g0 <= h < g1 for g0, g1 in gaps):
                continue
            c = float(np.exp(logp[h]))
            o = float(np.exp(logp[h - 1])) if h > 0 else c
            ot = H_START + h * HOUR
            rows.append([int(ot), _f(o), _f(max(o, c)), _f(min(o, c)), _f(c), _f(qv[h] / c), int(ot + HOUR - 1),
                         _f(qv[h]), 1000, _f(0.5 * qv[h] / c), _f(0.5 * qv[h]), "0"])
            if len(rows) >= limit:
                break
        return rows

    # ---- bulk host: funding files ----
    def bulk(self, rel_path: str):
        self.stats["bulk_calls"] += 1
        if "fundingRate" not in rel_path:
            return b"probe"
        name = rel_path.rsplit("/", 1)[-1]                       # SYM-fundingRate-YYYY-MM.zip
        sym, _, ym = name[:-4].split("-", 2)
        base = sym[:-4]
        w = self.w
        if base != "BTC" and (base not in w.alts or w.alts.index(base) >= 30):
            return None                                          # no perpetual for the thin coins
        y, m = int(ym[:4]), int(ym[5:7])
        t0 = ms(y, m, 1)
        t1 = ms(y + (m == 12), m % 12 + 1, 1)
        rng = np.random.default_rng(zlib.crc32(name.encode()) % 100000)
        lines = ["calc_time,funding_interval_hours,last_funding_rate"]
        for t in range(t0, t1, 8 * HOUR):
            lines.append(f"{t},8,{1e-4 + rng.normal(0, 5e-5):.8f}")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(name[:-4] + ".csv", "\n".join(lines) + "\n")
        return buf.getvalue()
