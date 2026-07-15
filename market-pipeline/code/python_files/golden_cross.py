#!/usr/bin/env python3
"""
golden_cross.py — one 50/200-DMA implementation for every market.

WHY
---
The golden crossover (50-DMA crossing above the 200-DMA) is a real strategy, but
it only existed in 2 of 5 markets, and unevenly:

    India   GC_Signal + DMA50_above_200 (bool)  — no DMA VALUES at all
    US      GC_Signal + DMA50 + DMA200 + Gap%   — complete
    Europe  200_Day_MA + Trend_Signal           — NO CROSS COMPUTED
    Japan   200_Day_MA + Trend_Signal           — NO CROSS COMPUTED
    Korea   200_Day_MA + Trend_Signal           — NO CROSS COMPUTED

Europe/Japan/Korea only ever labelled price-vs-200DMA ("Above 200MA (Uptrend)"),
which is a different, weaker signal: it says where price sits, not that the trend
structure just turned. So a strategy the brief presents as cross-market was
actually running on US + India only.

It was also impossible in Japan/Korea until today: both fetched a 3-MONTH window
(~62 bars) while a 200-DMA needs 200, so 200_Day_MA was 0/2,050 and 0/1,879
populated and Trend_Signal read "Insufficient History" for every row. With the 1y
window they now carry ~244 bars — enough for the cross, with ~44 bars of headroom.

CONTRACT
--------
Returns the union of both historical schemas so no caller loses a field:
    gc_signal        bool  — 50 crossed ABOVE 200 on the last bar (the event)
    dma50_above_200  bool  — 50 is above 200 (the state)
    dma50, dma200    float
    dma_gap_%        float — (50-200)/200, how far into the trend
    days_since_cross int   — bars since the last upward cross, None if none in window
    trend            str   — GOLDEN_CROSS / ABOVE_200DMA / BELOW_200DMA / INSUFFICIENT_HISTORY

`days_since_cross` is the addition: a cross is a one-day event, so `gc_signal`
alone finds almost nothing (US: 2 of 398 today). Knowing a cross happened 5 days
ago is what makes it tradeable.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

MIN_BARS = 201          # 200 for the MA + 1 to see the crossing


def compute(df: Optional[pd.DataFrame], lookback: int = 60) -> dict:
    """50/200-DMA state for one symbol. Never raises — returns a null result."""
    null = {"gc_signal": False, "dma50_above_200": False, "dma50": None,
            "dma200": None, "dma_gap_%": None, "days_since_cross": None,
            "trend": "INSUFFICIENT_HISTORY"}
    if df is None or not hasattr(df, "columns") or "Close" not in df.columns:
        return null
    closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(closes) < MIN_BARS:
        return null

    dma50 = closes.rolling(50).mean()
    dma200 = closes.rolling(200).mean()
    d50_t, d200_t = float(dma50.iloc[-1]), float(dma200.iloc[-1])
    d50_p, d200_p = float(dma50.iloc[-2]), float(dma200.iloc[-2])
    if not d200_t:
        return null

    above = dma50 > dma200
    crossed_today = bool((d50_p <= d200_p) and (d50_t > d200_t))

    # bars since the most recent upward cross, within `lookback`
    since = None
    win = above.dropna()
    if len(win) >= 2:
        w = win.iloc[-(lookback + 1):]
        for i in range(len(w) - 1, 0, -1):
            if bool(w.iloc[i]) and not bool(w.iloc[i - 1]):
                since = len(w) - 1 - i
                break

    return {
        "gc_signal": crossed_today,
        "dma50_above_200": bool(d50_t > d200_t),
        "dma50": round(d50_t, 2),
        "dma200": round(d200_t, 2),
        "dma_gap_%": round((d50_t - d200_t) / d200_t * 100, 2),
        "days_since_cross": since,
        "trend": ("GOLDEN_CROSS" if crossed_today
                  else "ABOVE_200DMA" if d50_t > d200_t else "BELOW_200DMA"),
    }


def row_fields(df: Optional[pd.DataFrame]) -> dict:
    """Scan-row fields, named consistently across every market."""
    g = compute(df)
    return {
        "DMA50": g["dma50"],
        "DMA200": g["dma200"],
        "DMA_Gap%": g["dma_gap_%"],
        "GC_Signal": g["trend"],
        "DMA50_above_200": g["dma50_above_200"],
        "Days_Since_Cross": g["days_since_cross"],
    }
