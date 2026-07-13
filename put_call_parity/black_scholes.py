"""
Black-Scholes options pricing engine.

Provides theoretical prices for European calls and puts, all five Greeks
(delta, gamma, theta, vega, rho), implied-volatility inversion via
Newton-Raphson, and a payoff-at-expiry helper used by the strategy builder.

Reference:
    Black, F. & Scholes, M. (1973). The Pricing of Options and Corporate
    Liabilities. Journal of Political Economy, 81(3), 637–654.

Quick reference — inputs used throughout:
    S     = current spot / futures price
    K     = option strike price
    T     = time to expiry in years  (e.g. 30 days → 30/365 ≈ 0.082)
    r     = risk-free rate (annualised, decimal form — 6.8% → 0.068)
    sigma = implied volatility (annualised, decimal — 20% → 0.20)
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, sqrt
from typing import Optional

from scipy.stats import norm

# Pull the project-wide risk-free rate; fall back to a reasonable default
# if this module is used standalone (e.g. in a Jupyter notebook).
try:
    from .config import RISK_FREE_RATE
except ImportError:
    RISK_FREE_RATE = 0.068   # ~6.8% — current Indian 91-day T-bill yield


# ── Greeks dataclass ──────────────────────────────────────────────────────────

@dataclass
class Greeks:
    """
    All five option Greeks in standard, trader-friendly units.

    delta: change in option price per ₹1 (or $1) move in the underlying.
           Calls: 0 to +1.  Puts: -1 to 0.
    gamma: rate of change of delta per ₹1 move.  Always positive for long options.
    theta: time decay per calendar day.  Always negative for long options
           (long options lose value as expiry approaches).
    vega:  change in option price for a 1% rise in implied volatility.
           Always positive for long options.
    rho:   change in option price for a 1% rise in the risk-free rate.
    """
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


# ── Internal Black-Scholes terms ──────────────────────────────────────────────

def _d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    First standardised normal variable in the B-S formula.
    Intuitively: how far the spot is above the PV of the strike, scaled by sigma.
    """
    return (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))


def _d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Second standardised normal variable: d1 minus one standard deviation."""
    return _d1(S, K, T, r, sigma) - sigma * sqrt(T)


# ── Option pricing ────────────────────────────────────────────────────────────

def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Theoretical European call price.
    At expiry (T=0) this reduces to the intrinsic value max(S-K, 0).
    """
    if T <= 0:
        return max(S - K, 0.0)
    d1, d2 = _d1(S, K, T, r, sigma), _d2(S, K, T, r, sigma)
    return S * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)


