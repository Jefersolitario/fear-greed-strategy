# Pre-registration: does on-chain data predict 1-, 7- and 30-day returns of BTC and ETH?

Written 2026-11-22 after the hindsight audit (section A) and BEFORE any script touched a forward return.
The local git history of this folder records the order: this file is committed before any `b*_` script is run.
Anything that deviates from this file is listed in REPORT.md under "Deviations".

## A. Audit definitions (already executed: `scripts/a1_vintage_pass.py`, `scripts/a2_audit_stats.py`)

Honest note on ordering: the thresholds below were fixed after I had seen raw counts of changed cells per metric
(output of a1) but before revision shares/sizes/timing were computed (a2). No return data is involved in the audit.

- Vintages: every commit touching `csv/btc.csv` / `csv/eth.csv`, 2020-01-24 .. 2025-06-19 (pre-rewrite history,
  recovered from fork `wds33817/data`, cross-checked against upstream `refs/pull/3` and seven other forks) and
  2026-03-26 .. 2026-05-24 (upstream `master`, re-initialised on 2026-03-26). No history exists for
  2025-06-20 .. 2026-03-25.
- Real-time date: first appeared in a commit later than the one that introduced the column, and not first seen
  in the first post-gap commit. Backfilled date: everything else.
- Revised: |final - first| > 1e-9 * max(|final|, |first|). Material: |final - first| > 0.10 x local scale, where
  local scale = median |x_t - x_{t-1}| of the final series over the 365 days ending at the date.
- Publication lag: commit time of first appearance minus 24:00 UTC of the data date.
- Classes: **safe** = material share <= 1% on real-time dates AND on backfilled dates, with >= 3 years of real-time
  vintages; **first-published / vintage only** = fails either 1% test but has >= 3 years of real-time vintages;
  **unusable** = under 3 years of real-time vintages (cannot be audited).

## B. Hypothesis

H0 (per test): the coefficient b in  r(d,h) = a + b * s(d) + e  is zero, where s(d) is an on-chain signal that was
knowable at decision time d and r(d,h) is the forward h-day log return. Two-sided.
Global question: does any on-chain signal survive false-discovery control, hold out of sample, beat buy-and-hold
after costs, and add information beyond price?

## C. Timing (point-in-time rules)

- Decision time for decision day d: 00:00 UTC at the start of calendar day d. Entry price E(d) = PriceUSD(d-1)
  (Coin Metrics daily close = reference rate at 00:00 UTC of d).
- Forward return: r(d,h) = ln( PriceUSD(d-1+h) / PriceUSD(d-1) ), h in {1, 7, 30} days. Daily sampling, so the
  7- and 30-day returns overlap.
- Measured publication lag (audit): median 13.2-13.6 h after the end of the data day, 98% within 24 h. Therefore a
  metric value for data day D is treated as available from decision day D+2 (00:00 UTC), never earlier.
- **V-sample (vintage, fully point-in-time):** s(d) is computed from the file exactly as committed in the last commit
  whose commit time is < 00:00 UTC of d (all rows of that file, including its revised history as known then).
  If the newest data date of the metric in that file is older than d-9, the observation is dropped (stale).
  Decision days 2020-01-25 .. 2026-05-23 minus the stale gap (2025-06-20 .. 2026-03-26).
