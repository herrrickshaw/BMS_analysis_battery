#!/usr/bin/env python3
"""
load_signals_to_warehouse.py

Loads 7 newly-collected screener-research parquet files into the
market_data Postgres warehouse's new fact tables:

    fact_screener_signal      <- factorial_screener_signals_us.parquet
                               <- factorial_screener_signals_IN_technical.parquet
                               <- factorial_screener_signals_JP_technical.parquet
                               <- factorial_screener_signals_KR_technical.parquet
                               <- factorial_screener_signals_CN_technical.parquet
    fact_short_interest       <- short_interest_us.parquet
    fact_insider_transaction  <- insider_transactions_us.parquet

See warehouse_schema_signals.sql for the DDL / ON CONFLICT rationale, and
warehouse_versioning.sql for how batch_id versioning changes that (each
run's rows accumulate as a new batch instead of overwriting the prior
run's values in place -- query the `<table>_current` views for "latest
value per natural key", matching this script's pre-versioning behavior).

Usage:
    .venv/bin/python3 load_signals_to_warehouse.py                # load all 7, smallest first
    .venv/bin/python3 load_signals_to_warehouse.py --only short_interest_us
    .venv/bin/python3 load_signals_to_warehouse.py --dry-run       # parse + resolve stock_ids, no writes

Design notes:
  - Symbols are stripped of their yfinance-style market suffix
    (.T / .KS,.KQ / .SS,.SZ) before joining against stocks.ticker, which
    stores bare tickers. USA/India symbols in the source files are
    already bare.
  - stock_id resolution: LEFT JOIN against a staged bare-ticker list per
    market. Any bare ticker not already present in `stocks` for that
    market_id gets a new minimal row inserted (ticker, market_id only —
    name/sector/etc left NULL, never fabricated).
  - Bulk load path: rows are staged into an UNLOGGED temp-ish staging
    table via COPY (psycopg2 copy_expert, csv format), then
    INSERT ... SELECT ... ON CONFLICT into the real fact table. COPY is
    used instead of executemany/to_sql because the US screener file
    alone is ~1.4M rows and row-by-row INSERT would be far too slow.
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

CACHE_DIR = Path("/Users/umashankar/market-pipeline/code/python_files/cache_seed")

PG_CONN_KWARGS = dict(host="/tmp", dbname="market_data", user="umashankar")

# market_name -> market_id (matches public.markets, verified at connect time too)
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

# Suffixes to strip from source `symbol` values, per market, to reach the
# bare ticker convention used by stocks.ticker. USA/India need no stripping.
SUFFIX_STRIP = {
    "japan": [".T"],
    "korea": [".KS", ".KQ"],
    "china": [".SS", ".SZ"],
}

SCREENER_RET_COLS = [
    "ret_T+5d", "bench_ret_T+5d", "xret_T+5d",
    "ret_T+21d", "bench_ret_T+21d", "xret_T+21d",
    "ret_T+63d", "bench_ret_T+63d", "xret_T+63d",
    "ret_T+126d", "bench_ret_T+126d", "xret_T+126d",
    "ret_T+252d", "bench_ret_T+252d", "xret_T+252d",
]
# Destination column names (lowercase, no '+', matches warehouse_schema_signals.sql)
SCREENER_RET_DEST = [
    "ret_t5d", "bench_ret_t5d", "xret_t5d",
    "ret_t21d", "bench_ret_t21d", "xret_t21d",
    "ret_t63d", "bench_ret_t63d", "xret_t63d",
    "ret_t126d", "bench_ret_t126d", "xret_t126d",
    "ret_t252d", "bench_ret_t252d", "xret_t252d",
]


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
        # Existing mappings
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
            # Re-select to pick up the stock_ids (including any that were
            # concurrently inserted / already existed due to the DO NOTHING race)
            cur.execute(
                "SELECT ticker, stock_id FROM stocks WHERE market_id = %s AND ticker = ANY(%s)",
                (market_id, missing),
            )
            for t, sid in cur.fetchall():
                mapping[t] = sid
    return mapping


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


def load_screener_file(conn, path: Path, market: str, chunksize: int = 200_000) -> int:
    log(f"Loading screener file {path.name} (market={market})")
    df = pd.read_parquet(path)
    log(f"  read {len(df):,} rows, columns={list(df.columns)}")

    batch_id = start_batch(conn, "fact_screener_signal", f"screener_{market}", str(path))
    log(f"  opened batch_id={batch_id}")

    df["bare_ticker"] = df["symbol"].map(lambda s: strip_suffix(s, market))
    ticker_map = resolve_stock_ids(conn, df["bare_ticker"], market)
    df["stock_id"] = df["bare_ticker"].map(ticker_map)

    unmatched = df["stock_id"].isna().sum()
    if unmatched:
        log(f"  WARNING: {unmatched} rows failed stock_id resolution after insert "
            f"(unexpected) -- dropping them")
        df = df[df["stock_id"].notna()]

    df["stock_id"] = df["stock_id"].astype(int)
    df["market_id"] = MARKET_IDS[market]
    df["signal_date"] = pd.to_datetime(df["signal_date"]).dt.date
    df["batch_id"] = batch_id

    rename = dict(zip(SCREENER_RET_COLS, SCREENER_RET_DEST))
    df = df.rename(columns=rename)

    staging_cols = [
        "stock_id", "market_id", "signal_date", "screener", "year",
        *SCREENER_RET_DEST, "dollar_vol_63d", "log_liquidity", "volatility_63d", "batch_id",
    ]
    for c in staging_cols:
        if c not in df.columns:
            df[c] = None
    df = df[staging_cols].rename(columns={"year": "signal_year"})
    staging_cols = [c if c != "year" else "signal_year" for c in staging_cols]

    try:
        total = 0
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg_screener_signal")
            cur.execute("CREATE TEMP TABLE stg_screener_signal (LIKE fact_screener_signal INCLUDING DEFAULTS)")
            cur.execute("ALTER TABLE stg_screener_signal DROP COLUMN signal_id, DROP COLUMN loaded_at")
        conn.commit()

        for start in range(0, len(df), chunksize):
            chunk = df.iloc[start:start + chunksize]
            copy_dataframe(conn, chunk, "stg_screener_signal", staging_cols)
            total += len(chunk)
            log(f"  staged {total:,}/{len(df):,} rows")

        with conn.cursor() as cur:
            # batch_id is always new here, so ON CONFLICT (nat key, batch_id)
            # only fires on a resumed/re-run of this exact batch -- DO UPDATE
            # keeps that resume idempotent without duplicating history rows.
            cur.execute(f"""
                INSERT INTO fact_screener_signal (
                    stock_id, market_id, signal_date, screener, signal_year,
                    {', '.join(SCREENER_RET_DEST)}, dollar_vol_63d, log_liquidity, volatility_63d, batch_id
                )
                SELECT DISTINCT ON (stock_id, signal_date, screener)
                    stock_id, market_id, signal_date, screener, signal_year,
                    {', '.join(SCREENER_RET_DEST)}, dollar_vol_63d, log_liquidity, volatility_63d, batch_id
                FROM stg_screener_signal
                ORDER BY stock_id, signal_date, screener
                ON CONFLICT (stock_id, signal_date, screener, batch_id) DO UPDATE SET
                    {', '.join(f"{c} = EXCLUDED.{c}" for c in SCREENER_RET_DEST)},
                    dollar_vol_63d = EXCLUDED.dollar_vol_63d,
                    log_liquidity = EXCLUDED.log_liquidity,
                    volatility_63d = EXCLUDED.volatility_63d,
                    signal_year = EXCLUDED.signal_year,
                    loaded_at = CURRENT_TIMESTAMP
            """)
            inserted = cur.rowcount
        conn.commit()
        log(f"  inserted {inserted:,} rows into fact_screener_signal (batch_id={batch_id})")
        finish_batch(conn, batch_id, inserted, status="success")
    except Exception as e:
        conn.rollback()
        finish_batch(conn, batch_id, 0, status="failed", notes=str(e)[:500])
        raise
    return inserted


def load_short_interest(conn, path: Path, chunksize: int = 50_000) -> int:
    log(f"Loading short interest file {path.name} (market=usa)")
    df = pd.read_parquet(path)
    log(f"  read {len(df):,} rows, columns={list(df.columns)}")

    batch_id = start_batch(conn, "fact_short_interest", "short_interest_us", str(path))
    log(f"  opened batch_id={batch_id}")

    ticker_map = resolve_stock_ids(conn, df["symbol"], "usa")
    df["stock_id"] = df["symbol"].map(ticker_map)
    unmatched = df["stock_id"].isna().sum()
    if unmatched:
        log(f"  WARNING: {unmatched} rows failed stock_id resolution -- dropping them")
        df = df[df["stock_id"].notna()]
    df["stock_id"] = df["stock_id"].astype(int)
    df["settlement_date"] = pd.to_datetime(df["settlementDate"]).dt.date

    rename = {
        "accountingYearMonthNumber": "accounting_year_month_number",
        "issueName": "issue_name",
        "issuerServicesGroupExchangeCode": "issuer_services_group_exchange_code",
        "marketClassCode": "market_class_code",
        "currentShortPositionQuantity": "current_short_position_quantity",
        "previousShortPositionQuantity": "previous_short_position_quantity",
        "stockSplitFlag": "stock_split_flag",
        "averageDailyVolumeQuantity": "average_daily_volume_quantity",
        "daysToCoverQuantity": "days_to_cover_quantity",
        "revisionFlag": "revision_flag",
        "changePercent": "change_percent",
        "changePreviousNumber": "change_previous_number",
    }
    df = df.rename(columns=rename)

    staging_cols = [
        "stock_id", "settlement_date", "accounting_year_month_number", "issue_name",
        "issuer_services_group_exchange_code", "market_class_code",
        "current_short_position_quantity", "previous_short_position_quantity",
        "stock_split_flag", "average_daily_volume_quantity", "days_to_cover_quantity",
        "revision_flag", "change_percent", "change_previous_number", "batch_id",
    ]
    df["batch_id"] = batch_id
    df = df[staging_cols]

    try:
        total = 0
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg_short_interest")
            cur.execute("CREATE TEMP TABLE stg_short_interest (LIKE fact_short_interest INCLUDING DEFAULTS)")
            cur.execute("ALTER TABLE stg_short_interest DROP COLUMN short_interest_id, DROP COLUMN loaded_at")
        conn.commit()

        for start in range(0, len(df), chunksize):
            chunk = df.iloc[start:start + chunksize]
            copy_dataframe(conn, chunk, "stg_short_interest", staging_cols)
            total += len(chunk)
        log(f"  staged {total:,} rows")

        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO fact_short_interest ({', '.join(staging_cols)})
                SELECT {', '.join(staging_cols)} FROM stg_short_interest
                ON CONFLICT (stock_id, settlement_date, batch_id) DO UPDATE SET
                    accounting_year_month_number = EXCLUDED.accounting_year_month_number,
                    issue_name = EXCLUDED.issue_name,
                    issuer_services_group_exchange_code = EXCLUDED.issuer_services_group_exchange_code,
                    market_class_code = EXCLUDED.market_class_code,
                    current_short_position_quantity = EXCLUDED.current_short_position_quantity,
                    previous_short_position_quantity = EXCLUDED.previous_short_position_quantity,
                    stock_split_flag = EXCLUDED.stock_split_flag,
                    average_daily_volume_quantity = EXCLUDED.average_daily_volume_quantity,
                    days_to_cover_quantity = EXCLUDED.days_to_cover_quantity,
                    revision_flag = EXCLUDED.revision_flag,
                    change_percent = EXCLUDED.change_percent,
                    change_previous_number = EXCLUDED.change_previous_number,
                    loaded_at = CURRENT_TIMESTAMP
            """)
            inserted = cur.rowcount
        conn.commit()
        log(f"  inserted {inserted:,} rows into fact_short_interest (batch_id={batch_id})")
        finish_batch(conn, batch_id, inserted, status="success")
    except Exception as e:
        conn.rollback()
        finish_batch(conn, batch_id, 0, status="failed", notes=str(e)[:500])
        raise
    return inserted


