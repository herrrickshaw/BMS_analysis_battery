"""
Live option chain fetcher and strategy analysis runner.

Fetches real option chain data via yfinance (works for US equities and some
NSE indices), then hands it to StrategyBuilder for strategy analysis.

For instruments where yfinance doesn't have option chains (e.g. BankNifty
futures on MCX), a synthetic chain is generated using Black-Scholes at a
reasonable default IV.  This gives meaningful payoff curves and Greeks
for educational use and strategy planning even without live data.

Data source priority:
    1. yfinance live option chain  (best — real market premiums and IV)
    2. Synthetic B-S chain         (fallback — theoretical prices at default IV)

The broker adapters in broker.py can replace step 1 with real-time
NSE/MCX data when API keys are configured.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import numpy as np
import yfinance as yf

from .black_scholes import RISK_FREE_RATE, implied_volatility, price_option
from .options_strategies import StrategyBuilder, StrategyResult

log = logging.getLogger(__name__)

# Default IV when no live data is available — roughly typical for Indian indices
_DEFAULT_IV = 0.18   # 18%

# ── Instrument → yfinance symbol mapping ──────────────────────────────────────
# BankNifty and Nifty have spot price data on yfinance but live option chains
# are not available; they fall back to a synthetic chain automatically.
_YF_SYMBOLS: dict[str, str] = {
    'BANKNIFTY': '^NSEBANK',
    'NIFTY':     '^NSEI',
    'CRUDEOIL':  'CL=F',   # Crude Oil front-month futures on NYMEX
    'SILVER':    'SI=F',   # Silver futures on COMEX
    'GOLD':      'GC=F',
    'NIFTYIT':   '^CNXIT',
    # For US equities/ETFs, pass the ticker directly (e.g. 'AAPL', 'SPY')
}

# Contract lot sizes for Indian instruments
_LOT_SIZES: dict[str, int] = {
    '^NSEBANK': 15,
    '^NSEI':    50,
    'CL=F':     100,
    'SI=F':     5000,
    'GC=F':     100,
}


# ── Helper functions ──────────────────────────────────────────────────────────

def _time_to_expiry(expiry: str | date) -> float:
    """
    Convert an expiry date to years remaining.
    Returns near-zero (not exactly zero) for today's expiry to avoid
    division-by-zero in Black-Scholes.
    """
    if isinstance(expiry, str):
        exp_date = datetime.strptime(expiry, '%Y-%m-%d').date()
    else:
        exp_date = expiry
    days = (exp_date - date.today()).days
    return max(days / 365.0, 1e-4)   # minimum 1/10000 year


def _nearest_expiry(ticker: yf.Ticker) -> Optional[str]:
    """Return the nearest available expiry from yfinance, or None."""
    try:
        exps = ticker.options   # returns a tuple of expiry date strings
        return exps[0] if exps else None
    except Exception:
        return None


def _chain_from_yf(ticker: yf.Ticker, expiry: str, spot: float) -> list[dict]:
    """
    Download and normalise a yfinance option chain into our standard format.
    Filters to strikes within ±20% of spot to keep the chain manageable.
    """
    try:
        import pandas as pd
        raw = ticker.option_chain(expiry)
        calls = raw.calls[['strike', 'lastPrice', 'impliedVolatility', 'openInterest', 'volume']].copy()
        puts  = raw.puts [['strike', 'lastPrice', 'impliedVolatility', 'openInterest', 'volume']].copy()
        calls.columns = ['strike', 'ce_price', 'ce_iv', 'ce_oi', 'ce_vol']
        puts.columns  = ['strike', 'pe_price', 'pe_iv', 'pe_oi', 'pe_vol']

        merged = calls.merge(puts, on='strike', how='outer').fillna(0)
        # Keep only strikes within ±20% of spot — far-OTM options have wide
        # bid/ask spreads that make strategy analysis unreliable
        merged = merged[(merged['strike'] >= spot * 0.80) & (merged['strike'] <= spot * 1.20)]
        return merged.to_dict('records')
    except Exception as exc:
        log.debug('yfinance option chain unavailable for %s: %s', expiry, exc)
        return []


def _synthetic_chain(spot: float, T: float, sigma: float = _DEFAULT_IV) -> list[dict]:
    """
    Build a theoretical option chain using Black-Scholes.

    Used when no live chain is available (e.g. BankNifty via yfinance).
    Generates 41 strikes from -20% to +20% around spot in 1% steps.
    All prices are theoretical at the given sigma; IV is set equal to sigma.
    """
    r    = RISK_FREE_RATE
    rows = []
    # Round to nearest integer to produce clean strike levels
    base = round(spot)
    step = max(round(spot * 0.01), 1)   # ~1% step

    for i in range(-20, 21):
        K = base + i * step
        if K <= 0:
            continue
        ce = max(price_option(spot, K, T, r, sigma, 'CE'), 0.05)
        pe = max(price_option(spot, K, T, r, sigma, 'PE'), 0.05)
        rows.append({
            'strike':  float(K),
            'ce_price': round(ce, 2),
            'pe_price': round(pe, 2),
            'ce_iv':    sigma,
            'pe_iv':    sigma,
            'ce_oi':    0,
            'pe_oi':    0,
        })
    return rows


def _spot_price(ticker: yf.Ticker, yf_symbol: str) -> float:
    """Fetch current spot price via yfinance fast_info or recent history."""
    try:
        info = ticker.fast_info
        price = (
            getattr(info, 'last_price', None)
            or getattr(info, 'regular_market_price', None)
        )
        if price and float(price) > 0:
            return float(price)
    except Exception:
        pass
    # Fallback: last close from recent history
    try:
        hist = ticker.history(period='2d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception:
        pass
    raise ValueError(f'Cannot determine spot price for {yf_symbol}')


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_option_chain(symbol: str, expiry: Optional[str] = None) -> dict:
    """
    Fetch (or synthesise) an option chain for a symbol.

    Returns a dict consumed directly by StrategyBuilder:
        symbol       : original symbol string
        yf_symbol    : yfinance ticker used
        spot         : current spot price
        expiry       : expiry date string (or 'synthetic')
        T            : time to expiry in years
        chain        : list of strike dicts
        lot_size     : contract multiplier
        data_source  : 'live' | 'synthetic'
    """
    yf_symbol = _YF_SYMBOLS.get(symbol.upper(), symbol.upper())
    lot_size  = _LOT_SIZES.get(yf_symbol, 1)

    ticker = yf.Ticker(yf_symbol)
    spot   = _spot_price(ticker, yf_symbol)

    # Resolve expiry
    if expiry is None:
        expiry = _nearest_expiry(ticker)

    T = _time_to_expiry(expiry) if expiry else 7 / 365.0

    # Try live chain first
    chain: list[dict] = []
    if expiry:
        chain = _chain_from_yf(ticker, expiry, spot)

    data_source = 'live'
    if not chain:
        log.info('%s: no live option chain — using synthetic Black-Scholes chain '
                 '(common for NSE indices via yfinance)', symbol)
        chain = _synthetic_chain(spot, T)
        data_source = 'synthetic'

    return {
        'symbol':      symbol,
        'yf_symbol':   yf_symbol,
        'spot':        spot,
        'expiry':      expiry or 'synthetic',
        'T':           T,
        'chain':       chain,
        'lot_size':    lot_size,
        'data_source': data_source,
    }


# yfinance's `impliedVolatility` field is frequently a stale/placeholder value
# (observed as low as 0.00001) rather than a genuine quote, especially for
# thinly-traded strikes — well below any real-world IV. Treat anything below
# this floor as missing rather than trusting it at face value.
_MIN_PLAUSIBLE_IV = 0.01   # 1%


def compute_atm_iv(chain_data: dict) -> float:
    """
    Estimate the ATM implied volatility from the option chain.
    ATM IV is the most commonly reported single-number summary of options pricing.
    """
    spot  = chain_data['spot']
    chain = chain_data['chain']
    T     = chain_data['T']

    if not chain:
        return _DEFAULT_IV

    # Find the strike closest to spot
    atm = min(chain, key=lambda r: abs(r['strike'] - spot))

    # Prefer IV directly from the chain metadata (yfinance provides this) —
    # but reject implausibly small values rather than trusting them at face
    # value (see _MIN_PLAUSIBLE_IV above).
    for iv_key in ('ce_iv', 'pe_iv'):
        iv = atm.get(iv_key)
        if iv and float(iv) >= _MIN_PLAUSIBLE_IV:
            return float(iv)

    # Fallback: back-solve from ATM call price
    ce_price = atm.get('ce_price', 0)
    if ce_price and float(ce_price) > 0:
        iv = implied_volatility(float(ce_price), spot, atm['strike'], T, RISK_FREE_RATE, 'CE')
        if iv and iv >= _MIN_PLAUSIBLE_IV:
            return iv

    return _DEFAULT_IV


def estimate_iv_rank(symbol: str, current_iv: float) -> float:
    """
    Estimate IV rank on a 0-100 scale.

    IV rank = (current_IV − 1yr_low) / (1yr_high − 1yr_low) × 100

    True IV rank requires a year of stored IV data; we approximate by using
    rolling 20-day realised volatility as a proxy for IV over the past year.

    IV rank > 60 → options are expensive → favour selling strategies
    IV rank < 40 → options are cheap     → favour buying strategies
    """
    try:
        yf_symbol = _YF_SYMBOLS.get(symbol.upper(), symbol.upper())
        hist      = yf.Ticker(yf_symbol).history(period='1y')

        if hist.empty or len(hist) < 30:
            return 50.0   # not enough history → neutral estimate

        # Rolling 20-day realised vol annualised (log-returns)
        log_returns = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        rv20        = log_returns.rolling(20).std() * np.sqrt(252)

        low_1y  = float(rv20.min())
        high_1y = float(rv20.max())

        if high_1y <= low_1y:
            return 50.0

        rank = (current_iv - low_1y) / (high_1y - low_1y) * 100
        return round(max(0.0, min(rank, 100.0)), 1)
    except Exception as exc:
        log.debug('IV rank estimation failed for %s: %s', symbol, exc)
        return 50.0   # neutral fallback


def run_strategy_scan(
    symbol: str,
    outlook: str = 'neutral',
    lots: int = 1,
    expiry: Optional[str] = None,
    otm_pct: float = 0.02,
) -> dict:
    """
    Full strategy analysis entry point — called by the FastAPI router.

    Returns a structured dict with:
        spot            : current price
        atm_iv          : ATM IV in % (e.g. 18.5 means 18.5%)
        iv_rank         : 0-100 percentile of current IV vs past year
        recommended     : 2-3 strategies suited to the given outlook + IV rank
        strategies      : complete catalogue of all 14 strategies with payoff data
        data_source     : 'live' or 'synthetic'
    """
    chain_data = fetch_option_chain(symbol, expiry)
    spot       = chain_data['spot']
    atm_iv     = compute_atm_iv(chain_data)
    iv_rank    = estimate_iv_rank(symbol, atm_iv)

    builder = StrategyBuilder(chain_data)

    # Build recommended strategies for the given outlook
    recommended = builder.recommend(outlook, iv_rank, lots=lots, otm_pct=otm_pct)

    # Build the complete catalogue (all 14 strategies) for the full-view panel
    all_strategies: dict[str, dict] = {}
    for key in StrategyBuilder.STRATEGY_CATALOGUE:
        try:
            all_strategies[key] = builder.build(key, lots=lots, otm_pct=otm_pct).as_dict()
        except Exception as exc:
            log.debug('Could not build strategy %s: %s', key, exc)

    return {
        'symbol':      symbol,
        'spot':        round(spot, 2),
        'expiry':      chain_data['expiry'],
        'T_days':      round(chain_data['T'] * 365),
        'atm_iv_pct':  round(atm_iv * 100, 2),    # percentage, e.g. 18.5
        'iv_rank':     iv_rank,
        'outlook':     outlook,
        'data_source': chain_data['data_source'],
        'recommended': [r.as_dict() for r in recommended],
        'strategies':  all_strategies,
    }
