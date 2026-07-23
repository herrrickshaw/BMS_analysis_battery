#!/usr/bin/env python3
"""
build_regimes.py — daily volatility-regime reference table for conditioning
signal calibration and backtests (CIO-review gap: "no regime conditioning
anywhere — split results by vol/rate regime, VIX / India-VIX terciles").

Sources (yfinance): ^VIX (global/US vol — used for US/EU/JP/KR/CN) and
^INDIAVIX (India vol — used for IN).

Regime label is POINT-IN-TIME SAFE: each day's VIX level is bucketed into
terciles of its own TRAILING 756-trading-day (~3y) window — no full-sample
lookahead. First 252 days of each series have no label (window too short).

    LOW  = bottom tercile of trailing window
    MID  = middle tercile
    HIGH = top tercile

OUTPUT: warehouse/regimes.parquet  (date, vix, vix_regime, indiavix,
        indiavix_regime) — one row per calendar day both indices are known,
        forward-filled over non-trading days so any signal_date joins.

    build_regimes.py            # build/refresh the table
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

WH = Path("/Users/umashankar/repos/global-market-data/warehouse")
OUT = WH / "regimes.parquet"
WINDOW = 756
MIN_WINDOW = 252


def _fetch(ticker: str) -> pd.Series:
    s = yf.Ticker(ticker).history(start="2015-01-01", auto_adjust=False)["Close"]
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.rename(ticker)


def _pit_tercile(s: pd.Series) -> pd.Series:
    """Trailing-window tercile label per day, no lookahead."""
    vals = s.values
    out = np.full(len(s), None, dtype=object)
    for i in range(len(s)):
        lo = max(0, i - WINDOW)
        win = vals[lo:i]  # strictly BEFORE today
        if len(win) < MIN_WINDOW:
            continue
        t1, t2 = np.quantile(win, [1 / 3, 2 / 3])
        out[i] = "LOW" if vals[i] <= t1 else ("MID" if vals[i] <= t2 else "HIGH")
    return pd.Series(out, index=s.index)


def main() -> int:
    vix = _fetch("^VIX")
    ivix = _fetch("^INDIAVIX")
    df = pd.concat(
        [
            vix.rename("vix"),
            _pit_tercile(vix).rename("vix_regime"),
            ivix.rename("indiavix"),
            _pit_tercile(ivix).rename("indiavix_regime"),
        ],
        axis=1,
    )
    # calendar-daily index, forward-filled, so any signal_date joins directly
    full = pd.date_range(df.index.min(), pd.Timestamp.now().normalize())
    df = df.reindex(full).ffill()
    df.index.name = "date"
    df = df.reset_index()

    tmp = OUT.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(OUT)
    last = df.dropna(subset=["vix_regime"]).iloc[-1]
    print(
        f"wrote {OUT} ({len(df):,} days, "
        f"{df.date.min().date()} -> {df.date.max().date()})"
    )
    print(
        f"latest: VIX {last.vix:.1f} [{last.vix_regime}] · "
        f"IndiaVIX {last.indiavix:.1f} [{last.indiavix_regime}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
