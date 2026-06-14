"""
News router — per-stock and per-sector news summaries.

Stock news : yfinance Ticker.news  (no API key required)
Sector news: Google News RSS       (no API key, built-in urllib)

Cache: in-memory, 30-minute TTL per key.
"""
from __future__ import annotations

import logging
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/news', tags=['news'])

# ── cache ────────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, list]] = {}
_cache_lock = threading.Lock()
_TTL = 1800  # 30 min


def _get(key: str) -> Optional[list]:
    with _cache_lock:
        if key in _cache:
            ts, data = _cache[key]
            if time.time() - ts < _TTL:
                return data
    return None


def _put(key: str, data: list) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), data)


# ── yfinance suffix by market ────────────────────────────────────────────────

_SUFFIX = {'india': '.NS', 'us': '', 'europe': '', 'japan': '', 'korea': '', 'china': ''}


def _yf_sym(ticker: str, market: str) -> str:
    suffix = _SUFFIX.get(market, '')
    if not suffix:
        return ticker
    return ticker if ticker.upper().endswith(suffix.upper()) else f'{ticker}{suffix}'


# ── epoch / pubDate → ISO string ─────────────────────────────────────────────

def _ts(v) -> Optional[str]:
    if v is None:
        return None
    try:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat()
    except Exception:
        return None


# ── stock news via yfinance ──────────────────────────────────────────────────

def _parse_yf_item(item: dict) -> Optional[dict]:
    """Handle both old (flat) and new (nested content) yfinance news formats."""
    # New format: item['content'] dict
    content = item.get('content') if isinstance(item.get('content'), dict) else None
    if content:
        title = content.get('title', '')
        link  = (content.get('canonicalUrl') or {}).get('url') or content.get('clickThroughUrl', {}).get('url', '')
        pub   = (content.get('provider') or {}).get('displayName', '')
        ts    = content.get('pubDate')
    else:
        title = item.get('title', '')
        link  = item.get('link', '')
        pub   = item.get('publisher', '')
        ts    = _ts(item.get('providerPublishTime'))

    if not title or not link:
        return None
    return {'title': title, 'publisher': pub, 'link': link, 'published_at': ts}


def _fetch_stock_news(ticker: str, market: str, limit: int) -> list[dict]:
    try:
        import yfinance as yf
        raw   = yf.Ticker(_yf_sym(ticker, market)).news or []
        items = [_parse_yf_item(n) for n in raw[:limit]]
        return [x for x in items if x]
    except Exception as exc:
        log.warning('news: stock fetch failed %s/%s: %s', market, ticker, exc)
        return []


# ── sector news via Google News RSS ─────────────────────────────────────────

_REGION_LABEL = {
    'india': 'India', 'us': 'US', 'europe': 'Europe',
    'japan': 'Japan', 'korea': 'Korea', 'china': 'China',
}
_UA = 'Mozilla/5.0 (compatible; StockScreener/1.0)'


def _fetch_sector_news(sector: str, market: str, limit: int) -> list[dict]:
    region = _REGION_LABEL.get(market, '')
    query  = f'{sector} stocks {region}'.strip().replace(' ', '+')
    url    = f'https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': _UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_bytes = resp.read()

        root  = ET.fromstring(xml_bytes)
        items = root.findall('./channel/item')
        results = []
        for item in items[:limit]:
            title = (item.findtext('title') or '').strip()
            link  = (item.findtext('link') or '').strip()
            pub   = (item.findtext('source') or '').strip()
            date  = (item.findtext('pubDate') or '').strip()

            if not title or not link:
                continue
            results.append({
                'title':        title,
                'publisher':    pub,
                'link':         link,
                'published_at': date,
            })
        return results
    except Exception as exc:
        log.warning('news: sector RSS failed %s/%s: %s', sector, market, exc)
        return []


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get('/stock/{ticker}')
async def get_stock_news(
    ticker: str,
    market: str = Query(default='india'),
    limit:  int = Query(default=8, ge=1, le=20),
):
    key    = f'stock:{market}:{ticker}:{limit}'
    cached = _get(key)
    if cached is not None:
        return {'ticker': ticker, 'market': market, 'articles': cached, 'cached': True}

    articles = await run_in_threadpool(_fetch_stock_news, ticker, market, limit)
    _put(key, articles)
    return {'ticker': ticker, 'market': market, 'articles': articles, 'cached': False}


@router.get('/sector')
async def get_sector_news(
    name:   str = Query(...),
    market: str = Query(default='all'),
    limit:  int = Query(default=10, ge=1, le=20),
):
    key    = f'sector:{market}:{name}:{limit}'
    cached = _get(key)
    if cached is not None:
        return {'sector': name, 'market': market, 'articles': cached, 'cached': True}

    articles = await run_in_threadpool(_fetch_sector_news, name, market, limit)
    _put(key, articles)
    return {'sector': name, 'market': market, 'articles': articles, 'cached': False}
