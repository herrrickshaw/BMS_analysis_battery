#!/usr/bin/env python3
"""
Japan technical-only factorial regression -- same OLS/HC3/BH-FDR machinery
as factorial_screener_analysis.py (US), applied to the 7 market-agnostic
technical screeners run on Japan by factorial_screener_test_JP.py.

Reuses factorial_screener_analysis.py's build_symbol_year_table(),
fit_factorial(), and winsorize() VERBATIM via monkeypatching its module-
level SCREENERS global to the 7 JP technical screener names -- both
functions read SCREENERS as a global at call time (not a parameter), so
patching it here is enough to retarget the whole symbol-year construction
and regression at Japan's screener set without touching
factorial_screener_analysis.py at all (same monkeypatch convention as
factorial_screener_test_JP.py's fst.BENCHMARK_SYMBOL patch). CONTROLS
(log_liquidity, volatility_63d), HORIZON_LABELS/HORIZONS/RAW_HORIZONS/
BENCH_HORIZONS, and MIN_CELL_N are left untouched -- they're already
market-agnostic (column-name conventions, not US-specific content).

SCOPE: only xret_T+63d and xret_T+252d are regressed here (not all 5
horizons) -- the two horizons the task asked for (~1 quarter, ~1 year),
matching year_by_year_consistency.py's own choice of primary horizons.

TECHNICAL-ONLY: no fundamentals screeners exist in the JP signals panel
(factorial_screener_test_JP.py never computed them -- see that script's
docstring on why: 2021-2026-only JP fundamentals coverage, plus this
account's separate audit finding the point-in-time filing-date field
fabricated). SCREENERS below is exactly the 7 technical factors, no more.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import false_discovery_control
from itertools import combinations

import factorial_screener_analysis as fsa

SIGNALS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_JP_technical.parquet"
SCREENERS = ["golden_cross", "darvas", "new_highs", "below_200dma",
             "reversal_weekly", "reversal_monthly", "low_beta"]
CONTROLS = fsa.CONTROLS  # ["log_liquidity", "volatility_63d"] -- unchanged, market-agnostic
HORIZON_LABELS = ["T+63d", "T+252d"]  # the two horizons this task asks for
HORIZONS = [f"xret_{h}" for h in HORIZON_LABELS]
RAW_HORIZONS = [f"ret_{h}" for h in HORIZON_LABELS]
BENCH_HORIZONS = [f"bench_ret_{h}" for h in HORIZON_LABELS]
MIN_CELL_N = fsa.MIN_CELL_N  # 30, same convention as US

# --- monkeypatch fsa's globals so its build_symbol_year_table/fit_factorial
# (which read SCREENERS/HORIZONS/CONTROLS as module globals, not parameters)
# operate on Japan's 7-screener technical panel instead of the US 33-screener one
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

    print("\nBenchmark context (Nikkei 225 / ^N225, same signal-years, for reference -- "
          "every effect below is tested on EXCESS return over this, not raw return):")
    for hl, raw, bench, xr in zip(HORIZON_LABELS, RAW_HORIZONS, BENCH_HORIZONS, HORIZONS):
        print(f"  {hl}: mean stock {sy[raw].mean():+.2f}%  mean ^N225 {sy[bench].mean():+.2f}%  "
              f"mean excess {sy[xr].mean():+.2f}%")

    print("\nDistribution of n_screeners firing per symbol-year:")
    print(sy["n_screeners"].value_counts().sort_index())

    print("\nPer-screener symbol-year incidence:")
    print(sy[SCREENERS].sum())

    # --- Determine which pairwise interactions have enough support ------------
    testable_interactions = []
    for a, b in combinations(SCREENERS, 2):
        n11 = ((sy[a] == 1) & (sy[b] == 1)).sum()
        if n11 >= MIN_CELL_N:
            testable_interactions.append((a, b))
    print(f"\nTestable pairwise interactions (n>={MIN_CELL_N} both-fire cases): {len(testable_interactions)}")
    for a, b in testable_interactions:
        n11 = ((sy[a] == 1) & (sy[b] == 1)).sum()
        print(f"  {a} x {b}: n={n11}")

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
    print("JAPAN TECHNICAL-ONLY FACTORIAL REGRESSION RESULTS (main effects = %-point excess return vs a")
    print("symbol-year with that screener NOT firing, holding others fixed; interactions = extra lift beyond additive)")
    print("=" * 100)
    for h in HORIZONS:
        sub = all_results[all_results["horizon"] == h].copy()
        sub["sig_fdr"] = sub["p_fdr"] < 0.05
        print(f"\n--- {h} (n={sub['n'].iloc[0]}) ---")
        print(sub[["effect", "coef", "se", "p", "p_fdr", "sig_fdr"]].to_string(index=False))

    all_results.to_csv(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_regression_results_JP_technical.csv",
        index=False)
    sy.to_parquet(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_symbol_year_table_JP_technical.parquet",
        index=False)
    print("\nSaved results -> cache_seed/factorial_regression_results_JP_technical.csv")


if __name__ == "__main__":
    main()
