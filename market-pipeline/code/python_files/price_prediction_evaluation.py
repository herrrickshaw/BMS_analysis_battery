#!/usr/bin/env python3
"""
price_prediction_evaluation.py -- out-of-sample calibration check for the
quantile-regression price predictor built in factorial_price_prediction.py.

Chronological train/test split (train <= 2023-12-31, test >= 2024-01-01),
SAME convention as regime_price_model.py's own established discipline in
this repo -- not a new choice invented for this script. Fits every
quantile model on TRAIN symbol-years only, then checks on TEST symbol-
years (never seen during fitting):

  - 90% interval coverage: fraction of actual excess/raw returns that fall
    inside the predicted [5th, 95th] interval. A well-calibrated model
    hits ~90%; well below it means the model is overconfident (intervals
    too narrow), well above means underconfident (too wide to be useful).
  - IQR (50%) coverage: same idea for [25th, 75th].
  - Median absolute error (MAE) of the predicted median vs. actual,
    compared against a NAIVE baseline that always predicts the TRAIN-set
    unconditional median (no screener information at all) -- the honest
    bar this model has to clear to be worth using over "just guess the
    historical average."

Reported per horizon, on BOTH raw return (price target) and excess return
over SPY (benchmark target) -- see factorial_screener_analysis.py's
benchmark note for why both are reported rather than raw return alone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factorial_screener_analysis import (
    SIGNALS_PATH, SCREENERS, CONTROLS, HORIZONS, RAW_HORIZONS, HORIZON_LABELS,
    build_symbol_year_table, winsorize,
)
from factorial_price_prediction import fit_quantile_models, predict_with_ci, QUANTILES

TRAIN_END_YEAR = 2023
TEST_START_YEAR = 2024


def evaluate(train: pd.DataFrame, test: pd.DataFrame, horizon: str) -> dict:
    models, factors, scaling = fit_quantile_models(train, horizon)
    y_test = winsorize(test[horizon])
    valid = y_test.notna() & test[CONTROLS].notna().all(axis=1)
    test_v = test.loc[valid, factors].copy()
    y_v = y_test[valid].reset_index(drop=True)
    if len(test_v) < 30:
        return None

    # vectorized prediction across the whole test set at once (not a
    # per-row Python loop -- test sets here run into the tens of thousands
    # of symbol-years x 5 quantiles x 10 horizon/target combinations,
    # which a naive row-by-row predict_with_ci() call would make slow)
    for c in CONTROLS:
        mu, sd = scaling[c]
        test_v[c] = (test_v[c] - mu) / sd
    Xtest = pd.DataFrame({"const": 1.0}, index=test_v.index).join(test_v)

    preds = {}
    for q in QUANTILES:
        m = models[q]
        Xq = Xtest[m.params.index]
        preds[q] = Xq.values @ m.params.values
    preds = pd.DataFrame(preds).reset_index(drop=True)
    # resolve any row-level quantile crossing the same way predict_with_ci
    # does (sort point estimates), vectorized via np.sort across columns
    sorted_vals = np.sort(preds[QUANTILES].values, axis=1)
    preds = pd.DataFrame(sorted_vals, columns=QUANTILES)

    in_90 = ((y_v >= preds[0.05]) & (y_v <= preds[0.95])).mean() * 100
    in_50 = ((y_v >= preds[0.25]) & (y_v <= preds[0.75])).mean() * 100
    mae_model = (y_v - preds[0.50]).abs().mean()
    naive_median = winsorize(train[horizon]).median()
    mae_naive = (y_v - naive_median).abs().mean()

    return {
        "horizon": horizon, "n_train": len(train), "n_test": len(test_v),
        "coverage_90pct_interval": in_90, "coverage_50pct_iqr": in_50,
        "mae_model": mae_model, "mae_naive_baseline": mae_naive,
        "improvement_vs_naive_pct": (1 - mae_model / mae_naive) * 100 if mae_naive else np.nan,
    }


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)
    train = sy[sy["year"] <= TRAIN_END_YEAR].copy()
    test = sy[sy["year"] >= TEST_START_YEAR].copy()
    print(f"Train: {len(train):,} symbol-years (<= {TRAIN_END_YEAR}) | "
          f"Test: {len(test):,} symbol-years (>= {TEST_START_YEAR}), never seen during fitting")

    print("\n" + "=" * 100)
    print("OUT-OF-SAMPLE CALIBRATION -- RAW RETURN (price target)")
    print("=" * 100)
    raw_results = []
    for h in RAW_HORIZONS:
        r = evaluate(train, test, h)
        if r:
            raw_results.append(r)
            print(f"  {h}: n_test={r['n_test']:,} | 90% interval coverage {r['coverage_90pct_interval']:.1f}% "
                  f"(target ~90%) | 50% IQR coverage {r['coverage_50pct_iqr']:.1f}% (target ~50%) | "
                  f"median MAE {r['mae_model']:.2f}pp vs naive-baseline MAE {r['mae_naive_baseline']:.2f}pp "
                  f"({r['improvement_vs_naive_pct']:+.1f}% improvement)")

    print("\n" + "=" * 100)
    print(f"OUT-OF-SAMPLE CALIBRATION -- EXCESS RETURN over SPY (benchmark target)")
    print("=" * 100)
    xret_results = []
    for h in HORIZONS:
        r = evaluate(train, test, h)
        if r:
            xret_results.append(r)
            print(f"  {h}: n_test={r['n_test']:,} | 90% interval coverage {r['coverage_90pct_interval']:.1f}% "
                  f"(target ~90%) | 50% IQR coverage {r['coverage_50pct_iqr']:.1f}% (target ~50%) | "
                  f"median MAE {r['mae_model']:.2f}pp vs naive-baseline MAE {r['mae_naive_baseline']:.2f}pp "
                  f"({r['improvement_vs_naive_pct']:+.1f}% improvement)")

    out = pd.DataFrame(raw_results + xret_results)
    out.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/price_prediction_evaluation_us.csv", index=False)
    print(f"\nSaved -> cache_seed/price_prediction_evaluation_us.csv")


if __name__ == "__main__":
    main()
