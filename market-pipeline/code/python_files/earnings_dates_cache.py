#!/usr/bin/env python3
"""
earnings_dates_cache.py — persistent cache of REAL quarterly earnings
dates + analyst-consensus EPS surprise (yfinance get_earnings_dates()),
generalizing earnings_calendar.py's fetch from the 57 sector-leader
candidates to the FULL classified universe (~2,747 symbols across
IN/US/JP/KR as of this build) so pead_sector_spillover_v2.py has real
quarterly events instead of pead_sector_spillover.py's annual filing-date
+ YoY-growth-proxy events (see that module's docstring for why the annual
version is coarser than the literature standard).

RESUMABLE BY DESIGN: fetching ~2,700 symbols will hit Yahoo Finance's rate
limit multiple times (same failure mode diagnosed twice already this
session — a full batch returns 0 results, not a partial/graceful
degradation). Results are cached to cache_seed/earnings_dates_cache/
{market}.parquet incrementally; re-running only fetches symbols NOT yet
cached, so recovering from a rate-limited batch is just running this
script again — no special-casing needed, unlike the manual per-market
fixes used earlier for cross_sectional_momentum.py's sector fetch.

Usage:
    python3 earnings_dates_cache.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from stock_utils import parallel_map
import cross_sectional_momentum as csm   # sector cache -> classified symbol lists
import earnings_calendar as ec           # _yf_ticker, _fetch_one

CACHE_DIR = Path("cache_seed/earnings_dates_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(market: str) -> Path:
    return CACHE_DIR / f"{market}.parquet"


def _load_cached(market: str) -> pd.DataFrame:
    p = _cache_path(market)
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame(columns=["ticker", "Earnings Date", "EPS Estimate", "Reported EPS", "Surprise(%)"])


def fetch_and_cache(market: str, workers: int = 8) -> pd.DataFrame:
    classified = csm._load_sector_cache()
    key = f"{market}:"
    all_symbols = [k[len(key):] for k, v in classified.items() if k.startswith(key) and v != "Unknown"]

    have = _load_cached(market)
    already = set(have["ticker"].unique()) if not have.empty else set()
    missing = [s for s in all_symbols if s not in already]

    print(f"[{market}] {len(all_symbols)} classified symbols, {len(already)} already cached, "
          f"{len(missing)} to fetch...")
    if missing:
        results = parallel_map(lambda s: ec._fetch_one((market, s)), missing,
                               workers=workers, progress_every=100, label=f"{market} earnings dates")
        new_rows = []
        for r in results:
            for row in r["rows"]:
                row = dict(row)
                row["ticker"] = r["symbol"]
                new_rows.append(row)
        n_got = len(set(r["symbol"] for r in results))
        print(f"[{market}] fetched {n_got}/{len(missing)} (rest likely rate-limited or delisted — "
              f"re-run this script to retry only what's still missing)")
        if new_rows:
            combined = pd.concat([have, pd.DataFrame(new_rows)], ignore_index=True) if not have.empty else pd.DataFrame(new_rows)
            combined.to_parquet(_cache_path(market), index=False)
            have = combined

    return have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    a = ap.parse_args()
    for m in a.market:
        df = fetch_and_cache(m)
        n_tickers = df["ticker"].nunique() if not df.empty else 0
        print(f"[{m}] cache now holds {len(df)} rows across {n_tickers} tickers\n")


if __name__ == "__main__":
    main()
