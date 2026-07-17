#!/usr/bin/env python3
"""
year_by_year_consistency.py -- which screeners (and, from sector_composite_
analysis.py's output, which sectors) were consistent top performers year
over year, not just strong on average because of one or two outlier years?

Uses the SAME symbol-year table as every other analysis stage. Per screener,
per calendar year, computes mean excess return over SPY at T+63d (the
primary consistency horizon -- ~1 quarter, long enough to filter noise,
short enough that most signal-years in this panel have it resolved) and
T+252d (~1yr, the horizon investors usually mean by "did it work this
year"). A screener's CONSISTENCY here is the fraction of years with a
positive mean excess return (a hit rate across years, not across
individual signals) -- deliberately a cruder, more conservative measure
than "average return across all years pooled," because pooling lets a
couple of blowout years (see the OLS mean-vs-quantile-median skew finding
already reported) dominate and masquerade as "the screener works."
MIN_YEARS gates out screeners with too few years of adequate signal
volume to say anything about consistency at all.
"""
from __future__ import annotations

import pandas as pd

from factorial_screener_analysis import SIGNALS_PATH, SCREENERS, build_symbol_year_table, winsorize

MIN_SIGNALS_PER_YEAR = 15
MIN_YEARS = 4


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)

    print("=" * 100)
    print("SCREENER CONSISTENCY ACROSS YEARS (excess return over SPY, T+63d and T+252d)")
    print("=" * 100)
    rows = []
    for s in SCREENERS:
        active = sy[sy[s] == 1]
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
    res = pd.DataFrame(rows).sort_values("hit_rate_years_252d", ascending=False)
    pd.set_option("display.width", 160)
    print(res.round(2).to_string(index=False))

    print("\nCONSISTENT screeners (hit rate >= 70% of years at T+252d, >= 4 years of data):")
    consistent = res[res["hit_rate_years_252d"] >= 70]
    print(consistent["screener"].tolist() if not consistent.empty else "  none met the bar")

    res.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/screener_consistency_us.csv", index=False)
    print("\nSaved -> cache_seed/screener_consistency_us.csv")


if __name__ == "__main__":
    main()
