"""
domain/shared/events.py
========================
Domain Events — things that happened in the domain.

Domain Events decouple aggregates: when a BreakoutDetected event fires,
the Screening domain doesn't need to know about Reporting or Notifications.
Each interested party subscribes independently.

Pattern: Simple synchronous event bus (suitable for v3.1).
For async/microservices, replace with Kafka/RabbitMQ in Infrastructure.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Type


# ── Base Domain Event ─────────────────────────────────────────────────────────

@dataclass
class DomainEvent:
    """Base class for all domain events."""
    event_id:   str      = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def event_name(self) -> str:
        return self.__class__.__name__


# ── Market Data Events ────────────────────────────────────────────────────────

@dataclass
class PriceDataUpdated(DomainEvent):
    """Fired when new OHLCV data is available for a stock."""
    ticker:     str = ""
    bars_added: int = 0
    from_date:  str = ""
    to_date:    str = ""


@dataclass
class CacheWarmed(DomainEvent):
    """Fired when the Parquet cache has been populated."""
    symbols_cached: int = 0
    total_bars:     int = 0
    cache_size_mb:  float = 0.0


@dataclass
class MarketRegimeChanged(DomainEvent):
    """Fired when the Nifty 50 / S&P 500 regime changes."""
    index:      str = ""   # "NIFTY50" or "SP500"
    old_regime: str = ""
    new_regime: str = ""
    vix:        float = 0.0


# ── Screening Events ──────────────────────────────────────────────────────────

@dataclass
class BreakoutDetected(DomainEvent):
    """Fired when a Darvas Box breakout is confirmed (volume + price)."""
    ticker:    str   = ""
    exchange:  str   = ""
    price:     float = 0.0
    box_top:   float = 0.0
    upside_pct: float = 0.0
    screener:  str   = "DarvasBox"


@dataclass
class MultiScreenHitDetected(DomainEvent):
    """Fired when a stock passes 3+ screeners simultaneously."""
    ticker:         str      = ""
    exchange:       str      = ""
    screens_passed: int      = 0
    screeners:      list     = field(default_factory=list)
    price:          float    = 0.0


@dataclass
class ScreenerRunCompleted(DomainEvent):
    """Fired when a full screener run finishes."""
    screener_name:  str = ""
    universe_size:  int = 0
    signals_found:  int = 0
    duration_sec:   float = 0.0


# ── IPO Events ────────────────────────────────────────────────────────────────

@dataclass
class NewListingDiscovered(DomainEvent):
    """Fired when a new NSE/BSE listing is detected via bhavcopy diff."""
    ticker:       str = ""
    listing_date: str = ""
    trading_bars: int = 0


@dataclass
class IPOScreenerGateReached(DomainEvent):
    """Fired when an IPO stock reaches enough bars for a new screener."""
    ticker:      str = ""
    screener:    str = ""
    bars:        int = 0
    gate_bars:   int = 0


# ── Intraday Events ───────────────────────────────────────────────────────────

@dataclass
class IntradayPatternDetected(DomainEvent):
    """Fired when an intraday pattern triggers (ORB, VWAP, etc.)."""
    ticker:      str   = ""
    pattern:     str   = ""
    signal:      str   = ""
    price:       float = 0.0
    confluence:  int   = 0
    interval_m:  int   = 15


@dataclass
class MarketOpenDetected(DomainEvent):
    """Fired at 09:15 IST when NSE opens."""
    session_date: str = ""


@dataclass
class MarketCloseDetected(DomainEvent):
    """Fired at 15:30 IST when NSE closes."""
    session_date: str = ""
    total_scans:  int = 0


# ── Backtest Events ───────────────────────────────────────────────────────────

@dataclass
class BacktestCompleted(DomainEvent):
    """Fired when a backtest run finishes."""
    run_id:        str   = ""
    period:        str   = ""   # "3y", "5y", "10y"
    n_signals:     int   = 0
    best_screener: str   = ""
    best_ev_pct:   float = 0.0


# ── Report Events ─────────────────────────────────────────────────────────────

@dataclass
class ReportGenerated(DomainEvent):
    """Fired when a report (Excel / email) is ready."""
    report_type: str = ""   # "Excel", "HTML_Email"
    path:        str = ""
    recipient:   str = ""


# ══════════════════════════════════════════════════════════════════════════════
# EVENT BUS — simple synchronous pub/sub
# ══════════════════════════════════════════════════════════════════════════════

class DomainEventBus:
    """
    In-process synchronous event bus.
    For v3.1: replace publish() with async queue for microservices.

    Usage:
        bus = DomainEventBus()
        bus.subscribe(BreakoutDetected, lambda e: print(e.ticker))
        bus.publish(BreakoutDetected(ticker="RELIANCE", price=1318.10))
    """

    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: Type[DomainEvent],
                  handler: Callable[[DomainEvent], None]) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(type(event), []):
            try:
                handler(event)
            except Exception as e:
                print(f"  [EventBus] Handler error for {event.event_name}: {e}")

    def publish_all(self, events: List[DomainEvent]) -> None:
        for event in events:
            self.publish(event)


# Singleton bus — wired up in Application layer
_bus: DomainEventBus = DomainEventBus()

def get_event_bus() -> DomainEventBus:
    return _bus
