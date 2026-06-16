"""
Background asyncio task that polls yfinance for watched portfolio tickers
and publishes market events when significant changes are detected.

Events emitted:
  PRICE_UP      — intraday move ≥ +2% vs previous close
  PRICE_DOWN    — intraday move ≤ -2% vs previous close
  RSI_OVERBOUGHT — RSI just crossed above 70
  RSI_OVERSOLD   — RSI just crossed below 30
  VOLUME_SURGE   — current session volume ≥ 2× 20-day average
  HIGH_52W       — price within 2% of 52-week high
  LOW_52W        — price within 2% of 52-week low
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

_PRICE_THRESHOLD = 0.02       # 2 % intraday move
_VOLUME_MULTIPLIER = 2.0      # 2× avg daily volume
_52W_PROXIMITY = 0.02         # within 2 % of 52W extreme
_RSI_OVERBOUGHT = 70.0
_RSI_OVERSOLD = 30.0


@dataclass
class _TickerState:
    market: str
    prev_rsi: Optional[float] = None


class PortfolioMonitor:
    def __init__(self, poll_interval: int = 300):
        self._tickers: dict[str, _TickerState] = {}
        self._interval = poll_interval
        self._task: Optional[asyncio.Task] = None

    # ── public API ─────────────────────────────────────────────────────────────

    def add_tickers(self, tickers: list[str], market: str) -> None:
        for t in tickers:
            if t not in self._tickers:
                self._tickers[t] = _TickerState(market=market)
                log.info('Monitor: watching %s (%s)', t, market)

    def remove_ticker(self, ticker: str) -> None:
        self._tickers.pop(ticker, None)
        log.info('Monitor: removed %s', ticker)

    def watched(self) -> dict[str, str]:
        return {t: s.market for t, s in self._tickers.items()}

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())
        log.info('PortfolioMonitor started (poll every %ds)', self._interval)

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            log.info('PortfolioMonitor stopped')

    # ── internals ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while True:
            if self._tickers:
                await self._poll()
            await asyncio.sleep(self._interval)

    async def _poll(self) -> None:
        from events.event_bus import bus, MarketEvent
        for ticker, state in list(self._tickers.items()):
            try:
                data = await asyncio.to_thread(_fetch_ticker_data, ticker, state.market)
                if not data:
                    continue
                for ev_kwargs in _detect_events(ticker, state, data):
                    await bus.publish(MarketEvent(**ev_kwargs))
                state.prev_rsi = data.get('rsi')
            except Exception:
                log.exception('Monitor poll error for %s', ticker)


# ── helpers (run in thread executor) ──────────────────────────────────────────

def _yf_sym(ticker: str, market: str) -> str:
    if market == 'india':
        return ticker if ticker.endswith('.NS') else f'{ticker}.NS'
    return ticker


def _compute_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i + 1] - closes[i] for i in range(len(closes) - 1)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [abs(min(d, 0.0)) for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 2)


def _fetch_ticker_data(ticker: str, market: str) -> Optional[dict]:
    try:
        import yfinance as yf
        t = yf.Ticker(_yf_sym(ticker, market))
        hist = t.history(period='30d', auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return None
        closes = hist['Close'].tolist()
        volumes = hist['Volume'].tolist()
        current_price = closes[-1]
        prev_close = closes[-2]
        current_volume = volumes[-1]
        avg_volume = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
        rsi = _compute_rsi(closes)
        fi = t.fast_info
        high52 = getattr(fi, 'year_high', None)
        low52 = getattr(fi, 'year_low', None)
        return {
            'price': current_price,
            'prev_close': prev_close,
            'volume': current_volume,
            'avg_volume': avg_volume,
            'rsi': rsi,
            'high_52w': high52,
            'low_52w': low52,
        }
    except Exception as exc:
        log.warning('_fetch_ticker_data %s: %s', ticker, exc)
        return None


def _detect_events(ticker: str, state: _TickerState, data: dict) -> list[dict]:
    events: list[dict] = []
    market = state.market
    price = data.get('price')
    prev_close = data.get('prev_close')
    rsi = data.get('rsi')
    volume = data.get('volume', 0)
    avg_vol = data.get('avg_volume', 1)
    high52 = data.get('high_52w')
    low52 = data.get('low_52w')

    # Price move
    if price and prev_close and prev_close > 0:
        pct = (price - prev_close) / prev_close
        if pct >= _PRICE_THRESHOLD:
            events.append({'type': 'PRICE_UP', 'ticker': ticker, 'market': market,
                           'data': {'price': round(price, 2), 'prev_close': round(prev_close, 2),
                                    'pct_change': round(pct * 100, 2)}})
        elif pct <= -_PRICE_THRESHOLD:
            events.append({'type': 'PRICE_DOWN', 'ticker': ticker, 'market': market,
                           'data': {'price': round(price, 2), 'prev_close': round(prev_close, 2),
                                    'pct_change': round(pct * 100, 2)}})

    # RSI crossings (only fire on transition, not every poll)
    if rsi is not None:
        prev_rsi = state.prev_rsi
        if rsi >= _RSI_OVERBOUGHT and (prev_rsi is None or prev_rsi < _RSI_OVERBOUGHT):
            events.append({'type': 'RSI_OVERBOUGHT', 'ticker': ticker, 'market': market,
                           'data': {'rsi': rsi, 'price': round(price, 2) if price else None}})
        elif rsi <= _RSI_OVERSOLD and (prev_rsi is None or prev_rsi > _RSI_OVERSOLD):
            events.append({'type': 'RSI_OVERSOLD', 'ticker': ticker, 'market': market,
                           'data': {'rsi': rsi, 'price': round(price, 2) if price else None}})

    # Volume surge
    if avg_vol and avg_vol > 0 and volume >= avg_vol * _VOLUME_MULTIPLIER:
        events.append({'type': 'VOLUME_SURGE', 'ticker': ticker, 'market': market,
                       'data': {'volume': int(volume), 'avg_volume': int(avg_vol),
                                'multiplier': round(volume / avg_vol, 1)}})

    # 52-week extremes
    if price and high52 and price >= high52 * (1 - _52W_PROXIMITY):
        events.append({'type': 'HIGH_52W', 'ticker': ticker, 'market': market,
                       'data': {'price': round(price, 2), 'high_52w': round(high52, 2)}})
    elif price and low52 and price <= low52 * (1 + _52W_PROXIMITY):
        events.append({'type': 'LOW_52W', 'ticker': ticker, 'market': market,
                       'data': {'price': round(price, 2), 'low_52w': round(low52, 2)}})

    return events


# Global singleton
monitor = PortfolioMonitor()
