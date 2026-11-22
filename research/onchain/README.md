# Does on-chain data predict 1-, 7- and 30-day moves of Bitcoin and Ether?

Research only, on its own branch. No orders, no keys, and nothing in this folder is read by the paper-trading job.

**Verdict (22 Nov 2026): no. Evidence grade: none.** In the window where every value can be used exactly as it
stood at decision time (January 2020 to May 2026), 3 of 204 tests pass at the 5% level where chance gives about 10,
none survives false-discovery control, and no long-or-flat rule beats buy-and-hold by more than chance after 10 bps
a trade. An independent review is still to come.

The full report is in the "Trading Ideas" project as `claude/onchain-predictive-study.md`. Where `PREREG.md` and
the scripts say `REPORT.md`, that document is meant.

## What is here

- `PREREG.md`: the tests, fixed before any return data was used.
- `run_all.sh`, `scripts/`, `tests/`, `requirements.txt`: the whole pipeline, from fetching the source to the tables.
- `results/`: every result table. Start with `summary.txt`, `diagnostics.txt` and `lead_check.txt`.
- `audit/`: the hindsight audit of the source: which metrics were changed after first publication, by how much
  and how late (`audit_table.md`), and the list of every file version used (`vintage_index.tsv`).
- `logs/`: the output of every script, and `local_git_history.txt`, the order in which the work was committed
  locally (pre-registration first, results after).

## What is not here, and why

The source is Coin Metrics community network data, `https://github.com/coinmetrics/data`, licensed CC BY-NC 4.0
(attribution, non-commercial use only). It is not redistributed here. That leaves out three things, all of which
`run_all.sh` rebuilds:

- `third_party/`: the clone of the source repository;
- `audit/pass1/`: first and final value of every cell;
- `data/`: the decision-day panels built from the source.

## Reproduce

The study ran on Python 3.13. From this folder:

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt
bash run_all.sh
```

It fetches about 120 MB of history from the public repository and one of its forks and takes about 25 minutes on
2 cores. The source stopped updating on 2026-05-24, and its earlier history survives only in forks, so a later
re-run depends on those forks still being there.
