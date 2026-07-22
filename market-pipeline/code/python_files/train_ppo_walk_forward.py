#!/usr/bin/env python3
"""
train_ppo_walk_forward.py -- Stages 2+3 extending Phase 3/4 of the PPO
factor-weight plan (/Users/umashankar/.claude/plans/bright-hatching-scone.md):
walk-forward (multi-fold) validation + shrinkage toward equal-weight,
addressing the overfitting Phase 4's single 80/20 split revealed (large
TRAIN-TEST gaps, corner-solution weight vectors -- e.g. US BULL put 96% of
weight on just 2 of 11 factors).

STAGE 1 (entropy regularization, tried first via train_ppo_factor_weights.
py's --ent-coef): a documented NEGATIVE result. ent_coef=0.05 on US barely
moved weight concentration (BULL effective-factors 2.00->2.14) and made
BEAR's TRAIN-TEST gap WORSE (2.07->9.45pp). PPO's entropy bonus only adds
noise to the STOCHASTIC action distribution during training -- it doesn't
change where the DETERMINISTIC policy mean (what score_and_reward always
evaluates, deterministic=True) converges, so it can't fix a reward
landscape that genuinely rewards a 2-factor corner solution in-sample.

This file implements two fixes that actually change what's being
optimized/evaluated, not just how noisily training explores:

  1. WALK-FORWARD: K sequential (train, test) folds with an EXPANDING
     train window, instead of Phase 4's one 80/20 split. That single test
     window was itself thin (India: 98-152 rows spanning 1-3.5 months) --
     any one fold's OOS number is partly luck. Reports the reward
     DISTRIBUTION (mean +/- std) across folds, not a single draw.
  2. SHRINKAGE: blend the PPO-learned weight vector w_ppo with the
     equal-weight vector w_eq: w = alpha*w_ppo + (1-alpha)*w_eq, re-
     normalized. Standard fix for an overfit estimated weight vector on a
     small sample (same idea as Ledoit-Wolf shrinkage for a covariance
     matrix) -- it MECHANICALLY reduces concentration (unlike entropy
     regularization, which measurably didn't), and alpha=0 recovers
     equal-weight exactly. Evaluated across a FIXED grid of alphas
     (0/0.25/0.5/0.75/1.0), not a single tuned value -- tuning alpha to
     maximize reward on the same folds it's scored on would just relocate
     the overfitting into alpha-selection instead of removing it. Whether
     OOS reward improves monotonically as alpha shrinks toward 0 is
     itself the finding.

REUSE: load_market_ohlcv(), attach_forward_return(), compute_excess_
columns(), PANEL_PATH, CURATED_FACTORS_COMMON, US_ONLY_FACTORS, MIN_N are
all imported from train_ppo_factor_weights.py verbatim -- same data prep,
not reimplemented.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
from train_ppo_factor_weights import (  # noqa: E402
    PANEL_PATH, CURATED_FACTORS_COMMON, US_ONLY_FACTORS, MIN_N,
    load_market_ohlcv, attach_forward_return, compute_excess_columns,
)
from regime_weighted_score_env import REGIMES, RegimeWeightedScoreEnv, softmax_weights  # noqa: E402

SHRINK_ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0]  # 0.0 = pure equal-weight, 1.0 = pure PPO
TIMESTEPS_PER_FOLD = 30_000


def walk_forward_folds(df: pd.DataFrame, k: int) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """K sequential (train, test) folds, EXPANDING train window: the date
    range is cut into k equal-ROW-COUNT slices; fold i's test is slice i,
    fold i's train is every row strictly before that slice. Fold 0 has no
    prior data and is skipped (nothing to train on)."""
    df = df.sort_values("filed").reset_index(drop=True)
    n = len(df)
    edges = [int(round(n * i / k)) for i in range(k + 1)]
    folds = []
    for i in range(1, k):
        train = df.iloc[:edges[i]]
        test = df.iloc[edges[i]:edges[i + 1]]
        if len(train) < MIN_N or len(test) < MIN_N:
            continue
        folds.append((train, test))
    return folds


def train_one_fold(train_df: pd.DataFrame, factors: list[str], timesteps: int, seed: int) -> dict:
    env = Monitor(RegimeWeightedScoreEnv(train_df, factors, min_n=MIN_N, seed=seed))
    model = PPO("MlpPolicy", env, verbose=0, seed=seed, n_steps=256, batch_size=64)
    model.learn(total_timesteps=timesteps)
    weights = {}
    for r in REGIMES:
        oh = np.zeros(3, dtype=np.float32)
        oh[REGIMES.index(r)] = 1.0
        action, _ = model.predict(oh, deterministic=True)
        weights[r] = softmax_weights(np.asarray(action, dtype=np.float64))
    return weights


def shrink_toward_equal(w_ppo: np.ndarray, n_factors: int, alpha: float) -> np.ndarray:
    w_eq = np.full(n_factors, 1.0 / n_factors)
    w = alpha * w_ppo + (1 - alpha) * w_eq
    return w / w.sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["us", "india"], required=True)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--timesteps", type=int, default=TIMESTEPS_PER_FOLD)
    args = ap.parse_args()

    factors = CURATED_FACTORS_COMMON + (US_ONLY_FACTORS if args.market == "us" else [])

    print(f"=== {args.market.upper()}: loading panel + forward returns ===")
    panel = pd.read_parquet(PANEL_PATH)
    df = panel[(panel["market"] == args.market) & (panel["regime"] != "UNKNOWN")].copy()
    ohlcv = load_market_ohlcv(args.market)
    df = attach_forward_return(df, ohlcv, args.market)
    df = compute_excess_columns(df)
    print(f"  {len(df):,} rows with a valid forward return")

    folds = walk_forward_folds(df, args.folds)
    print(f"  {len(folds)} usable walk-forward folds (requested {args.folds})")
    for i, (tr, te) in enumerate(folds):
        print(f"  fold {i}: TRAIN {len(tr):,} rows to {tr['filed'].max().date()}, "
              f"TEST {len(te):,} rows {te['filed'].min().date()} to {te['filed'].max().date()}, "
              f"TEST regimes {te['regime'].value_counts().to_dict()}")

    methods = ["equal_weight"] + [f"ppo_shrink_{a}" for a in SHRINK_ALPHAS]
    results = {r: {m: [] for m in methods} for r in REGIMES}
    floor_hits = {r: {m: 0 for m in methods} for r in REGIMES}

    for i, (train_df, test_df) in enumerate(folds):
        print(f"\n--- Fold {i} ---")
        test_env = RegimeWeightedScoreEnv(test_df, factors, min_n=MIN_N, seed=100 + i)
        w_eq = np.full(len(factors), 1.0 / len(factors))
        ppo_weights = train_one_fold(train_df, factors, args.timesteps, seed=42 + i)
        for r in REGIMES:
            rew_eq, info_eq = test_env.score_and_reward(r, w_eq)
            results[r]["equal_weight"].append(rew_eq)
            if info_eq.get("note"):
                floor_hits[r]["equal_weight"] += 1
            line = [f"equal-weight={rew_eq:+.3f}"]
            for a in SHRINK_ALPHAS:
                w = shrink_toward_equal(ppo_weights[r], len(factors), a)
                rew, info = test_env.score_and_reward(r, w)
                results[r][f"ppo_shrink_{a}"].append(rew)
                if info.get("note"):
                    floor_hits[r][f"ppo_shrink_{a}"] += 1
                line.append(f"shrink@{a}={rew:+.3f}")
            print(f"  {r}: " + "  ".join(line))

    print("\n" + "=" * 100)
    print(f"WALK-FORWARD SUMMARY ({args.market.upper()}, {len(folds)} folds) "
          "-- mean OOS reward +/- std across folds")
    print("=" * 100)
    for r in REGIMES:
        print(f"\n  {r}:")
        for m in methods:
            vals = results[r][m]
            n_floor = floor_hits[r][m]
            note = f"  ({n_floor}/{len(vals)} folds hit the min_n floor -- treat as thin)" if n_floor else ""
            print(f"    {m:<20s} mean={np.mean(vals):+.3f}  std={np.std(vals):.3f}  "
                  f"n_folds={len(vals)}{note}")
        # monotonicity check: does reward improve as alpha -> 0 (more equal-weight)?
        means = [np.mean(results[r][f"ppo_shrink_{a}"]) for a in SHRINK_ALPHAS]
        increasing_toward_eq = all(means[i] >= means[i + 1] - 1e-9 for i in range(len(means) - 1))
        print(f"    shrinkage pattern (alpha {SHRINK_ALPHAS[0]}->{SHRINK_ALPHAS[-1]}, i.e. eq->ppo): "
              f"{[round(m, 3) for m in means]}  "
              f"{'monotonically WORSE as alpha rises (shrinkage toward equal-weight HELPS)' if increasing_toward_eq else 'not monotonic'}")

    out_path = f"/Users/umashankar/market-pipeline/code/python_files/cache_seed/ppo_walk_forward_{args.market}.csv"
    rows = []
    for r in REGIMES:
        for m in methods:
            for fold_i, v in enumerate(results[r][m]):
                rows.append({"market": args.market, "regime": r, "method": m, "fold": fold_i, "reward": v})
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"\nSaved fold-level results -> {out_path}")


if __name__ == "__main__":
    main()
