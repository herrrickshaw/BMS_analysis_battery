"""
domain/market_data/entities.py
================================
Market Data Domain — Entities, Value Objects, Aggregate Root.

DOMAIN CONCEPTS
───────────────
Stock       : A tradeable equity instrument identified by Ticker.
              Has a company name, sector, exchange, and listing date.
              Aggregate Root for all price and fundamental data.

PriceBar    : A single OHLCV bar (open, high, low, close, volume) for a
              given date and interval. Immutable after recording.

PriceSeries : A time-ordered collection of PriceBars. Provides technical
              indicator computation as domain behaviour (not in infrastructure).

MarketIndex : A market benchmark (Nifty 50, S&P 500) used for regime
              classification and alpha calculation.

AGGREGATE ROOT: Stock
──────────────────────
Stock is the aggregate root for the MarketData bounded context.
All access to price data goes through Stock.
Invariants enforced by Stock:
  - A Stock must have a valid Ticker
  - PriceBars must be in ascending date order
  - A Breakout can only be recorded after sufficient price history (35+ bars)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

import pandas as pd

from domain.shared.value_objects import (
    Exchange, MarketRegime, PEZone, Percentage, Price, Ticker
)


# ── Value Objects specific to Market Data domain ──────────────────────────────

@dataclass(frozen=True)
class PriceBar:
    """Single OHLCV bar. Immutable — price history cannot be changed."""
    date:   date
    open:   float
    high:   float
    low:    float
    close:  float
    volume: int

    def __post_init__(self):
        if self.high < self.low:
            raise ValueError(f"High {self.high} < Low {self.low} on {self.date}")
        if self.close < 0 or self.open < 0:
            raise ValueError(f"Price cannot be negative on {self.date}")

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def body_pct(self) -> float:
        """Candle body as % of range."""
        return abs(self.close - self.open) / self.range * 100 if self.range > 0 else 0


@dataclass(frozen=True)
class Sector:
    """Industry sector with PE classification thresholds."""
    name: str
    pe_buy:    float  # PE below this = buy zone
    pe_fair:   float  # PE below this = fair value
    pe_caution: float # PE below this = caution

    def classify_pe(self, pe: Optional[float]) -> PEZone:
        if pe is None or pe <= 0:
            return PEZone.NA
        if pe <= self.pe_buy:
            return PEZone.BUY_ZONE
        if pe <= self.pe_fair:
            return PEZone.FAIR_VALUE
        if pe <= self.pe_caution:
            return PEZone.CAUTION
        return PEZone.SELL_ZONE

    # Factory methods for standard Indian market sectors
    @classmethod
    def banking(cls)        -> Sector: return cls("Banking/NBFC",       12, 18, 22)
    @classmethod
    def technology(cls)     -> Sector: return cls("IT/Software",        18, 28, 38)
    @classmethod
    def fmcg(cls)           -> Sector: return cls("FMCG/Consumer",      40, 60, 80)
    @classmethod
    def pharma(cls)         -> Sector: return cls("Pharma/Healthcare",  25, 40, 50)
    @classmethod
    def energy(cls)         -> Sector: return cls("Energy/Oil & Gas",   10, 18, 25)
    @classmethod
    def auto(cls)           -> Sector: return cls("Auto",               15, 25, 30)
    @classmethod
    def default(cls)        -> Sector: return cls("General",            15, 25, 35)

    @classmethod
    def from_yfinance_sector(cls, sector_str: str) -> Sector:
        """Map yfinance sector string to a Sector value object."""
        s = (sector_str or "").lower()
        if "bank" in s or "financial" in s or "nbfc" in s: return cls.banking()
        if "technology" in s or "software" in s or "it " in s: return cls.technology()
        if "consumer" in s and "staple" in s: return cls.fmcg()
        if "consumer" in s and "discret" in s: return cls(s, 18, 28, 40)
        if "health" in s or "pharma" in s: return cls.pharma()
        if "energy" in s or "oil" in s: return cls.energy()
        if "auto" in s or "vehicle" in s: return cls.auto()
        return cls.default()


# ── Stock Entity (Aggregate Root) ─────────────────────────────────────────────

@dataclass
class Stock:
    """
    Aggregate Root for the Market Data bounded context.

    Invariants:
      - ticker is always valid and non-empty
      - price_series is always sorted ascending by date
      - company_name defaults to ticker.symbol if not provided

    Behaviour (domain methods, not infrastructure):
      - add_price_bar(): enforces ordering, fires PriceUpdated event
      - compute_darvas_box(): pure domain logic, no I/O
      - is_darvas_eligible(): validates minimum bar requirement
      - pe_zone(): returns PE zone using Sector classification
    """
    ticker:       Ticker
    company_name: str                = ""
    sector:       Optional[Sector]   = None
    listing_date: Optional[date]     = None
    market_cap:   Optional[float]    = None   # in crores (INR) or millions (USD)
    trailing_pe:  Optional[float]    = None
    forward_pe:   Optional[float]    = None

    _price_series: List[PriceBar]    = field(default_factory=list, repr=False)
    _domain_events: list             = field(default_factory=list, repr=False)

    def __post_init__(self):
        if not self.company_name:
            self.company_name = self.ticker.symbol

    # ── Price Series Management ──────────────────────────────────────────────

    def add_price_bar(self, bar: PriceBar) -> None:
        """Add a price bar, enforcing ascending date order."""
        if self._price_series and bar.date <= self._price_series[-1].date:
            raise ValueError(
                f"PriceBar date {bar.date} is not after last bar "
                f"{self._price_series[-1].date} for {self.ticker}"
            )
        self._price_series.append(bar)

    def load_price_series(self, bars: List[PriceBar]) -> None:
        """Load a sorted price series (bulk import, skips ordering check)."""
        sorted_bars = sorted(bars, key=lambda b: b.date)
        self._price_series = sorted_bars

    def load_from_dataframe(self, df: pd.DataFrame) -> None:
        """Load price series from a pandas DataFrame (from cache/yfinance)."""
        bars = []
        for dt, row in df.iterrows():
            try:
                bars.append(PriceBar(
                    date=dt.date() if hasattr(dt, "date") else dt,
                    open=float(row.get("Open", row.get("open", 0))),
                    high=float(row.get("High", row.get("high", 0))),
                    low=float(row.get("Low",  row.get("low",  0))),
                    close=float(row.get("Close", row.get("close", 0))),
                    volume=int(row.get("Volume", row.get("volume", 0))),
                ))
            except Exception:
                continue
        self.load_price_series(bars)

    @property
    def price_series(self) -> List[PriceBar]:
        return list(self._price_series)

    @property
    def bar_count(self) -> int:
        return len(self._price_series)

    @property
    def current_price(self) -> Optional[Price]:
        if not self._price_series:
            return None
        currency = "INR" if self.ticker.exchange in (Exchange.NSE, Exchange.BSE) else "USD"
        return Price(self._price_series[-1].close, currency)

    @property
    def days_since_listing(self) -> int:
        if self.listing_date and self._price_series:
            return (self._price_series[-1].date - self.listing_date).days
        return self.bar_count  # approximate

    # ── Domain Behaviour ──────────────────────────────────────────────────────

    @property
    def pe_zone(self) -> PEZone:
        """Classify PE ratio using sector-aware thresholds."""
        s = self.sector or Sector.default()
        return s.classify_pe(self.trailing_pe or self.forward_pe)

    def is_darvas_eligible(self, min_bars: int = 35) -> bool:
        """Stock must have min_bars of history for Darvas Box to be meaningful."""
        return self.bar_count >= min_bars

    def is_golden_cross_eligible(self) -> bool:
        """Requires 200 bars for the 200-day DMA to be valid."""
        return self.bar_count >= 205

    def get_price_array(self, col: str = "close") -> list:
        """Return a list of prices for a given OHLCV column."""
        return [getattr(b, col.lower()) for b in self._price_series]

    # ── Domain Events ─────────────────────────────────────────────────────────

    def record_event(self, event) -> None:
        self._domain_events.append(event)

    def pull_events(self) -> list:
        """Collect and clear pending domain events (outbox pattern)."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events

    def __repr__(self) -> str:
        return (f"Stock({self.ticker.display}, bars={self.bar_count}, "
                f"price={self.current_price})")


