"""Census of the exchangeInfo attributes of every USDT pair (one request). Used to decide, from the exchange's own
metadata, which pairs are tokenized equities or other pegged products that must stay out of the coin universe.

Output: out/s0/usdt_symbols_info.csv, out/s0/samples.json
"""
from __future__ import annotations

import csv
import json
import os
import sys

import common as C

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "s0")
SAMPLES = ("BTCUSDT", "HYPEUSDT", "NVDABUSDT", "SPYBUSDT", "QNTBUSDT", "USDEBUSDT", "WENBUSDT", "YBUSDT", "PAXGUSDT",
           "UUSDT", "ANTBUSDT", "UVXYBUSDT")


def main():
    cfg = C.load_config()
    client = C.make_client(cfg)
    os.makedirs(OUT, exist_ok=True)
    info = client.exchange_info()
    syms = [s for s in info["symbols"] if s.get("quoteAsset") == "USDT"]
    std = {"symbol", "status", "baseAsset", "baseAssetPrecision", "quoteAsset", "quotePrecision", "quoteAssetPrecision",
           "baseCommissionPrecision", "quoteCommissionPrecision", "orderTypes", "icebergAllowed", "ocoAllowed", "otoAllowed",
           "quoteOrderQtyMarketAllowed", "allowTrailingStop", "cancelReplaceAllowed", "amendAllowed", "isSpotTradingAllowed",
           "isMarginTradingAllowed", "filters", "permissions", "permissionSets", "defaultSelfTradePreventionMode",
           "allowedSelfTradePreventionModes", "pegInstructionsAllowed", "opoAllowed"}
    with open(os.path.join(OUT, "usdt_symbols_info.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "base", "status", "isSpotTradingAllowed", "isMarginTradingAllowed", "permissions", "permissionSets",
                    "filter_types", "other_keys"])
        for s in sorted(syms, key=lambda x: x["symbol"]):
            other = {k: s[k] for k in s if k not in std}
            w.writerow([s["symbol"], s["baseAsset"], s.get("status"), s.get("isSpotTradingAllowed"), s.get("isMarginTradingAllowed"),
                        json.dumps(s.get("permissions")), json.dumps(s.get("permissionSets")),
                        "|".join(sorted(x.get("filterType", "") for x in s.get("filters", []))), json.dumps(other, sort_keys=True)])
    C.write_json(os.path.join(OUT, "samples.json"), {"top_level_keys": sorted(k for k in info if k != "symbols"),
                                                     "samples": [s for s in syms if s["symbol"] in SAMPLES],
                                                     "meta": C.run_meta(client)})
    print("wrote", len(syms), "rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
