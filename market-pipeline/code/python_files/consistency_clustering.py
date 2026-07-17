#!/usr/bin/env python3
"""
consistency_clustering.py -- v2 "beat the market" line of work.

K-means clusters stocks on THEIR OWN return-consistency profile (hit rate,
mean/std excess return vs SPY, from stock_level_consistency.py -- ground
truth, not screener-conditioned) plus their SCREENER-PASS PROFILE (what
fraction of years each of the 15 v1 screeners fired on that stock) and
average liquidity/volatility. The goal: find a cluster of stocks that are
regular outperformers, then (in new_screener_synthesis.py) ask what
combination of existing screener signals characterizes that cluster.

LIQUIDITY GATE: stock_level_consistency.py's raw yearly-return data
includes extreme outliers (a handful of OTC/micro-cap tickers show
1,000-30,000% single-year "returns" even after split-day exclusion --
consistent with this account's own established finding that illiquid
names are where extreme, hard-to-trade numbers concentrate, see
project_cost_capacity/project_piotroski_plus memory). hit_rate itself is
a SIGN-only statistic and is not distorted by this, but mean_excess/
std_excess/sharpe_like are, and K-means on unscaled/unfiltered magnitude
features would let a handful of illiquid tickers dominate the distance
metric. A minimum average liquidity (63d dollar volume, log-scaled) gate
is applied before clustering -- this is a candidate-selection filter for
this analysis, not a retroactive edit of the raw consistency numbers.

K: chosen by silhouette score across k=3..8 on the standardized feature
matrix, not fixed a priori.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

from factorial_screener_analysis import SIGNALS_PATH, SCREENERS, build_symbol_year_table

CONSISTENCY_SUMMARY_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/stock_level_consistency_summary_us.parquet"
MIN_LOG_LIQUIDITY = 13.0  # roughly log1p($440k/day) -- excludes the thinnest-traded tail, not just top-cap names
MIN_N_YEARS = 5


def build_feature_table() -> pd.DataFrame:
    consistency = pd.read_parquet(CONSISTENCY_SUMMARY_PATH)
    consistency = consistency[consistency["n_years"] >= MIN_N_YEARS].copy()

    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)
    screener_profile = sy.groupby("symbol")[SCREENERS].mean().reset_index()
    liquidity = sy.groupby("symbol")[["log_liquidity", "volatility_63d"]].mean().reset_index()

    feat = consistency.merge(screener_profile, left_on="symbol", right_on="symbol", how="inner")
    feat = feat.merge(liquidity, on="symbol", how="inner")
    feat = feat.dropna(subset=["log_liquidity", "volatility_63d"])
    before = len(feat)
    feat = feat[feat["log_liquidity"] >= MIN_LOG_LIQUIDITY]
    print(f"Liquidity gate (log_liquidity >= {MIN_LOG_LIQUIDITY}): {before:,} -> {len(feat):,} stocks")
    return feat


def choose_k(X: np.ndarray, k_range=range(3, 9)) -> int:
    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(X)
        scores[k] = silhouette_score(X, labels)
    best_k = max(scores, key=scores.get)
    print("Silhouette scores by k:", {k: round(v, 3) for k, v in scores.items()})
    print(f"Chosen k={best_k}")
    return best_k


def main():
    feat = build_feature_table()

    cluster_cols = ["hit_rate", "mean_excess", "std_excess"] + SCREENERS + ["log_liquidity", "volatility_63d"]
    X = feat[cluster_cols].fillna(0).values
    Xs = StandardScaler().fit_transform(X)

    k = choose_k(Xs)
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    feat["cluster"] = km.fit_predict(Xs)

    print("\n" + "=" * 100)
    print("CLUSTER PROFILES")
    print("=" * 100)
    pd.set_option("display.width", 160)
    profile = feat.groupby("cluster").agg(
        n_stocks=("symbol", "count"),
        avg_hit_rate=("hit_rate_pct", "mean"),
        avg_mean_excess=("mean_excess", "mean"),
        avg_std_excess=("std_excess", "mean"),
        avg_liquidity=("log_liquidity", "mean"),
    ).round(2)
    print(profile.to_string())

    # identify the "consistent outperformer" cluster: highest avg hit rate
    # among clusters with a reasonable minimum size (>=20 stocks, so it's
    # a real pattern, not 2-3 lucky tickers)
    candidates = profile[profile["n_stocks"] >= 20]
    winner_cluster = candidates["avg_hit_rate"].idxmax()
    print(f"\n'Consistent outperformer' cluster: #{winner_cluster} "
          f"({profile.loc[winner_cluster,'n_stocks']:.0f} stocks, "
          f"avg hit rate {profile.loc[winner_cluster,'avg_hit_rate']:.1f}%, "
          f"avg mean excess {profile.loc[winner_cluster,'avg_mean_excess']:+.2f}pp)")

    print(f"\nScreener-pass profile of cluster #{winner_cluster} vs overall universe "
          f"(fraction of years each screener fired):")
    cluster_screener = feat[feat["cluster"] == winner_cluster][SCREENERS].mean()
    overall_screener = feat[SCREENERS].mean()
    comp = pd.DataFrame({"cluster_rate": cluster_screener, "universe_rate": overall_screener})
    comp["lift"] = comp["cluster_rate"] / comp["universe_rate"].replace(0, np.nan)
    print(comp.sort_values("lift", ascending=False).round(3).to_string())

    print(f"\nTop 15 stocks in cluster #{winner_cluster} by hit rate:")
    top = feat[feat["cluster"] == winner_cluster].sort_values("hit_rate_pct", ascending=False).head(15)
    print(top[["symbol", "n_years", "hit_rate_pct", "mean_excess", "log_liquidity"]].round(2).to_string(index=False))

    feat["is_consistent_outperformer"] = (feat["cluster"] == winner_cluster).astype(int)
    feat.to_parquet("/Users/umashankar/market-pipeline/code/python_files/cache_seed/consistency_clusters_us.parquet", index=False)
    print(f"\nSaved -> cache_seed/consistency_clusters_us.parquet ({len(feat):,} stocks)")


if __name__ == "__main__":
    main()
