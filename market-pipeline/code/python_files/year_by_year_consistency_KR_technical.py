#!/usr/bin/env python3
"""
year_by_year_consistency_KR_technical.py -- Korea, technical screeners only.
Same logic as year_by_year_consistency.py (US), pointed at the KR technical
signal table via factorial_screener_analysis_KR_technical's own
SIGNALS_PATH/SCREENERS/build_symbol_year_table/winsorize.

Per screener, per calendar year, mean excess return over KOSPI at T+63d and
T+252d. CONSISTENCY = fraction of years with positive mean excess return
(a hit rate across years, not across individual signals) -- deliberately
cruder than "average return across all years pooled" so a couple of
blowout years can't masquerade as "the screener works." MIN_SIGNALS_PER_YEAR/
MIN_YEARS gate out screener-years with too little signal volume to say
anything about consistency.
"""
from __future__ import annotations

import pandas as pd

from factorial_screener_analysis_KR_technical import SIGNALS_PATH, SCREENERS, build_symbol_year_table, winsorize

MIN_SIGNALS_PER_YEAR = 15
MIN_YEARS = 4


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)

    print("=" * 100)
    print("SCREENER CONSISTENCY ACROSS YEARS -- KOREA TECHNICAL (excess return over KOSPI, T+63d and T+252d)")
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

    res.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/screener_consistency_KR_technical.csv", index=False)
    print("\nSaved -> cache_seed/screener_consistency_KR_technical.csv")


if __name__ == "__main__":
    main()
