"""
Surge pricing API router.

Three endpoints — one per transport mode — each accepting a POST body
and returning the computed price with a full factor breakdown.

  POST /api/pricing/flight    → flight ticket quote
  POST /api/pricing/uber      → ride-share quote
  POST /api/pricing/railway   → railway ticket quote
  GET  /api/pricing/reference → human-readable factor reference
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from pricing.flight  import price_flight,   _CLASS_MULTIPLIER   as _FLIGHT_CLASSES
from pricing.uber    import price_uber,     _VEHICLE_RATES,     _WEATHER_FACTOR
from pricing.railway import price_railway,  _CLASS_MULTIPLIER   as _RAIL_CLASSES, \
                                            _TRAIN_TYPE_FACTOR, _DAYS_BREAKPOINTS  # noqa: F401

router = APIRouter(prefix="/api/pricing", tags=["surge_pricing"])


# ── Request models ─────────────────────────────────────────────────────────────

class FlightQuoteRequest(BaseModel):
    origin:          str
    destination:     str
    departure_dt:    datetime
    seat_class:      str   = "economy"   # economy | premium_economy | business | first
    seats_available: int   = Field(ge=0, default=50)
    seats_total:     int   = Field(ge=1, default=180)
    base_fare:       float = Field(ge=0, default=200.0)
    currency:        str   = "USD"


class UberQuoteRequest(BaseModel):
    distance_km:       float  = Field(ge=0,    default=10.0)
    duration_min:      float  = Field(ge=0,    default=25.0)
    vehicle_type:      str    = "economy"
    available_drivers: int    = Field(ge=0,    default=10)
    active_requests:   int    = Field(ge=0,    default=12)
    timestamp:         Optional[datetime] = None   # defaults to now()
    weather:           str    = "clear"
    is_special_event:  bool   = False
    base_fare_override:float  = Field(ge=0,    default=0.0)
    currency:          str    = "INR"


class RailwayQuoteRequest(BaseModel):
    base_fare_per_km: float  = Field(ge=0,    default=0.50)
    distance_km:      float  = Field(ge=1,    default=500.0)
    journey_dt:       datetime
    coach_class:      str    = "SL"   # 2S|SL|CC|3E|3A|2A|1A|EC
    seats_available:  int    = Field(ge=0,    default=30)
    waiting_list:     int    = Field(ge=0,    default=0)
    total_quota:      int    = Field(ge=1,    default=72)
    train_type:       str    = "express"
    currency:         str    = "INR"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/flight")
def quote_flight(req: FlightQuoteRequest):
    """Return a surge-priced flight quote."""
    result = price_flight(
        base_fare       = req.base_fare,
        departure_dt    = req.departure_dt,
        seat_class      = req.seat_class,
        seats_available = req.seats_available,
        seats_total     = req.seats_total,
        currency        = req.currency,
    )
    return {
        "transport":    "flight",
        "route":        f"{req.origin.upper()} → {req.destination.upper()}",
        "seat_class":   req.seat_class,
        **result.__dict__,
    }


@router.post("/uber")
def quote_uber(req: UberQuoteRequest):
    """Return a surge-priced ride-share quote."""
    ts     = req.timestamp or datetime.now()
    result = price_uber(
        distance_km       = req.distance_km,
        duration_min      = req.duration_min,
        vehicle_type      = req.vehicle_type,
        available_drivers = req.available_drivers,
        active_requests   = req.active_requests,
        timestamp         = ts,
        weather           = req.weather,
        is_event          = req.is_special_event,
        base_fare_override= req.base_fare_override,
        currency          = req.currency,
    )
    return {
        "transport": "uber",
        **result.__dict__,
    }


@router.post("/railway")
def quote_railway(req: RailwayQuoteRequest):
    """Return a surge-priced railway ticket quote."""
    result = price_railway(
        base_fare_per_km = req.base_fare_per_km,
        distance_km      = req.distance_km,
        journey_dt       = req.journey_dt,
        coach_class      = req.coach_class,
        seats_available  = req.seats_available,
        waiting_list     = req.waiting_list,
        total_quota      = req.total_quota,
        train_type       = req.train_type,
        currency         = req.currency,
    )
    return {
        "transport": "railway",
        **result.__dict__,
    }


@router.get("/reference")
def factor_reference():
    """
    Human-readable reference for every pricing factor and its possible values.
    Useful for building UI dropdowns and explanations.
    """
    return {
        "flight": {
            "seat_classes": list(_FLIGHT_CLASSES.keys()),
            "days_breakpoints": [
                {"days_ahead": f"{t}+", "multiplier": m}
                for t, m in [
                    (90, 1.00), (60, 1.10), (45, 1.22), (30, 1.40),
                    (21, 1.65), (14, 2.00), (7,  2.60), (3,  3.20),
                    (1,  4.00), (0,  5.00),
                ]
            ],
            "peak_months": "Jan, May, Jun, Oct, Nov, Dec",
        },
        "uber": {
            "vehicle_types": list(_VEHICLE_RATES.keys()),
            "weather_conditions": list(_WEATHER_FACTOR.keys()),
            "surge_cap": "6×",
            "rush_hour_peaks": {
                "morning":  "07:00–10:00 (1.6×)",
                "evening":  "16:00–21:00 (1.7×)",
            },
        },
        "railway": {
            "coach_classes": {k: f"{v}×" for k, v in _RAIL_CLASSES.items()},
            "train_types":   list(_TRAIN_TYPE_FACTOR.keys()),
            "tatkal_window": "≤3 days to journey (+30%)",
            "regret_limit":  "Waitlist > 50 → not bookable",
        },
    }
