"""
Alpha Vantage provider.
US stocks + forex; free tier 25 req/day (300 req/day with free key registration).
https://www.alphavantage.co/documentation/
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

_BASE    = 'https://www.alphavantage.co/query'
_SESSION = requests.Session()
_LAST_CALL = 0.0
_MIN_INTERVAL = 12.5   # ~5 req/min on free tier (conservative)


def _get(params: dict, retries: int = 3) -> dict:
    global _LAST_CALL
    wait = _MIN_INTERVAL - (time.time() - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    params['apikey'] = cfg.ALPHA_VANTAGE_KEY
    for attempt in range(retries):
        try:
            r = _SESSION.get(_BASE, params=params, timeout=20)
            _LAST_CALL = time.time()
            r.raise_for_status()
            data = r.json()
            if 'Note' in data or 'Information' in data:
                log.warning('alpha_vantage: rate limit hit — sleeping 60s')
                time.sleep(60)
                continue
            return data
        except requests.RequestException as exc:
            log.debug('alpha_vantage._get attempt %d: %s', attempt, exc)
            time.sleep(2 ** attempt)
    return {}


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


class AlphaVantageProvider(DataProvider):
    name = 'alpha_vantage'

    def is_available(self) -> bool:
        return bool(cfg.ALPHA_VANTAGE_KEY)

    def get_ohlcv(self, ticker: str, period_days: int = 365) -> pd.DataFrame:
        outputsize = 'full' if period_days > 100 else 'compact'
        data = _get({'function': 'TIME_SERIES_DAILY_ADJUSTED',
                     'symbol': ticker, 'outputsize': outputsize})
        ts = data.get('Time Series (Daily)', {})
        if not ts:
            return pd.DataFrame()
        rows = []
        for d, v in ts.items():
            rows.append({
                'date':   pd.Timestamp(d),
                'Open':   float(v.get('1. open', 0)),
                'High':   float(v.get('2. high', 0)),
                'Low':    float(v.get('3. low', 0)),
                'Close':  float(v.get('5. adjusted close', v.get('4. close', 0))),
                'Volume': float(v.get('6. volume', 0)),
            })
        df = pd.DataFrame(rows).set_index('date').sort_index()
        return df.tail(period_days + 10)

    def get_fundamentals(self, ticker: str, market: str) -> dict:
        data = _get({'function': 'OVERVIEW', 'symbol': ticker})
        if not data or 'Symbol' not in data:
            return {}

        def _f(k: str) -> Optional[float]:
            return _safe_float(data.get(k))

        def _pct(k: str) -> Optional[float]:
            v = _f(k)
            return round(v * 100, 2) if v is not None else None

        mc = _f('MarketCapitalization')
        return {
            'name':           data.get('Name') or None,
            'sector':         data.get('Sector') or None,
            'industry':       data.get('Industry') or None,
            'pe':             _f('TrailingPE') or _f('PERatio'),
            'pb':             _f('PriceToBookRatio'),
            'roe':            _pct('ReturnOnEquityTTM'),
            'opm':            _pct('OperatingMarginTTM'),
            'market_cap':     round(mc / 1e6, 2) if mc else None,
            'debt_to_equity': _f('DebtToEquityRatio') or _f('DebtToEquity'),
            'beta':           _f('Beta'),
            'eps':            _f('EPS'),
            'dividend_yield': _pct('DividendYield'),
            'revenue_growth': _pct('RevenueGrowthYOY'),
        }

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        df = self.get_ohlcv(ticker)
        if df.empty:
            return None
        tech = compute_technicals(df['Close'], df.get('Volume'))
        if not tech.get('cmp'):
            return None
        fund = self.get_fundamentals(ticker, market)
        return QuoteData(ticker=ticker, source='alpha_vantage', **{**tech, **fund})

    def get_forex_rate(self, from_currency: str, to_currency: str = 'USD') -> Optional[float]:
        """Get current exchange rate between two currencies."""
        data = _get({'function': 'CURRENCY_EXCHANGE_RATE',
                     'from_currency': from_currency,
                     'to_currency': to_currency})
        rate = data.get('Realtime Currency Exchange Rate', {}).get('5. Exchange Rate')
        return _safe_float(rate)
