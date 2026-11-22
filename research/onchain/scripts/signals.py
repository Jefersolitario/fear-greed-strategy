"""Signal definitions (PREREG.md section D). Everything is trailing-window only.

Two implementations of the same definitions:
  full_signals(raw)  : pandas rolling over a whole daily history  -> used for the L-sample (last vintage)
  last_signals(raw)  : numpy, value at the last valid date only    -> used for every as-of vintage (V-sample)
`tests/test_signals.py` checks that they agree, and b1 checks V == L on never-revised metrics.
"""
import numpy as np
import pandas as pd

FLOW = ["AdrActCnt", "TxCnt", "TxTfrCnt", "FeeTotNtv", "HashRate", "BlkCnt", "FlowInExNtv", "FlowOutExNtv",
        "TxTfrValAdjUSD", "NVTAdj"]
STOCK = ["AdrBalCnt", "CapMVRVCur", "CapRealUSD", "Puell", "NVTAdj90", "SplyActPct1yr", "VelCur1yr"]
DERIVED_FLOW_NOLOG = ["NetFlowEx"]
METRICS = FLOW + DERIVED_FLOW_NOLOG + STOCK

RAW_NEEDED = ["PriceUSD", "AdrActCnt", "AdrBalCnt", "TxCnt", "TxTfrCnt", "FeeTotNtv", "HashRate", "BlkCnt",
              "CapMVRVCur", "CapMrktCurUSD", "IssTotUSD", "FlowInExNtv", "FlowOutExNtv", "SplyCur",
              "NVTAdj", "NVTAdj90", "TxTfrValAdjUSD", "SplyActPct1yr", "VelCur1yr"]

CLIP = 4.0
# variant name -> (kind, change window k, z window W)
VARIANTS = {
    "lvl": ("lvl", 0, 365), "chg7": ("chg", 7, 365),                     # primary
    "lvl_z180": ("lvl", 0, 180), "chg7_z180": ("chg", 7, 180),           # R1
    "lvl_z730": ("lvl", 0, 730), "chg7_z730": ("chg", 7, 730),           # R2
    "chg1": ("chg", 1, 365), "chg30": ("chg", 30, 365),                  # R3, R4
}
PRIMARY = ["lvl", "chg7"]


def minp(W):
    return int(round(W * 300.0 / 365.0))


def _safe_log(a):
    out = np.full(a.shape, np.nan)
    ok = np.isfinite(a) & (a > 0)
    out[ok] = np.log(a[ok])
    return out


def derived_raw(raw):
    """Add the derived daily inputs. raw: dict name -> float array on a consecutive daily index."""
    r = dict(raw)
    n = len(next(iter(raw.values())))
    nan = np.full(n, np.nan)
    g = lambda k: raw.get(k, nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r["CapRealUSD"] = np.where(g("CapMVRVCur") > 0, g("CapMrktCurUSD") / g("CapMVRVCur"), np.nan)
        r["NetFlowEx"] = np.where(g("SplyCur") > 0, (g("FlowInExNtv") - g("FlowOutExNtv")) / g("SplyCur"), np.nan)
        iss = pd.Series(g("IssTotUSD"))
        r["Puell"] = (iss / iss.rolling(365, min_periods=300).mean()).to_numpy()
    return r


def base_series(raw, metric):
    """y(t) for one metric from the (derived) raw dict; NaN where not defined."""
    x = raw.get(metric)
    if x is None:
        return None
    x = np.asarray(x, float)
    if metric in FLOW or metric in DERIVED_FLOW_NOLOG:
        m = pd.Series(x).rolling(7, min_periods=5).mean().to_numpy().copy()
        m[~np.isfinite(x)] = np.nan           # defined only on dates whose own value is published
        return _safe_log(m) if metric in FLOW else m
    return _safe_log(x)


def _z_full(v, W):
    s = pd.Series(v)
    mu = s.rolling(W, min_periods=minp(W)).mean()
    sd = s.rolling(W, min_periods=minp(W)).std(ddof=1)
    z = ((s - mu) / sd).to_numpy().copy()
    z[~np.isfinite(z)] = np.nan
    return np.clip(z, -CLIP, CLIP)


def full_signals(raw, metrics=METRICS, variants=VARIANTS):
    """dict (metric, variant) -> array over the whole index; value at t uses data <= t only."""
    raw = derived_raw(raw)
    out = {}
    for m in metrics:
        y = base_series(raw, m)
        if y is None:
            continue
        for vname, (kind, k, W) in variants.items():
            if kind == "lvl":
                v = y
            else:
                v = y - np.concatenate([np.full(k, np.nan), y[:-k]])
            out[(m, vname)] = _z_full(v, W)
    return out


def _z_last(v, W):
    w = v[-W:]
    ok = np.isfinite(w)
    if not np.isfinite(v[-1]) or ok.sum() < minp(W):
        return np.nan
    sd = w[ok].std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return np.nan
    return float(np.clip((v[-1] - w[ok].mean()) / sd, -CLIP, CLIP))


def last_signals(raw, metrics=METRICS, variants=VARIANTS):
    """As-of evaluation: for each metric, the signal values at its last valid date.
    raw: dict name -> array on a consecutive daily index (a tail of >= 1,200 rows is enough).
    Returns dict metric -> (offset_of_last_valid_date_from_end, dict variant -> value)."""
    raw = derived_raw(raw)
    out = {}
    for m in metrics:
        y = base_series(raw, m)
        if y is None:
            continue
        ok = np.nonzero(np.isfinite(y))[0]
        if ok.size == 0:
            continue
        last = int(ok[-1])
        yy = y[: last + 1]
        vals = {}
        for vname, (kind, k, W) in variants.items():
            if kind == "lvl":
                v = yy
            else:
                v = yy - np.concatenate([np.full(k, np.nan), yy[:-k]]) if len(yy) > k else np.full(len(yy), np.nan)
            vals[vname] = _z_last(v, W)
        out[m] = (len(y) - 1 - last, vals)
    return out


def price_baselines(price):
    """Price-only signals on a consecutive daily close series; value at t uses closes <= t only."""
    lp = _safe_log(np.asarray(price, float))
    s = pd.Series(lp)
    runmax = s.cummax()   # NaN-safe running maximum of the log price
    return {
        "PX_M7": _z_full((s - s.shift(7)).to_numpy(), 365),
        "PX_M30": _z_full((s - s.shift(30)).to_numpy(), 365),
        "PX_DD": _z_full((s - runmax).to_numpy(), 365),
        "PX_Z": _z_full(lp, 365),
    }
