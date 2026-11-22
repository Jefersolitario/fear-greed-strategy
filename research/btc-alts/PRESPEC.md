# Pre-specification: coins following Bitcoin, and crypto pair trading after costs

Written on 22 Nov 2026, before any data on other coins or any backtest result was seen. The git history of
this branch shows the order: this file is committed before the first data run. Anything that was changed
after results were seen is listed in `REPORT.md` under "Deviations from the pre-specification".

Research only. No orders, no API keys. Spot prices from Binance's public market-data API stand in for
perpetual-futures prices throughout.

## Common definitions

- **Source.** `https://data-api.binance.vision/api/v3/klines` (spot, USDT pairs). Bulk files from
  `https://data.binance.vision/` only for perpetual funding rates, if that host answers GitHub's servers.
- **Point-in-time universe.** For a date D (00:00 UTC): all Binance spot USDT pairs that have a bar in the
  24 hours before D, minus exclusions, ranked by the sum of quote volume over the 30 days before D.
  "Top 100" is ranks 1 to 100 of that list. This is a liquidity ranking on one exchange, not market
  capitalisation. Tiers: ranks 1-10, 11-30, 31-100 (Bitcoin is in the ranking; it is reported separately).
- **Exclusions** (decided on names and on trailing data only): stablecoins and fiat (static list), wrapped,
  staked or commodity-pegged tokens (static list), leveraged tokens (`*UP`/`*DOWN` pairs, `*BULL`/`*BEAR`),
  and any pair whose hourly log-return standard deviation over the 30 days before D is below 8 bps
  (catches pegged tokens missing from the static list).
- **Trailing beta.** OLS slope of the coin's hourly log return on Bitcoin's over the 720 hours that end
  before the event hour (at least 360 valid hours), nothing later.
- **Costs** (per side, on traded notional): taker fee 5 bps on perpetuals; half-spread 2 bps for ranks
  1-10, 5 bps for 11-30, 10 bps for 31-100; maker case: 2 bps fee and no spread cost, reported as an optimistic
  bound (it ignores missed fills and adverse selection); funding from Binance's published history where
  the perpetual existed, otherwise zero plus a sensitivity. Spot taker fee of 10 bps is reported as a
  second sensitivity.
- **Seeds.** Every random draw uses `numpy.random.default_rng(20261122 + k)` with k fixed in the code.
- **Split in time.** Part 1: events of 2023-2024 (selection) against 2025-2026 (evaluation).
  Part 2: trading windows that start before 2024-01-01 (selection) against the rest (evaluation).

## Part 1: how fast the other coins follow a Bitcoin shock

### 1.1 Events (Bitcoin only)

- Period: 2023-01-01 00:00 UTC to the last complete UTC day before the run.
- At each second s, `r60(s) = C(s) / C(s - 60 s) - 1` on BTCUSDT 1-second closes. A down trigger is
  `r60 <= -theta`, an up trigger `r60 >= +theta`. This is a rolling 1-minute return, so the trigger can be
  computed in real time and does not depend on what happens after it.
- Clusters: a trigger with no trigger of the same sign in the 2 hours before it starts a new event; the
  event is that first trigger. The trigger time `t*` is the end of the trigger second.
- `theta` is taken from the grid 0.40, 0.50, 0.60, 0.75, 1.00, 1.25, 1.50 %: the value whose number of
  down events lies in [50, 150] and is closest to 100 (ties: the larger theta; if none lies in the range,
  the closest to 100). The up set uses the same theta. Only Bitcoin data enters this choice.
- To avoid downloading four years of 1-second data, minutes are screened on 1-minute bars with the
  necessary condition `low(M) <= (1 - 0.40%) * high(M-1)` (mirror for up) and the rolling return is then
  computed on 1-second bars for those minutes only.
- Placebo windows: 100 random seconds, uniform over the period, at least 2 hours from any trigger at the
  smallest theta and from each other.

### 1.2 Event study

- For each event and each coin of the point-in-time top 100: 1-second bars from `t* - 120 s` to `t* + 3600 s`.
- Cumulative log return from the close at `t* - 60 s` (the base of the Bitcoin trigger return) to
  `t* + lag`, lag in {0, 1, 2, 5, 15, 60, 300, 900, 3600} s, on last-trade closes.
- Reported by tier: (a) mean cumulative return per lag; (b) the share of the +60 min move completed at
  each lag as a ratio of event means, and the median and interquartile range of per-event ratios for events
  whose tier move at +60 min is at least 25 bps in absolute value; (c) the lag at which half of the +60 min
  move is completed, next to Bitcoin's own; (d) the same with the +60 s move as denominator (the shock
  itself, less contaminated by later news); (e) the catch-up ratio `sum(coin move) / sum(beta * BTC move)`
  at each lag; (f) the share of coins that have traded since the trigger at each lag, because a last-trade
  price that has not updated is not a price one can sell at.
