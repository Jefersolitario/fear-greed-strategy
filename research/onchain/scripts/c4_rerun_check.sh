#!/usr/bin/env bash
# C4: seeds are fixed, so a second run must give byte-identical result files. Re-runs two of the result scripts
# into a scratch folder and compares. Usage: bash scripts/c4_rerun_check.sh   (from the research folder, ~3 min)
set -euo pipefail
T=$(mktemp -d results/_rerun.XXXXXX)
.venv/bin/python -I scripts/b2_regressions.py data "$T" eth > /dev/null
.venv/bin/python -I scripts/b3_oos_rules.py data "$T" btc > /dev/null
for f in regressions_eth.csv oos_btc.csv rules_btc.csv; do
  cmp "results/$f" "$T/$f" && echo "$f: byte-identical on re-run"
done
rm -rf "$T"
