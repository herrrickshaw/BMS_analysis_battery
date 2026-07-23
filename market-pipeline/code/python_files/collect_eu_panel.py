#!/usr/bin/env python3
"""
collect_eu_panel.py — full 10-year EU panel collection (one-shot rebuild).

Closes the EU coverage gap: the old warehouse/ohlcv/EU panel was 1 year x 852
symbols and anchored only 12% of EU scan signals. This collects the FULL span
(2016-06-27 -> today, matching the other markets) for the union universe:

    europe_all_list (~/data/market_data.duckdb, 966 tickers, 17 exchanges)
  ∪ existing panel symbols (852)
  ∪ every EU symbol that ever appeared in the signal ledger

Convention: auto_adjust=True, same as every other non-IN panel. A full
re-collection is a fresh assembly — the residual-split set resets to empty,
but re-run price_adjuster_global.py --markets EU afterwards anyway (cheap,
verifies exactly that).

The old 1y partitions are REPLACED (their rows are contained in the new
collection); the pre-rebuild panel survives in git history.

    collect_eu_panel.py            # collect + rebuild partitions
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb
import pandas as pd
import yfinance as yf

WH = Path("/Users/umashankar/repos/global-market-data/warehouse")
UNIVERSE_DB = os.path.expanduser("~/data/market_data.duckdb")
BASE = Path(__file__).resolve().parent
START = "2016-06-27"
BATCH = 50
COLS = ["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]


def universe() -> list[str]:
    syms: set[str] = set()
    con = duckdb.connect(UNIVERSE_DB, read_only=True)
    syms |= set(con.execute(
        "SELECT DISTINCT yf_ticker FROM europe_all_list").df()["yf_ticker"])
    con2 = duckdb.connect()
    try:
        syms |= set(con2.execute(
            f"SELECT DISTINCT Symbol FROM read_parquet('{WH}/ohlcv/EU/*.parquet')"
        ).df()["Symbol"])
    except Exception:
        pass
    for lf in ("signal_ledger.parquet", "signal_ledger_backfill.parquet"):
        p = BASE / "cache_seed" / lf
        if p.exists():
            led = pd.read_parquet(p)
            syms |= set(led.loc[led["market"] == "EU", "symbol"].astype(str))
    syms = {s for s in syms if s and s == s}
    print(f"  universe: {len(syms)} symbols")
    return sorted(syms)


def collect(syms: list[str]) -> pd.DataFrame:
    frames = []
    n_batches = (len(syms) - 1) // BATCH + 1
    for i in range(0, len(syms), BATCH):
        batch = syms[i:i + BATCH]
        try:
            d = yf.download(batch, start=START, auto_adjust=True,
                            progress=False, group_by="ticker", threads=True)
        except Exception as e:
            print(f"    batch {i // BATCH + 1}: download failed ({e})")
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
        if (i // BATCH) % 5 == 0:
            print(f"    …batch {i // BATCH + 1}/{n_batches} "
                  f"({sum(len(f) for f in frames):,} rows so far)")
    new = pd.concat(frames, ignore_index=True)
    new["Date"] = pd.to_datetime(new["Date"]).dt.tz_localize(None)
    return new[COLS]


def main() -> int:
    syms = universe()
    d = collect(syms)
    got = d["Symbol"].nunique()
    print(f"  collected {len(d):,} rows, {got}/{len(syms)} symbols, "
          f"{d.Date.min().date()} -> {d.Date.max().date()}")

    dst = WH / "ohlcv" / "EU"
    dst.mkdir(parents=True, exist_ok=True)
    old = sorted(dst.glob("year=*.parquet"))
    for y, g in d.groupby(d["Date"].dt.year):
        p = dst / f"year={y}.parquet"
        tmp = p.with_suffix(".parquet.tmp")
        g.sort_values(["Symbol", "Date"]).to_parquet(
            tmp, compression="zstd", index=False)
        tmp.replace(p)
        print(f"    year={y}: {len(g):,} rows")
    # drop old partitions for years absent from the new collection (none
    # expected — the new span is a superset)
    new_years = {f"year={y}.parquet" for y in d["Date"].dt.year.unique()}
    for p in old:
        if p.name not in new_years:
            p.unlink()
            print(f"    removed stale {p.name}")
    print("NOTE: run price_adjuster_global.py --markets EU, then score_signals.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
