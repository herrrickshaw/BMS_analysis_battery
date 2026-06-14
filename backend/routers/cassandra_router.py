"""
REST endpoints for Cassandra database management.
"""
from __future__ import annotations

import asyncio

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


@router.post('/fetch_quotes')
async def fetch_quotes_one(
    market: str = Query(..., description='Market: india | us | europe | japan | korea | china'),
    batch_size: int = Query(50, ge=5, le=200,
        description='Tickers per yf.download() call (default 50)'),
    max_workers: int = Query(4, ge=1, le=12,
        description='Threads for fundamentals phase (default 4)'),
    with_fundamentals: bool = Query(True,
        description='Also fetch PE/ROE/market-cap per ticker (slower)'),
):
    """
    Start a background job that fetches live quotes for all instruments
    in the given market and writes them to Cassandra stock_quotes.
    Phase 1 uses yf.download() in batches (rate-limit friendly).
    Phase 2 fetches fundamentals individually at ~30/min.
    Returns immediately; poll /api/db/fetch_progress for status.
    """
    if market not in MARKETS:
        raise HTTPException(400, f'Unknown market "{market}". Choose from: {MARKETS}')
    if not await run_in_threadpool(cass.is_available):
        raise HTTPException(503, 'Cassandra is offline')

    from db.bulk_fetcher import fetch_market_quotes
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, fetch_market_quotes, market, batch_size, max_workers, with_fundamentals,
    )
    return {
        'status':  'started',
        'market':  market,
        'message': f'Fetching {market} in background (Phase 1: OHLCV bulk, Phase 2: fundamentals). Poll /api/db/fetch_progress.',
    }


@router.post('/fetch_quotes/all')
async def fetch_quotes_all(
    batch_size: int = Query(50, ge=5, le=200),
    max_workers: int = Query(4, ge=1, le=12),
    with_fundamentals: bool = Query(True),
):
    """
    Fetch live quotes for ALL markets sequentially.
    Phase 1: yf.download() batches (16 K tickers ≈ 20–40 min).
    Phase 2: individual .info for fundamentals (1–3 hours, optional).
    Returns immediately; poll /api/db/fetch_progress for status.
    """
    if not await run_in_threadpool(cass.is_available):
        raise HTTPException(503, 'Cassandra is offline')

    from db.bulk_fetcher import fetch_all_quotes, MARKETS as BF_MARKETS
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, fetch_all_quotes, None, batch_size, max_workers, with_fundamentals)

    s = cass.session()
    counts = {}
    for m in BF_MARKETS:
        try:
            r = s.execute(
                f'SELECT COUNT(*) FROM {cass.KEYSPACE}.instruments WHERE market = %s', (m,)
            ).one()
            counts[m] = int(r[0]) if r else 0
        except Exception:
            counts[m] = 0

    total = sum(counts.values())
    return {
        'status':  'started',
        'markets': BF_MARKETS,
        'instrument_counts': counts,
        'total_instruments': total,
        'message': (
            f'Fetching {total:,} instruments across {len(BF_MARKETS)} markets. '
            f'Phase 1 (OHLCV+RSI) takes ~20-40min; '
            f'Phase 2 (fundamentals) adds ~1-3h if with_fundamentals=true. '
            f'Poll /api/db/fetch_progress.'
        ),
    }


@router.post('/fetch_quotes/cancel')
async def cancel_fetch():
    """Cancel a running bulk fetch job."""
    from db.bulk_fetcher import cancel
    cancel()
    return {'status': 'cancel_requested'}


@router.get('/fetch_progress')
async def fetch_progress():
    """Return per-market progress for any running or completed bulk fetch."""
    from db.bulk_fetcher import get_progress
    progress = await run_in_threadpool(get_progress)
    return {'progress': progress}


# ── Scheduler endpoints ───────────────────────────────────────────────────────

