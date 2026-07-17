#!/usr/bin/env python3
"""
blended_mpt_bandit_portfolio.py -- v5 "beat the market" line of work.

Blended 100-stock portfolio: 50 from the S&P 500 + 50 from the REST of
the US universe, walk-forward, no lookahead. Two axes tested together,
each isolated so the comparison shows which one (if either) actually
helps:

  SELECTION axis:
    RANDOM  -- uniformly sample 50+50 from each pool (matches this
               account's existing bandit_stock_selection.py random
               baseline convention, averaged over N_RANDOM_TRIALS seeds).
    BANDIT  -- walk-forward Thompson Sampling (Beta-Bernoulli, reward =
               beat SPY in PRIOR years only), run SEPARATELY within each
               pool so the 50+50 blend structure is always honored --
               same mechanics as bandit_stock_selection.py, just split
               into two independent arms-pools instead of one.

  WEIGHTING axis (Modern Portfolio Theory, Markowitz mean-variance):
    EQUAL   -- 1/100 each, the naive baseline.
    MAXSHARPE -- tangency portfolio via scipy SLSQP, IDENTICAL convention
               to this account's own portfolio_analysis.py
               (portfolio_stats/_neg_sharpe/optimise_portfolios, reused
               not reinvented): weights maximize (annualized return -
               risk-free rate) / annualized volatility, subject to
               weights >=0 and summing to 1 (long-only, no leverage).
               Covariance/mean estimated from the TRAILING year's daily
               returns only -- the optimizer never sees the year it's
               being scored on.

4 combinations x however many years are eligible, each compared to SPY.

S&P 500 MEMBERSHIP CAVEAT (stated up front): fetched from today's
Wikipedia constituent list (503 tickers, 500 matched to this account's
OHLCV universe), applied retroactively across 2017-2025 -- this is
CURRENT membership, not true point-in-time historical membership.
Survivorship bias in the S&P 500 pool specifically (today's constituents
were, almost by definition, winners that stayed large enough to remain
in the index) is a real, acknowledged limitation, not hidden.

LIQUIDITY GATE: same MIN_LOG_LIQUIDITY convention as consistency_
clustering.py/bandit_stock_selection.py (min ~$442k/day 63d dollar
volume), applied here too after the first run's "rest of universe" pool
(5,995 unfiltered symbols, no such gate) produced a portfolio return of
+1,603,920% in 2021 -- the same illiquid-OTC percentage-math explosion
already diagnosed and fixed twice this branch (v3's reversal screener,
the original v1 signal panel). The S&P 500 pool itself is inherently
large-cap/liquid and barely affected; this gate matters almost entirely
for the rest-of-universe pool.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from factorial_screener_test import load_ohlcv, BENCHMARK_SYMBOL

STOCK_YEARS_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/stock_level_consistency_us.parquet"
SP500_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/sp500_constituents.csv"
N_PER_POOL = 50
MIN_PRIOR_YEARS = 2
N_RANDOM_TRIALS = 50        # cheap equal-weight average -- more trials, more stable
N_RANDOM_TRIALS_MPT = 8     # each trial runs a 100-variable SLSQP optimization -- keep this small
SEED = 42
MIN_DOLLAR_VOL = 442000.0  # matches the log_liquidity>=13.0 gate used throughout v2-v4 (exp(13)-1)
TRADING_DAYS = 252
RISK_FREE_RATE = 0.04  # matches portfolio_analysis.py's convention (approx contemporary T-bill rate)


# ── Modern Portfolio Theory (reused verbatim from portfolio_analysis.py's ──
# ── own convention, not reinvented) ─────────────────────────────────────

def portfolio_stats(weights, mean_daily_returns, cov_daily):
    ret = float(np.dot(weights, mean_daily_returns) * TRADING_DAYS)
    vol = float(np.sqrt(weights @ cov_daily @ weights))
    sharpe = (ret - RISK_FREE_RATE) / vol if vol > 0 else 0.0
    return ret, vol, sharpe


def _neg_sharpe(w, mu, cov):
    _, _, s = portfolio_stats(w, mu, cov)
    return -s


def max_sharpe_weights(mean_daily_returns: np.ndarray, cov_annual: np.ndarray) -> np.ndarray:
    n = len(mean_daily_returns)
    w0 = np.full(n, 1 / n)
    bounds = [(0.0, 1.0)] * n
    sum_to_one = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
    res = minimize(_neg_sharpe, w0, args=(mean_daily_returns, cov_annual),
                    method="SLSQP", bounds=bounds, constraints=sum_to_one,
                    options={"ftol": 1e-10, "maxiter": 500})
    return res.x if res.success else w0


# ── Pool construction ────────────────────────────────────────────────────

def build_pools(ohlcv: pd.DataFrame) -> tuple[set, set]:
    sp500 = pd.read_csv(SP500_PATH)
    sp500_syms = set(sp500["Symbol"]) & set(ohlcv["Symbol"].unique())
    all_syms = set(ohlcv["Symbol"].unique()) - {BENCHMARK_SYMBOL}
    rest_syms = all_syms - sp500_syms
    print(f"S&P 500 pool: {len(sp500_syms)} matched symbols | Rest-of-universe pool: {len(rest_syms):,} symbols")
    return sp500_syms, rest_syms


# ── Selection: random vs walk-forward Thompson Sampling bandit ─────────────

def thompson_pick(pool: set, eligible_this_year: set, wins: dict, losses: dict, n: int, rng) -> list:
    candidates = [s for s in eligible_this_year if s in pool and (wins.get(s, 0) + losses.get(s, 0)) >= MIN_PRIOR_YEARS]
    if len(candidates) < n:
        return []
    samples = {s: rng.beta(1 + wins.get(s, 0), 1 + losses.get(s, 0)) for s in candidates}
    return list(pd.Series(samples).sort_values(ascending=False).head(n).index)


def random_pick(pool: set, eligible_this_year: set, n: int, rng) -> list:
    candidates = [s for s in eligible_this_year if s in pool]
    if len(candidates) < n:
        return []
    return list(rng.choice(candidates, size=n, replace=False))


# ── Portfolio return computation ────────────────────────────────────────

def portfolio_year_return(symbols: list, daily_by_year: dict, year: int, weights: np.ndarray | None) -> float:
    """Actual realized return of `symbols` (equal- or MPT-weighted) over `year`,
    using ONLY that year's realized daily returns -- no lookahead in the outcome,
    only in the WEIGHTS (which, if MPT, were fit on the prior year)."""
    rets = daily_by_year.get(year)
    if rets is None:
        return np.nan
    sub = rets[[s for s in symbols if s in rets.columns]].dropna(how="all")
    if sub.shape[1] < len(symbols) * 0.8:  # too many missing names this year
        return np.nan
    sub = sub.fillna(0.0)
    w = weights if weights is not None else np.full(sub.shape[1], 1 / sub.shape[1])
    w = w[:sub.shape[1]] / w[:sub.shape[1]].sum()
    port_daily = (sub.values * w).sum(axis=1)
    return float((1 + port_daily).prod() - 1) * 100


def main():
    ohlcv = load_ohlcv()
    ohlcv["year"] = ohlcv["Date"].dt.year
    ohlcv["daily_ret"] = ohlcv.groupby("Symbol")["Close"].pct_change()
    ohlcv.loc[ohlcv["likely_split"], "daily_ret"] = np.nan  # same split-exclusion convention as every other v-stage
    sp500_pool, rest_pool = build_pools(ohlcv)

    print("Pivoting daily returns by year (this takes a minute)...")
    daily_by_year = {}
    for yr, g in ohlcv.groupby("year"):
        daily_by_year[yr] = g.pivot_table(index="Date", columns="Symbol", values="daily_ret")

    stock_years = pd.read_parquet(STOCK_YEARS_PATH)
    bench_by_year = stock_years.groupby("year")["bench_return_pct"].first()
    # only years with BOTH a full daily panel AND a clean stock_level_consistency
    # summary -- avoids silently processing partial edge-of-panel years
    years = sorted(set(daily_by_year.keys()) & set(stock_years["year"].unique()))
    eligible_by_year = {yr: set(stock_years.loc[stock_years["year"] == yr, "Symbol"]) for yr in years}

    liquidity_by_symyear = ohlcv.groupby(["Symbol", "year"])["dollar_vol_63d"].mean()
    liquid_by_year = {
        yr: set(liquidity_by_symyear.xs(yr, level="year").loc[lambda s: s >= MIN_DOLLAR_VOL].index)
        for yr in years
    }
    print(f"Liquidity gate (avg 63d dollar volume >= ${MIN_DOLLAR_VOL:,.0f}/day): "
          f"e.g. {years[-1]} -> {len(liquid_by_year[years[-1]]):,} liquid symbols")

    seen_years = {}  # symbol -> count of years seen SO FAR (walk-forward eligibility)
    wins, losses = {}, {}
    rng_bandit = np.random.RandomState(SEED)
    rng_random = np.random.RandomState(SEED)

    rows = []
    for yr in years:
        eligible_now = {s for s, n in seen_years.items() if n >= MIN_PRIOR_YEARS} & liquid_by_year.get(yr, set())
        bench_ret = bench_by_year.get(yr, np.nan)

        if len(eligible_now & sp500_pool) >= N_PER_POOL and len(eligible_now & rest_pool) >= N_PER_POOL:
            # --- RANDOM selection, averaged over trials ---
            # equal-weight is cheap (no optimization) -- more trials for a stable
            # average; max_sharpe runs a 100-variable SLSQP per trial, so far fewer
            eq_rets, mpt_rets = [], []
            for trial in range(N_RANDOM_TRIALS):
                r1 = list(np.random.RandomState(SEED + trial).choice(list(eligible_now & sp500_pool), N_PER_POOL, replace=False))
                r2 = list(np.random.RandomState(SEED + 1000 + trial).choice(list(eligible_now & rest_pool), N_PER_POOL, replace=False))
                picks = r1 + r2
                eq_rets.append(portfolio_year_return(picks, daily_by_year, yr, None))
                if trial < N_RANDOM_TRIALS_MPT and yr - 1 in daily_by_year:
                    prior = daily_by_year[yr - 1][[s for s in picks if s in daily_by_year[yr - 1].columns]].dropna(axis=1, thresh=100)
                    if prior.shape[1] >= N_PER_POOL:
                        mu, cov = prior.mean().values, prior.cov().values * TRADING_DAYS
                        w = max_sharpe_weights(mu, cov)
                        mpt_rets.append(portfolio_year_return(list(prior.columns), daily_by_year, yr, w))
            rows.append({"year": yr, "selection": "random", "weighting": "equal", "port_ret": np.nanmean(eq_rets), "bench_ret": bench_ret})
            if mpt_rets:
                rows.append({"year": yr, "selection": "random", "weighting": "max_sharpe", "port_ret": np.nanmean(mpt_rets), "bench_ret": bench_ret})

            # --- BANDIT selection ---
            b1 = thompson_pick(sp500_pool, eligible_now, wins, losses, N_PER_POOL, rng_bandit)
            b2 = thompson_pick(rest_pool, eligible_now, wins, losses, N_PER_POOL, rng_bandit)
            if b1 and b2:
                picks = b1 + b2
                rows.append({"year": yr, "selection": "bandit", "weighting": "equal",
                              "port_ret": portfolio_year_return(picks, daily_by_year, yr, None), "bench_ret": bench_ret})
                if yr - 1 in daily_by_year:
                    prior = daily_by_year[yr - 1][[s for s in picks if s in daily_by_year[yr - 1].columns]].dropna(axis=1, thresh=100)
                    if prior.shape[1] >= N_PER_POOL:
                        mu, cov = prior.mean().values, prior.cov().values * TRADING_DAYS
                        w = max_sharpe_weights(mu, cov)
                        rows.append({"year": yr, "selection": "bandit", "weighting": "max_sharpe",
                                      "port_ret": portfolio_year_return(list(prior.columns), daily_by_year, yr, w), "bench_ret": bench_ret})
            print(f"  {yr}: eligible sp500={len(eligible_now & sp500_pool)}, rest={len(eligible_now & rest_pool)} -- ran")
        else:
            print(f"  {yr}: not enough eligible names yet, skipped")

        # update walk-forward state with THIS year's actual outcomes (for next year)
        for s in eligible_by_year.get(yr, []):
            seen_years[s] = seen_years.get(s, 0) + 1
        yr_outcomes = stock_years[stock_years["year"] == yr].set_index("Symbol")["beat_spy"]
        for s, beat in yr_outcomes.items():
            wins.setdefault(s, 0)
            losses.setdefault(s, 0)
            if beat:
                wins[s] += 1
            else:
                losses[s] += 1

    res = pd.DataFrame(rows)
    res["excess_ret"] = res["port_ret"] - res["bench_ret"]
    res["beat_spy"] = res["excess_ret"] > 0
    res.to_csv("/Users/umashankar/market-pipeline/code/python_files/cache_seed/blended_mpt_bandit_results_us.csv", index=False)

    print("\n" + "=" * 100)
    print(f"BLENDED 50 S&P500 + 50 REST-OF-UNIVERSE PORTFOLIO -- vs {BENCHMARK_SYMBOL}, walk-forward")
    print("=" * 100)
    pd.set_option("display.width", 140)
    for sel in ["random", "bandit"]:
        for wt in ["equal", "max_sharpe"]:
            sub = res[(res["selection"] == sel) & (res["weighting"] == wt)]
            if sub.empty:
                continue
            print(f"\n{sel} / {wt} (n years={len(sub)}):")
            print(sub[["year", "port_ret", "bench_ret", "excess_ret", "beat_spy"]].round(2).to_string(index=False))
            print(f"  avg hit rate: {sub['beat_spy'].mean()*100:.1f}% | avg excess: {sub['excess_ret'].mean():+.2f}pp | "
                  f"avg port return: {sub['port_ret'].mean():+.2f}% | avg SPY return: {sub['bench_ret'].mean():+.2f}%")

    print(f"\nSaved -> cache_seed/blended_mpt_bandit_results_us.csv")


if __name__ == "__main__":
    main()
