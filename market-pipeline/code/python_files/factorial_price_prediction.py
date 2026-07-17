#!/usr/bin/env python3
"""
factorial_price_prediction.py -- probability-distribution price prediction
with confidence intervals, built on the SAME signal panel and SAME symbol-
year construction as factorial_screener_analysis.py (single source of
truth: cache_seed/factorial_screener_signals_us.parquet, built once by
factorial_screener_test.py -- see that script's data-consistency note).
SCREENERS, CONTROLS, HORIZONS, build_symbol_year_table() and winsorize()
are imported directly rather than reimplemented, so this can't silently
drift onto a different universe, date range, or split-handling convention
than the hypothesis-test stage.

Where factorial_screener_analysis.py fits OLS (a single expected-return
number per screener), this fits QUANTILE regression (Koenker & Bassett
1978) at 5 quantiles (5/25/50/75/95th pct) per horizon -- the output is a
full predicted DISTRIBUTION of forward return, not just a mean: a 90%
prediction interval (5th-95th pct) plus the median and IQR. Predicted
price = current Close x (1 + predicted return/100).

Same 15 screener factors + log_liquidity/volatility_63d controls as the
OLS stage, main effects only (no pairwise interactions -- quantile
regression on cells with <100 symbol-years produces unstable, noisy
quantile crossing; kept to the well-supported main-effect factors that
have full-sample support).

CONFIDENCE INTERVALS: statsmodels QuantReg's default 'robust' vcov is the
Powell (1991) sandwich estimator -- the quantile-regression analogue of the
HC3 robust SEs already used for the OLS stage, so both stages handle stock
returns' known heteroskedasticity the same way. The CI on a PREDICTED value
(not just a coefficient) is the standard delta-method propagation:
se(y_hat) = sqrt(x' Cov(beta) x), y_hat +/- 1.96*se. Predicted quantiles are
rearranged (sorted) per Chernozhukov/Fernandez-Val/Galichon (2010) if they
cross -- a known, expected quantile-regression artifact at covariate
combinations far from the bulk of the data, not a bug.

BENCHMARKED (2026-07-17, explicit user instruction): every prediction is
reported THREE ways per horizon -- (1) predicted raw-return distribution
-> absolute predicted price, fit on `ret_T+*d`; (2) the S&P 500's own
historical mean return over the same horizon, for reference; (3) predicted
EXCESS-return distribution over SPY, fit on `xret_T+*d` (raw stock return
minus SPY's own return over the identical window) -- this is the "does it
beat the index" distribution, not just "does it go up," which in a
sustained bull market is a much easier bar to clear for no real reason.
RAW_HORIZONS/HORIZONS/BENCH_HORIZONS are imported from factorial_screener_
analysis.py, not redefined, so this can't drift from that stage's
benchmark convention.

OBSERVATIONAL data: this reports "conditional on which screens fired
historically, here is the empirical spread of what happened next," not a
causal forecast and not investment advice.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.quantile_regression import QuantReg

from factorial_screener_analysis import (
    SIGNALS_PATH, SCREENERS, CONTROLS, HORIZONS, RAW_HORIZONS, BENCH_HORIZONS,
    HORIZON_LABELS, build_symbol_year_table, winsorize,
)
from factorial_screener_test import BENCHMARK_SYMBOL

QUANTILES = [0.05, 0.25, 0.50, 0.75, 0.95]
OHLCV_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"
MIN_SUPPORT = 50  # don't fit/report a factor whose symbol-year incidence is below this


def fit_quantile_models(sy: pd.DataFrame, horizon: str) -> tuple[dict, list[str], dict]:
    """Returns (models, factors, scaling). scaling holds {control: (mean, std)}
    for the continuous CONTROLS -- log_liquidity (~10-20) and volatility_63d
    (~0.2-2) sit next to 0/1 binary screeners with wildly different scale,
    which starved statsmodels' QuantReg interior-point solver of numerical
    conditioning: every fit hit the max_iter cap and returned near-zero
    coefficients on every binary screener (verified: the raw median T+252d
    return is +3.8pts but the unstandardized q=0.5 fit put darvas's
    coefficient at 0.0035 -- two orders of magnitude too small to be real,
    and inconsistent with the OLS mean effect of +37pts on the SAME data).
    z-scoring the two continuous controls before fitting (and un-scaling in
    predict_with_ci) fixes conditioning without changing what's estimated."""
    y = winsorize(sy[horizon])
    valid = y.notna() & sy[CONTROLS].notna().all(axis=1)
    factors = [s for s in SCREENERS if sy.loc[valid, s].sum() >= MIN_SUPPORT] + CONTROLS
    Xraw = sy.loc[valid, factors].copy()
    scaling = {}
    for c in CONTROLS:
        mu, sd = Xraw[c].mean(), Xraw[c].std()
        scaling[c] = (mu, sd)
        Xraw[c] = (Xraw[c] - mu) / sd
    X = sm.add_constant(Xraw)
    yv = y[valid]
    models = {}
    for q in QUANTILES:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fit = QuantReg(yv, X).fit(q=q, vcov="robust", max_iter=20000, p_tol=1e-7)
            if any("Maximum number of iterations" in str(w.message) for w in caught):
                print(f"  WARNING: {horizon} q={q} still hit the iteration cap at 20000")
        models[q] = fit
    return models, factors, scaling


