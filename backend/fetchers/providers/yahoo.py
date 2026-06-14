"""
Yahoo Finance provider via yfinance.
Primary source for all non-US markets; global coverage, no API key required.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Optional

import pandas as pd

from fetchers.providers.base import DataProvider, QuoteData, compute_technicals

log = logging.getLogger(__name__)

_RATE_BACKOFFS = [90, 180, 300]


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _pct(v) -> Optional[float]:
    f = _safe_float(v)
    return round(f * 100, 2) if f is not None else None


class YahooProvider(DataProvider):
    name = 'yahoo'

    def is_available(self) -> bool:
        try:
            import yfinance  # noqa: F401
            return True
        except ImportError:
            return False

    def get_ohlcv(self, ticker: str, period_days: int = 365) -> pd.DataFrame:
        try:
            import yfinance as yf
            period = '1y' if period_days <= 365 else '2y'
            df = yf.download(ticker, period=period, auto_adjust=True,
                             progress=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as exc:
            log.debug('yahoo.get_ohlcv(%s): %s', ticker, exc)
            return pd.DataFrame()

    def get_quotes_bulk(self, tickers: list[str], market: str) -> dict[str, QuoteData]:
        """Download 1-year OHLCV for a batch, compute technicals."""
        try:
            import yfinance as yf
        except ImportError:
            return {}

        raw = None
        for attempt, backoff in enumerate([0] + _RATE_BACKOFFS):
            if backoff:
                time.sleep(backoff)
            try:
                raw = yf.download(tickers, period='1y', auto_adjust=True,
                                  progress=False, threads=False)
                break
            except Exception as exc:
                if 'rate' in str(exc).lower() or '429' in str(exc):
                    continue
                log.warning('yahoo.get_quotes_bulk: %s', exc)
                return {}

        if raw is None or raw.empty:
            return {}

        multi = isinstance(raw.columns, pd.MultiIndex)
        result: dict[str, QuoteData] = {}

        for ticker in tickers:
            try:
                if multi:
                    close_col  = ('Close',  ticker)
                    volume_col = ('Volume', ticker)
                    high_col   = ('High',   ticker)
                    low_col    = ('Low',    ticker)
                    if close_col not in raw.columns:
                        continue
                    closes  = raw[close_col].dropna()
                    volumes = raw[volume_col].dropna() if volume_col in raw.columns else None
                    highs   = raw[high_col].dropna()   if high_col   in raw.columns else None
                    lows    = raw[low_col].dropna()    if low_col    in raw.columns else None
                else:
                    closes  = raw['Close'].dropna()
                    volumes = raw.get('Volume', pd.Series(dtype=float)).dropna()
                    highs   = raw['High'].dropna() if 'High' in raw.columns else None
                    lows    = raw['Low'].dropna()  if 'Low'  in raw.columns else None

                if len(closes) < 2:
                    continue

                tech = compute_technicals(closes, volumes, highs, lows)
                if not tech.get('cmp'):
                    continue

                result[ticker] = QuoteData(ticker=ticker, source='yahoo', **tech)
            except Exception as exc:
                log.debug('yahoo bulk[%s]: %s', ticker, exc)

        return result

    def get_fundamentals(self, ticker: str, market: str) -> dict:
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            if not info:
                return {}
            is_inr = market == 'india'
            mc = info.get('marketCap')
            return {
                'pe':             _safe_float(info.get('trailingPE')),
                'pb':             _safe_float(info.get('priceToBook')),
                'roe':            _pct(info.get('returnOnEquity')),
                'opm':            _pct(info.get('operatingMargins')),
                'market_cap':     round(mc / (1e7 if is_inr else 1e6), 2) if mc else None,
                'debt_to_equity': _safe_float(info.get('debtToEquity')),
                'beta':           _safe_float(info.get('beta')),
                'current_ratio':  _safe_float(info.get('currentRatio')),
                'revenue_growth': _pct(info.get('revenueGrowth')),
                'eps':            _safe_float(info.get('trailingEps')),
                'dividend_yield': _pct(info.get('dividendYield')),
                'sector':         info.get('sector') or None,
                'industry':       info.get('industry') or None,
                'name':           info.get('longName') or info.get('shortName') or None,
            }
        except Exception as exc:
            log.debug('yahoo.get_fundamentals(%s): %s', ticker, exc)
            return {}

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        df = self.get_ohlcv(ticker)
        if df.empty:
            return None
        closes  = df['Close'].dropna()  if 'Close'  in df.columns else pd.Series(dtype=float)
        volumes = df['Volume'].dropna() if 'Volume' in df.columns else None
        highs   = df['High'].dropna()   if 'High'   in df.columns else None
        lows    = df['Low'].dropna()    if 'Low'    in df.columns else None
        tech = compute_technicals(closes, volumes, highs, lows)
        if not tech.get('cmp'):
            return None
        fund = self.get_fundamentals(ticker, market)
        return QuoteData(ticker=ticker, source='yahoo', **{**tech, **fund})