- One event is one observation. Confidence intervals: bootstrap over events (10,000 draws).
- Placebo: the same statistics on the random windows. Asymmetry: the same on the up set.

### 1.3 Lead-lag outside the events

- On the random windows: correlation and lagged beta of the coin's 1-second log return at `t + k` with
  Bitcoin's at `t`, k from -60 to +60 (negative k is the control: the coin leading Bitcoin).
- Fresh-price version, to separate a real delay from stale last-trade prices: for seconds in which the coin
  traded, regress its return from that second's VWAP to its close h seconds later (h = 5, 60) on Bitcoin's
  return in the single second g seconds earlier (g = 1, 2, 3, 5, 10).
- Inference: bootstrap over windows.

### 1.4 Is the lag tradeable?

- Decision at `t* + d`, d in {1, 2, 5, 60} s, on bars that have closed by then. A coin is a laggard if
  Bitcoin's move so far `b(d)` is negative and the coin's move `m(d) > 0.5 * beta * b(d)` (it has done less
  than half of its beta-implied move). Coins without a positive trailing beta are skipped.
- Sell each laggard at the first second after the decision second in which it trades (give up after 60 s),
  buy back at the first traded second at or after entry + H, H in {30 s, 5 min, 30 min}.
- Variants (all declared here): outright short; short hedged with `beta` units of Bitcoin bought and sold
  at the same seconds. 4 delays x 3 horizons x 2 = 24 cells.
- PnL per event = equal-weighted mean over that event's trades; events without a laggard count as zero
  trades and are reported. Three prices: (i) gross on VWAP of all trades; (ii) net of the assumed costs
  above (primary); (iii) executable proxy: enter at that second's taker-sell VWAP, exit at the taker-buy
  VWAP, minus fees only.
- Control: the same trade on the coins that are not laggards. Mirror: buy laggards after up events.
- Inference: bootstrap over events; Bonferroni over the 24 cells; the best cell on 2023-2024 is evaluated
  once on 2025-2026. Capacity: quote volume traded in the 5 seconds after the decision.

## Part 2: pair trading after costs

### 2.1 Data and windows

- Hourly bars, 2021-01-01 to the last complete hour before the run. Gaps of up to 6 hours inside a
  listing are filled with the last close; longer gaps are missing data.
- Formation 60 days, trading 30 days, rolled every 30 days: `T_k = 2021-03-02 + 30 k` days; only complete
  trading windows.
- Universe at `T_k`: top 100 as above, restricted to pairs with a bar in every hour of the formation window.

### 2.2 Selection (top 20 pairs per method per window)

- **Distance**: prices divided by their value at the start of formation; sum of squared differences over
  the formation window; the 20 smallest. Spread = difference of normalised prices.
- **Cointegration**: Engle-Granger on hourly log prices, constant in the cointegrating regression, ADF on
  the residual with one lag and no constant; both orderings are run and the one with the more negative
  statistic is kept; hedge ratio must be positive; the 20 most negative statistics. Spread = OLS residual.
  The number of pairs passing Benjamini-Hochberg at 5% per window is reported.

### 2.3 Trading rule

- z = (spread - formation mean) / formation standard deviation, on hourly closes.
- Flat and |z| >= 2 (and < 4): open, short the rich leg and long the cheap leg, one unit of notional each
  (dollar-neutral), no rebalancing. Close when z crosses 0. Stop when |z| >= 4 against the position; a
  stopped pair is not reopened in that window. Everything is closed at the window end. If a leg stops
  trading, the pair is closed at its last price.
- Signals on the close of hour t are filled at the open of hour t+1.
- Variants (the only ones): entry at 1.5; entry at 2.5; volatility-scaled notional (weight proportional
  to 1 / formation standard deviation of the hourly return difference, mean weight 1 over the 20 pairs,
  entry 2). With two methods that is 8 configurations.
- Return = PnL / (20 pairs x 2 legs x 1 unit), i.e. on committed gross notional, daily, UTC days.
- Execution sensitivity (not a variant for selection): fill one bar later.

### 2.4 The owner's idea: overshoot and reversion after a Bitcoin shock

- Events: the Part 1 down events (primary). Robustness: hourly shocks 2021-2026, Bitcoin hourly close-to-close
  return <= -theta_h, theta_h from {2, 2.5, 3, 4, 5} % by the same count rule, clusters separated by 24 hours.
- Shock bar h contains the trigger. `AR = [log C(h+1) - log C(h-1)] - beta * same for Bitcoin`.
- At the open of bar h+2: buy the 10 coins of the top 100 with the most negative AR, each hedged by a
  short of `beta` units of Bitcoin; close at the open H hours later, H in {4, 24, 72}; primary H = 24.
