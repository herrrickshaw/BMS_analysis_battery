#!/usr/bin/env python3
"""
India FULL (technical + fundamental) screener test -- extends
factorial_screener_test_IN.py (technical-only, 7 screeners) now that a
genuine balance-sheet-bearing India fundamentals panel exists.

WHY THIS SCRIPT EXISTS NOW, WHEN IT DIDN'T BEFORE: every prior India pass
this session was deliberately technical-only, because both existing India
fundamentals sources (screener.in's IN.parquet, NSE's results-comparison
API) lacked a real balance sheet entirely -- no total_assets, current_assets/
liabilities, long_term_debt, or retained_earnings in either, which meant
current_ratio, every solvency ratio, and the Altman Z-score could not be
computed for India at all, regardless of any collector's block status. This
session built collect_yfinance_pit_fundamentals.py + merge_india_
fundamentals.py to fix that: cache_seed/fundamentals_history/IN.parquet is
now a merged, source-tagged file with 1,401/1,776 tickers carrying a full
balance sheet (primarily from yfinance, cross-referenced against NSE's own
filing dates where both exist). See SCREENER_RESEARCH_DATA_SOURCES.md and
RATIO_DEFINITIONS_CFA.md for the full provenance and formula citations.

REUSE, NOT REIMPLEMENTATION: compute_fundamental_screens(), attach_market_
cap(), build_fundamental_signal_dates(), and every technical screener
function are imported and called VERBATIM from factorial_screener_test.py
-- the same discipline factorial_screener_test_IN.py already established.
The technical-screener wiring (OHLCV loading, benchmark, min_price
reasoning) is reused directly from that file via import, not copied.

THE ONE REAL INDIA-SPECIFIC FIX NEEDED: attach_market_cap() has three
absolute (not ratio) market-cap thresholds hardcoded in USD terms --
coffee_can's mcap>=$1e9, magic_formula's mcap>$5e7, small_cap_growth's
mcap<$2e9. Every OTHER ratio in this codebase (P/B, P/S, EV/EBITDA, PEG,
ROE, D/E, ...) is scale-invariant -- mcap and equity/revenue/net_income are
both in the filing's native currency, so the ratio comes out right
regardless of whether that currency is USD or INR. Only these three
ABSOLUTE thresholds break, because they compare an INR-denominated mcap
against a USD-calibrated literal. Fixed below by recomputing just these
three pass columns using a fixed ~83 INR/USD conversion (a deliberate
approximation -- not a historical daily rate -- documented, not hidden;
see INR_PER_USD below) applied to the same literals attach_market_cap()
already uses internally, using the underlying ratio columns (rev_growth,
de_ratio, roe, roic, earnings_yield) that remain accessible on the merged
frame after attach_market_cap() returns, rather than touching that
function's US-tested internals at all.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
import factorial_screener_test as fst  # noqa: E402  -- reused verbatim, not reimplemented
import factorial_screener_test_IN as fst_in  # noqa: E402  -- reuse its OHLCV loader + technical wiring

FUND_PATH_IN = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/IN.parquet"
BACKUP_PATH_IN = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/IN_screener_only_backup.parquet"
OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_IN_full.parquet"
SMOKE_OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_IN_full_SMOKETEST.parquet"

fst.FUND_PATH = FUND_PATH_IN  # module-level monkeypatch, read by load_fundamentals() at call time

INR_PER_USD = 83.0  # fixed approximation, not a historical daily rate -- stated, not hidden
MCAP_COFFEE_CAN_INR = 1e9 * INR_PER_USD
MCAP_MAGIC_FORMULA_INR = 5e7 * INR_PER_USD
MCAP_SMALL_CAP_GROWTH_INR = 2e9 * INR_PER_USD


def fix_currency_scaled_thresholds(merged: pd.DataFrame) -> pd.DataFrame:
    """Recompute the three USD-literal-dependent pass columns using INR-scaled
    thresholds and the underlying ratio columns, which attach_market_cap()
    leaves untouched on `merged`. Does not modify attach_market_cap() itself."""
    merged = merged.copy()
    merged["coffee_can_pass"] = (
        merged["coffee_can_pass"].astype(bool) & (merged["mcap"] >= MCAP_COFFEE_CAN_INR)
    ).astype(int)
    # attach_market_cap() already ANDed a too-low (wrong) USD-literal mcap
    # gate into coffee_can_pass -- but 1e9 (wrong) < 8.3e10 (correct), so the
    # wrong gate is a SUPERSET (never excludes anything the right gate
    # would also exclude); re-ANDing with the correct, higher INR threshold
    # is sufficient and doesn't need the pre-gate ratio conditions back.
    merged["magic_formula_pass"] = (
        (merged["roic"] > 0.25) & (merged["earnings_yield"] > 0.15)
        & (merged["mcap"] > MCAP_MAGIC_FORMULA_INR)
    ).astype(int)
    merged["small_cap_growth_pass"] = (
        (merged["mcap"] < MCAP_SMALL_CAP_GROWTH_INR) & (merged["rev_growth"] > 0.15)
        & (merged["de_ratio"] < 0.5) & (merged["roe"] > 0.15)
    ).astype(int)
    # small_cap_growth's wrong (2e9 INR, ~$24M) upper bound was TOO
    # restrictive, not too permissive -- almost no real company has mcap
    # below that in INR terms, so the wrong version couldn't be salvaged by
    # re-ANDing (that would keep it near-empty); recomputed fully from the
    # underlying ratio columns instead, which is why they're referenced here.
    return merged


def merge_backup_fields(fund: pd.DataFrame) -> pd.DataFrame:
    """Merge in receivables/inventory/industry/cogs from IN_screener_only_
    backup.parquet -- collected earlier this session but never merged into
    the main IN.parquet panel (confirmed via 2026-07-18 gap analysis: these
    three columns don't exist in IN.parquet at all). Left-merge on (ticker,
    fy_end); coverage is PARTIAL (receivables 2,660/3,054 rows, inventory
    2,363/3,054 in the backup file itself, and only 2,859/3,054 backup rows
    have a matching (ticker, fy_end) in the main panel) -- missing stays
    NaN, not fabricated, same convention as every other field in this file.

    2026-07-19: backup file refreshed with a full re-collection that adds
    dividend_amount (48.5% populated -- non-payers legitimately NaN, not
    missing) and promoter/FII/DII/public_holding + num_shareholders (~27-30%
    overall, but 93.6% for fy_end>=2024 specifically -- screener.in only
    exposes a trailing ~3-year shareholding window, so older fiscal years
    are structurally unreachable, not a collection gap; see
    screener_history_collector.py's module docstring)."""
    backup = pd.read_parquet(BACKUP_PATH_IN)[
        ["ticker", "fy_end", "receivables", "inventory", "industry", "cogs",
         "dividend_amount", "promoter_holding", "fii_holding", "dii_holding",
         "public_holding", "num_shareholders"]
    ]
    backup["fy_end"] = pd.to_datetime(backup["fy_end"])
    return fund.merge(backup, on=["ticker", "fy_end"], how="left")


def add_working_capital_ratios(fund_scored: pd.DataFrame) -> pd.DataFrame:
    """Quick ratio, inventory turnover (+ N-years-back), debtor days (+
    N-years-back) -- unlocked by merge_backup_fields()'s receivables/
    inventory/cogs columns. India-only: the backup file this depends on
    has no US equivalent, so this stays local rather than going into the
    shared compute_fundamental_screens()/attach_market_cap() -- same
    "don't touch US-tested internals" discipline as
    fix_currency_scaled_thresholds() above.

    quick_ratio_pass uses >1.0, the standard textbook liquidity threshold
    (same convention level as current_ratio elsewhere in this pipeline).
    inventory_turnover and debtor_days are exposed as VALUES only, no
    _pass threshold -- unlike quick ratio, a single universal cutoff for
    either isn't a textbook convention (both are industry-dependent), so
    inventing one here would be an ungrounded threshold, not a reused one."""
    df = fund_scored.sort_values(["ticker", "fy_end"]).copy()
    g = df.groupby("ticker")
    df["quick_ratio"] = (df["current_assets"] - df["inventory"]) / df["current_liabilities"]
    df["quick_ratio_pass"] = (df["quick_ratio"] > 1.0).astype(int)
    df["inventory_turnover"] = df["cogs"] / df["inventory"]
    for _n in (3, 5, 7, 10):
        df[f"inventory_turnover_{_n}y_back"] = g["inventory_turnover"].shift(_n)
    df["debtor_days"] = df["receivables"] / df["revenue"] * 365
    for _n in (3, 5):
        df[f"debtor_days_{_n}y_back"] = g["debtor_days"].shift(_n)
    return df


def run_fundamental_screeners(fund: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
    print("\nComputing fundamental signals (India)...")
    fund = merge_backup_fields(fund)
    fund_scored = fst.compute_fundamental_screens(fund)
    fund_scored = fst.attach_market_cap(fund_scored, ohlcv)
    fund_scored = fix_currency_scaled_thresholds(fund_scored)
    fund_scored = add_working_capital_ratios(fund_scored)
    fund_sig = fst.build_fundamental_signal_dates(fund_scored)

    cols = ["piotroski_pass", "coffee_can_pass", "magic_formula_pass", "bull_cartel_pass",
            "roce_plus_pass", "sloan_pass", "not_distress",
            "capacity_expansion_pass", "growth_stocks_pass", "graham_10y_pass", "small_cap_growth_pass",
            "pead_positive_surprise_pass", "debt_reduction_pass",
            "net_margin_pass", "operating_margin_pass", "pb_pass", "ps_pass",
            "ev_ebitda_pass", "peg_pass", "fcf_yield_pass",
            "eps_growth_pass", "roic_pass", "fcf_margin_pass", "net_debt_ebitda_pass", "ev_sales_pass",
            "low_asset_growth_pass", "buyback_yield_pass", "pe_pass"]
    for c in cols:
        print(f"  {c}: {fund_sig[c].sum():,} filing-level passes")
    # quick_ratio_pass isn't in build_fundamental_signal_dates()'s shared,
    # US-facing cols list (it depends on the India-only backup merge above)
    # -- reported and melted separately, straight off fund_scored.
    print(f"  quick_ratio_pass: {fund_scored['quick_ratio_pass'].sum():,} filing-level passes")

    fund_long = []
    for c, name in [("piotroski_pass", "piotroski"), ("coffee_can_pass", "coffee_can"),
                     ("magic_formula_pass", "magic_formula"), ("bull_cartel_pass", "bull_cartel"),
                     ("roce_plus_pass", "roce_plus"), ("sloan_pass", "sloan_quality"),
                     ("not_distress", "not_distress"),
                     ("capacity_expansion_pass", "capacity_expansion"),
                     ("growth_stocks_pass", "growth_stocks"),
                     ("graham_10y_pass", "graham_10y"),
                     ("small_cap_growth_pass", "small_cap_growth"),
                     ("pead_positive_surprise_pass", "pead_positive_surprise"),
                     ("debt_reduction_pass", "debt_reduction"),
                     ("net_margin_pass", "net_margin"),
                     ("operating_margin_pass", "operating_margin"),
                     ("pb_pass", "pb_value"),
                     ("ps_pass", "ps_value"),
                     ("ev_ebitda_pass", "ev_ebitda_value"),
                     ("peg_pass", "peg_value"),
                     ("fcf_yield_pass", "fcf_yield"),
                     ("eps_growth_pass", "eps_growth"),
                     ("roic_pass", "roic_value"),
                     ("fcf_margin_pass", "fcf_margin"),
                     ("net_debt_ebitda_pass", "net_debt_ebitda"),
                     ("ev_sales_pass", "ev_sales"),
                     ("low_asset_growth_pass", "low_asset_growth"),
                     ("buyback_yield_pass", "buyback_yield"),
                     ("pe_pass", "pe_value")]:
        sub = fund_sig[fund_sig[c] == 1][["symbol", "signal_date"]].copy()
        sub["screener"] = name
        fund_long.append(sub)

    quick_sub = fund_scored.dropna(subset=["filed"])
    quick_sub = quick_sub[quick_sub["quick_ratio_pass"] == 1][["ticker", "filed"]].rename(
        columns={"ticker": "symbol", "filed": "signal_date"}
    )
    quick_sub["screener"] = "quick_ratio"
    fund_long.append(quick_sub)

    fund_long = pd.concat(fund_long, ignore_index=True)
    fund_long["signal_date"] = pd.to_datetime(fund_long["signal_date"])
    fund_long["year"] = fund_long["signal_date"].dt.year
    return fund_long


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--smoke-n", type=int, default=200)
    args = parser.parse_args()

    ohlcv = fst_in.load_ohlcv_in(smoke_test=args.smoke_test, smoke_n=args.smoke_n)
    tech_signals = fst_in.run_technical_screeners(ohlcv)

    fund = fst.load_fundamentals()
    fund_signals = run_fundamental_screeners(fund, ohlcv)

    all_signals = pd.concat([tech_signals, fund_signals], ignore_index=True)
    print(f"\nTotal signals (7 technical + 29 fundamental screeners): {len(all_signals):,}")
    print(all_signals["screener"].value_counts())

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
            print("  no non-NaN xret_T+252d values in the smoke sample")


if __name__ == "__main__":
    main()
