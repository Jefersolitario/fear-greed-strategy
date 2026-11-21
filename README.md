# fear-greed-strategy

Buy bitcoin when the Crypto Fear & Greed index is low. This repository holds the backtest, the paper-trading
job and the published results that the portfolio dashboard reads
([portfolio-trading-strategies](https://github.com/Jefersolitario/portfolio-trading-strategies)).

**Status: paper trading only. No real orders are sent.**

## The rules

| | Paper traded | Rule |
|---|---|---|
| `fng10_hold` | no | Buy 1,000 USD of BTC on every day the index is below 10. Never sell. |
| `fng20_below_2y_avg` | no | Buy 1,000 USD on every day the index is below 20, if the previous close was below its 730-day average. Never sell. |
| `fng20_hold` | no | Buy on every day the index is below 20. |
| `cmc_le10_sell80` | yes, the portfolio | The same rule as the next line, read on CoinMarketCap's Fear and Greed index, one day late: the value of the day before decides. |
| `fng_le10_sell80` | yes, monitoring only | Buy 1,000 USD on every day the index is 10 or lower. Sell everything on the first day it is at or above 80. |
| `fng_le15_sell80` | yes, monitoring only | The same with 15 as the threshold. Published for comparison; dashboards keep it out of portfolio totals. |
| `fng10_sell80` | no | The same with a strict threshold: buy only when the index is below 10. |
| `fng20_mayer` | no | Buy below 20, if the previous close was more than 20% under its 200-day average. |

Only `cmc_le10_sell80` is in the portfolio, since 21 Nov 2026. That day the owner moved the portfolio from
Alternative.me's index to CoinMarketCap's. A rule on another index is a different rule, so it has a new id, its own
backtest and a paper book that starts flat; `fng_le10_sell80` keeps running for comparison. The section on
CoinMarketCap's index below says what the evidence for the move is, and it is thin.

Until 18 Nov 2026 the rule in the portfolio bought strictly below 10; it was
changed to include 10 before any paper fill had happened, and it got a new id because a different rule has a
different history. The hold rules were dropped on 17 Nov 2026: their Sharpe on dollar PnL is
about 0.25 and their drawdowns are larger than their profits. They stay in the backtest table as tested variants.

Conventions, the same in the backtest and in paper trading:

- Alternative.me's value stamped day D is published around 00:00 UTC on D. The buy is filled at the **UTC close of D**.
- CoinMarketCap's daily value is, in its own words, the value at 12am UTC, and nothing says when a day's value is
  published. The rule on it therefore waits a day: the value stamped D-1 decides the trade at the UTC close of D.
- Price filters use the close of D-1 only.
- 10 bps cost per side, cash earns 0%, PnL = BTC value + sale proceeds - dollars put in.
- Paper books start flat on `paper_start` in `strategies.toml`. Backtest lots are not carried over.

## Backtest, 1 Feb 2018 to 14 Nov 2026

| Rule | Buys | PnL | Return on money in | Sharpe | Sortino | Max drawdown | Placebo p |
|---|---|---|---|---|---|---|---|
| F&G under 10, hold | 42 | +$107,780 | +257% | 0.25 | 0.36 | -$135,139 | 0.40 |
| F&G under 20, below 2-year average | 228 | +$991,848 | +435% | 0.27 | 0.39 | -$1,181,455 | 0.16 |
| F&G under 20, hold | 350 | +$1,567,975 | +448% | 0.25 | 0.36 | -$1,895,742 | 0.14 |
| F&G 10 or lower, sell all at 80 | 69 | +$41,610 | +60% | 0.75 | 1.19 | -$10,403 | n/a |
| F&G 15 or lower, sell all at 80 | 244 | +$153,811 | +63% | 0.85 | 1.36 | -$29,987 | n/a |
| F&G under 10, sell all at 80 | 42 | +$24,392 | +58% | 0.68 | 1.07 | -$7,675 | n/a |
| F&G under 20, Mayer below 0.8 | 237 | +$1,079,517 | +455% | 0.26 | 0.37 | -$1,294,473 | 0.18 |

Sharpe and Sortino are on daily dollar PnL from the first buy, times the square root of 365, zero risk-free
rate. Max drawdown is the largest peak-to-trough fall of cumulative PnL. Placebo p is the share of circular
date-shifts of the buy days that end with at least as much PnL.

### How much to believe it

- **The evidence for an edge is weak.** No hold rule beats its own date-shifted placebo at the usual 5% level
  (p 0.14 to 0.40). Buying the same number of dollars on random days did about as well.
- **One period carries the result.** About 93% of the base rule's PnL comes from lots bought in 2018 to 2020.
  Lots bought since 2024 are slightly underwater (about -$10K).
- **The price filters do not add return.** They cut the dollars at risk by about a third; return per dollar
  is unchanged (435% and 455% against 448%).
- **Sharpe on dollar PnL understates an accumulate-and-hold rule** because the position keeps growing. Per
  dollar at risk the base rule's Sharpe is 0.68.
- **The sell-at-80 Sharpe of 0.68 rests on three closed round trips,** and it is measured on dollar PnL, which
  flatters a rule that is in cash on 44% of days. Per dollar at risk its Sharpe is 0.45, below the hold rules.

Paper trading exists to find out whether any of this holds on days nobody has seen yet.

## CoinMarketCap's index, 30 Jun 2023 to 20 Nov 2026

CoinMarketCap's index starts on 29 Jun 2023, so this is all the history there is: 3.4 years and one cycle. Both
books below start flat on that day and use the rule "10 or lower, sell all at 80".

| Index | Buys | Sales | PnL | Return on money in | Sharpe | Max drawdown |
|---|---|---|---|---|---|---|
| CoinMarketCap, value of the day before | 11 | 1 | +$899 | +8.2% | 0.32 | -$3,292 |
| Alternative.me, value of the day | 35 | 0 | -$5,026 | -14.4% | -0.36 | -$13,103 |

- **The whole difference is one sale.** CoinMarketCap's index reached 80 to 82 on 24 to 27 Aug 2026 and the book was
  sold at 78,500. Alternative.me's index read 65 to 74 on those days and has peaked at 79 since its first buy here.
- **Its buys were not better.** Alternative.me's buys closed with CoinMarketCap's sale make +$4,048 (+11.6%).
- **The sell level is what is fragile.** Selling at 75 instead of 80 on Alternative.me's index makes +$7,851 (+22.4%)
  over the same days.
- **Three buy episodes and one sale are not evidence** that one index is better than the other. The published
  backtest of this rule can never be longer than the index itself.

The two indexes agree most of the time (correlation 0.90). CoinMarketCap's was at 10 or lower on 12 days,
Alternative.me's on 35, and 7 of those days are shared. Sharpe is measured from each book's first buy, as in the
table above; `research/cmc_backtest.py` reproduces the rest and reports Sharpe over the whole window instead
(0.17 and -0.25).

## How it runs

`.github/workflows/paper.yml` runs twice a day. It appends the last complete UTC day to
`data/live_daily.csv` (index from alternative.me, close from Coinbase with Kraken as the fallback) and the
CoinMarketCap value that day was decided on to `data/cmc_live.csv`, recomputes the books and commits `results/`.
CoinMarketCap's keyless public API is used; if the repository has a secret named `CMC_API_KEY`, the keyed API is
used instead. A run that is late, skipped or repeated only delays the record: a day is appended only when all its
inputs are there, and never out of order. Four guards stop a run instead of quietly rewriting history:

- a fetched value that disagrees with a stored input day, for either index or the close;
- a published day whose PnL would change (`--allow-restate` overrides this on purpose);
- a paper day that would be added after results for that day were already published without it, which is what
  happens when a rule is merged after its `paper_start`. The message says which `paper_start` to set;
- three complete days in a row that cannot be appended. The message says which input is missing.

GitHub runs schedules on a best-effort basis and switches them off in public repositories after 60 days
without repository activity. The daily commit counts as activity. If a schedule ever stops, use
*Actions → paper-trading → Run workflow*; the job catches up on every missing day.

```bash
pip install -e ".[dev]"
pytest -q                          # reproduces the audited backtest numbers
python -m fng.cli run              # recompute from stored inputs into ./results
python -m fng.cli run --fetch      # first append new complete days from the live sources
```

## Published results: the contract

Every strategy in the portfolio publishes the same files, so the dashboard needs no strategy-specific code.

```
results/
  index.json                   strategy ids, contract version, last update
  backtest_summary.parquet     one row per tested variant
  <strategy_id>/manifest.json  name, market, currency, days per year, start dates, code version, role
  <strategy_id>/daily.parquet  date, mode (backtest | paper | live), pnl, capital, n_trades
```

`pnl` is that day's PnL in the manifest currency. It is not cumulative and not a return: daily PnL is the one
form that adds up across strategies and re-bases to any date range. `capital` is the market value of open
positions at the close. The dashboard computes every statistic itself. A manifest `role` of `monitor` marks a
strategy that is published for comparison only and stays out of portfolio totals.

`--out` accepts any fsspec location, so the same command publishes to a bucket:
`python -m fng.cli run --fetch --out gs://<bucket>/fear-greed-strategy` (see [docs/gcs.md](docs/gcs.md)).

## Data

- `data/inputs_snapshot.csv`: the daily inputs behind the backtest. Fear & Greed values are from
  [alternative.me](https://alternative.me/crypto/fear-and-greed-index/). Closes are Coin Metrics community
  reference rates to 23 May 2026 (CC BY-NC 4.0) and the Binance BTCUSDT 00:00 UTC price after that.
- `data/live_daily.csv`: days appended by the scheduled job.
- `data/cmc_snapshot.csv`: CoinMarketCap's daily Fear and Greed values from 29 Jun 2023 to 20 Nov 2026, downloaded
  from its keyless public API on 21 Nov 2026 with `research/fetch_cmc_fng.py`. `data/cmc_live.csv`: the values
  appended since, each one a day after its date.
- The index has 4 missing days in its own history (2018-04-14, 2018-04-15, 2018-04-16, 2024-10-26). A day without a value is a day without a signal.

## research/

The scripts behind the numbers above, kept as they were run: the original backtest, its independent
recomputation and sensitivity checks, and the cycle-indicator study. They read raw files that are not
redistributed here, so they document the work rather than run out of the box. The two CoinMarketCap scripts
(`fetch_cmc_fng.py`, `cmc_backtest.py`) do run as they are.
