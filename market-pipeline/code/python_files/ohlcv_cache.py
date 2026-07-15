#!/usr/bin/env python3
"""
ohlcv_cache.py — one incremental OHLCV store per market, shared by every consumer.

WHY
---
Measured on the 2026-07-14 run:

  * The market scans download ~13,084 tickers x 1 YEAR of history EVERY night, then
    `market_correlation_scan.py` downloads **the same universe again** for its own
    correlation matrix. Two full passes over identical data.
  * Those correlation scans had never actually run — they died on
    `ModuleNotFoundError: networkx` every night, which is why the 98-minute Jul-14
    run appeared tolerable. With networkx fixed the second 13k-ticker pass starts
    happening, and the plist's "3-5 hours" estimate becomes real.
  * India already solves this: bhavcopy fetches only the 1-2 NEW dates each day.
    US/EU/JP/KR re-fetch a full year nightly to learn one new bar.

This module applies the bhavcopy pattern to any market: persist a long-format
OHLCV parquet, and on each run fetch only dates NEWER than what's stored. A warm
run pulls ~1 bar/ticker instead of ~250 — and the second consumer pulls nothing at
all, because the first already populated the cache.

NOT a batch-size problem. `fetch_universe_prices` uses batch_size=50 deliberately:
yfinance swallows per-ticker rate-limit errors internally, so a large burst can
silently degrade a scan to 0 resolved symbols with no exception to catch (seen
live on the HK scan). Bigger batches would reintroduce that. The fix is to stop
re-fetching, not to fetch harder — so the conservative batch/sleep defaults are
preserved here.

Usage:
    import ohlcv_cache as oc
    frames = oc.get("US", symbols)              # {symbol: DataFrame(O,H,L,C,V)}
    closes = oc.get_closes("NSE", symbols, yf_suffix=".NS")   # aligned close matrix
"""
from __future__ import annotations

import datetime as _dt
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

