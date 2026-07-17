#!/usr/bin/env python3
"""
bandit_stock_selection.py -- v2 "beat the market" line of work.

Reward-optimization technique: walk-forward Thompson Sampling (Beta-
Bernoulli multi-armed bandit) over stocks-as-arms, reward = did this
stock beat SPY in a given calendar year (from stock_level_consistency.py's
stock-year table, NOT screener-conditioned). Compared against a RANDOM-
SELECTION baseline and a naive equal-weight-the-whole-universe baseline,
exactly as asked.

WALK-FORWARD, NO LOOKAHEAD: at the start of year t, each arm's posterior
Beta(alpha, beta) is built ONLY from that stock's beat/lose record in
years < t (alpha=1+wins, beta=1+losses, Beta(1,1) uninformative prior).
Every stock present in year t has its outcome recorded into that
posterior for year t+1 regardless of whether it was actually selected
that year (an arm's own track record doesn't depend on whether the
bandit happened to pick it) -- outcome recording and portfolio selection
are two separate steps, not conditional on each other.

LIQUIDITY GATE + WINSORIZE (2026-07-17, added after the first run):
stock_level_consistency.py's raw yearly data includes a handful of OTC/
micro-cap tickers with 1,000-30,000% single-year "returns" even after
split-day exclusion (consistent with this account's own established
finding that illiquid names are where extreme, hard-to-trade numbers
concentrate). hit_rate is sign-only and unaffected, but mean excess
return is not -- the first run of this script reported a "random"
baseline average excess of +1,001pp, which is not a real, tradeable
number, just outlier contamination. Fixed two ways: (1) the eligible
universe is liquidity-gated the same way as consistency_clustering.py,
(2) excess returns are winsorized at the 1st/99th percentile (same
convention as factorial_screener_analysis.py) before averaging for
the REPORTED mean-excess figures.

CANDIDATE UNIVERSE CAVEAT: with ~8 usable years and thousands of stocks,
most arms get pulled 0-1 times each -- a real, honest power limitation of
applying a bandit to a short annual time series, not a flaw unique to
this implementation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factorial_screener_analysis import SIGNALS_PATH, build_symbol_year_table, winsorize

STOCK_YEARS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/stock_level_consistency_us.parquet"
K_PORTFOLIO = 30
MIN_PRIOR_YEARS = 2
N_RANDOM_TRIALS = 200
SEED = 42
MIN_LOG_LIQUIDITY = 13.0  # same gate as consistency_clustering.py


def load_liquidity_gated_stock_years() -> pd.DataFrame:
    stock_years = pd.read_parquet(STOCK_YEARS_PATH)
    signals = pd.read_parquet(SIGNALS_PATH)
    sy = build_symbol_year_table(signals)
    liquidity = sy.groupby(["symbol", "year"])["log_liquidity"].mean().reset_index()
    merged = stock_years.merge(liquidity, left_on=["Symbol", "year"], right_on=["symbol", "year"], how="inner")
    before = merged["Symbol"].nunique()
    merged = merged[merged["log_liquidity"] >= MIN_LOG_LIQUIDITY]
    print(f"Liquidity gate: {before:,} -> {merged['Symbol'].nunique():,} distinct symbols across all years "
          f"({len(merged):,} stock-year rows)")
    merged["excess_return_pct_w"] = winsorize(merged["excess_return_pct"])
    return merged


def run_thompson(stock_years: pd.DataFrame, years: list) -> pd.DataFrame:
    wins, losses = {}, {}
    rng = np.random.RandomState(SEED)
    rows = []
    for t in years:
        this_year = stock_years[stock_years["year"] == t]
        history_syms = [s for s in wins if (wins[s] + losses[s]) >= MIN_PRIOR_YEARS]
        eligible = this_year[this_year["Symbol"].isin(history_syms)]
        if len(eligible) >= K_PORTFOLIO:
            samples = {s: rng.beta(1 + wins[s], 1 + losses[s]) for s in eligible["Symbol"]}
            picked = pd.Series(samples).sort_values(ascending=False).head(K_PORTFOLIO).index
            outcomes = eligible.set_index("Symbol").loc[picked]
            rows.append({"year": t, "strategy": "thompson_sampling", "n_eligible": len(eligible),
                         "portfolio_hit_rate": outcomes["beat_spy"].mean() * 100,
                         "portfolio_mean_excess": outcomes["excess_return_pct_w"].mean()})
        # outcome recording is UNCONDITIONAL -- every stock present this year updates its
        # own posterior for next year, whether or not it was in this year's picked-K
        for s, row in this_year.set_index("Symbol").iterrows():
            wins.setdefault(s, 0)
            losses.setdefault(s, 0)
            if row["beat_spy"]:
                wins[s] += 1
            else:
                losses[s] += 1
    return pd.DataFrame(rows)


def run_random(stock_years: pd.DataFrame, years: list) -> pd.DataFrame:
    seen_years = {}
    rows = []
    for t in years:
        this_year = stock_years[stock_years["year"] == t]
        eligible_syms = [s for s in seen_years if seen_years[s] >= MIN_PRIOR_YEARS]
        eligible = this_year[this_year["Symbol"].isin(eligible_syms)]
        for s in this_year["Symbol"]:
            seen_years[s] = seen_years.get(s, 0) + 1
        if len(eligible) < K_PORTFOLIO:
            continue
        trial_hits, trial_excess = [], []
        for trial in range(N_RANDOM_TRIALS):
            picked = eligible.sample(n=K_PORTFOLIO, random_state=SEED + trial)
            trial_hits.append(picked["beat_spy"].mean() * 100)
            trial_excess.append(picked["excess_return_pct_w"].mean())
        rows.append({"year": t, "strategy": "random", "n_eligible": len(eligible),
                     "portfolio_hit_rate": np.mean(trial_hits), "portfolio_mean_excess": np.mean(trial_excess)})
    return pd.DataFrame(rows)


def run_equal_weight_universe(stock_years: pd.DataFrame, years: list) -> pd.DataFrame:
    """Sanity-check baseline: what if you just held the entire eligible
    universe equal-weighted, no selection at all?"""
    seen_years = {}
    rows = []
    for t in years:
        this_year = stock_years[stock_years["year"] == t]
        eligible_syms = [s for s in seen_years if seen_years[s] >= MIN_PRIOR_YEARS]
        eligible = this_year[this_year["Symbol"].isin(eligible_syms)]
        for s in this_year["Symbol"]:
            seen_years[s] = seen_years.get(s, 0) + 1
        if len(eligible) < K_PORTFOLIO:
            continue
        rows.append({"year": t, "strategy": "equal_weight_universe", "n_eligible": len(eligible),
                     "portfolio_hit_rate": eligible["beat_spy"].mean() * 100,
                     "portfolio_mean_excess": eligible["excess_return_pct_w"].mean()})
    return pd.DataFrame(rows)


def main():
    stock_years = load_liquidity_gated_stock_years()
    years = sorted(stock_years["year"].unique())
    print(f"Years available: {years}")

    ts = run_thompson(stock_years, years)
    rand = run_random(stock_years, years)
    ew = run_equal_weight_universe(stock_years, years)

    combined = pd.concat([ts, rand, ew], ignore_index=True)
    combined.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/bandit_stock_selection_us.csv", index=False)

    print("\n" + "=" * 100)
    print(f"WALK-FORWARD PORTFOLIO SELECTION -- Thompson Sampling vs Random vs Equal-Weight Universe "
          f"(K={K_PORTFOLIO} stocks/year, liquidity-gated, excess winsorized)")
    print("=" * 100)
    pd.set_option("display.width", 140)
    piv_hit = combined.pivot(index="year", columns="strategy", values="portfolio_hit_rate")
    piv_ex = combined.pivot(index="year", columns="strategy", values="portfolio_mean_excess")
    print("\nHit rate (% of K stocks beating SPY that year):")
    print(piv_hit.round(1).to_string())
    print("\nMean excess return, winsorized (pct pts):")
    print(piv_ex.round(2).to_string())

    print("\nAcross all evaluated years (equal-weighted by year, not by stock-count):")
    for strat in ["thompson_sampling", "random", "equal_weight_universe"]:
        sub = combined[combined["strategy"] == strat]
        if sub.empty:
            print(f"  {strat}: no years met the K-eligible threshold")
            continue
        print(f"  {strat}: avg hit rate {sub['portfolio_hit_rate'].mean():.1f}%, "
              f"avg mean excess {sub['portfolio_mean_excess'].mean():+.2f}pp, "
              f"years evaluated {len(sub)}")

    print(f"\nSaved -> cache_seed/bandit_stock_selection_us.csv")


if __name__ == "__main__":
    main()
