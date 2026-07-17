#!/usr/bin/env python3
"""
lasso_cluster_synthesis.py -- v2 "beat the market" line of work, third
technique: use Lasso regression (L1-regularized linear regression,
https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.
Lasso.html) to select which of the 15 v1 screeners + liquidity/volatility
actually carry independent predictive signal for excess return over SPY,
then K-means CLUSTER stocks in that Lasso-selected subspace only -- new
clusters informed by variable selection, not clustering on all 17 raw
features the way consistency_clustering.py / new_screener_synthesis.py
did.

WHY LASSO HERE, DIFFERENT FROM THE OLS/TREE ALREADY DONE: v1's OLS
(factorial_screener_analysis.py) reports EVERY screener's coefficient
with a p-value; the tree in new_screener_synthesis.py greedily splits on
whichever feature reduces impurity most at each node. Lasso does neither
-- it's a CONTINUOUS regression (not classification) with an L1 penalty
that shrinks weak/redundant coefficients EXACTLY to zero, which is a
different, complementary form of variable selection: it tends to keep
one representative from a correlated group (e.g., darvas/golden_cross/
new_highs are highly correlated technical screeners, see v1's dashboard)
and zero out the rest, rather than splitting on all of them piecemeal.
Comparing what Lasso keeps vs. what the OLS found "Robust" vs. what the
tree split on is itself informative triangulation, not just a fourth
redundant technique.

Same discipline as the rest of v2: chronological train (<=2023) / test
(>=2024) split, liquidity gate, winsorized target, out-of-time validation
that never touches the test period until the very last step.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

from factorial_screener_analysis import SIGNALS_PATH, SCREENERS, winsorize
from new_screener_synthesis import period_summary, screener_profile, TRAIN_END_YEAR, TEST_START_YEAR, MIN_LOG_LIQUIDITY, MIN_TRAIN_YEARS

STOCK_YEARS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/stock_level_consistency_us.parquet"
FEATURES = SCREENERS + ["log_liquidity", "volatility_63d"]
TOP_QUANTILE = 0.90  # top decile of Lasso-predicted score = the new candidate group


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
    feat["train_mean_excess_w"] = winsorize(feat["train_mean_excess"])
    print(f"Training universe: {len(feat):,} stocks with >={MIN_TRAIN_YEARS} train years, liquidity-gated")

    # --- Lasso: predict continuous excess return from screener-pass rates ------
    X = feat[FEATURES].values
    y = feat["train_mean_excess_w"].values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    lasso = LassoCV(cv=5, random_state=42, n_alphas=100, max_iter=10000)
    lasso.fit(Xs, y)
    print(f"\nLassoCV chosen alpha: {lasso.alpha_:.4f}  |  R^2 (train, in-sample): {lasso.score(Xs, y):.3f}")

    coefs = pd.Series(lasso.coef_, index=FEATURES).sort_values(key=np.abs, ascending=False)
    print("\n" + "=" * 100)
    print("LASSO COEFFICIENTS (standardized features; predicting train-period mean excess return)")
    print("=" * 100)
    print(coefs.round(3).to_string())
    kept = coefs[coefs != 0].index.tolist()
    zeroed = coefs[coefs == 0].index.tolist()
    print(f"\nKept (nonzero): {kept}")
    print(f"Zeroed out: {zeroed}")

    if len(kept) < 2:
        print("\nFewer than 2 features survived -- widening to top 4 by |coef| for a meaningful cluster space.")
        kept = coefs.index[:4].tolist()

    # --- Lasso-predicted score, and a K-means clustering restricted to the ----
    # --- Lasso-selected subspace only ------------------------------------------
    feat["lasso_score"] = lasso.predict(Xs)
    Xk = StandardScaler().fit_transform(feat[kept].values)
    sil = {}
    for k in range(3, 7):
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(Xk)
        sil[k] = silhouette_score(Xk, labels)
    best_k = max(sil, key=sil.get)
    print(f"\nSilhouette by k on Lasso-selected subspace: {{{', '.join(f'{k}: {v:.3f}' for k, v in sil.items())}}} -> k={best_k}")
    km = KMeans(n_clusters=best_k, n_init=10, random_state=42)
    feat["lasso_cluster"] = km.fit_predict(Xk)

    print("\n" + "=" * 100)
    print(f"CLUSTERS ON THE LASSO-SELECTED SUBSPACE ({', '.join(kept)})")
    print("=" * 100)
    pd.set_option("display.width", 160)
    feat["train_hit_rate_pct"] = feat["train_hit_rate"] * 100
    profile = feat.groupby("lasso_cluster").agg(
        n=("symbol", "count"), avg_hit_rate_pct=("train_hit_rate_pct", "mean"),
        avg_mean_excess=("train_mean_excess_w", "mean"), avg_lasso_score=("lasso_score", "mean"),
    ).round(2)
    print(profile.to_string())
    candidates = profile[profile["n"] >= 20]
    winner = candidates["avg_mean_excess"].idxmax()
    print(f"\nBest Lasso-subspace cluster: #{winner} ({profile.loc[winner,'n']:.0f} stocks, "
          f"train hit rate {profile.loc[winner,'avg_hit_rate_pct']:.1f}%, "
          f"train mean excess {profile.loc[winner,'avg_mean_excess']:+.2f}pp)")
    top_names = feat[feat["lasso_cluster"] == winner].sort_values("train_mean_excess", ascending=False).head(15)
    print(top_names[["symbol", "train_n_years", "train_hit_rate_pct", "train_mean_excess", "lasso_score"]].round(2).to_string(index=False))

    # --- Out-of-time validation, both for the cluster AND the top-decile-by-score group
    validation = feat[["symbol", "lasso_cluster", "lasso_score"]].merge(test_perf, on="symbol", how="inner")
    validation = validation[validation["test_n_years"] >= 1]

    print("\n" + "=" * 100)
    print(f"OUT-OF-TIME VALIDATION -- test period {TEST_START_YEAR}-{stock_years['year'].max()}")
    print("=" * 100)

    cluster_group = validation[validation["lasso_cluster"] == winner]
    rest = validation[validation["lasso_cluster"] != winner]
    print(f"\nBest Lasso-subspace cluster (#{winner}), n={len(cluster_group):,}: "
          f"test hit rate {cluster_group['test_hit_rate'].mean()*100:.1f}%, "
          f"test mean excess {cluster_group['test_mean_excess'].mean():+.2f}pp")
    print(f"Rest of universe, n={len(rest):,}: test hit rate {rest['test_hit_rate'].mean()*100:.1f}%, "
          f"test mean excess {rest['test_mean_excess'].mean():+.2f}pp")

    threshold = feat["lasso_score"].quantile(TOP_QUANTILE)
    top_score = validation[validation["lasso_score"] >= threshold]
    below = validation[validation["lasso_score"] < threshold]
    print(f"\nTop decile by Lasso-predicted score (score >= {threshold:.2f}), n={len(top_score):,}: "
          f"test hit rate {top_score['test_hit_rate'].mean()*100:.1f}%, "
          f"test mean excess {top_score['test_mean_excess'].mean():+.2f}pp")
    print(f"Bottom 90% by score, n={len(below):,}: test hit rate {below['test_hit_rate'].mean()*100:.1f}%, "
          f"test mean excess {below['test_mean_excess'].mean():+.2f}pp")

    feat.to_parquet("/Users/umashankar/market-pipeline/code/python_files/cache_seed/lasso_clusters_us.parquet", index=False)
    validation.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/lasso_cluster_validation_us.csv", index=False)
    print(f"\nSaved -> cache_seed/lasso_clusters_us.parquet, cache_seed/lasso_cluster_validation_us.csv")


if __name__ == "__main__":
    main()
