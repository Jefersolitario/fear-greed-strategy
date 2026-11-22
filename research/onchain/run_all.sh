#!/usr/bin/env bash
# Rebuilds every number of the study from the public repository. About 25 minutes on 2 cores.
# Usage: bash run_all.sh        (from this folder; needs .venv, see requirements.txt)
set -euo pipefail
PY=".venv/bin/python -I"
R=third_party/cm_data
# ---- A. data and hindsight audit
bash scripts/a00_fetch_history.sh "$PWD"                                   # history of csv/btc.csv, csv/eth.csv (~120 MB)
$PY scripts/a0_header_inventory.py $R audit/vintage_index.tsv audit       > logs/a0_header_inventory.log
$PY scripts/a1_vintage_pass.py $R audit/vintage_index.tsv audit/pass1 btc > logs/a1_vintage_pass_btc.log
$PY scripts/a1_vintage_pass.py $R audit/vintage_index.tsv audit/pass1 eth > logs/a1_vintage_pass_eth.log
$PY scripts/a2_audit_stats.py audit/pass1 audit                            > logs/a2_audit_stats.log 2>&1
$PY scripts/a3_legacy_2018_check.py $R audit/vintage_index.tsv audit/audit_legacy_2018_vs_later.csv > logs/a3_legacy_2018_check.log
bash scripts/a4_fork_crosscheck.sh $R                                      > logs/a4_fork_crosscheck.log
$PY scripts/a5_audit_table.py audit                                        > /dev/null
$PY scripts/a6_restatement_direction.py audit/pass1 audit/audit_restatement_direction.txt > /dev/null 2>&1
# ---- tests of the tools
$PY tests/test_signals.py
$PY tests/test_stats.py                                                    > logs/test_stats.log
# ---- B. predictive tests (PREREG.md)
$PY scripts/b1_build_panels.py $R audit/vintage_index.tsv data             > logs/b1_build_panels.log
$PY scripts/c1_check_panels.py data results/check_panels.txt               > /dev/null
for a in btc eth; do
  $PY scripts/b2_regressions.py data results $a  > logs/b2_regressions_$a.log
  $PY scripts/b3_oos_rules.py data results $a    > logs/b3_oos_rules_$a.log
  $PY scripts/b4_beyond_price.py data results $a > logs/b4_beyond_price_$a.log
done
$PY scripts/b5_summary.py results                                          > logs/b5_summary.log
# ---- C. diagnostics (post hoc)
$PY scripts/c2_diagnostics.py data results                                 > logs/c2_diagnostics.log 2>&1
$PY scripts/c3_lead_check.py data results                                  > logs/c3_lead_check.log
echo done
