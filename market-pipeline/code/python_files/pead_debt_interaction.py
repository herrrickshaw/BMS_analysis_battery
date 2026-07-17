#!/usr/bin/env python3
"""
pead_debt_interaction.py -- v4: does PEAD (post-earnings-announcement
drift) picking help specifically among companies that are stepping OUT
of debt?

Two complementary views, both needed:
  1. The RAW INTERSECTION comparison: PEAD alone vs debt_reduction alone
     vs BOTH together (unconditional hit rate / mean excess return over
     SPY) -- the direct, literal answer to "does PEAD picking help as
     companies step out of debt."
  2. The FORMAL interaction coefficient from factorial_screener_analysis.py's
     OLS (if pead_positive_surprise x debt_reduction had >=30 both-fire
     symbol-years to test) -- this is the coefficient on top of each
     factor's own main effect, i.e. genuine synergy vs. just "both are
     independently good things that happen to co-occur sometimes."

Both views on a chronological train(<=2023)/test(>=2024) split, matching
this branch's established discipline (v2's bandit/tree/Lasso, v3's
reversal) -- an in-sample-only finding here would repeat the exact
mistake this whole branch has spent three techniques demonstrating.
"""
from __future__ import annotations

import pandas as pd

from factorial_screener_analysis import SIGNALS_PATH, build_symbol_year_table, winsorize

TRAIN_END_YEAR = 2023
TEST_START_YEAR = 2024
HORIZON_LABELS = ["T+21d", "T+63d", "T+126d", "T+252d"]


def report_group(sy: pd.DataFrame, mask, label: str, period_name: str):
    sub = sy[mask]
    if len(sub) < 15:
        print(f"    {label} ({period_name}): n={len(sub)} -- too few symbol-years to report")
        return
    parts = []
    for hl in HORIZON_LABELS:
        x = winsorize(sub[f"xret_{hl}"]).dropna()
        if len(x) < 10:
            continue
        parts.append(f"{hl}: hit={100*(x>0).mean():.1f}% exc={x.mean():+.1f}pp")
    print(f"    {label} ({period_name}, n={len(sub)}): " + " | ".join(parts))


def main():
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)
    train = sy[sy["year"] <= TRAIN_END_YEAR]
    test = sy[sy["year"] >= TEST_START_YEAR]

    print("=" * 100)
    print("PEAD x DEBT-REDUCTION -- unconditional hit rate / mean excess return over SPY")
    print("=" * 100)

    for name, df in [("TRAIN 2017-2023", train), ("TEST 2024-2025", test)]:
        print(f"\n--- {name} ---")
        pead_only = (df["pead_positive_surprise"] == 1) & (df["debt_reduction"] == 0)
        debt_only = (df["pead_positive_surprise"] == 0) & (df["debt_reduction"] == 1)
        both = (df["pead_positive_surprise"] == 1) & (df["debt_reduction"] == 1)
        neither = (df["pead_positive_surprise"] == 0) & (df["debt_reduction"] == 0)
        report_group(df, pead_only, "PEAD alone (no debt reduction)", name)
        report_group(df, debt_only, "Debt reduction alone (no PEAD)", name)
        report_group(df, both, "PEAD + debt reduction TOGETHER", name)
        report_group(df, neither, "Neither (baseline)", name)

    print("\n" + "=" * 100)
    print("FORMAL INTERACTION TERM (from factorial_screener_analysis.py's OLS, if testable)")
    print("=" * 100)
    try:
        res = pd.read_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_regression_results_us.csv")
        inter = res[res["effect"].str.contains("pead_positive_surprise") &
                     res["effect"].str.contains("debt_reduction") &
                     res["effect"].str.contains(":")]
        if inter.empty:
            print("  Not enough both-fire symbol-years (<30) to test the interaction formally --")
            print("  falling back to the raw intersection comparison above as the only evidence available.")
        else:
            print(inter[["effect", "horizon", "coef", "se", "p", "p_fdr"]].to_string(index=False))
        for main_effect in ["pead_positive_surprise", "debt_reduction"]:
            row = res[res["effect"] == main_effect]
            if not row.empty:
                print(f"\n  {main_effect} main effect (holding all else fixed):")
                print(row[["horizon", "coef", "p_fdr"]].to_string(index=False))
    except FileNotFoundError:
        print("  factorial_regression_results_us.csv not found -- run factorial_screener_analysis.py first")


if __name__ == "__main__":
    main()
