"""
Flight surge pricing engine — three operating modes:

  "legacy"     Lufthansa / American Airlines style: fare-bucket bid-price model,
               weights booking pace heavily, applies full O&D demand curve logic.
               Competitor anchor pulls price toward market rate.

  "lcc"        Ryanair style: "load-active / yield-passive" — fill the plane first,
               recover margin through ancillaries.  Prices fall when pace lags;
               does NOT weight class upgrades (single cabin).  Ancillary revenue
               is added on top.

  "continuous" Lufthansa PROS Request-Specific Pricing approximation: blends all
               factors with a booking-pace velocity signal; price adjusts smoothly
               rather than in step-function buckets.

Formula (all modes)
-------------------
  adjusted_base  = base_fare × class_multiplier   [legacy/continuous only]
  surge          = days_factor × fill_factor × pace_factor
                 × season_factor × dow_factor
  final_fare     = adjusted_base × surge × competitor_anchor_weight
                 + ancillary_estimate              [lcc mode]
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .demand import (
    booking_pace_factor,
    day_of_week_multiplier,
    days_ahead,
    fill_rate,
    season_multiplier,
    sigmoid_ramp,
)

# Class upgrade multipliers (economy = 1.0 baseline) — used by legacy + continuous.
_CLASS_MULTIPLIER: dict[str, float] = {
    "economy":         1.00,
    "premium_economy": 1.55,
    "business":        3.20,
    "first":           6.00,
}

# Days-to-departure step function (used by legacy + lcc modes).
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

# Ryanair LCC: fares FALL when load lags, not just stay flat.
_LCC_PACE_FACTOR: list[tuple[float, float]] = [
    (0.30, 0.55),   # severely under-pace → slash prices
    (0.50, 0.70),
    (0.70, 0.85),
    (0.90, 0.95),
    (1.10, 1.00),   # on-track
    (1.50, 1.20),
    (2.00, 1.45),
    (9.99, 1.80),   # well ahead of pace
]


def _days_factor(days: int) -> float:
    for threshold, mult in _DAYS_BREAKPOINTS:
        if days >= threshold:
            return mult
    return 5.00


def _lcc_pace(ratio: float) -> float:
    for threshold, mult in _LCC_PACE_FACTOR:
        if ratio <= threshold:
            return mult
    return 1.80


@dataclass
class FlightPriceResult:
    airline_model: str          # legacy | lcc | continuous
    base_fare: float            # base after class multiplier, pre-surge
    class_multiplier: float
    days_multiplier: float
    fill_multiplier: float
    booking_pace_factor: float  # velocity of sales vs. historical curve
    season_multiplier: float
    dow_multiplier: float
    competitor_anchor_factor: float  # 1.0 if no anchor; pulls toward market
    surge_multiplier: float
    final_fare: float
    ancillary_estimate: float   # LCC mode only: estimated add-on revenue per pax
    currency: str
    days_to_departure: int
    fill_rate_pct: float
    demand_level: str
    model_notes: list[str]      # explains which model-specific rules fired
    breakdown: dict


def price_flight(
    base_fare: float,
    departure_dt: datetime,
    seat_class: str,
    seats_available: int,
    seats_total: int,
    currency: str = "USD",
    airline_model: str = "legacy",
    # Booking pace: compare current bookings against historical expected at same point.
    current_bookings: int = 0,
    historical_expected: int = 0,
    # Competitor anchor: if provided, price is pulled toward this reference fare.
    competitor_fare: float = 0.0,
    competitor_weight: float = 0.25,   # how much to blend toward competitor
    # LCC ancillary estimate per passenger (bags + seat + boarding)
    ancillary_per_pax: float = 25.0,
) -> FlightPriceResult:
    days  = days_ahead(departure_dt)
    fill  = fill_rate(seats_available, seats_total)
    model = airline_model.lower()
    notes: list[str] = []

    # ── Class multiplier ──────────────────────────────────────────────────────
    if model == "lcc":
        class_mult = 1.0   # LCC: single cabin, no cabin class premium in base
        notes.append("LCC: single-cabin — class multiplier bypassed")
    else:
        class_mult = _CLASS_MULTIPLIER.get(seat_class.lower(), 1.0)

    adjusted_base = base_fare * class_mult

    # ── Days factor ───────────────────────────────────────────────────────────
    days_mult = _days_factor(days)

    # ── Fill / load factor ────────────────────────────────────────────────────
    fill_mult = 1.0 + sigmoid_ramp(fill) * 2.5

    # ── Booking pace factor ───────────────────────────────────────────────────
    if current_bookings > 0 and historical_expected > 0:
        pace_ratio = current_bookings / historical_expected
        if model == "lcc":
            pace_factor = _lcc_pace(pace_ratio)
            if pace_ratio < 0.70:
                notes.append(f"LCC load-active: pace {pace_ratio:.2f} < target → stimulation pricing")
            elif pace_ratio > 1.30:
                notes.append(f"LCC load-active: ahead of pace ({pace_ratio:.2f}) → yield recovery")
        else:
            pace_factor = booking_pace_factor(current_bookings, historical_expected, days)
            if pace_ratio > 1.5:
                notes.append(f"Booking pace {pace_ratio:.2f}× expected — accelerated demand signal")
    else:
        pace_factor = 1.0

    # ── Season + day-of-week ──────────────────────────────────────────────────
    season_mult = season_multiplier(departure_dt)
    dow_mult    = day_of_week_multiplier(departure_dt)

    # ── Competitor anchor (legacy + continuous) ───────────────────────────────
    if competitor_fare > 0 and model != "lcc":
        # Blend: final = (1 - w) × own_price + w × competitor
        # Expressed as a post-surge multiplier adjustment
        own_price_est  = adjusted_base * days_mult * (0.45 + 0.55 * fill_mult) * season_mult * dow_mult
        blended        = (1 - competitor_weight) * own_price_est + competitor_weight * competitor_fare
        anchor_factor  = blended / max(own_price_est, 0.01)
        notes.append(f"Competitor anchor {currency}{competitor_fare:.0f} → blend factor {anchor_factor:.3f}")
    else:
        anchor_factor = 1.0

    # ── Assemble surge multiplier ─────────────────────────────────────────────
    if model == "lcc":
        # Ryanair: booking pace is the primary lever; days still matter but fill
        # is secondary to pace (they have load targets per point in schedule).
        surge = days_mult * pace_factor * season_mult
        notes.append("LCC model: pace replaces fill-rate as primary lever")
    elif model == "continuous":
        # Continuous pricing: smooth blend, pace modulates fill.
        # Approximates Lufthansa PROS request-specific pricing.
        surge = days_mult * (0.40 + 0.60 * fill_mult) * pace_factor * season_mult * dow_mult * anchor_factor
        notes.append("Continuous: smooth price curve, pace modulates fill signal")
    else:
        # Legacy: step-function days + fill blend + pace signal + anchor.
        surge = days_mult * (0.45 + 0.55 * fill_mult) * pace_factor * season_mult * dow_mult * anchor_factor
        notes.append("Legacy: bid-price + fare-bucket logic approximated")

    final = adjusted_base * surge

    # LCC: add estimated ancillary revenue per seat
    ancillary = ancillary_per_pax if model == "lcc" else 0.0
    if ancillary > 0:
        notes.append(f"LCC: ancillary revenue +{currency}{ancillary:.0f}/pax (bags, seat, priority)")

    if surge >= 3.5:   demand_level = "critical"
    elif surge >= 2.0: demand_level = "high"
    elif surge >= 1.35:demand_level = "medium"
    else:              demand_level = "low"

    return FlightPriceResult(
        airline_model           = model,
        base_fare               = round(adjusted_base,  2),
        class_multiplier        = round(class_mult,     3),
        days_multiplier         = round(days_mult,      3),
        fill_multiplier         = round(fill_mult,      3),
        booking_pace_factor     = round(pace_factor,    3),
        season_multiplier       = round(season_mult,    3),
        dow_multiplier          = round(dow_mult,       3),
        competitor_anchor_factor= round(anchor_factor,  3),
        surge_multiplier        = round(surge,          3),
        final_fare              = round(final,          2),
        ancillary_estimate      = round(ancillary,      2),
        currency                = currency,
        days_to_departure       = days,
        fill_rate_pct           = round(fill * 100,     1),
        demand_level            = demand_level,
        model_notes             = notes,
        breakdown={
            "class_upgrade":        round(class_mult,    3),
            "days_to_departure":    round(days_mult,     3),
            "seat_fill_rate":       round(fill_mult,     3),
            "booking_pace":         round(pace_factor,   3),
            "season":               round(season_mult,   3),
            "day_of_week":          round(dow_mult,      3),
            "competitor_anchor":    round(anchor_factor, 3),
        },
    )
