"""
REST endpoints for Cassandra database management.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from db import cassandra_client as cass
from db.seeder import seed_market, seed_all, MARKETS

router = APIRouter(prefix='/api/db', tags=['cassandra'])


@router.get('/status')
async def db_status():
    """Cassandra health and per-market instrument counts."""
    available = await run_in_threadpool(cass.is_available)
    if not available:
        return {
            'cassandra': 'offline',
            'keyspace': cass.KEYSPACE,
            'instruments': {},
            'quotes': {},
        }

    s = cass.session()
    instruments: dict[str, int] = {}
    quotes: dict[str, int] = {}

    for market in MARKETS:
        try:
            r = s.execute(
                f"SELECT COUNT(*) FROM {cass.KEYSPACE}.instruments WHERE market = %s",
                (market,)
            ).one()
            instruments[market] = int(r[0]) if r else 0
        except Exception:
            instruments[market] = -1
        try:
            r = s.execute(
                f"SELECT COUNT(*) FROM {cass.KEYSPACE}.stock_quotes WHERE market = %s",
                (market,)
            ).one()
            quotes[market] = int(r[0]) if r else 0
        except Exception:
            quotes[market] = -1

    return {
        'cassandra': 'online',
        'keyspace': cass.KEYSPACE,
        'instruments': instruments,
        'quotes': quotes,
    }


@router.post('/seed')
async def seed_one(
    market: str = Query(..., description='Market: india | us | europe | japan | korea | china'),
    force: bool = Query(False, description='Re-seed even if already loaded'),
):
    """Seed (or re-seed) one market's instrument list into Cassandra."""
    if market not in MARKETS:
        raise HTTPException(400, f'Unknown market "{market}". Choose from: {MARKETS}')
    if not await run_in_threadpool(cass.is_available):
        raise HTTPException(503, 'Cassandra is offline')
    result = await run_in_threadpool(seed_market, market, force)
    return result


@router.post('/seed/all')
async def seed_all_markets(
    force: bool = Query(False, description='Re-seed all markets even if already loaded'),
):
    """Seed all markets (idempotent — skips already-loaded markets unless force=true)."""
    if not await run_in_threadpool(cass.is_available):
        raise HTTPException(503, 'Cassandra is offline')
    results = await run_in_threadpool(seed_all, force)
    return {'results': results}


@router.get('/search')
async def search_instruments(
    market: str = Query(...),
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Prefix-search instruments by name or exact symbol match.
    Uses instruments_by_name and instruments_by_symbol — no ALLOW FILTERING.
    """
    if not await run_in_threadpool(cass.is_available):
        return {'market': market, 'query': q, 'results': [], 'source': 'cassandra_offline'}

    hits = await run_in_threadpool(_search, market, q.strip(), limit)
    return {'market': market, 'query': q, 'results': hits, 'source': 'cassandra'}


def _search(market: str, q: str, limit: int) -> list[dict]:
    s = cass.session()
    q_lower = q.lower()
    q_upper_sym = q.upper()

    # Compute prefix-range upper bounds
    def _next(s: str) -> str:
        return s[:-1] + chr(ord(s[-1]) + 1) if s else '￿'

    name_upper = _next(q_lower)
    sym_upper  = _next(q_upper_sym)

    results: dict[str, dict] = {}

    try:
        for row in s.execute(
            f"SELECT yf_ticker, name FROM {cass.KEYSPACE}.instruments_by_name "
            f"WHERE market = %s AND name_lower >= %s AND name_lower < %s LIMIT %s",
            (market, q_lower, name_upper, limit),
        ):
            results[row.yf_ticker] = {'yf_ticker': row.yf_ticker, 'name': row.name}
    except Exception as exc:
        pass

    try:
        for row in s.execute(
            f"SELECT yf_ticker, name FROM {cass.KEYSPACE}.instruments_by_symbol "
            f"WHERE market = %s AND symbol >= %s AND symbol < %s LIMIT %s",
            (market, q_upper_sym, sym_upper, limit // 2),
        ):
            results.setdefault(row.yf_ticker, {'yf_ticker': row.yf_ticker, 'name': row.name})
    except Exception:
        pass

    return list(results.values())[:limit]
