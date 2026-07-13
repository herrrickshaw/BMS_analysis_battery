"""
Bayesian dynamic threshold optimization for the put-call parity strategy.

Derived from patent MY269148 "System and method for optimizing an attribute
value dynamically in finite-horizon environments using Bayesian inference"
(IIIT-Hyderabad, CSG). Applies Beta-Bernoulli Bayesian updating to the
per-instrument `min_deviation` threshold in config.py: each options-expiry
cycle is a finite horizon, and every trade closed within it is one Bernoulli
observation ("was this trade profitable net of costs?"). The recommended
threshold tightens when recent trades near it underperform, and relaxes when
they've been reliably profitable -- instead of the fixed value set once in
config.py.

Uses DISCOUNTED Thompson Sampling (Raj & Kalyani, "Taming Non-stationary
Bandits: A Bayesian Approach", arXiv:1707.09727, 2017), not the textbook
vanilla Beta-Bernoulli update. Vanilla Beta-Bernoulli assumes every trade
is an IID draw from a *fixed* win probability -- a plainly false assumption
for financial markets, where the true win-rate drifts with the regime. Under
that assumption the posterior keeps concentrating on an increasingly stale
average as more (increasingly outdated) evidence piles up. Discounting
(multiplying the accumulated alpha/beta by `discount_factor` < 1 before
adding each new observation) makes the posterior track a moving win-rate
instead, at the cost of noisier estimates -- the standard bias/variance
trade-off documented for this exact non-stationary-bandit setting.

This module is standalone and does not change strategy.py's live trading
decisions on its own -- wiring recommended_threshold() into the live scan
loop is a deliberate follow-up, not something this module does silently.

Usage:
    tracker = BayesianThresholdTracker(base_threshold=30.0, discount_factor=0.97)
    tracker.observe(entry_deviation=32.0, was_profitable=True)
    tracker.observe(entry_deviation=31.0, was_profitable=False)
    threshold = tracker.recommended_threshold()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class BayesianThresholdTracker:
    """
    Tracks trade outcomes near a base deviation threshold and produces a
    dynamically adjusted recommended threshold using a discounted
    Beta-Bernoulli posterior over "is a trade at this deviation level
    profitable?".

    base_threshold: the static min_deviation this tracker adapts around
        (e.g. config.INSTRUMENTS['BANKNIFTY'].min_deviation).
    prior_alpha/prior_beta: Beta(1,1) = uniform prior by default -- weak
        enough that a handful of observed trades quickly dominates it.
    discount_factor: multiplies the accumulated alpha/beta by this value
        before adding each new observation (Raj & Kalyani 2017's discounted
        Thompson Sampling). 1.0 = no discounting (plain cumulative
        Beta-Bernoulli, correct only if the true win-rate is truly
        stationary). Values around 0.95-0.99 give a rough "effective window"
        of roughly 1/(1-gamma) recent trades -- e.g. 0.97 weights the last
        ~33 trades most heavily without a hard cutoff.
    confidence_target: the posterior win-probability required to hold the
        current threshold; the tracker raises the threshold (demands a
        wider edge) when the posterior mean win rate is below this, and
        relaxes it (down to a floor) when comfortably above it.
    """
    base_threshold: float
    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    discount_factor: float = 1.0
    confidence_target: float = 0.55
    min_threshold_fraction: float = 0.5    # never relax below 50% of base
    max_threshold_fraction: float = 3.0    # never tighten above 300% of base
    adjustment_step: float = 0.1           # 10% move per re-evaluation
    _alpha: float = field(init=False, default=0.0)
    _beta: float = field(init=False, default=0.0)
    _n_observed: int = field(init=False, default=0)
    _multiplier: float = field(init=False, default=1.0)

    def __post_init__(self) -> None:
        self._alpha = self.prior_alpha
        self._beta = self.prior_beta

    def observe(self, entry_deviation: float, was_profitable: bool) -> None:
        """
        Record one closed trade's outcome. Call this once per finite-horizon
        episode (i.e. once a trade closes at or before expiry).

        entry_deviation is accepted for logging/API completeness (a caller
        may want to record what deviation level a trade entered at) but
        does not feed into the posterior update itself -- only the binary
        outcome does.
        """
        self._alpha = self._alpha * self.discount_factor + (1.0 if was_profitable else 0.0)
        self._beta = self._beta * self.discount_factor + (0.0 if was_profitable else 1.0)
        self._n_observed += 1

    def posterior(self) -> Tuple[float, float]:
        """Beta(alpha, beta) posterior over win probability, given (discounted) trades observed so far."""
        return (self._alpha, self._beta)

    def posterior_mean(self) -> float:
        a, b = self.posterior()
        return a / (a + b)

    def credible_interval(self, width: float = 0.90) -> Tuple[float, float]:
        """(low, high) equal-tailed credible interval at the given width."""
        from scipy.stats import beta as beta_dist
        a, b = self.posterior()
        lo = (1 - width) / 2
        hi = 1 - lo
        return (float(beta_dist.ppf(lo, a, b)), float(beta_dist.ppf(hi, a, b)))

    def recommended_threshold(self) -> float:
        """The dynamically adjusted min_deviation to use, given evidence so far this horizon."""
        if self._n_observed == 0:
            return self.base_threshold  # no evidence yet -- use the static prior

        mean = self.posterior_mean()
        if mean < self.confidence_target:
            # Recent trades near this threshold underperform -- demand more edge.
            self._multiplier = min(self.max_threshold_fraction,
                                    self._multiplier * (1 + self.adjustment_step))
        else:
            # Comfortably profitable -- can afford to relax and catch more trades.
            self._multiplier = max(self.min_threshold_fraction,
                                    self._multiplier * (1 - self.adjustment_step))
        return round(self.base_threshold * self._multiplier, 2)

    def reset_horizon(self) -> None:
        """
        Clear observations and the learned multiplier at the start of a new
        finite-horizon episode (e.g. a new expiry cycle). Deliberately does
        NOT carry the multiplier forward: a threshold that drifted to an
        extreme on a small/stale sample last horizon shouldn't silently
        persist into the next one with no new evidence -- each horizon starts
        back at base_threshold until it earns its own adjustment.

        Note this is a second, separate mechanism from discount_factor:
        discounting fades old evidence *within* an ongoing horizon (handles
        gradual regime drift), while reset_horizon() is a hard cut at a
        known structural boundary (a new expiry cycle starting).
        """
        self._alpha = self.prior_alpha
        self._beta = self.prior_beta
        self._n_observed = 0
        self._multiplier = 1.0


def build_trackers_for_all_instruments(discount_factor: float = 1.0) -> "dict[str, BayesianThresholdTracker]":
    """
    One tracker per configured instrument (config.INSTRUMENTS) -- this
    subsystem's actual "universe" is the 3 tradeable instruments (BankNifty,
    CrudeOil, Silver), not the broader stock market, so expanding this module
    means covering all of them rather than just the single example instrument
    used during development.

    Each tracker starts at its instrument's static config.min_deviation and
    is independent -- a losing streak on Silver shouldn't tighten BankNifty's
    threshold.
    """
    from . import config
    return {
        key: BayesianThresholdTracker(base_threshold=inst.min_deviation, discount_factor=discount_factor)
        for key, inst in config.INSTRUMENTS.items()
    }
