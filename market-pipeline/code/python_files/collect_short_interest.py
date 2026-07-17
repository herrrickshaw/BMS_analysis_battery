#!/usr/bin/env python3
"""
collect_short_interest.py -- v8: genuinely NEW data collection (not a new
formula on data already in this pipeline), per explicit user request.

Source: FINRA's public, unauthenticated REST API
(api.finra.org/data/group/otcMarket/name/consolidatedShortInterest) --
the same bi-monthly "consolidated short interest" settlement-date dataset
financial media cites ("short interest rose 12%", "days to cover of
2.4x"). Verified live (2026-07-17): data available from at least
2019-01-15 through the current settlement date; no API key required,
just a declared User-Agent (same courtesy convention this account's own
SEC EDGAR collectors already use).

SCOPE (stated up front, not hidden): this pilot covers the S&P 500 pool
(484 symbols from cache_seed/sp500_constituents.csv, already built in
v5) rather than the full 6,480-symbol universe. One API call per symbol
returns that symbol's full available settlement history in one shot (no
need to enumerate ~170 individual settlement dates), so this is ~484
calls, tractable with light pacing. Full-universe collection would be a
follow-up, not attempted here.

POINT-IN-TIME NOTE: `settlementDate` is when short positions were
counted, not when the data became public -- FINRA publishes each
settlement's results roughly 8 trading days later on a fixed publication
calendar. This collector does NOT yet add a publication-lag adjustment
(a genuine simplification, flagged not hidden) -- the downstream
screener should be read as "N trading days after the settlement date",
slightly optimistic on availability by roughly a week. Documented here
so it isn't silently assumed away.
"""
from __future__ import annotations

import time

import pandas as pd
import requests

SP500_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/sp500_constituents.csv"
OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/short_interest_us.parquet"
API_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
HEADERS = {"User-Agent": "market-pipeline research umashankartd1991@gmail.com",
           "Content-Type": "application/json"}
PAUSE_SEC = 0.15  # light courtesy pacing, no documented rate limit found but avoid hammering


def fetch_symbol(symbol: str, limit: int = 250) -> pd.DataFrame:
    body = {"limit": limit, "compareFilters": [
        {"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": symbol}]}
    try:
        r = requests.post(API_URL, headers=HEADERS, json=body, timeout=20)
    except requests.RequestException as e:
        print(f"  {symbol}: request failed ({e})")
        return pd.DataFrame()
    if r.status_code == 204:
        return pd.DataFrame()
    if r.status_code != 200:
        print(f"  {symbol}: HTTP {r.status_code}")
        return pd.DataFrame()
    from io import StringIO
    df = pd.read_csv(StringIO(r.text))
    return df


def main():
    sp500 = pd.read_csv(SP500_PATH)
    symbols = sp500["Symbol"].tolist()
    print(f"Fetching FINRA short interest for {len(symbols)} S&P 500 symbols...")

    frames = []
    for i, sym in enumerate(symbols):
        df = fetch_symbol(sym)
        if not df.empty:
            frames.append(df)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(symbols)} symbols fetched, {sum(len(f) for f in frames):,} rows so far")
        time.sleep(PAUSE_SEC)

    if not frames:
        print("No data fetched -- aborting.")
        return
    out = pd.concat(frames, ignore_index=True)
    out["settlementDate"] = pd.to_datetime(out["settlementDate"])
    out = out.rename(columns={"symbolCode": "symbol"})
    out = out.sort_values(["symbol", "settlementDate"]).reset_index(drop=True)

    print(f"\nTotal: {len(out):,} settlement records, {out['symbol'].nunique()} symbols, "
          f"{out['settlementDate'].min().date()} to {out['settlementDate'].max().date()}")
    out.to_parquet(OUT_PATH, index=False)
    print(f"Saved -> cache_seed/short_interest_us.parquet")


if __name__ == "__main__":
    main()