- **L-sample (long history, metrics classed safe only):** s(d) uses the last vintage (2026-05-24) with data through
  d-2 only. BTC decision days 2012-01-01 .. 2026-05-23, ETH 2017-01-01 .. 2026-05-23. Caveat stated up front:
  values for data dates before 2020-01-23 are the values of the 2020-01-24 vintage (identical to today's) and
  cannot be verified as first-published.
- Price baselines use prices through E(d) (the entry price itself); prices are observable live.
- Outcome prices: PriceUSD of the last vintage (audited: BTC 4 of 2,034 real-time days changed, by < 0.1% of a
  daily move; ETH none).

## D. Signals

Base series y(t) per metric (t = data date):
- flow-type (daily totals with weekly seasonality): y = ln(mean of the last 7 daily values, at least 5 present).
  Metrics: AdrActCnt, TxCnt, TxTfrCnt, FeeTotNtv, HashRate, BlkCnt, FlowInExNtv, FlowOutExNtv, TxTfrValAdjUSD, NVTAdj.
  NetFlowEx = (FlowInExNtv - FlowOutExNtv) / SplyCur: 7-day mean, no log (can be negative).
- stock/ratio-type: y = ln(latest daily value). Metrics: AdrBalCnt, CapMVRVCur, CapRealUSD (= CapMrktCurUSD /
  CapMVRVCur), Puell (= IssTotUSD / trailing-365d mean of IssTotUSD, BTC only), NVTAdj90, SplyActPct1yr, VelCur1yr.
- Non-positive inputs to a log are missing.

Transforms (the two primary ones):
- `lvl`  = ( y(t) - mean_365(y) ) / sd_365(y)                  trailing 365 obs ending at t, >= 300 present
- `chg7` = z-score, same trailing 365-day rule, of c(t) = y(t) - y(t-7)
- All z-scores clipped to [-4, 4]. No full-sample statistic enters any signal.

Metric universe (fixed by the audit; on-chain columns only):
- V-sample BTC (18): AdrActCnt, AdrBalCnt*, TxCnt, TxTfrCnt, FeeTotNtv, HashRate, BlkCnt, CapMVRVCur, CapRealUSD,
  Puell, FlowInExNtv*, FlowOutExNtv*, NetFlowEx*, NVTAdj+, NVTAdj90+, TxTfrValAdjUSD+, SplyActPct1yr*+, VelCur1yr*+
- V-sample ETH (16): AdrActCnt, AdrBalCnt*, TxCnt, TxTfrCnt, FeeTotNtv, BlkCnt, CapMVRVCur*, CapRealUSD*,
  FlowInExNtv*, FlowOutExNtv*, NetFlowEx*, NVTAdj+, NVTAdj90+, TxTfrValAdjUSD+, SplyActPct1yr*+, VelCur1yr*+
  (* = real-time vintages start 2021-05-07;  + = dropped from the free file after 2025-06-19, so the sample ends there)
- L-sample BTC (10, all classed safe and still published): AdrActCnt, AdrBalCnt, TxCnt, TxTfrCnt, FeeTotNtv,
  HashRate, BlkCnt, CapMVRVCur, CapRealUSD, Puell
- L-sample ETH (5): AdrBalCnt, TxCnt, TxTfrCnt, FeeTotNtv, BlkCnt
- Excluded a priori: price columns and price-only derivatives (PriceUSD, PriceBTC, ReferenceRate*, ROI*,
  CapMrktCurUSD, CapMrktEstUSD: these are the price baseline, not on-chain); USD duplicates of native flows;
  protocol schedules (SplyCur, SplyExpFut10yr, IssTotNtv); metadata (Asset*CompletionTime); SplyExNtv/SplyExUSD and
  volume_reported_spot_usd_1d (unusable: 60 days of vintages; the latter is not on-chain); ETH HashRate (ended at
  the Merge); the remaining ~110 discontinued columns (address-balance and supply-distribution buckets etc.).
  NVT/transfer value/active supply/velocity are V-sample only because their pre-2020 history is known to have been
  restated (2018 vintage vs 2020 vintage) or cannot be checked.

Price-only baselines (same z-score machinery, on E(d)):
PX_M7 = z365 of ln E(d) - ln E(d-7); PX_M30 = z365 of ln E(d) - ln E(d-30);
PX_DD = z365 of ln( E(d) / running maximum of E ); PX_Z = z365 of ln E(d).

## E. Tests

Primary family = {V-sample, L-sample} x asset x metric x {lvl, chg7} x h in {1, 7, 30}:
V: (18 + 16) x 2 x 3 = 204 tests; L: (10 + 5) x 2 x 3 = 90 tests; 294 in total.

1. In-sample predictive regression, OLS with intercept. Newey-West (Bartlett) standard errors with
   lag = max(5, 2(h-1)) -> 5, 12, 58. Report b in % per h days per 1 sd of signal, t_HAC, p_HAC (normal).
2. Bootstrap p-value (the p-value used for inference): null imposed (b = 0); AR(1) for the signal with Kendall bias
   correction; moving-block resampling (block 60 days) of the paired residuals (daily return residual, signal
   innovation) so that their cross-correlation at all short lags, volatility clustering and the overlap of h-day
   returns are preserved; statistic = t_HAC; B = 5,000; p = (1 + #{|t*| >= |t|}) / (B + 1). Seeds fixed.
3. Placebo: the same regression with the signal circularly shifted by k days, k = 90, 97, ... , T-90; report the
   share of shifts with |t_k| >= |t| and, per family, the expected number of nominal 5% rejections under the
   placebo next to the actual number.
4. Out-of-sample forecasts: expanding-window OLS re-estimated every day on pairs (s(j), r(j,h)) with j + h <= d,
   against the expanding historical mean with the same information. Evaluation period: V from 2023-01-01,
   L from 2021-01-01. Report OOS R2 = 1 - SSE_model / SSE_mean and the Clark-West (2007) one-sided p-value
   (HAC, same lags).
5. Long-or-flat rule: position 1 when q * (s(d) - theta) > 0, else 0; q in {+1, -1}, theta in
   {-1, -0.5, 0, 0.5, 1}. (q, theta) chosen once on the training part (V: before 2023-01-01; L: before
   2021-01-01) by net Sharpe; evaluated once on the later part. Daily re-evaluation, 10 bps per unit of position
   change, cash earns 0. Report annualised return (CAGR), annualised Sharpe (sqrt 365), maximum drawdown, time in
   market, number of trades, against buy-and-hold on the same days; stationary-bootstrap (mean block 30 days,
   B = 2,000) interval and one-sided p for the Sharpe difference; placebo percentile from circular shifts.
6. Beyond price: (i) joint regression r(d,h) on s(d) and the four price baselines, t_HAC of the on-chain
   coefficient and its circular-shift placebo p; (ii) expanding-window OOS: price-only model against price +
   signal, incremental OOS R2 and Clark-West p; (iii) rule Sharpe against the best price-only rule chosen on the
   same training part (4 baselines x 10 rules), bootstrap interval for the difference.
   The four price baselines also run through tests 1-5 as a benchmark family (not counted in the on-chain FDR).
7. Multiple testing: Benjamini-Hochberg at q = 0.10 (also 0.05) on the bootstrap p-values, for the V family, the
   L family and pooled; Benjamini-Yekutieli as the conservative variant; the same on p_HAC for comparison.
8. Stability: b and t_HAC per sub-period. L: start..2020-12-31, 2021-01-01..2023-12-31, 2024-01-01..end.
   V: 2020-01-25..2021-12-31, 2022-01-01..2023-12-31, 2024-01-01..end.

Implementation conventions: observations with a missing signal or return are dropped and the remaining ones are
treated as consecutive for HAC and bootstrap purposes (the V-sample has one 9-month hole); expanding-window
forecasts need at least 365 realised training pairs; a test with fewer than 500 usable observations is reported
as "insufficient data" and not counted.

Robustness variants (reported in full, HAC p-values only, not used to pick anything; BH also reported over the
extended family = primary + variants):
R1 z-window 180 days; R2 z-window 730 days; R3 `chg1` (1-day change of y); R4 `chg30` (30-day change of y);
R5 L-sample with data through d-1 instead of d-2 (infeasible: one day of look-ahead, shown as an upper bound).

## F. Evidence grade (decided here, applied mechanically)

- strong: at least one signal in the V family survives BH (q = 0.10), has OOS R2 > 0 with Clark-West p < 0.05,
  its rule beats buy-and-hold on Sharpe in the test part with a bootstrap interval excluding 0, it adds beyond price
  (joint p < 0.05 and incremental OOS R2 > 0), and its sign is the same in all sub-periods.
- moderate: a BH survivor with OOS R2 > 0 (Clark-West p < 0.10) that fails the tradeable test or the beyond-price
  test or the stability test.
- weak: nominal 5% rejections clearly above the placebo expectation, but no BH survivor, or survivors fail OOS.
- none: nominal rejections in line with the placebo expectation, no BH survivor, OOS R2 <= 0 for the bulk.

## G. Fixed constants

Random seed base 20261122. z-window 365 (min 300). Clip 4. Costs 10 bps per trade. Annualisation 365.
HAC lags 5 / 12 / 58. Bootstrap B = 5,000 (regressions), 2,000 (rules); block 60 / mean block 30.
