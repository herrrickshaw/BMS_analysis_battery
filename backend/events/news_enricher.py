"""
News enricher: subscribes to all market events from the EventBus,
fetches relevant news via NewsAPI (if NEWSAPI_KEY env var is set)
or yfinance as a fallback, and stores Alerts for SSE delivery.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import deque
from dataclasses import asdict, dataclass

log = logging.getLogger(__name__)

NEWSAPI_KEY = os.getenv('NEWSAPI_KEY', '')
_MAX_ALERTS = 100

_alert_store: deque = deque(maxlen=_MAX_ALERTS)
_sse_queues: list[asyncio.Queue] = []


@dataclass
class Alert:
    id: str
    event_type: str
    ticker: str
    market: str
    event_data: dict
    news: list
    timestamp: str


# ── public API ─────────────────────────────────────────────────────────────────

def get_alerts(limit: int = 20) -> list[dict]:
    """Return the most recent alerts, newest first."""
    alerts = list(_alert_store)
    return [asdict(a) for a in reversed(alerts[-limit:])]


def subscribe_sse() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_queues.append(q)
    return q


def unsubscribe_sse(q: asyncio.Queue) -> None:
    try:
        _sse_queues.remove(q)
    except ValueError:
        pass


def setup() -> None:
    """Wire the enricher to the global event bus. Call once at startup."""
    from events.event_bus import bus
    bus.subscribe('*', _on_event)
    log.info('NewsEnricher subscribed to EventBus (NewsAPI key: %s)',
             'set' if NEWSAPI_KEY else 'not set — using yfinance fallback')


# ── event handler (runs as asyncio task) ──────────────────────────────────────

async def _on_event(event) -> None:
    try:
        news = await asyncio.to_thread(_fetch_news, event.ticker, event.market)
        alert = Alert(
            id=uuid.uuid4().hex[:8],
            event_type=event.type,
            ticker=event.ticker,
            market=event.market,
            event_data=event.data,
            news=news,
            timestamp=event.timestamp,
        )
        _alert_store.append(alert)
        payload = asdict(alert)
        for q in list(_sse_queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass
        log.info('Alert stored: %s %s/%s (%d articles)',
                 alert.event_type, alert.market, alert.ticker, len(news))
    except Exception:
        log.exception('NewsEnricher._on_event error')


# ── news fetchers (blocking — run in thread pool) ──────────────────────────────

def _fetch_news(ticker: str, market: str, limit: int = 5) -> list[dict]:
    if NEWSAPI_KEY:
        articles = _fetch_newsapi(ticker, limit)
        if articles:
            return articles
    return _fetch_yfinance(ticker, market, limit)


def _fetch_newsapi(ticker: str, limit: int) -> list[dict]:
    import requests
    # Strip exchange suffixes for a cleaner company search
    clean_ticker = ticker.split('.')[0]
    url = (
        'https://newsapi.org/v2/everything'
        f'?q={clean_ticker}&language=en&sortBy=publishedAt'
        f'&pageSize={limit}&apiKey={NEWSAPI_KEY}'
    )
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        articles = []
        for a in r.json().get('articles', [])[:limit]:
            if a.get('title') and a.get('url'):
                articles.append({
                    'title': a['title'],
                    'publisher': (a.get('source') or {}).get('name', ''),
                    'link': a['url'],
                    'published_at': a.get('publishedAt', ''),
                    'description': a.get('description', ''),
                    'source': 'newsapi',
                })
        return articles
    except Exception as exc:
        log.warning('NewsAPI fetch failed for %s: %s', ticker, exc)
        return []


def _fetch_yfinance(ticker: str, market: str, limit: int) -> list[dict]:
    try:
        import yfinance as yf
        yf_sym = ticker if market != 'india' or ticker.endswith('.NS') else f'{ticker}.NS'
        raw = yf.Ticker(yf_sym).news or []
        articles = []
        for item in raw[:limit]:
            c = item.get('content') if isinstance(item.get('content'), dict) else None
            if c:
                title = c.get('title', '')
                link = (c.get('canonicalUrl') or {}).get('url', '') or \
                       (c.get('clickThroughUrl') or {}).get('url', '')
                pub = (c.get('provider') or {}).get('displayName', '')
                ts = c.get('pubDate', '')
            else:
                title = item.get('title', '')
                link = item.get('link', '')
                pub = item.get('publisher', '')
                ts = str(item.get('providerPublishTime', ''))
            if title and link:
                articles.append({'title': title, 'publisher': pub, 'link': link,
                                 'published_at': ts, 'source': 'yfinance'})
        return articles
    except Exception as exc:
        log.warning('yfinance news fetch failed for %s: %s', ticker, exc)
        return []
