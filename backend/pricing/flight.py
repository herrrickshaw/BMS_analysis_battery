"""
Flight surge pricing engine.

Formula
-------
  adjusted_base  = base_fare × class_multiplier
  surge          = days_factor × fill_factor × season_factor × day_of_week_factor
  final_fare     = adjusted_base × surge

All four components compound — a last-minute Friday flight in December on a
nearly-full business cabin gets hit by every factor simultaneously.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from .demand import (
    day_of_week_multiplier,
    days_ahead,
    fill_rate,
    season_multiplier,
    sigmoid_ramp,
)

# Class upgrade multipliers (economy = 1.0 baseline).
_CLASS_MULTIPLIER: dict[str, float] = {
    "economy":         1.00,
    "premium_economy": 1.55,
    "business":        3.20,
    "first":           6.00,
}

# (minimum days ahead, multiplier to apply when days >= threshold)
# Scanned top-to-bottom; first match wins.
_DAYS_BREAKPOINTS: list[tuple[int, float]] = [
    (90, 1.00),
    (60, 1.10),
    (45, 1.22),
    (30, 1.40),
    (21, 1.65),
    (14, 2.00),
    (7,  2.60),
    (3,  3.20),
    (1,  4.00),
    (0,  5.00),
]


def _days_factor(days: int) -> float:
    for threshold, mult in _DAYS_BREAKPOINTS:
        if days >= threshold:
            return mult
    return 5.00


@dataclass
class FlightPriceResult:
    base_fare: float            # base_fare × class_multiplier (pre-surge)
    class_multiplier: float
    days_multiplier: float
    fill_multiplier: float
    season_multiplier: float
    dow_multiplier: float
    surge_multiplier: float     # combined days × fill × season × dow
    final_fare: float
    currency: str
    days_to_departure: int
    fill_rate_pct: float        # % of seats already sold
    demand_level: str           # low / medium / high / critical
    breakdown: dict             # per-factor floats for the UI


def price_flight(
    base_fare: float,
    departure_dt: datetime,
    seat_class: str,
    seats_available: int,
    seats_total: int,
    currency: str = "USD",
) -> FlightPriceResult:
    days = days_ahead(departure_dt)
    fill = fill_rate(seats_available, seats_total)

    class_mult  = _CLASS_MULTIPLIER.get(seat_class.lower(), 1.0)
    days_mult   = _days_factor(days)
    # Fill multiplier: 1.0 when empty, up to ~3.5 when nearly full.
    fill_mult   = 1.0 + sigmoid_ramp(fill) * 2.5
    season_mult = season_multiplier(departure_dt)
    dow_mult    = day_of_week_multiplier(departure_dt)

    # Blend days and fill so neither dominates alone.
    surge = days_mult * (0.45 + 0.55 * fill_mult) * season_mult * dow_mult

    adjusted_base = base_fare * class_mult
    final         = adjusted_base * surge

    if surge >= 3.5:
        demand_level = "critical"
    elif surge >= 2.0:
        demand_level = "high"
    elif surge >= 1.35:
        demand_level = "medium"
    else:
        demand_level = "low"

    return FlightPriceResult(
        base_fare        = round(adjusted_base, 2),
        class_multiplier = round(class_mult,    3),
        days_multiplier  = round(days_mult,     3),
        fill_multiplier  = round(fill_mult,     3),
        season_multiplier= round(season_mult,   3),
        dow_multiplier   = round(dow_mult,      3),
        surge_multiplier = round(surge,         3),
        final_fare       = round(final,         2),
        currency         = currency,
        days_to_departure= days,
        fill_rate_pct    = round(fill * 100,    1),
        demand_level     = demand_level,
        breakdown={
            "class_upgrade":    round(class_mult,    3),
            "days_to_departure":round(days_mult,     3),
            "seat_fill_rate":   round(fill_mult,     3),
            "season":           round(season_mult,   3),
            "day_of_week":      round(dow_mult,      3),
        },
    )
