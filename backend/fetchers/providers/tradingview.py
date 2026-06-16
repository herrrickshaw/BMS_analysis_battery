"""
TradingView provider via tvdatafeed (unofficial, community library).
Works without credentials (delayed/limited) or with a TV account for full history.
Supports all global exchanges through TradingView's data feed.
https://github.com/StreamAlpha/tvdatafeed

pip install tvdatafeed
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from config.providers import cfg
from fetchers.providers.base import DataProvider, QuoteData, compute_technicals

log = logging.getLogger(__name__)

# TradingView exchange codes per market
_TV_EXCHANGE: dict[str, str] = {
    'us':        'NASDAQ',
    'india':     'NSE',
    'europe':    'XETR',       # Deutsche Boerse; suffix-mapped per ticker
    'japan':     'TSE',
    'korea':     'KRX',
    'china':     'SSE',
    'hong_kong': 'HKEX',
    'canada':    'TSX',
}

# Suffix → TradingView exchange override
_SUFFIX_TV: dict[str, str] = {
    '.NS': 'NSE', '.BO': 'BSE',
    '.T':  'TSE',
    '.KS': 'KRX', '.KQ': 'KOSDAQ',
    '.SS': 'SSE', '.SZ': 'SZSE',
    '.HK': 'HKEX',
    '.TO': 'TSX',
    '.L':  'LSE',   '.DE': 'XETR',  '.F': 'FWB',
    '.PA': 'EURONEXT', '.MI': 'MIL', '.AS': 'EURONEXT',
}


def _get_tv():
    """Return a tvdatafeed TvDatafeed instance, anonymous or authenticated."""
    try:
        from tvdatafeed import TvDatafeed
        if cfg.TRADINGVIEW_USER and cfg.TRADINGVIEW_PASS:
            return TvDatafeed(cfg.TRADINGVIEW_USER, cfg.TRADINGVIEW_PASS)
        return TvDatafeed()   # anonymous — delayed, limited history
    except Exception as exc:
        log.debug('tvdatafeed init: %s', exc)
        return None


def _tv_symbol_exchange(ticker: str, market: str) -> tuple[str, str]:
    """Map a yfinance-style ticker to (tv_symbol, tv_exchange)."""
    if '.' in ticker:
        parts = ticker.rsplit('.', 1)
        suffix = '.' + parts[1]
        exchange = _SUFFIX_TV.get(suffix, _TV_EXCHANGE.get(market, 'NASDAQ'))
        return parts[0], exchange
    return ticker, _TV_EXCHANGE.get(market, 'NASDAQ')


class TradingViewProvider(DataProvider):
    name = 'tradingview'

    def is_available(self) -> bool:
        try:
            from tvdatafeed import TvDatafeed  # noqa: F401
            return True
        except ImportError:
            return False

    def get_ohlcv(self, ticker: str, period_days: int = 365,
                  market: str = 'us') -> pd.DataFrame:
        tv = _get_tv()
        if tv is None:
            return pd.DataFrame()
        try:
            from tvdatafeed import Interval
            sym, exch = _tv_symbol_exchange(ticker, market)
            n_bars    = min(period_days + 20, 5000)
            df = tv.get_hist(symbol=sym, exchange=exch,
                             interval=Interval.in_daily, n_bars=n_bars)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={'open': 'Open', 'high': 'High',
                                     'low': 'Low', 'close': 'Close',
                                     'volume': 'Volume'})
            return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(subset=['Close'])
        except Exception as exc:
            log.debug('tradingview.get_ohlcv(%s): %s', ticker, exc)
            return pd.DataFrame()

    def get_quotes_bulk(self, tickers: list[str], market: str) -> dict[str, QuoteData]:
        tv = _get_tv()
        if tv is None:
            return {}
        result: dict[str, QuoteData] = {}
        for ticker in tickers:
            try:
                df = self.get_ohlcv(ticker, period_days=365, market=market)
                if df.empty:
                    continue
                tech = compute_technicals(df['Close'], df.get('Volume'))
                if tech.get('cmp'):
                    result[ticker] = QuoteData(ticker=ticker, source='tradingview', **tech)
            except Exception as exc:
                log.debug('tradingview bulk[%s]: %s', ticker, exc)
        return result

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        df = self.get_ohlcv(ticker, market=market)
        if df.empty:
            return None
        tech = compute_technicals(df['Close'], df.get('Volume'))
        if not tech.get('cmp'):
            return None
        return QuoteData(ticker=ticker, source='tradingview', **tech)
