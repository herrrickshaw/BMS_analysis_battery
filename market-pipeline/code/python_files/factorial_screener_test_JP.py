#!/usr/bin/env python3
"""
Japan technical-only extension of factorial_screener_test.py.

Reuses the US script's MARKET-AGNOSTIC technical screeners verbatim
(golden_cross_signals, darvas_signals, new_high_signals, below_200dma_
signals, short_term_reversal_signals, low_beta_signals, plus
_flag_split_days/benchmark_lookup/forward_returns/attach_forward_returns)
by importing factorial_screener_test as a module and monkeypatching its
BENCHMARK_SYMBOL global -- none of that logic is reimplemented here, so
none of the already-fixed bugs (min_price floor, Darvas current-bar
exclusion, split-day exclusion) can be silently reintroduced.

TECHNICAL-ONLY, DELIBERATELY: Japan's fundamentals in this repo cover only
2021-2026 (per factorial_screener_test.py's own module docstring -- too
short for a real walk-forward) AND a separate audit of this account's own
found the point-in-time filing-date field for non-US fundamentals to be
FABRICATED. Neither issue touches the technical screeners (they only ever
read OHLCV), so this script runs the 7 technical-only screeners and stops
there -- no fundamentals module is imported or referenced.

MIN_PRICE FLOOR (JPY, not the US $5.0 default): factorial_screener_test.py's
min_price=5.0 default is a USD floor calibrated to US sub-cent OTC penny
stocks. Japan trades in JPY with much larger nominal denominations (lot-
size/lot-price conventions keep even small-cap names in the hundreds of
yen) -- this panel's median Close is ~983 JPY, 25th percentile ~538 JPY,
and only ~0.001% of rows are below 5 JPY at all, so a literal 5.0 floor
would do effectively nothing here and let genuinely illiquid/broken
sub-100-yen names through. Checked the empirical distribution before
picking a number: ~1.4% of rows sit below 100 JPY vs. ~0.37% below 50 JPY
-- JP_MIN_PRICE = 100.0 JPY excludes the thin low tail without cutting into
the real small-cap universe (which mostly sits well above that). This is a
documented judgment call, same spirit as the US $5 floor, not a rigorous
calibration -- the goal is excluding broken/near-worthless quotes, not
matching the US number.

DATA-QUALITY ANOMALY FOUND AND HANDLED: symbol 8303.T has 11 consecutive
rows (2025-11-17 to 2025-12-01) with Close pinned at exactly
55,320,000,000 JPY and Volume=0 throughout -- a data-capture artifact, not
a real price: the series returns to its normal ~1,300-1,700 JPY range
immediately after, and the jump doesn't match any of _SPLIT_RATIOS (so
_flag_split_days would NOT have caught it as an unadjusted split -- a
different failure mode). This is the ONLY symbol/window in the whole
7.3M-row panel above 1,000,000 JPY (612 rows sit above 100,000 JPY, all
economically plausible pre-split blue-chip names, left untouched).
Excluded via a hard sanity ceiling (Close <= PRICE_SANITY_CEILING) applied
BEFORE _flag_split_days and before any screener runs, so it cannot
contaminate golden_cross/new_high/below_200dma signals or forward-return
windows for that symbol -- same "exclude the artifact, don't let it
silently distort a percentage-based screener" principle as the US script's
own split-day handling.

BENCHMARK: no Nikkei/TOPIX series exists in the JP OHLCV parquet, so it is
fetched here via yfinance (^N225), reshaped to the same Date/Open/High/
Low/Close/Volume/Symbol schema, and APPENDED to the JP OHLCV BEFORE
_flag_split_days runs on the combined frame -- so the benchmark gets
dollar_vol_63d/vol_63d_ann/likely_split computed by the exact same code
path as every stock, not a separately-sourced index level bolted on after
the fact. fst.BENCHMARK_SYMBOL is monkeypatched to "^N225" at import time,
which is enough for low_beta_signals/benchmark_lookup/attach_forward_
returns (all of which read the module-level global at call time, not at
def time) to pick it up with zero changes to factorial_screener_test.py.
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")

import pandas as pd

import factorial_screener_test as fst

JP_OHLCV_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/JP.parquet"
OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_JP_technical.parquet"

JP_MIN_PRICE = 100.0  # JPY -- see module docstring for the empirical calibration
PRICE_SANITY_CEILING = 10_000_000.0  # JPY -- excludes the 8303.T data-capture artifact, see docstring

fst.BENCHMARK_SYMBOL = "^N225"  # module-level monkeypatch; must happen before any fst function is called


def fetch_nikkei_benchmark() -> pd.DataFrame:
    """Fetch ^N225 via yfinance and reshape to the OHLCV schema every
    screener/forward-return function expects. Verifies the fetch actually
    returned a real multi-year daily series before returning -- an empty
    or short benchmark would silently zero out every low_beta/xret
    computation downstream."""
    import yfinance as yf
    t = yf.Ticker("^N225")
    h = t.history(start="2016-01-01", end="2026-07-15", auto_adjust=False)
    if h is None or h.empty or len(h) < 500:
        raise RuntimeError(
            f"^N225 fetch via yfinance failed or returned too little data "
            f"({0 if h is None else len(h)} rows) -- refusing to proceed with a broken benchmark"
        )
    h = h.reset_index()
    h["Date"] = pd.to_datetime(h["Date"]).dt.tz_localize(None)
    out = h[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    out["Symbol"] = "^N225"
    span_years = (out["Date"].max() - out["Date"].min()).days / 365.25
    print(f"  ^N225 fetched via yfinance: {len(out):,} rows, "
          f"{out['Date'].min().date()} to {out['Date'].max().date()} ({span_years:.1f}y)")
    if span_years < fst.MIN_YEARS_HISTORY:
        raise RuntimeError(f"^N225 benchmark span ({span_years:.1f}y) is below MIN_YEARS_HISTORY -- broken fetch")
    return out


def load_jp_ohlcv(symbol_limit: int | None = None) -> pd.DataFrame:
    df = pd.read_parquet(JP_OHLCV_PATH)

    n_before = len(df)
    df = df[df["Close"] <= PRICE_SANITY_CEILING].copy()
    n_dropped = n_before - len(df)
    if n_dropped:
        print(f"  dropped {n_dropped:,} rows with Close > {PRICE_SANITY_CEILING:,.0f} JPY "
              f"(8303.T data-capture artifact sanity ceiling, see module docstring)")

    if symbol_limit:
        keep_syms = sorted(df["Symbol"].unique())[:symbol_limit]
        df = df[df["Symbol"].isin(keep_syms)].copy()
        print(f"  SMOKE TEST: limited to first {len(keep_syms)} symbols (of {df['Symbol'].nunique()} kept after limit)")

    df = df.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    span = df.groupby("Symbol")["Date"].agg(lambda s: (s.max() - s.min()).days / 365.25)
    keep = span[span >= fst.MIN_YEARS_HISTORY].index
    df = df[df["Symbol"].isin(keep)].copy()

    bench = fetch_nikkei_benchmark()
    # append BEFORE _flag_split_days so the benchmark gets the identical
    # split-detection / dollar_vol_63d / vol_63d_ann treatment as every stock
    df = pd.concat([df, bench], ignore_index=True)

    df = fst._flag_split_days(df)
    print(f"OHLCV (JP stocks + ^N225 benchmark): {df['Symbol'].nunique()} symbols with "
          f">={fst.MIN_YEARS_HISTORY}y history, {len(df):,} rows, "
          f"{df['Date'].min().date()} to {df['Date'].max().date()}")
    return df


def run_screeners(ohlcv: pd.DataFrame) -> pd.DataFrame:
    print(f"\nComputing technical signals (min_price = {JP_MIN_PRICE:.0f} JPY)...")
    gc = fst.golden_cross_signals(ohlcv, min_price=JP_MIN_PRICE)
    gc["screener"] = "golden_cross"
    dv = fst.darvas_signals(ohlcv, min_price=JP_MIN_PRICE)
    dv["screener"] = "darvas"
    nh = fst.new_high_signals(ohlcv, min_price=JP_MIN_PRICE)
    nh["screener"] = "new_highs"
    b200 = fst.below_200dma_signals(ohlcv, min_price=JP_MIN_PRICE)
    b200["screener"] = "below_200dma"
    rev_w = fst.short_term_reversal_signals(ohlcv, lookback=5, min_price=JP_MIN_PRICE)
    rev_w["screener"] = "reversal_weekly"
    rev_m = fst.short_term_reversal_signals(ohlcv, lookback=21, min_price=JP_MIN_PRICE)
    rev_m["screener"] = "reversal_monthly"
    lb = fst.low_beta_signals(ohlcv, min_price=JP_MIN_PRICE)
    lb["screener"] = "low_beta"

    parts = [("golden_cross", gc), ("darvas", dv), ("new_highs", nh), ("below_200dma", b200),
             ("reversal_weekly", rev_w), ("reversal_monthly", rev_m), ("low_beta", lb)]
    for name, d in parts:
        print(f"  {name}: {len(d):,} signals across {d['symbol'].nunique():,} symbols")

    all_signals = pd.concat(
        [d[["symbol", "signal_date", "screener"]] for _, d in parts], ignore_index=True)
    all_signals["signal_date"] = pd.to_datetime(all_signals["signal_date"])
    all_signals["year"] = all_signals["signal_date"].dt.year

    n_bench_signals = (all_signals["symbol"] == fst.BENCHMARK_SYMBOL).sum()
    all_signals = all_signals[all_signals["symbol"] != fst.BENCHMARK_SYMBOL].reset_index(drop=True)
    print(f"  dropped {n_bench_signals:,} technical-screener signals fired on {fst.BENCHMARK_SYMBOL} itself "
          f"-- it's the benchmark, not a stock under test")
    print(f"\nTotal signals (all 7 technical screeners): {len(all_signals):,}")
    print(all_signals["screener"].value_counts())
    return all_signals


def attach_returns(ohlcv: pd.DataFrame, all_signals: pd.DataFrame) -> pd.DataFrame:
    print("\nComputing forward returns...")
    lookups = fst.forward_returns(ohlcv)
    bench = fst.benchmark_lookup(ohlcv)
    return fst.attach_forward_returns(all_signals, lookups, bench)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke-test", action="store_true", help="run on first 200 symbols only, write to a *_smoketest.parquet")
    ap.add_argument("--symbol-limit", type=int, default=None, help="override smoke-test symbol count")
    args = ap.parse_args()
    limit = args.symbol_limit or (200 if args.smoke_test else None)

    ohlcv = load_jp_ohlcv(symbol_limit=limit)
    all_signals = run_screeners(ohlcv)
    all_signals = attach_returns(ohlcv, all_signals)

    out_path = OUT_PATH.replace(".parquet", "_smoketest.parquet") if args.smoke_test else OUT_PATH
    all_signals.to_parquet(out_path, index=False)
    print(f"\nSaved {len(all_signals):,} signal rows -> {out_path}")


if __name__ == "__main__":
    main()
