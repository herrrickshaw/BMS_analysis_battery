from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import pandas as pd

from routers.upload import data_store
from fetchers.live import (
    fetch_live, get_nse_index_symbols, compare_dataframes,
    NSE_INDEX_URLS,
)
from scanners import darvas, piotroski, coffee_can

router = APIRouter()

# Live data: market → DataFrame fetched from yfinance
live_store: dict[str, pd.DataFrame] = {}
# Per-market fetch progress
fetch_progress: dict[str, dict] = {}

MARKET_EXCHANGE: dict[str, str] = {
    'nse_largecap':  'NSE',
    'nse_midcap':    'NSE',
    'nse_smallcap':  'NSE',
    'bse':           'BSE',
    'nasdaq_adr':    'NASDAQ',
}

SCANNERS = {
    'darvas':     darvas.scan,
    'piotroski':  piotroski.scan,
    'coffee_can': coffee_can.scan,
}


class FetchRequest(BaseModel):
    index: Optional[str] = None              # 'nifty50' | 'nifty100' | ...
    symbols: Optional[list[str]] = None      # explicit symbol list (with yfinance suffixes)
    portfolio_market: Optional[str] = None   # 'india'|'us'|'europe'|'japan'|'korea'


@router.post("/api/live/fetch")
async def fetch_live_data(market: str, req: FetchRequest = FetchRequest()):
    """
    Fetch live financial data from yfinance.
    Symbol resolution order:
      1. req.symbols (explicit list)
      2. req.index   (NSE index archive CSV)
      3. tickers from uploaded Screener CSV for this market
    """
    # portfolio_market overrides the tab-level exchange when fetching
    # symbols extracted from an uploaded file (they already carry yfinance suffixes)
    _PORTFOLIO_EXCHANGE = {
        'india': 'NSE', 'us': 'US', 'europe': 'EUROPE',
        'japan': 'JAPAN', 'korea': 'KOREA',
    }
    exchange = (
        _PORTFOLIO_EXCHANGE.get(req.portfolio_market)
        if req.portfolio_market
        else MARKET_EXCHANGE.get(market, 'NSE')
    )

    symbols: list[str] = []

    if req.symbols:
        symbols = req.symbols
    elif req.index:
        fetch_progress[market] = {'status': 'resolving', 'note': f'Getting {req.index} symbols...'}
        symbols = await run_in_threadpool(get_nse_index_symbols, req.index)
        if not symbols:
            raise HTTPException(502, f"Could not fetch symbol list for index '{req.index}'")
    elif market in data_store:
        df = data_store[market]
        col = 'ticker' if 'ticker' in df.columns else None
        if col:
            symbols = df[col].dropna().str.strip().tolist()

    if not symbols:
        raise HTTPException(
            400,
            "No symbols to fetch. Either upload a Screener CSV first, "
            "provide an index name, or pass explicit symbols."
        )

    fetch_progress[market] = {
        'status':  'fetching',
        'total':   len(symbols),
        'done':    0,
        'errors':  0,
    }

    live_df = await run_in_threadpool(fetch_live, symbols, exchange)

    if live_df.empty:
        fetch_progress[market] = {'status': 'error', 'error': 'yfinance returned no data'}
        raise HTTPException(502, "yfinance returned no data")

    errors = int(live_df.get('_error', pd.Series(dtype=str)).notna().sum()) if '_error' in live_df.columns else 0
    live_store[market] = live_df

    fetch_progress[market] = {
        'status': 'done',
        'total':  len(symbols),
        'done':   len(live_df) - errors,
        'errors': errors,
    }

    return {
        'market':    market,
        'exchange':  exchange,
        'requested': len(symbols),
        'fetched':   len(live_df) - errors,
        'errors':    errors,
    }


@router.get("/api/live/status")
def live_status(market: str):
    return fetch_progress.get(market, {'status': 'idle'})


@router.post("/api/live/scan")
async def scan_live(market: str, scan_type: str = 'all'):
    """Run scan engines on live-fetched data (not the Screener CSV)."""
    if market not in live_store:
        raise HTTPException(404, "No live data for this market. Call /api/live/fetch first.")

    df = live_store[market]

    if scan_type == 'all':
        results: dict[str, list] = {}
        for name, fn in SCANNERS.items():
            results[name] = await run_in_threadpool(fn, df)
        return {'market': market, 'source': 'live', 'results': results}

    if scan_type not in SCANNERS:
        raise HTTPException(400, f"Unknown scan type '{scan_type}'")

    rows = await run_in_threadpool(SCANNERS[scan_type], df)
    return {'market': market, 'source': 'live', 'results': {scan_type: rows}}


@router.get("/api/live/compare")
async def compare_live(market: str):
    """
    Field-by-field comparison between the uploaded Screener CSV and
    live yfinance data for the same market.
    """
    if market not in data_store:
        raise HTTPException(404, "No Screener data. Upload a CSV first.")
    if market not in live_store:
        raise HTTPException(404, "No live data. Call /api/live/fetch first.")

    comparison = await run_in_threadpool(
        compare_dataframes,
        data_store[market],
        live_store[market],
    )

    all_deltas = [
        f['delta_pct']
        for s in comparison
        for f in s['fields']
        if f['delta_pct'] is not None and not f['noisy']
    ]

    summary = {
        'stocks_compared':    len(comparison),
        'avg_delta_pct':      round(sum(all_deltas) / len(all_deltas), 1) if all_deltas else 0,
        'high_discrepancy':   sum(1 for s in comparison if s['overall_flag'] == 'red'),
        'medium_discrepancy': sum(1 for s in comparison if s['overall_flag'] == 'amber'),
        'low_discrepancy':    sum(1 for s in comparison if s['overall_flag'] == 'green'),
    }

    return {
        'market':      market,
        'summary':     summary,
        'comparisons': comparison,
    }


@router.get("/api/live/indices")
def available_indices():
    return {'indices': list(NSE_INDEX_URLS.keys())}
