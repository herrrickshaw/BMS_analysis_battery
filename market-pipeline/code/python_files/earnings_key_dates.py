#!/usr/bin/env python3
"""
earnings_key_dates.py — the single "next scheduled earnings date" per
stock, stored as a queryable parquet key-date table (not just an in-memory
report like earnings_calendar.py), covering the FULL classified universe
(~2,747 symbols across IN/US/JP/KR), not just the 57 sector-leader
candidates earnings_calendar.py focused on.

TWO DATA LAYERS, cheapest/most-available first:
  1. POINT ESTIMATE from earnings_dates_cache.py's already-fetched
     get_earnings_dates() data (no new network calls — reuses what
     earnings_dates_cache.py collected for the PEAD v2 rebuild). For each
     ticker, the earliest row with no Reported EPS yet (i.e. still in the
     future / unconfirmed) becomes next_date_start = next_date_end = that
     date, is_range=False.
  2. RANGE OVERRIDE from yfinance's .calendar field, which Yahoo itself
     sometimes expresses as a 2-date window (`Earnings Date: [d1, d2]`)
     rather than a single confirmed date, when the exact day hasn't been
     announced yet — this is the NATIVE range representation, not
     something invented here. Where available, it overrides the point
     estimate with next_date_start=min(d1,d2), next_date_end=max(d1,d2),
     is_range=True. This is a SEPARATE, smaller fetch pass (one extra call
     per symbol) — run it only after earnings_dates_cache.py's larger fetch
     has finished, not concurrently, to avoid compounding the same Yahoo
     Finance rate limit hit twice already this session.

OUTPUT: cache_seed/earnings_key_dates/{market}.parquet — columns:
  symbol, next_date_start, next_date_end, is_range, days_until, source, as_of

MONITORING: designed to be re-run on the SAME daily cadence as
pead_monitor.py's launchd job (com.marketpipeline.peadmonitor) — see
that script's docstring for the install pattern; wire a call to
refresh_all() into pead_monitor.py's check_and_run() rather than standing
up a second launchd job for what is fundamentally the same "did new
earnings data arrive" check.

Usage:
    python3 earnings_key_dates.py --market IN US JP KR              # layer 1 only
    python3 earnings_key_dates.py --market IN US JP KR --ranges     # + layer 2
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from stock_utils import parallel_map
import earnings_dates_cache as edc

OUT_DIR = Path("cache_seed/earnings_key_dates")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def build_point_estimates(market: str) -> pd.DataFrame:
    """Layer 1 — derived entirely from the already-cached
    earnings_dates_cache data, zero new network calls."""
    cached = edc._load_cached(market)
    if cached.empty:
        return pd.DataFrame(columns=["symbol", "next_date_start", "next_date_end",
                                      "is_range", "days_until", "source", "as_of"])
    df = cached.copy()
    df["Reported EPS"] = pd.to_numeric(df["Reported EPS"], errors="coerce")
    df["Earnings Date"] = pd.to_datetime(df["Earnings Date"]).dt.tz_localize(None)
    now = pd.Timestamp.now()
    # "Reported EPS is NaN" alone is NOT a reliable "this is upcoming" filter —
    # some old rows (e.g. 2016, 2023) never got a reported EPS backfilled by
    # yfinance and would otherwise masquerade as the "next" earnings date.
    # Require the date itself to actually be in the future.
    upcoming = df[df["Reported EPS"].isna() & (df["Earnings Date"] >= now - pd.Timedelta(days=1))]
    upcoming = upcoming.sort_values(["ticker", "Earnings Date"])
    nxt = upcoming.groupby("ticker").first().reset_index()

    out = pd.DataFrame({
        "symbol": nxt["ticker"],
        "next_date_start": nxt["Earnings Date"],
        "next_date_end": nxt["Earnings Date"],
        "is_range": False,
        "days_until": (nxt["Earnings Date"] - now).dt.days,
        "source": "get_earnings_dates",
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return out


def _yf_ticker(market: str, symbol: str) -> str:
    if market == "IN":
        return f"{symbol}.NS"
    return symbol


def _fetch_calendar_range(args) -> dict | None:
    market, symbol = args
    try:
        import yfinance as yf
        from yf_session import configure_yfinance, call_with_backoff
        configure_yfinance()
        cal = call_with_backoff(lambda: yf.Ticker(_yf_ticker(market, symbol)).calendar)
        if not cal:
            return None
        dates = cal.get("Earnings Date")
        if not dates:
            return None
        return {"symbol": symbol, "dates": [pd.Timestamp(d) for d in dates]}
    except Exception:
        return None


def enrich_with_ranges(market: str, base: pd.DataFrame, workers: int = 6, limit: int | None = None) -> pd.DataFrame:
    """Layer 2 — one .calendar call per symbol, overrides base's point
    estimate with a true [start,end] window where Yahoo itself only knows
    a range. Run AFTER the bulk earnings_dates_cache.py fetch has settled,
    not concurrently with it."""
    symbols = base["symbol"].tolist()
    if limit:
        symbols = symbols[:limit]
    print(f"[{market}] fetching .calendar range data for {len(symbols)} symbols...")
    results = parallel_map(lambda s: _fetch_calendar_range((market, s)), symbols,
                           workers=workers, progress_every=100, label=f"{market} calendar ranges")
    by_symbol = {r["symbol"]: r["dates"] for r in results}

    base = base.set_index("symbol")
    now = pd.Timestamp.now()
    for sym, dates in by_symbol.items():
        future = [d for d in dates if d > now]
        if not future:
            continue
        if sym not in base.index:
            base.loc[sym] = {"next_date_start": min(future), "next_date_end": max(future),
                              "is_range": len(future) > 1, "days_until": (min(future) - now).days,
                              "source": "calendar", "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        elif len(future) > 1:
            base.loc[sym, "next_date_start"] = min(future)
            base.loc[sym, "next_date_end"] = max(future)
            base.loc[sym, "is_range"] = True
            base.loc[sym, "days_until"] = (min(future) - now).days
            base.loc[sym, "source"] = "calendar_range"
    return base.reset_index()


def refresh_all(markets=("IN", "US", "JP", "KR"), with_ranges: bool = False) -> dict[str, pd.DataFrame]:
    out = {}
    for m in markets:
        df = build_point_estimates(m)
        if with_ranges and not df.empty:
            df = enrich_with_ranges(m, df)
        path = OUT_DIR / f"{m}.parquet"
        df.to_parquet(path, index=False)
        print(f"[{m}] {len(df)} symbols with a next earnings date -> {path}")
        out[m] = df
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    ap.add_argument("--ranges", action="store_true", help="also fetch .calendar range overrides (extra network calls)")
    a = ap.parse_args()
    results = refresh_all(a.market, with_ranges=a.ranges)

    print("\n\n" + "=" * 78)
    print("EARNINGS KEY-DATE TABLE SUMMARY")
    print("=" * 78)
    for m, df in results.items():
        if df.empty:
            print(f"{m}: no data (run earnings_dates_cache.py first)")
            continue
        n_range = int(df["is_range"].sum())
        soon = df[df["days_until"].between(0, 14)].sort_values("days_until")
        print(f"\n{m}: {len(df)} symbols, {n_range} with a real date RANGE (not a point estimate)")
        print(f"  {len(soon)} announcing within 14 days:")
        for _, r in soon.head(10).iterrows():
            date_str = (r["next_date_start"].strftime("%Y-%m-%d") if not r["is_range"]
                       else f"{r['next_date_start'].strftime('%Y-%m-%d')}..{r['next_date_end'].strftime('%Y-%m-%d')}")
            print(f"    {r['symbol']:14s} {date_str}  ({r['days_until']}d, source={r['source']})")


if __name__ == "__main__":
    main()
