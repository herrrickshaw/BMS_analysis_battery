"""
Quandl / Nasdaq Data Link provider.
Historical OHLCV + fundamentals for US and global equities.
https://data.nasdaq.com/tools/api
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config.providers import cfg
from fetchers.providers.base import DataProvider, QuoteData, compute_technicals

log = logging.getLogger(__name__)


def _ndl_available() -> bool:
    try:
        import nasdaqdatalink  # noqa: F401
        return bool(cfg.QUANDL_KEY)
    except ImportError:
        try:
            import quandl  # noqa: F401
            return bool(cfg.QUANDL_KEY)
        except ImportError:
            return False


def _get_client():
    """Return configured nasdaqdatalink or quandl module."""
    try:
        import nasdaqdatalink as ndl
        ndl.ApiConfig.api_key = cfg.QUANDL_KEY
        return ndl
    except ImportError:
        import quandl
        quandl.ApiConfig.api_key = cfg.QUANDL_KEY
        return quandl


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


class QuandlNDLProvider(DataProvider):
    name = 'quandl'

    def is_available(self) -> bool:
        return _ndl_available()

    def get_ohlcv(self, ticker: str, period_days: int = 365) -> pd.DataFrame:
        if not self.is_available():
            return pd.DataFrame()
        start = (date.today() - timedelta(days=period_days + 10)).isoformat()
        try:
            ndl = _get_client()
            # WIKI dataset (free, US stocks, last update 2018 — use for historical only)
            df = ndl.get(f'WIKI/{ticker}',
                         start_date=start,
                         column_index=[1, 2, 3, 11])  # Open High Low Adj.Close
            if df.empty:
                return pd.DataFrame()
            df.columns = ['Open', 'High', 'Low', 'Close']
            df.index = pd.DatetimeIndex(df.index)
            return df.sort_index()
        except Exception:
            pass
        # Fallback: EOD dataset (paid but has current data)
        try:
            ndl = _get_client()
            df = ndl.get(f'EOD/{ticker}', start_date=start,
                         column_index=[1, 2, 3, 5, 6])  # O H L Adj.Close Vol
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            df.index = pd.DatetimeIndex(df.index)
            return df.sort_index()
        except Exception as exc:
            log.debug('quandl.get_ohlcv(%s): %s', ticker, exc)
            return pd.DataFrame()

    def get_fundamentals(self, ticker: str, market: str) -> dict:
        if not self.is_available() or market != 'us':
            return {}
        try:
            ndl = _get_client()
            # SHARADAR/SF1 — core US fundamentals (requires subscription)
            df = ndl.get_table('SHARADAR/SF1',
                               ticker=ticker,
                               dimension='MRY',   # most recent annual
                               qopts={'columns': ['ticker', 'pe', 'pb', 'roe',
                                                   'ebitdamargin', 'de', 'currentratio',
                                                   'marketcap', 'eps', 'divyield']})
            if df.empty:
                return {}
            r = df.iloc[-1]
            return {
                'pe':             _safe_float(r.get('pe')),
                'pb':             _safe_float(r.get('pb')),
                'roe':            _safe_float(r.get('roe')),
                'opm':            _safe_float(r.get('ebitdamargin')),
                'debt_to_equity': _safe_float(r.get('de')),
                'current_ratio':  _safe_float(r.get('currentratio')),
                'market_cap':     round(float(r['marketcap']) / 1e6, 2)
                                  if r.get('marketcap') else None,
                'eps':            _safe_float(r.get('eps')),
                'dividend_yield': _safe_float(r.get('divyield')),
            }
        except Exception as exc:
            log.debug('quandl.get_fundamentals(%s): %s', ticker, exc)
            return {}

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        df = self.get_ohlcv(ticker)
        if df.empty:
            return None
        closes  = df['Close']
        volumes = df.get('Volume')
        tech    = compute_technicals(closes, volumes)
        if not tech.get('cmp'):
            return None
        fund = self.get_fundamentals(ticker, market)
        return QuoteData(ticker=ticker, source='quandl', **{**tech, **fund})
