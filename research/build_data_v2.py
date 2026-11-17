"""Corrected daily table. The 4h file's timestamps are UTC up to 2025-05-08 16:00 and UTC+4 from the row
labelled 2025-05-08 20:00 on (shown by the Coin Metrics comparison and by the 10 Oct 2025 crash candle).
So after Coin Metrics ends, the UTC close of day d is the close of the candle LABELLED 00:00 on d+1.

Usage: python build_data_v2.py daily.parquet btc_with_fgi_4h.csv coinmetrics_btc.csv daily_v2.parquet btc_long.parquet
"""
import sys
from datetime import timedelta

import polars as pl

daily_path, b_path, cm_path, out_daily, out_long = sys.argv[1:6]
old = pl.read_parquet(daily_path)
b = pl.read_csv(b_path).with_columns(pl.col("timestamp").str.to_datetime("%Y-%m-%d %H:%M:%S").alias("ts"))
# candle labelled 00:00 on d+1 covers 20:00-24:00 UTC of d
fix = (b.filter(pl.col("ts").dt.hour() == 0)
        .select((pl.col("ts").dt.date() - pl.duration(days=1)).alias("date"), pl.col("close").alias("close_fix")))
new = (old.join(fix, on="date", how="left")
          .with_columns(pl.when(pl.col("px_src") == "binance_4h").then(pl.col("close_fix")).otherwise(pl.col("close")).alias("close_new")))
chg = new.filter((pl.col("px_src") == "binance_4h") & pl.col("close").is_not_null())
d = (chg["close_new"] / chg["close"] - 1).abs() * 100
print(f"days repriced: {chg.height} ({chg['date'].min()} .. {chg['date'].max()}); median |change| {d.median():.2f}%, p90 {d.quantile(0.9):.2f}%, max {d.max():.2f}%")
print("last five days, old -> new close:", [(r["date"].isoformat(), round(r["close"]), round(r["close_new"])) for r in chg.tail(5).iter_rows(named=True)])
last = new.filter(pl.col("close_new").is_not_null()).tail(1)
print("last complete day in corrected table:", last["date"][0], round(last["close_new"][0]))
new.select("date", "fng", pl.col("close_new").alias("close"), "px_src").write_parquet(out_daily)

# long history for cycle work: Coin Metrics daily since 2010 (price plus the on-chain columns it ships), then corrected Binance closes
cm = pl.read_csv(cm_path, infer_schema_length=0)
print("Coin Metrics columns:", cm.columns)
keep = [c for c in ("PriceUSD", "CapMrktCurUSD", "CapMVRVCur", "CapRealUSD", "SplyCur", "IssTotNtv", "IssTotUSD", "HashRate", "AdrActCnt", "TxTfrValAdjUSD", "NVTAdj", "FeeTotUSD", "BlkCnt") if c in cm.columns]
long = cm.select(pl.col("time").str.slice(0, 10).str.to_date().alias("date"), *[pl.col(c).cast(pl.Float64, strict=False) for c in keep]).filter(pl.col("PriceUSD").is_not_null())
tail = new.filter(pl.col("date") > long["date"].max()).filter(pl.col("close_new").is_not_null()).select("date", pl.col("close_new").alias("PriceUSD"))
long = pl.concat([long, tail], how="diagonal").sort("date")
long.write_parquet(out_long)
print("long file:", long["date"].min(), "..", long["date"].max(), long.height, "rows; columns", long.columns)
print("non-null counts:", {c: long[c].drop_nulls().len() for c in long.columns if c != "date"})
