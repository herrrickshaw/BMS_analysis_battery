"""
Persist yfinance fetch results into Cassandra stock_quotes and read them back.

upsert_quotes() — called fire-and-forget after every /api/live/fetch
get_quotes()    — called during /api/portfolio/parse to enrich matched tickers
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from db import cassandra_client as cass

log = logging.getLogger(__name__)

_stmts: dict[str, Any] = {}


def _prepare(s) -> None:
    if _stmts:
        return
    ks = cass.KEYSPACE
    _stmts['upsert'] = s.prepare(
        f"INSERT INTO {ks}.stock_quotes "
        "(market, yf_ticker, fetched_at, cmp, rsi, ema_50, rsi_signal, "
        " pe, pb, roe, opm, market_cap, volume, high_52w, low_52w, debt_to_equity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    _stmts['select_in'] = s.prepare(
        f"SELECT yf_ticker, fetched_at, cmp, rsi, ema_50, rsi_signal, "
        f"pe, pb, roe, opm, market_cap, volume, high_52w, low_52w, debt_to_equity "
        f"FROM {ks}.stock_quotes WHERE market = ? AND yf_ticker IN ?"
    )


def _f(row: pd.Series, key: str) -> Optional[float]:
    try:
        v = float(row.get(key))
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _i(row: pd.Series, key: str) -> Optional[int]:
    v = _f(row, key)
    return int(v) if v is not None else None


def upsert_quotes(market: str, live_df: pd.DataFrame) -> int:
    """
    Write live fetch results into stock_quotes.
    Blocking — must be dispatched from a background thread.
    Returns the number of rows written.
    """
    s = cass.session()
    if s is None or live_df.empty:
        return 0

    _prepare(s)
    now = datetime.now(timezone.utc)

    rows: list[tuple] = []
    for _, row in live_df.iterrows():
        ticker = str(row.get('ticker', '')).strip()
        if not ticker or row.get('_error'):
            continue
        rows.append((
            market,
            ticker,
            now,
            _f(row, 'cmp'),
            _f(row, 'rsi'),
            _f(row, 'ema_50'),
            str(row.get('rsi_signal', 'HOLD') or 'HOLD'),
            _f(row, 'pe'),
            _f(row, 'pb'),
            _f(row, 'roe'),
            _f(row, 'opm'),
            _f(row, 'market_cap'),
            _i(row, 'volume'),
            _f(row, 'high_52w'),
            _f(row, 'low_52w'),
            _f(row, 'debt_to_equity'),
        ))

    if not rows:
        return 0

    try:
        from cassandra.concurrent import execute_concurrent_with_args
        execute_concurrent_with_args(s, _stmts['upsert'], rows, concurrency=50)
        log.info('quote_updater: wrote %d quotes for %s', len(rows), market)
        return len(rows)
    except Exception as exc:
        log.warning('quote_updater: write error for %s: %s', market, exc)
        return 0


def get_quotes(market: str, yf_tickers: list[str]) -> dict[str, dict]:
    """
    Fetch cached quote data for a list of yfinance tickers.
    Returns {yf_ticker: {cmp, rsi, ema_50, rsi_signal, fetched_at, ...}}.
    Returns {} if Cassandra is offline or tickers list is empty.
    """
    s = cass.session()
    if s is None or not yf_tickers:
        return {}

    _prepare(s)
    try:
        rows = s.execute(_stmts['select_in'], (market, yf_tickers))
        return {
            row.yf_ticker: {
                'cmp':           row.cmp,
                'rsi':           row.rsi,
                'ema_50':        row.ema_50,
                'rsi_signal':    row.rsi_signal,
                'pe':            row.pe,
                'pb':            row.pb,
                'roe':           row.roe,
                'opm':           row.opm,
                'market_cap':    row.market_cap,
                'volume':        row.volume,
                'high_52w':      row.high_52w,
                'low_52w':       row.low_52w,
                'debt_to_equity': row.debt_to_equity,
                'fetched_at':    row.fetched_at.isoformat() if row.fetched_at else None,
            }
            for row in rows
        }
    except Exception as exc:
        log.warning('quote_updater: read error for %s: %s', market, exc)
        return {}
