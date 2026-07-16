#!/usr/bin/env python3
"""
factor_valuation_quality.py — Earnings Yield (valuation) + Sloan Ratio (earnings
quality), the two blind spots piotroski_plus.py's own docstring already names:

    "ROCE is an accounting-earnings measure... says nothing about cash flow...
     Piotroski Plus is a QUALITY filter... not a liquidity filter."

Piotroski F-score asks "getting better?"; ROCE asks "efficient historically?".
Neither asks "is it cheap?" (Earnings Yield) or "is the accounting income
actually cash?" (Sloan Ratio) — a company can pass both existing blocks while
trading at 40x EBIT on manufactured earnings.

EARNINGS YIELD = EBIT / Enterprise Value
-----------------------------------------
Greenblatt's Magic Formula (2005) operating yield: EBIT/EV rather than E/P
because it (a) is capital-structure-neutral — comparable across a levered and an
unlevered company where P/E is not, and (b) uses EBIT, the same numerator
piotroski_plus.py's ROCE already uses, so "cheap" and "efficient" are measured on
a shared basis and can be combined without a units mismatch.

    EV = market_cap + long_term_debt + short_term_debt - cash

market_cap needs a PRICE, which the F-score/ROCE block never did — this is the
one input this module adds beyond piotroski_plus.py's fundamentals-only universe.
Missing debt/cash tags are treated as ZERO, not as missing data, matching the
`cash0 = _at(cash, y0) or 0.0` convention piotroski_plus.py already uses for
ROCE-ex-cash: SEC's debt tags are only ~21-30% populated, and a filer with no
debt tag is far more likely genuinely debt-free than silently unmeasured —
treating absence as missing would exclude most of the universe rather than
most of the debt.

SLOAN RATIO (accrual ratio; Sloan 1996, The Accounting Review)
----------------------------------------------------------------
    accrual_ratio = (net_income - CFO) / total_assets

The ORIGINAL Sloan decomposes accruals from balance-sheet deltas (working
capital, depreciation, etc.); this is the simplified cash-flow-statement version
used in most modern replications — it needs only fields piotroski_plus.py's
Piotroski tests 1-4 already consume (net_income, cfo, total_assets), so no new
data collection is required for this factor.

    LOW (more negative) accrual ratio = income is backed by cash  = HIGH quality
    HIGH (positive) accrual ratio     = income is non-cash accounting deltas
                                         (receivables growth, inventory build,
                                         one-time gains) = suspect quality

This is Piotroski test 4 restated as a continuous figure rather than a boolean —
test 4 asks "is CFO/TA > NI/TA" (equivalent to accrual_ratio < 0, since
CFO/TA > NI/TA  <=>  NI - CFO < 0), so a company with `sloan < 0` already passes
the existing test 4 by construction. What this module adds is the MAGNITUDE — a
rank, not just a pass/fail — for use as a tiebreaker among companies that all
already pass test 4.

WHAT THIS DOES NOT MEASURE
---------------------------
Earnings Yield says nothing about growth (a business earning cheaply on EV may be
cheap because it is shrinking) or bankruptcy risk (Altman Z-Score territory, not
built here). Sloan Ratio flags non-cash income but not WHY — a genuine
receivables build ahead of real revenue growth and channel-stuffing look
identical in this one number; it is a screen, not a diagnosis.
"""
from __future__ import annotations


def enterprise_value(market_cap, long_term_debt=None, short_term_debt=None, cash=None):
    """market_cap + debt - cash. Missing debt/cash legs default to 0 (see module
    docstring for why absence is treated as zero, not missing, for these fields).
    Returns None if market_cap itself is unusable."""
    if market_cap is None or market_cap <= 0:
        return None
    ltd = long_term_debt or 0.0
    std = short_term_debt or 0.0
    csh = cash or 0.0
    return market_cap + ltd + std - csh


def earnings_yield(ebit, ev):
    """EBIT / EV. None if EV is unusable (<=0 — a net-cash company with EV<=0 is
    not a meaningful earnings-yield candidate; it needs a different valuation
    approach entirely, not an infinite or negative yield)."""
    if ebit is None or ev is None or ev <= 0:
        return None
    return ebit / ev


def sloan_ratio(net_income, cfo, total_assets):
    """(net_income - CFO) / total_assets. None if total_assets is unusable."""
    if net_income is None or cfo is None or total_assets is None or total_assets <= 0:
        return None
    return (net_income - cfo) / total_assets


def earnings_quality_flag(sloan):
    """LOW accrual ratio (< 0) = cash-backed income = the pass condition.
    Returns None (untested), not False, when sloan itself is None."""
    if sloan is None:
        return None
    return bool(sloan < 0)
