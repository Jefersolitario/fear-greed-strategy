"""Compare the liquidity ranking used in this study with a market-capitalisation ranking, point in time.

The market-cap side is THIRD-PARTY, UNVERIFIED data: weekly CoinMarketCap "historical snapshot" scrapes published
in the public GitHub repository dmclink/crypto-historical-marketcaps-scraper-go (file
sample_marketcap_snapshots_2023-12-22, 2013-04-28 to 2023-12-17). It is read as data only and is not
redistributed here. Coverage ends in December 2023, so the comparison covers the formation dates of 2021-2023.

Run (standalone, isolated):  python -I marketcap_compare.py <path to the snapshot csv> <out/s1 directory>
Output: <out/s1>/marketcap_overlap.csv and a printed summary.
"""
import csv
import datetime as dt
import gzip
import os
import sys

STABLE_WRAPPED = {
    "USDT", "USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "UST", "USTC", "SUSD", "USDS", "PYUSD", "USDD", "FRAX",
    "LUSD", "GUSD", "HUSD", "USDJ", "USDN", "EURS", "EURT", "XAUT", "PAXG", "WBTC", "WETH", "WBNB", "STETH", "WSTETH",
    "CBETH", "RETH", "BTCB", "RENBTC", "HBTC", "BETH", "WBETH", "TBTC", "FRXETH", "SFRXETH", "MIM", "USDX", "FEI", "TRIBE",
    "CUSDC", "CDAI", "CETH", "CUSDT", "USDK", "VAI", "RSR_", "WEMIX$", "BTCST_",
}
ALIAS = {"MIOTA": "IOTA", "BTT": "BTTC", "BCHABC": "BCH", "NANO": "XNO", "LUNA": "LUNA", "ELON": "ELON"}


def norm_binance(base):
    for pre in ("1000000", "1000", "1M"):
        if base.startswith(pre) and len(base) > len(pre) + 1:
            return base[len(pre):]
    return base


def main():
    snap_path, s1 = sys.argv[1], sys.argv[2]
    snaps = {}
    with open(snap_path, newline="") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if len(row) < 6 or row[0] < "2021-01-01":
                continue
            try:
                rank = int(row[2])
            except ValueError:
                continue
            if rank <= 400:
                snaps.setdefault(row[0], []).append((rank, row[4].upper()))
    dates = sorted(snaps)
    listed = {}
    with open(os.path.join(s1, "symbols.csv"), newline="") as f:
        for r in csv.DictReader(f):
            if r["first_bar"]:
                listed.setdefault(norm_binance(r["base"]), []).append((r["first_bar"][:10], r["last_bar"][:10]))
    uni = {}
    with gzip.open(os.path.join(s1, "formation_universe.csv.gz"), "rt", newline="") as f:
        for r in csv.DictReader(f):
            uni.setdefault(r["T"], []).append((int(r["rank"]), norm_binance(r["symbol"][:-4])))
    rows = []
    for T in sorted(uni):
        prior = [d for d in dates if d <= T]
        if not prior or (dt.date.fromisoformat(T) - dt.date.fromisoformat(prior[-1])).days > 10:
            continue
        mc = [ALIAS.get(s, s) for _, s in sorted(snaps[prior[-1]]) if s not in STABLE_WRAPPED]
        m100, m200 = mc[:100], set(mc[:200])
        liq = [b for _, b in sorted(uni[T])]
        l100, l30 = set(liq), set(liq[:30])
        on_binance = {s for s in m100 if any(a <= T <= b for a, b in listed.get(s, []))}
        rows.append({"T": T, "snapshot": prior[-1], "liq_top100_in_mcap_top100": len(l100 & set(m100)),
                     "liq_top100_in_mcap_top200": len(l100 & m200), "liq_top30_in_mcap_top100": len(l30 & set(m100)),
                     "mcap_top100_listed_on_binance_usdt": len(on_binance), "mcap_top100_in_liq_top100": len(set(m100) & l100),
                     "mcap_top30_in_liq_top100": len(set(m100[:30]) & l100)})
    out = os.path.join(s1, "marketcap_overlap.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    print(f"{n} formation dates from {rows[0]['T']} to {rows[-1]['T']}")
    for k in list(rows[0])[2:]:
        v = [r[k] for r in rows]
        print(f"  {k}: mean {sum(v) / n:.1f}, min {min(v)}, max {max(v)}")
    print("wrote", out)


if __name__ == "__main__":
    main()
