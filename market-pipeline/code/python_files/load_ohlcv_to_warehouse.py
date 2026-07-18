#!/usr/bin/env python3
"""
load_ohlcv_to_warehouse.py

Loads missing OHLCV price history into the market_data Postgres warehouse's
pre-existing `ohlcv_history` fact table for usa/japan/korea (india and china
are already populated; uk/germany/europe have no verified source file yet
and are out of scope).

Source files (see SCREENER_RESEARCH_DATA_SOURCES.md §1):
    usa   <- ~/repos/global-stock-screener/cache_seed/ltm/US.parquet  (~16.2M rows)
    japan <- ~/repos/global-stock-screener/cache_seed/ltm/JP.parquet (~7.3M rows)
    korea <- ~/repos/global-stock-screener/cache_seed/ltm/KR.parquet (~5.3M rows)

Schema (all 3, verified): Date, Open, High, Low, Close, Volume, Symbol.
No adjusted-close column in the source -- adj_close is left NULL throughout
(this repo's convention is split-day exclusion, not price adjustment).

Design mirrors load_signals_to_warehouse.py:
  - Symbols are stripped of their yfinance-style market suffix (.T for
    Japan, .KS/.KQ for Korea) before joining against stocks.ticker, which
    stores bare tickers. USA symbols are already bare.
  - stock_id resolution: existing (ticker, market_id) rows are looked up in
    `stocks`; any bare ticker not already present gets a new minimal row
    inserted (ticker, market_id only -- no fabricated name/sector/etc).
  - Bulk load path: rows are staged into a TEMP table via COPY
    (psycopg2 copy_expert, csv format) in chunks, then
    INSERT ... SELECT DISTINCT ON (stock_id, date) ... ON CONFLICT DO UPDATE
    into ohlcv_history. COPY is used instead of executemany/to_sql because
    these files are multi-million-row.
  - Verified (see this script's own exploration, no duplicate (Symbol,
    Date) rows and no cross-suffix bare-ticker collisions in any of the 3
    source files) but DISTINCT ON is kept anyway as a defensive guard, same
    class of bug load_signals_to_warehouse.py hit and fixed for
    fact_screener_signal.

Versioning (see warehouse_versioning.sql): every run opens a load_batches
row via warehouse_batch.start_batch(), tags every staged row with that
batch_id, and the natural key is (stock_id, date, batch_id) -- so a reload
no longer overwrites the prior load's values in place, it adds a new,
separately-queryable version. Query ohlcv_history_current for "latest
value per (stock_id, date)", matching this script's pre-versioning
behavior.

Usage:
    .venv/bin/python3 load_ohlcv_to_warehouse.py                 # load all 3, smallest first (korea, japan, usa)
    .venv/bin/python3 load_ohlcv_to_warehouse.py --only korea
    .venv/bin/python3 load_ohlcv_to_warehouse.py --dry-run        # parse + resolve stock_ids, no writes
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

from warehouse_batch import start_batch, finish_batch

SRC_DIR = Path("/Users/umashankar/repos/global-stock-screener/cache_seed/ltm")

PG_CONN_KWARGS = dict(host="/tmp", dbname="market_data", user="umashankar")

# market_name -> market_id (matches public.markets)
MARKET_IDS = {
    "india": 1,
    "usa": 2,
    "uk": 3,
    "germany": 4,
    "europe": 5,
    "japan": 6,
    "korea": 7,
    "china": 8,
}

# Suffixes to strip from source `Symbol` values, per market, to reach the
# bare ticker convention used by stocks.ticker. USA needs no stripping.
SUFFIX_STRIP = {
    "japan": [".T"],
    "korea": [".KS", ".KQ"],
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def strip_suffix(symbol: str, market: str) -> str:
    for suf in SUFFIX_STRIP.get(market, []):
        if symbol.endswith(suf):
            return symbol[: -len(suf)]
    return symbol


def resolve_stock_ids(conn, bare_tickers: pd.Series, market: str) -> dict[str, int]:
    """
    Returns {bare_ticker: stock_id} for every distinct ticker in bare_tickers,
    inserting minimal new rows into stocks for any ticker not already present
    for this market_id.
    """
    market_id = MARKET_IDS[market]
    distinct = sorted(set(bare_tickers.dropna().unique().tolist()))
    if not distinct:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker, stock_id FROM stocks WHERE market_id = %s AND ticker = ANY(%s)",
            (market_id, distinct),
        )
        mapping = {t: sid for t, sid in cur.fetchall()}

        missing = [t for t in distinct if t not in mapping]
        if missing:
            log(f"  {market}: inserting {len(missing)} new minimal stocks rows "
                f"(not previously in stocks for market_id={market_id})")
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO stocks (ticker, market_id) VALUES %s "
                "ON CONFLICT (ticker, market_id) DO NOTHING",
                [(t, market_id) for t in missing],
            )
            conn.commit()
            cur.execute(
                "SELECT ticker, stock_id FROM stocks WHERE market_id = %s AND ticker = ANY(%s)",
                (market_id, missing),
            )
            for t, sid in cur.fetchall():
                mapping[t] = sid
    return mapping, len(missing)


def copy_dataframe(conn, df: pd.DataFrame, table: str, columns: list[str]) -> None:
    """Fast bulk COPY of a dataframe (already column-ordered) into `table`."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
            buf,
        )


