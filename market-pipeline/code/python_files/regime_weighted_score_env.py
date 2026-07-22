#!/usr/bin/env python3
"""
regime_weighted_score_env.py -- Phase 3 (env half) of PPO regime-conditional
factor-weight scoring (see /Users/umashankar/.claude/plans/bright-hatching-
scone.md).

A gymnasium.Env, but CONTEXTUAL-BANDIT-STYLE, not a sequential trading
agent, per the approved plan's own explicit framing: state = current
market regime (one-hot), action = one continuous factor-weight vector
(softmax-squashed so weights are non-negative and comparable), reward =
that vector's cross-sectional performance, episode terminates after one
step. A full sequential MDP would need far more independent episodes than
this data (India especially, 4,356 filings total) can support without
overfitting -- see the plan's "Realistic framing" section.

REWARD, reused from reward_screener_opt.py's convention (not its code --
that script's own attach_forward_and_price()/reward() are import-heavy
with CLI/data-loading side effects not needed here; the FORMULA is what's
reused, reimplemented as a 5-line function): winsor-robust median forward
excess return, where "excess" = raw forward return minus the SAME
(market, entry-year) cohort's median forward return that year -- removes
"the market went up that year" without depending on a specific benchmark
index, per that script's own "cohort-neutral reward" comment.

Composite score, per row: weight-normalized OVER ONLY THE FACTORS THAT
EXIST for that row -- sum(weight_i * z_i * has_i) / sum(weight_i * has_i)
-- so a row with 4/10 factors populated isn't penalized relative to one
with 10/10, it's just averaged over what it actually has. A row where the
weighted-available mass is ~0 (every weighted factor missing) gets
excluded, not scored as 0 (a 0 composite would rank as "average," which is
not what "no data" means).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as e:
    raise ImportError(
        "regime_weighted_score_env.py needs gymnasium + stable_baselines3 "
        "(pip install -r requirements.txt) -- following this repo's own "
        "established optional-RL-dependency pattern (rl_trader.py --ppo)."
    ) from e

REGIMES = ["BULL", "BEAR", "SIDEWAYS"]
MIN_DEN_MASS = 1e-6  # a row's weighted-available factor mass below this is "no real signal"


def softmax_weights(action: np.ndarray) -> np.ndarray:
    """Non-negative, sums to 1 -- makes weights directly comparable across
    factors and across regimes (a long-only composite score can't have a
    factor work "against" a stock, per the approved plan's own spec)."""
    a = action - action.max()
    w = np.exp(a)
    return w / w.sum()


def compute_reward(sub: pd.DataFrame) -> dict | None:
    """Same formula as reward_screener_opt.py's reward(): n, median excess
    (primary), mean of the winsorized excess, win rate."""
    if len(sub) == 0:
        return None
    return {
        "n": len(sub),
        "med": float(sub["excess"].median()),
        "mean": float(sub["excess_w"].mean()),
        "win": float((sub["excess"] > 0).mean()),
    }


class RegimeWeightedScoreEnv(gym.Env):
    """One episode = one regime draw -> one weight-vector action -> reward
    from that vector's top-decile cross-sectional performance in that
    regime's rows. `df` must already carry z_<factor>/has_<factor> columns
    (factor_zscore_panel.py) and `excess`/`excess_w` (this file's caller,
    train_ppo_factor_weights.py, attaches these from forward returns)."""

    metadata = {"render_modes": []}

    def __init__(self, df: pd.DataFrame, factors: list[str], top_frac: float = 0.10,
                 min_n: int = 30, seed: int | None = None):
        super().__init__()
        self.factors = factors
        self.top_frac = top_frac
        self.min_n = min_n
        self.regime_frames = {}
        for r in REGIMES:
            sub = df[df["regime"] == r]
            self.regime_frames[r] = {
                "z": sub[[f"z_{f}" for f in factors]].to_numpy(dtype=np.float64),
                "has": sub[[f"has_{f}" for f in factors]].to_numpy(dtype=np.float64),
                "excess": sub["excess"].to_numpy(dtype=np.float64),
                "excess_w": sub["excess_w"].to_numpy(dtype=np.float64),
            }
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(3,), dtype=np.float32)
        self.action_space = spaces.Box(low=-5.0, high=5.0, shape=(len(factors),), dtype=np.float32)
        self._rng = np.random.default_rng(seed)
        self.current_regime = REGIMES[0]

    def _obs(self) -> np.ndarray:
        oh = np.zeros(3, dtype=np.float32)
        oh[REGIMES.index(self.current_regime)] = 1.0
        return oh

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self.current_regime = REGIMES[self._rng.integers(0, len(REGIMES))]
        return self._obs(), {}

    def score_and_reward(self, regime: str, weights: np.ndarray) -> tuple[float, dict]:
        """Exposed separately from step() so train_ppo_factor_weights.py can
        run the SAME scoring logic deterministically on held-out data using
        a fixed weight vector (no reset()/gymnasium bookkeeping needed for
        an out-of-sample evaluation pass)."""
        d = self.regime_frames[regime]
        if len(d["excess"]) < self.min_n:
            return 0.0, {"n": len(d["excess"]), "note": "below min_n floor for this regime"}
        num = np.nansum(d["z"] * d["has"] * weights, axis=1)
        den = (d["has"] * weights).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            # np.where evaluates num/den for EVERY row before masking, so
            # den==0 rows raise a (harmless, np.where discards them) warning
            composite = np.where(den > MIN_DEN_MASS, num / den, np.nan)
        valid = ~np.isnan(composite)
        if valid.sum() < self.min_n:
            return 0.0, {"n": int(valid.sum()), "note": "below min_n floor after masking"}
        order = np.argsort(-composite[valid])
        n_top = max(self.min_n, int(valid.sum() * self.top_frac))
        top_idx = np.flatnonzero(valid)[order[:n_top]]
        sub = pd.DataFrame({
            "excess": d["excess"][top_idx],
            "excess_w": d["excess_w"][top_idx],
        }).dropna(subset=["excess", "excess_w"])
        rew = compute_reward(sub)
        return (rew["med"] if rew else 0.0), (rew or {"n": 0, "note": "no valid top-N rows"})

    def step(self, action: np.ndarray):
        weights = softmax_weights(np.asarray(action, dtype=np.float64))
        reward, info = self.score_and_reward(self.current_regime, weights)
        return self._obs(), float(reward), True, False, info
