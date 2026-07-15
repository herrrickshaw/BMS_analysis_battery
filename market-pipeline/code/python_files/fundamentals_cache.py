#!/usr/bin/env python3
"""
fundamentals_cache.py — reuse quarterly fundamentals instead of refetching nightly.

WHY
---
Fundamentals (Piotroski, Coffee Can, Magic Formula, sector) come from quarterly
filings. They do not change day to day. Refetching them every night costs one
yf.Ticker(...).info call PER STOCK — which is the single most expensive thing this
pipeline does and the reason it trips Yahoo's rate limiter (surfacing as
"Invalid Crumb"/YFRateLimitError, which then breaks *other* markets' FX and their
liquidity gates).

Measured 2026-07-15: the US Stage 4 ran .info across ~5,700 stocks nightly —
62m54s, 2.3x the next-slowest step. Reusing the previous workbook took it to 4s.
India documented this rationale years ago ("fundamentals are quarterly and do not
change day-to-day, so they are reused from the most recent existing full-scan
workbook") — but only India and, since today, the US actually did it. Europe,
Japan and Korea still refetched everything, every night.

SHEET NAMING IS INCONSISTENT and silently breaks reuse:
    full_indian_market_scan.py -> "All_Fundamentals"
    scan_bhavcopy.py           -> reads "Fundamentals"   (never matches!)
    full_us_market_scan.py     -> "All_Fundamentals"
    Europe / Japan / Korea     -> "Fundamentals"
India's reuse was therefore structurally impossible: its seeder writes one name and
its consumer reads the other. This helper accepts either, so a rename cannot
silently disable reuse again.

Usage:
    import fundamentals_cache as fc
    cached, src = fc.load("japan_scan/japan_market_scan_*.xlsx", key="Code")
    need = [s for s in symbols if s not in cached]
"""
from __future__ import annotations

import glob
import os
import time
from typing import Dict, Optional, Tuple

import pandas as pd

# Quarterly data: a week-old score is the same score. Beyond that, refresh.
REUSE_DAYS = 7
SHEET_NAMES = ("All_Fundamentals", "Fundamentals")


def load(pattern: str, key: str = "Symbol", reuse_days: int = REUSE_DAYS,
         verbose: bool = True) -> Tuple[Dict[str, dict], Optional[str]]:
    """({symbol: fundamentals_row}, source_filename) from the newest usable workbook.

    Returns ({}, None) when nothing is reusable — caller then does a full fetch.
    Walks backwards through recent workbooks: the newest file may be from a run
    that produced no fundamentals (e.g. a momentum-only pass), and stopping at the
    first miss would discard perfectly good data one file back.
    """
    files = sorted(glob.glob(pattern))
    if not files:
        return {}, None

    for f in reversed(files[-6:]):
        age_d = (time.time() - os.path.getmtime(f)) / 86400
        if age_d > reuse_days:
            if verbose:
                print(f"  fundamentals: newest cache {age_d:.1f}d old "
                      f"(> {reuse_days}d) — full refresh")
            return {}, None
        try:
            sheets = pd.ExcelFile(f).sheet_names
        except Exception:
            continue
        name = next((s for s in SHEET_NAMES if s in sheets), None)
        if not name:
            continue                       # this run produced none; try older
        try:
            fd = pd.read_excel(f, sheet_name=name)
        except Exception:
            continue
        if fd.empty or key not in fd.columns:
            continue
        out = {}
        for _, r in fd.iterrows():
            k = str(r.get(key, "")).strip()
            if k and k.lower() != "nan":
                out[k] = r.to_dict()
        if out:
            if verbose:
                print(f"  fundamentals: reusing {len(out):,} rows from "
                      f"{os.path.basename(f)}:{name} ({age_d:.1f}d old)")
            return out, f"{os.path.basename(f)}:{name}"
    if verbose:
        print("  fundamentals: no usable cache — full refresh")
    return {}, None


def merge(cached: dict, symbols: list, price_map: dict, price_fields: tuple) -> list:
    """Rows for symbols served from cache, with price fields refreshed from today.

    The caller's fetch loop only runs the symbols NOT in cache, so without this the
    reused ones vanish from the output entirely — trading a slow scan for a
    truncated one. Only the quarterly fields come from cache; anything
    price-derived is overwritten with today's values.
    """
    rows = []
    for s in symbols:
        cr = cached.get(s)
        if cr is None:
            continue
        today = price_map.get(s)
        if today is None:
            continue                       # not in today's gated universe
        row = dict(cr)
        for fld in price_fields:
            if fld in today:
                row[fld] = today[fld]
        rows.append(row)
    return rows
