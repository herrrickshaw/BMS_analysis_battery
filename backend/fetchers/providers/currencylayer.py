"""
Currencylayer provider — forex exchange rates.
Used to convert market prices to a common currency for cross-market comparison.
Free tier: 100 req/month (USD base only).
https://currencylayer.com/documentation
"""
from __future__ import annotations

import logging
import time
from datetime import date
from functools import lru_cache
from typing import Optional

import requests

from fetchers.providers.base import DataProvider, QuoteData
from config.providers import cfg

log = logging.getLogger(__name__)
_SESSION  = requests.Session()
_CACHE_TTL = 3600   # seconds


def _get(endpoint: str, params: dict) -> dict:
    params['access_key'] = cfg.CURRENCYLAYER_KEY
    try:
        r = _SESSION.get(f'{cfg.CURRENCYLAYER_BASE}/{endpoint}',
                         params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data.get('success', True):
            log.warning('currencylayer error: %s', data.get('error'))
            return {}
        return data
    except requests.RequestException as exc:
        log.debug('currencylayer._get(%s): %s', endpoint, exc)
        return {}


# Market → ISO 4217 currency code
MARKET_CURRENCY_CODE: dict[str, str] = {
    'india':     'INR',
    'us':        'USD',
    'europe':    'EUR',
    'japan':     'JPY',
    'korea':     'KRW',
    'china':     'CNY',
    'hong_kong': 'HKD',
    'canada':    'CAD',
}


class CurrencylayerProvider(DataProvider):
    """
    Not a stock data provider — used purely for FX rate lookups.
    get_quote() always returns None; use get_rate() directly.
    """
    name = 'currencylayer'
    _rates: dict[str, float] = {}
    _rates_fetched_at: float = 0.0

    def is_available(self) -> bool:
        return bool(cfg.CURRENCYLAYER_KEY)

    def _refresh_rates(self) -> None:
        if time.time() - self._rates_fetched_at < _CACHE_TTL:
            return
        data = _get('live', {'source': 'USD'})
        quotes = data.get('quotes', {})
        if quotes:
            # Strip 'USD' prefix — keys are like 'USDINR'
            self._rates = {k[3:]: v for k, v in quotes.items()}
            self._rates_fetched_at = time.time()
            log.info('currencylayer: refreshed %d FX rates', len(self._rates))

    def get_rate(self, currency: str, base: str = 'USD') -> Optional[float]:
        """Return how many `base` units equal 1 `currency` unit."""
        if not self.is_available():
            return None
        self._refresh_rates()
        if not self._rates:
            return None
        if base == 'USD':
            rate_vs_usd = self._rates.get(currency.upper())
            return 1.0 / rate_vs_usd if rate_vs_usd else None
        # Cross rate via USD
        from_rate = self._rates.get(currency.upper())
        to_rate   = self._rates.get(base.upper())
        if from_rate and to_rate:
            return to_rate / from_rate
        return None

    def get_market_rate_to_usd(self, market: str) -> Optional[float]:
        """Return USD per 1 unit of the market's home currency."""
        code = MARKET_CURRENCY_CODE.get(market)
        return self.get_rate(code, 'USD') if code else None

    def get_historical_rate(self, currency: str, for_date: date,
                             base: str = 'USD') -> Optional[float]:
        """Return historical rate for a specific date."""
        if not self.is_available():
            return None
        data = _get('historical', {'date': for_date.isoformat(), 'source': base})
        quotes = data.get('quotes', {})
        key = f'{base}{currency}'.upper()
        rate = quotes.get(key)
        return 1.0 / float(rate) if rate else None

    # DataProvider interface stubs (not meaningful for FX-only provider)
    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        return None
