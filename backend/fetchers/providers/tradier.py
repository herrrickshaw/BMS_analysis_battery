"""
Tradier provider — US equities + options data.
Developer sandbox (free) or brokerage account.
https://documentation.tradier.com/brokerage-api
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests

from fetchers.providers.base import DataProvider, QuoteData, compute_technicals
from config.providers import cfg

log = logging.getLogger(__name__)
_SESSION = requests.Session()
_SESSION.headers.update({'Accept': 'application/json'})


def _auth() -> dict:
    return {'Authorization': f'Bearer {cfg.TRADIER_TOKEN}'}


def _get(path: str, params: dict | None = None) -> dict:
    try:
        r = _SESSION.get(f'{cfg.TRADIER_BASE}{path}',
                         params=params, headers=_auth(), timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        log.debug('tradier._get(%s): %s', path, exc)
        return {}


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


class TradierProvider(DataProvider):
    name = 'tradier'

    def is_available(self) -> bool:
        return bool(cfg.TRADIER_TOKEN)

    def get_ohlcv(self, ticker: str, period_days: int = 365) -> pd.DataFrame:
        end   = date.today().isoformat()
        start = (date.today() - timedelta(days=period_days + 10)).isoformat()
        data  = _get('/markets/history', {'symbol': ticker, 'interval': 'daily',
                                          'start': start, 'end': end})
        hist  = data.get('history') or {}
        days  = hist.get('day', [])
        if isinstance(days, dict):
            days = [days]
        if not days:
            return pd.DataFrame()
        rows = [{'date': pd.Timestamp(d['date']),
                 'Open': _safe_float(d.get('open')),
                 'High': _safe_float(d.get('high')),
                 'Low':  _safe_float(d.get('low')),
                 'Close': _safe_float(d.get('close')),
                 'Volume': _safe_float(d.get('volume'))}
                for d in days]
        return pd.DataFrame(rows).set_index('date').dropna(subset=['Close'])

    def get_quotes_bulk(self, tickers: list[str], market: str) -> dict[str, QuoteData]:
        if market != 'us' or not tickers:
            return {}
        result: dict[str, QuoteData] = {}
        # Tradier quotes endpoint: comma-separated, up to 100 symbols
        for i in range(0, len(tickers), 100):
            syms = ','.join(tickers[i:i + 100])
            data = _get('/markets/quotes', {'symbols': syms, 'greeks': 'false'})
            quotes = data.get('quotes', {}).get('quote', [])
            if isinstance(quotes, dict):
                quotes = [quotes]
            for q in quotes:
                sym = q.get('symbol', '')
                cmp = _safe_float(q.get('last') or q.get('close'))
                if not cmp:
                    continue
                prev = _safe_float(q.get('prevclose'))
                ret_1d = round((cmp - prev) / prev * 100, 2) if prev and prev > 0 else None
                result[sym] = QuoteData(
                    ticker=sym, source='tradier',
                    cmp=cmp,
                    high_52w=_safe_float(q.get('week_52_high')),
                    low_52w=_safe_float(q.get('week_52_low')),
                    volume=int(q['volume']) if q.get('volume') else None,
                    ret_1d=ret_1d,
                )
        return result

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        if market != 'us':
            return None
        df = self.get_ohlcv(ticker)
        if df.empty:
            return None
        tech = compute_technicals(df['Close'], df.get('Volume'))
        if not tech.get('cmp'):
            return None
        return QuoteData(ticker=ticker, source='tradier', **tech)