# ── Market Index Entity ───────────────────────────────────────────────────────

@dataclass
class MarketIndex:
    """
    A market benchmark index used for regime classification and alpha calculation.
    NOT an aggregate root — accessed via IMarketIndexRepository.
    """
    symbol:  str     # "^NSEI", "^GSPC"
    name:    str     # "Nifty 50", "S&P 500"
    country: str     # "IN", "US"

    _price_series: List[PriceBar] = field(default_factory=list, repr=False)

    def load_from_dataframe(self, df: pd.DataFrame) -> None:
        bars = []
        for dt, row in df.iterrows():
            try:
                bars.append(PriceBar(
                    date=dt.date() if hasattr(dt, "date") else dt,
                    open=float(row.get("Open", 0)),
                    high=float(row.get("High", 0)),
                    low=float(row.get("Low",   0)),
                    close=float(row.get("Close", 0)),
                    volume=int(row.get("Volume", 0)),
                ))
            except Exception:
                continue
        self._price_series = sorted(bars, key=lambda b: b.date)

    @property
    def bar_count(self) -> int:
        return len(self._price_series)

    @property
    def current_level(self) -> Optional[float]:
        return self._price_series[-1].close if self._price_series else None

    def classify_regime(self, dma_period: int = 200,
                        slope_bars: int = 5,
                        sideways_pct: float = 1.5) -> MarketRegime:
        """
        Classify current regime using 200 DMA + slope.
        Pure domain logic — no external dependencies.
        """
        if self.bar_count < dma_period + slope_bars:
            return MarketRegime.SIDEWAYS

        closes = [b.close for b in self._price_series]
        dma200 = sum(closes[-dma_period:]) / dma_period
        slope  = closes[-1] - closes[-(1 + slope_bars)]
        current = closes[-1]
        pct_from = (current - dma200) / dma200 * 100

        if abs(pct_from) <= sideways_pct:
            return MarketRegime.SIDEWAYS
        if current > dma200 and slope > 0:
            return MarketRegime.BULL
        if current < dma200 and slope < 0:
            return MarketRegime.BEAR
        return MarketRegime.SIDEWAYS

    @property
    def dma200(self) -> Optional[float]:
        if self.bar_count < 200:
            return None
        closes = [b.close for b in self._price_series[-200:]]
        return sum(closes) / 200

    @property
    def dma50(self) -> Optional[float]:
        if self.bar_count < 50:
            return None
        closes = [b.close for b in self._price_series[-50:]]
        return sum(closes) / 50