def load_insider_transactions(conn, path: Path, chunksize: int = 50_000) -> int:
    log(f"Loading insider transactions file {path.name} (market=usa)")
    df = pd.read_parquet(path)
    log(f"  read {len(df):,} rows, columns={list(df.columns)}")

    batch_id = start_batch(conn, "fact_insider_transaction", "insider_transactions_us", str(path))
    log(f"  opened batch_id={batch_id}")

    ticker_map = resolve_stock_ids(conn, df["symbol"], "usa")
    df["stock_id"] = df["symbol"].map(ticker_map)
    unmatched = df["stock_id"].isna().sum()
    if unmatched:
        log(f"  WARNING: {unmatched} rows failed stock_id resolution -- dropping them")
        df = df[df["stock_id"].notna()]
    df["stock_id"] = df["stock_id"].astype(int)

    df["trans_date"] = pd.to_datetime(df["TRANS_DATE"]).dt.date
    df["filing_date"] = pd.to_datetime(df["FILING_DATE"]).dt.date

    rename = {
        "ACCESSION_NUMBER": "accession_number",
        "TRANS_CODE": "trans_code",
        "TRANS_SHARES": "trans_shares",
        "TRANS_PRICEPERSHARE": "trans_price_per_share",
    }
    df = df.rename(columns=rename)

    staging_cols = [
        "stock_id", "accession_number", "trans_date", "filing_date",
        "trans_code", "trans_shares", "trans_price_per_share", "quarter", "batch_id",
    ]
    df["batch_id"] = batch_id
    df = df[staging_cols]

    try:
        total = 0
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg_insider_transaction")
            cur.execute("CREATE TEMP TABLE stg_insider_transaction (LIKE fact_insider_transaction INCLUDING DEFAULTS)")
            cur.execute("ALTER TABLE stg_insider_transaction DROP COLUMN insider_txn_id, DROP COLUMN loaded_at")
        conn.commit()

        for start in range(0, len(df), chunksize):
            chunk = df.iloc[start:start + chunksize]
            copy_dataframe(conn, chunk, "stg_insider_transaction", staging_cols)
            total += len(chunk)
        log(f"  staged {total:,} rows")

        with conn.cursor() as cur:
            # Natural key is NOT extended with batch_id here -- a filed
            # Form 4 transaction is immutable, so a reload hitting the same
            # key is the same record, not a new version (see
            # warehouse_versioning.sql). batch_id is still recorded on
            # every row for load-lineage.
            cur.execute(f"""
                INSERT INTO fact_insider_transaction ({', '.join(staging_cols)})
                SELECT {', '.join(staging_cols)} FROM stg_insider_transaction
                ON CONFLICT (accession_number, stock_id, trans_date, trans_code, trans_shares, trans_price_per_share)
                DO NOTHING
            """)
            inserted = cur.rowcount
        conn.commit()
        log(f"  inserted {inserted:,} new rows into fact_insider_transaction (batch_id={batch_id}) "
            f"({len(df) - inserted:,} were exact-duplicate natural keys, skipped)")
        finish_batch(conn, batch_id, inserted, status="success")
    except Exception as e:
        conn.rollback()
        finish_batch(conn, batch_id, 0, status="failed", notes=str(e)[:500])
        raise
    return inserted


