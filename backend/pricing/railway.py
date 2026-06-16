"""
Railway ticket surge pricing engine (Indian Railways model + generalised).

Pricing layers
--------------
  base_fare      = base_fare_per_km × distance_km × class_multiplier × train_type_factor
  surge          = availability_factor × days_factor × season_factor
  tatkal_premium = +30% of base_fare when ≤ 3 days to journey
  final_fare     = base_fare × surge + tatkal_premium

Booking status is determined by the availability/waitlist position and
feeds directly into the availability_factor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .demand import days_ahead, season_multiplier

# Coach class → fare multiplier (SL = 1.0 baseline).
_CLASS_MULTIPLIER: dict[str, float] = {
    "2S": 0.65,   # Second Sitting (unreserved class)
    "SL": 1.00,   # Sleeper
    "CC": 1.75,   # AC Chair Car (day trains)
    "3E": 2.00,   # Third AC Economy (newer coaches)
    "3A": 2.80,   # Third AC
    "2A": 4.20,   # Second AC
    "1A": 7.00,   # First AC
    "EC": 3.50,   # Executive Chair Car (Shatabdi/Vande Bharat)
}

# Train category → base fare multiplier.
_TRAIN_TYPE_FACTOR: dict[str, float] = {
    "local":        0.60,
    "passenger":    0.70,
    "express":      1.00,
    "superfast":    1.20,
    "shatabdi":     1.40,
    "rajdhani":     1.60,
    "duronto":      1.55,
    "vande_bharat": 1.80,
    "tejas":        1.70,
    "premium":      2.00,
}

_TATKAL_WINDOW_DAYS = 3
_TATKAL_RATE        = 0.30   # +30% of base fare
_REGRET_WL_LIMIT    = 50     # WL beyond this → REGRET (no booking)


def _days_factor(days: int) -> float:
    """Price accelerates in the Tatkal window (≤3 days)."""
    if days >= 60: return 1.00
    if days >= 30: return 1.05
    if days >= 15: return 1.12
    if days >= 7:  return 1.25
    if days >= 4:  return 1.55   # Tatkal bookings open
    if days >= 2:  return 2.10   # Premium Tatkal
    if days >= 1:  return 2.50
    return 3.00                  # same-day (if applicable)


def _availability(
    seats_available: int,
    waiting_list: int,
    total_quota: int,
) -> tuple[float, str]:
    """Returns (availability_factor, booking_status_label).

    Waitlisted passengers above the REGRET threshold cannot board;
    factor = 0.0 signals this to the caller.
    """
    if waiting_list > _REGRET_WL_LIMIT:
        return 0.0, "REGRET"

    if waiting_list > 0:
        if waiting_list <= 10:
            return 1.90, f"WL{waiting_list}"
        if waiting_list <= 30:
            return 2.20, f"WL{waiting_list}"
        return 2.60, f"WL{waiting_list}"

    # Seats still open — price rises as quota fills up.
    fill = 1.0 - seats_available / max(total_quota, 1)
    if fill >= 0.95: return 2.80, "AVAILABLE (last few)"
    if fill >= 0.85: return 2.00, "AVAILABLE (<15%)"
    if fill >= 0.70: return 1.60, "AVAILABLE (<30%)"
    if fill >= 0.50: return 1.30, "AVAILABLE (<50%)"
    if fill >= 0.30: return 1.10, "AVAILABLE"
    return 1.00, "AVAILABLE (plenty)"


@dataclass
class RailwayPriceResult:
    base_fare: float            # base after class + train-type adjustments, pre-surge
    class_multiplier: float
    train_type_factor: float
    days_factor: float
    availability_factor: float
    season_factor: float
    surge_multiplier: float
    final_fare: float
    tatkal_premium: float       # flat addition when ≤3 days; 0 otherwise
    currency: str
    days_to_journey: int
    booking_status: str         # e.g. "AVAILABLE (plenty)" / "WL12" / "REGRET"
    demand_level: str           # low / medium / high / critical / n/a
    breakdown: dict


def price_railway(
    base_fare_per_km: float,
    distance_km: float,
    journey_dt: datetime,
    coach_class: str,
    seats_available: int,
    waiting_list: int,
    total_quota: int,
    train_type: str = "express",
    currency: str = "INR",
) -> RailwayPriceResult:
    days         = days_ahead(journey_dt)
    class_mult   = _CLASS_MULTIPLIER.get(coach_class.upper(), 1.0)
    train_factor = _TRAIN_TYPE_FACTOR.get(train_type.lower(), 1.0)
    d_factor     = _days_factor(days)
    season_mult  = season_multiplier(journey_dt)
    avail_factor, booking_status = _availability(seats_available, waiting_list, total_quota)

    base_fare    = base_fare_per_km * distance_km * class_mult * train_factor
    tatkal_prem  = base_fare * _TATKAL_RATE if days <= _TATKAL_WINDOW_DAYS else 0.0

    _NA = RailwayPriceResult(
        base_fare          = round(base_fare, 2),
        class_multiplier   = round(class_mult,   3),
        train_type_factor  = round(train_factor, 3),
        days_factor        = round(d_factor,     3),
        availability_factor= 0.0,
        season_factor      = round(season_mult,  3),
        surge_multiplier   = 0.0,
        final_fare         = 0.0,
        tatkal_premium     = 0.0,
        currency           = currency,
        days_to_journey    = days,
        booking_status     = "REGRET – Fully Waitlisted",
        demand_level       = "n/a",
        breakdown          = {},
    )

    if avail_factor == 0.0:
        return _NA

    surge = avail_factor * d_factor * season_mult
    final = base_fare * surge + tatkal_prem

    if surge >= 2.5:   demand_level = "critical"
    elif surge >= 1.7: demand_level = "high"
    elif surge >= 1.2: demand_level = "medium"
    else:              demand_level = "low"

    return RailwayPriceResult(
        base_fare          = round(base_fare,    2),
        class_multiplier   = round(class_mult,   3),
        train_type_factor  = round(train_factor, 3),
        days_factor        = round(d_factor,     3),
        availability_factor= round(avail_factor, 3),
        season_factor      = round(season_mult,  3),
        surge_multiplier   = round(surge,        3),
        final_fare         = round(final,        2),
        tatkal_premium     = round(tatkal_prem,  2),
        currency           = currency,
        days_to_journey    = days,
        booking_status     = booking_status,
        demand_level       = demand_level,
        breakdown={
            "availability":   round(avail_factor, 3),
            "days_to_journey":round(d_factor,     3),
            "season":         round(season_mult,  3),
            "tatkal_premium": round(tatkal_prem,  2),
        },
    )
