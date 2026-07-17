#!/usr/bin/env python3
"""
India technical-screener-only extension of factorial_screener_test.py.

SCOPE: Technical screeners ONLY (golden_cross, darvas, new_highs,
below_200dma, reversal_weekly, reversal_monthly, low_beta). Fundamentals are
explicitly OUT OF SCOPE here -- separately audited and found too thin/
unreliable for India (factorial_screener_test.py's own docstring: 75/8944
symbols with PIT fundamentals coverage). Do not add fundamental screeners to
this script; that determination stands.

REUSE, NOT REIMPLEMENTATION: every screener function, the split-day flagging
pass, the forward-return machinery, and the benchmark-lookup mechanism are
imported directly from factorial_screener_test.py and called verbatim. This
file only supplies a different OHLCV source, a different benchmark symbol,
and the wiring to run just the 7 technical screeners. No screener logic is
copied or reimplemented, so none of the (now-fixed) US bugs -- e.g. the
missing min_price floor that produced +18,999,884% "excess returns" on
sub-cent OTC tickers -- can be reintroduced by drift between two copies of
the same logic.

BENCHMARK: NIFTYBEES (a Nifty 50 ETF, confirmed present in IN.parquet: 1,238
rows, 2021-07-02 to 2026-07-02) stands in for SPY. Its history is SHORTER
than the full OHLCV panel (2016-06-27 to 2026-07-02) -- any signal dated
before 2021-07-02 has no benchmark price to compare against, so its xret_*
columns come out NaN via attach_forward_returns' existing NaN-on-missing-
lookup behavior (searchsorted against bench_dates returns an out-of-range
position, both _window_return calls with fpos >= len(dates) return NaN, and
NaN - NaN registers as NaN in xrows). This is a REAL LIMITATION, not
silently patched around: roughly the first 5 years of this 10-year OHLCV
panel cannot be excess-return-tested against Nifty 50 with this benchmark.
Downstream analysis scripts should report this rather than avoid mentioning
it.

MIN_PRICE FLOOR (INR vs USD): golden_cross_signals, darvas_signals,
new_high_signals, and below_200dma_signals all default to min_price=5.0,
calibrated in the US script to keep out sub-$5 OTC penny stocks whose
percentage returns blow up near a near-zero denominator. Kept AS-IS (not
scaled up for INR) here, deliberately:
  - INR 5 (~$0.06 at ~83 INR/USD) is a much LOWER absolute bar in USD terms
    than the original $5 US floor -- so if anything this floor is looser for
    India, not tighter, and won't falsely exclude legitimate small/mid-caps
    the way a naively-scaled ~INR 400 floor might.
  - The purpose of this floor was never "match a specific dollar amount of
    economic significance" -- it was "keep the denominator of a percentage
    return far enough from zero that a few-paisa/cent bounce doesn't
    register as a four-to-eight-digit percentage gain." INR 5 already does
    that: a stock has to move by whole rupees, not paise, to cross a
    material band around that floor.
  - NSE/BSE do list genuine sub-INR-5 shell/penny names (SME-platform micro-
    caps, delisting candidates) that exhibit exactly the same microstructure/
    bid-ask-bounce pathology the US floor was built to exclude -- so the
    mechanism this floor defends against is present in India too, and a
    floor of INR 5 (not 0, not lowered) is the right call, not a US-specific
    artifact copied over uncritically.
  - NOT raising it to something like INR 100-500 (a more India-typical
    "not a penny stock" bar) because that would change the FLOOR'S PURPOSE
    from "exclude data-artifact percentage explosions" to "exclude small-cap
    stocks as an asset class" -- a much broader and more consequential
    filtering decision this task was not asked to make, and one that would
    make this script's screener universe silently narrower than the US
    script's for no documented reason.
  This is a judgment call, stated plainly rather than assumed: min_price=5.0
  is kept as the INR floor, understood as "a few rupees, not a calibrated
  fraction of a typical Indian share price."

DATA-CONSISTENCY: this is the one and only script that builds the signal
panel every downstream India analysis (factorial_screener_analysis_IN_
technical.py, year_by_year_consistency_IN.py if added later) should read --
cache_seed/factorial_screener_signals_IN_technical.parquet -- for the same
"exactly one source of truth" reason factorial_screener_test.py documents
for the US panel.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
import factorial_screener_test as fst  # noqa: E402  -- reused verbatim, not reimplemented

OHLCV_PATH_IN = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/IN.parquet"
BENCHMARK_SYMBOL_IN = "NIFTYBEES"
OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_IN_technical.parquet"
SMOKE_OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_IN_technical_SMOKETEST.parquet"

# Monkeypatch AFTER import, at module load time, so every fst function that
# reads the module-level BENCHMARK_SYMBOL global (low_beta_signals,
# benchmark_lookup, attach_forward_returns' print lines) sees NIFTYBEES, not
# the US default SPY, for the whole lifetime of this process.
fst.BENCHMARK_SYMBOL = BENCHMARK_SYMBOL_IN


def load_ohlcv_in(smoke_test: bool = False, smoke_n: int = 200) -> pd.DataFrame:
    """Same >=5yr-history filter and _flag_split_days pass as fst.load_ohlcv(),
    pointed at the India parquet instead of US -- WITH ONE DOCUMENTED
    EXCEPTION: the benchmark symbol (NIFTYBEES) is exempted from the >=5yr
    filter. Its actual span is (2026-07-02 - 2021-07-02) = 1,826 days /
    365.25 = 4.9993 years -- a hair UNDER the 5.0y threshold, so applying the
    filter uniformly would drop the benchmark itself and silently zero out
    every xret_* column for the whole panel (attach_forward_returns would
    have no NIFTYBEES price series to diff against at all, not even for
    recent signals). The >=5y filter exists to make sure a SCREENED symbol
    has enough history for its own signal computation (golden_cross needs
    210+ bars, new_highs 260+, etc.) -- NIFTYBEES is never screened (it's
    dropped from all_signals as "the benchmark, not a stock under test"), so
    that rationale doesn't apply to it; only "does it have a Date/Close
    series to look prices up in" does, and 1,238 rows comfortably clears
    every screener's own internal length requirement (low_beta's is the
    longest, at lookback+5=257).

    For --smoke-test: rather than literally "first N symbols alphabetically"
    (verified to be degenerate here -- India's alphabetically-earliest
    symbols, e.g. 07AGG/08ABB/0KFL25, are short-lived NCD/bond tickers with
    0.0-1.1 years of history, not equities, so a literal alphabetical slice
    would smoke-test on zero real signals), take the first `smoke_n` symbols
    alphabetically AMONG THOSE THAT CLEAR THE >=5y FILTER on the full panel,
    plus the benchmark. This keeps the spirit of the instruction (a small,
    deterministic, non-cherry-picked subset) while actually exercising the
    screener logic."""
    df = pd.read_parquet(OHLCV_PATH_IN)
    df = df.sort_values(["Symbol", "Date"]).reset_index(drop=True)

    span = df.groupby("Symbol")["Date"].agg(lambda s: (s.max() - s.min()).days / 365.25)
    eligible = set(span[span >= fst.MIN_YEARS_HISTORY].index)
    print(f"  {len(eligible):,}/{df['Symbol'].nunique():,} symbols clear the >={fst.MIN_YEARS_HISTORY}y "
          f"history filter on the full panel")
    if BENCHMARK_SYMBOL_IN not in eligible:
        bench_span = span.get(BENCHMARK_SYMBOL_IN, float("nan"))
        print(f"  NOTE: {BENCHMARK_SYMBOL_IN} span = {bench_span:.4f}y, below the {fst.MIN_YEARS_HISTORY}y "
              f"filter -- exempted explicitly (benchmark role, not a screened stock; see docstring)")

    keep = eligible | {BENCHMARK_SYMBOL_IN}

    if smoke_test:
        sample = sorted(eligible)[:smoke_n]
        if BENCHMARK_SYMBOL_IN not in sample:
            sample.append(BENCHMARK_SYMBOL_IN)
        keep = keep & set(sample)
        print(f"[SMOKE TEST] restricted to {len(keep)} symbols "
              f"(first {smoke_n} alphabetically among >={fst.MIN_YEARS_HISTORY}y-eligible + {BENCHMARK_SYMBOL_IN})")

    df = df[df["Symbol"].isin(keep)].copy()
    df = fst._flag_split_days(df)
    print(f"OHLCV (India): {df['Symbol'].nunique()} symbols, "
          f"{len(df):,} rows, {df['Date'].min().date()} to {df['Date'].max().date()}")
    if BENCHMARK_SYMBOL_IN not in df["Symbol"].unique():
        raise ValueError(f"{BENCHMARK_SYMBOL_IN} missing from the filtered panel -- cannot benchmark returns")
    return df


def run_technical_screeners(ohlcv: pd.DataFrame) -> pd.DataFrame:
    print("\nComputing technical signals (India)...")
    gc = fst.golden_cross_signals(ohlcv)
    gc["screener"] = "golden_cross"
    dv = fst.darvas_signals(ohlcv)
    dv["screener"] = "darvas"
    nh = fst.new_high_signals(ohlcv)
    nh["screener"] = "new_highs"
    b200 = fst.below_200dma_signals(ohlcv)
    b200["screener"] = "below_200dma"
    rev_w = fst.short_term_reversal_signals(ohlcv, lookback=5)
    rev_w["screener"] = "reversal_weekly"
    rev_m = fst.short_term_reversal_signals(ohlcv, lookback=21)
    rev_m["screener"] = "reversal_monthly"
    lb = fst.low_beta_signals(ohlcv)
    lb["screener"] = "low_beta"

    print(f"  golden_cross: {len(gc):,} signals across {gc['symbol'].nunique():,} symbols")
    print(f"  darvas: {len(dv):,} signals across {dv['symbol'].nunique():,} symbols")
    print(f"  new_highs: {len(nh):,} signals across {nh['symbol'].nunique():,} symbols")
    print(f"  below_200dma: {len(b200):,} signals across {b200['symbol'].nunique():,} symbols")
    print(f"  reversal_weekly: {len(rev_w):,} signals across {rev_w['symbol'].nunique():,} symbols")
    print(f"  reversal_monthly: {len(rev_m):,} signals across {rev_m['symbol'].nunique():,} symbols")
    print(f"  low_beta: {len(lb):,} signals across {lb['symbol'].nunique():,} symbols")

    all_signals = pd.concat(
        [gc[["symbol", "signal_date", "screener"]],
         dv[["symbol", "signal_date", "screener"]],
         nh[["symbol", "signal_date", "screener"]],
         b200[["symbol", "signal_date", "screener"]],
         rev_w[["symbol", "signal_date", "screener"]],
         rev_m[["symbol", "signal_date", "screener"]],
         lb[["symbol", "signal_date", "screener"]]],
        ignore_index=True,
    )
    all_signals["signal_date"] = pd.to_datetime(all_signals["signal_date"])
    all_signals["year"] = all_signals["signal_date"].dt.year

    n_bench_signals = (all_signals["symbol"] == BENCHMARK_SYMBOL_IN).sum()
    all_signals = all_signals[all_signals["symbol"] != BENCHMARK_SYMBOL_IN].reset_index(drop=True)
    print(f"  dropped {n_bench_signals:,} technical-screener signals fired on {BENCHMARK_SYMBOL_IN} itself "
          f"-- it's the benchmark, not a stock under test")
    print(f"\nTotal signals (7 technical screeners): {len(all_signals):,}")
    print(all_signals["screener"].value_counts())
    return all_signals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true",
                         help="Restrict to first 200 symbols (alphabetical) + NIFTYBEES for a fast sanity run")
    parser.add_argument("--smoke-n", type=int, default=200)
    args = parser.parse_args()

    ohlcv = load_ohlcv_in(smoke_test=args.smoke_test, smoke_n=args.smoke_n)
    all_signals = run_technical_screeners(ohlcv)

    print("\nComputing forward returns (reads the full OHLCV panel into memory per symbol)...")
    lookups = fst.forward_returns(ohlcv)
    bench = fst.benchmark_lookup(ohlcv)
    all_signals = fst.attach_forward_returns(all_signals, lookups, bench)

    out_path = SMOKE_OUT_PATH if args.smoke_test else OUT_PATH
    all_signals.to_parquet(out_path, index=False)
    print(f"\nSaved {len(all_signals):,} signal rows -> {out_path}")

    if args.smoke_test:
        print("\n[SMOKE TEST] spot-checking xret_T+252d distribution for absurd values...")
        x = all_signals["xret_T+252d"].dropna()
        if len(x):
            print(f"  n={len(x):,}  min={x.min():+.2f}%  max={x.max():+.2f}%  "
                  f"mean={x.mean():+.2f}%  median={x.median():+.2f}%")
            extreme = all_signals[all_signals["xret_T+252d"].abs() > 1000]
            print(f"  rows with |xret_T+252d| > 1000%: {len(extreme)}")
            if len(extreme):
                print(extreme[["symbol", "screener", "signal_date", "xret_T+252d"]].head(20).to_string(index=False))
        else:
            print("  no non-NaN xret_T+252d values in the smoke sample (expected -- 252 trading days "
                  "~1 calendar year needs signals well before the panel's own end date to resolve)")


if __name__ == "__main__":
    main()
