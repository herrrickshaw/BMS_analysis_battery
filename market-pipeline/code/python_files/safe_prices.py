#!/usr/bin/env python3
"""
safe_prices.py — primitives that make this repo's recurring bugs unrepresentable.

WHY TYPES AND NOT MORE CHECKS
-----------------------------
Six distinct bugs on 2026-07-21 shared one shape: a non-local invariant a human
had to remember, silently violated, producing a plausible wrong number that
review did not catch.

    .fillna(0) on closes        "a missing price is not a price of zero"
                                -> 2,472 of 2,480 Korea signals wrong, 5 markets
    Rs turnover vs $ floor      "compare like currencies"
                                -> India's floor check passed on an ~87x unit error
    max(mtime) for freshness    "a set is as fresh as its WORST member"
                                -> gate passed on 57%-stale data
    as_of before entry date     "a price predating entry cannot measure a return"
                                -> +26.2% printed on a zero-day holding

None raised. Each returned a number. The fixes so far have mostly been GUARDS —
assertions that fail loudly — which is better than silence but still catches the
mistake after someone writes it. Following the Safe Coding argument (Google,
CACM 2025): stop asking developers to maintain the invariant, and make the
unsafe state impossible to construct.

    Money       comparing INR to USD raises TypeError, at the comparison site
    Bar         cannot be constructed from NaN, so "price zero" never exists
    PriceSeries .last() returns a Bar carrying its DATE, so a price can never
                travel without the date it belongs to

HONEST LIMIT — this is opt-in.
Google's result depended on the unsafe operation being UNAVAILABLE in
application code. In Python the unsafe path (raw float, bare pd.Series) is
always one keystroke away, so these primitives only help where they are used.
That makes them worth adopting at the boundaries that have actually burned us —
liquidity gating, box computation, P&L — not everywhere at once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

import pandas as pd


class UnsafePrice(ValueError):
    """A price-like value that cannot be trusted as a price."""


# ── Money ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, order=False)
class Money:
    """An amount that knows its currency.

    Ordering across currencies raises. That is the entire point: on 2026-07-21
    consistency_audit compared India's Median_Turnover (RUPEES) against a USD
    floor constant and the check PASSED, because rupee turnover is ~87x the USD
    figure and cleared the bar for every row. A unit error that passes is worse
    than one that fails.
    """
    amount: float
    currency: str

    def __post_init__(self):
        if self.amount is None or (isinstance(self.amount, float) and math.isnan(self.amount)):
            raise UnsafePrice("Money cannot be NaN — a missing amount is not zero")
        if not self.currency or len(self.currency) != 3:
            raise UnsafePrice(f"currency must be a 3-letter code, got {self.currency!r}")
        object.__setattr__(self, "currency", self.currency.upper())

    def _check(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError(f"cannot compare Money to {type(other).__name__} — "
                            "a bare number has no currency")
        if self.currency != other.currency:
            raise TypeError(
                f"cannot compare {self.currency} to {other.currency}. "
                "Convert explicitly: this is the Rs-turnover-vs-USD-floor bug.")

    def __lt__(self, other): self._check(other); return self.amount < other.amount
    def __le__(self, other): self._check(other); return self.amount <= other.amount
    def __gt__(self, other): self._check(other); return self.amount > other.amount
    def __ge__(self, other): self._check(other); return self.amount >= other.amount
    def __eq__(self, other):
        return (isinstance(other, Money) and self.currency == other.currency
                and self.amount == other.amount)
    def __hash__(self): return hash((self.amount, self.currency))

    def to(self, currency: str, rate: float) -> "Money":
        """Explicit conversion. `rate` is units of `currency` per 1 of self."""
        if rate is None or rate != rate or rate <= 0:
            raise UnsafePrice(f"bad FX rate {rate!r} for {self.currency}->{currency}")
        return Money(self.amount * rate, currency)

    def __repr__(self): return f"{self.currency} {self.amount:,.2f}"


# ── Bar ───────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Bar:
    """One settled price observation, inseparable from its date.

    A Bar cannot hold NaN. `.fillna(0)` on a close produced current=0, and zero
    is below every Darvas box bottom, so the entire universe reported
    BREAKDOWN_SELL — with a real LTP printed alongside, because LTP was computed
    separately with .dropna(). Making zero-from-missing unconstructible removes
    that failure at the source.
    """
    when: date
    close: float

    def __post_init__(self):
        c = self.close
        if c is None or (isinstance(c, float) and math.isnan(c)):
            raise UnsafePrice("Bar.close cannot be NaN — use PriceSeries.last(), "
                              "which returns None when there is no settled bar")
        if c <= 0:
            raise UnsafePrice(f"Bar.close must be positive, got {c!r} — "
                              "zero is the signature of a zero-filled NaN")
        # ALWAYS normalise. `isinstance(x, date)` is True for pd.Timestamp —
        # Timestamp subclasses datetime subclasses date — so a guard of
        # "convert only if not already a date" never fires, and the Timestamp
        # survives to blow up later on `date - Timestamp`. A type check that is
        # vacuously true is worse than none: it reads as handled.
        object.__setattr__(self, "when", pd.Timestamp(self.when).date())

    def age_days(self, asof: Optional[date] = None) -> int:
        return ((asof or date.today()) - self.when).days

    def __repr__(self): return f"Bar({self.when} {self.close:,.2f})"


# ── PriceSeries ───────────────────────────────────────────────────────────────
class PriceSeries:
    """A close series whose last value cannot be taken without its date.

    `.last()` returns Optional[Bar]: None when nothing has settled, never a
    silent NaN and never a stale value dressed as current. Trailing empty bars
    are dropped on construction — vendors append a row for the current session
    before it prints, and that row is what became `current = 0`.
    """

    def __init__(self, s: pd.Series, symbol: str = "", currency: str = ""):
        s = pd.to_numeric(s, errors="coerce")
        if not isinstance(s.index, pd.DatetimeIndex):
            raise UnsafePrice("PriceSeries needs a DatetimeIndex — a price "
                              "without dates cannot be checked for staleness")
        self._s = s.dropna()
        self.symbol, self.currency = symbol, currency.upper()

    def __len__(self) -> int: return len(self._s)

    def last(self) -> Optional[Bar]:
        if self._s.empty:
            return None
        return Bar(self._s.index[-1], float(self._s.iloc[-1]))

    def asof(self, when) -> Optional[Bar]:
        """Last settled bar at or before `when` — never a look-ahead."""
        w = pd.Timestamp(when)
        prior = self._s[self._s.index <= w]
        if prior.empty:
            return None
        return Bar(prior.index[-1], float(prior.iloc[-1]))

    def pct_between(self, start, end=None) -> Optional[float]:
        """Return between two settled bars, or None.

        Refuses when the end bar predates the start — that ordering produced a
        +26.2% "gain" on a position held zero days, by differencing a scan price
        against a bhavcopy bar from the previous day.
        """
        a = self.asof(start)
        b = self.last() if end is None else self.asof(end)
        if a is None or b is None or b.when < a.when:
            return None
        return (b.close / a.close - 1) * 100

    def money_last(self) -> Optional[Money]:
        b = self.last()
        if b is None:
            return None
        if not self.currency:
            raise UnsafePrice(f"{self.symbol}: no currency set — refusing to "
                              "produce Money that could be compared cross-market")
        return Money(b.close, self.currency)


def median_age_days(bars: Iterable[Optional[Bar]], asof: Optional[date] = None) -> Optional[float]:
    """Staleness of a COLLECTION by its median member, never its newest.

    max(mtime) said a directory was fresh when one file in it was seconds old and
    the other 7,000 were four days stale. The median moves only when the bulk of
    the set moves, which is the question actually being asked.
    """
    ages = [b.age_days(asof) for b in bars if b is not None]
    return float(pd.Series(ages).median()) if ages else None
