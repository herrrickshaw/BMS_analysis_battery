#!/usr/bin/env python3
"""
stock_level_consistency.py -- v2 "beat the market" line of work, branch
claude/beat-the-market-v2.

The v1 dashboard's headline finding was that no SCREENER beats the S&P 500
in >=70% of years. This script asks a different, prior question: forget
screeners for a moment -- which INDIVIDUAL STOCKS, on their own calendar-
year return, have regularly beaten SPY, independent of whether any
screener happened to fire on them? This is the "ground truth" consistency
signal that everything downstream in v2 (the bandit, the clustering, the
synthesized screener) is built on and validated against.

METHOD: same OHLCV panel and split-exclusion convention as v1
(factorial_screener_test.py's _flag_split_days, ported not reimplemented).
For every symbol with >=5y of history, for every CALENDAR year fully
covered by the panel, compute (a) the stock's own return from the first
to the last trading day of that year and (b) SPY's return over the
identical two dates -- so a stock's "year" and SPY's "year" are always
measured on the exact same two calendar dates, never a mismatched window.
A stock-year is dropped (not winsorized) if either the stock's or SPY's
window crosses a likely-unadjusted-split day.

OUTPUT: cache_seed/stock_level_consistency_us.parquet, one row per
(symbol, year) with excess return; cache_seed/stock_level_consistency_
summary_us.parquet, one row per symbol with hit_rate/mean/std across
years -- this second table is what the bandit and clustering stages
consume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factorial_screener_test import OHLCV_PATH, BENCHMARK_SYMBOL, _flag_split_days, MIN_YEARS_HISTORY

MIN_YEARS_FOR_SUMMARY = 4


def load_ohlcv_with_splits() -> pd.DataFrame:
    df = pd.read_parquet(OHLCV_PATH)
    df = df.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    span = df.groupby("Symbol")["Date"].agg(lambda s: (s.max() - s.min()).days / 365.25)
    keep = span[span >= MIN_YEARS_HISTORY].index
    df = df[df["Symbol"].isin(keep)].copy()
    df = _flag_split_days(df)
    print(f"OHLCV: {df['Symbol'].nunique():,} symbols with >={MIN_YEARS_HISTORY}y history, {len(df):,} rows")
    return df


def yearly_returns(df: pd.DataFrame) -> pd.DataFrame:
    """First/last trading day Close per (symbol, year), plus whether any
    day in that window was flagged as a likely split."""
    df = df.copy()
    df["year"] = df["Date"].dt.year
    g = df.groupby(["Symbol", "year"])
    first = g.first()[["Close"]].rename(columns={"Close": "close_first"})
    last = g.last()[["Close"]].rename(columns={"Close": "close_last"})
    any_split = g["likely_split"].any().rename("any_split")
    n_days = g.size().rename("n_days")
    out = first.join(last).join(any_split).join(n_days).reset_index()
    out["year_return_pct"] = (out["close_last"] / out["close_first"] - 1) * 100
    out.loc[out["any_split"], "year_return_pct"] = np.nan
    return out


def main():
    ohlcv = load_ohlcv_with_splits()
    yr = yearly_returns(ohlcv)
    # only keep years with reasonably full coverage (>=200 trading days --
    # drops partial first/last calendar years at the edge of the panel)
    yr = yr[yr["n_days"] >= 200].copy()

    bench = yr[yr["Symbol"] == BENCHMARK_SYMBOL][["year", "year_return_pct"]].rename(
        columns={"year_return_pct": "bench_return_pct"})
    print(f"\n{BENCHMARK_SYMBOL} yearly returns:")
    print(bench.set_index("year")["bench_return_pct"].round(2).to_string())

    stocks = yr[yr["Symbol"] != BENCHMARK_SYMBOL].merge(bench, on="year", how="inner")
    stocks["excess_return_pct"] = stocks["year_return_pct"] - stocks["bench_return_pct"]
    stocks["beat_spy"] = stocks["excess_return_pct"] > 0

    stocks.to_parquet(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/stock_level_consistency_us.parquet",
        index=False)
    print(f"\nSaved {len(stocks):,} stock-year rows -> cache_seed/stock_level_consistency_us.parquet")

    summary = stocks.groupby("Symbol").agg(
        n_years=("year", "nunique"),
        hit_rate=("beat_spy", "mean"),
        mean_excess=("excess_return_pct", "mean"),
        std_excess=("excess_return_pct", "std"),
        worst_year=("excess_return_pct", "min"),
        best_year=("excess_return_pct", "max"),
    ).reset_index().rename(columns={"Symbol": "symbol"})
    summary["hit_rate_pct"] = summary["hit_rate"] * 100
    summary = summary[summary["n_years"] >= MIN_YEARS_FOR_SUMMARY]
    summary["sharpe_like"] = summary["mean_excess"] / summary["std_excess"]

    print(f"\nStocks with >={MIN_YEARS_FOR_SUMMARY} years of clean yearly data: {len(summary):,}")
    print("\nDistribution of hit rate across stocks (fraction of years beating SPY):")
    print(summary["hit_rate_pct"].describe().round(1).to_string())

    top = summary.sort_values(["hit_rate_pct", "mean_excess"], ascending=False).head(20)
    print("\nTop 20 by hit rate (then mean excess) among stocks with >=4 years:")
    pd.set_option("display.width", 140)
    print(top[["symbol", "n_years", "hit_rate_pct", "mean_excess", "std_excess", "worst_year", "best_year"]].round(2).to_string(index=False))

    n_ge_70 = (summary["hit_rate_pct"] >= 70).sum()
    n_ge_80 = (summary["hit_rate_pct"] >= 80).sum()
    print(f"\nStocks with hit rate >=70%: {n_ge_70:,} ({n_ge_70/len(summary)*100:.1f}%) | "
          f">=80%: {n_ge_80:,} ({n_ge_80/len(summary)*100:.1f}%)")

    summary.to_parquet(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/stock_level_consistency_summary_us.parquet",
        index=False)
    print(f"\nSaved -> cache_seed/stock_level_consistency_summary_us.parquet")


if __name__ == "__main__":
    main()
