"""Order-book snapshot of the current top 100: what it costs to cross the spot book with 1,000 and 10,000 USD.

A size check for the cost assumptions (2 / 5 / 10 bps half-spread by tier). It is a snapshot of today's spot
books in calm conditions, not history and not the perpetual books; it says nothing about books during a shock.

Inputs : out/s1/spread_snapshot.csv (symbols with their current liquidity rank)
Outputs: out/s2/depth_cost.csv, out/s2/depth_summary.json
Run: python s2_depth.py     |     BTCALTS_TEST=1 python s2_depth.py
"""
from __future__ import annotations

import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import common as C

TEST = os.environ.get("BTCALTS_TEST") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "out_test" if TEST else "out")
OUT = os.path.join(OUT_ROOT, "s2")
SIZES = (1_000.0, 10_000.0)
SNAPSHOTS = 2 if TEST else 4
PAUSE_S = 0 if TEST else 240


def walk(levels, quote):
    """Average price paid (or received) for `quote` USD against the levels; None if the book shown is too thin."""
    left, base = quote, 0.0
    for px, qty in levels:
        take = min(left, px * qty)
        base += take / px
        left -= take
        if left <= 1e-9:
            return quote / base
    return None


def one_book(client, sym):
    d = client.depth(sym, 100)
    if not d or not d.get("bids") or not d.get("asks"):
        return None
    bids = [(float(p), float(q)) for p, q in d["bids"]]
    asks = [(float(p), float(q)) for p, q in d["asks"]]
    mid = (bids[0][0] + asks[0][0]) / 2
    row = {"half_spread_bps": (asks[0][0] - bids[0][0]) / 2 / mid * 1e4,
           "bid_depth_usd": sum(p * q for p, q in bids), "ask_depth_usd": sum(p * q for p, q in asks)}
    for size in SIZES:
        b, s = walk(asks, size), walk(bids, size)
        key = f"cost_{int(size / 1000)}k_bps"
        row[key] = ((b / mid - 1) + (1 - s / mid)) / 2 * 1e4 if b and s else float("nan")
    return row


def main():
    cfg = C.load_config()
    client = C.make_client(cfg)
    os.makedirs(OUT, exist_ok=True)
    syms = []
    with open(os.path.join(OUT_ROOT, "s1", "spread_snapshot.csv")) as f:
        for r in csv.DictReader(f):
            if int(r["rank"]) <= 100:
                syms.append((r["symbol"], int(r["rank"]), int(r["tier"])))
    rows, refused = [], None
    for snap in range(SNAPSHOTS):
        t0 = time.time()
        try:
            with ThreadPoolExecutor(4) as ex:
                res = list(ex.map(lambda x: one_book(client, x[0]), syms))
        except C.Refused as e:
            refused = repr(e)
            break
        for (sym, rank, tier), r in zip(syms, res):
            if r:
                rows.append([snap, C.iso(int(t0 * 1000)), sym, rank, tier] + [f"{r[k]:.3f}" for k in
                            ("half_spread_bps", "cost_1k_bps", "cost_10k_bps")] + [f"{r['bid_depth_usd']:.0f}", f"{r['ask_depth_usd']:.0f}"])
        print(time.strftime("%H:%M:%S"), f"snapshot {snap + 1}/{SNAPSHOTS}: {sum(1 for r in res if r)} books", flush=True)
        if snap < SNAPSHOTS - 1:
            time.sleep(PAUSE_S)
    with open(os.path.join(OUT, "depth_cost.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["snapshot", "utc", "symbol", "rank", "tier", "half_spread_bps", "cost_1k_bps", "cost_10k_bps",
                    "bid_depth_100_levels_usd", "ask_depth_100_levels_usd"])
        w.writerows(rows)
    by_tier = {}
    for t in (1, 2, 3):
        sub = [r for r in rows if r[4] == t]
        per_coin = {}
        for r in sub:
            per_coin.setdefault(r[2], []).append([float(r[5]), float(r[6]), float(r[7]), min(float(r[8]), float(r[9]))])
        m = np.array([np.nanmedian(np.array(v), axis=0) for v in per_coin.values()]) if per_coin else np.zeros((0, 4))
        if len(m) == 0:
            continue
        by_tier[f"tier{t}"] = {
            "coins": int(len(m)), "half_spread_median_bps": float(np.nanmedian(m[:, 0])),
            "cost_1k_median_bps": float(np.nanmedian(m[:, 1])), "cost_1k_p75_bps": float(np.nanpercentile(m[:, 1], 75)),
            "cost_1k_max_bps": float(np.nanmax(m[:, 1])),
            "cost_10k_median_bps": float(np.nanmedian(m[:, 2])), "cost_10k_p75_bps": float(np.nanpercentile(m[:, 2], 75)),
            "cost_10k_max_bps": float(np.nanmax(m[:, 2])), "books_too_thin_for_10k": int(np.isnan(m[:, 2]).sum()),
            "depth_100_levels_median_usd": float(np.nanmedian(m[:, 3])), "assumed_half_spread_bps": C.HALF_SPREAD[t]}
    C.write_json(os.path.join(OUT, "depth_summary.json"), {"by_tier": by_tier, "snapshots": SNAPSHOTS, "refused": refused,
                                                           "note": "spot books, calm conditions, today; not history",
                                                           "meta": C.run_meta(client)})
    for k, v in by_tier.items():
        print(k, v, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