CACHE_DIR = Path(os.environ.get(
    "BHAV_CACHE", Path.home() / "Downloads" / "data" / "bhavcopy_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Conservative on purpose — see the module docstring. Do not raise without
# re-reading fetch_universe_prices' rate-limit note.
BATCH_SIZE = 50
SLEEP_BETWEEN = 0.0
COLS = ["Open", "High", "Low", "Close", "Volume"]


def _path(market: str) -> Path:
    return CACHE_DIR / f"ohlcv_{market.upper()}.parquet"


def _read(market: str) -> pd.DataFrame:
    p = _path(market)
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(p)
        df["Date"] = pd.to_datetime(df["Date"])
        return df
    except Exception:
        return pd.DataFrame()


def _yf(sym: str, suffix: str) -> str:
    return f"{sym}{suffix}" if suffix and "." not in sym else sym


def _download(yf_symbols: List[str], period: Optional[str], start) -> Optional[pd.DataFrame]:
    import yfinance as yf
    kw = dict(auto_adjust=True, progress=False, group_by="ticker", threads=True)
    if start is not None:
        kw["start"] = start
    else:
        kw["period"] = period
    try:
        return yf.download(yf_symbols, **kw)
    except Exception as e:
        print(f"    batch failed: {str(e)[:70]}", flush=True)
        return None


def refresh(market: str, symbols: List[str], yf_suffix: str = "",
            period: str = "1y", verbose: bool = True) -> pd.DataFrame:
    """Bring the market's cache up to date, fetching ONLY missing dates."""
    cached = _read(market)
    today = _dt.date.today()
    start = None
    fetch_list = list(symbols)

    if not cached.empty:
        mx = cached["Date"].max().date()
        date_fresh = mx >= today - _dt.timedelta(days=1)
        # Symbol coverage matters as much as freshness. Checking only the date lets
        # a cache seeded with a SUBSET satisfy a request for the full universe: a
        # 60-ticker probe made a later 2,637-ticker Korea scan return "warm — no
        # fetch" and silently produce 57/2,637. Freshness is per-(symbol,date), not
        # per-file.
        have = set(cached["Symbol"].unique())
        missing = [s for s in symbols if s not in have]

        if date_fresh and not missing:
            if verbose:
                print(f"  ohlcv_cache[{market}]: warm ({len(cached):,} rows, "
                      f"{len(have):,} symbols, through {mx}) — no fetch", flush=True)
            return cached

        if missing:
            # New symbols need their full history, not just the recent gap, so they
            # are seeded over `period` while known symbols only need new dates.
            # Fetching everything over `period` is the simple, correct union.
            fetch_list = missing if date_fresh else list(symbols)
            if verbose:
                print(f"  ohlcv_cache[{market}]: {len(missing):,} of {len(symbols):,} "
                      f"symbols absent — seeding those over {period}"
                      + ("" if date_fresh else f"; cache also stale (through {mx})"),
                      flush=True)
        else:
            start = mx + _dt.timedelta(days=1)
            if verbose:
                print(f"  ohlcv_cache[{market}]: incremental from {start} "
                      f"(cache through {mx}, {len(have):,} symbols)", flush=True)
    elif verbose:
        print(f"  ohlcv_cache[{market}]: cold — seeding {period}", flush=True)

    rows = []
    n_batches = (len(fetch_list) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(fetch_list), BATCH_SIZE):
        batch = fetch_list[i:i + BATCH_SIZE]
        ys = [_yf(s, yf_suffix) for s in batch]
        bn = i // BATCH_SIZE + 1
        if verbose:
            print(f"    [{bn}/{n_batches}] {len(batch)} symbols", flush=True)
        raw = _download(ys, period, start)
        if raw is None or raw.empty:
            if SLEEP_BETWEEN:
                time.sleep(SLEEP_BETWEEN)
            continue
        for sym, ysym in zip(batch, ys):
            try:
                sub = raw[ysym] if len(ys) > 1 else raw
                sub = sub[[c for c in COLS if c in sub.columns]].dropna(how="all")
            except (KeyError, TypeError):
                continue
            if sub.empty:
                continue
            sub = sub.reset_index()
            sub.columns = ["Date"] + list(sub.columns[1:])
            sub["Symbol"] = sym
            rows.append(sub)
        if SLEEP_BETWEEN and bn < n_batches:
            time.sleep(SLEEP_BETWEEN)

    if rows:
        fresh = pd.concat(rows, ignore_index=True)
        fresh["Date"] = pd.to_datetime(fresh["Date"]).dt.tz_localize(None)
        out = pd.concat([cached, fresh], ignore_index=True) if not cached.empty else fresh
        out = out.drop_duplicates(subset=["Symbol", "Date"], keep="last")
        try:
            out.to_parquet(_path(market), compression="snappy", index=False)
        except Exception as e:
            if verbose:
                print(f"  ohlcv_cache[{market}]: could not persist: {e}", flush=True)
        if verbose:
            new = len(out) - len(cached)
            print(f"  ohlcv_cache[{market}]: +{new:,} rows -> {len(out):,} total", flush=True)
        return out
    return cached


def get(market: str, symbols: List[str], yf_suffix: str = "", period: str = "1y",
        min_history: int = 0, verbose: bool = True) -> Dict[str, pd.DataFrame]:
    """{symbol: DataFrame(Open..Volume, DatetimeIndex)} — refreshed incrementally."""
    df = refresh(market, symbols, yf_suffix, period, verbose)
    if df.empty:
        return {}
    want = set(symbols)
    out: Dict[str, pd.DataFrame] = {}
    for sym, g in df[df["Symbol"].isin(want)].groupby("Symbol"):
        g = g.set_index("Date").sort_index()[[c for c in COLS if c in g.columns]]
        if len(g) >= min_history:
            out[str(sym)] = g
    return out


def get_closes(market: str, symbols: List[str], yf_suffix: str = "",
               period: str = "1y", min_history: int = 100,
               verbose: bool = True) -> pd.DataFrame:
    """Aligned close-price matrix — drop-in for fetch_universe_prices()."""
    df = refresh(market, symbols, yf_suffix, period, verbose)
    if df.empty:
        return pd.DataFrame()
    want = set(symbols)
    df = df[df["Symbol"].isin(want)]
    wide = df.pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last")
    # same contract as fetch_universe_prices: drop thin series (delistings,
    # illiquid/renamed tickers) rather than treat them as an error
    keep = [c for c in wide.columns if wide[c].dropna().shape[0] >= min_history]
    return wide[keep].sort_index()
