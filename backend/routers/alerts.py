"""
Alerts router — event-driven stock news delivery.

Endpoints:
  POST   /api/alerts/portfolio          Register tickers to monitor
  GET    /api/alerts/portfolio          List watched tickers
  DELETE /api/alerts/portfolio/{ticker} Stop watching a ticker
  GET    /api/alerts/latest             Recent alerts (polling fallback)
  POST   /api/alerts/trigger/{ticker}  Manually trigger a news fetch
  GET    /api/alerts/stream             Server-Sent Events stream
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from events.news_enricher import get_alerts, subscribe_sse, unsubscribe_sse
from events.portfolio_monitor import monitor

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/alerts', tags=['alerts'])


class PortfolioWatchRequest(BaseModel):
    tickers: list[str]
    market: str = 'india'


@router.post('/portfolio')
async def add_to_watchlist(req: PortfolioWatchRequest):
    clean = [t.strip().upper() for t in req.tickers if t.strip()]
    monitor.add_tickers(clean, req.market)
    return {'watched': monitor.watched(), 'added': clean}


@router.get('/portfolio')
async def get_watchlist():
    return {'watched': monitor.watched()}


@router.delete('/portfolio/{ticker}')
async def remove_from_watchlist(ticker: str):
    monitor.remove_ticker(ticker.upper())
    return {'watched': monitor.watched()}


@router.get('/latest')
async def get_latest_alerts(limit: int = Query(default=20, ge=1, le=100)):
    """Polling endpoint — returns most recent alerts, newest first."""
    return {'alerts': get_alerts(limit)}


@router.post('/trigger/{ticker}')
async def manual_trigger(ticker: str, market: str = Query(default='india')):
    """
    Immediately fetch news for a ticker without waiting for a market event.
    Useful for on-demand enrichment or testing.
    """
    from events.event_bus import MarketEvent, bus
    await bus.publish(
        MarketEvent(type='MANUAL', ticker=ticker.upper(), market=market, data={})
    )
    return {'status': 'triggered', 'ticker': ticker.upper(), 'market': market}


@router.get('/stream')
async def sse_stream():
    """
    Server-Sent Events stream.  Connect once and receive alerts in real time.
    On connect the last 10 stored alerts are replayed so the client starts
    with context even if it missed earlier events.
    """
    q = subscribe_sse()

    async def _generator():
        try:
            # Replay recent history on first connect
            for alert in get_alerts(10):
                yield f'data: {json.dumps(alert)}\n\n'
            # Stream new alerts as they arrive
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                    yield f'data: {json.dumps(payload)}\n\n'
                except asyncio.TimeoutError:
                    yield ': keepalive\n\n'  # prevent proxy/browser timeout
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe_sse(q)

    return StreamingResponse(
        _generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
