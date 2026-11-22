"""Shared helpers: read Coin Metrics community CSV vintages from the git object store.

Nothing from the third-party repository is executed or imported; blobs are read with
`git cat-file --batch` and parsed as plain CSV text.
"""
import io
import subprocess
import numpy as np
import polars as pl

EPOCH = np.datetime64("2009-01-01", "D")
ND = int((np.datetime64("2026-12-31", "D") - EPOCH).astype(int)) + 1  # length of the global daily index
NON_NUMERIC = {"principal_market_usd"}
LEGACY_NCOMMITS = 4  # the four 2018 commits use an older schema ("date", "txCount", ...)


def read_index(index_path):
    """vintage_index.tsv -> list of dict(lineage, commit, time(np.datetime64[s], UTC), btc, eth)."""
    rows = []
    for line in open(index_path):
        lineage, commit, ctime, btc, eth = line.rstrip("\n").split("\t")
        # commit times carry an offset (+00:00 or -04:00); convert to UTC
        t = np.datetime64(pl.Series([ctime]).str.to_datetime(time_zone="UTC").dt.replace_time_zone(None)[0], "s")
        rows.append(dict(lineage=lineage, commit=commit, time=t, btc=btc, eth=eth, time_str=ctime))
    return rows


class BlobReader:
    def __init__(self, repo):
        self.p = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, oid):
        self.p.stdin.write((oid + "\n").encode())
        self.p.stdin.flush()
        hdr = self.p.stdout.readline().decode().split()
        if len(hdr) < 3 or hdr[1] != "blob":
            raise RuntimeError(f"bad object {oid}: {hdr}")
        size = int(hdr[2])
        data = self.p.stdout.read(size)
        self.p.stdout.read(1)
        return data

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def parse_vintage(data):
    """CSV bytes -> (date_idx int array, dict metric -> float64 array). Empty cells -> NaN."""
    df = pl.read_csv(io.BytesIO(data), infer_schema_length=0)
    tcol = "time" if "time" in df.columns else "date"
    dates = df[tcol].str.slice(0, 10).str.to_date().to_numpy().astype("datetime64[D]")
    didx = (dates - EPOCH).astype(np.int64)
    cols = {}
    for c in df.columns:
        if c == tcol or c in NON_NUMERIC:
            continue
        s = df[c].cast(pl.Float64, strict=False)
        cols[c] = s.to_numpy().astype(np.float64)  # nulls -> NaN
    return didx, cols


def idx_to_date(i):
    return EPOCH + np.asarray(i).astype("timedelta64[D]")
