"""
Provider registry — lazy-imports each provider class and exposes a
singleton instance for each.  Providers that require optional libraries
or API keys degrade gracefully (is_available() → False).
"""
from __future__ import annotations

from fetchers.providers.alpha_vantage import AlphaVantageProvider
from fetchers.providers.base import DataProvider, QuoteData, compute_technicals
from fetchers.providers.currencylayer import CurrencylayerProvider
from fetchers.providers.iex import IEXProvider
from fetchers.providers.interactive_brokers import InteractiveBrokersProvider
from fetchers.providers.polygon import PolygonProvider
from fetchers.providers.quandl_ndl import QuandlNDLProvider
from fetchers.providers.tradier import TradierProvider
from fetchers.providers.tradingview import TradingViewProvider
from fetchers.providers.yahoo import YahooProvider

# Singletons
yahoo               = YahooProvider()
alpha_vantage       = AlphaVantageProvider()
polygon             = PolygonProvider()
iex                 = IEXProvider()
tradier             = TradierProvider()
quandl              = QuandlNDLProvider()
currencylayer       = CurrencylayerProvider()
interactive_brokers = InteractiveBrokersProvider()
tradingview         = TradingViewProvider()

ALL_PROVIDERS: dict[str, DataProvider] = {
    'yahoo':               yahoo,
    'polygon':             polygon,
    'iex':                 iex,
    'tradier':             tradier,
    'alpha_vantage':       alpha_vantage,
    'quandl':              quandl,
    'currencylayer':       currencylayer,
    'interactive_brokers': interactive_brokers,
    'tradingview':         tradingview,
}


def available_providers() -> list[str]:
    """Return names of providers that are currently configured and importable."""
    return [name for name, p in ALL_PROVIDERS.items() if p.is_available()]


__all__ = [
    'DataProvider', 'QuoteData', 'compute_technicals',
    'yahoo', 'alpha_vantage', 'polygon', 'iex', 'tradier',
    'quandl', 'currencylayer', 'interactive_brokers', 'tradingview',
    'ALL_PROVIDERS', 'available_providers',
]
