#!/usr/bin/env python3
"""
factor_growth_risk.py — the "growth & insolvency risk" and "cash-conversion"
blind spots factor_valuation_quality.py's own docstring names but doesn't cover:
P/FCF, FCF/EBITDA, Altman Z-Score, Reinvestment Rate x ROCE. 12-1 Month
Momentum lives here too (pure price data, no fundamentals) rather than in a
separate module, since all five are this project's "step 2" scope together.

FREE CASH FLOW = CFO - CapEx
-----------------------------
The plain, standard definition. P/FCF (Price / FCF) and FCF/EBITDA (cash
conversion of operating profit) both build on it. Unlike Sloan's accrual ratio
(NI - CFO), which asks "is REPORTED INCOME cash-backed", FCF/EBITDA asks "how
much of OPERATING PROFIT survives capital spending" — a different question:
a capital-intensive but honest business can have high earnings quality (low
accruals) and still convert little of EBITDA to free cash, because the capex
is real, not an accounting artifact.

ALTMAN Z-SCORE (Altman 1968, Journal of Finance) — the ORIGINAL 5-factor
model for public manufacturers, not the private-firm or non-manufacturer
variants (Z' / Z''), which need book equity or drop the sales/assets term:
    Z = 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MVE/TL) + 1.0*(Sales/TA)
    WC = working capital = current_assets - current_liabilities
    RE = retained earnings (accumulated deficit if negative)
    MVE = market value of equity = shares x price (NOT book equity — this is
          what makes it forward-looking rather than purely accounting-based)
    TL = total liabilities (the DIRECT reported figure, not TA - equity — see
         sec_history_collector.py's CONCEPTS comment for why)
Zones (Altman's own thresholds): Z > 2.99 SAFE | 1.81-2.99 GREY | Z < 1.81 DISTRESS.
Using the manufacturer model on a non-manufacturer is a KNOWN, ACCEPTED
limitation here — this repo does not yet have an industry classification
granular enough to route financials/services firms to a different Z variant
(see piotroski_plus.py / roace_by_liquidity.py's own unresolved lender-
detection notes for why "is this company non-standard" is already a hard,
unsolved problem in this codebase).

REINVESTMENT RATE x ROCE = Intrinsic Growth Rate (Damodaran-style)
---------------------------------------------------------------------
    reinvestment_rate = (capex - d_and_a) / NOPAT
    NOPAT = EBIT x (1 - ASSUMED_TAX_RATE)
    intrinsic_growth = reinvestment_rate x roce

ASSUMED_TAX_RATE is a STATED APPROXIMATION, not a per-company effective rate —
the collector does not fetch tax expense, so this is the flat 21% US federal
statutory corporate rate (post-TCJA 2017), not each filer's actual effective
rate (which varies with state taxes, credits, and international mix). This
understates the rate for most real filers, which means NOPAT and therefore
the reinvestment rate are systematically a hair too low; reported as a
LEVEL, not treated as precise, and this bias applies uniformly so cross-
sectional RANKING is far less affected than any single company's absolute
number.

12-1 MONTH MOMENTUM (Jegadeesh & Titman 1993, Journal of Finance)
--------------------------------------------------------------------
Cumulative return from t-252 trading days to t-21 trading days — deliberately
EXCLUDING the most recent ~1 month, because short-term reversal (Jegadeesh
1990) runs the OPPOSITE direction of 12-month momentum and would net the two
effects together into a smaller, muddier signal if the recent month were
included. Needs price data only; see momentum_12_1_sql() for the DuckDB
window-function form used by the sweep/funnel scripts.
"""
from __future__ import annotations

ASSUMED_TAX_RATE = 0.21   # US federal statutory rate, post-TCJA 2017 — see module docstring
ALTMAN_SAFE = 2.99
ALTMAN_DISTRESS = 1.81


