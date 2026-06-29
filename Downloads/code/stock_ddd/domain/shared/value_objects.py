"""
domain/shared/value_objects.py
================================
Shared Value Objects — immutable, equality by value, no identity.

Design principles (Evans, Domain-Driven Design 2003):
  - Value Objects have no conceptual identity — two Ticker("RELIANCE")
    instances are equal and interchangeable.
  - They are immutable after creation (frozen=True).
  - They encapsulate domain validation so invalid state is impossible.
  - They contain behaviour that belongs to the concept they represent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


# ── Enumerations ──────────────────────────────────────────────────────────────

class Exchange(str, Enum):
    NSE     = "NSE"      # National Stock Exchange (India)
    BSE     = "BSE"      # Bombay Stock Exchange (India)
    NASDAQ  = "NASDAQ"   # NASDAQ (US)
    NYSE    = "NYSE"     # New York Stock Exchange (US)
    UNKNOWN = "UNKNOWN"


class MarketRegime(str, Enum):
    BULL          = "BULL"          # Index > 200 DMA, DMA upsloping
    BEAR          = "BEAR"          # Index < 200 DMA, DMA downsloping
    SIDEWAYS      = "SIDEWAYS"      # Price within 1.5% of 200 DMA
    BULL_VOLATILE = "BULL_VOLATILE" # Bull but VIX ≥ 18
    BEAR_EXTREME  = "BEAR_EXTREME"  # Bear + VIX > 25


class SignalDirection(str, Enum):
    BUY     = "BUY"
    SELL    = "SELL"
    NEUTRAL = "NEUTRAL"
    HOLD    = "HOLD"


class PEZone(str, Enum):
    BUY_ZONE   = "BUY ZONE"    # 🟢 PE well below sector average
    FAIR_VALUE = "FAIR VALUE"  # 🟡 PE within normal range
    CAUTION    = "CAUTION"     # 🟠 PE above normal
    SELL_ZONE  = "SELL ZONE"   # 🔴 PE significantly above sector norms
    NA         = "N/A"         # ⚪ Not available


# ── Core Value Objects ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Ticker:
    """
    A stock ticker symbol with its exchange context.
    Immutable — two Ticker("RELIANCE", Exchange.NSE) are always equal.
    """
    symbol:   str
    exchange: Exchange = Exchange.NSE

    def __post_init__(self):
        if not self.symbol or not self.symbol.strip():
            raise ValueError("Ticker symbol cannot be empty")
        # Normalise to uppercase (defensive)
        object.__setattr__(self, "symbol", self.symbol.strip().upper())

    @property
    def yfinance_symbol(self) -> str:
        """Returns yfinance-compatible ticker (e.g. RELIANCE.NS, AAPL)."""
        suffix_map = {Exchange.NSE: ".NS", Exchange.BSE: ".BO"}
        return self.symbol + suffix_map.get(self.exchange, "")

    @property
    def display(self) -> str:
        """Human-readable: RELIANCE [NSE]"""
        return f"{self.symbol} [{self.exchange.value}]"

    def __str__(self) -> str:
        return self.yfinance_symbol


@dataclass(frozen=True)
class Price:
    """
    A monetary price in a specific currency.
    Prevents mixing INR and USD prices accidentally.
    """
    amount:   float
    currency: str = "INR"   # ISO 4217

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError(f"Price cannot be negative: {self.amount}")

    def __add__(self, other: Price) -> Price:
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Price(self.amount + other.amount, self.currency)

    def __sub__(self, other: Price) -> Price:
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract {self.currency} from {other.currency}")
        return Price(self.amount - other.amount, self.currency)

    @property
    def symbol(self) -> str:
        return "₹" if self.currency == "INR" else "$"

    def __str__(self) -> str:
        return f"{self.symbol}{self.amount:,.2f}"


@dataclass(frozen=True)
class Percentage:
    """A percentage value (e.g. return, change, upside)."""
    value: float   # e.g. 5.25 means 5.25%

    def __str__(self) -> str:
        sign = "+" if self.value >= 0 else ""
        return f"{sign}{self.value:.2f}%"

    def as_decimal(self) -> float:
        return self.value / 100.0

    @classmethod
    def from_decimal(cls, decimal: float) -> Percentage:
        return cls(decimal * 100.0)


@dataclass(frozen=True)
class DateRange:
    """An inclusive date range [start, end]."""
    start: date
    end:   date

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError(f"DateRange start ({self.start}) must be ≤ end ({self.end})")

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def __str__(self) -> str:
        return f"{self.start} – {self.end}"


@dataclass(frozen=True)
class ReturnHorizon:
    """
    A forward-looking return measurement horizon.
    Encapsulates the mapping from label to trading days.
    """
    label:         str    # "T+21d"
    trading_days:  int    # 21

    # Pre-defined horizons (factory methods)
    @classmethod
    def next_day(cls)     -> "ReturnHorizon": return cls("T+1d",   1)
    @classmethod
    def three_days(cls)   -> "ReturnHorizon": return cls("T+3d",   3)
    @classmethod
    def one_week(cls)     -> "ReturnHorizon": return cls("T+5d",   5)
    @classmethod
    def two_weeks(cls)    -> "ReturnHorizon": return cls("T+10d", 10)
    @classmethod
    def one_month(cls)    -> "ReturnHorizon": return cls("T+21d", 21)
    @classmethod
    def three_months(cls) -> "ReturnHorizon": return cls("T+63d", 63)
    @classmethod
    def six_months(cls)   -> "ReturnHorizon": return cls("T+126d", 126)
    @classmethod
    def one_year(cls)     -> "ReturnHorizon": return cls("T+252d", 252)

    @staticmethod
    def all_horizons() -> list:
        """All 8 standard return horizons in ascending order."""
        return [
            ReturnHorizon("T+1d", 1), ReturnHorizon("T+3d", 3),
            ReturnHorizon("T+5d", 5), ReturnHorizon("T+10d", 10),
            ReturnHorizon("T+21d", 21), ReturnHorizon("T+63d", 63),
            ReturnHorizon("T+126d", 126), ReturnHorizon("T+252d", 252),
        ]

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True)
class VIXLevel:
    """
    India VIX or CBOE VIX level with regime interpretation.
    Encapsulates the classification rules (so they live in the domain).
    """
    value: float

    @property
    def regime(self) -> str:
        if self.value > 30:   return "PANIC"
        if self.value > 22:   return "HIGH_FEAR"
        if self.value > 17:   return "ELEVATED"
        if self.value > 12:   return "NORMAL"
        return "COMPLACENCY"

    @property
    def position_size_factor(self) -> float:
        """Recommended position size scaling based on VIX (1.0 = full size)."""
        if self.value > 30:   return 0.25
        if self.value > 22:   return 0.50
        if self.value > 17:   return 0.75
        return 1.0

    def __str__(self) -> str:
        return f"VIX {self.value:.2f} [{self.regime}]"
