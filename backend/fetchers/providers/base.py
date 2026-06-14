"""
Abstract base class and shared data types for all data providers.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd


@dataclass
class QuoteData:
    """Canonical quote + fundamentals record returned by every provider."""
    ticker:          str
    source:          str

    # Price / technicals
    cmp:             Optional[float] = None
    rsi:             Optional[float] = None
    ema_50:          Optional[float] = None
    ema_200:         Optional[float] = None
    macd:            Optional[float] = None
    macd_signal:     Optional[float] = None
    rsi_signal:      str             = 'HOLD'
    high_52w:        Optional[float] = None
    low_52w:         Optional[float] = None
    volume:          Optional[int]   = None
    volume_20d_avg:  Optional[int]   = None
    volume_ratio:    Optional[float] = None

    # Period returns (%)
    ret_1d:  Optional[float] = None
    ret_1w:  Optional[float] = None
    ret_1m:  Optional[float] = None
    ret_3m:  Optional[float] = None
    ret_6m:  Optional[float] = None
    ret_1y:  Optional[float] = None

    # Fundamentals
    pe:             Optional[float] = None
    pb:             Optional[float] = None
    roe:            Optional[float] = None   # %
    opm:            Optional[float] = None   # %
    market_cap:     Optional[float] = None   # USD M or INR Cr
    debt_to_equity: Optional[float] = None
    beta:           Optional[float] = None
    current_ratio:  Optional[float] = None
    revenue_growth: Optional[float] = None   # %
    eps:            Optional[float] = None
    dividend_yield: Optional[float] = None   # %

    # Meta
    sector:   Optional[str] = None
    industry: Optional[str] = None
    name:     Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def merge(self, other: 'QuoteData') -> 'QuoteData':
        """Fill None fields from another QuoteData (self takes priority)."""
        d = asdict(self)
        for k, v in asdict(other).items():
            if d.get(k) is None and v is not None:
                d[k] = v
        d['source'] = f'{self.source}+{other.source}'
        return QuoteData(**d)


def compute_technicals(closes: pd.Series, volumes: Optional[pd.Series] = None) -> dict:
    """
    Compute RSI-14, EMA-50/200, MACD, 52W hi/lo, period returns, volume ratio
    from a daily close series.  Returns a partial QuoteData-compatible dict.
    """
    if closes is None or len(closes) < 2:
        return {}

    closes = closes.dropna()
    n = len(closes)
    cmp = float(closes.iloc[-1])

    # RSI-14
    rsi = None
    if n >= 15:
        delta = closes.diff().dropna()
        gains  = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        ag = gains.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
        al = losses.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
        rsi = 100.0 if al == 0 else round(100 - 100 / (1 + ag / al), 2)

    ema50  = round(float(closes.ewm(span=50,  adjust=False).mean().iloc[-1]), 2)
    ema200 = round(float(closes.ewm(span=200, adjust=False).mean().iloc[-1]), 2) if n >= 50 else None

    # MACD
    macd_val = macd_sig = None
    if n >= 26:
        e12 = closes.ewm(span=12, adjust=False).mean()
        e26 = closes.ewm(span=26, adjust=False).mean()
        ml  = e12 - e26
        macd_val = round(float(ml.iloc[-1]), 4)
        if n >= 35:
            macd_sig = round(float(ml.ewm(span=9, adjust=False).mean().iloc[-1]), 4)

    # 52W hi/lo
    w = min(252, n)
    h52 = round(float(closes.rolling(w).max().iloc[-1]), 2)
    l52 = round(float(closes.rolling(w).min().iloc[-1]), 2)

    # Returns
    def _ret(nb: int):
        if n <= nb:
            return None
        prev = float(closes.iloc[-(nb + 1)])
        return round((cmp - prev) / prev * 100, 2) if prev > 0 and not math.isnan(prev) else None

    ret_1y = None
    if n >= 2:
        first = float(closes.iloc[0])
        ret_1y = round((cmp - first) / first * 100, 2) if first > 0 and not math.isnan(first) else None

    # Volume
    vol = vol_avg = vol_ratio = None
    if volumes is not None and len(volumes) >= 1:
        volumes = volumes.dropna()
        if not volumes.empty:
            vol = int(volumes.iloc[-1])
            if len(volumes) >= 5:
                vw = min(20, len(volumes))
                vol_avg = int(volumes.iloc[-vw:].mean())
                vol_ratio = round(vol / vol_avg, 2) if vol_avg > 0 else None

    # RSI signal
    if rsi is None:
        sig = 'HOLD'
    elif rsi < 30 and cmp > ema50:
        sig = 'BUY'
    elif rsi > 70 and cmp < ema50:
        sig = 'SELL'
    else:
        sig = 'HOLD'

    return {
        'cmp': round(cmp, 2), 'rsi': rsi, 'ema_50': ema50, 'ema_200': ema200,
        'macd': macd_val, 'macd_signal': macd_sig, 'rsi_signal': sig,
        'high_52w': h52, 'low_52w': l52,
        'volume': vol, 'volume_20d_avg': vol_avg, 'volume_ratio': vol_ratio,
        'ret_1d': _ret(1), 'ret_1w': _ret(5), 'ret_1m': _ret(21),
        'ret_3m': _ret(63), 'ret_6m': _ret(126), 'ret_1y': ret_1y,
    }


class DataProvider(ABC):
    """Abstract base for all data providers."""

    name: str = 'base'

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""
        ...

    def get_quote(self, ticker: str, market: str) -> Optional[QuoteData]:
        """Fetch a single quote.  Override for providers with live quote endpoints."""
        return None

    def get_quotes_bulk(self, tickers: list[str], market: str) -> dict[str, QuoteData]:
        """
        Fetch multiple quotes in one call (batch endpoint).
        Default: calls get_quote() sequentially.  Override for true batch APIs.
        """
        result: dict[str, QuoteData] = {}
        for t in tickers:
            q = self.get_quote(t, market)
            if q:
                result[t] = q
        return result

    def get_ohlcv(self, ticker: str, period_days: int = 365) -> pd.DataFrame:
        """
        Return daily OHLCV DataFrame with columns: Open High Low Close Volume.
        Index: DatetimeIndex.  Empty DataFrame if not available.
        """
        return pd.DataFrame()

    def get_fundamentals(self, ticker: str, market: str) -> dict:
        """
        Return fundamentals dict with keys matching QuoteData field names.
        Empty dict if not available.
        """
        return {}

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} enabled={self.is_available()}>'
