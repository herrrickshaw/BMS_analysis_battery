#!/usr/bin/env python3
"""
reversal_validation.py -- v3: direct out-of-time check for the two new
short-term reversal screeners (Lehmann 1990 weekly, Jegadeesh 1990
monthly), independent of the OLS/holding-period/consistency reports that
already cover them by virtue of being added to SCREENERS.

WHY A SEPARATE, DIRECT CHECK: v2's whole finding was that ML-DERIVED
combinations of the original 15 screeners (a decision tree, a Lasso-
selected K-means cluster) looked good in-sample and collapsed out-of-
time -- textbook post-selection overfitting. Reversal is different in
kind: it's not derived from this data at all, it's a single, specific,
pre-registered (in the sense that the literature predicts it BEFORE
seeing this dataset) academic strategy. The right test is not "does a
model fit to 2017-2023 data predict 2024-2025" (that's the v2 test,
already failed 3 ways) but "does the literature's OWN claim -- short-
horizon losers outperform -- show up with similar strength in both
halves of this specific panel." A strategy that holds up in BOTH halves
independently is a materially different, stronger claim than one that
only worked in the half it was fit on.
"""
from __future__ import annotations

import pandas as pd

from factorial_screener_analysis import SIGNALS_PATH, build_symbol_year_table, winsorize

TRAIN_END_YEAR = 2023
TEST_START_YEAR = 2024
REVERSAL_SCREENERS = ["reversal_weekly", "reversal_monthly"]
HORIZON_LABELS = ["T+5d", "T+21d", "T+63d", "T+126d", "T+252d"]


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)

    print("=" * 100)
    print("SHORT-TERM REVERSAL -- TRAIN (2017-2023) vs TEST (2024-2025), excess return over SPY")
    print("=" * 100)

    for s in REVERSAL_SCREENERS:
        active = sy[sy[s] == 1]
        train = active[active["year"] <= TRAIN_END_YEAR]
        test = active[active["year"] >= TEST_START_YEAR]
        print(f"\n{s}:")
        for hl in HORIZON_LABELS:
            xcol = f"xret_{hl}"
            tr = winsorize(train[xcol]).dropna()
            te = winsorize(test[xcol]).dropna()
            if len(tr) < 20 or len(te) < 10:
                print(f"  {hl}: insufficient data (train n={len(tr)}, test n={len(te)})")
                continue
            print(f"  {hl}: train n={len(tr):4d} hit_rate={100*(tr>0).mean():5.1f}% mean_excess={tr.mean():+7.2f}pp  |  "
                  f"test n={len(te):4d} hit_rate={100*(te>0).mean():5.1f}% mean_excess={te.mean():+7.2f}pp")

    # side-by-side against the best-performing v1 screeners for context
    print("\n" + "=" * 100)
    print("CONTEXT: same train/test split for the 5 v1 'Robust' screeners")
    print("=" * 100)
    for s in ["darvas", "golden_cross", "new_highs", "roce_plus", "graham_10y"]:
        active = sy[sy[s] == 1]
        train = active[active["year"] <= TRAIN_END_YEAR]
        test = active[active["year"] >= TEST_START_YEAR]
        xcol = "xret_T+63d"
        tr = winsorize(train[xcol]).dropna()
        te = winsorize(test[xcol]).dropna()
        print(f"  {s} (T+63d): train hit_rate={100*(tr>0).mean():5.1f}%  |  test hit_rate={100*(te>0).mean():5.1f}%")


if __name__ == "__main__":
    main()