def predict_with_ci(models: dict, factors: list[str], scaling: dict, factor_vector: dict) -> pd.DataFrame:
    """factor_vector: {name: value} for any subset of `factors`, in ORIGINAL
    (unscaled) units -- missing = 0. Returns one row per quantile: point
    estimate + 95% CI, quantile-crossing already resolved by sorting the
    point estimates."""
    x = {"const": 1.0}
    for f in factors:
        v = factor_vector.get(f, 0.0)
        if f in scaling:
            mu, sd = scaling[f]
            v = (v - mu) / sd
        x[f] = v
    x = pd.Series(x)
    rows = []
    for q in QUANTILES:
        m = models[q]
        x_ord = x[m.params.index]
        yhat = float((x_ord * m.params).sum())
        cov = m.cov_params()
        se = float(np.sqrt(x_ord.values @ cov.values @ x_ord.values.T))
        rows.append({"quantile": q, "pred_return_pct": yhat, "se": se,
                      "ci_lo": yhat - 1.96 * se, "ci_hi": yhat + 1.96 * se})
    out = pd.DataFrame(rows).sort_values("quantile").reset_index(drop=True)
    # Chernozhukov/Fernandez-Val/Galichon (2010) rearrangement: point estimates
    # must be monotone in q; if a covariate combination causes crossing, sort
    # the point estimates (and carry each row's own CI half-width along, since
    # re-sorting the CI bounds independently would double-count the crossing).
    if not out["pred_return_pct"].is_monotonic_increasing:
        halfwidth = out["ci_hi"] - out["pred_return_pct"]
        order = out["pred_return_pct"].values.argsort()
        out["pred_return_pct"] = out["pred_return_pct"].values[order]
        out["se"] = out["se"].values[order]
        out["ci_lo"] = out["pred_return_pct"] - halfwidth.values[order]
        out["ci_hi"] = out["pred_return_pct"] + halfwidth.values[order]
        out["crossing_resolved"] = True
    else:
        out["crossing_resolved"] = False
    return out


