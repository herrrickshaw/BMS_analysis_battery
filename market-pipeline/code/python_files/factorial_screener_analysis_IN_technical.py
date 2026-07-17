#!/usr/bin/env python3
"""
India technical-screener-only factorial regression + year-by-year
consistency pass, mirroring factorial_screener_analysis.py and
year_by_year_consistency.py's own logic exactly, adapted for:
  - 7 technical screeners only (golden_cross, darvas, new_highs,
    below_200dma, reversal_weekly, reversal_monthly, low_beta) -- no
    fundamentals, per factorial_screener_test_IN.py's scope decision.
  - Signal panel = cache_seed/factorial_screener_signals_IN_technical.parquet
    (built by factorial_screener_test_IN.py), NOT the US parquet.
  - Benchmark = NIFTYBEES (Nifty 50 ETF), not SPY. Per factorial_screener_
    test_IN.py's own documented limitation: NIFTYBEES's price history starts
    2021-07-02, while the OHLCV panel goes back to 2016-06-27 -- so any
    signal dated before mid-2021 has xret_* == NaN (no benchmark price to
    diff against). This shows up here as fewer usable symbol-years in the
    early part of the panel and is NOT worked around; symbol-years with NaN
    xret_T+63d/T+252d are simply excluded from their respective regressions
    by `valid = y.notna() & ...`, exactly as the US script already handles
    any other missing-return case.

Regression scope: only xret_T+63d and xret_T+252d are tested here (per this
task's own instruction), not the full 5-horizon HORIZONS list the US script
tests -- everything else (HC3 robust SEs, BH FDR correction across the
screener-effect family only, winsorize() as a secondary guard on top of the
already-split-excluded panel, MIN_CELL_N=30 pairwise-interaction gate,
log_liquidity/volatility_63d controls) is IDENTICAL to factorial_screener_
analysis.py's own convention, reused rather than reinvented.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import false_discovery_control
from itertools import combinations

SIGNALS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_IN_technical.parquet"
BENCHMARK_SYMBOL = "NIFTYBEES"

SCREENERS = ["golden_cross", "darvas", "new_highs", "below_200dma",
             "reversal_weekly", "reversal_monthly", "low_beta"]
CONTROLS = ["log_liquidity", "volatility_63d"]

# Only these two horizons are regressed, per task scope (the parquet itself
# carries all 5 -- T+5d/21d/63d/126d/252d -- computed by factorial_screener_
# test_IN.py's attach_forward_returns call, same machinery as the US script).
HORIZON_LABELS = ["T+63d", "T+252d"]
HORIZONS = [f"xret_{h}" for h in HORIZON_LABELS]
RAW_HORIZONS = [f"ret_{h}" for h in HORIZON_LABELS]
BENCH_HORIZONS = [f"bench_ret_{h}" for h in HORIZON_LABELS]
MIN_CELL_N = 30

# --- year-by-year consistency pass constants (matches year_by_year_consistency.py) ---
MIN_SIGNALS_PER_YEAR = 15
MIN_YEARS = 4


def build_symbol_year_table(signals: pd.DataFrame) -> pd.DataFrame:
    """Identical approach to factorial_screener_analysis.build_symbol_year_table:
    one row per (symbol, year), screener dummies as 0/1 columns, representative
    (mean) return columns, avoiding pseudo-replication from multiple same-year
    signals of one screener type."""
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
    """Same secondary guard as factorial_screener_analysis.py: the underlying
    panel already EXCLUDES (not winsorizes) split-day-crossing windows via
    _flag_split_days/attach_forward_returns, but this still caps genuine
    fat-tailed (non-split) outliers -- e.g. ADANIGREEN/ASAL's real
    multi-hundred-percent 1-year rallies confirmed during the smoke test,
    which are real prices, not data artifacts, but are extreme enough to
    dominate an unweighted OLS coefficient if left uncapped."""
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


def year_by_year_consistency(sy: pd.DataFrame) -> pd.DataFrame:
    """Exact port of year_by_year_consistency.py's logic: per screener, per
    calendar year, mean excess return at T+63d/T+252d (winsorized), gated by
    MIN_SIGNALS_PER_YEAR; consistency = hit rate = fraction of qualifying
    years with positive mean excess return; MIN_YEARS gates out screeners
    with too few years of adequate signal volume to say anything at all."""
    rows = []
    for s in SCREENERS:
        active = sy[sy[s] == 1]
        yearly = []
        for yr, grp in active.groupby("year"):
            if len(grp) < MIN_SIGNALS_PER_YEAR:
                continue
            x63 = winsorize(grp["xret_T+63d"]).mean()
            x252 = winsorize(grp["xret_T+252d"]).mean()
            yearly.append({"year": yr, "n": len(grp), "mean_excess_63d": x63, "mean_excess_252d": x252})
        if len(yearly) < MIN_YEARS:
            continue
        yr_df = pd.DataFrame(yearly)
        hit_rate_63 = (yr_df["mean_excess_63d"] > 0).mean() * 100
        hit_rate_252 = (yr_df["mean_excess_252d"] > 0).mean() * 100
        rows.append({
            "screener": s, "n_years": len(yr_df),
            "hit_rate_years_63d": hit_rate_63, "hit_rate_years_252d": hit_rate_252,
            "avg_excess_63d": yr_df["mean_excess_63d"].mean(),
            "avg_excess_252d": yr_df["mean_excess_252d"].mean(),
            "worst_year_252d": yr_df["mean_excess_252d"].min(),
            "best_year_252d": yr_df["mean_excess_252d"].max(),
        })
    return pd.DataFrame(rows).sort_values("hit_rate_years_252d", ascending=False)


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    print(f"Loaded {len(signals):,} signal rows, {signals['symbol'].nunique():,} symbols, "
          f"{signals['year'].min()}-{signals['year'].max()}")
    n_nan_xret = signals["xret_T+252d"].isna().sum()
    print(f"NOTE: {n_nan_xret:,}/{len(signals):,} rows have NaN xret_T+252d -- includes signals dated before "
          f"{BENCHMARK_SYMBOL}'s 2021-07-02 history start (no benchmark price available) as well as windows "
          f"too close to the panel's end date (2026-07-02) to have a resolved T+252d exit, and any split-day-"
          f"crossing exclusions. This is the real limitation documented in factorial_screener_test_IN.py, not "
          f"silently patched over.")

    sy = build_symbol_year_table(signals)
    print(f"\nSymbol-year units: {len(sy):,}")

    print(f"\nBenchmark context ({BENCHMARK_SYMBOL} / Nifty 50, same signal-years, for reference -- "
          "every effect below is tested on EXCESS return over this, not raw return):")
    for hl, raw, bench, xr in zip(HORIZON_LABELS, RAW_HORIZONS, BENCH_HORIZONS, HORIZONS):
        n_valid = sy[xr].notna().sum()
        print(f"  {hl}: mean stock {sy[raw].mean():+.2f}%  mean {BENCHMARK_SYMBOL} {sy[bench].mean():+.2f}%  "
              f"mean excess {sy[xr].mean():+.2f}%  (n valid = {n_valid:,}/{len(sy):,})")

    print("\nDistribution of n_screeners firing per symbol-year:")
    print(sy["n_screeners"].value_counts().sort_index())

    print("\nPer-screener symbol-year incidence:")
    print(sy[SCREENERS].sum())

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
    print("FACTORIAL REGRESSION RESULTS -- India, technical screeners only (main effects = %-point return")
    print("vs a symbol-year with that screener NOT firing, holding others fixed; interactions = extra lift")
    print("beyond additive)")
    print("=" * 100)
    for h in HORIZONS:
        sub = all_results[all_results["horizon"] == h].copy()
        sub["sig_fdr"] = sub["p_fdr"] < 0.05
        print(f"\n--- {h} (n={sub['n'].iloc[0]}) ---")
        print(sub[["effect", "coef", "se", "p", "p_fdr", "sig_fdr"]].to_string(index=False))

    all_results.to_csv(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_regression_results_IN_technical.csv",
        index=False)
    sy.to_parquet(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_symbol_year_table_IN_technical.parquet",
        index=False)
    print("\nSaved regression results -> cache_seed/factorial_regression_results_IN_technical.csv")

    print("\n" + "=" * 100)
    print("SCREENER CONSISTENCY ACROSS YEARS (excess return over NIFTYBEES, T+63d and T+252d)")
    print("=" * 100)
    consistency = year_by_year_consistency(sy)
    print(consistency.round(2).to_string(index=False) if not consistency.empty else "  no screener met MIN_YEARS")

    print(f"\nCONSISTENT screeners (hit rate >= 70% of years at T+252d, >= {MIN_YEARS} years of data):")
    consistent = consistency[consistency["hit_rate_years_252d"] >= 70] if not consistency.empty else consistency
    print(consistent["screener"].tolist() if len(consistent) else "  none met the bar")

    consistency.to_csv(
        "/Users/umashankar/market-pipeline/code/python_files/cache_seed/screener_consistency_IN_technical.csv",
        index=False)
    print("\nSaved consistency results -> cache_seed/screener_consistency_IN_technical.csv")


if __name__ == "__main__":
    main()
