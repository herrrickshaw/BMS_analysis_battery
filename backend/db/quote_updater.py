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
_hist_stmts: dict[str, Any] = {}


def _prepare_hist(s) -> None:
    if _hist_stmts:
        return
    ks = cass.KEYSPACE
    _hist_stmts['insert'] = s.prepare(
        f"INSERT INTO {ks}.price_history (yf_ticker, price_date, close_price) VALUES (?, ?, ?)"
    )
    _hist_stmts['select'] = s.prepare(
        f"SELECT close_price FROM {ks}.price_history WHERE yf_ticker = ? AND price_date = ?"
    )


def cache_price_on_date(yf_ticker: str, price_date, close_price: float) -> None:
    """Store a historical closing price in Cassandra. Silent no-op if offline."""
    s = cass.session()
    if s is None:
        return
    try:
        _prepare_hist(s)
        s.execute(_hist_stmts['insert'], (yf_ticker, price_date, close_price))
    except Exception as exc:
        log.debug('cache_price_on_date failed for %s %s: %s', yf_ticker, price_date, exc)


def get_cached_price(yf_ticker: str, price_date) -> Optional[float]:
    """Return cached closing price for a ticker on a given date, or None."""
    s = cass.session()
    if s is None:
        return None
    try:
        _prepare_hist(s)
        row = s.execute(_hist_stmts['select'], (yf_ticker, price_date)).one()
        return float(row.close_price) if row and row.close_price is not None else None
    except Exception:
        return None


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


def get_market_quotes_df(market: str) -> pd.DataFrame:
    """
    Read ALL cached quotes for a market into a DataFrame ready for scanner input.
    Joins with instruments table for name/exchange. Returns empty DataFrame on failure.
    """
    s = cass.session()
    if s is None:
        return pd.DataFrame()

    _prepare(s)

    # Read all quotes for the market
    try:
        quote_rows = list(s.execute(
            f"SELECT yf_ticker, cmp, rsi, ema_50, rsi_signal, pe, pb, roe, opm, "
            f"market_cap, volume, high_52w, low_52w, debt_to_equity "
            f"FROM {cass.KEYSPACE}.stock_quotes WHERE market = %s",
            (market,),
        ))
    except Exception as exc:
        log.warning('get_market_quotes_df: read error for %s: %s', market, exc)
        return pd.DataFrame()

    if not quote_rows:
        return pd.DataFrame()

    # Build name + exchange lookup from instruments table
    name_map: dict[str, str] = {}
    exch_map: dict[str, str] = {}
    try:
        inst_rows = s.execute(
            f"SELECT yf_ticker, name, exchange FROM {cass.KEYSPACE}.instruments WHERE market = %s",
            (market,),
        )
        for r in inst_rows:
            if r.yf_ticker:
                name_map[r.yf_ticker] = r.name or ''
                exch_map[r.yf_ticker] = r.exchange or ''
    except Exception as exc:
        log.debug('get_market_quotes_df: instrument lookup failed for %s: %s', market, exc)

    records = []
    for r in quote_rows:
        if r.cmp is None:
            continue
        rec = {
            'ticker':         r.yf_ticker,
            'name':           name_map.get(r.yf_ticker, ''),
            'cmp':            r.cmp,
            'rsi':            r.rsi,
            'ema_50':         r.ema_50,
            'rsi_signal':     r.rsi_signal or 'HOLD',
            'pe':             r.pe,
            'pb':             r.pb,
            'roe':            r.roe,
            'opm':            r.opm,
            'market_cap':     r.market_cap,
            'volume':         r.volume,
            'high_52w':       r.high_52w,
            'low_52w':        r.low_52w,
            'debt_to_equity': r.debt_to_equity,
            '_exchange':      exch_map.get(r.yf_ticker, ''),
        }
        records.append(rec)

    return pd.DataFrame(records) if records else pd.DataFrame()


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
