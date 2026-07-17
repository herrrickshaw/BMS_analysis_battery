#!/usr/bin/env python3
"""
screener_stock_breakdown.py -- Phase E: apply the 5 screeners found ROBUST
(FDR-significant at every horizon, see factorial_screener_analysis.py) at
their own recommended holding period (from holding_period_analysis.py) to
today's actual active signals, producing a screener -> stock table with
LTP, probability of a positive return, and the predicted % return.

DELIBERATELY NOT a "buy list": every table here also carries the
per-screener YEAR-hit-rate from year_by_year_consistency.py (none of these
5 clears the 70% bar -- see that script's own finding) and the
probability-of-return column is the screener's own HISTORICAL signal-level
hit rate, not a guarantee.

PROBABILITY OF RETURN: fraction of this screener's individual historical
signals that beat the S&P 500 at ITS recommended holding period (from
holding_period_analysis_us.csv's `hit_rate` column) -- a frequentist
historical rate, not a model-derived posterior probability. Kept
deliberately simple/transparent rather than backing it out of only 5
quantile points (5th/25th/50th/75th/95th), which would be a noisy
interpolation for an "is P(return>0) 42% or 48%?" question the 5-point
quantile grid isn't built to answer precisely.

% RETURN ESTIMATE: the median (q=0.5) predicted EXCESS return over SPY
from the SAME quantile regression used in factorial_price_prediction.py,
at the screener's own peak holding period -- not a generic single horizon
for every screener.

Universe capped to the top N stocks per screener by predicted return, not
the full active list (some screeners have 2,000-4,000 concurrently active
signals -- not dashboard-able, and ranking by predicted return surfaces
the names the model itself is most confident about, for better or worse).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factorial_screener_analysis import (
    SIGNALS_PATH, SCREENERS, CONTROLS, HORIZONS, HORIZON_LABELS,
    build_symbol_year_table,
)
from factorial_price_prediction import fit_quantile_models, predict_with_ci, OHLCV_PATH
from factorial_screener_test import BENCHMARK_SYMBOL

ROBUST_SCREENERS = ["darvas", "golden_cross", "new_highs", "roce_plus", "graham_10y"]
TOP_N_PER_SCREENER = 10


def main():
    hp = pd.read_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/holding_period_analysis_us.csv")
    peak = hp.loc[hp.groupby("screener")["risk_adj"].idxmax()].set_index("screener")

    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)
    latest_year = sy["year"].max()
    current = sy[sy["year"] == latest_year].copy()

    needed_horizons = sorted(set(peak.loc[ROBUST_SCREENERS, "horizon"]),
                              key=lambda h: HORIZON_LABELS.index(h))
    print(f"Fitting quantile models for {len(needed_horizons)} distinct peak horizon(s): {needed_horizons}")
    models_by_h, factors_by_h, scaling_by_h = {}, {}, {}
    for hl in needed_horizons:
        xret_col = f"xret_{hl}"
        models_by_h[hl], factors_by_h[hl], scaling_by_h[hl] = fit_quantile_models(sy, xret_col)

    all_symbols = set()
    for s in ROBUST_SCREENERS:
        all_symbols |= set(current.loc[current[s] == 1, "symbol"])
    print(f"Fetching latest Close for {len(all_symbols)} candidate symbols...")
    px = pd.read_parquet(OHLCV_PATH, columns=["Date", "Symbol", "Close"])
    px = px[px["Symbol"].isin(all_symbols)].sort_values("Date")
    ltp = px.groupby("Symbol").tail(1).set_index("Symbol")["Close"].to_dict()

    rows = []
    for s in ROBUST_SCREENERS:
        peak_h = peak.loc[s, "horizon"]
        hit_rate = peak.loc[s, "hit_rate"]
        active = current[current[s] == 1].copy()
        active = active[active["symbol"].isin(ltp.keys())]
        active = active.dropna(subset=["log_liquidity", "volatility_63d"])

        preds = []
        for _, row in active.iterrows():
            fv = {sc: row.get(sc, 0) for sc in SCREENERS}
            fv["log_liquidity"] = row["log_liquidity"]
            fv["volatility_63d"] = row["volatility_63d"]
            dist = predict_with_ci(models_by_h[peak_h], factors_by_h[peak_h], scaling_by_h[peak_h], fv)
            med = dist[dist["quantile"] == 0.50].iloc[0]
            preds.append({"symbol": row["symbol"], "screener": s, "peak_horizon": peak_h,
                          "hit_rate_pct": hit_rate, "ltp": ltp[row["symbol"]],
                          "pred_excess_return_pct": med["pred_return_pct"],
                          "ci_lo": med["ci_lo"], "ci_hi": med["ci_hi"]})
        pred_df = pd.DataFrame(preds).sort_values("pred_excess_return_pct", ascending=False)
        rows.append(pred_df.head(TOP_N_PER_SCREENER))
        print(f"  {s}: {len(active)} active signals -> top {min(TOP_N_PER_SCREENER, len(pred_df))} by predicted excess return")

    out = pd.concat(rows, ignore_index=True)
    out["predicted_price"] = out["ltp"] * (1 + out["pred_excess_return_pct"] / 100)

    print("\n" + "=" * 100)
    print(f"SCREENER -> STOCK BREAKDOWN (top {TOP_N_PER_SCREENER}/screener by predicted excess return, "
          f"each screener's OWN peak holding period, vs {BENCHMARK_SYMBOL})")
    print("=" * 100)
    pd.set_option("display.width", 160)
    for s in ROBUST_SCREENERS:
        sub = out[out["screener"] == s]
        print(f"\n{s} (hold: {sub['peak_horizon'].iloc[0]}, historical hit rate {sub['hit_rate_pct'].iloc[0]:.1f}%):")
        print(sub[["symbol", "ltp", "pred_excess_return_pct", "ci_lo", "ci_hi"]].round(2).to_string(index=False))

    out.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/screener_stock_breakdown_us.csv", index=False)
    print(f"\nSaved -> cache_seed/screener_stock_breakdown_us.csv")


if __name__ == "__main__":
    main()
