#!/usr/bin/env python3
"""
sector_composite_analysis.py -- builds sector composite return indices and
checks which sectors show up disproportionately among active screener
signals, for the US universe.

DATA-COVERAGE CAVEAT (honest, not hidden): sector tags exist for only 680
of 6,480 US symbols in this panel (cache_seed/sector_map_cache.json, ~11%
coverage, yfinance .info fetched once per symbol by cross_sectional_
momentum.py in an earlier session). No full-universe sector source exists
in this repo -- company_list.parquet has no sector/industry column. This
is a PARTIAL, sector-tilted sample, not a full-universe sector study;
results describe the covered names, not necessarily the whole market.

METHOD:
  1. Sector composite = equal-weighted daily return across all COVERED
     symbols in that sector (from the same OHLCV panel/split-exclusion
     convention as every other stage here), compounded into an index
     rebased to 100 at the panel's start.
  2. Screener-sector affinity = for each screener, the sector composition
     of its ACTIVE signals vs. that sector's share of the covered
     universe (lift ratio > 1 means the screener fires on that sector
     more than its base rate -- "sectors that emerge repeatedly").
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from factorial_screener_test import OHLCV_PATH, BENCHMARK_SYMBOL
from factorial_screener_analysis import SIGNALS_PATH, SCREENERS

SECTOR_CACHE_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/sector_map_cache.json"


def load_sector_map() -> dict:
    d = json.load(open(SECTOR_CACHE_PATH))
    return {k.split(":", 1)[1]: v for k, v in d.items()
            if k.startswith("US:") and v not in (None, "Unknown")}


def build_sector_composites(sector_map: dict) -> pd.DataFrame:
    covered = list(sector_map.keys())
    ohlcv = pd.read_parquet(OHLCV_PATH, columns=["Date", "Symbol", "Close"])
    ohlcv = ohlcv[ohlcv["Symbol"].isin(covered) & (ohlcv["Symbol"] != BENCHMARK_SYMBOL)].copy()
    ohlcv["sector"] = ohlcv["Symbol"].map(sector_map)
    ohlcv = ohlcv.sort_values(["Symbol", "Date"])
    ohlcv["daily_ret"] = ohlcv.groupby("Symbol")["Close"].pct_change()
    # drop return outliers the same way the rest of this pipeline does --
    # a single unadjusted-split day would otherwise distort the whole
    # sector's equal-weighted average for that day
    ohlcv = ohlcv[ohlcv["daily_ret"].abs() < 0.5]

    daily = ohlcv.groupby(["sector", "Date"])["daily_ret"].mean().reset_index()
    daily = daily.sort_values(["sector", "Date"])
    daily["index_level"] = daily.groupby("sector")["daily_ret"].transform(
        lambda s: 100 * (1 + s.fillna(0)).cumprod())
    return daily


def screener_sector_affinity(sector_map: dict) -> pd.DataFrame:
    signals = pd.read_parquet(SIGNALS_PATH, columns=["symbol", "screener"])
    signals = signals[signals["screener"].isin(SCREENERS)].copy()
    signals["sector"] = signals["symbol"].map(sector_map)
    covered = signals.dropna(subset=["sector"])
    base_rate = pd.Series(sector_map).value_counts(normalize=True)

    rows = []
    for s in SCREENERS:
        sub = covered[covered["screener"] == s]
        if len(sub) < 20:
            continue
        mix = sub["sector"].value_counts(normalize=True)
        for sector in mix.index:
            lift = mix[sector] / base_rate.get(sector, np.nan)
            rows.append({"screener": s, "sector": sector, "signal_share": mix[sector],
                         "universe_share": base_rate.get(sector, np.nan),
                         "lift": lift, "n_signals": (sub["sector"] == sector).sum()})
    return pd.DataFrame(rows)


def main():
    sector_map = load_sector_map()
    print(f"Sector-tagged symbols: {len(sector_map)} of 6,480 US symbols in the panel "
          f"({len(sector_map)/6480*100:.1f}% coverage -- PARTIAL, not full-universe)")

    print("\nBuilding sector composite return indices from covered symbols...")
    composites = build_sector_composites(sector_map)
    composites.to_parquet("/Users/umashankar/market-pipeline/code/python_files/cache_seed/sector_composites_us.parquet", index=False)

    print("\n" + "=" * 100)
    print("SECTOR COMPOSITE TOTAL RETURN, full panel window (equal-weighted, covered symbols only)")
    print("=" * 100)
    summary = composites.groupby("sector").agg(
        start=("index_level", "first"), end=("index_level", "last"),
        n_days=("Date", "nunique"),
    )
    summary["total_return_pct"] = (summary["end"] / summary["start"] - 1) * 100
    daily_ret_std = composites.groupby("sector")["daily_ret"].std()
    summary["daily_vol_pct"] = daily_ret_std * 100
    summary = summary.sort_values("total_return_pct", ascending=False)
    print(summary[["n_days", "total_return_pct", "daily_vol_pct"]].round(2).to_string())

    print("\n" + "=" * 100)
    print("SCREENER-SECTOR AFFINITY (lift > 1 = this screener fires on this sector more than")
    print("the sector's base rate in the covered universe -- 'sectors that emerge repeatedly')")
    print("=" * 100)
    affinity = screener_sector_affinity(sector_map)
    affinity.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/screener_sector_affinity_us.csv", index=False)
    for s in affinity["screener"].unique():
        sub = affinity[affinity["screener"] == s].sort_values("lift", ascending=False)
        top = sub[sub["n_signals"] >= 10].head(3)
        if top.empty:
            continue
        desc = ", ".join(f"{r.sector} (lift {r.lift:.2f}x, n={r.n_signals})" for r in top.itertuples())
        print(f"  {s}: {desc}")

    print(f"\nSaved -> cache_seed/sector_composites_us.parquet, cache_seed/screener_sector_affinity_us.csv")


if __name__ == "__main__":
    main()
