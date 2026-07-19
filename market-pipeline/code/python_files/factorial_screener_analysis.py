#!/usr/bin/env python3
"""
Factorial ANOVA (regression-based, for unbalanced/non-orthogonal data --
Montgomery "Design and Analysis of Experiments" Ch. 15) on the universe-wide
US screener signals built by factorial_screener_test.py.

15 binary screener factors, symbol-year unit of analysis (avoids
pseudo-replication from multiple same-year signals of one screener type),
HC3 robust standard errors (stock returns are fat-tailed/heteroskedastic),
Benjamini-Hochberg FDR correction across every effect x horizon tested.

DATA CONSISTENCY (2026-07-17): reads the single signals parquet built by
factorial_screener_test.py, which now excludes (not winsorizes) any
forward-return window crossing a likely-unadjusted-split day -- see that
script's module docstring. winsorize() below is kept ONLY as a light
secondary guard against genuine fat-tailed (non-split) outliers, not as
the primary defense against split contamination anymore.

ADDITIONAL DATA: log_liquidity (log 63d dollar volume) and volatility_63d
(63d annualized realized vol), both computed once in factorial_screener_
test.py, are included as continuous controls in every regression. This
account's own prior research (project_liquidity_scan_research memory)
found liquidity predicts BOTH which screens a stock passes and its forward
returns -- an omitted-variable confound. Without controlling for it, a
screener's coefficient partly reflects "stocks like this tend to be
liquid/illiquid," not the screener itself. Controlling for it holds
liquidity and volatility fixed, so each screener's coefficient is the
return difference at comparable liquidity/risk.

BENCHMARKED RETURNS (2026-07-17, explicit user instruction): every return
tested here is now EXCESS return over the S&P 500 (`xret_T+*d` = stock
return minus SPY's own return over the identical [entry, entry+horizon]
trading-day window, computed once in factorial_screener_test.py from the
SAME OHLCV panel). A screener's raw return can look great purely because
the whole market rallied over the years that screener happened to fire
(2023-2024 vs. 2022, say) -- that's beta, not the screener adding
anything. Testing excess return holds the market's own move fixed, so a
positive/significant coefficient here means "beat the index," not "went
up." RAW_HORIZONS (raw stock return, pre-benchmark) is kept only for the
price-prediction stage, which needs an absolute price target, not an
alpha estimate. Nifty 50 is the India equivalent of this benchmark, but
this script's own docstring already documents why India can't run the
full screener universe honestly today (75/8944 symbols with point-in-time
fundamentals) -- not added here.

OBSERVATIONAL data, not a randomized experiment: reported as descriptive/
correlational, no causal claim. Pairwise interactions are only fit where
the cell has >=30 symbol-years -- Montgomery Ch.8/9's fractional-design
principle applied to real sparse data: don't estimate an effect the data
can't support.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import false_discovery_control
from itertools import combinations

SIGNALS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_us.parquet"
SCREENERS = ["darvas", "golden_cross", "new_highs", "below_200dma",
             "piotroski", "coffee_can", "magic_formula", "bull_cartel",
             "roce_plus", "sloan_quality", "not_distress",
             "capacity_expansion", "growth_stocks", "graham_10y", "small_cap_growth",
             "reversal_weekly", "reversal_monthly",  # v3: Lehmann (1990) / Jegadeesh (1990)
             "pead_positive_surprise", "debt_reduction",  # v4: PEAD x deleveraging
             "net_margin", "operating_margin", "pb_value", "ps_value",  # v6: Screener.in ratio taxonomy
             "ev_ebitda_value", "peg_value", "fcf_yield", "low_beta",
             "eps_growth", "roic_value", "fcf_margin", "net_debt_ebitda", "ev_sales",  # v7: financial-media gap check
             "low_asset_growth", "buyback_yield",  # v8: Cooper/Gulen/Schill (2008) asset growth + buyback yield
             "insider_buying", "short_interest_decline",  # v8: Form 4 + FINRA short interest, S&P 500 scope only
             "operating_profit_growth", "debt_reduction_and_opgrowth"]  # 2026-07-19: user-requested combined filter
CONTROLS = ["log_liquidity", "volatility_63d"]
HORIZON_LABELS = ["T+5d", "T+21d", "T+63d", "T+126d", "T+252d"]
HORIZONS = [f"xret_{h}" for h in HORIZON_LABELS]        # primary: excess return over SPY
RAW_HORIZONS = [f"ret_{h}" for h in HORIZON_LABELS]      # raw return, for price prediction only
BENCH_HORIZONS = [f"bench_ret_{h}" for h in HORIZON_LABELS]  # SPY's own return, for reporting
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
    """Cap extreme returns at the 1st/99th percentile. The raw Close-price
    panel here is NOT confirmed split-adjusted -- this account's own memory
    (reference_deep_10y_market_data.md) already diagnosed this exact
    failure mode ("raw Close not Adj Close -- splits fake extreme premia")
    in a sibling dataset. Observed here too: max 252d return of 2.5M%,
    std of 16,818% -- not real stock performance, a data artifact. Without
    this, a handful of split-contaminated rows would dominate every OLS
    coefficient."""
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)


def fit_factorial(df: pd.DataFrame, horizon: str, interactions: list[tuple[str, str]]) -> pd.DataFrame:
    y = winsorize(df[horizon])
    valid = y.notna() & df[CONTROLS].notna().all(axis=1)
    X = df.loc[valid, SCREENERS].copy()
    for a, b in interactions:
        X[f"{a}:{b}"] = df.loc[valid, a] * df.loc[valid, b]
    # liquidity/volatility controls -- held fixed so screener coefficients
    # are not confounded with "this screener happens to select liquid/
    # volatile names" (see module docstring)
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

    print("\nBenchmark context (S&P 500 / SPY, same signal-years, for reference -- "
          "every effect below is tested on EXCESS return over this, not raw return):")
    for hl, raw, bench, xr in zip(HORIZON_LABELS, RAW_HORIZONS, BENCH_HORIZONS, HORIZONS):
        print(f"  {hl}: mean stock {sy[raw].mean():+.2f}%  mean SPY {sy[bench].mean():+.2f}%  "
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

    # FDR correction applies only to the screener-effect family (main effects
    # + interactions) being tested -- log_liquidity/volatility_63d are
    # controls, not hypotheses under test, so folding them into the same
    # correction would dilute power against the screener hypotheses for no
    # reason (they're expected to be significant; that's not what's tested).
    is_control = all_results["effect"].isin(CONTROLS)
    all_results["p_fdr"] = np.nan
    all_results.loc[~is_control, "p_fdr"] = false_discovery_control(
        all_results.loc[~is_control, "p"].values, method="bh")
    all_results = all_results.sort_values(["horizon", "p_fdr"])

    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", None)
    print("\n" + "=" * 100)
    print("FACTORIAL REGRESSION RESULTS (main effects = %-point return vs a symbol-year with")
    print("that screener NOT firing, holding others fixed; interactions = extra lift beyond additive)")
    print("=" * 100)
    for h in HORIZONS:
        sub = all_results[all_results["horizon"] == h].copy()
        sub["sig_fdr"] = sub["p_fdr"] < 0.05
        print(f"\n--- {h} (n={sub['n'].iloc[0]}) ---")
        print(sub[["effect", "coef", "se", "p", "p_fdr", "sig_fdr"]].to_string(index=False))

    all_results.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_regression_results_us.csv", index=False)
    sy.to_parquet("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_symbol_year_table_us.parquet", index=False)
    print("\nSaved results -> cache_seed/factorial_regression_results_us.csv")


if __name__ == "__main__":
    main()
