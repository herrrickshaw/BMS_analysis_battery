"""Shared demand-modelling utilities used by all three transport pricers."""
from __future__ import annotations

import math
from datetime import datetime, timezone

# Month → base season multiplier (applies to all transport modes).
# 1.0 = off-peak, higher = more expensive.
_SEASON_MULTIPLIER: dict[int, float] = {
    1:  1.40,   # New Year + winter holidays
    2:  1.00,   # off-peak
    3:  1.15,   # spring break
    4:  1.12,   # spring travel
    5:  1.35,   # summer start
    6:  1.30,   # summer
    7:  1.20,   # mid-summer
    8:  1.15,   # late summer
    9:  1.00,   # off-peak
    10: 1.28,   # Diwali / fall festivals
    11: 1.22,   # festive season
    12: 1.50,   # Christmas / New Year rush
}


def days_ahead(departure: datetime) -> int:
    """Calendar days between now and departure date (floor to 0)."""
    tz = departure.tzinfo or timezone.utc
    now = datetime.now(tz=tz)
    delta = departure.date() - now.date()
    return max(0, delta.days)


def fill_rate(available: int, total: int) -> float:
    """Fraction of capacity already sold — 0.0 (empty) to 1.0 (full)."""
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - available / total))


def season_multiplier(dt: datetime) -> float:
    return _SEASON_MULTIPLIER.get(dt.month, 1.0)


def day_of_week_multiplier(dt: datetime) -> float:
    """Friday / Sunday departures cost more; mid-week is cheapest."""
    dow = dt.weekday()   # 0 = Monday, 6 = Sunday
    if dow == 4: return 1.25   # Friday
    if dow == 6: return 1.20   # Sunday
    if dow == 0: return 1.10   # Monday
    if dow == 3: return 1.10   # Thursday
    return 1.00


def booking_pace_factor(
    current_bookings: int,
    historical_expected: int,
    days: int,
) -> float:
    """
    Compares current booking velocity against the historical expected bookings
    at this same point in the advance-purchase window.

    This is the single most important factor real airlines (AA, Lufthansa) use
    that simple fill-rate models miss.  A flight booking 2× faster than usual
    should be priced up immediately; one booking at half the expected pace
    needs stimulation (lower prices or promotions).

    ratio < 0.5  → significantly under-pacing → discount factor (0.80)
    ratio ≈ 1.0  → on track → neutral (1.0)
    ratio = 2.0  → double the pace → surge (up to 2.2×)
    """
    if historical_expected <= 0:
        return 1.0
    ratio = current_bookings / historical_expected
    if ratio <= 0.30: return 0.75
    if ratio <= 0.55: return 0.85
    if ratio <= 0.80: return 0.95
    if ratio <= 1.10: return 1.00
    if ratio <= 1.40: return 1.15
    if ratio <= 1.80: return 1.35
    if ratio <= 2.50: return 1.65
    return min(2.20, 1.0 + ratio * 0.40)


def sigmoid_ramp(x: float, steepness: float = 5.0) -> float:
    """
    Smooth 0→1 ramp via sigmoid.

    Returns values close to 0 when x≈0 and close to 1 when x≈1,
    with the inflection point at x=0.5.  Used to make fill-rate pricing
    accelerate sharply only as seats get very scarce.
    """
    return 1.0 / (1.0 + math.exp(-steepness * (x - 0.5)))
