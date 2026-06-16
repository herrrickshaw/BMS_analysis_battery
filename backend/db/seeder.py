"""
Seed all market instrument tables from the existing CSV-backed in-memory dicts.

Design:
  - Idempotent: checks seed_status before inserting.
  - Uses cassandra.concurrent.execute_concurrent_with_args for fast bulk inserts.
  - Falls through silently if Cassandra is offline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from db import cassandra_client as cass

log = logging.getLogger(__name__)

MARKETS = ['india', 'us', 'europe', 'japan', 'korea', 'china', 'hong_kong', 'canada']

_stmts: dict[str, Any] = {}


def _prepare(s) -> None:
    if _stmts:
        return
    ks = cass.KEYSPACE
    _stmts['main'] = s.prepare(
        f"INSERT INTO {ks}.instruments "
        "(market, yf_ticker, symbol, name, name_lower, isin, exchange, country) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    _stmts['by_sym'] = s.prepare(
        f"INSERT INTO {ks}.instruments_by_symbol "
        "(market, symbol, yf_ticker, name) VALUES (?, ?, ?, ?)"
    )
    _stmts['by_name'] = s.prepare(
        f"INSERT INTO {ks}.instruments_by_name "
        "(market, name_lower, yf_ticker, name) VALUES (?, ?, ?, ?)"
    )
    _stmts['by_isin'] = s.prepare(
        f"INSERT INTO {ks}.instruments_by_isin "
        "(isin, market, yf_ticker, symbol, name) VALUES (?, ?, ?, ?, ?)"
    )
    _stmts['seed_check'] = s.prepare(
        f"SELECT seeded_at FROM {ks}.seed_status WHERE market = ?"
    )
    _stmts['seed_write'] = s.prepare(
        f"INSERT INTO {ks}.seed_status (market, seeded_at, row_count) VALUES (?, ?, ?)"
    )


def _already_seeded(s, market: str) -> bool:
    row = s.execute(_stmts['seed_check'], (market,)).one()
    return row is not None


def seed_market(market: str, force: bool = False) -> dict:
    """
    Seed one market into Cassandra. Skips if already seeded (unless force=True).
    Blocking — run via threadpool.
    """
    s = cass.session()
    if s is None:
        return {'market': market, 'inserted': 0, 'error': 'cassandra_offline'}

    _prepare(s)

    if not force and _already_seeded(s, market):
        log.info('Seeder: %s already seeded — skipping', market)
        return {'market': market, 'inserted': 0, 'skipped': True}

    # Use the existing in-memory CSV dicts as the source of truth
    from parsers.market_db import _db
    db = _db(market)
    by_yf: dict[str, dict] = db.get('by_yf', {})

    if not by_yf:
        log.warning('Seeder: no data for %s (CSV missing?)', market)
        return {'market': market, 'inserted': 0, 'skipped': False}

    # Build ISIN map for India (symbol → isin)
    isin_map: dict[str, str] = {}
    if market == 'india':
        from parsers.symbol_db import _BY_SYMBOL, _load
        _load()
        isin_map = {sym: v['isin'] for sym, v in _BY_SYMBOL.items() if v.get('isin')}

    rows_main: list[tuple] = []
    rows_sym:  list[tuple] = []
    rows_name: list[tuple] = []
    rows_isin: list[tuple] = []

    for yf_ticker, entry in by_yf.items():
        symbol    = entry.get('code') or yf_ticker.split('.')[0]
        name      = entry.get('name', '')
        name_low  = name.lower()
        isin      = isin_map.get(symbol, '')
        exchange  = entry.get('exchange', '') or entry.get('market', '')
        country   = entry.get('country', '')

        rows_main.append((market, yf_ticker, symbol, name, name_low, isin, exchange, country))
        if symbol:
            rows_sym.append((market, symbol.upper(), yf_ticker, name))
        if name:
            rows_name.append((market, name_low, yf_ticker, name))
        if isin:
            rows_isin.append((isin, market, yf_ticker, symbol, name))

    from cassandra.concurrent import execute_concurrent_with_args

    execute_concurrent_with_args(s, _stmts['main'],    rows_main, concurrency=100)
    execute_concurrent_with_args(s, _stmts['by_sym'],  rows_sym,  concurrency=100)
    execute_concurrent_with_args(s, _stmts['by_name'], rows_name, concurrency=100)
    if rows_isin:
        execute_concurrent_with_args(s, _stmts['by_isin'], rows_isin, concurrency=100)

    s.execute(_stmts['seed_write'], (market, datetime.now(timezone.utc), len(rows_main)))
    log.info('Seeder: %s — %d instruments inserted', market, len(rows_main))
    return {'market': market, 'inserted': len(rows_main), 'skipped': False}


def seed_all(force: bool = False) -> list[dict]:
    return [seed_market(m, force=force) for m in MARKETS]
