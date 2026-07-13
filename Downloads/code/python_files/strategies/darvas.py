#!/usr/bin/env python3
# Darvas Box — Nicolas Darvas ("How I Made $2,000,000 in the Stock Market", 1960).
# A stock consolidates in a "box" (confirmed resistance = box top, confirmed
# support = box bottom) for several bars; buy on a breakout above the box top,
# sell on a breakdown below the box bottom. This is the SAME box-detection
# algorithm used by full_us_market_scan.py / full_indian_market_scan.py /
# full_european_market_scan.py / darvas_breakouts.py — kept in sync here so
# every "Darvas" screen in this codebase means the same thing.
from __future__ import annotations
from .base import StockData, Result

META = {"name": "Darvas Box", "slug": "darvas", "category": "technical",
        "description": "Nicolas Darvas box breakout: price breaks above a confirmed "
                       "consolidation range (box top) after several bars of support.",
        "needs": "price"}

CONFIRM = 3   # bars either side of a candidate box edge that must not exceed it


def _compute_box(df) -> dict:
    """Box top/bottom detection, current bar excluded from box formation (no
    lookahead) — identical logic to compute_darvas_box() in the market-scan
    scripts, adapted to whatever OHLC column names the frame carries."""
    if df is None or len(df) < CONFIRM + 5:
        return {"signal": "INSUFFICIENT_DATA", "box_top": None, "box_bottom": None}

    def col(name):
        for c in df.columns:
            if name.upper() in str(c).upper():
                return c
        return None

    h_col, l_col, c_col = col("High"), col("Low"), col("Close")
    if not all([h_col, l_col, c_col]):
        return {"signal": "INSUFFICIENT_DATA", "box_top": None, "box_bottom": None}

    all_highs = df[h_col].astype(float).fillna(0).tolist()
    all_lows = df[l_col].astype(float).fillna(0).tolist()
    all_closes = df[c_col].astype(float).fillna(0).tolist()

    current = all_closes[-1]
    highs = all_highs[:-1]
    lows = all_lows[:-1]
    n = len(highs)

    box_top_idx = box_top = None
    for i in range(n - CONFIRM - 1, -1, -1):
        candidate = highs[i]
        if candidate == 0:
            continue
        window = highs[i + 1: i + 1 + CONFIRM]
        if len(window) == CONFIRM and all(h < candidate for h in window):
            box_top_idx, box_top = i, candidate
            break
    if box_top is None:
        return {"signal": "NO_BOX", "box_top": None, "box_bottom": None,
                "current_price": round(current, 2)}

    segment = lows[box_top_idx:]
    box_bottom = None
    for i in range(len(segment) - CONFIRM):
        candidate = segment[i]
        if candidate == 0:
            continue
        window = segment[i + 1: i + 1 + CONFIRM]
        if len(window) == CONFIRM and all(l > candidate for l in window):
            box_bottom = candidate
            break
    if box_bottom is None:
        valid = [l for l in segment if l > 0]
        box_bottom = min(valid) if valid else None
    if box_bottom is None:
        return {"signal": "NO_BOX", "box_top": round(box_top, 2), "box_bottom": None,
                "current_price": round(current, 2)}

    signal = ("BREAKOUT_BUY" if current > box_top else
              "BREAKDOWN_SELL" if current < box_bottom else "IN_BOX")
    box_range = box_top - box_bottom
    return {
        "signal": signal,
        "box_top": round(box_top, 2),
        "box_bottom": round(box_bottom, 2),
        "current_price": round(current, 2),
        "upside_to_top_pct": round((box_top - current) / current * 100, 2) if current else 0,
        "position_in_box_pct": round((current - box_bottom) / box_range * 100, 1) if box_range else 0,
    }


def screen(s: StockData) -> Result | None:
    df = s.ohlcv
    if df is None or len(df) < CONFIRM + 5:
        return None
    box = _compute_box(df)
    if box["signal"] in ("INSUFFICIENT_DATA", "NO_BOX"):
        return None
    passed = box["signal"] == "BREAKOUT_BUY"
    return Result(s.symbol, META["slug"], passed=passed,
                  score=box.get("position_in_box_pct"),   # further above the box ranks higher
                  metrics={"LTP": box["current_price"], "Box_Top": box["box_top"],
                           "Box_Bottom": box["box_bottom"],
                           "Position_in_Box%": box.get("position_in_box_pct"),
                           "Upside_to_Top%": box.get("upside_to_top_pct")},
                  note=box["signal"])
