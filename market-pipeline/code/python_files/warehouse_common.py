#!/usr/bin/env python3
"""
warehouse_common.py -- shared connection config, ticker-resolution, and
bulk-COPY helpers for load_signals_to_warehouse.py and
load_ohlcv_to_warehouse.py.

Extracted because both loaders had grown byte-identical copies of
PG_CONN_KWARGS, MARKET_IDS, log(), strip_suffix(), resolve_stock_ids(), and
copy_dataframe() -- two loaders is enough for a real divergence risk (a fix
to one copy silently not applying to the other), so this is the single
source of truth both import from. See warehouse_versioning.sql /
warehouse_batch.py for the versioning layer this sits alongside.
"""
from __future__ import annotations

import io
import time

import pandas as pd
import psycopg2
import psycopg2.extras

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

# Suffixes to strip from source ticker values, per market, to reach the bare
# ticker convention used by stocks.ticker. USA/India need no stripping. Kept
# as the superset of both loaders' needs (load_ohlcv_to_warehouse.py doesn't
# load china, but having the entry present is harmless).
SUFFIX_STRIP = {
    "japan": [".T"],
    "korea": [".KS", ".KQ"],
    "china": [".SS", ".SZ"],
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def strip_suffix(symbol: str, market: str) -> str:
    for suf in SUFFIX_STRIP.get(market, []):
        if symbol.endswith(suf):
            return symbol[: -len(suf)]
    return symbol


def resolve_stock_ids(conn, bare_tickers: pd.Series, market: str) -> tuple[dict[str, int], int]:
    """
    Returns ({bare_ticker: stock_id}, n_new) for every distinct ticker in
    bare_tickers, inserting minimal new rows into stocks for any ticker not
    already present for this market_id. n_new is how many of those were newly
    inserted (0 if none).
    """
    market_id = MARKET_IDS[market]
    distinct = sorted(set(bare_tickers.dropna().unique().tolist()))
    if not distinct:
        return {}, 0

    with conn.cursor() as cur:
        # Existing mappings
        cur.execute(
            "SELECT ticker, stock_id FROM stocks WHERE market_id = %s AND ticker = ANY(%s)",
            (market_id, distinct),
        )
        mapping = {t: sid for t, sid in cur.fetchall()}

        missing = [t for t in distinct if t not in mapping]
        if missing:
            log(
                f"  {market}: inserting {len(missing)} new minimal stocks rows "
                f"(not previously in stocks for market_id={market_id})"
            )
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