JOBS = {
    "short_interest_us": lambda conn: load_short_interest(conn, CACHE_DIR / "short_interest_us.parquet"),
    "insider_transactions_us": lambda conn: load_insider_transactions(conn, CACHE_DIR / "insider_transactions_us.parquet"),
    "screener_IN": lambda conn: load_screener_file(conn, CACHE_DIR / "factorial_screener_signals_IN_technical.parquet", "india"),
    "screener_KR": lambda conn: load_screener_file(conn, CACHE_DIR / "factorial_screener_signals_KR_technical.parquet", "korea"),
    "screener_JP": lambda conn: load_screener_file(conn, CACHE_DIR / "factorial_screener_signals_JP_technical.parquet", "japan"),
    "screener_CN": lambda conn: load_screener_file(conn, CACHE_DIR / "factorial_screener_signals_CN_technical.parquet", "china"),
    "screener_US": lambda conn: load_screener_file(conn, CACHE_DIR / "factorial_screener_signals_us.parquet", "usa"),
}
# Smallest-first order (approximate, by known row counts / file size)
JOB_ORDER = [
    "short_interest_us",
    "insider_transactions_us",
    "screener_IN",
    "screener_KR",
    "screener_JP",
    "screener_CN",
    "screener_US",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(JOBS.keys()), default=None,
                     help="Run only these named jobs (default: all, smallest first)")
    args = ap.parse_args()

    jobs = args.only if args.only else JOB_ORDER

    conn = psycopg2.connect(**PG_CONN_KWARGS)
    try:
        for name in jobs:
            t0 = time.time()
            n = JOBS[name](conn)
            log(f"=== {name} done: {n:,} rows affected in {time.time()-t0:.1f}s ===\n")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
