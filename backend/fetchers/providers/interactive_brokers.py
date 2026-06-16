"""
Interactive Brokers provider via ib_insync.
Requires IB Gateway or TWS running on IB_HOST:IB_PORT (default 127.0.0.1:7497).
Supports global markets through IB's market data subscriptions.

Setup:
  1. Install IB Gateway (free) or TWS desktop app
  2. Enable API connections: Configure → API → Settings → Enable ActiveX and Socket Clients
  3. Set port: 7497 (paper) / 7496 (live)
  4. pip install ib_insync
"""
from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config.providers import cfg
from fetchers.providers.base import DataProvider, QuoteData, compute_technicals

log = logging.getLogger(__name__)
_lock = threading.Lock()
_ib   = None   # ib_insync.IB instance (lazily connected)


def _connect():
    global _ib
    with _lock:
        if _ib is not None and _ib.isConnected():
            return _ib
        try:
            from ib_insync import IB
            ib = IB()
            ib.connect(cfg.IB_HOST, cfg.IB_PORT, clientId=cfg.IB_CLIENT_ID,
                       timeout=10, readonly=True)
            _ib = ib
            log.info('IB Gateway connected at %s:%d', cfg.IB_HOST, cfg.IB_PORT)
            return ib
        except Exception as exc:
            log.debug('IB connect failed: %s', exc)
            return None


def _disconnect():
    global _ib
    with _lock:
        if _ib and _ib.isConnected():
            try:
                _ib.disconnect()
            except Exception:
                pass
        _ib = None


def _contract_for(ticker: str, market: str):
    """Build an ib_insync Contract for a given ticker + market."""
    from ib_insync import Forex, Stock
    exchange_map = {
        'us':        ('SMART',    'USD'),
        'india':     ('NSE',      'INR'),
        'europe':    ('SMART',    'EUR'),
        'japan':     ('TSEJ',     'JPY'),
        'korea':     ('KSE',      'KRW'),
        'china':     ('SEHK',     'CNH'),
        'hong_kong': ('SEHK',     'HKD'),
        'canada':    ('TSE',      'CAD'),
    }
    exch, currency = exchange_map.get(market, ('SMART', 'USD'))
    # Strip exchange suffix from ticker if present
    bare = ticker.split('.')[0]
    return Stock(bare, exch, currency)


class InteractiveBrokersProvider(DataProvider):
    name = 'interactive_brokers'

    def is_available(self) -> bool:
        return _connect() is not None

    def get_ohlcv(self, ticker: str, period_days: int = 365) -> pd.DataFrame:
        ib = _connect()
        if ib is None:
            return pd.DataFrame()
        try:
            from ib_insync import util
            contract = _contract_for(ticker, 'us')
            ib.qualifyContracts(contract)
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=f'{min(period_days, 365)} D',
                barSizeSetting='1 day',
                whatToShow='ADJUSTED_LAST',
                useRTH=True,
                formatDate=1,
            )
            if not bars:
                return pd.DataFrame()
            df = util.df(bars).set_index('date')
            df.index = pd.DatetimeIndex(df.index)
            return df[['open', 'high', 'low', 'close', 'volume']].rename(columns={
                'open': 'Open', 'high': 'High', 'low': 'Low',
                'close': 'Close', 'volume': 'Volume'
            })
        except Exception as exc:
            log.debug('ib.get_ohlcv(%s): %s', ticker, exc)
            return pd.DataFrame()

    def get_fundamentals(self, ticker: str, market: str) -> dict:
        ib = _connect()
        if ib is None:
            return {}
        try:
            contract  = _contract_for(ticker, market)
            ib.qualifyContracts(contract)
            # IB fundamental data report types: 'ReportsFinSummary', 'ReportSnapshot'
            xml = ib.reqFundamentalData(contract, 'ReportSnapshot')
            if not xml:
                return {}
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml)

            def _find(tag: str) -> Optional[float]:
                el = root.find(f'.//{tag}')
                try:
                    return float(el.text) if el is not None and el.text else None
                except (ValueError, TypeError):
                    return None

            return {
                'pe':             _find('PEEXCLXOR') or _find('TTMPE'),
                'pb':             _find('PRICE2BK'),
                'roe':            _find('TTMROEPCT'),
                'opm':            _find('TTMOPMGN'),
                'market_cap':     _find('MKTCAP'),
                'debt_to_equity': _find('TTMDEBT2EQ') or _find('QDEBT2EQ'),
                'beta':           _find('BETA'),
                'current_ratio':  _find('QCURRATIO'),
                'eps':            _find('TTMEPS'),
                'dividend_yield': _find('TTMDIVSHR'),
            }
        except Exception as exc:
            log.debug('ib.get_fundamentals(%s): %s', ticker, exc)
            return {}

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        df = self.get_ohlcv(ticker, period_days=365)
        if df.empty:
            return None
        tech = compute_technicals(df['Close'], df.get('Volume'))
        if not tech.get('cmp'):
            return None
        fund = self.get_fundamentals(ticker, market)
        return QuoteData(ticker=ticker, source='interactive_brokers', **{**tech, **fund})

    def get_live_price(self, ticker: str, market: str = 'us') -> Optional[float]:
        """Request real-time market data snapshot."""
        ib = _connect()
        if ib is None:
            return None
        try:
            from ib_insync import util
            contract = _contract_for(ticker, market)
            ib.qualifyContracts(contract)
            ticker_obj = ib.reqMktData(contract, '', False, False)
            ib.sleep(2)   # wait for data
            price = ticker_obj.last or ticker_obj.close
            ib.cancelMktData(contract)
            return float(price) if price else None
        except Exception as exc:
            log.debug('ib.get_live_price(%s): %s', ticker, exc)
            return None
