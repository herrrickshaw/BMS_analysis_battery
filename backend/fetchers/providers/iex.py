"""
IEX Cloud provider — US equities, credit-based pricing.
https://iexcloud.io/docs/api/
"""
from __future__ import annotations

import logging
import math
import time
from typing import Optional

import pandas as pd
import requests

from config.providers import cfg
from fetchers.providers.base import DataProvider, QuoteData, compute_technicals

log = logging.getLogger(__name__)
_SESSION = requests.Session()


def _get(path: str, params: dict | None = None, retries: int = 3) -> dict | list:
    params = {**(params or {}), 'token': cfg.IEX_TOKEN}
    url = f'{cfg.IEX_BASE}{path}'
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            if r.status_code == 402:
                log.warning('iex: insufficient credits for %s', path)
                return {}
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            log.debug('iex._get(%s) attempt %d: %s', path, attempt, exc)
            time.sleep(2 ** attempt)
    return {}


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


class IEXProvider(DataProvider):
    name = 'iex'

    def is_available(self) -> bool:
        return bool(cfg.IEX_TOKEN)

    def get_ohlcv(self, ticker: str, period_days: int = 365) -> pd.DataFrame:
        period = '1y' if period_days <= 365 else '2y'
        data   = _get(f'/stock/{ticker}/chart/{period}', {'chartCloseOnly': 'true'})
        if not isinstance(data, list) or not data:
            return pd.DataFrame()
        rows = [{'date': pd.Timestamp(d['date']),
                 'Open':   _safe_float(d.get('open',   d.get('fOpen'))),
                 'High':   _safe_float(d.get('high',   d.get('fHigh'))),
                 'Low':    _safe_float(d.get('low',    d.get('fLow'))),
                 'Close':  _safe_float(d.get('close',  d.get('fClose'))),
                 'Volume': _safe_float(d.get('volume', d.get('fVolume')))}
                for d in data]
        return pd.DataFrame(rows).set_index('date').dropna(subset=['Close'])

    def get_quotes_bulk(self, tickers: list[str], market: str) -> dict[str, QuoteData]:
        if market != 'us' or not tickers:
            return {}
        result: dict[str, QuoteData] = {}
        # Batch endpoint: max 100 symbols per call
        for i in range(0, len(tickers), 100):
            batch = ','.join(tickers[i:i + 100])
            data  = _get('/stock/market/batch',
                         {'symbols': batch, 'types': 'quote', 'range': '1y'})
            if not isinstance(data, dict):
                continue
            for sym, payload in data.items():
                q = payload.get('quote', {})
                cmp = _safe_float(q.get('latestPrice') or q.get('iexRealtimePrice'))
                if not cmp:
                    continue
                prev = _safe_float(q.get('previousClose'))
                ret_1d = round((cmp - prev) / prev * 100, 2) if prev and prev > 0 else None
                result[sym] = QuoteData(
                    ticker=sym, source='iex',
                    cmp=cmp,
                    high_52w=_safe_float(q.get('week52High')),
                    low_52w=_safe_float(q.get('week52Low')),
                    volume=int(q['latestVolume']) if q.get('latestVolume') else None,
                    market_cap=round(float(q['marketCap']) / 1e6, 2) if q.get('marketCap') else None,
                    pe=_safe_float(q.get('peRatio')),
                    ret_1d=ret_1d,
                )
            time.sleep(0.1)
        return result

    def get_fundamentals(self, ticker: str, market: str) -> dict:
        if market != 'us':
            return {}
        data = _get(f'/stock/{ticker}/advanced_stats')
        if not isinstance(data, dict):
            return {}

        def _f(k): return _safe_float(data.get(k))
        def _pct(k):
            v = _f(k)
            return round(v * 100, 2) if v is not None else None

        mc = _f('marketcap')
        return {
            'pe':             _f('peRatio') or _f('ttmEPS'),
            'pb':             _f('priceToBook'),
            'roe':            _pct('returnOnEquity'),
            'opm':            _pct('profitMargin'),
            'market_cap':     round(mc / 1e6, 2) if mc else None,
            'debt_to_equity': _f('debtToEquity'),
            'beta':           _f('beta'),
            'current_ratio':  _f('currentRatio'),
            'revenue_growth': _pct('revenueGrowth'),
            'eps':            _f('ttmEPS'),
            'dividend_yield': _pct('dividendYield'),
        }

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        if market != 'us':
            return None
        df = self.get_ohlcv(ticker)
        if df.empty:
            return None
        tech = compute_technicals(df['Close'], df.get('Volume'))
        if not tech.get('cmp'):
            return None
        fund = self.get_fundamentals(ticker, market)
        return QuoteData(ticker=ticker, source='iex', **{**tech, **fund})
