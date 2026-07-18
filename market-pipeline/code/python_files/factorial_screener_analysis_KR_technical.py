#!/usr/bin/env python3
"""
Factorial ANOVA (regression-based, for unbalanced/non-orthogonal data --
Montgomery "Design and Analysis of Experiments" Ch. 15) on the Korea
TECHNICAL-ONLY screener signals built by factorial_screener_test_KR.py.

Directly adapts factorial_screener_analysis.py's own build_symbol_year_table/
fit_factorial pattern -- same symbol-year unit of analysis (avoids pseudo-
replication from multiple same-year signals of one screener type), same
HC3 robust standard errors, same Benjamini-Hochberg FDR correction across
every effect x horizon tested, same "pairwise interaction only if the cell
has >=30 both-fire symbol-years" rule (Montgomery Ch.8/9's fractional-
design principle), same log_liquidity/volatility_63d controls (both
already computed by _flag_split_days in the SAME parquet this reads).

SCOPE: 7 technical screeners only (golden_cross, darvas, new_highs,
below_200dma, reversal_weekly, reversal_monthly, low_beta) -- no
fundamentals (Piotroski/Coffee Can/etc never computed for Korea in this
task, out of scope per the task's own instruction: Korea PIT fundamentals
were separately audited and found to have a fabricated filing-date field).

BENCHMARK: excess return is over KOSPI (^KS11), not SPY -- xret_T+*d here
was already computed relative to ^KS11 inside factorial_screener_test_KR.py's
attach_forward_returns() call (BENCHMARK_SYMBOL was monkeypatched to
"^KS11" before that ran), so no extra work needed here -- same column
names, different benchmark under the hood.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import false_discovery_control
from itertools import combinations

SIGNALS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_KR_technical.parquet"
SCREENERS = ["golden_cross", "darvas", "new_highs", "below_200dma",
             "reversal_weekly", "reversal_monthly", "low_beta"]
CONTROLS = ["log_liquidity", "volatility_63d"]
HORIZON_LABELS = ["T+5d", "T+21d", "T+63d", "T+126d", "T+252d"]
HORIZONS = [f"xret_{h}" for h in HORIZON_LABELS]        # primary: excess return over KOSPI
RAW_HORIZONS = [f"ret_{h}" for h in HORIZON_LABELS]      # raw return
BENCH_HORIZONS = [f"bench_ret_{h}" for h in HORIZON_LABELS]  # KOSPI's own return, for reporting
MIN_CELL_N = 30


def build_symbol_year_table(signals: pd.DataFrame) -> pd.DataFrame:
    sy = signals.groupby(["symbol", "year", "screener"])[HORIZONS].mean().reset_index()
    wide_factors = sy.pivot_table(index=["symbol", "year"], columns="screener",
                                    values=HORIZONS[0], aggfunc="count").fillna(0)
    wide_factors = (wide_factors > 0).astype(int)
    for s in SCREENERS:
        if s not in wide_factors.columns:
            wide_factors[s] = 0
    wide_factors = wide_factors[SCREENERS]

    rep_returns = signals.groupby(["symbol", "year"])[HORIZONS + RAW_HORIZONS + BENCH_HORIZONS + CONTROLS].mean()
    out = wide_factors.join(rep_returns).reset_index()
    out["n_screeners"] = out[SCREENERS].sum(axis=1)
    return out


def winsorize(s: pd.Series, lower=0.01, upper=0.99) -> pd.Series:
    """Light secondary guard against genuine fat-tailed (non-split, non-
    stale-data) outliers -- the primary defenses (min_price floor,
    _flag_split_days, and the KR-specific stale/halted-data flag in
    factorial_screener_test_KR.py) already excluded the two data-quality
    bugs found in this panel (a delisted-ticker phantom-price artifact and
    the standard split-day case). This is the same convention as
    factorial_screener_analysis.py's own winsorize()."""
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)


def fit_factorial(df: pd.DataFrame, horizon: str, interactions: list[tuple[str, str]]) -> pd.DataFrame:
    y = winsorize(df[horizon])
    valid = y.notna() & df[CONTROLS].notna().all(axis=1)
    X = df.loc[valid, SCREENERS].copy()
    for a, b in interactions:
        X[f"{a}:{b}"] = df.loc[valid, a] * df.loc[valid, b]
    X["log_liquidity"] = df.loc[valid, "log_liquidity"]
    X["volatility_63d"] = df.loc[valid, "volatility_63d"]
    X = sm.add_constant(X)
    model = sm.OLS(y[valid], X).fit(cov_type="HC3")
    res = pd.DataFrame({
        "effect": model.params.index,
        "coef": model.params.values,
        "se": model.bse.values,
        "p": model.pvalues.values,
    })
    res = res[res["effect"] != "const"]
    res["horizon"] = horizon
    res["n"] = valid.sum()
    return res


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    print(f"Loaded {len(signals):,} signal rows, {signals['symbol'].nunique():,} symbols, "
          f"{signals['year'].min()}-{signals['year'].max()}")

    sy = build_symbol_year_table(signals)
    print(f"\nSymbol-year units: {len(sy):,}")

    print("\nBenchmark context (KOSPI / ^KS11, same signal-years, for reference -- "
          "every effect below is tested on EXCESS return over this, not raw return):")
    for hl, raw, bench, xr in zip(HORIZON_LABELS, RAW_HORIZONS, BENCH_HORIZONS, HORIZONS):
        print(f"  {hl}: mean stock {sy[raw].mean():+.2f}%  mean KOSPI {sy[bench].mean():+.2f}%  "
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
    print("FACTORIAL REGRESSION RESULTS -- KOREA, TECHNICAL SCREENERS ONLY (main effects = %-point")
    print("return vs a symbol-year with that screener NOT firing, holding others fixed;")
    print("interactions = extra lift beyond additive)")
    print("=" * 100)
    for h in HORIZONS:
        sub = all_results[all_results["horizon"] == h].copy()
        sub["sig_fdr"] = sub["p_fdr"] < 0.05
        print(f"\n--- {h} (n={sub['n'].iloc[0]}) ---")
        print(sub[["effect", "coef", "se", "p", "p_fdr", "sig_fdr"]].to_string(index=False))

    all_results.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_regression_results_KR_technical.csv", index=False)
    sy.to_parquet("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_symbol_year_table_KR_technical.parquet", index=False)
    print("\nSaved results -> cache_seed/factorial_regression_results_KR_technical.csv")


if __name__ == "__main__":
    main()
