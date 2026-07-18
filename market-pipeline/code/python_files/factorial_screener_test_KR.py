#!/usr/bin/env python3
"""
South Korea extension of factorial_screener_test.py -- TECHNICAL SCREENERS
ONLY. Fundamentals are explicitly out of scope for this script: they were
separately audited and found to have a fabricated point-in-time filing-date
field, so nothing here touches Piotroski/Coffee Can/Magic Formula/Bull
Cartel/etc.

Reuses the reference implementation's screener functions VERBATIM (imported
directly from factorial_screener_test.py, not reimplemented) -- those
functions are market-agnostic: they only operate on whatever OHLCV
DataFrame is passed in (columns Symbol/Date/Open/High/Low/Close/Volume),
so the exact same golden_cross_signals/darvas_signals/new_high_signals/
below_200dma_signals/short_term_reversal_signals/low_beta_signals,
_flag_split_days, forward_returns/benchmark_lookup/attach_forward_returns
code that was already debugged (including the min_price penny-stock fix)
on the US panel runs unmodified here.

MIN-PRICE FLOOR FOR KOREA (read this before changing it):
The US default min_price=5.0 assumes USD-denominated prices where $5 is a
meaningful "this is not an OTC penny stock" floor. Korean equities are
KRW-denominated and trade at prices that are numerically ~1,000-1,500x
larger than the equivalent USD price for a similar-cap company (no KRW
equivalent of a "$1 stock" convention -- a normal, liquidity, large-cap
Korean stock routinely trades in the thousands to tens of thousands of won).
Using 5.0 KRW as the floor would exclude essentially nothing (see the data
check below) and would NOT catch the same "near-zero-price denominator
produces an astronomical percentage return" failure mode the US fix was
built for.

Checked the actual KR.parquet distribution before picking a number:
  - min Close across the whole panel: KRW 2.0 (a handful of clearly-broken
    rows -- this is the exact near-zero-price artifact pattern from the US
    bug, just at KRW scale)
  - 25th/50th/75th percentile Close: KRW 3,422 / 6,993 / 16,607
  - 0 of 2,597 symbols have a MEDIAN Close below KRW 5
  - 18 of 2,597 symbols have a MEDIAN Close below KRW 1,000 (a mix of
    genuinely low-priced small/micro caps, not obviously broken data, but
    still the kind of thin/illiquid name where a small absolute move
    produces a large percentage move)
  - only ~2.08% of all rows have Close < KRW 1,000; ~0.34% < KRW 500

MIN_PRICE_KR = 1,000.0 KRW is used for every screener below (all six
reusable screener functions that accept a min_price parameter --
golden_cross, darvas, new_highs, below_200dma, short_term_reversal
[weekly+monthly], low_beta -- get the same floor, for the same reason the
US version applies it uniformly: the failure mode is "percentage return on
a near-zero denominator," not specific to any one screener). This excludes
a small, deliberately conservative slice of the panel (~2% of rows) while
being nowhere near restrictive enough to exclude genuine large/mid-cap
Korean names, which trade far above this level. It is NOT a literal
unit-for-unit translation of the US $5 floor (that would be economically
meaningless in KRW) -- it is picked to serve the SAME PURPOSE the US floor
serves: excluding broken/near-zero-price data, not matching a nominal
number across currencies.

KOSPI BENCHMARK: no Korea benchmark exists in the KR.parquet panel (unlike
US.parquet, which includes SPY as a row). Fetched separately via yfinance
(^KS11, the KOSPI Composite Index) and appended as additional Symbol=^KS11
rows to the OHLCV panel BEFORE _flag_split_days runs, so the benchmark gets
the identical split-detection / dollar_vol_63d / vol_63d_ann treatment as
every real stock -- same convention as SPY's row in the US panel.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
import factorial_screener_test as fst  # noqa: E402 -- reuse, do not reimplement

OHLCV_PATH_KR = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/KR.parquet"
OUT_PATH_FULL = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_KR_technical.parquet"
OUT_PATH_SMOKE = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_KR_technical_SMOKETEST.parquet"

MIN_PRICE_KR = 1000.0  # see module docstring for the reasoning
BENCHMARK_SYMBOL_KR = "^KS11"  # KOSPI Composite
STALE_MIN_RUN = 20  # trading days; see _flag_stale_halted_days docstring


# ── KOSPI benchmark fetch ────────────────────────────────────────────────────

def fetch_kospi_benchmark() -> pd.DataFrame:
    """Fetch ^KS11 (KOSPI Composite) daily OHLCV via yfinance and reshape it
    to match the KR.parquet schema (Date/Open/High/Low/Close/Volume/Symbol).
    Verifies the fetch actually returned a real multi-year daily series
    before returning -- do not silently continue with an empty/broken
    benchmark."""
    import yfinance as yf

    print("Fetching KOSPI Composite (^KS11) benchmark via yfinance...")
    raw = yf.Ticker(BENCHMARK_SYMBOL_KR).history(start="2016-01-01", end="2026-07-15", auto_adjust=False)
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned an empty ^KS11 series -- cannot proceed without a benchmark")

    raw = raw.reset_index()
    # yfinance's index column is named "Date", tz-aware (Asia/Seoul) -- strip tz
    # to match the tz-naive datetime64[ns] Date column in KR.parquet
    raw["Date"] = pd.to_datetime(raw["Date"]).dt.tz_localize(None)
    bench = raw[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    bench["Symbol"] = BENCHMARK_SYMBOL_KR
    bench = bench.sort_values("Date").reset_index(drop=True)

    span_years = (bench["Date"].max() - bench["Date"].min()).days / 365.25
    print(f"  ^KS11: {len(bench):,} rows, {bench['Date'].min().date()} to {bench['Date'].max().date()} "
          f"({span_years:.1f} years)")
    if len(bench) < 500 or span_years < 5.0:
        raise RuntimeError(
            f"^KS11 benchmark fetch looks broken/too short (rows={len(bench)}, span={span_years:.1f}y) "
            f"-- refusing to proceed with a bad benchmark")
    if bench["Close"].isna().all() or (bench["Close"] <= 0).all():
        raise RuntimeError("^KS11 benchmark fetch has no valid Close prices -- refusing to proceed")
    return bench


def _flag_stale_halted_days(df: pd.DataFrame, min_run: int = STALE_MIN_RUN) -> pd.DataFrame:
    """Korea-specific data-quality addition -- NOT part of the reused
    factorial_screener_test.py convention, added after the smoke test
    caught it (see spot_check() output / final report). A slice of the
    small/micro-cap KR.parquet symbols carry long stretches of Volume==0
    with a perfectly FLAT Close (no real trade happening -- reads like a
    suspended/delisted ticker whose feed keeps printing a stale last-mark
    price), followed by a discontinuous jump when the feed updates again.

    Concretely found on 000300.KS in the 200-symbol smoke test: Volume=0
    for hundreds of consecutive trading days at a flat KRW 1,607.74, then a
    jump to KRW 14,481.09 (+801%, NOT one of the ratios _flag_split_days
    checks for -- that detector only pattern-matches recognizable stock-
    split ratios) with volume still 0. Repeats three more times through
    mid-2025 (each ~+800%), producing xret_T+252d up to +72,798% -- not a
    real stock return (nobody could trade a Volume=0 print), a dead/stale-
    data artifact the split detector was never designed to catch.

    Flags any day inside a run of >=min_run consecutive Volume==0-and-flat-
    Close days, PLUS the first day after such a run ends (where the
    discontinuous "catch-up" jump typically prints), and ORs it into the
    SAME `likely_split` column the reused screener/forward-return functions
    already respect -- reuses the existing exclusion machinery (flag-and-
    exclude, not winsorize, matching this repo's own convention) rather
    than adding a parallel one. min_run=20 trading days (~1 month) is
    chosen to avoid flagging genuinely illiquid-but-real single no-trade
    days, while still catching multi-month halted/delisted stretches."""
    df = df.sort_values(["Symbol", "Date"]).copy()
    flat_zero = (df["Volume"] == 0) & (df["Close"] == df.groupby("Symbol")["Close"].shift(1))
    notflat = (~flat_zero).astype(int)
    grp = notflat.groupby(df["Symbol"]).cumsum()
    run_len = flat_zero.groupby([df["Symbol"], grp]).transform("sum")
    is_stale_run = flat_zero & (run_len >= min_run)
    resumption = is_stale_run.groupby(df["Symbol"]).shift(1, fill_value=False) & ~is_stale_run
    stale_flag = is_stale_run | resumption
    n_before = int(df["likely_split"].sum())
    df["likely_split"] = df["likely_split"] | stale_flag
    n_after = int(df["likely_split"].sum())
    print(f"  [KR data-quality] flagged {int(stale_flag.sum()):,} stale/halted-data days "
          f"(Volume=0 flat-price runs >={min_run}d + resumption day) across "
          f"{df.loc[stale_flag, 'Symbol'].nunique():,} symbols -- folded into likely_split "
          f"({n_before:,} -> {n_after:,} total flagged rows)")
    return df


# ── Load & filter (Korea) ────────────────────────────────────────────────────

def load_ohlcv_kr(smoke_test: bool = False, smoke_n: int = 200) -> pd.DataFrame:
    df = pd.read_parquet(OHLCV_PATH_KR)
    df = df.sort_values(["Symbol", "Date"]).reset_index(drop=True)

    if smoke_test:
        symbols = sorted(df["Symbol"].unique())[:smoke_n]
        df = df[df["Symbol"].isin(symbols)].copy()
        print(f"[SMOKE TEST] subset to first {len(symbols)} symbols before filtering")

    # same >=5yr history filter as load_ohlcv() (US)
    span = df.groupby("Symbol")["Date"].agg(lambda s: (s.max() - s.min()).days / 365.25)
    keep = span[span >= fst.MIN_YEARS_HISTORY].index
    df = df[df["Symbol"].isin(keep)].copy()
    print(f"KR OHLCV: {df['Symbol'].nunique()} symbols with >={fst.MIN_YEARS_HISTORY}y history, "
          f"{len(df):,} rows, {df['Date'].min().date()} to {df['Date'].max().date()}")

    bench = fetch_kospi_benchmark()
    combined = pd.concat([df, bench], ignore_index=True)

    # _flag_split_days runs on the COMBINED frame so the benchmark gets the
    # same split-detection / dollar_vol_63d / vol_63d_ann treatment as every
    # stock (per module docstring)
    combined = fst._flag_split_days(combined)
    combined = _flag_stale_halted_days(combined)
    print(f"Combined (stocks + ^KS11): {combined['Symbol'].nunique()} symbols, {len(combined):,} rows")
    return combined


# ── Main ──────────────────────────────────────────────────────────────────────

def run(smoke_test: bool, smoke_n: int) -> pd.DataFrame:
    ohlcv = load_ohlcv_kr(smoke_test=smoke_test, smoke_n=smoke_n)

    # monkeypatch the module-level BENCHMARK_SYMBOL used internally by
    # low_beta_signals / benchmark_lookup -- resolved dynamically at call
    # time, so this takes effect for every call below
    fst.BENCHMARK_SYMBOL = BENCHMARK_SYMBOL_KR

    print("\nComputing technical signals (Korea, min_price=KRW %.0f)..." % MIN_PRICE_KR)
    gc = fst.golden_cross_signals(ohlcv, min_price=MIN_PRICE_KR)
    gc["screener"] = "golden_cross"
    dv = fst.darvas_signals(ohlcv, min_price=MIN_PRICE_KR)
    dv["screener"] = "darvas"
    nh = fst.new_high_signals(ohlcv, min_price=MIN_PRICE_KR)
    nh["screener"] = "new_highs"
    b200 = fst.below_200dma_signals(ohlcv, min_price=MIN_PRICE_KR)
    b200["screener"] = "below_200dma"
    rev_w = fst.short_term_reversal_signals(ohlcv, lookback=5, min_price=MIN_PRICE_KR)
    rev_w["screener"] = "reversal_weekly"
    rev_m = fst.short_term_reversal_signals(ohlcv, lookback=21, min_price=MIN_PRICE_KR)
    rev_m["screener"] = "reversal_monthly"
    lb = fst.low_beta_signals(ohlcv, min_price=MIN_PRICE_KR)
    lb["screener"] = "low_beta"

    for name, sdf in [("golden_cross", gc), ("darvas", dv), ("new_highs", nh),
                       ("below_200dma", b200), ("reversal_weekly", rev_w),
                       ("reversal_monthly", rev_m), ("low_beta", lb)]:
        print(f"  {name}: {len(sdf):,} signals across {sdf['symbol'].nunique():,} symbols")

    all_signals = pd.concat(
        [gc[["symbol", "signal_date", "screener"]],
         dv[["symbol", "signal_date", "screener"]],
         nh[["symbol", "signal_date", "screener"]],
         b200[["symbol", "signal_date", "screener"]],
         rev_w[["symbol", "signal_date", "screener"]],
         rev_m[["symbol", "signal_date", "screener"]],
         lb[["symbol", "signal_date", "screener"]]],
        ignore_index=True)
    all_signals["signal_date"] = pd.to_datetime(all_signals["signal_date"])
    all_signals["year"] = all_signals["signal_date"].dt.year

    n_bench_signals = (all_signals["symbol"] == BENCHMARK_SYMBOL_KR).sum()
    all_signals = all_signals[all_signals["symbol"] != BENCHMARK_SYMBOL_KR].reset_index(drop=True)
    print(f"  dropped {n_bench_signals:,} technical-screener signals fired on {BENCHMARK_SYMBOL_KR} itself "
          f"-- it's the benchmark, not a stock under test")
    print(f"\nTotal signals (all technical screeners): {len(all_signals):,}")
    print(all_signals["screener"].value_counts())

    print("\nComputing forward returns...")
    lookups = fst.forward_returns(ohlcv)
    bench = fst.benchmark_lookup(ohlcv)
    all_signals = fst.attach_forward_returns(all_signals, lookups, bench)

    return all_signals


def spot_check(signals: pd.DataFrame) -> None:
    """Sanity check before trusting the run: any xret in the millions-of-
    percent range indicates the min_price floor isn't working or there's a
    data-quality issue analogous to the earlier US penny-stock bug."""
    xret_cols = [c for c in signals.columns if c.startswith("xret_")]
    print("\n--- Spot check: xret extremes per horizon ---")
    blown_up = False
    for c in xret_cols:
        s = signals[c].dropna()
        if s.empty:
            continue
        print(f"  {c}: min={s.min():+.1f}%  max={s.max():+.1f}%  mean={s.mean():+.2f}%  "
              f"|>10,000%|={((s.abs() > 10000)).sum()}")
        if (s.abs() > 1_000_000).any():
            blown_up = True
    if blown_up:
        print("  *** WARNING: found xret values >1,000,000% -- min_price floor or data quality issue, "
              "investigate before trusting this run ***")
    else:
        print("  no xret values in the millions-of-percent range -- looks sane")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke-test", action="store_true", help="run on first N symbols only, for validation")
    ap.add_argument("--smoke-n", type=int, default=200)
    args = ap.parse_args()

    signals = run(smoke_test=args.smoke_test, smoke_n=args.smoke_n)
    spot_check(signals)

    out_path = OUT_PATH_SMOKE if args.smoke_test else OUT_PATH_FULL
    signals.to_parquet(out_path, index=False)
    print(f"\nSaved {len(signals):,} signal rows -> {out_path}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
