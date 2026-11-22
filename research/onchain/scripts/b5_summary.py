#!/usr/bin/env python
"""B5: multiple-testing control and summary tables (PREREG.md E.7, E.8, F).

Reads results/{regressions,oos,rules,beyond_price}_{btc,eth}.csv and writes
  results/summary_tests.csv     one row per primary test (294) with every statistic joined
  results/summary_rules.csv     one row per rule (primary + price baselines)
  results/fdr_summary.csv       survivors per family and method
  results/summary.txt           the numbers quoted in REPORT.md

Usage: python -I scripts/b5_summary.py <results_dir>
"""
import os, sys
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats import bh, by, bh_adjust

res = sys.argv[1]
rd = lambda name: pl.concat([pl.read_csv(os.path.join(res, f"{name}_{a}.csv"), infer_schema_length=None)
                             for a in ("btc", "eth")], how="diagonal_relaxed")
reg, oos, rules, bp = rd("regressions"), rd("oos"), rd("rules"), rd("beyond_price")
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); lines.append(s)

key = ["sample", "asset", "metric", "variant"]
prim = reg.filter((pl.col("family") == "primary") & (pl.col("note") == ""))
prim = prim.join(oos.filter(pl.col("family") == "primary").select(key + ["h", "oos_n", "oos_r2", "cw_p"]), on=key + ["h"], how="left")
prim = prim.join(bp.select(key + ["h", "r2_signal_on_price", "b_joint_pct", "t_joint", "p_joint_hac", "placebo_p_joint",
                                  "oos_r2_price_vs_mean", "oos_r2_incremental", "cw_p_incremental"]), on=key + ["h"], how="left")
rcols = ["rule_dir", "rule_theta", "train_sharpe", "train_sharpe_bh", "test_n", "test_cagr", "test_sharpe", "test_maxdd",
         "test_time_in_market", "test_trades", "bh_cagr", "bh_sharpe", "bh_maxdd", "dsharpe_vs_bh", "dsharpe_vs_bh_lo",
         "dsharpe_vs_bh_hi", "dsharpe_vs_bh_p", "placebo_p", "px_rule", "px_test_sharpe", "px_test_cagr", "dsharpe_vs_px",
         "dsharpe_vs_px_lo", "dsharpe_vs_px_hi", "dsharpe_vs_px_p"]
prim = prim.join(rules.filter(pl.col("family") == "primary").select(key + rcols).rename({"placebo_p": "rule_placebo_p"}),
                 on=key, how="left")

# ---------------- false discovery rate
def add_fdr(df, pcol, tag):
    p = df[pcol].to_numpy()
    out = {f"q_{tag}_pooled": bh_adjust(p)}
    smp = df["sample"].to_numpy()
    qf = np.full(len(p), np.nan)
    for s in ("V", "L"):
        m = smp == s
        qf[m] = bh_adjust(p[m])
    out[f"q_{tag}_family"] = qf
    return df.with_columns([pl.Series(k, v) for k, v in out.items()])
