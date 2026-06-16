"""
Multi-source data fetcher.

Routes quote and fundamentals requests to the best available provider
per market, with automatic fallback and result merging.

Priority matrix (higher = tried first):
  US stocks:        Polygon → IEX → Tradier → TradingView → Alpha Vantage → Yahoo
  India:            IB → Yahoo → Alpha Vantage → TradingView
  Europe:           IB → Yahoo → TradingView → Alpha Vantage
  Japan / Korea:    IB → Yahoo → TradingView
  HK / Canada:      IB → Yahoo → TradingView
  China:            Yahoo → TradingView
  Fundamentals US:  Polygon → IEX → Quandl → Alpha Vantage → Yahoo
  Fundamentals ROW: Yahoo → Alpha Vantage
  FX rates:         Currencylayer → Alpha Vantage

When a provider is not configured / not installed, it is silently skipped.
The first provider that returns a non-empty result wins (OHLCV/quotes).
Fundamentals are always merged across providers (fill-in-the-blanks strategy).
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from fetchers.providers import (
    DataProvider,
    QuoteData,
    alpha_vantage,
    currencylayer,
    iex,
    interactive_brokers,
    polygon,
    quandl,
    tradier,
    tradingview,
    yahoo,
)
from fetchers.providers.currencylayer import MARKET_CURRENCY_CODE

log = logging.getLogger(__name__)

# ── Provider priority lists ───────────────────────────────────────────────────

_OHLCV_PRIORITY: dict[str, list[DataProvider]] = {
    'us':        [polygon, iex, tradier, tradingview, alpha_vantage, yahoo],
    'india':     [interactive_brokers, yahoo, tradingview, alpha_vantage],
    'europe':    [interactive_brokers, yahoo, tradingview, alpha_vantage],
    'japan':     [interactive_brokers, yahoo, tradingview],
    'korea':     [interactive_brokers, yahoo, tradingview],
    'china':     [yahoo, tradingview],
    'hong_kong': [interactive_brokers, yahoo, tradingview],
    'canada':    [interactive_brokers, tradier, yahoo, tradingview],
}

_FUND_PRIORITY: dict[str, list[DataProvider]] = {
    'us':        [polygon, iex, quandl, alpha_vantage, yahoo],
    'india':     [yahoo, alpha_vantage],
    'europe':    [yahoo, alpha_vantage],
    'japan':     [yahoo, alpha_vantage],
    'korea':     [yahoo, alpha_vantage],
    'china':     [yahoo, alpha_vantage],
    'hong_kong': [yahoo, alpha_vantage],
    'canada':    [yahoo, alpha_vantage],
}

_BULK_PRIORITY: dict[str, list[DataProvider]] = {
    'us':        [polygon, iex, tradier, yahoo],
    'india':     [yahoo],
    'europe':    [yahoo],
    'japan':     [yahoo],
    'korea':     [yahoo],
    'china':     [yahoo],
    'hong_kong': [yahoo],
    'canada':    [yahoo],
}

_DEFAULT_PROVIDERS = [yahoo]


def _providers_for(market: str, table: dict) -> list[DataProvider]:
    return [p for p in table.get(market, _DEFAULT_PROVIDERS) if p.is_available()]


# ── Public API ────────────────────────────────────────────────────────────────

def get_ohlcv(ticker: str, market: str, period_days: int = 365) -> pd.DataFrame:
    """
    Return daily OHLCV DataFrame for a ticker from the best available provider.
    Falls back through the priority list until a non-empty result is returned.
    """
    for provider in _providers_for(market, _OHLCV_PRIORITY):
        try:
            df = provider.get_ohlcv(ticker, period_days)
            if not df.empty:
                log.debug('get_ohlcv(%s) via %s', ticker, provider.name)
                return df
        except Exception as exc:
            log.debug('%s.get_ohlcv(%s): %s', provider.name, ticker, exc)
    return pd.DataFrame()


def get_fundamentals(ticker: str, market: str) -> dict:
    """
    Return fundamentals merged from all available providers (fill-in strategy).
    Polygon/IEX/Quandl data takes precedence over Yahoo for US stocks.
    """
    merged: dict = {}
    for provider in _providers_for(market, _FUND_PRIORITY):
        try:
            fund = provider.get_fundamentals(ticker, market)
            for k, v in fund.items():
                if v is not None and merged.get(k) is None:
                    merged[k] = v
            # Stop early if all key fields are filled
            if all(merged.get(k) is not None
                   for k in ('pe', 'pb', 'roe', 'market_cap', 'sector')):
                break
        except Exception as exc:
            log.debug('%s.get_fundamentals(%s): %s', provider.name, ticker, exc)
    return merged


def get_quote(ticker: str, market: str) -> Optional[QuoteData]:
    """
    Full quote (OHLCV-derived technicals + fundamentals) for a single ticker.
    """
    # Phase 1: best provider for OHLCV
    df = get_ohlcv(ticker, market)
    if df.empty:
        return None
    from fetchers.providers.base import compute_technicals
    closes  = df['Close'].dropna() if 'Close' in df.columns else pd.Series(dtype=float)
    volumes = df['Volume'].dropna() if 'Volume' in df.columns else None
    tech    = compute_technicals(closes, volumes)
    if not tech.get('cmp'):
        return None

    # Phase 2: merged fundamentals
    fund = get_fundamentals(ticker, market)
    return QuoteData(ticker=ticker, source='multi', **{**tech, **fund})


def get_quotes_bulk(tickers: list[str], market: str) -> dict[str, QuoteData]:
    """
    Bulk OHLCV fetch: try providers in priority order.
    Each provider's batch result is accepted; only missing tickers are retried
    on the next provider.
    """
    result:  dict[str, QuoteData] = {}
    pending: list[str]            = list(tickers)

    for provider in _providers_for(market, _BULK_PRIORITY):
        if not pending:
            break
        try:
            batch = provider.get_quotes_bulk(pending, market)
            for ticker, quote in batch.items():
                if ticker not in result:
                    result[ticker] = quote
            covered = set(batch.keys())
            pending = [t for t in pending if t not in covered]
            if covered:
                log.debug('get_quotes_bulk(%s) via %s: %d/%d',
                          market, provider.name, len(covered), len(tickers))
        except Exception as exc:
            log.debug('%s.get_quotes_bulk(%s): %s', provider.name, market, exc)

    return result


def get_fx_rate(market: str) -> Optional[float]:
    """
    Return USD per 1 unit of the market's home currency.
    Uses Currencylayer first, Alpha Vantage as fallback.
    """
    currency = MARKET_CURRENCY_CODE.get(market)
    if not currency or currency == 'USD':
        return 1.0

    if currencylayer.is_available():
        rate = currencylayer.get_market_rate_to_usd(market)
        if rate is not None:
            return rate

    if alpha_vantage.is_available():
        rate = alpha_vantage.get_forex_rate(currency, 'USD')
        if rate is not None:
            return rate

    return None


def provider_status() -> dict[str, dict]:
    """Return availability and name of every provider (for /api/providers endpoint)."""
    from fetchers.providers import ALL_PROVIDERS
    return {
        name: {'available': p.is_available(), 'name': p.name}
        for name, p in ALL_PROVIDERS.items()
    }