STAGING_COLS = ["stock_id", "date", "open_price", "high_price", "low_price",
                 "close_price", "volume", "adj_close", "batch_id"]


def load_ohlcv_file(conn, path: Path, market: str, dry_run: bool = False,
                     chunksize: int = 500_000) -> tuple[int, int]:
    log(f"Loading OHLCV file {path.name} (market={market})")
    df = pd.read_parquet(path)
    log(f"  read {len(df):,} rows, columns={list(df.columns)}")

    expected_cols = {"Date", "Open", "High", "Low", "Close", "Volume", "Symbol"}
    missing_cols = expected_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"{path.name}: missing expected columns {missing_cols}")

    df["bare_ticker"] = df["Symbol"].map(lambda s: strip_suffix(s, market))

    dup_key = df.duplicated(subset=["bare_ticker", "Date"]).sum()
    if dup_key:
        log(f"  WARNING: {dup_key} duplicate (bare_ticker, Date) rows found in source "
            f"-- DISTINCT ON in the final INSERT will keep one arbitrarily")
    else:
        log("  no duplicate (bare_ticker, Date) rows in source (verified)")

    ticker_map, n_new = resolve_stock_ids(conn, df["bare_ticker"], market)
    df["stock_id"] = df["bare_ticker"].map(ticker_map)

    unmatched = df["stock_id"].isna().sum()
    if unmatched:
        log(f"  WARNING: {unmatched} rows failed stock_id resolution after insert "
            f"(unexpected) -- dropping them")
        df = df[df["stock_id"].notna()]

    df["stock_id"] = df["stock_id"].astype(int)
    df["date"] = pd.to_datetime(df["Date"]).dt.date
    df["adj_close"] = None  # no adjusted-close in source; never fabricate one

    df = df.rename(columns={
        "Open": "open_price", "High": "high_price", "Low": "low_price",
        "Close": "close_price", "Volume": "volume",
    })

    if dry_run:
        log(f"  [dry-run] would stage/upsert {len(df):,} rows, {n_new} new stocks rows")
        return len(df), n_new

    batch_id = start_batch(conn, "ohlcv_history", f"ohlcv_{market}", str(path))
    df["batch_id"] = batch_id
    df = df[STAGING_COLS]
    log(f"  opened batch_id={batch_id}")

    total = 0
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg_ohlcv")
            cur.execute("CREATE TEMP TABLE stg_ohlcv (LIKE ohlcv_history INCLUDING DEFAULTS)")
            cur.execute("ALTER TABLE stg_ohlcv DROP COLUMN ohlcv_id, DROP COLUMN created_at")
        conn.commit()

        for start in range(0, len(df), chunksize):
            chunk = df.iloc[start:start + chunksize]
            copy_dataframe(conn, chunk, "stg_ohlcv", STAGING_COLS)
            total += len(chunk)
            log(f"  staged {total:,}/{len(df):,} rows")

        with conn.cursor() as cur:
            # batch_id is always new here, so ON CONFLICT (stock_id, date,
            # batch_id) only fires if this exact batch is resumed after a
            # crash -- DO UPDATE keeps that resume idempotent without
            # creating duplicate history rows for the same batch.
            cur.execute(f"""
                INSERT INTO ohlcv_history ({', '.join(STAGING_COLS)})
                SELECT DISTINCT ON (stock_id, date)
                    {', '.join(STAGING_COLS)}
                FROM stg_ohlcv
                ORDER BY stock_id, date
                ON CONFLICT (stock_id, date, batch_id) DO UPDATE SET
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume,
                    adj_close = EXCLUDED.adj_close
            """)
            inserted = cur.rowcount
        conn.commit()
        log(f"  inserted {inserted:,} rows into ohlcv_history (batch_id={batch_id})")
        finish_batch(conn, batch_id, inserted, status="success")
    except Exception as e:
        conn.rollback()
        finish_batch(conn, batch_id, 0, status="failed", notes=str(e)[:500])
        raise
    return inserted, n_new


JOBS = {
    "korea": lambda conn, dry: load_ohlcv_file(conn, SRC_DIR / "KR.parquet", "korea", dry_run=dry),
    "japan": lambda conn, dry: load_ohlcv_file(conn, SRC_DIR / "JP.parquet", "japan", dry_run=dry),
    "usa": lambda conn, dry: load_ohlcv_file(conn, SRC_DIR / "US.parquet", "usa", dry_run=dry),
}
# Smallest-first order (by known row counts): korea 5.3M, japan 7.3M, usa 16.2M
JOB_ORDER = ["korea", "japan", "usa"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(JOBS.keys()), default=None,
                     help="Run only these named jobs (default: all, smallest first)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Parse + resolve stock_ids, no writes to ohlcv_history")
    args = ap.parse_args()

    jobs = args.only if args.only else JOB_ORDER

    conn = psycopg2.connect(**PG_CONN_KWARGS)
    try:
        for name in jobs:
            t0 = time.time()
            n, n_new = JOBS[name](conn, args.dry_run)
            log(f"=== {name} done: {n:,} rows affected, {n_new} new stocks rows, "
                f"{time.time()-t0:.1f}s ===\n")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
