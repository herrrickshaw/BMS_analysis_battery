#!/usr/bin/env python3
"""
China A-share TECHNICAL-ONLY factorial regression + year-by-year
consistency pass, on the signal panel built by
factorial_screener_test_CN.py.

Adapted directly from factorial_screener_analysis.py (OLS/HC3/BH-FDR
factorial regression logic) and year_by_year_consistency.py (hit-rate
consistency logic) -- SAME methodology, restricted to the 7 technical
screeners this CN panel actually has (no fundamentals -- CN's
point-in-time filing-date field was separately found fabricated, out of
scope here) and to xret_T+63d / xret_T+252d only (the two horizons this
task asks for), rather than all 5.

OBSERVATIONAL data, not a randomized experiment: reported as descriptive/
correlational, no causal claim. Pairwise interactions only fit where the
cell has >=30 symbol-years both firing (same Montgomery Ch.8/9
fractional-design principle as the US script: don't estimate an effect
the data can't support).
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import false_discovery_control

SIGNALS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_CN_technical.parquet"
SCREENERS = ["golden_cross", "darvas", "new_highs", "below_200dma",
             "reversal_weekly", "reversal_monthly", "low_beta"]
CONTROLS = ["log_liquidity", "volatility_63d"]
HORIZON_LABELS_ALL = ["T+5d", "T+21d", "T+63d", "T+126d", "T+252d"]
HORIZONS_ALL = [f"xret_{h}" for h in HORIZON_LABELS_ALL]
RAW_HORIZONS_ALL = [f"ret_{h}" for h in HORIZON_LABELS_ALL]
BENCH_HORIZONS_ALL = [f"bench_ret_{h}" for h in HORIZON_LABELS_ALL]

# This task asks specifically for T+63d and T+252d in the OLS stage.
OLS_HORIZON_LABELS = ["T+63d", "T+252d"]
OLS_HORIZONS = [f"xret_{h}" for h in OLS_HORIZON_LABELS]

MIN_CELL_N = 30
MIN_SIGNALS_PER_YEAR = 15
MIN_YEARS = 4


def build_symbol_year_table(signals: pd.DataFrame) -> pd.DataFrame:
    """Same construction as factorial_screener_analysis.py's own function:
    one row per (symbol, year), 0/1 dummy per screener (fired at least
    once that symbol-year), mean forward returns across all
    same-symbol-year signals (avoids pseudo-replication)."""
    sy = signals.groupby(["symbol", "year", "screener"])[HORIZONS_ALL].mean().reset_index()
    wide_factors = sy.pivot_table(index=["symbol", "year"], columns="screener",
                                    values=HORIZONS_ALL[0], aggfunc="count").fillna(0)
    wide_factors = (wide_factors > 0).astype(int)
    for s in SCREENERS:
        if s not in wide_factors.columns:
            wide_factors[s] = 0
    wide_factors = wide_factors[SCREENERS]

    rep_returns = signals.groupby(["symbol", "year"])[HORIZONS_ALL + RAW_HORIZONS_ALL + BENCH_HORIZONS_ALL + CONTROLS].mean()
    out = wide_factors.join(rep_returns).reset_index()
    out["n_screeners"] = out[SCREENERS].sum(axis=1)
    return out


def winsorize(s: pd.Series, lower=0.01, upper=0.99) -> pd.Series:
    """Same light secondary guard as factorial_screener_analysis.py --
    the primary defense against split/limit-run contamination is the
    exclude-not-winsorize logic already applied in
    factorial_screener_test_CN.py / factorial_screener_test.py's
    attach_forward_returns(); this just caps genuine fat-tailed
    (non-split) outliers before they dominate an OLS coefficient."""
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


def year_by_year_consistency(signals: pd.DataFrame) -> pd.DataFrame:
    """Same logic as year_by_year_consistency.py: per screener, per
    calendar year, mean excess return at T+63d/T+252d (winsorized);
    consistency = fraction of years with positive mean excess return
    (hit rate ACROSS years, not across individual signals -- deliberately
    cruder/more conservative than pooling, so one or two blowout years
    can't masquerade as "the screener works")."""
    rows = []
    for s in SCREENERS:
        active = signals[signals[s] == 1]
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

    sy = build_symbol_year_table(signals)
    print(f"\nSymbol-year units: {len(sy):,}")

    print("\nBenchmark context (China index, same signal-years, for reference -- every effect below "
          "is tested on EXCESS return over this, not raw return):")
    for hl, raw, bench, xr in zip(HORIZON_LABELS_ALL, RAW_HORIZONS_ALL, BENCH_HORIZONS_ALL, HORIZONS_ALL):
        print(f"  {hl}: mean stock {sy[raw].mean():+.2f}%  mean bench {sy[bench].mean():+.2f}%  "
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
    for h in OLS_HORIZONS:
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
    print("FACTORIAL REGRESSION RESULTS -- China A-shares, technical screeners only")
    print("(main effects = %-point excess return vs a symbol-year with that screener NOT firing,")
    print(" holding others + liquidity/volatility fixed; interactions = extra lift beyond additive)")
    print("=" * 100)
    for h in OLS_HORIZONS:
        sub = all_results[all_results["horizon"] == h].copy()
        sub["sig_fdr"] = sub["p_fdr"] < 0.05
        print(f"\n--- {h} (n={sub['n'].iloc[0]}) ---")
        print(sub[["effect", "coef", "se", "p", "p_fdr", "sig_fdr"]].to_string(index=False))

    all_results.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_regression_results_CN_technical.csv", index=False)
    sy.to_parquet("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_symbol_year_table_CN_technical.parquet", index=False)
    print("\nSaved regression results -> cache_seed/factorial_regression_results_CN_technical.csv")

    # --- Year-by-year consistency -------------------------------------------
    print("\n" + "=" * 100)
    print("SCREENER CONSISTENCY ACROSS YEARS (excess return over China benchmark, T+63d and T+252d)")
    print("=" * 100)
    consistency = year_by_year_consistency(sy)
    print(consistency.round(2).to_string(index=False))

    print("\nCONSISTENT screeners (hit rate >= 70% of years at T+252d, >= 4 years of data):")
    consistent = consistency[consistency["hit_rate_years_252d"] >= 70]
    print(consistent["screener"].tolist() if not consistent.empty else "  none met the bar")

    consistency.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/screener_consistency_CN_technical.csv", index=False)
    print("\nSaved consistency results -> cache_seed/screener_consistency_CN_technical.csv")


if __name__ == "__main__":
    main()
