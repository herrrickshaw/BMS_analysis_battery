#!/usr/bin/env python3
"""Compress correlation_scan/*_correlation_matrix.csv -> same-named float16 zstd parquet.

WHY: market_correlation_scan.py regenerates full N x N correlation matrices as CSV
every run (us alone is ~800 MB). CSV of dense float data is 5-10x larger than a
float16 zstd parquet, and the extra precision is meaningless for a correlation
(the sibling corr_dense.npz in market-correlation-matrices already uses float16).
Converting to parquet keeps the data, retains the base name so a downstream
consumer only swaps .csv -> .parquet, and keeps files small enough to live as
REGULAR git objects (no LFS -> no LFS-storage billing). Anything still >100 MB
after float16 (only us, ~113 MB) is left as parquet for the caller to route to
Dropbox rather than GitHub.

Idempotent: if a market has no CSV, it is skipped. A CSV is deleted only after
its parquet is written AND re-read with a matching (rows, cols) shape.

Usage:
  compress_correlation_matrices.py [--dir DIR] [--keep-csv]
"""
import argparse
import os
import sys

SUFFIX = "_correlation_matrix.csv"
GITHUB_REGULAR_LIMIT = 100 * 1024 * 1024  # GitHub rejects non-LFS files > 100 MB


def compress_one(csv_path, keep_csv=False):
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    out = csv_path[: -len(".csv")] + ".parquet"
    df = pd.read_csv(csv_path)
    idx = df.columns[0]  # first column is the Symbol/ticker index (string)
    floatcols = [c for c in df.columns if c != idx]
    df[floatcols] = df[floatcols].astype("float16")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out, compression="zstd")

    # verify before deleting the source
    chk = pd.read_parquet(out)
    if chk.shape != df.shape:
        raise RuntimeError(f"shape mismatch {csv_path}: csv {df.shape} != parquet {chk.shape}")

    csv_bytes = os.path.getsize(csv_path)
    pq_bytes = os.path.getsize(out)
    if not keep_csv:
        os.remove(csv_path)
    return csv_bytes, pq_bytes, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "correlation_scan"),
    )
    ap.add_argument("--keep-csv", action="store_true", help="convert but do not delete the CSV")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        print(f"compress_correlation_matrices: no dir {args.dir} (nothing to do)")
        return 0

    csvs = sorted(f for f in os.listdir(args.dir) if f.endswith(SUFFIX))
    if not csvs:
        print(f"compress_correlation_matrices: no *{SUFFIX} in {args.dir} (nothing to do)")
        return 0

    saved = 0
    oversize = []
    for name in csvs:
        path = os.path.join(args.dir, name)
        try:
            cb, pb, out = compress_one(path, keep_csv=args.keep_csv)
        except Exception as e:  # noqa: BLE001 - report and continue with the rest
            print(f"  FAIL {name}: {e}", file=sys.stderr)
            continue
        saved += cb - pb
        flag = ""
        if pb > GITHUB_REGULAR_LIMIT:
            oversize.append(os.path.basename(out))
            flag = "  [>100MB: route to Dropbox, not GitHub]"
        print(f"  {name} -> {os.path.basename(out)}  {cb // 1048576}MB -> {pb // 1048576}MB{flag}")

    print(f"compress_correlation_matrices: reclaimed ~{saved // 1048576} MB")
    if oversize:
        print("  still >100 MB (LFS-free GitHub impossible): " + ", ".join(oversize))
    return 0


if __name__ == "__main__":
    sys.exit(main())
