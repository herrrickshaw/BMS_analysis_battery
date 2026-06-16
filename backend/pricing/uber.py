"""
Ride-share (Uber / Ola) surge pricing engine.

Formula
-------
  raw_fare         = base + per_km × distance + per_min × duration
  surge_multiplier = demand_supply_factor × time_of_day_factor
                   × weather_factor × event_factor          (capped at 6×)
  final_fare       = raw_fare × surge_multiplier
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Default rates per vehicle type (USD-based; scale by currency at call site).
_VEHICLE_RATES: dict[str, dict[str, float]] = {
    "economy": {"base": 2.00, "per_km": 0.80, "per_min": 0.15},
    "premium": {"base": 4.00, "per_km": 1.40, "per_min": 0.25},
    "xl":      {"base": 5.00, "per_km": 1.80, "per_min": 0.30},
    "moto":    {"base": 1.00, "per_km": 0.50, "per_min": 0.08},
    "auto":    {"base": 1.50, "per_km": 0.65, "per_min": 0.10},
    "black":   {"base": 8.00, "per_km": 2.20, "per_min": 0.45},
}

# (hour-range, factor)  — checked in order, first match wins.
_TIME_OF_DAY: list[tuple[range, float]] = [
    (range(7,  10), 1.60),   # morning rush
    (range(16, 21), 1.70),   # evening rush (longest window)
    (range(21, 24), 1.35),   # night
    (range(0,   2), 1.30),   # midnight
    (range(5,   7), 1.15),   # early morning
    (range(2,   5), 1.00),   # dead of night (low demand)
    (range(10, 16), 1.10),   # midday
]

_WEATHER_FACTOR: dict[str, float] = {
    "clear":       1.00,
    "cloudy":      1.05,
    "rain":        1.40,
    "heavy_rain":  1.80,
    "storm":       2.50,
    "snow":        2.20,
    "fog":         1.30,
}

_SURGE_CAP = 6.0


def _time_factor(hour: int) -> float:
    for rng, factor in _TIME_OF_DAY:
        if hour in rng:
            return factor
    return 1.10   # fallback


def _demand_supply_factor(requests: int, drivers: int) -> float:
    """
    Ratio of active ride requests to available drivers.
    Below 0.8 = undersupply of demand → discount.
    Above 1.0 = more demand than supply → surge.
    """
    if drivers <= 0:
        return 4.0
    ratio = requests / drivers
    if ratio <= 0.30: return 0.80   # fleet idling
    if ratio <= 0.60: return 0.90
    if ratio <= 0.80: return 1.00
    if ratio <= 1.20: return 1.30
    if ratio <= 1.80: return 1.80
    if ratio <= 2.50: return 2.50
    if ratio <= 3.50: return 3.20
    return min(_SURGE_CAP, 1.0 + ratio * 1.10)


@dataclass
class UberPriceResult:
    vehicle_type: str
    distance_km: float
    duration_min: float
    base_component: float
    distance_component: float
    time_component: float
    raw_fare: float
    demand_supply_factor: float
    time_of_day_factor: float
    weather_factor: float
    event_factor: float
    surge_multiplier: float     # capped at 6×
    final_fare: float
    currency: str
    demand_level: str           # low / medium / high / critical
    eta_minutes: int            # rough estimated wait time
    breakdown: dict


def price_uber(
    distance_km: float,
    duration_min: float,
    vehicle_type: str,
    available_drivers: int,
    active_requests: int,
    timestamp: datetime,
    weather: str = "clear",
    is_event: bool = False,
    base_fare_override: float = 0.0,
    currency: str = "INR",
) -> UberPriceResult:
    vtype = vehicle_type.lower()
    rates = _VEHICLE_RATES.get(vtype, _VEHICLE_RATES["economy"])

    base_comp = rates["base"]
    dist_comp = distance_km * rates["per_km"]
    time_comp = duration_min * rates["per_min"]
    raw_fare  = base_fare_override if base_fare_override > 0 else (base_comp + dist_comp + time_comp)

    ds_factor      = _demand_supply_factor(active_requests, available_drivers)
    tod_factor     = _time_factor(timestamp.hour)
    weather_factor = _WEATHER_FACTOR.get(weather.lower(), 1.00)
    event_factor   = 1.35 if is_event else 1.00

    surge = min(_SURGE_CAP, ds_factor * tod_factor * weather_factor * event_factor)
    final = raw_fare * surge

    if surge >= 3.0:   demand_level = "critical"
    elif surge >= 2.0: demand_level = "high"
    elif surge >= 1.3: demand_level = "medium"
    else:              demand_level = "low"

    # Rough ETA: more demand relative to supply = longer wait.
    ratio = active_requests / max(available_drivers, 1)
    eta   = max(2, int(4 + ratio * 3.5))

    return UberPriceResult(
        vehicle_type        = vtype,
        distance_km         = distance_km,
        duration_min        = duration_min,
        base_component      = round(base_comp,      2),
        distance_component  = round(dist_comp,      2),
        time_component      = round(time_comp,      2),
        raw_fare            = round(raw_fare,        2),
        demand_supply_factor= round(ds_factor,       3),
        time_of_day_factor  = round(tod_factor,      3),
        weather_factor      = round(weather_factor,  3),
        event_factor        = round(event_factor,    3),
        surge_multiplier    = round(surge,           3),
        final_fare          = round(final,           2),
        currency            = currency,
        demand_level        = demand_level,
        eta_minutes         = eta,
        breakdown={
            "demand_supply": round(ds_factor,      3),
            "time_of_day":   round(tod_factor,     3),
            "weather":       round(weather_factor, 3),
            "special_event": round(event_factor,   3),
        },
    )
