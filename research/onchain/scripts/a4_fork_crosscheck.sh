#!/usr/bin/env bash
# A4: integrity cross-check of the pre-rewrite history used for the audit.
# The upstream repository was re-initialised on 2026-03-26, so its 2020-2025 history survives only in
# (a) upstream refs/pull/{1,2,3}/head (through 2022-06-24) and (b) forks made before the rewrite.
# This lists the head of every fork found by GitHub search and checks whether it lies on the audited chain
# (ancestor of, or equal to, the head of the fork used: wds33817/data @ 178d6934).
# Usage: bash scripts/a4_fork_crosscheck.sh <repo_dir>
set -u
R="$1"
echo "upstream pull/3 parent (last upstream bot commit 2022-06-24) on audited chain: $(git -C "$R" merge-base --is-ancestor 3142e4febf144c071abb06cbf4703b350f108d36 fork_wds/master && echo yes || echo NO)"
for f in amsi4991/data Benny2000/data croque-m/coinmetrics-data c3016229/data shivam7207/data slowcoder-fastsleeper/data li294151664/data jedsonpinto/data tmduc90/data giuse88/data; do
  sha=$(git ls-remote "https://github.com/$f" refs/heads/master 2>/dev/null | cut -f1)
  if [ -z "$sha" ]; then echo "$f: no master ref"; continue; fi
  if git -C "$R" cat-file -e "$sha^{commit}" 2>/dev/null; then
    if git -C "$R" merge-base --is-ancestor "$sha" fork_wds/master 2>/dev/null; then rel="on audited pre-rewrite chain"
    elif git -C "$R" merge-base --is-ancestor "$sha" master 2>/dev/null; then rel="on upstream master (post-rewrite)"
    else
      mb=$(git -C "$R" merge-base "$sha" fork_wds/master 2>/dev/null)
      rel="own commit(s) on top of audited chain at $(git -C "$R" log -1 --format='%h %cI' "$mb" 2>/dev/null); commits ahead: $(git -C "$R" rev-list --count "$mb..$sha" 2>/dev/null)"
    fi
    echo "$f $sha $(git -C "$R" log -1 --format=%cI "$sha") -> $rel"
  else echo "$f $sha -> commit not in local clone"; fi
done
