#!/usr/bin/env python
"""A0: inventory of column sets per vintage (commit) for csv/btc.csv and csv/eth.csv.

Reads blobs straight from the git object store (no checkout, nothing executed from the repo).
Usage: python -I scripts/a0_header_inventory.py <repo_dir> <vintage_index.tsv> <out_dir>
"""
import subprocess, sys, json, os

repo, index_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out_dir, exist_ok=True)

rows = [l.rstrip("\n").split("\t") for l in open(index_path)]
# one long-lived cat-file process
p = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

def read_blob(oid):
    p.stdin.write((oid + "\n").encode()); p.stdin.flush()
    hdr = p.stdout.readline().decode().split()
    if len(hdr) < 3 or hdr[1] != "blob":
        raise RuntimeError(f"bad object {oid}: {hdr}")
    size = int(hdr[2])
    data = p.stdout.read(size)
    p.stdout.read(1)
    return data

out = {}
for asset, col in (("btc", 3), ("eth", 4)):
    prev = None
    events = []
    for r in rows:
        lineage, commit, ctime, oid = r[0], r[1], r[2], r[col]
        if oid == "NA":
            continue
        data = read_blob(oid)
        nl = data.find(b"\n")
        header = data[:nl].decode("utf-8", "replace").strip().split(",")
        nrows = data.count(b"\n") - 1
        last_line = data.rstrip(b"\n").rsplit(b"\n", 1)[-1].decode("utf-8", "replace")
        cur = tuple(header)
        if prev is None or set(cur) != set(prev):
            added = sorted(set(cur) - set(prev or ()))
            removed = sorted(set(prev or ()) - set(cur))
            events.append(dict(commit=commit, time=ctime, lineage=lineage, ncols=len(cur), nrows=nrows,
                               size=len(data), added=added, removed=removed, last_date=last_line.split(",")[0],
                               sep_guess="," ))
        prev = cur
    out[asset] = dict(events=events, final_header=list(prev))
json.dump(out, open(os.path.join(out_dir, "header_inventory.json"), "w"), indent=1)
for asset in out:
    print("=====", asset, "final header:", ",".join(out[asset]["final_header"]))
    for e in out[asset]["events"]:
        print(e["time"], e["lineage"], "ncols", e["ncols"], "nrows", e["nrows"], "size", e["size"], "last", e["last_date"])
        if len(e["added"]) <= 80:
            print("   + ", ",".join(e["added"]))
        print("   - ", ",".join(e["removed"]))
