"""Cycle indicators, second pass: data to 14 Nov 2026, CBBI, adaptive MVRV, every cycle from 2011,
and the elimination rule "an indicator that misses a cycle is out".

Usage: python cycle2.py btc_ext.parquet btc_long.parquet hut.csv cycle_scripts_dir out_dir
"""
import datetime as dt
import json
import sys

import numpy as np
import polars as pl

ext_path, long_path, hut_path, lib_dir, out_dir = sys.argv[1:6]
sys.path.insert(0, lib_dir)
import cyclelib as cl  # noqa: E402

D = dt.date
E = pl.read_parquet(ext_path).sort("date")
L = pl.read_parquet(long_path).sort("date")
H = pl.read_csv(hut_path).select(pl.col("time").str.slice(0, 10).str.to_date().alias("date"),
                                 pl.col("SplyCur").alias("sply_h"), pl.col("CapMVRVCur").alias("mvrv_h"))

# ---------- 1. extended long file in the library's column names ----------
df = L.select("date", "PriceUSD", "CapMVRVCur", "SplyCur", "IssTotUSD").join(H, on="date", how="left").join(
    E.select("date", pl.col("mvrv").alias("mvrv_est"), "mvrv_src", "cbbi_rupl",
             *[c for c in E.columns if c.startswith("cbbi") and c not in ("cbbi_rupl",)]), on="date", how="left").sort("date")
dates = df["date"].to_list()
n = len(dates)
p = df["PriceUSD"].to_numpy().astype(float)
mv = df["CapMVRVCur"].to_numpy().astype(float)
mv = np.where(np.isfinite(mv), mv, df["mvrv_h"].to_numpy().astype(float))
est = df["mvrv_est"].to_numpy().astype(float)
rup = df["cbbi_rupl"].to_numpy().astype(float)
last_act = int(np.max(np.where(np.isfinite(mv))[0]))
# after the last actual day: implied realized price from the CBBI reconstruction, 21-day trailing median,
# skipping days where CBBI's NUPL input is a forward-filled repeat of the day before
rp_imp = p / est
stale = np.zeros(n, bool)
stale[1:] = rup[1:] == rup[:-1]
rp = p / mv
for t in range(last_act + 1, n):
    lo = max(last_act + 1, t - 20)
    w = [rp_imp[k] for k in range(lo, t + 1) if np.isfinite(rp_imp[k]) and not stale[k]]
    w = [rp[k] for k in range(max(0, last_act - (20 - len(w))), last_act + 1)] + w if len(w) < 21 else w
    rp[t] = float(np.median(w))
mvrv = p / rp
approx = np.arange(n) > last_act
sply = df["SplyCur"].to_numpy().astype(float)
sply = np.where(np.isfinite(sply), sply, df["sply_h"].to_numpy().astype(float))
ls = int(np.max(np.where(np.isfinite(sply))[0]))
sply[ls + 1:] = sply[ls] + 450.0 * np.arange(1, n - ls)
iss = df["IssTotUSD"].to_numpy().astype(float)
li = int(np.max(np.where(np.isfinite(iss))[0]))
iss[li + 1:] = 450.0 * p[li + 1:]
long2 = pl.DataFrame({"date": dates, "PriceUSD": p, "CapMrktCurUSD": sply * p, "CapMVRVCur": mvrv, "SplyCur": sply, "IssTotUSD": iss})
long2.write_parquet(f"{out_dir}/btc_long_ext.parquet")
print(f"actual MVRV to {dates[last_act]}; estimated {int(approx.sum())} days to {dates[-1]}; realized price est. now {rp[-1]:,.0f} (last actual {rp[last_act]:,.0f}); MVRV now {mvrv[-1]:.3f}")
print(f"MVRV range in estimated window: {mvrv[approx].min():.3f} .. {mvrv[approx].max():.3f}")

ind = cl.compute_indicators(long2)
flags, thr = cl.build_flags(ind)
g = {c: ind[c].to_numpy() for c in ind.columns if c != "date"}
cbbi = df["cbbi"].to_numpy().astype(float)
lt = lambda x, v: np.where(np.isnan(x), False, x < v)
gt = lambda x, v: np.where(np.isnan(x), False, x > v)
for lo_, hi_ in ((10, 90), (15, 85), (20, 80)):
    flags[f"cbbi|{lo_}/{hi_}"] = dict(cheap=cl.lag1(lt(cbbi, lo_)), exp=cl.lag1(gt(cbbi, hi_)))