@router.get('/scheduler/status')
async def scheduler_status():
    """
    Return the daily pre-compute scheduler state:
    next_run, last_run, last_status, total_written, elapsed_s.
    """
    import scheduler as sched
    return await run_in_threadpool(sched.status)


@router.post('/scheduler/trigger')
async def scheduler_trigger():
    """
    Immediately fire a full-market prefetch in the background.
    Returns 409 if a run is already in progress.
    """
    import scheduler as sched
    started = await run_in_threadpool(sched.trigger)
    if not started:
        raise HTTPException(409, 'A prefetch is already running. Check /api/db/fetch_progress.')
    return {
        'status':  'triggered',
        'message': 'Full-market prefetch started. Poll /api/db/fetch_progress for live progress.',
    }


@router.post('/scheduler/pause')
async def scheduler_pause():
    """Pause the daily job (does not stop a running prefetch)."""
    import scheduler as sched
    await run_in_threadpool(sched.pause)
    return {'status': 'paused'}


@router.post('/scheduler/resume')
async def scheduler_resume():
    """Resume a paused daily job."""
    import scheduler as sched
    await run_in_threadpool(sched.resume)
    st = await run_in_threadpool(sched.status)
    return {'status': 'resumed', 'next_run': st.get('next_run')}


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


# ── Daily scan report ─────────────────────────────────────────────────────────

_MARKET_CURRENCY = {
    'india':  '₹',
    'us':     '$',
    'europe': '€',
    'japan':  '¥',
    'korea':  '₩',
    'china':  '¥',
}

_MARKET_LABEL = {
    'india':  'India',
    'us':     'US',
    'europe': 'Europe',
    'japan':  'Japan',
    'korea':  'Korea',
    'china':  'China',
}


def _run_daily_scan(markets: list[str], scan_types: list[str]) -> dict:
    from db.quote_updater import get_market_quotes_df
    from scanners.daily_scanner import scan_darvas, scan_piotroski

    SCANNER_FN = {
        'darvas':     scan_darvas,
        'piotroski':  scan_piotroski,
    }

    results: dict[str, list] = {s: [] for s in scan_types}

    for market in markets:
        df = get_market_quotes_df(market)
        if df.empty:
            continue

        currency = _MARKET_CURRENCY.get(market, '')
        label    = _MARKET_LABEL.get(market, market)

        for scan_type in scan_types:
            fn  = SCANNER_FN.get(scan_type)
            if fn is None:
                continue
            rows = fn(df)
            for row in rows:
                # Only include BUY and WATCH signals
                if row.get('signal') not in ('BUY', 'WATCH'):
                    continue
                row['market']    = market
                row['market_label'] = label
                row['currency']  = currency
                row['exchange']  = row.get('_exchange', '')
                results[scan_type].append(row)

    # Sort each scan type by score desc
    for scan_type in results:
        results[scan_type].sort(key=lambda r: r.get('score', 0) or 0, reverse=True)

    return results


@router.post('/daily/scan')
async def daily_scan(
    markets: str = Query(default='india,us,europe,japan,korea'),
    scans:   str = Query(default='darvas,piotroski'),
):
    """
    Run Darvas/Buffett and Piotroski scans across all Cassandra-cached markets.
    Returns BUY + WATCH signals only, sorted by score descending.
    """
    if not cass.is_available():
        raise HTTPException(503, 'Cassandra offline')

    market_list = [m.strip() for m in markets.split(',') if m.strip()]
    scan_list   = [s.strip() for s in scans.split(',')
                   if s.strip() in ('darvas', 'piotroski')]

    if not market_list:
        raise HTTPException(400, 'No valid markets specified')
    if not scan_list:
        raise HTTPException(400, 'No valid scan types (darvas, piotroski)')

    results = await run_in_threadpool(_run_daily_scan, market_list, scan_list)

    totals = {s: len(v) for s, v in results.items()}
    return {
        'markets':  market_list,
        'scans':    scan_list,
        'totals':   totals,
        'results':  results,
    }
