#!/usr/bin/env python3
"""
holding_period_analysis.py -- for each screener, at what holding period do
excess returns (over S&P 500) peak? Uses the SAME signal panel as every
other stage (cache_seed/factorial_screener_signals_us.parquet, built once
by factorial_screener_test.py), now spanning 5 horizons: T+5d (~1wk),
T+21d (~1mo), T+63d (~1qtr), T+126d (~6mo), T+252d (~1yr).

METHOD: per screener, per horizon, mean and median EXCESS return (xret_T+*d
= stock return minus SPY's own return over the identical window -- see
factorial_screener_analysis.py's benchmark note) plus a risk-adjusted
figure (mean excess / std of excess, a Sharpe-style ratio on the excess
series, NOT annualized -- comparing horizons of different length on an
annualized basis would itself bias toward the shortest horizon). "Peak"
is reported on the RISK-ADJUSTED figure, not raw mean excess, because raw
mean excess is mechanically non-decreasing in a bull-market panel (more
trading days = more time for drift to accumulate) -- that's not the same
question as "when is the risk-adjusted edge largest."

CAVEAT: T+252d is the longest horizon this panel supports; a screener
whose risk-adjusted edge is still climbing at 252d has a peak we can't see
(genuinely unknown, not zero) -- flagged explicitly, not guessed at.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factorial_screener_analysis import (
    SIGNALS_PATH, SCREENERS, HORIZON_LABELS, HORIZONS, RAW_HORIZONS, BENCH_HORIZONS,
    build_symbol_year_table, winsorize,
)

MIN_SUPPORT = 30


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)
    print(f"Symbol-year units: {len(sy):,} ({sy['year'].min()}-{sy['year'].max()})")
    print(f"Horizons: {', '.join(HORIZON_LABELS)}\n")

    rows = []
    for s in SCREENERS:
        active = sy[sy[s] == 1]
        if len(active) < MIN_SUPPORT:
            continue
        for hl, xr, raw, bench in zip(HORIZON_LABELS, HORIZONS, RAW_HORIZONS, BENCH_HORIZONS):
            x = winsorize(active[xr]).dropna()
            if len(x) < MIN_SUPPORT:
                continue
            mean_x, med_x, sd_x = x.mean(), x.median(), x.std()
            rows.append({
                "screener": s, "horizon": hl, "n": len(x),
                "mean_excess_pct": mean_x, "median_excess_pct": med_x,
                "risk_adj": mean_x / sd_x if sd_x else np.nan,
                "hit_rate": (x > 0).mean() * 100,
            })
    res = pd.DataFrame(rows)

    print("=" * 100)
    print("HOLDING-PERIOD RETURN CURVE PER SCREENER (excess return over S&P 500)")
    print("=" * 100)
    pd.set_option("display.width", 160)
    for s in res["screener"].unique():
        sub = res[res["screener"] == s].set_index("horizon").reindex(HORIZON_LABELS).dropna(how="all")
        if sub.empty:
            continue
        peak_h = sub["risk_adj"].idxmax()
        still_rising = peak_h == HORIZON_LABELS[-1] and len(sub) == len(HORIZON_LABELS)
        print(f"\n{s} (n at longest horizon={int(sub['n'].dropna().iloc[-1]) if sub['n'].notna().any() else 0}):")
        print(sub[["n", "mean_excess_pct", "median_excess_pct", "risk_adj", "hit_rate"]].round(2).to_string())
        flag = " [still rising at longest horizon tested -- true peak may be beyond T+252d, unknown]" if still_rising else ""
        print(f"  -> recommended holding period (peak risk-adjusted excess return): {peak_h}{flag}")

    res.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/holding_period_analysis_us.csv", index=False)
    print(f"\nSaved -> cache_seed/holding_period_analysis_us.csv")


if __name__ == "__main__":
    main()