g["cbbi"] = cbbi
for w_y in (3, 4, 5):
    r = cl._rolling_pct(g["mvrv"], 365 * w_y)
    g[f"mvrv_r{w_y}y"] = r
    for q in (0.10, 0.20, 0.25):
        flags[f"mvrv_r{w_y}y|{int(q * 100)}"] = dict(cheap=cl.lag1(lt(r, q)), exp=cl.lag1(gt(r, 1 - q)))
# MVRV against its own slow-moving floor: within x% of the trailing 4-year minimum / maximum
mn = np.full(n, np.nan); mx = np.full(n, np.nan)
for t in range(1460, n):
    seg = g["mvrv"][t - 1460:t]  # strictly before t
    if np.isfinite(seg).sum() >= 1000:
        mn[t], mx[t] = np.nanmin(seg), np.nanmax(seg)
for x in (0.25, 0.5):
    flags[f"mvrv_floor4y|+{int(x * 100)}%"] = dict(cheap=cl.lag1(np.where(np.isnan(mn), False, g["mvrv"] < mn * (1 + x))), exp=None)

# ---------- 2. turning points ----------
ix = {d: i for i, d in enumerate(dates)}
def ext(d0, d1, kind):
    i0, i1 = ix[d0], ix[min(d1, dates[-1])]
    seg = p[i0:i1 + 1]
    return i0 + int(np.argmax(seg) if kind == "max" else np.argmin(seg))
HIGHS = {"2011": ext(D(2011, 1, 1), D(2011, 12, 31), "max"), "2013": ext(D(2013, 6, 1), D(2014, 6, 30), "max"),
         "2017": ext(D(2017, 1, 1), D(2018, 6, 30), "max"), "2021 Apr": ext(D(2021, 1, 1), D(2021, 7, 31), "max"),
         "2021 Nov": ext(D(2021, 8, 1), D(2022, 6, 30), "max"), "2025": ext(D(2024, 6, 1), D(2026, 11, 14), "max")}
LOWS = {"2011": ext(D(2011, 6, 9), D(2012, 12, 31), "min"), "2015": ext(D(2014, 1, 1), D(2016, 6, 30), "min"),
        "2018": ext(D(2018, 1, 1), D(2019, 12, 31), "min"), "2022": ext(D(2021, 12, 1), D(2023, 12, 31), "min"),
        "2026*": ext(dates[HIGHS["2025"]], dates[-1], "min")}
for k, i in list(HIGHS.items()):
    print(f"high {k:9s} {dates[i]}  ${p[i]:>10,.0f}")
prev_hi = {"2011": "2011", "2015": "2013", "2018": "2017", "2022": "2021 Nov", "2026*": "2025"}
for k, i in LOWS.items():
    print(f"low  {k:9s} {dates[i]}  ${p[i]:>10,.0f}  drawdown {p[i] / p[HIGHS[prev_hi[k]]] - 1:+.0%}  MVRV {g['mvrv'][i]:.2f}  CBBI today's file {cbbi[i]:.1f}")

SOURCE = {"mvrv": "mvrv", "mvrvz": "mvrvz", "nupl": "nupl", "puell": "puell", "w200": "w200", "mayer": "mayer", "ma2y": "ma2y", "dd": "dd",
          "plaw": "plaw", "plaw_pct": "plaw_pct", "s2f_fix": "s2f_fix", "s2f_exp": "s2f_exp", "comp": "comp", "pi": "pi", "halv": "halv",
          "mvrv_r4y": "mvrv_r4y", "mayer_r4y": "mayer_r4y", "cbbi": "cbbi", "mvrv_r3y": "mvrv_r3y", "mvrv_r5y": "mvrv_r5y", "mvrv_floor4y": None}
def valid_at(name, i):
    base = name.split("|")[0]
    col = SOURCE.get(base)
    if base == "mvrv_floor4y":
        return np.isfinite(mn[i])
    if base == "halv":
        return np.isfinite(g["halv"][i])
    x = g[col]
    return bool(np.isfinite(x[max(i - 30, 0):i + 31]).all())

def episodes(mask, gap=90):
    ii = np.where(mask)[0]
    if len(ii) == 0:
        return []
    cuts = np.where(np.diff(ii) > gap)[0]
    starts = np.r_[ii[0], ii[cuts + 1]]; ends = np.r_[ii[cuts], ii[-1]]
    return list(zip(starts, ends))

