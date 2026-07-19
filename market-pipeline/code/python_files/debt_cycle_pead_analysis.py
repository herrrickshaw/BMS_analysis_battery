#!/usr/bin/env python3
"""
debt_cycle_pead_analysis.py -- does a company's DEBT CYCLE position (multi-
year deleveraging streak, not just single-year debt_reduction_pass) combined
with operating profit growth translate into a STRONGER post-earnings-
announcement drift (PEAD)?

US ONLY. India's fundamentals history is too thin for a multi-year cycle
classification (Explore-agent survey, 2026-07-19: 0 India tickers reach a
5-year consecutive debt-history run, vs 1,103 in the US) -- a "cycle" needs
several consecutive years per ticker, not one YoY comparison.

DATA SOURCES, both already collected (recovered 2026-07-19 from the
unmerged claude/event-driven-stock-news-msv0cq branch, not re-collected):
  - fundamentals_history/US.parquet (SEC EDGAR, this session's own recovery
    of the 7 missing balance-sheet fields) -> debt cycle + operating profit
    growth, via compute_fundamental_screens()
  - cache_seed/earnings_price_dataset/US.parquet -- REAL earnings dates,
    REAL analyst-consensus-relative surprise_pct, REAL 1d/5d/21d forward
    price moves (yfinance Ticker.earnings_dates + SEC 8-K Item 2.02 dates,
    consolidated by earnings_price_dataset.py). This replaces
    pead_positive_surprise_pass's coarse `ni_growth > 0` annual proxy with
    the real thing -- a quarterly, consensus-relative surprise measure.

METHODOLOGY:
  1. deleveraging_streak: consecutive fiscal years (ending at this filing,
     inclusive) where total_debt_strict declined YoY. This is the genuine
     multi-year "cycle position" the user asked for -- distinct from
     debt_reduction_pass (a single-year >10% YoY cut).
  2. Point-in-time join: each earnings announcement gets the ticker's LATEST
     fiscal filing STRICTLY BEFORE the announcement date (merge_asof,
     direction='backward') -- no lookahead, same discipline as
     attach_market_cap() elsewhere in this codebase.
  3. PEAD proper: restrict to POSITIVE-surprise announcements (surprise_pct
     > 0) -- the classic "drift continues after a positive surprise"
     definition (Bernard & Thomas 1989), not just "any earnings event."
  4. Compare mean/median price_change_5d and price_change_21d between
     positive-surprise events where the company was ALSO mid deleveraging-
     streak + growing operating profit, vs positive-surprise events where
     it wasn't -- plus a Mann-Whitney U test (returns are fat-tailed, not
     assumed normal) alongside the mean-difference t-test.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
import factorial_screener_test as fst  # noqa: E402

EARNINGS_PRICE_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/earnings_price_dataset/US.parquet"
STREAK_THRESHOLD = 3  # "sustained" deleveraging: 3+ consecutive years of debt decline


def build_debt_cycle(scored: pd.DataFrame) -> pd.DataFrame:
    """Consecutive-years-of-declining-debt streak, per (ticker, fy_end).
    A break (debt flat/rising, or debt_change_pct missing) resets the
    streak to 0 -- this is a genuine multi-year cycle-position measure,
    not the single-year debt_reduction_pass gate (>10% one-year cut)."""
    df = scored.sort_values(["ticker", "fy_end"]).copy()
    declining = (df["debt_change_pct"] < 0).fillna(False)
    # reset-on-break cumulative count, per ticker: group by (ticker, breaks-so-far)
    breaks = (~declining).groupby(df["ticker"]).cumsum()
    df["deleveraging_streak"] = declining.groupby([df["ticker"], breaks]).cumcount() + 1
    df["deleveraging_streak"] = df["deleveraging_streak"].where(declining, 0)
    df["sustained_deleveraging"] = (df["deleveraging_streak"] >= STREAK_THRESHOLD).astype(int)
    df["debt_cycle_and_opgrowth"] = (
        (df["sustained_deleveraging"] == 1) & (df["operating_profit_growth_pass"] == 1)
    ).astype(int)
    return df


def main():
    print("Loading US fundamentals, computing debt-cycle position...")
    fund = fst.load_fundamentals()
    scored = fst.compute_fundamental_screens(fund)
    scored = build_debt_cycle(scored)

    n_complete = scored["total_debt_strict"].notna().sum()
    print(f"  {n_complete:,}/{len(scored):,} rows have complete debt data")
    print("  deleveraging_streak distribution (non-zero only):")
    print(scored.loc[scored["deleveraging_streak"] > 0, "deleveraging_streak"].value_counts().sort_index())
    print(f"  sustained_deleveraging (>={STREAK_THRESHOLD}y): {scored['sustained_deleveraging'].sum():,} filings, "
          f"{scored.loc[scored['sustained_deleveraging']==1, 'ticker'].nunique():,} unique tickers")
    print(f"  debt_cycle_and_opgrowth (sustained deleveraging AND opgrowth this year): "
          f"{scored['debt_cycle_and_opgrowth'].sum():,} filings, "
          f"{scored.loc[scored['debt_cycle_and_opgrowth']==1, 'ticker'].nunique():,} unique tickers")

    keep_cols = ["ticker", "fy_end", "filed", "sustained_deleveraging",
                 "deleveraging_streak", "operating_profit_growth_pass", "debt_cycle_and_opgrowth"]
    cycle = scored[keep_cols].dropna(subset=["filed"]).sort_values(["ticker", "filed"]).reset_index(drop=True)

    print("\nLoading real earnings-price dataset (actual dates + consensus-relative surprise%)...")
    ep = pd.read_parquet(EARNINGS_PRICE_PATH)
    ep = ep[ep["market"] == "US"].copy()
    ep["earnings_date"] = pd.to_datetime(ep["earnings_date"]).dt.tz_localize(None)
    print(f"  {len(ep):,} announcement rows, {ep['ticker'].nunique():,} tickers, "
          f"{ep['earnings_date'].min().date()} to {ep['earnings_date'].max().date()}")

    print("\nPoint-in-time join: each announcement -> latest fiscal filing strictly before it...")
    ep_sorted = ep.sort_values("earnings_date").reset_index(drop=True)
    cycle_sorted = cycle.rename(columns={"filed": "earnings_date"}).sort_values("earnings_date")
    merged = pd.merge_asof(
        ep_sorted, cycle_sorted, on="earnings_date", by="ticker",
        direction="backward", tolerance=pd.Timedelta(days=548),  # <=18mo stale filing tolerance
    )
    matched = merged["sustained_deleveraging"].notna().sum()
    print(f"  {matched:,}/{len(merged):,} announcements matched to a recent-enough fundamentals filing")

    merged["debt_cycle_and_opgrowth"] = merged["debt_cycle_and_opgrowth"].fillna(0)

    print("\n" + "=" * 100)
    print(f"PEAD TEST -- positive-surprise announcements only (surprise_pct > 0)")
    print("=" * 100)
    pos = merged[(merged["surprise_pct"] > 0) & merged["sustained_deleveraging"].notna()].copy()
    print(f"n = {len(pos):,} positive-surprise, fundamentals-matched announcements "
          f"({pos['ticker'].nunique():,} tickers)")

    for horizon in ["price_change_5d", "price_change_21d"]:
        treat = pos.loc[pos["debt_cycle_and_opgrowth"] == 1, horizon].dropna()
        ctrl = pos.loc[pos["debt_cycle_and_opgrowth"] == 0, horizon].dropna()
        if len(treat) < 5:
            print(f"\n{horizon}: n_treat={len(treat)} -- too few for a meaningful test")
            continue
        t_stat, t_p = stats.ttest_ind(treat, ctrl, equal_var=False)
        u_stat, u_p = stats.mannwhitneyu(treat, ctrl, alternative="two-sided")
        print(f"\n{horizon}:")
        print(f"  debt_cycle_and_opgrowth=1: n={len(treat):,}  mean={treat.mean():+.2f}%  median={treat.median():+.2f}%")
        print(f"  debt_cycle_and_opgrowth=0: n={len(ctrl):,}  mean={ctrl.mean():+.2f}%  median={ctrl.median():+.2f}%")
        print(f"  difference in means: {treat.mean()-ctrl.mean():+.2f}pp   "
              f"Welch t-test p={t_p:.4f}   Mann-Whitney p={u_p:.4f}")

    print("\n" + "=" * 100)
    print("Same test using sustained_deleveraging ALONE (no operating-profit-growth requirement)")
    print("=" * 100)
    for horizon in ["price_change_5d", "price_change_21d"]:
        treat = pos.loc[pos["sustained_deleveraging"] == 1, horizon].dropna()
        ctrl = pos.loc[pos["sustained_deleveraging"] == 0, horizon].dropna()
        if len(treat) < 5:
            print(f"\n{horizon}: n_treat={len(treat)} -- too few for a meaningful test")
            continue
        t_stat, t_p = stats.ttest_ind(treat, ctrl, equal_var=False)
        u_stat, u_p = stats.mannwhitneyu(treat, ctrl, alternative="two-sided")
        print(f"\n{horizon}:")
        print(f"  sustained_deleveraging=1: n={len(treat):,}  mean={treat.mean():+.2f}%  median={treat.median():+.2f}%")
        print(f"  sustained_deleveraging=0: n={len(ctrl):,}  mean={ctrl.mean():+.2f}%  median={ctrl.median():+.2f}%")
        print(f"  difference in means: {treat.mean()-ctrl.mean():+.2f}pp   "
              f"Welch t-test p={t_p:.4f}   Mann-Whitney p={u_p:.4f}")

    out_path = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/debt_cycle_pead_merged.parquet"
    merged.to_parquet(out_path, index=False)
    print(f"\nSaved merged dataset -> {out_path}")


if __name__ == "__main__":
    main()
