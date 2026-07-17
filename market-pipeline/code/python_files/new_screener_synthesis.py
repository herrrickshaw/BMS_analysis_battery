#!/usr/bin/env python3
"""
new_screener_synthesis.py -- v2 "beat the market" line of work, final
stage: synthesize a NEW screener rule from the existing 15 screeners'
pass-patterns, and validate it OUT-OF-TIME (not just out-of-sample).

WHY OUT-OF-TIME, NOT JUST A RANDOM HOLDOUT: consistency_clustering.py's
cluster label is built from a stock's FULL 2017-2025 history pooled. If
this script re-used that same pooled label to both build and grade a
rule, the "validation" would just be re-describing the training data in
different words -- not a real test of whether the rule generalizes to
performance the rule never saw. Instead:
  TRAIN period: stock-years 2017-2023. Cluster stocks into a "consistent
    outperformer" cluster USING ONLY train-period hit rate/excess return/
    screener-pass-profile. Fit a shallow (max_depth=3) decision tree
    predicting cluster membership from the 15 v1 screeners' train-period
    pass rates + liquidity/volatility -- this tree IS the new screener,
    expressed as a short, human-readable rule (sklearn export_text).
  TEST period: stock-years 2024-2025, genuinely held out from both the
    clustering and the tree fit. For every stock the synthesized rule
    flags "yes" (using its TRAIN-period screener behavior as input, since
    that's what the rule was fit against), report its ACTUAL TEST-period
    hit rate and mean excess return -- compared against the test-period
    hit rate of the best v1 screener (Bull Cartel, 58.8% pooled) measured
    on the SAME 2024-2025 window for a fair, apples-to-apples comparison.

This is the honest way to answer "build a new screener with a high
probability of beating the index": show what it would ACTUALLY have done
on years it never touched while being built, not years it was fit on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from factorial_screener_analysis import SIGNALS_PATH, SCREENERS, build_symbol_year_table

STOCK_YEARS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/stock_level_consistency_us.parquet"
TRAIN_END_YEAR = 2023
TEST_START_YEAR = 2024
MIN_LOG_LIQUIDITY = 13.0
MIN_TRAIN_YEARS = 4
# v1's own dashboard flagged coffee_can/magic_formula/growth_stocks/small_cap_growth as
# "Thin data" (each under ~1,000 historical signals) -- the first run of this script's
# tree split almost entirely on those four, a classic overfit-to-noise signature on a
# max_depth=3 tree with binary features that rarely equal 1. Restricting the RULE (not
# the clustering, which still uses all 15 for its descriptive picture) to the well-
# supported screeners is the direct fix, not a post-hoc excuse for a bad result.
THIN_DATA_SCREENERS = {"coffee_can", "magic_formula", "growth_stocks", "small_cap_growth"}
RULE_SCREENERS = [s for s in SCREENERS if s not in THIN_DATA_SCREENERS]


def period_summary(stock_years: pd.DataFrame, lo: int, hi: int, prefix: str) -> pd.DataFrame:
    sub = stock_years[(stock_years["year"] >= lo) & (stock_years["year"] <= hi)]
    g = sub.groupby("Symbol").agg(
        n_years=("year", "nunique"), hit_rate=("beat_spy", "mean"),
        mean_excess=("excess_return_pct", "mean"), std_excess=("excess_return_pct", "std"),
    ).reset_index().rename(columns={"Symbol": "symbol"})
    g.columns = ["symbol"] + [f"{prefix}_{c}" for c in g.columns[1:]]
    return g


def screener_profile(signals: pd.DataFrame, lo: int, hi: int) -> pd.DataFrame:
    sy = build_symbol_year_table(signals)
    sub = sy[(sy["year"] >= lo) & (sy["year"] <= hi)]
    prof = sub.groupby("symbol")[SCREENERS + ["log_liquidity", "volatility_63d"]].mean().reset_index()
    return prof


def main():
    stock_years = pd.read_parquet(STOCK_YEARS_PATH)
    signals = pd.read_parquet(SIGNALS_PATH)

    train_perf = period_summary(stock_years, stock_years["year"].min(), TRAIN_END_YEAR, "train")
    test_perf = period_summary(stock_years, TEST_START_YEAR, stock_years["year"].max(), "test")
    train_prof = screener_profile(signals, stock_years["year"].min(), TRAIN_END_YEAR)

    feat = train_perf.merge(train_prof, on="symbol", how="inner")
    feat = feat[feat["train_n_years"] >= MIN_TRAIN_YEARS]
    feat = feat.dropna(subset=["log_liquidity", "volatility_63d"])
    feat = feat[feat["log_liquidity"] >= MIN_LOG_LIQUIDITY]
    print(f"Training universe: {len(feat):,} stocks with >={MIN_TRAIN_YEARS} train years, liquidity-gated")

    cluster_cols = ["train_hit_rate", "train_mean_excess", "train_std_excess"] + SCREENERS + ["log_liquidity", "volatility_63d"]
    X = feat[cluster_cols].fillna(0).values
    Xs = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=5, n_init=10, random_state=42)
    feat["cluster"] = km.fit_predict(Xs)
    profile = feat.groupby("cluster").agg(n=("symbol", "count"), hr=("train_hit_rate", "mean"))
    candidates = profile[profile["n"] >= 20]
    winner = candidates["hr"].idxmax()
    feat["is_consistent_train"] = (feat["cluster"] == winner).astype(int)
    print(f"Train-period 'consistent outperformer' cluster: #{winner}, "
          f"{profile.loc[winner,'n']:.0f} stocks, train hit rate {profile.loc[winner,'hr']*100:.1f}%")

    # --- Fit the interpretable rule (the new screener) -------------------------
    rule_features = RULE_SCREENERS + ["log_liquidity", "volatility_63d"]
    tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=30, random_state=42, class_weight="balanced")
    tree.fit(feat[rule_features], feat["is_consistent_train"])
    print("\n" + "=" * 100)
    print("SYNTHESIZED NEW SCREENER (decision tree, max depth 3, train period 2017-2023 only)")
    print("=" * 100)
    print(export_text(tree, feature_names=rule_features))

    feat["rule_flag"] = tree.predict(feat[rule_features])
    train_precision = feat.loc[feat["rule_flag"] == 1, "is_consistent_train"].mean()
    print(f"\nRule's IN-SAMPLE precision (of stocks it flags, fraction actually in the "
          f"train-period consistent cluster): {train_precision*100:.1f}%")

    # --- Out-of-time validation -------------------------------------------------
    validation = feat[["symbol", "rule_flag", "train_hit_rate"]].merge(test_perf, on="symbol", how="inner")
    validation = validation[validation["test_n_years"] >= 1]
    print("\n" + "=" * 100)
    print(f"OUT-OF-TIME VALIDATION -- test period {TEST_START_YEAR}-{stock_years['year'].max()}, "
          f"NEVER used to build the cluster or fit the rule")
    print("=" * 100)

    flagged = validation[validation["rule_flag"] == 1]
    not_flagged = validation[validation["rule_flag"] == 0]
    print(f"\nStocks the new screener flags: {len(flagged):,}")
    print(f"  test-period hit rate:   {flagged['test_hit_rate'].mean()*100:.1f}%")
    print(f"  test-period mean excess: {flagged['test_mean_excess'].mean():+.2f}pp")
    print(f"\nStocks NOT flagged (rest of universe): {len(not_flagged):,}")
    print(f"  test-period hit rate:   {not_flagged['test_hit_rate'].mean()*100:.1f}%")
    print(f"  test-period mean excess: {not_flagged['test_mean_excess'].mean():+.2f}pp")

    # Bull Cartel comparison on the SAME 2024-2025 test window, for a fair fight
    sy_test = build_symbol_year_table(signals)
    sy_test = sy_test[sy_test["year"] >= TEST_START_YEAR]
    bc = sy_test[sy_test["bull_cartel"] == 1]
    bc_hit_rate = (bc["xret_T+252d"] > 0).mean() * 100 if len(bc) else float("nan")
    print(f"\nBull Cartel (best v1 screener, pooled hit rate 58.8%) on the SAME 2024-2025 window: "
          f"{bc_hit_rate:.1f}% signal-level hit rate, n={len(bc):,} signal-years")

    validation.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/new_screener_validation_us.csv", index=False)
    flagged[["symbol", "train_hit_rate", "test_hit_rate", "test_mean_excess"]].sort_values(
        "test_mean_excess", ascending=False
    ).to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/new_screener_flagged_stocks_us.csv", index=False)
    print(f"\nSaved -> cache_seed/new_screener_validation_us.csv, cache_seed/new_screener_flagged_stocks_us.csv")


if __name__ == "__main__":
    main()
