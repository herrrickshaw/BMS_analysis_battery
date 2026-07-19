#!/usr/bin/env python3
"""
train_ppo_factor_weights.py -- Phase 3 (driver half) + Phase 4 (validation)
of PPO regime-conditional factor-weight scoring (see /Users/umashankar/
.claude/plans/bright-hatching-scone.md).

CLI: --market {us,india}. Trains ONE policy per market (never pooled --
the plan is explicit that India's much thinner sample would be dominated
by the US's if combined).

DATA PREP (this file, not regime_weighted_score_env.py -- the env takes a
ready-made df, it doesn't fetch prices):
  - Loads factor_zscore_panel_regime.parquet (Phase 1+2 output), filters to
    one market, drops UNKNOWN-regime rows (no benchmark to classify them
    against -- excluded, not imputed, per regime_tag_panel.py's own
    convention).
  - Attaches raw forward return via factorial_screener_test.py's OWN
    forward_returns()/attach_forward_returns() machinery (split-day
    exclusion, trading-day offsets) -- REUSED, not reimplemented, same
    discipline as every other script this session. Needs a `signals`-
    shaped frame (symbol=ticker, signal_date=filed) as that function's
    expected input shape.

    HORIZON: T+63d (~3 months), NOT reward_screener_opt.py's own default
    of 252d -- changed after a T+252d dry run on India (2026-07-19) showed
    only 494/2,942 regime-known rows survive a full year-ahead requirement,
    because the OHLCV panel ends 2026-07-02: any filing in the last ~12
    months of the panel has no T+252d window at all. That collapsed the
    chronological test split to 98 rows spanning one month, 97 of them
    BULL -- unusable for a bull-vs-bear comparison. T+63d keeps far more
    rows and a wider date spread. The plan only specified reusing the
    cohort-demeaning FORMULA, not the specific horizon -- this is a
    data-driven choice, not a deviation from anything the plan actually
    pinned down.
  - `excess`/`excess_w`: reward_screener_opt.py's own cohort-neutral
    convention (raw forward return minus the SAME entry-year median,
    winsorized at 1/99pct for the mean stat only) -- computed here directly
    on the raw return rather than the SPY-relative xret, because that's
    the literal formula in the script the approved plan named as the reward
    to reuse; the entry-year demeaning is itself already a market-drift
    control, distinct from (and, by using this panel's own universe median
    rather than a cap-weighted index, arguably better matched to) the
    S&P-500 benchmarking used everywhere else in this codebase.
  - Chronological 80/20 split on `filed` (TRAIN before the cutoff, TEST
    after) -- same convention as backtest_weight_optimization.py.

TRAINING: stable_baselines3 PPO, MlpPolicy, on RegimeWeightedScoreEnv
wrapping the TRAIN split only.

VALIDATION (Phase 4): evaluate the trained policy's per-regime weight
vector (deterministic action from a pure one-hot observation) via
env.score_and_reward() on BOTH splits -- reports train vs test reward
prominently, a large gap being itself the headline finding (overfitting),
not a footnote. Compared against an equal-weight baseline and a greedy
single-best-factor baseline (chosen by TRAIN reward, evaluated OOS on
TEST) -- both computed with the exact same score_and_reward() logic so the
comparison is apples-to-apples.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
import factorial_screener_test as fst  # noqa: E402
import factorial_screener_test_IN as fst_in  # noqa: E402
from regime_weighted_score_env import (  # noqa: E402
    REGIMES, RegimeWeightedScoreEnv, softmax_weights,
)

PANEL_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factor_zscore_panel_regime.parquet"
FORWARD_HORIZON_LABEL = "T+63d"  # see module docstring: T+252d left too little usable data
TEST_FRACTION = 0.20
TOTAL_TIMESTEPS = 50_000
MIN_N = 30

# local copies -- BENCHMARK_SYMBOL_US/_IN, same footgun-avoidance as
# regime_tag_panel.py (importing factorial_screener_test_IN clobbers
# fst.BENCHMARK_SYMBOL as a module-level side effect)
BENCHMARK_SYMBOL_US = "SPY"
BENCHMARK_SYMBOL_IN = fst_in.BENCHMARK_SYMBOL_IN

CURATED_FACTORS_COMMON = [
    "pb_ratio", "pe_ttm", "roe", "roic", "operating_margin", "net_margin",
    "de_ratio", "rev_growth", "eps_growth", "ebit_growth",
]
US_ONLY_FACTORS = ["fcf_yield"]


def load_market_ohlcv(market: str) -> pd.DataFrame:
    if market == "us":
        return fst.load_ohlcv()
    return fst_in.load_ohlcv_in()


def attach_forward_return(df: pd.DataFrame, ohlcv: pd.DataFrame, market: str) -> pd.DataFrame:
    signals = df[["ticker", "filed"]].rename(columns={"ticker": "symbol", "filed": "signal_date"}).copy()
    signals["signal_date"] = pd.to_datetime(signals["signal_date"])
    lookups = fst.forward_returns(ohlcv)
    bench_symbol = BENCHMARK_SYMBOL_US if market == "us" else BENCHMARK_SYMBOL_IN
    # NEVER call fst.benchmark_lookup() here -- it reads the mutable
    # fst.BENCHMARK_SYMBOL global, which importing factorial_screener_test_IN
    # clobbers to "NIFTYBEES" as a module-level side effect (hit this exact
    # bug on the first US run: it tried to look up NIFTYBEES in the US OHLCV
    # panel and crashed). _bench_lookup() below is the same logic, keyed off
    # the local BENCHMARK_SYMBOL_US/_IN constants instead.
    bench = _bench_lookup(ohlcv, bench_symbol)
    signals = fst.attach_forward_returns(signals, lookups, bench)
    out = df.copy()
    out["ret"] = signals[f"ret_{FORWARD_HORIZON_LABEL}"].to_numpy()
    return out


def _bench_lookup(ohlcv: pd.DataFrame, symbol: str) -> tuple:
    """India equivalent of fst.benchmark_lookup() -- that function is
    hardcoded to BENCHMARK_SYMBOL (a mutable global this file deliberately
    does not touch, see module docstring)."""
    g = ohlcv[ohlcv["Symbol"] == symbol].sort_values("Date").reset_index(drop=True)
    if g.empty:
        raise ValueError(f"{symbol} not found in this OHLCV panel")
    return g["Date"].values, g["Close"].values, g["likely_split"].values


def compute_excess_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.dropna(subset=["ret"]).copy()
    out["entry_year"] = pd.to_datetime(out["filed"]).dt.year
    lo, hi = out["ret"].quantile([0.01, 0.99])
    out["ret_w"] = out["ret"].clip(lo, hi)
    out["excess"] = out["ret"] - out.groupby("entry_year")["ret"].transform("median")
    out["excess_w"] = out["ret_w"] - out.groupby("entry_year")["ret_w"].transform("median")
    return out


def chronological_split(df: pd.DataFrame, test_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values("filed")
    cutoff = df["filed"].quantile(1 - test_fraction)
    train = df[df["filed"] <= cutoff]
    test = df[df["filed"] > cutoff]
    return train, test


def equal_weight_baseline(env: RegimeWeightedScoreEnv, n_factors: int) -> dict:
    w = np.full(n_factors, 1.0 / n_factors)
    return {r: env.score_and_reward(r, w) for r in REGIMES}


def best_single_factor_baseline(train_env: RegimeWeightedScoreEnv, test_env: RegimeWeightedScoreEnv,
                                 factors: list[str]) -> dict:
    """Greedy 1-factor screener: pick, PER REGIME, whichever single factor
    gives the best TRAIN reward, then report its OOS TEST reward -- the
    simplest possible baseline the PPO-tuned composite has to beat."""
    out = {}
    for r in REGIMES:
        best_f, best_train_rew = None, -np.inf
        for i, f in enumerate(factors):
            w = np.zeros(len(factors))
            w[i] = 1.0
            rew, _ = train_env.score_and_reward(r, w)
            if rew > best_train_rew:
                best_train_rew, best_f = rew, f
        if best_f is None:
            out[r] = {"factor": None, "train": (0.0, {}), "test": (0.0, {})}
            continue
        w = np.zeros(len(factors))
        w[factors.index(best_f)] = 1.0
        out[r] = {
            "factor": best_f,
            "train": (best_train_rew, {}),
            "test": test_env.score_and_reward(r, w),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["us", "india"], required=True)
    ap.add_argument("--timesteps", type=int, default=TOTAL_TIMESTEPS)
    args = ap.parse_args()

    factors = CURATED_FACTORS_COMMON + (US_ONLY_FACTORS if args.market == "us" else [])

    print(f"=== {args.market.upper()}: loading panel + forward returns ===")
    panel = pd.read_parquet(PANEL_PATH)
    df = panel[(panel["market"] == args.market) & (panel["regime"] != "UNKNOWN")].copy()
    print(f"  {len(df):,} regime-known rows before forward-return attach")

    ohlcv = load_market_ohlcv(args.market)
    df = attach_forward_return(df, ohlcv, args.market)
    df = compute_excess_columns(df)
    print(f"  {len(df):,} rows with a valid {FORWARD_HORIZON_LABEL} forward return")
    print(f"  regime distribution: {df['regime'].value_counts().to_dict()}")

    train_df, test_df = chronological_split(df, TEST_FRACTION)
    print(f"\n  TRAIN: {len(train_df):,} rows, {train_df['filed'].min().date()} to {train_df['filed'].max().date()}")
    print(f"  TEST:  {len(test_df):,} rows, {test_df['filed'].min().date() if len(test_df) else 'n/a'} "
          f"to {test_df['filed'].max().date() if len(test_df) else 'n/a'}")
    print("  TRAIN regime counts:", train_df["regime"].value_counts().to_dict())
    print("  TEST  regime counts:", test_df["regime"].value_counts().to_dict())

    train_env = Monitor(RegimeWeightedScoreEnv(train_df, factors, min_n=MIN_N, seed=42))
    test_env_raw = RegimeWeightedScoreEnv(test_df, factors, min_n=MIN_N, seed=43)

    print(f"\n=== Training PPO ({args.timesteps:,} timesteps, {len(factors)} factors) ===")
    model = PPO("MlpPolicy", train_env, verbose=0, seed=42, n_steps=256, batch_size=64)
    model.learn(total_timesteps=args.timesteps)

    print("\n=== Per-regime PPO weight vectors + train/test reward ===")
    ppo_weights = {}
    for r in REGIMES:
        oh = np.zeros(3, dtype=np.float32)
        oh[REGIMES.index(r)] = 1.0
        action, _ = model.predict(oh, deterministic=True)
        weights = softmax_weights(np.asarray(action, dtype=np.float64))
        ppo_weights[r] = weights
        train_rew, train_info = RegimeWeightedScoreEnv(train_df, factors, min_n=MIN_N).score_and_reward(r, weights)
        test_rew, test_info = test_env_raw.score_and_reward(r, weights)
        print(f"\n  {r}:")
        for f, w in sorted(zip(factors, weights), key=lambda x: -x[1]):
            print(f"    {f:<20s} {w:6.3f}")
        train_note = train_info.get("note")
        test_note = test_info.get("note")
        print(f"    TRAIN reward (median excess): {train_rew:+.4f}  "
              f"({train_info.get('n', 0)} names{', ' + train_note if train_note else ' in top decile'})")
        print(f"    TEST  reward (median excess): {test_rew:+.4f}  "
              f"({test_info.get('n', 0)} names{', ' + test_note if test_note else ' in top decile'})")
        if train_note or test_note:
            print("    NOTE: a 0.0000 reward above a min_n floor note is a DATA-SCARCITY ARTIFACT "
                  "(too few rows to trust a top-decile cut), not a genuine null result.")
        else:
            gap = train_rew - test_rew
            print(f"    TRAIN-TEST gap: {gap:+.4f} {'<-- LARGE, possible overfit' if abs(gap) > 0.05 else ''}")

    print("\n=== Baseline: equal-weight composite ===")
    eq_train = equal_weight_baseline(RegimeWeightedScoreEnv(train_df, factors, min_n=MIN_N), len(factors))
    eq_test = equal_weight_baseline(test_env_raw, len(factors))
    for r in REGIMES:
        print(f"  {r}: TRAIN {eq_train[r][0]:+.4f}  TEST {eq_test[r][0]:+.4f}")

    print("\n=== Baseline: greedy single-best-factor screener ===")
    single = best_single_factor_baseline(
        RegimeWeightedScoreEnv(train_df, factors, min_n=MIN_N), test_env_raw, factors)
    for r in REGIMES:
        s = single[r]
        print(f"  {r}: best factor = {s['factor']}  TRAIN {s['train'][0]:+.4f}  TEST {s['test'][0]:+.4f}")

    print("\n=== Summary: does PPO beat the baselines OOS (TEST reward)? ===")
    for r in REGIMES:
        ppo_test, _ = test_env_raw.score_and_reward(r, ppo_weights[r])
        print(f"  {r}: PPO {ppo_test:+.4f}  vs equal-weight {eq_test[r][0]:+.4f}  "
              f"vs single-factor({single[r]['factor']}) {single[r]['test'][0]:+.4f}  "
              f"-> PPO wins: {ppo_test > eq_test[r][0] and ppo_test > single[r]['test'][0]}")

    out_path = f"/Users/umashankar/market-pipeline/code/python_files/cache_seed/ppo_factor_weights_{args.market}.npz"
    np.savez(out_path, factors=factors, **{f"weights_{r}": ppo_weights[r] for r in REGIMES})
    print(f"\nSaved PPO weight vectors -> {out_path}")


if __name__ == "__main__":
    main()
