"""Extend on-chain data past the end of the Coin Metrics files.

1. Actual Coin Metrics MVRV / realized price to 2026-07-30 (a second public copy of the community data).
2. 2026-07-31 onward: recover NUPL (and so MVRV) from the official CBBI file. CBBI publishes
   RUPL_index = (NUPL - low_line) / (high_line - low_line), both lines straight in time, so
   NUPL = a0 + a1*t + index*(b0 + b1*t): four numbers, fitted where raw NUPL is known and then checked out of sample.
3. Also writes the CBBI confidence series and its nine components.

Usage: python extend_onchain.py btc_long.parquet btc_mvrv_dataset.csv cbbi_latest.json daily_v2.parquet out.parquet
"""
import datetime as dt
import json
import sys

import numpy as np
import polars as pl

long_path, hut_path, cbbi_path, daily_path, out_path = sys.argv[1:6]
L = pl.read_parquet(long_path)
H = pl.read_csv(hut_path).select(
    pl.col("time").str.slice(0, 10).str.to_date().alias("date"),
    pl.col("CapMVRVCur").alias("mvrv_h"),
    pl.col("PriceUSD").alias("px_h"),
)
J = json.load(open(cbbi_path))
day = lambda ts: dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).date()
keys = list(J["Confidence"])
cols = {"date": [day(t) for t in keys]}
for k in J:
    cols["cbbi" if k == "Confidence" else "cbbi_" + k.lower()] = [J[k].get(t) for t in keys]
C = pl.DataFrame(cols).sort("date")
C = C.with_columns([(pl.col(c) * 100).alias(c) for c in C.columns if c.startswith("cbbi") and c != "cbbi_price"])

df = L.join(H, on="date", how="full", coalesce=True).join(C, on="date", how="full", coalesce=True).sort("date")
df = df.with_columns(
    pl.coalesce("CapMVRVCur", "mvrv_h").alias("mvrv_actual"),
    pl.coalesce("PriceUSD", "px_h", "cbbi_price").alias("price"),
).filter(pl.col("price").is_not_null())

d = np.array([x.toordinal() for x in df["date"].to_list()])
t = (d - d[0]) / 365.25
idx = df["cbbi_rupl"].to_numpy().astype(float) / 100
mv = df["mvrv_actual"].to_numpy().astype(float)
nupl = 1 - 1 / mv
known = np.isfinite(idx) & np.isfinite(nupl)
ok = known & (idx > 0.03) & (idx < 0.97)
X = np.c_[np.ones_like(t), t, idx, idx * t]


def fit(mask):
    return np.linalg.lstsq(X[mask], nupl[mask], rcond=None)[0]


cut = dt.date(2025, 12, 31).toordinal()
train, test = ok & (d <= cut), known & (d > cut)
b = fit(train)
err = (1 / (1 - X[test] @ b)) / mv[test] - 1
print(f"out-of-sample check, fitted to end-2025 and tested on {int(test.sum())} days of 2026: "
      f"MVRV error median {np.median(np.abs(err)) * 100:.2f}%, max {np.max(np.abs(err)) * 100:.2f}%, mean {err.mean() * 100:+.2f}%")
b = fit(ok)
fitted = 1 / (1 - X @ b)
e_all = fitted[ok] / mv[ok] - 1
last60 = np.where(np.isfinite(mv) & np.isfinite(fitted))[0][-60:]
print(f"final fit on {int(ok.sum())} days: MVRV error median {np.median(np.abs(e_all)) * 100:.2f}%, "
      f"99th pct {np.quantile(np.abs(e_all), 0.99) * 100:.2f}%; last 60 known days mean {np.mean(fitted[last60] / mv[last60] - 1) * 100:+.2f}%")
adj = float(np.mean(mv[last60] / fitted[last60]))
mvrv = np.where(np.isfinite(mv), mv, fitted * adj)
src = np.where(np.isfinite(mv), "coinmetrics", "from_cbbi_rupl")
df = df.with_columns(pl.Series("mvrv_raw", mvrv), pl.Series("mvrv_src", src))
df = df.with_columns((pl.col("price") / pl.col("mvrv_raw")).alias("realized_price"))

# my corrected UTC closes after the Coin Metrics prices end; MVRV restated on that price
dv = pl.read_parquet(daily_path).filter(pl.col("close").is_not_null()).select("date", "close", "fng")
df = df.join(dv, on="date", how="left")
df = df.with_columns(pl.coalesce("PriceUSD", "close", "price").alias("price"))
df = df.with_columns((pl.col("price") / pl.col("realized_price")).alias("mvrv"))
out = df.select(
    "date", "price", "fng", "mvrv", "mvrv_src", "realized_price", "IssTotNtv", "IssTotUSD", "SplyCur", "BlkCnt",
    *[c for c in df.columns if c.startswith("cbbi")],
).filter(pl.col("date") <= dv["date"].max())
out.write_parquet(out_path)

with pl.Config(tbl_rows=40, tbl_cols=12):
    print(out.filter((pl.col("mvrv_src") == "from_cbbi_rupl") & pl.col("date").dt.day().is_in([1, 15]))
          .select("date", "price", pl.col("mvrv").round(3), pl.col("realized_price").round(0), pl.col("cbbi").round(1)))
new = out.filter(pl.col("date") > dt.date(2026, 5, 23))
i = int(np.argmin(new["mvrv"].to_numpy()))
print("lowest MVRV since 24 May 2026:", new["date"][i], round(new["mvrv"][i], 3), "price", round(new["price"][i]),
      "| latest:", out["date"][-1], round(out["mvrv"][-1], 3), "realized price", round(out["realized_price"][-1]))
print("rows", out.height, out["date"].min(), out["date"].max(), "| MVRV sources:", out.group_by("mvrv_src").len().to_dicts())
print("days with MVRV < 1 since 2023:", out.filter((pl.col("date") >= dt.date(2023, 6, 1)) & (pl.col("mvrv") < 1)).height)