def score(name, side, win=30):
    m = flags[name][side]
    if m is None:
        return None
    ev = LOWS if side == "cheap" else HIGHS
    marks, lead = {}, {}
    for k, i in ev.items():
        if not valid_at(name, i):
            marks[k] = "-"
            continue
        hit = bool(m[max(i - win, 0):i + win + 1].any())
        marks[k] = "Y" if hit else "n"
    first_valid = next((t for t in range(n) if valid_at(name, t)), n)
    on = m[first_valid:]
    eps = episodes(m)
    evi = list(ev.values())
    false_eps = sum(1 for s, e in eps if not any(s - 180 <= i <= e + 180 for i in evi))
    return dict(marks=marks, share_on=float(on.mean()) if len(on) else 0.0, days_on=int(m.sum()), episodes=len(eps), false_eps=false_eps,
                on_now=bool(m[-1]), days_since_H2025=int(m[HIGHS["2025"]:].sum()))

res = {"scores": {}, "events": {"highs": {k: str(dates[i]) for k, i in HIGHS.items()}, "lows": {k: str(dates[i]) for k, i in LOWS.items()}}}
SHOW = ["mvrv|lit", "mvrvz|lit", "puell|lit", "cbbi|10/90", "cbbi|15/85", "cbbi|20/80", "comp|cal17", "dd|lit", "w200|lit", "ma2y|lit", "mayer|lit",
        "plaw_pct|adapt", "s2f_fix|cal17", "s2f_exp|cal17", "pi|lit", "halv|lit", "halv|cal17", "mvrv_r4y|adapt", "mvrv_r3y|20", "mvrv_r4y|20", "mvrv_r5y|20",
        "mvrv_r4y|25", "mvrv_floor4y|+25%", "mvrv_floor4y|+50%", "mayer_r4y|adapt", "mvrv|cal17", "puell|cal17", "mayer|cal17", "ma2y|cal17", "w200|cal17", "dd|cal17"]
flags["mvrv_r4y|20"] = flags["mvrv_r4y|20"]
for side, ev in (("cheap", LOWS), ("exp", HIGHS)):
    print(f"\n=== {side.upper()} side: fired within 30 days of each {'low' if side == 'cheap' else 'high'} ({' / '.join(ev)}) | share of days on | episodes (false) | days on since Oct-2025 high | on now")
    for name in SHOW:
        s30 = score(name, side, 30)
        if s30 is None:
            continue
        s90 = score(name, side, 90)
        res["scores"][f"{name}|{side}"] = dict(w30=s30, w90=s90["marks"])
        m30 = " ".join(s30["marks"][k] for k in ev); m90 = " ".join(s90["marks"][k] for k in ev)
        verdict = "OUT" if "n" in m30 else "survives"
        print(f"{name:20s} ±30d: {m30}   ±90d: {m90}   on {s30['share_on']:5.1%}  eps {s30['episodes']:2d} ({s30['false_eps']} false)  since-high {s30['days_since_H2025']:3d}  now {'ON' if s30['on_now'] else 'off'}  -> {verdict}")

# current readings
print("\ncurrent readings (close of", dates[-1], "):")
for k in ("price", "mvrv", "realized_price", "puell", "mayer", "ma2y", "w200", "dd", "plaw_pct", "comp", "mvrv_r4y", "halv", "pi", "cbbi"):
    print(f"  {k:15s} {g[k][-1]:,.3f}")
print("  trailing-4y MVRV quantiles now: p10 %.3f  p20 %.3f  p25 %.3f  min %.3f" % (*np.nanquantile(g["mvrv"][-1460:], [0.1, 0.2, 0.25]), np.nanmin(g["mvrv"][-1460:])))
i26 = LOWS["2026*"]
print("  at the 2026 low-so-far: MVRV %.3f, its 4y percentile %.3f; trailing-4y p10 %.3f p20 %.3f" % (g["mvrv"][i26], g["mvrv_r4y"][i26], *np.nanquantile(g["mvrv"][i26 - 1459:i26 + 1], [0.1, 0.2])))

ind2 = ind.with_columns(pl.Series("cbbi", cbbi), pl.Series("fng", df.join(E.select("date", "fng"), on="date", how="left")["fng"].to_numpy().astype(float)),
                        pl.Series("mvrv_approx", approx), *[pl.Series(k, g[k]) for k in ("mvrv_r3y", "mvrv_r5y")])
ind2.write_parquet(f"{out_dir}/indicators2.parquet")
np.savez(f"{out_dir}/flags2.npz", **{f"{k}|{s}": v[s] for k, v in flags.items() for s in ("cheap", "exp") if v[s] is not None})
json.dump(res, open(f"{out_dir}/scores2.json", "w"), indent=1)
