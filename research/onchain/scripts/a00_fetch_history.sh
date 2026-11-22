#!/usr/bin/env bash
# A00: obtain every committed version of csv/btc.csv and csv/eth.csv without pulling the multi-gigabyte history.
#   1. blobless, no-checkout clone of coinmetrics/data (commits and trees only, a few MB)
#   2. the pre-rewrite history: upstream refs/pull/*/head (to 2022-06-24) and fork wds33817/data (to 2025-06-19)
#   3. an index: lineage, commit, commit time, blob id of csv/btc.csv, blob id of csv/eth.csv
#   4. the ~4,000 blobs fetched in commit order in batches, so that consecutive versions arrive as small deltas
#      (about 95 MB in total instead of ~30 GB of raw CSV text)
# Nothing from the repository is checked out or executed.
# Usage: bash scripts/a00_fetch_history.sh <root_dir>      (root_dir/third_party/cm_data and root_dir/audit are created)
set -euo pipefail
ROOT="$1"
R="$ROOT/third_party/cm_data"
mkdir -p "$ROOT/third_party" "$ROOT/audit"
if [ ! -d "$R/.git" ]; then
  GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none --no-checkout https://github.com/coinmetrics/data "$R"
fi
git -C "$R" fetch --filter=blob:none origin 'refs/pull/*/head:refs/remotes/origin/pull/*'
git -C "$R" remote add fork_wds https://github.com/wds33817/data 2>/dev/null || true
git -C "$R" fetch --filter=blob:none fork_wds 'refs/heads/master:refs/remotes/fork_wds/master'
OUT="$ROOT/audit/vintage_index.tsv"
: > "$OUT"
for lineage in fork_wds/master master; do
  git -C "$R" log --reverse --format='%H %cI' "$lineage" -- csv/btc.csv csv/eth.csv | while read -r c t; do
    b=$(git -C "$R" rev-parse -q --verify "$c:csv/btc.csv" 2>/dev/null || echo NA)
    e=$(git -C "$R" rev-parse -q --verify "$c:csv/eth.csv" 2>/dev/null || echo NA)
    printf '%s\t%s\t%s\t%s\t%s\n' "$lineage" "$c" "$t" "$b" "$e" >> "$OUT"
  done
done
W=$(mktemp -d "$ROOT/third_party/fetch.XXXXXX")
for col in 4 5; do
  cut -f"$col" "$OUT" | grep -v NA | awk '!seen[$0]++' > "$W/blobs_$col.txt"
  split -l 300 -d "$W/blobs_$col.txt" "$W/chunk_${col}_"
  for f in "$W"/chunk_"${col}"_*; do
    git -C "$R" -c fetch.negotiationAlgorithm=noop fetch fork_wds --no-tags --no-write-fetch-head \
        --recurse-submodules=no --filter=blob:none --stdin < "$f"
  done
done
echo "commits indexed: $(wc -l < "$OUT"); last upstream commit: $(git -C "$R" log -1 --format='%H %cI' master)"
