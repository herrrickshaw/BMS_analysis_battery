#!/usr/bin/env python3
"""
China A-share TECHNICAL-ONLY factorial screener test -- extension of
factorial_screener_test.py (US) to the CN market.

SCOPE: technical screeners only. CN point-in-time fundamentals were
separately audited and found to have a FABRICATED filing-date field --
do not touch fundamentals for this market until that is independently
fixed. This script therefore runs only the 7 market-agnostic technical
screeners already defined and debugged in factorial_screener_test.py:
golden_cross, darvas, new_highs, below_200dma, reversal_weekly,
reversal_monthly, low_beta. They are IMPORTED and reused verbatim from
that module (not reimplemented) -- reimplementing risks silently
reintroducing the min_price / split-day / anti-lookahead bugs that
module's own docstrings document having already been found and fixed.

MIN_PRICE FLOOR (CNY): golden_cross/darvas/new_highs/below_200dma (and
short_term_reversal/low_beta) all take a min_price parameter, defaulted
to 5.0 in the US (USD) script after a serious bug where these screeners
fired on sub-cent OTC penny stocks and produced "excess returns" in the
millions of percent. That PROTECTION (a price floor gating out near-zero
prices) must not be bypassed here -- China has its own illiquid
low-priced/ST names that could reproduce the exact same failure mode.
But the NUMBER 5.0 does not transplant directly: it was calibrated to
USD price levels, and CNY-denominated A-share prices run structurally
lower than USD (China has no equivalent of Nasdaq/NYSE's de facto
$1-$5 minimum-price delisting pressure; many liquid, large, real
small/mid-cap constituents of CSI 500/1000 trade in the single-digit-CNY
range as a matter of routine par-value/listing convention, not distress).
Using min_price=5.0 CNY (~$0.70) would misclassify a meaningful slice of
genuinely investable China A-shares as "penny stocks" and exclude them.
Chosen instead: MIN_PRICE_CNY = 2.0 -- roughly 1/2500th of a typical
~5,000 CNY-denominated large cap, still >>100x the sub-1-CNY / sub-0.10
range where the original bug's near-zero-denominator percentage-explosion
pattern lives, and low enough to keep legitimate single-digit-CNY small
caps in the sample. Kept simple per this task's own instruction: NOT
paired with a supplementary dollar-volume/liquidity gate (dollar_vol_63d
is already computed and attached as a regression CONTROL downstream in
factorial_screener_analysis_CN_technical.py, which is where a liquidity
consideration actually belongs for this design) -- flagged as a
documented simplification, not silently omitted.

DAILY PRICE-MOVE LIMITS vs. THE _SPLIT_RATIOS SPLIT-DAY DETECTOR: China
enforces daily price-move limits -- +/-10% on the main boards (SSE/SZSE),
+/-20% on ChiNext (.SZ 300xxx) and STAR Market (.SS 688xxx), +/-5% on
ST-designated (financially distressed) stocks. _SPLIT_RATIOS (imported
unchanged from factorial_screener_test.py: -50/-66.7/-75/-80/-90/+100/
+200/+300/+400, +/-3pp tolerance) targets single-day jumps of >=50
percentage points -- the size of an unadjusted stock split or bonus
issue. A single limit-move day (+/-5% to +/-20%) is nowhere near any of
those ratios and will correctly NOT be flagged `likely_split` -- it's a
genuine one-day price move under an exchange rule, not a data artifact,
so this is the CORRECT behavior for a single day. The real risk is
different: a MULTI-DAY RUN of consecutive limit-up (or limit-down) days
around a signal date compounds into a large genuine cumulative move
(10 consecutive +10% days = +159%) that the split detector has no
mechanism to catch (by design -- it isn't a split) but that can look, in
a forward-return histogram, like the same kind of outlier a split would
produce. `_diagnose_limit_move_clustering()` below checks for exactly
this -- it does NOT exclude or winsorize anything, only reports counts,
per this task's explicit instruction to "note, don't necessarily fix."

BENCHMARK: no CSI300/Shanghai Composite series exists in this repo's
OHLCV panels -- fetched here via yfinance, reshaped to the OHLCV schema,
and APPENDED to the China panel BEFORE _flag_split_days() runs, so the
benchmark gets the identical split-detection/dollar_vol_63d/vol_63d_ann
treatment as every stock (same convention factorial_screener_test.py
uses for SPY). See fetch_benchmark() for the fallback chain actually
exercised (000300.SS -> ^SSEC -> 000001.SS -> akshare) and why
000001.SS (SSE Composite Index, Yahoo's actual ticker for what this
task calls "Shanghai Composite") is what ended up being used.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import factorial_screener_test as fst

OHLCV_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/CN.parquet"
OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_CN_technical.parquet"

# See module docstring "MIN_PRICE FLOOR (CNY)" above for the full reasoning.
MIN_PRICE_CNY = 2.0

BENCH_START = "2016-01-01"
BENCH_END = "2026-07-15"


# ── Benchmark fetch ──────────────────────────────────────────────────────────

def _reshape_yf_index(h: pd.DataFrame, symbol: str) -> pd.DataFrame:
    h = h.reset_index()
    date_col = "Date" if "Date" in h.columns else h.columns[0]
    h = h.rename(columns={date_col: "Date"})
    h["Date"] = pd.to_datetime(h["Date"])
    if h["Date"].dt.tz is not None:
        h["Date"] = h["Date"].dt.tz_localize(None)
    out = h[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    out["Symbol"] = symbol
    return out.sort_values("Date").reset_index(drop=True)


def fetch_benchmark() -> tuple[pd.DataFrame, str]:
    """Fallback chain: 000300.SS (CSI 300) -> ^SSEC (Shanghai Composite,
    literal ticker per task instructions) -> 000001.SS (SSE Composite
    Index -- Yahoo's actual ticker for the same index ^SSEC names, tried
    because ^SSEC 404s on Yahoo under that symbol) -> akshare
    index_zh_a_hist as a last resort. Each attempt is checked for a REAL
    multi-year series (>=1,000 rows AND >=8 years of span) before being
    accepted -- a technically-successful-but-thin fetch (e.g. 000300.SS
    below, which returns data but only from 2021 onward) is treated as a
    failure and the chain continues, per this task's explicit instruction
    not to silently continue with a broken/inadequate benchmark."""
    import yfinance as yf

    attempts = [
        ("000300.SS", "CSI 300"),
        ("^SSEC", "Shanghai Composite (literal ^SSEC ticker)"),
        ("000001.SS", "SSE Composite Index / Shanghai Composite (actual Yahoo ticker)"),
    ]
    for sym, label in attempts:
        try:
            h = yf.Ticker(sym).history(start=BENCH_START, end=BENCH_END, auto_adjust=False)
        except Exception as e:
            print(f"  yfinance {sym} ({label}): FAILED -- {e!r}")
            continue
        n = len(h)
        if n == 0:
            print(f"  yfinance {sym} ({label}): FAILED -- empty response")
            continue
        span_years = (h.index.max() - h.index.min()).days / 365.25
        print(f"  yfinance {sym} ({label}): {n:,} rows, "
              f"{h.index.min().date()} to {h.index.max().date()} ({span_years:.1f}y span)")
        if n >= 1000 and span_years >= 8.0:
            print(f"  -> ACCEPTED {sym} as benchmark (real multi-year daily series)")
            return _reshape_yf_index(h, sym), sym
        print(f"  -> REJECTED {sym}: does not adequately cover the 2016-2026 stock panel range, trying next option")

    print("  all yfinance attempts inadequate -- trying akshare fallback...")
    try:
        import akshare as ak
        raw = ak.index_zh_a_hist(symbol="000300", period="daily",
                                  start_date=BENCH_START.replace("-", ""), end_date=BENCH_END.replace("-", ""))
        if raw is None or len(raw) < 1000:
            raise RuntimeError(f"akshare returned only {0 if raw is None else len(raw)} rows")
        raw = raw.rename(columns={"日期": "Date", "开盘": "Open", "最高": "High",
                                   "最低": "Low", "收盘": "Close", "成交量": "Volume"})
        raw["Date"] = pd.to_datetime(raw["Date"])
        out = raw[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        out["Symbol"] = "000300.CSI_AKSHARE"
        span_years = (out["Date"].max() - out["Date"].min()).days / 365.25
        print(f"  akshare 000300: {len(out):,} rows, {out['Date'].min().date()} to {out['Date'].max().date()} "
              f"({span_years:.1f}y span) -- ACCEPTED")
        return out.sort_values("Date").reset_index(drop=True), "000300.CSI_AKSHARE"
    except Exception as e:
        print(f"  akshare fallback FAILED -- {e!r}")

    raise RuntimeError(
        "No usable China benchmark index series could be fetched from yfinance (000300.SS, ^SSEC, 000001.SS) "
        "or akshare (index_zh_a_hist). Cannot proceed without a benchmark -- refusing to silently continue.")


# ── Diagnostics: China price-move limits vs. the split-day detector ─────────

def _diagnose_limit_move_clustering(ohlcv: pd.DataFrame, tol: float = 0.3, min_run: int = 5) -> None:
    """Reports (does not exclude/fix) clustering of daily %% changes at
    China's exchange price-move-limit levels (+/-10%/+/-20%/+/-5%) and
    multi-day runs of consecutive limit moves -- see module docstring."""
    df = ohlcv[ohlcv["Symbol"] != fst.BENCHMARK_SYMBOL].copy()
    chg = df["daily_ret"] * 100
    caps_up = [10.0, 20.0, 5.0]
    caps_down = [-10.0, -20.0, -5.0]
    near_any = pd.Series(False, index=df.index)
    for c in caps_up + caps_down:
        near_any |= (chg - c).abs() <= tol
    n = int(near_any.sum())
    print(f"  {n:,} rows ({n / len(df) * 100:.2f}% of {len(df):,} non-benchmark rows) within +/-{tol}pp of a "
          f"China price-limit level (+/-10%/+/-20%/+/-5%) -- this is EXPECTED mechanical clustering from "
          f"exchange rules on a single day, not split contamination (_SPLIT_RATIOS targets >=50pp moves and "
          f"correctly does not flag these).")

    df = df.assign(_chg=chg.values)
    df = df.sort_values(["Symbol", "Date"])
    for label, caps in [("limit-up", caps_up), ("limit-down", caps_down)]:
        near = pd.Series(False, index=df.index)
        for c in caps:
            near |= (df["_chg"] - c).abs() <= tol
        df["_near"] = near.values
        grp_change = (df["_near"] != df.groupby("Symbol")["_near"].shift(1)).astype(int)
        run_id = grp_change.groupby(df["Symbol"]).cumsum()
        run_len = df.groupby(["Symbol", run_id])["_near"].transform("size")
        long_runs = df[df["_near"] & (run_len >= min_run)]
        n_rows = len(long_runs)
        n_syms = long_runs["Symbol"].nunique()
        print(f"  {label} runs of >={min_run} consecutive near-cap days: {n_rows:,} rows across {n_syms:,} symbols"
              + (f" (e.g. {sorted(long_runs['Symbol'].unique())[:5]})" if n_syms else ""))


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true",
                         help="restrict to the first 200 symbols (alphabetically) for a quick sanity check")
    args = parser.parse_args()

    print("Fetching China benchmark index...")
    bench_df, bench_symbol = fetch_benchmark()
    fst.BENCHMARK_SYMBOL = bench_symbol
    print(f"Benchmark set: BENCHMARK_SYMBOL = {bench_symbol!r} "
          f"({len(bench_df):,} rows, {bench_df['Date'].min().date()} to {bench_df['Date'].max().date()})")

    print("\nLoading China OHLCV...")
    raw = pd.read_parquet(OHLCV_PATH)
    raw = raw.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    span = raw.groupby("Symbol")["Date"].agg(lambda s: (s.max() - s.min()).days / 365.25)
    keep = span[span >= fst.MIN_YEARS_HISTORY].index
    n_total = raw["Symbol"].nunique()
    raw = raw[raw["Symbol"].isin(keep)].copy()
    print(f"  {raw['Symbol'].nunique():,} of {n_total:,} symbols with >={fst.MIN_YEARS_HISTORY}y history, "
          f"{len(raw):,} rows")

    if args.smoke_test:
        smoke_symbols = sorted(raw["Symbol"].unique())[:200]
        raw = raw[raw["Symbol"].isin(smoke_symbols)].copy()
        print(f"  SMOKE TEST: restricted to first {len(smoke_symbols)} symbols, {len(raw):,} rows")

    combined = pd.concat([raw, bench_df], ignore_index=True)
    ohlcv = fst._flag_split_days(combined)
    print(f"OHLCV+benchmark: {ohlcv['Symbol'].nunique():,} symbols, {len(ohlcv):,} rows, "
          f"{ohlcv['Date'].min().date()} to {ohlcv['Date'].max().date()}")

    print("\nDiagnosing China price-move-limit clustering (report only, not a fix)...")
    _diagnose_limit_move_clustering(ohlcv)

    print(f"\nComputing technical signals (min_price = {MIN_PRICE_CNY} CNY)...")
    gc = fst.golden_cross_signals(ohlcv, min_price=MIN_PRICE_CNY)
    gc["screener"] = "golden_cross"
    dv = fst.darvas_signals(ohlcv, min_price=MIN_PRICE_CNY)
    dv["screener"] = "darvas"
    nh = fst.new_high_signals(ohlcv, min_price=MIN_PRICE_CNY)
    nh["screener"] = "new_highs"
    b200 = fst.below_200dma_signals(ohlcv, min_price=MIN_PRICE_CNY)
    b200["screener"] = "below_200dma"
    rev_w = fst.short_term_reversal_signals(ohlcv, lookback=5, min_price=MIN_PRICE_CNY)
    rev_w["screener"] = "reversal_weekly"
    rev_m = fst.short_term_reversal_signals(ohlcv, lookback=21, min_price=MIN_PRICE_CNY)
    rev_m["screener"] = "reversal_monthly"
    lb = fst.low_beta_signals(ohlcv, min_price=MIN_PRICE_CNY)
    lb["screener"] = "low_beta"

    for name, d in [("golden_cross", gc), ("darvas", dv), ("new_highs", nh), ("below_200dma", b200),
                     ("reversal_weekly", rev_w), ("reversal_monthly", rev_m), ("low_beta", lb)]:
        print(f"  {name}: {len(d):,} signals across {d['symbol'].nunique():,} symbols")

    all_signals = pd.concat(
        [gc[["symbol", "signal_date", "screener"]], dv[["symbol", "signal_date", "screener"]],
         nh[["symbol", "signal_date", "screener"]], b200[["symbol", "signal_date", "screener"]],
         rev_w[["symbol", "signal_date", "screener"]], rev_m[["symbol", "signal_date", "screener"]],
         lb[["symbol", "signal_date", "screener"]]], ignore_index=True)
    all_signals["signal_date"] = pd.to_datetime(all_signals["signal_date"])
    all_signals["year"] = all_signals["signal_date"].dt.year

    n_bench_signals = (all_signals["symbol"] == fst.BENCHMARK_SYMBOL).sum()
    all_signals = all_signals[all_signals["symbol"] != fst.BENCHMARK_SYMBOL].reset_index(drop=True)
    print(f"  dropped {n_bench_signals:,} technical-screener signals fired on {fst.BENCHMARK_SYMBOL} itself "
          f"-- it's the benchmark, not a stock under test")
    print(f"\nTotal signals (7 technical screeners): {len(all_signals):,}")
    print(all_signals["screener"].value_counts())

    print("\nComputing forward returns...")
    lookups = fst.forward_returns(ohlcv)
    bench = fst.benchmark_lookup(ohlcv)
    all_signals = fst.attach_forward_returns(all_signals, lookups, bench)

    print("\nSpot-check: xret_{h} range per horizon (looking for millions-of-percent outliers "
          "that would indicate the min_price floor isn't working):")
    for h in fst.HORIZONS:
        col = f"xret_{h}"
        vals = all_signals[col].dropna()
        if len(vals):
            print(f"  {col}: min={vals.min():+.1f}%  max={vals.max():+.1f}%  "
                  f"n>1000%={int((vals.abs() > 1000).sum())}  n>10000%={int((vals.abs() > 10000).sum())}")
        else:
            print(f"  {col}: no valid rows")

    out_path = OUT_PATH.replace(".parquet", "_smoketest.parquet") if args.smoke_test else OUT_PATH
    all_signals.to_parquet(out_path, index=False)
    print(f"\nSaved {len(all_signals):,} signal rows -> {out_path}")


if __name__ == "__main__":
    main()
