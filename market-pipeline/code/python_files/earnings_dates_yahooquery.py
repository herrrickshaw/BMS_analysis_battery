#!/usr/bin/env python3
"""
earnings_dates_yahooquery.py — replaces the fragile per-ticker
yfinance.get_earnings_dates() approach (earnings_dates_cache.py) with
yahooquery's BATCH-FRIENDLY, OFFICIAL-endpoint equivalent.

WHY THIS EXISTS: earnings_dates_cache.py hit Yahoo's rate limit repeatedly
this session (full multi-hundred-symbol batches returning 0 results even
with exponential backoff — see yf_session.py's investigation) and Korea in
particular never recovered past 68/579 symbols (12%) across many retries.
yahooquery batches MANY tickers into ONE request (`Ticker([...],
asynchronous=True)`) against Yahoo's quoteSummary endpoint instead of one
HTTP call per ticker — empirically this sidesteps whatever specifically
rate-limited yfinance's per-ticker calls this session:

    EMPIRICAL TEST (2026-07-16): all 700 classified Korea symbols in ONE
    batch call -> 699/700 succeeded in 8.7 seconds (the 1 failure was a
    genuine "no fundamentals data" ticker, not a rate limit). Compare
    against yfinance's per-ticker approach, which needed 5+ retry rounds
    over ~40 minutes to reach even 68/579 (12%) for the same market.

TWO DATA SOURCES PER TICKER, both from yahooquery's Ticker object:
  1. `.calendar_events` — forward-looking: next earnings date + consensus
     EPS/revenue estimate range (High/Low/Average). Mirrors
     earnings_key_dates.py's "point estimate" layer.
  2. `.earnings` -> `earningsChart.quarterly` — HISTORICAL: last ~4
     quarters, each with `reportedDate` (the REAL announcement timestamp,
     not just a quarter-end), `actual`, `estimate`, `surprisePct`. This is
     a full substitute for pead_sector_spillover_v2.py's event source
     (earnings_dates_cache.py's Reported EPS / EPS Estimate / Surprise(%)
     columns), with the same semantics.

OUTPUT: cache_seed/earnings_dates_yahooquery/{market}.parquet — one row per
(ticker, quarter), columns: ticker, market, reported_date, period_end_date,
actual, estimate, surprise_pct, fiscal_quarter, calendar_quarter,
next_earnings_date, next_earnings_is_estimate, source="yahooquery".

RECONCILIATION: same discipline as the other independent sources built
this session (earnings_dates_sec_8k.py, earnings_dates_nse.py) — this does
NOT overwrite earnings_dates_cache.py's yfinance-sourced parquet, it's a
parallel, independently-sourced table. pead_sector_spillover_v2.py can be
pointed at whichever source has better coverage for a given market (this
one, for Korea specifically, given the coverage gap above).

Usage:
    python3 earnings_dates_yahooquery.py --market IN US JP KR
    python3 earnings_dates_yahooquery.py --market KR --batch-size 250
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

SECTOR_CACHE = Path("cache_seed/sector_map_cache.json")
OUT_DIR = Path("cache_seed/earnings_dates_yahooquery")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _yf_ticker(market: str, symbol: str) -> str:
    if market == "IN":
        return f"{symbol}.NS"
    return symbol  # US bare; JP/KR already suffixed in our data


def _classified_symbols(market: str) -> list[str]:
    cache = json.loads(SECTOR_CACHE.read_text())
    key = f"{market}:"
    return [k[len(key):] for k, v in cache.items() if k.startswith(key) and v != "Unknown"]


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def fetch_batch(market: str, symbols: list[str]) -> list[dict]:
    from yahooquery import Ticker
    yf_syms = [_yf_ticker(market, s) for s in symbols]
    sym_map = dict(zip(yf_syms, symbols))  # yf ticker -> original symbol
    t = Ticker(yf_syms, asynchronous=True, max_workers=10)

    rows = []
    try:
        earnings = t.earnings
    except Exception as e:
        print(f"  [{market}] .earnings batch call failed: {e}")
        earnings = {}
    try:
        cal = t.calendar_events
    except Exception as e:
        print(f"  [{market}] .calendar_events batch call failed: {e}")
        cal = {}

    for yf_sym, orig_sym in sym_map.items():
        edata = earnings.get(yf_sym) if isinstance(earnings, dict) else None
        cdata = cal.get(yf_sym) if isinstance(cal, dict) else None

        next_date, next_is_est = None, None
        if isinstance(cdata, dict):
            ed = cdata.get("earnings", {}).get("earningsDate")
            if ed:
                next_date = ed[0]
            next_is_est = cdata.get("earnings", {}).get("isEarningsDateEstimate")

        chart = None
        if isinstance(edata, dict):
            chart = edata.get("earningsChart", {}).get("quarterly")
        if not chart:
            # still record the forward-looking date even with no history
            rows.append({"ticker": orig_sym, "market": market, "reported_date": None,
                         "period_end_date": None, "actual": None, "estimate": None,
                         "surprise_pct": None, "fiscal_quarter": None, "calendar_quarter": None,
                         "next_earnings_date": next_date, "next_earnings_is_estimate": next_is_est,
                         "source": "yahooquery"})
            continue

        for q in chart:
            reported = q.get("reportedDate")
            reported_dt = pd.to_datetime(reported, unit="s") if reported else None
            period_end = q.get("periodEndDate")
            period_end_dt = pd.to_datetime(period_end, unit="s") if period_end else None
            rows.append({
                "ticker": orig_sym, "market": market,
                "reported_date": reported_dt, "period_end_date": period_end_dt,
                "actual": q.get("actual"), "estimate": q.get("estimate"),
                "surprise_pct": float(q["surprisePct"]) if q.get("surprisePct") not in (None, "") else None,
                "fiscal_quarter": q.get("fiscalQuarter"), "calendar_quarter": q.get("calendarQuarter"),
                "next_earnings_date": next_date, "next_earnings_is_estimate": next_is_est,
                "source": "yahooquery",
            })
    return rows


def run_market(market: str, batch_size: int = 300, resume: bool = True) -> pd.DataFrame:
    """resume=True (default): skip tickers that already have a row with
    real historical data (reported_date notna) from a prior run — makes
    retries actually accumulate progress instead of re-fetching (and
    re-risking rate-limit gaps for) the same symbols every time, matching
    the resumability contract earnings_dates_cache.py already established.
    Tickers with ONLY a null-history row (no earnings chart data at all,
    e.g. ETFs/indices) are retried every time, since that null could be a
    rate-limit artifact rather than a genuine "no data" result."""
    symbols = _classified_symbols(market)
    out_path = OUT_DIR / f"{market}.parquet"
    prior = pd.read_parquet(out_path) if resume and out_path.exists() else pd.DataFrame()

    if not prior.empty:
        have_history = set(prior[prior["reported_date"].notna()]["ticker"].unique())
        symbols = [s for s in symbols if s not in have_history]
        print(f"[{market}] {len(have_history)} tickers already have historical data cached, "
              f"{len(symbols)} still to fetch...")
    else:
        print(f"[{market}] {len(symbols)} classified symbols, batching by {batch_size}...")

    all_rows = []
    for i, batch in enumerate(_chunks(symbols, batch_size), 1):
        t0 = time.time()
        rows = fetch_batch(market, batch)
        all_rows.extend(rows)
        n_with_history = len(set(r["ticker"] for r in rows if r["reported_date"] is not None))
        print(f"  [{market}] batch {i}: {len(batch)} symbols in {time.time()-t0:.1f}s, "
              f"{n_with_history} with historical earnings data")

    new_df = pd.DataFrame(all_rows)
    if not prior.empty and not new_df.empty:
        # new rows for a ticker replace its old (possibly null) rows entirely
        refreshed_tickers = set(new_df["ticker"].unique())
        prior = prior[~prior["ticker"].isin(refreshed_tickers)]
        df = pd.concat([prior, new_df], ignore_index=True)
    elif not new_df.empty:
        df = new_df
    else:
        df = prior

    if not df.empty:
        df = df.drop_duplicates(subset=["ticker", "period_end_date"])
        df.to_parquet(out_path, index=False)
        n_tickers = df["ticker"].nunique()
        n_with_hist = df[df["reported_date"].notna()]["ticker"].nunique()
        n_with_next = df.dropna(subset=["next_earnings_date"])["ticker"].nunique()
        print(f"[{market}] -> {out_path}: {len(df)} rows, {n_tickers} tickers total, "
              f"{n_with_hist} with historical data, {n_with_next} with a next earnings date")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    ap.add_argument("--batch-size", type=int, default=300)
    a = ap.parse_args()
    for m in a.market:
        run_market(m, a.batch_size)


if __name__ == "__main__":
    main()
