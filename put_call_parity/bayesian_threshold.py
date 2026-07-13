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

This module is standalone and does not change strategy.py's live trading
decisions on its own -- wiring recommended_threshold() into the live scan
loop is a deliberate follow-up, not something this module does silently.

Usage:
    tracker = BayesianThresholdTracker(base_threshold=30.0)
    tracker.observe(entry_deviation=32.0, was_profitable=True)
    tracker.observe(entry_deviation=31.0, was_profitable=False)
    threshold = tracker.recommended_threshold()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class _Trade:
    entry_deviation: float
    was_profitable: bool


@dataclass
class BayesianThresholdTracker:
    """
    Tracks trade outcomes near a base deviation threshold and produces a
    dynamically adjusted recommended threshold using a Beta-Bernoulli
    posterior over "is a trade at this deviation level profitable?".

    base_threshold: the static min_deviation this tracker adapts around
        (e.g. config.INSTRUMENTS['BANKNIFTY'].min_deviation).
    prior_alpha/prior_beta: Beta(1,1) = uniform prior by default -- weak
        enough that a handful of observed trades quickly dominates it.
    confidence_target: the posterior win-probability required to hold the
        current threshold; the tracker raises the threshold (demands a
        wider edge) when the posterior mean win rate is below this, and
        relaxes it (down to a floor) when comfortably above it.
    """
    base_threshold: float
    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    confidence_target: float = 0.55
    min_threshold_fraction: float = 0.5    # never relax below 50% of base
    max_threshold_fraction: float = 3.0    # never tighten above 300% of base
    adjustment_step: float = 0.1           # 10% move per re-evaluation
    _trades: List[_Trade] = field(default_factory=list)
    _multiplier: float = 1.0

    def observe(self, entry_deviation: float, was_profitable: bool) -> None:
        """
        Record one closed trade's outcome. Call this once per finite-horizon
        episode (i.e. once a trade closes at or before expiry).
        """
        self._trades.append(_Trade(entry_deviation, was_profitable))

    def posterior(self) -> Tuple[float, float]:
        """Beta(alpha, beta) posterior over win probability, given trades observed so far."""
        successes = sum(1 for t in self._trades if t.was_profitable)
        failures = len(self._trades) - successes
        return (self.prior_alpha + successes, self.prior_beta + failures)

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
        if not self._trades:
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
        """
        self._trades.clear()
        self._multiplier = 1.0