- Also reported: mean AR (do coins fall more than beta implies?), the mean per-event cross-sectional slope
  of the post-event hedged return on AR, the aggregate (all coins) hedged return, and the mirror on up events.
- Placebo: the same rule at 1,000 random hours at least 24 hours from any event.

### 2.5 Benchmarks and inference

- Placebo portfolios: 1,000 draws of 20 random pairs per window from the same universe, same rule, same
  costs, for every configuration; the strategy's percentile in that distribution; the best configuration
  against the distribution of the best-of-8 placebo.
- Stationary block bootstrap of daily net PnL (mean block 30 days, 10,000 draws).
- Results by calendar year. Deflated Sharpe ratio with N = 8. Expected shortfall (5%), worst day, worst
  5 days and maximum drawdown next to Sharpe.
- The best configuration on the selection period is evaluated once on the evaluation period.
- Hindsight check: the 20 best pairs of each window chosen after the fact, and whether a pair's PnL in one
  window predicts its PnL in the next (rank correlation), to show what naming winners afterwards is worth.
- Capacity: hourly quote volume of the thinner leg in the signal bar.

## Addendum, 22 Nov 2026, still before any data run: the owner's prior P1

The owner stated, before any result existed: **"pair trading will be full of competitors, so the edge should be
small unless you are very fast."** It is tested directly, with these additions (all counted as declared variants):

- **Part 1.** One table of the lag rule's net PnL against the reaction delay, so the decay with speed is
  visible. Delays 1, 2, 5 and 60 s as above (the owner's bot reacts in about one to two seconds), plus a
  delay of 0 s (decision at the end of the trigger second, fill in the next traded second) as a reference
  for an actor faster than the owner. The 0 s row is not tradeable for the owner and is not part of the
  24-cell family.
- **Part 2, one bar late.** Every configuration is run twice: fills at the open of the bar after the
  signal (within seconds of the signal, "on time"), and every entry and exit one full bar later ("late").
  Both net results are reported side by side. This replaces the "execution sensitivity" line of 2.3.
- **Part 2, 5-minute bars.** The base rule (entry 2, exit 0, stop 4) for both selection methods on
  5-minute bars, the 30 most liquid coins (point-in-time top 30 at each formation end), the most recent
  12 months, with the same number of bars as the hourly test: formation 1,440 bars (5 days), trading 720
  bars (2.5 days), rolled every 720 bars, top 20 pairs of the 435, on time and one bar late. Same costs.
- **Trials for the deflated Sharpe ratio**: hourly 8 configurations x 2 timings + 5-minute 2 x 2 = 20.
- **What would count for or against P1.** For: net results that are zero or negative at the owner's speed
  while gross results or the faster rows are clearly positive, and a loss of most of the gross edge from
  one bar of delay. Against: a net edge at 1-2 s (Part 1) or on time at hourly bars (Part 2) that survives
  costs, the placebo and the split in time, or no dependence of the result on speed at all.

## Addendum 2, 22 Nov 2026, still before any Part 1 or Part 2 result: trade size

From the owner: a trade is about **1,000 USD** (per leg for pairs). That size is the main case for capacity
and slippage; 10,000 USD is shown only as a reference line.

- Part 1: for the laggard trades, the quote volume that actually traded in the entry second, in total and
  on the side the rule trades on, against 1,000 and 10,000 USD.
- Part 2: 1,000 and 10,000 USD against the quote volume of the thinner leg in the signal bar; and the net
  results recomputed with the measured cost of crossing today's spot order books with 1,000 and 10,000 USD
  (median and 75th-percentile coin of each tier, four snapshots, `s2_depth.py`) in place of the assumed
  half-spreads. The assumed costs stay the primary cost model for the placebo and the inference, because
  an order-book snapshot of today is not point-in-time for 2021-2026.
- The 5-minute test keeps the same number of bars as the hourly test (5 days formation, 2.5 days trading).
  Whether the owner prefers the same calendar windows instead was asked through the coordinator.

## Addendum 3, 22 Nov 2026, still before any Part 1 or Part 2 result: the 5-minute test in two forms

The owner's answer: run both, and keep them apart in the report.

- **5-minute A (same number of bars)**: formation 1,440 bars (5 days), trading 720 bars (2.5 days), rolled every
  2.5 days. It answers whether a faster strategy has an edge.
- **5-minute B (same calendar windows)**: formation 60 days, trading 30 days, as in the hourly test, with
  5-minute bars; trading windows end at the data end. It answers whether finer timing improves the slow trade.
- Both: the 30 most liquid coins, the most recent 12 months of 5-minute data, top 20 of the 435 pairs, base
  rule, on time and one bar late. The number of trading windows each rests on is reported.
- Trials for the deflated Sharpe ratio: hourly 16 + A 4 + B 4 = 24.
