"""
Multi-leg options strategy builder — Sensibull-style.

Sensibull (sensibull.com) is a popular Indian options platform that lets traders
build, visualise, and compare multi-leg strategies.  This module replicates the
core engine: given a live option chain, it constructs named strategies, calculates
payoff-at-expiry curves, combined Greeks, and key metrics.

Supported strategies (14 total):
  Directional  : long_call, long_put, covered_call, protective_put
  Credit spreads: bull_put_spread, bear_call_spread
  Debit spreads : bull_call_spread, bear_put_spread
  Volatility   : long_straddle, short_straddle, long_strangle, short_strangle
  Advanced     : iron_condor, iron_butterfly

Usage:
    chain_data = fetch_option_chain('BANKNIFTY')   # from strategy_scanner.py
    builder = StrategyBuilder(chain_data)
    result  = builder.build('iron_condor', lots=1)
    print(result.as_dict())

    # Or get recommendations for your market view:
    recs = builder.recommend(outlook='neutral', iv_rank=65, lots=1)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .black_scholes import Greeks, greeks, implied_volatility, payoff_at_expiry, price_option

try:
    from .config import RISK_FREE_RATE
except ImportError:
    RISK_FREE_RATE = 0.068


# ── Leg ───────────────────────────────────────────────────────────────────────

@dataclass
class Leg:
    """
    A single option or futures leg inside a multi-leg strategy.

    option_type : 'CE' (call), 'PE' (put), or 'FUT' (futures — used for
                  covered call / protective put where you hold the underlying)
    action      : 'BUY' or 'SELL'
    strike      : the option strike price (or futures entry for FUT legs)
    lots        : number of contracts
    lot_size    : contract multiplier  (e.g. 15 for BankNifty)
    premium     : market price per unit you pay (BUY) or receive (SELL)
    iv          : implied volatility in decimal form (0.20 = 20%)
    greeks      : computed Greeks for this leg (None for FUT)
    """
    option_type: str
    action: str
    strike: float
    lots: int
    lot_size: int
    premium: float
    iv: Optional[float] = field(default=None)
    greeks: Optional[Greeks] = field(default=None)

    def as_dict(self) -> dict:
        return {
            'option_type': self.option_type,
            'action':      self.action,
            'strike':      self.strike,
            'lots':        self.lots,
            'lot_size':    self.lot_size,
            'premium':     round(self.premium, 2),
            'iv_pct':      round(self.iv * 100, 2) if self.iv else None,
            'greeks': {
                'delta': self.greeks.delta,
                'gamma': self.greeks.gamma,
                'theta': self.greeks.theta,
                'vega':  self.greeks.vega,
            } if self.greeks else None,
        }


# ── StrategyResult ────────────────────────────────────────────────────────────

@dataclass
class StrategyResult:
    """
    Full output of a built strategy including payoff curve, Greeks, and metrics.

    net_premium  : positive = debit (you pay to enter), negative = credit (you receive)
    max_profit   : maximum possible P&L.  float('inf') = unlimited (e.g. long call)
    max_loss     : maximum possible loss. float('inf') = unlimited (e.g. short straddle)
    breakevens   : spot price(s) where P&L = 0 at expiry
    payoff       : list of {spot, pnl} covering ±25% around spot at expiry
    """
    name: str
    description: str
    outlook: str                  # 'bullish' | 'bearish' | 'neutral' | 'volatile'
    legs: list[Leg]
    net_premium: float
    max_profit: float             # float('inf') for unlimited
    max_loss: float               # float('inf') for unlimited
    breakevens: list[float]
    combined_greeks: Greeks
    payoff: list[dict]            # [{spot: float, pnl: float}, ...]
    lot_size: int
    lots: int

    def as_dict(self) -> dict:
        return {
            'name':        self.name,
            'description': self.description,
            'outlook':     self.outlook,
            'legs':        [leg.as_dict() for leg in self.legs],
            'net_premium': round(self.net_premium, 2),
            'max_profit':  self.max_profit if self.max_profit != float('inf') else 'unlimited',
            'max_loss':    self.max_loss   if self.max_loss   != float('inf') else 'unlimited',
            'breakevens':  [round(b, 2) for b in self.breakevens],
            'combined_greeks': {
                'delta': round(self.combined_greeks.delta, 4),
                'gamma': round(self.combined_greeks.gamma, 6),
                'theta': round(self.combined_greeks.theta, 4),
                'vega':  round(self.combined_greeks.vega,  4),
            },
            'payoff':   self.payoff,
            'lot_size': self.lot_size,
            'lots':     self.lots,
        }


# ── StrategyBuilder ───────────────────────────────────────────────────────────

class StrategyBuilder:
    """
    Constructs any of 14 named options strategies from a live option chain.

    The option_chain dict (produced by strategy_scanner.fetch_option_chain) must have:
        spot      : float  — current underlying price
        T         : float  — time to expiry in years
        chain     : list[dict] — each row has: strike, ce_price, pe_price,
                                 ce_iv, pe_iv, ce_oi, pe_oi
        lot_size  : int
    """

    # catalogue maps strategy key → (display name, market outlook, one-line description)
    STRATEGY_CATALOGUE: dict[str, tuple[str, str, str]] = {
        # ── Directional ────────────────────────────────────────────────────────
        'long_call': (
            'Long Call', 'bullish',
            'Buy ATM call. Unlimited upside if spot rises; max loss = premium paid.',
        ),
        'long_put': (
            'Long Put', 'bearish',
            'Buy ATM put. Profits if spot falls sharply; max loss = premium paid.',
        ),
        'covered_call': (
            'Covered Call', 'neutral',
            'Hold underlying (long futures) + sell OTM call to earn premium. '
            'Capped upside but lower cost basis.',
        ),
        'protective_put': (
            'Protective Put', 'bullish',
            'Hold underlying (long futures) + buy OTM put as downside insurance.',
        ),
        # ── Credit spreads (receive premium; profit in a direction with limited risk) ─
        'bull_put_spread': (
            'Bull Put Spread', 'bullish',
            'Sell higher put + buy lower put. Net credit upfront. '
            'Profits if spot stays above the short put strike.',
        ),
        'bear_call_spread': (
            'Bear Call Spread', 'bearish',
            'Sell lower call + buy higher call. Net credit. '
            'Profits if spot stays below the short call strike.',
        ),
        # ── Debit spreads (pay premium; defined-risk directional plays) ────────
        'bull_call_spread': (
            'Bull Call Spread', 'bullish',
            'Buy ATM call + sell OTM call. Lower cost than long call; upside capped.',
        ),
        'bear_put_spread': (
            'Bear Put Spread', 'bearish',
            'Buy ATM put + sell OTM put. Lower cost than long put; downside profit capped.',
        ),
        # ── Volatility: buy both sides (profit from big moves) ─────────────────
        'long_straddle': (
            'Long Straddle', 'volatile',
            'Buy ATM call + ATM put (same strike). Profits from any large move. '
            'Best when IV is low and a big event is expected.',
        ),
        'long_strangle': (
            'Long Strangle', 'volatile',
            'Buy OTM call + OTM put (different strikes). Cheaper than straddle; '
            'needs an even bigger move to profit.',
        ),
        # ── Volatility: sell both sides (profit from quiet markets) ───────────
        'short_straddle': (
            'Short Straddle', 'neutral',
            'Sell ATM call + ATM put. Max profit if spot pins at strike; '
            'unlimited risk on both sides. Best when IV is very high.',
        ),
        'short_strangle': (
            'Short Strangle', 'neutral',
            'Sell OTM call + OTM put. Wider profit zone than short straddle; '
            'still unlimited risk. Suited to very high IV environments.',
        ),
        # ── Advanced (defined risk on all sides) ──────────────────────────────
        'iron_condor': (
            'Iron Condor', 'neutral',
            'Sell inner OTM call+put, buy outer OTM call+put as wings. '
            'Collect premium if spot stays in the profit zone between wings. '
            'Defined risk on all sides — the most popular NSE F&O strategy.',
        ),
        'iron_butterfly': (
            'Iron Butterfly', 'neutral',
            'Sell ATM call+put, buy OTM wings. Higher premium collected than Iron '
            'Condor but narrower profit zone. Max profit exactly at ATM at expiry.',
        ),
    }

    # Strategies with theoretically unlimited profit (spot can go to infinity)
    _UNLIMITED_PROFIT = {'long_call', 'long_put', 'long_straddle', 'long_strangle',
                         'covered_call', 'protective_put'}
    # Strategies with theoretically unlimited loss (naked short options)
    _UNLIMITED_LOSS   = {'short_straddle', 'short_strangle'}

    def __init__(self, option_chain: dict) -> None:
        self.spot     = option_chain['spot']
        self.T        = option_chain['T']
        self.chain    = option_chain['chain']   # list of strike rows
        self.lot_size = option_chain.get('lot_size', 1)
        self.r        = RISK_FREE_RATE
        self._strikes = sorted({row['strike'] for row in self.chain})

    # ── Strike selection helpers ───────────────────────────────────────────────

    def _atm(self) -> float:
        """Strike closest to current spot (ATM = at-the-money)."""
        return min(self._strikes, key=lambda k: abs(k - self.spot))

    def _otm_call(self, pct: float) -> float:
        """OTM call strike ~`pct`% above spot (e.g. pct=0.02 → 2% OTM)."""
        return min(self._strikes, key=lambda k: abs(k - self.spot * (1 + pct)))

    def _otm_put(self, pct: float) -> float:
        """OTM put strike ~`pct`% below spot."""
        return min(self._strikes, key=lambda k: abs(k - self.spot * (1 - pct)))

    # ── Market data helpers ────────────────────────────────────────────────────

    def _premium(self, strike: float, option_type: str) -> float:
        """
        Return the market premium for a strike from the option chain.
        Falls back to a Black-Scholes price at 20% IV if the strike isn't in the chain.
        """
        key = 'ce_price' if option_type == 'CE' else 'pe_price'
        for row in self.chain:
            if row['strike'] == strike:
                price = row.get(key)
                if price and float(price) > 0:
                    return float(price)
        # Fallback: theoretical price at default 20% IV
        return price_option(self.spot, strike, self.T, self.r, 0.20, option_type)

    def _iv(self, strike: float, option_type: str) -> Optional[float]:
        """Return IV from chain metadata or back-solve it from the market price."""
        key = 'ce_iv' if option_type == 'CE' else 'pe_iv'
        for row in self.chain:
            if row['strike'] == strike:
                iv = row.get(key)
                if iv and float(iv) > 0:
                    return float(iv)
        # Back-solve from market price
        prem = self._premium(strike, option_type)
        return implied_volatility(prem, self.spot, strike, self.T, self.r, option_type)

    # ── Leg factory ───────────────────────────────────────────────────────────

    def _leg(self, action: str, option_type: str, strike: float, lots: int) -> Leg:
        """
        Create a single Leg with market premium, IV, and Greeks.
        FUT (futures) legs use a simplified treatment: delta=±1, no other Greeks.
        """
        if option_type == 'FUT':
            # Model the underlying as a futures position entered at spot
            fut_greeks = Greeks(
                delta=1.0 if action == 'BUY' else -1.0,
                gamma=0.0, theta=0.0, vega=0.0, rho=0.0,
            )
            return Leg(
                option_type='FUT', action=action, strike=self.spot,
                lots=lots, lot_size=self.lot_size,
                premium=self.spot,   # notional entry price
                iv=None, greeks=fut_greeks,
            )

        prem = self._premium(strike, option_type)
        iv   = self._iv(strike, option_type)
        g    = greeks(self.spot, strike, self.T, self.r, iv or 0.20, option_type)
        return Leg(
            option_type=option_type, action=action, strike=strike,
            lots=lots, lot_size=self.lot_size,
            premium=round(prem, 2), iv=iv, greeks=g,
        )

    # ── Portfolio-level calculations ───────────────────────────────────────────

    def _combine_greeks(self, legs: list[Leg]) -> Greeks:
        """
        Sum Greeks across all legs.
        BUY legs add their Greeks; SELL legs subtract them.
        Scale by lots × lot_size so Greeks reflect total position size.
        """
        delta = gamma = theta = vega = rho = 0.0
        for leg in legs:
            if not leg.greeks:
                continue
            sign  = 1 if leg.action == 'BUY' else -1
            scale = leg.lots  # lot_size baked into per-lot Greeks already
            delta += sign * leg.greeks.delta * scale
            gamma += sign * leg.greeks.gamma * scale
            theta += sign * leg.greeks.theta * scale
            vega  += sign * leg.greeks.vega  * scale
            rho   += sign * leg.greeks.rho   * scale
        return Greeks(delta=round(delta, 4), gamma=round(gamma, 6),
                      theta=round(theta, 4), vega=round(vega, 4), rho=round(rho, 4))

    def _net_premium(self, legs: list[Leg]) -> float:
        """
        Net cash outlay: positive = debit (you pay), negative = credit (you receive).
        Debit strategies cost money upfront; credit strategies put cash in your account.
        """
        total = 0.0
        for leg in legs:
            cost = leg.premium * leg.lots * leg.lot_size
            total += cost if leg.action == 'BUY' else -cost
        return round(total, 2)

    def _build_payoff(self, legs: list[Leg]) -> list[dict]:
        """Build the ±25% payoff curve for the whole strategy."""
        leg_dicts = [
            {
                'option_type': leg.option_type,
                'action':      leg.action,
                'strike':      leg.strike,
                'premium':     leg.premium,
                'lots':        leg.lots,
                'lot_size':    leg.lot_size,
            }
            for leg in legs
        ]
        return payoff_at_expiry(
            leg_dicts,
            spot_min=self.spot * 0.75,
            spot_max=self.spot * 1.25,
            steps=80,
        )

    def _breakevens(self, payoff: list[dict]) -> list[float]:
        """
        Find spot prices where the P&L curve crosses zero.
        Uses linear interpolation between consecutive points that straddle zero.
        """
        bvs = []
        for i in range(len(payoff) - 1):
            p1, p2 = payoff[i]['pnl'], payoff[i + 1]['pnl']
            if p1 * p2 < 0:   # sign change → zero crossing
                s1, s2 = payoff[i]['spot'], payoff[i + 1]['spot']
                bv = s1 + (s2 - s1) * abs(p1) / (abs(p1) + abs(p2))
                bvs.append(round(bv, 2))
        return bvs

    def _max_metrics(self, payoff: list[dict]) -> tuple[float, float]:
        """(max_profit, max_loss) from the payoff curve within the ±25% range."""
        pnls  = [p['pnl'] for p in payoff]
        return round(max(pnls), 2), round(abs(min(pnls)), 2)

    # ── Legs factory per strategy ─────────────────────────────────────────────

    def _make_legs(self, strategy: str, lots: int, otm_pct: float) -> list[Leg]:
        """
        Define the specific legs for each strategy.

        otm_pct controls how far OTM the short legs are placed.
        0.02 = 2% OTM (default); higher = wider and safer, but less premium.
        """
        atm     = self._atm()
        otm_c   = self._otm_call(otm_pct)
        otm_p   = self._otm_put(otm_pct)
        # Outer wings for iron condor/butterfly — wider than inner legs
        outer_c = self._otm_call(otm_pct * 2.5)
        outer_p = self._otm_put(otm_pct * 2.5)

        _l = self._leg   # shorthand

        if strategy == 'long_call':
            return [_l('BUY', 'CE', atm, lots)]

        if strategy == 'long_put':
            return [_l('BUY', 'PE', atm, lots)]

        if strategy == 'covered_call':
            # Long underlying (futures) + sell OTM call to reduce cost basis
            return [_l('BUY', 'FUT', atm, lots), _l('SELL', 'CE', otm_c, lots)]

        if strategy == 'protective_put':
            # Long underlying + buy OTM put as portfolio insurance
            return [_l('BUY', 'FUT', atm, lots), _l('BUY', 'PE', otm_p, lots)]

        if strategy == 'long_straddle':
            # Buy both ATM call and put — profits from any large directional move
            return [_l('BUY', 'CE', atm, lots), _l('BUY', 'PE', atm, lots)]

        if strategy == 'short_straddle':
            # Sell both — collect maximum premium; naked risk on both sides
            return [_l('SELL', 'CE', atm, lots), _l('SELL', 'PE', atm, lots)]

        if strategy == 'long_strangle':
            # Buy OTM call and OTM put — cheaper than straddle, needs bigger move
            return [_l('BUY', 'CE', otm_c, lots), _l('BUY', 'PE', otm_p, lots)]

        if strategy == 'short_strangle':
            # Sell OTM call and put — wider profit zone than short straddle
            return [_l('SELL', 'CE', otm_c, lots), _l('SELL', 'PE', otm_p, lots)]

        if strategy == 'bull_call_spread':
            # Buy lower call + sell upper call: capped upside, lower cost than naked call
            return [_l('BUY', 'CE', atm, lots), _l('SELL', 'CE', otm_c, lots)]

        if strategy == 'bear_put_spread':
            # Buy higher put + sell lower put: capped downside profit, lower cost
            return [_l('BUY', 'PE', atm, lots), _l('SELL', 'PE', otm_p, lots)]

        if strategy == 'bull_put_spread':
            # Sell higher put + buy lower put: credit received; profits if spot stays up
            return [_l('SELL', 'PE', atm, lots), _l('BUY', 'PE', otm_p, lots)]

        if strategy == 'bear_call_spread':
            # Sell lower call + buy higher call: credit received; profits if spot stays down
            return [_l('SELL', 'CE', atm, lots), _l('BUY', 'CE', otm_c, lots)]

        if strategy == 'iron_condor':
            # Four legs: sell inner OTM call+put, buy outer wings for protection
            # Net credit received; profitable as long as spot stays inside the inner strikes
            return [
                _l('BUY',  'PE', outer_p, lots),   # lower wing — caps downside loss
                _l('SELL', 'PE', otm_p,   lots),   # inner short put — where credit comes from
                _l('SELL', 'CE', otm_c,   lots),   # inner short call
                _l('BUY',  'CE', outer_c, lots),   # upper wing — caps upside loss
            ]

        if strategy == 'iron_butterfly':
            # Sell ATM straddle + buy OTM wings: higher credit than condor, narrower zone
            return [
                _l('BUY',  'PE', otm_p, lots),   # lower wing
                _l('SELL', 'PE', atm,   lots),   # ATM short put
                _l('SELL', 'CE', atm,   lots),   # ATM short call
                _l('BUY',  'CE', otm_c, lots),   # upper wing
            ]

        raise ValueError(f'Unknown strategy key: "{strategy}". '
                         f'Valid keys: {list(self.STRATEGY_CATALOGUE)}')

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        strategy: str,
        lots: int = 1,
        otm_pct: float = 0.02,
    ) -> StrategyResult:
        """
        Build a named strategy and return the full StrategyResult.

        strategy : one of the keys in STRATEGY_CATALOGUE (e.g. 'iron_condor')
        lots     : number of contracts per leg
        otm_pct  : how far out-of-the-money to place spread/strangle legs
                   (0.02 = 2% from ATM)
        """
        name, outlook, desc = self.STRATEGY_CATALOGUE[strategy]
        legs   = self._make_legs(strategy, lots, otm_pct)
        payoff = self._build_payoff(legs)

        max_p_curve, max_l_curve = self._max_metrics(payoff)

        return StrategyResult(
            name=name,
            description=desc,
            outlook=outlook,
            legs=legs,
            net_premium=self._net_premium(legs),
            # For unlimited-risk/reward strategies, report what's within our ±25% window
            # but flag them as unlimited so the UI can display the appropriate warning
            max_profit=float('inf') if strategy in self._UNLIMITED_PROFIT else max_p_curve,
            max_loss=float('inf')   if strategy in self._UNLIMITED_LOSS   else max_l_curve,
            breakevens=self._breakevens(payoff),
            combined_greeks=self._combine_greeks(legs),
            payoff=payoff,
            lot_size=self.lot_size,
            lots=lots,
        )

    def recommend(
        self,
        outlook: str,
        iv_rank: float,
        lots: int = 1,
        otm_pct: float = 0.02,
    ) -> list[StrategyResult]:
        """
        Recommend 2-3 appropriate strategies based on market view and IV environment.

        outlook  : 'bullish' | 'bearish' | 'neutral' | 'volatile'
        iv_rank  : 0-100 (0 = IV at 1-year low, 100 = IV at 1-year high)
                   When IV is high (>60) → prefer selling strategies (collect rich premium)
                   When IV is low (<40)  → prefer buying strategies (options are cheap)

        This mirrors Sensibull's "Strategy Finder" which recommends strategies
        based on your view + the current IV environment.
        """
        iv_high = iv_rank > 60   # above 60th percentile → premium is expensive

        # Each entry: (low-IV favourites, high-IV favourites)
        _MAP: dict[str, tuple[list[str], list[str]]] = {
            'bullish':  (['long_call', 'bull_call_spread'],      ['bull_put_spread', 'covered_call']),
            'bearish':  (['long_put',  'bear_put_spread'],       ['bear_call_spread']),
            'neutral':  (['iron_condor', 'iron_butterfly'],      ['short_strangle', 'iron_condor', 'short_straddle']),
            'volatile': (['long_straddle', 'long_strangle'],     ['long_straddle']),
        }
        choices = _MAP.get(outlook.lower(), _MAP['neutral'])
        selected = choices[1] if iv_high else choices[0]

        results = []
        for key in selected:
            try:
                results.append(self.build(key, lots=lots, otm_pct=otm_pct))
            except Exception:
                pass
        return results
