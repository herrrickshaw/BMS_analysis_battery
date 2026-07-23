#!/usr/bin/env python3
"""
refresh_panels.py — incremental refresh of the gmd warehouse OHLCV panels.

Extends warehouse/ohlcv/<MKT> from each panel's max date to today for the
panel's own symbol universe, via yf.download batches. Unblocks the pending
signal scores that accumulate whenever a panel goes stale (JP/KR/EU ended
2026-07-01/02 with ~2,000 scores waiting).

Semantics: increments are fetched auto_adjust=True — the SAME convention the
panels were collected under. A symbol that split between the panel's last
assembly and today will therefore carry a residual break at its ex-date (old
rows in the old adjusted base). That is expected and handled downstream:
ALWAYS re-run price_adjuster_global.py after a refresh (staleness trigger in
claims.yaml `non-india-panels-already-adjusted`).

    refresh_panels.py --markets JP KR EU
    refresh_panels.py --markets US            # any warehouse market except IN
                                              # (IN comes from bhavcopy, not yf)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd
import yfinance as yf

WH = Path("/Users/umashankar/repos/global-market-data/warehouse")
BATCH = 50
COLS = ["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]


def refresh(market: str) -> None:
    con = duckdb.connect()
    src = f"{WH}/ohlcv/{market}/*.parquet"
    syms, dmax = con.execute(
        f"SELECT list(DISTINCT Symbol), max(Date) FROM read_parquet('{src}')"
    ).fetchone()
    dmax = pd.Timestamp(dmax)
    start = (dmax + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    print(
        f"  {market}: {len(syms)} symbols, panel ends {dmax.date()}, "
        f"fetching {start} -> today"
    )
    if dmax >= pd.Timestamp.now().normalize() - pd.Timedelta(days=1):
        print(f"  {market}: already fresh")
        return

    frames = []
    for i in range(0, len(syms), BATCH):
        batch = syms[i : i + BATCH]
        try:
            d = yf.download(
                batch,
                start=start,
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            print(f"    batch {i // BATCH}: download failed ({e}) — skipped")
            continue
        if d is None or d.empty:
            continue
        for s in batch:
            try:
                sub = d[s].dropna(subset=["Close"])
            except KeyError:
                continue
            if sub.empty:
                continue
            sub = sub.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
            sub["Symbol"] = s
            frames.append(sub)
        if (i // BATCH) % 10 == 0:
            print(f"    …batch {i // BATCH + 1}/{(len(syms) - 1) // BATCH + 1}")

    if not frames:
        print(f"  {market}: nothing fetched")
        return
    new = pd.concat(frames, ignore_index=True)
    new["Date"] = pd.to_datetime(new["Date"]).dt.tz_localize(None)
    new = new[new["Date"] > dmax][COLS]
    print(
        f"  {market}: {len(new):,} new rows "
        f"({new.Date.min().date()} -> {new.Date.max().date()})"
    )

    # merge into year partitions atomically, dedup on (Symbol, Date)
    for y, g in new.groupby(new["Date"].dt.year):
        p = WH / "ohlcv" / market / f"year={y}.parquet"
        if p.exists():
            old = pd.read_parquet(p)
            old["Date"] = pd.to_datetime(old["Date"])
            merged = pd.concat([old, g], ignore_index=True).drop_duplicates(
                subset=["Symbol", "Date"], keep="first"
            )
        else:
            merged = g
        tmp = p.with_suffix(".parquet.tmp")
        merged.sort_values(["Symbol", "Date"]).to_parquet(
            tmp, compression="zstd", index=False
        )
        tmp.replace(p)
        print(f"    year={y}: {len(merged):,} rows")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", nargs="+", required=True)
    a = ap.parse_args()
    for m in a.markets:
        if m == "IN":
            print("  IN is bhavcopy-fed (daily_pipeline) — skipping")
            continue
        refresh(m)
    print(
        "NOTE: re-run price_adjuster_global.py for refreshed markets "
        "(residual-split staleness trigger)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
