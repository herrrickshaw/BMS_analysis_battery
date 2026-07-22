#!/usr/bin/env python3
"""
India FULL (technical + fundamental) factorial regression -- same OLS/HC3/
BH-FDR machinery as factorial_screener_analysis.py (US), applied to the 34
screeners (7 technical + 27 fundamental) run on India by
factorial_screener_test_IN_full.py.

Reuses build_symbol_year_table(), fit_factorial(), and winsorize() VERBATIM
via monkeypatching factorial_screener_analysis.py's module-level SCREENERS
global -- same convention as factorial_screener_analysis_JP_technical.py.

CAVEAT, STATED UP FRONT: several fundamental screeners have very few
signals in India (magic_formula=1, ev_ebitda_value=1, roce_plus=3,
small_cap_growth=5, capacity_expansion=8, piotroski=17) -- this reflects
genuinely thin India fundamentals history (yfinance's quarterly coverage
for many mid/small-caps is shorter than the 10-year OHLCV window, and only
1,401/1,776 tickers have a full balance sheet at all after this session's
multi-source merge). Read any main-effect coefficient for these screeners
as "insufficient data to conclude anything," not as a weak-but-real signal
-- the regression will still run and print a number, but that number is
not comparable in reliability to a well-populated screener like
net_debt_ebitda (2,814 signals) or reversal_weekly (150,674 signals).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import false_discovery_control
from itertools import combinations

import factorial_screener_analysis as fsa

SIGNALS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_IN_full.parquet"
SCREENERS = [
    # technical (7)
    "golden_cross", "darvas", "new_highs", "below_200dma",
    "reversal_weekly", "reversal_monthly", "low_beta",
    # fundamental (27, as of the original build)
    "piotroski", "coffee_can", "magic_formula", "bull_cartel",
    "roce_plus", "sloan_quality", "not_distress",
    "capacity_expansion", "growth_stocks", "graham_10y", "small_cap_growth",
    "pead_positive_surprise", "debt_reduction",
    "net_margin", "operating_margin", "pb_value", "ps_value",
    "ev_ebitda_value", "peg_value", "fcf_yield",
    "eps_growth", "roic_value", "fcf_margin", "net_debt_ebitda", "ev_sales",
    "low_asset_growth", "buyback_yield",
    # added 2026-07-18/19 (Bucket B + this analysis's own request)
    "pe_value", "quick_ratio",
    "operating_profit_growth", "debt_reduction_and_opgrowth",
]
CONTROLS = fsa.CONTROLS
HORIZON_LABELS = ["T+63d", "T+252d"]
HORIZONS = [f"xret_{h}" for h in HORIZON_LABELS]
RAW_HORIZONS = [f"ret_{h}" for h in HORIZON_LABELS]
BENCH_HORIZONS = [f"bench_ret_{h}" for h in HORIZON_LABELS]
MIN_CELL_N = fsa.MIN_CELL_N

fsa.SCREENERS = SCREENERS
fsa.HORIZONS = HORIZONS
fsa.RAW_HORIZONS = RAW_HORIZONS
fsa.BENCH_HORIZONS = BENCH_HORIZONS
fsa.CONTROLS = CONTROLS

build_symbol_year_table = fsa.build_symbol_year_table
winsorize = fsa.winsorize
fit_factorial = fsa.fit_factorial


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    print(f"Loaded {len(signals):,} signal rows, {signals['symbol'].nunique():,} symbols, "
          f"{signals['year'].min()}-{signals['year'].max()}")

    sy = build_symbol_year_table(signals)
    print(f"\nSymbol-year units: {len(sy):,}")

    print("\nBenchmark context (NIFTYBEES / Nifty 50 proxy, same signal-years, for reference -- "
          "every effect below is tested on EXCESS return over this, not raw return):")
    for hl, raw, bench, xr in zip(HORIZON_LABELS, RAW_HORIZONS, BENCH_HORIZONS, HORIZONS):
        print(f"  {hl}: mean stock {sy[raw].mean():+.2f}%  mean NIFTYBEES {sy[bench].mean():+.2f}%  "
              f"mean excess {sy[xr].mean():+.2f}%")

    print("\nDistribution of n_screeners firing per symbol-year:")
    print(sy["n_screeners"].value_counts().sort_index())

    print("\nPer-screener symbol-year incidence:")
    print(sy[SCREENERS].sum().sort_values(ascending=False))

    testable_interactions = []
    for a, b in combinations(SCREENERS, 2):
        n11 = ((sy[a] == 1) & (sy[b] == 1)).sum()
        if n11 >= MIN_CELL_N:
            testable_interactions.append((a, b))
    print(f"\nTestable pairwise interactions (n>={MIN_CELL_N} both-fire cases): {len(testable_interactions)}")

    all_results = []
    for h in HORIZONS:
        res = fit_factorial(sy, h, testable_interactions)
        all_results.append(res)
    all_results = pd.concat(all_results, ignore_index=True)

    is_control = all_results["effect"].isin(CONTROLS)
    all_results["p_fdr"] = np.nan
    all_results.loc[~is_control, "p_fdr"] = false_discovery_control(
        all_results.loc[~is_control, "p"].values, method="bh")
    all_results = all_results.sort_values(["horizon", "p_fdr"])

    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", None)
    print("\n" + "=" * 100)
    print("INDIA FULL (TECHNICAL + FUNDAMENTAL) FACTORIAL REGRESSION RESULTS")
    print("=" * 100)
    for h in HORIZONS:
        sub = all_results[all_results["horizon"] == h].copy()
        sub["sig_fdr"] = sub["p_fdr"] < 0.05
        # main effects only, sorted by significance, for a quick read --
        # full table (incl. interactions) still saved to CSV below
        main_only = sub[sub["effect"].isin(SCREENERS)]
        print(f"\n--- {h} main effects (n={sub['n'].iloc[0]}) ---")
        print(main_only[["effect", "coef", "se", "p", "p_fdr", "sig_fdr"]].to_string(index=False))

    all_results.to_csv(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_regression_results_IN_full.csv",
        index=False)
    sy.to_parquet(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_symbol_year_table_IN_full.parquet",
        index=False)
    print("\nSaved results -> cache_seed/factorial_regression_results_IN_full.csv")


if __name__ == "__main__":
    main()
