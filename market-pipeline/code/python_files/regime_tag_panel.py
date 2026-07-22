#!/usr/bin/env python3
"""
regime_tag_panel.py -- Phase 2 of PPO regime-conditional factor-weight
scoring (see /Users/umashankar/.claude/plans/bright-hatching-scone.md).

Tags every row of factor_zscore_panel.parquet (Phase 1's output) with a
BULL/BEAR/SIDEWAYS/UNKNOWN regime as of that filing's PIT `filed` date --
the date the RL env's state should reflect, not the (often much earlier)
fiscal period end.

REUSE, NOT REIMPLEMENTATION: classify_regime() is imported verbatim from
walk_forward_backtest.py (200-day benchmark DMA + 5-bar slope; SIDEWAYS
band is |price-dma|<1.5% of dma). That function's own fetch_index() does a
fresh yfinance download of Nifty ONLY (India-specific, network call) --
not reused here. Instead this script computes the identical dma200/
dma200_sl formula directly off the SPY/NIFTYBEES rows already sitting in
the OHLCV parquets factor_zscore_panel.py already loaded (via
factorial_screener_test.py's BENCHMARK_SYMBOL="SPY" and
factorial_screener_test_IN.py's BENCHMARK_SYMBOL_IN="NIFTYBEES") -- zero
new network calls, and the benchmark series is held to the SAME split-
detection pass as every other symbol in this pipeline (see
benchmark_lookup()'s own docstring in factorial_screener_test.py).

FOOTGUN, HIT AND FIXED WHILE BUILDING THIS: importing factorial_screener_
test_IN monkeypatches fst.BENCHMARK_SYMBOL to "NIFTYBEES" as a module-level
side effect (its own line 93) -- the same class of bug already documented
for fst.FUND_PATH in factor_zscore_panel.py, but missed on the first pass
here (the US regime index silently got built off "NIFTYBEES", which isn't
in the US OHLCV panel, and crashed loudly rather than silently -- caught
immediately). Fixed by reading BENCHMARK_SYMBOL_US/BENCHMARK_SYMBOL_IN from
local constants below instead of the mutable fst.BENCHMARK_SYMBOL global.
"""
from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
import factorial_screener_test as fst  # noqa: E402
import factorial_screener_test_IN as fst_in  # noqa: E402
from walk_forward_backtest import classify_regime  # noqa: E402

PANEL_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factor_zscore_panel.parquet"
OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factor_zscore_panel_regime.parquet"

# importing factorial_screener_test_IN monkeypatches fst.BENCHMARK_SYMBOL to
# "NIFTYBEES" as a module-level side effect (its own line 93) -- same footgun
# already documented for fst.FUND_PATH in factor_zscore_panel.py. Capture the
# real US value from the module before that import can clobber it, and use
# these two local constants everywhere below instead of trusting the mutable
# global at call time.
BENCHMARK_SYMBOL_US = "SPY"
BENCHMARK_SYMBOL_IN = fst_in.BENCHMARK_SYMBOL_IN


def build_index_df(ohlcv: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Same dma200/dma200_sl construction as walk_forward_backtest.py's
    fetch_index(), applied to a benchmark row already in an OHLCV panel
    instead of a fresh yfinance download."""
    g = ohlcv[ohlcv["Symbol"] == symbol].sort_values("Date").set_index("Date")
    if g.empty:
        raise ValueError(f"{symbol} not found in this OHLCV panel -- cannot build regime index")
    g = g[["Close"]].copy()
    g["dma200"] = g["Close"].rolling(200).mean()
    g["dma200_sl"] = g["dma200"].diff(5)
    return g


def tag_regimes(panel: pd.DataFrame, index_us: pd.DataFrame, index_in: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    df["filed"] = pd.to_datetime(df["filed"])
    regimes = []
    for mkt, dt in zip(df["market"], df["filed"]):
        idx = index_us if mkt == "us" else index_in
        regimes.append(classify_regime(dt, idx))
    df["regime"] = regimes
    return df


def main():
    panel = pd.read_parquet(PANEL_PATH)
    print(f"Loaded {len(panel):,} panel rows ({panel['market'].value_counts().to_dict()})")

    print("\nLoading US OHLCV for SPY-based regime index...")
    ohlcv_us = fst.load_ohlcv()
    index_us = build_index_df(ohlcv_us, BENCHMARK_SYMBOL_US)
    print(f"  SPY index: {len(index_us):,} bars, {index_us.index.min().date()} to {index_us.index.max().date()}")

    print("\nLoading India OHLCV for NIFTYBEES-based regime index...")
    ohlcv_in = fst_in.load_ohlcv_in()
    index_in = build_index_df(ohlcv_in, BENCHMARK_SYMBOL_IN)
    print(f"  NIFTYBEES index: {len(index_in):,} bars, {index_in.index.min().date()} to {index_in.index.max().date()}")

    tagged = tag_regimes(panel, index_us, index_in)

    print("\nRegime distribution by market:")
    print(tagged.groupby(["market", "regime"]).size().unstack(fill_value=0))

    unknown_pct = (tagged["regime"] == "UNKNOWN").mean() * 100
    print(f"\nUNKNOWN rate: {unknown_pct:.1f}% (filings before the benchmark's own 200-bar warmup, "
          f"or a filed date with no benchmark bar within range -- excluded from Phase 3 training, not imputed)")

    tagged.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {len(tagged):,} regime-tagged rows -> {OUT_PATH}")


if __name__ == "__main__":
    main()