def latest_close_lookup(symbols: list[str]) -> dict:
    px = pd.read_parquet(OHLCV_PATH, columns=["Date", "Symbol", "Close"])
    px = px[px["Symbol"].isin(symbols)]
    last = px.sort_values("Date").groupby("Symbol").tail(1)
    return dict(zip(last["Symbol"], zip(last["Close"], last["Date"])))


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)
    print(f"Symbol-year units: {len(sy):,} ({sy['year'].min()}-{sy['year'].max()})")

    print(f"\nFitting quantile regressions -- raw return (-> price) and excess return over "
          f"{BENCHMARK_SYMBOL} (-> beats-the-index probability), main effects + liquidity/vol controls...")
    raw_models, raw_factors, raw_scaling = {}, {}, {}
    xret_models, xret_factors, xret_scaling = {}, {}, {}
    for raw_h, xret_h in zip(RAW_HORIZONS, HORIZONS):
        m, f, s = fit_quantile_models(sy, raw_h)
        raw_models[raw_h], raw_factors[raw_h], raw_scaling[raw_h] = m, f, s
        m, f, s = fit_quantile_models(sy, xret_h)
        xret_models[xret_h], xret_factors[xret_h], xret_scaling[xret_h] = m, f, s
        print(f"  {raw_h}: {len(f) - len(CONTROLS)} screener factors with >={MIN_SUPPORT} symbol-year support "
              f"(+ {len(CONTROLS)} controls), n={sy[raw_h].notna().sum():,}")

    # --- Illustrative predictions: real, currently-active signal combos ------
    latest_year = sy["year"].max()
    current = sy[(sy["year"] == latest_year) & (sy["n_screeners"] >= 1)].copy()
    current = current.sort_values("n_screeners", ascending=False)
    # a small, varied set: top-stacked names, plus the below_200dma+not_distress
    # "quality dip" combo the OLS stage flagged as a large positive interaction
    picks = list(current.head(5)["symbol"])
    dip_combo = current[(current["below_200dma"] == 1) & (current["not_distress"] == 1)]
    picks += list(dip_combo.head(3)["symbol"])
    picks = list(dict.fromkeys(picks))  # de-dup, keep order

    px_lookup = latest_close_lookup(picks)

    print("\n" + "=" * 100)
    print(f"PREDICTED FORWARD-RETURN DISTRIBUTION & PRICE, {latest_year} active signals -- BENCHMARKED "
          f"against {BENCHMARK_SYMBOL} (price = latest available Close x (1+predicted RAW return))")
    print("=" * 100)
    pred_rows = []
    for sym in picks:
        row = current[current["symbol"] == sym].iloc[0]
        active = [s for s in SCREENERS if row.get(s, 0) == 1]
        close, asof = px_lookup.get(sym, (None, None))
        if close is None:
            continue
        print(f"\n{sym} -- active screens: {', '.join(active) if active else '(none)'} "
              f"| latest Close ${close:,.2f} as of {pd.Timestamp(asof).date()}")
        for hl, raw_h, xret_h, bench_h in zip(HORIZON_LABELS, RAW_HORIZONS, HORIZONS, BENCH_HORIZONS):
            fv = {s: row.get(s, 0) for s in SCREENERS}
            fv["log_liquidity"] = row.get("log_liquidity", np.nan)
            fv["volatility_63d"] = row.get("volatility_63d", np.nan)
            if pd.isna(fv["log_liquidity"]) or pd.isna(fv["volatility_63d"]):
                continue
            dist = predict_with_ci(raw_models[raw_h], raw_factors[raw_h], raw_scaling[raw_h], fv)
            dist["symbol"] = sym
            dist["horizon"] = hl
            dist["price"] = close * (1 + dist["pred_return_pct"] / 100)
            dist["price_ci_lo"] = close * (1 + dist["ci_lo"] / 100)
            dist["price_ci_hi"] = close * (1 + dist["ci_hi"] / 100)

            xdist = predict_with_ci(xret_models[xret_h], xret_factors[xret_h], xret_scaling[xret_h], fv)
            xdist["symbol"] = sym
            xdist["horizon"] = hl
            xdist["metric"] = f"excess_vs_{BENCHMARK_SYMBOL}"
            pred_rows.append(dist)
            pred_rows.append(xdist.rename(columns={"pred_return_pct": "pred_excess_pct"}))

            med = dist[dist["quantile"] == 0.50].iloc[0]
            p05 = dist[dist["quantile"] == 0.05].iloc[0]
            p95 = dist[dist["quantile"] == 0.95].iloc[0]
            xmed = xdist[xdist["quantile"] == 0.50].iloc[0]
            bench_hist_mean = sy[bench_h].mean()
            flag = " [quantile crossing resolved]" if dist["crossing_resolved"].iloc[0] else ""
            print(f"  {hl}: median {med['pred_return_pct']:+.1f}% (95% CI {med['ci_lo']:+.1f} to {med['ci_hi']:+.1f}) "
                  f"-> ${med['price']:,.2f} | 90% predictive interval ${p05['price']:,.2f} - ${p95['price']:,.2f}{flag}")
            print(f"           vs {BENCHMARK_SYMBOL} (historical mean {bench_hist_mean:+.1f}% this horizon): "
                  f"predicted excess median {xmed['pred_return_pct']:+.1f}% (95% CI {xmed['ci_lo']:+.1f} to "
                  f"{xmed['ci_hi']:+.1f}) -- {'beats' if xmed['pred_return_pct'] > 0 else 'lags'} the index at the median")

    all_pred = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    all_pred.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_price_predictions_us.csv", index=False)
    print(f"\nSaved {len(all_pred):,} prediction rows -> cache_seed/factorial_price_predictions_us.csv")


if __name__ == "__main__":
    main()
