#!/usr/bin/env python3
"""
year_by_year_consistency_JP_technical.py -- Japan analogue of
year_by_year_consistency.py, same logic exactly, retargeted at the 7
technical-only Japan screeners via factorial_screener_analysis_JP_
technical.py's SIGNALS_PATH/SCREENERS/build_symbol_year_table/winsorize
(imported, not reimplemented -- same "one source of truth" convention as
every other script in this family).

Per screener, per calendar year, mean excess return over ^N225 at T+63d
and T+252d; CONSISTENCY = fraction of years with positive mean excess
return (a hit rate across years, not across individual signals) --
deliberately conservative vs. pooling all years together, for the same
reason the US version documents: a couple of blowout years can dominate a
pooled average and masquerade as "the screener works."
"""
from __future__ import annotations

import pandas as pd

from factorial_screener_analysis_JP_technical import SIGNALS_PATH, SCREENERS, build_symbol_year_table, winsorize

MIN_SIGNALS_PER_YEAR = 15
MIN_YEARS = 4


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)

    print("=" * 100)
    print("JAPAN TECHNICAL SCREENER CONSISTENCY ACROSS YEARS (excess return over ^N225, T+63d and T+252d)")
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

    res.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/screener_consistency_JP_technical.csv", index=False)
    print("\nSaved -> cache_seed/screener_consistency_JP_technical.csv")


if __name__ == "__main__":
    main()