prim = add_fdr(add_fdr(prim, "p_boot", "boot"), "p_hac", "hac")
s1, s2, s3 = (np.sign(prim[f"sub{i}_b_pct"].to_numpy()) for i in (1, 2, 3))
full_sign = np.sign(prim["b_pct_per_sd"].to_numpy())
prim = prim.with_columns(pl.Series("same_sign_all_subperiods", (s1 == full_sign) & (s2 == full_sign) & (s3 == full_sign)),
                         (pl.col("n") // pl.col("h")).alias("n_nonoverlap"))
prim.write_csv(os.path.join(res, "summary_tests.csv"))
rules.write_csv(os.path.join(res, "summary_rules.csv"))

fdr_rows = []
P("=== 1. Multiple testing: primary family (bootstrap p unless stated) ===")
for fam, df in (("V (point-in-time, 2020-2026)", prim.filter(pl.col("sample") == "V")),
                ("L (long history, safe metrics)", prim.filter(pl.col("sample") == "L")), ("pooled", prim)):
    pb, ph = df["p_boot"].to_numpy(), df["p_hac"].to_numpy()
    exp_plc = float(df["placebo_share_abs_t_gt_1p96"].sum())
    row = dict(family=fam, n_tests=df.height, nominal_p_boot_lt_05=int((pb < 0.05).sum()), expected_by_chance=0.05 * df.height,
               abs_t_gt_1p96=int((df["t_hac"].abs() > 1.96).sum()), placebo_expected_abs_t_gt_1p96=exp_plc,
               placebo_p_lt_05=int((df["placebo_p"] < 0.05).sum()), min_p_boot=float(pb.min()),
               bh10_boot=int(bh(pb, 0.10).sum()), bh05_boot=int(bh(pb, 0.05).sum()), by10_boot=int(by(pb, 0.10).sum()),
               bh10_hac=int(bh(ph, 0.10).sum()), bh05_hac=int(bh(ph, 0.05).sum()), by10_hac=int(by(ph, 0.10).sum()),
               bh10_placebo=int(bh(df["placebo_p"].to_numpy(), 0.10).sum()))
    fdr_rows.append(row)
    P(f"{fam}: {row['n_tests']} tests | p_boot<0.05: {row['nominal_p_boot_lt_05']} (chance {row['expected_by_chance']:.1f}) | "
      f"|t|>1.96: {row['abs_t_gt_1p96']} (placebo expects {exp_plc:.1f}) | min p_boot {row['min_p_boot']:.4f} | "
      f"BH q=0.10: {row['bh10_boot']}, q=0.05: {row['bh05_boot']}, BY q=0.10: {row['by10_boot']} | "
      f"on HAC p: BH10 {row['bh10_hac']}, BH05 {row['bh05_hac']}, BY10 {row['by10_hac']} | on placebo p: BH10 {row['bh10_placebo']}")
# extended family (primary + robustness variants R1-R4), HAC p only
ext = reg.filter(pl.col("family").is_in(["primary", "R1_z180", "R2_z730", "R3_chg1", "R4_chg30"]) & (pl.col("note") == ""))
for fam, df in (("extended V", ext.filter(pl.col("sample") == "V")), ("extended L", ext.filter(pl.col("sample") == "L")), ("extended pooled", ext)):
    ph = df["p_hac"].to_numpy()
    fdr_rows.append(dict(family=fam, n_tests=df.height, nominal_p_hac_lt_05=int((ph < 0.05).sum()), expected_by_chance=0.05 * df.height,
                         bh10_hac=int(bh(ph, 0.10).sum()), bh05_hac=int(bh(ph, 0.05).sum()), by10_hac=int(by(ph, 0.10).sum())))
    P(f"{fam}: {df.height} tests | p_hac<0.05: {int((ph < 0.05).sum())} (chance {0.05*df.height:.1f}) | BH q=0.10 on HAC p: {int(bh(ph, 0.10).sum())}, BY: {int(by(ph, 0.10).sum())}")
for fam in ("R1_z180", "R2_z730", "R3_chg1", "R4_chg30", "R5_lookahead_1d"):
    for s in ("V", "L"):
        df = reg.filter((pl.col("family") == fam) & (pl.col("sample") == s) & (pl.col("note") == ""))
        if df.height:
            P(f"  variant {fam} {s}: {df.height} tests, p_hac<0.05: {int((df['p_hac'] < 0.05).sum())}, max |t| {float(df['t_hac'].abs().max()):.2f}")
pl.DataFrame(fdr_rows, infer_schema_length=None).write_csv(os.path.join(res, "fdr_summary.csv"))

P("\n=== 2. Sign of the nominally significant coefficients and where they sit ===")
sig = prim.filter(pl.col("p_boot") < 0.05)
for s in ("V", "L"):
    d = sig.filter(pl.col("sample") == s)
    P(f"{s}: {d.height} nominal; positive slope {int((d['b_pct_per_sd'] > 0).sum())}, negative {int((d['b_pct_per_sd'] < 0).sum())}; "
      f"price-built {int(d['price_built'].sum())}; same sign in all three sub-periods {int(d['same_sign_all_subperiods'].sum())}; "
      f"|t|>1.96 in sub-period 1/2/3: {int((d['sub1_t'].abs() > 1.96).sum())}/{int((d['sub2_t'].abs() > 1.96).sum())}/{int((d['sub3_t'].abs() > 1.96).sum())}")

P("\n=== 3. Out of sample (expanding window vs historical mean) ===")
for s in ("V", "L"):
    d = prim.filter(pl.col("sample") == s)
    P(f"{s}: OOS R2 > 0 in {int((d['oos_r2'] > 0).sum())} of {d.height}; median OOS R2 {100*float(d['oos_r2'].median()):.2f}%; "
      f"Clark-West p<0.05: {int((d['cw_p'] < 0.05).sum())}; BH q=0.10 on CW p: {int(bh(d['cw_p'].to_numpy(), 0.10).sum())}")
    for h in (1, 7, 30):
        dh = d.filter(pl.col("h") == h)
        P(f"    h={h}: OOS R2 > 0 in {int((dh['oos_r2'] > 0).sum())} of {dh.height}; median {100*float(dh['oos_r2'].median()):.2f}%; best {100*float(dh['oos_r2'].max()):.2f}%; CW p<0.05: {int((dh['cw_p'] < 0.05).sum())}")

P("\n=== 4. Long-or-flat rules, chosen on the early part, evaluated once on the later part, 10 bps per trade ===")
for s in ("V", "L"):
    d = rules.filter((pl.col("sample") == s) & (pl.col("family") == "primary"))
    P(f"{s}: {d.height} rules; test Sharpe above buy-and-hold: {int((d['dsharpe_vs_bh'] > 0).sum())}; bootstrap p<0.05 vs buy-and-hold: {int((d['dsharpe_vs_bh_p'] < 0.05).sum())}; "
      f"placebo p<0.05: {int((d['placebo_p'] < 0.05).sum())}; above best price-only rule: {int((d['dsharpe_vs_px'] > 0).sum())}, p<0.05: {int((d['dsharpe_vs_px_p'] < 0.05).sum())}; "
      f"median Sharpe difference vs buy-and-hold {float(d['dsharpe_vs_bh'].median()):+.2f}; median train Sharpe {float(d['train_sharpe'].median()):.2f} vs median test Sharpe {float(d['test_sharpe'].median()):.2f}")
    for a in ("btc", "eth"):
        da = d.filter(pl.col("asset") == a)
        if da.height:
            P(f"    {a}: buy-and-hold test Sharpe {float(da['bh_sharpe'].max()):.2f} (longest window), rules above it: {int((da['dsharpe_vs_bh'] > 0).sum())} of {da.height}; "
              f"BH q=0.10 on bootstrap p: {int(bh(da['dsharpe_vs_bh_p'].to_numpy(), 0.10).sum())}")
    P(f"    BH q=0.10 across all {d.height} rules of the sample (bootstrap p vs buy-and-hold): {int(bh(d['dsharpe_vs_bh_p'].to_numpy(), 0.10).sum())}; (placebo p): {int(bh(d['placebo_p'].to_numpy(), 0.10).sum())}")

P("\n=== 5. Beyond price (joint regression with four price baselines; incremental OOS R2) ===")
for s in ("V", "L"):
    d = prim.filter(pl.col("sample") == s)
    P(f"{s}: joint p_hac<0.05: {int((d['p_joint_hac'] < 0.05).sum())} of {d.height} (chance {0.05*d.height:.1f}); joint placebo p<0.05: {int((d['placebo_p_joint'] < 0.05).sum())}; "
      f"BH q=0.10 on joint HAC p: {int(bh(d['p_joint_hac'].to_numpy(), 0.10).sum())}, on joint placebo p: {int(bh(d['placebo_p_joint'].to_numpy(), 0.10).sum())}; "
      f"incremental OOS R2 > 0: {int((d['oos_r2_incremental'] > 0).sum())}; CW p<0.05: {int((d['cw_p_incremental'] < 0.05).sum())}; BH q=0.10 on CW p: {int(bh(d['cw_p_incremental'].to_numpy(), 0.10).sum())}")
    dsig = d.filter(pl.col("p_boot") < 0.05)
    P(f"    of the {dsig.height} nominally significant univariate tests: still p<0.05 jointly (HAC): {int((dsig['p_joint_hac'] < 0.05).sum())}; (placebo): {int((dsig['placebo_p_joint'] < 0.05).sum())}; "
      f"median |t| univariate {float(dsig['t_hac'].abs().median()) if dsig.height else float('nan'):.2f} -> joint {float(dsig['t_joint'].abs().median()) if dsig.height else float('nan'):.2f}; "
      f"incremental OOS R2 > 0: {int((dsig['oos_r2_incremental'] > 0).sum())}")

P("\n=== 6. Price-only baselines through the same tests ===")
pxr = reg.filter(pl.col("family") == "price_baseline").join(oos.filter(pl.col("family") == "price_baseline").select(key + ["h", "oos_r2", "cw_p"]), on=key + ["h"], how="left")
for s in ("V", "L"):
    d = pxr.filter(pl.col("sample") == s)
    P(f"{s}: {d.height} tests; p_boot<0.05: {int((d['p_boot'] < 0.05).sum())}; OOS R2 > 0: {int((d['oos_r2'] > 0).sum())}; CW p<0.05: {int((d['cw_p'] < 0.05).sum())}")
    dr = rules.filter((pl.col("sample") == s) & (pl.col("family") == "price_baseline"))
    P(f"    rules: {dr.height}; above buy-and-hold: {int((dr['dsharpe_vs_bh'] > 0).sum())}; bootstrap p<0.05: {int((dr['dsharpe_vs_bh_p'] < 0.05).sum())}")

P("\n=== 7. Mechanical grade (PREREG.md F) ===")
V = prim.filter(pl.col("sample") == "V")
surv = V.filter(pl.col("q_boot_family") <= 0.10)
strong = surv.filter((pl.col("oos_r2") > 0) & (pl.col("cw_p") < 0.05) & (pl.col("dsharpe_vs_bh_lo") > 0) & (pl.col("p_joint_hac") < 0.05)
                     & (pl.col("oos_r2_incremental") > 0) & pl.col("same_sign_all_subperiods"))
moderate = surv.filter((pl.col("oos_r2") > 0) & (pl.col("cw_p") < 0.10))
nomV, expV = int((V["t_hac"].abs() > 1.96).sum()), float(V["placebo_share_abs_t_gt_1p96"].sum())
P(f"V family: BH(q=0.10) survivors {surv.height}; of which meeting every 'strong' condition {strong.height}; meeting 'moderate' {moderate.height}; "
  f"nominal |t|>1.96 {nomV} vs placebo expectation {expV:.1f}; p_boot<0.05 {int((V['p_boot'] < 0.05).sum())} vs chance {0.05*V.height:.1f}; "
  f"OOS R2 > 0 in {int((V['oos_r2'] > 0).sum())} of {V.height}")
grade = "strong" if strong.height else "moderate" if moderate.height else ("weak" if (nomV > 1.5 * expV and int((V['p_boot'] < 0.05).sum()) > 1.5 * 0.05 * V.height) else "none")
P(f"Grade for the point-in-time (V) family by the pre-registered rule: {grade}")

P("\n=== 8. Sample sizes: daily observations and the number of non-overlapping h-day periods they contain ===")
for s_ in ("V", "L"):
    for a in ("btc", "eth"):
        d = prim.filter((pl.col("sample") == s_) & (pl.col("asset") == a))
        for h in (1, 7, 30):
            dh = d.filter(pl.col("h") == h)
            P(f"{s_} {a} h={h:2d}: daily n min/median/max {int(dh['n'].min())}/{int(dh['n'].median())}/{int(dh['n'].max())}; "
              f"non-overlapping periods min/median/max {int(dh['n_nonoverlap'].min())}/{int(dh['n_nonoverlap'].median())}/{int(dh['n_nonoverlap'].max())}; "
              f"first decision day {dh['first'].min()} .. last {dh['last'].max()}")
open(os.path.join(res, "summary.txt"), "w").write("\n".join(lines) + "\n")