def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Theoretical European put price.
    At expiry (T=0) reduces to max(K-S, 0).
    """
    if T <= 0:
        return max(K - S, 0.0)
    d1, d2 = _d1(S, K, T, r, sigma), _d2(S, K, T, r, sigma)
    return K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def price_option(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str
) -> float:
    """Price a call ('CE') or put ('PE')."""
    return call_price(S, K, T, r, sigma) if option_type.upper() == 'CE' else put_price(S, K, T, r, sigma)


# ── Greeks ────────────────────────────────────────────────────────────────────

def greeks(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str
) -> Greeks:
    """
    Calculate all five Greeks for a European option.

    Returns zero Greeks at expiry (T ≈ 0) to avoid division-by-zero.
    """
    if T <= 1e-6:
        return Greeks(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)

    d1_val = _d1(S, K, T, r, sigma)
    d2_val = d1_val - sigma * sqrt(T)
    pdf_d1 = norm.pdf(d1_val)   # standard normal PDF at d1
    is_call = option_type.upper() == 'CE'

    # Delta — sensitivity to spot price
    # Call delta is N(d1); put delta is N(d1)-1 (always between -1 and 0)
    delta_val = norm.cdf(d1_val) if is_call else norm.cdf(d1_val) - 1

    # Gamma — curvature; identical for calls and puts at the same strike
    gamma_val = pdf_d1 / (S * sigma * sqrt(T))

    # Theta — daily time decay (divide the annual figure by 365)
    # The formula differs by sign on the interest term for calls vs puts
    common_theta = -S * pdf_d1 * sigma / (2 * sqrt(T))
    if is_call:
        theta_val = (common_theta - r * K * exp(-r * T) * norm.cdf(d2_val)) / 365
    else:
        theta_val = (common_theta + r * K * exp(-r * T) * norm.cdf(-d2_val)) / 365

    # Vega — per 1% change in IV (divide the raw formula result by 100)
    vega_val = S * pdf_d1 * sqrt(T) / 100

    # Rho — per 1% change in risk-free rate
    if is_call:
        rho_val = K * T * exp(-r * T) * norm.cdf(d2_val) / 100
    else:
        rho_val = -K * T * exp(-r * T) * norm.cdf(-d2_val) / 100

    return Greeks(
        delta=round(delta_val, 4),
        gamma=round(gamma_val, 6),
        theta=round(theta_val, 4),
        vega=round(vega_val, 4),
        rho=round(rho_val, 4),
    )


# ── Implied Volatility ────────────────────────────────────────────────────────

def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
) -> Optional[float]:
    """
    Back-solve for the implied volatility given a market price.

    Uses Newton-Raphson iteration, which converges quickly for liquid options.
    Returns None if it fails to converge (e.g. deep in/out-of-the-money options
    where vega is near zero and the algorithm can't make progress).

    The initial sigma guess uses the Brenner-Subrahmanyam (1988) approximation
    for ATM options; falls back to 30% for very off-ATM strikes.
    """
    if T <= 0 or market_price <= 0:
        return None

    # Initial guess: Brenner-Subrahmanyam approximation for ATM
    moneyness = abs(log(S / K))
    sigma = sqrt(2 * moneyness / T + 0.5) if moneyness > 0.01 else sqrt(2 * market_price / (S * sqrt(T / (2 * 3.14159))))
    sigma = max(0.01, min(sigma, 5.0))   # clamp to [1%, 500%]

    for _ in range(max_iterations):
        price = price_option(S, K, T, r, sigma, option_type)
        # Vega in raw form (not divided by 100) for the Newton step
        raw_vega = S * norm.pdf(_d1(S, K, T, r, sigma)) * sqrt(T)
        if abs(raw_vega) < 1e-10:
            break   # vega too small — can't converge
        diff = price - market_price
        sigma -= diff / raw_vega
        sigma = max(0.001, min(sigma, 5.0))
        if abs(diff) < tolerance:
            return round(sigma, 6)

    return None   # didn't converge


# ── Payoff at expiry ──────────────────────────────────────────────────────────

def payoff_at_expiry(
    legs: list[dict],
    spot_min: float,
    spot_max: float,
    steps: int = 80,
) -> list[dict]:
    """
    Calculate the combined strategy P&L at expiry across a range of spot prices.

    This is the core calculation behind every payoff chart — it shows what the
    strategy makes or loses if held until expiry at each possible spot price.

    Each leg dict must contain:
        option_type : 'CE', 'PE', or 'FUT'
        action      : 'BUY' or 'SELL'
        strike      : float — the option strike (or futures entry price for FUT)
        premium     : float — price paid per unit (positive = you paid it)
        lots        : int
        lot_size    : int

    Returns a list of {'spot': x, 'pnl': y} dicts, one per step.
    """
    step_size = (spot_max - spot_min) / steps
    results = []

    for i in range(steps + 1):
        spot = spot_min + i * step_size
        total_pnl = 0.0

        for leg in legs:
            action      = leg['action'].upper()
            option_type = leg['option_type'].upper()
            strike      = leg['strike']
            premium     = leg['premium']
            lot_size    = leg.get('lot_size', 1)
            lots        = leg.get('lots', 1)
            multiplier  = lot_size * lots

            # Intrinsic value at expiry (what the contract is worth at expiry)
            if option_type == 'CE':
                intrinsic = max(spot - strike, 0.0)   # call is only worth positive diff
            elif option_type == 'PE':
                intrinsic = max(strike - spot, 0.0)   # put only worth positive diff
            else:   # FUT — linear P&L, no optionality
                intrinsic = spot - strike

            # Net P&L for this leg:
            # BUY: you paid the premium, you receive the intrinsic at expiry
            # SELL: you received the premium, you pay the intrinsic at expiry
            if action == 'BUY':
                leg_pnl = (intrinsic - premium) * multiplier
            else:
                leg_pnl = (premium - intrinsic) * multiplier

            total_pnl += leg_pnl

        results.append({'spot': round(spot, 2), 'pnl': round(total_pnl, 2)})

    return results
