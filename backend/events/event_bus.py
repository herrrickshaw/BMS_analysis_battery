"""
Async pub/sub event bus for market events.

Events flow: PortfolioMonitor → EventBus → NewsEnricher → SSE clients
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Deque

log = logging.getLogger(__name__)


@dataclass
class MarketEvent:
    type: str       # PRICE_UP | PRICE_DOWN | RSI_OVERBOUGHT | RSI_OVERSOLD | VOLUME_SURGE | HIGH_52W | LOW_52W | MANUAL
    ticker: str
    market: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    def __init__(self, max_history: int = 200):
        self._subscribers: dict[str, list[Callable]] = {}
        self._history: Deque[MarketEvent] = deque(maxlen=max_history)

    async def publish(self, event: MarketEvent) -> None:
        self._history.append(event)
        log.info('EventBus: %s %s/%s %s', event.type, event.market, event.ticker, event.data)
        callbacks = (
            list(self._subscribers.get(event.type, []))
            + list(self._subscribers.get('*', []))
        )
        for cb in callbacks:
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:
                log.exception('EventBus callback error for event type %s', event.type)

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe callback to a specific event type or '*' for all events."""
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        subs = self._subscribers.get(event_type, [])
        try:
            subs.remove(callback)
        except ValueError:
            pass

    @property
    def history(self) -> list[MarketEvent]:
        return list(self._history)


# Global singleton used by all modules
bus = EventBus()