def free_cash_flow(cfo, capex):
    """CFO - CapEx. capex is a POSITIVE outflow number as reported by the
    collector (PaymentsToAcquirePropertyPlantAndEquipment); this is not
    guaranteed sign-consistent across all filers, so callers passing raw
    XBRL-derived capex should confirm sign convention for their sample."""
    if cfo is None or capex is None:
        return None
    return cfo - abs(capex)


def price_to_fcf(market_cap, fcf):
    """Market Cap / FCF. None if FCF is non-positive — a negative-FCF company
    has an undefined (or worse, sign-flipped-cheap-looking) P/FCF, not a
    meaningfully low one."""
    if market_cap is None or fcf is None or fcf <= 0:
        return None
    return market_cap / fcf


def fcf_to_ebitda(fcf, ebit, d_and_a):
    """FCF / EBITDA, EBITDA = EBIT + D&A. None if EBITDA is non-positive."""
    if fcf is None or ebit is None or d_and_a is None:
        return None
    ebitda = ebit + abs(d_and_a)
    if ebitda <= 0:
        return None
    return fcf / ebitda


def altman_z_score(current_assets, current_liabilities, total_assets,
                    retained_earnings, ebit, market_cap, total_liabilities, revenue):
    """Original Altman (1968) 5-factor Z-Score for public manufacturers.
    None if total_assets or total_liabilities is unusable (both are
    denominators central to the formula, not optional legs)."""
    if total_assets is None or total_assets <= 0:
        return None
    if total_liabilities is None or total_liabilities <= 0:
        return None
    if None in (current_assets, current_liabilities, retained_earnings, ebit, market_cap, revenue):
        return None
    wc = current_assets - current_liabilities
    x1 = wc / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_liabilities
    x5 = revenue / total_assets
    return 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5


def altman_zone(z):
    """SAFE / GREY / DISTRESS per Altman's own thresholds, or None if
    z itself is None (untested, not "distressed" by default)."""
    if z is None:
        return None
    if z > ALTMAN_SAFE:
        return "SAFE"
    if z >= ALTMAN_DISTRESS:
        return "GREY"
    return "DISTRESS"


def reinvestment_rate(capex, d_and_a, ebit, tax_rate=ASSUMED_TAX_RATE):
    """(CapEx - D&A) / NOPAT. NOPAT = EBIT x (1 - tax_rate) — see module
    docstring for why tax_rate is a stated flat assumption, not measured.
    None if NOPAT is non-positive (a loss-making or breakeven EBIT company
    has no meaningful reinvestment-rate denominator)."""
    if capex is None or d_and_a is None or ebit is None:
        return None
    nopat = ebit * (1 - tax_rate)
    if nopat <= 0:
        return None
    return (abs(capex) - abs(d_and_a)) / nopat


def intrinsic_growth_rate(reinv_rate, roce):
    """reinvestment_rate x roce — the growth a company can fund WITHOUT new
    outside capital, at its current reinvestment pace and return on capital."""
    if reinv_rate is None or roce is None:
        return None
    return reinv_rate * roce


def momentum_12_1_sql(price_table: str, hold_col: str = "Close") -> str:
    """Return a DuckDB SQL fragment computing 12-1 month momentum (252 trading
    days back to 21 trading days back, EXCLUDING the most recent ~month — see
    module docstring for why) as a window function over `price_table`. Meant
    to be embedded in a larger query, not run standalone; callers own the
    final SELECT and any date filtering.

    Columns produced: Symbol, Date, mom_12_1 (fraction, e.g. 0.35 = +35%).
    """
    return f"""
        SELECT Symbol, Date,
               lag({hold_col}, 21)  OVER (PARTITION BY Symbol ORDER BY Date)
               / NULLIF(lag({hold_col}, 252) OVER (PARTITION BY Symbol ORDER BY Date), 0)
               - 1 AS mom_12_1
        FROM {price_table}
        WHERE {hold_col} > 0
    """
