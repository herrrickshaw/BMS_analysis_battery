#!/usr/bin/env python3
"""
adaptive_liquidity.py — a liquidity filter that adapts to each market AND to your capital.

WHY THE EXISTING FILTER IS NOT ENOUGH
------------------------------------
liquidity.py gates on ABSOLUTE USD bands, anchored to the India floor the user chose
(Rs 1 crore/day ~ USD 120k) and carried across every market:

    SCAN_TIERS_USD = ((12M,"T1_MEGA"),(3M,"T2_LARGE"),(600k,"T3_MID"),(0,"T4_SMALL"))

That is right for the FLOOR and wrong for the TIERS, and today's runs show both:

  * As a floor it works. Rs 1cr/day removes names you genuinely cannot buy, and it
    removed corporate debt, liquid-fund ETFs and REITs from the India scan without any
    instrument-type rule.

  * As TIERS it fails to discriminate. The first US sweep put 94% of its sample in
    T1_MEGA — because the US median stock trades $0.4M/day while the tested names traded
    $17.3M/day. Bands tuned to India cannot separate US stocks from each other. A tier
    that swallows 94% of the sample is not a tier.

The two jobs are different and need different logic:

    FLOOR  = "can this be bought at all?"      -> ABSOLUTE, and capital-dependent
    TIERS  = "how liquid is this, relative     -> PERCENTILE, within the market's
              to its own market?"                 own distribution

WHY PERCENTILE TIERS
--------------------
"Illiquid" must mean the same thing in Mumbai and New York for a cross-market claim to
survive. It cannot, if the cut is a fixed dollar number: today's US "illiquid" tercile
sits at the 77th percentile of US liquidity — i.e. US MID-CAP — which is why every US
result carries a range-restriction caveat. Percentile tiers make the comparison honest
and make each market self-calibrating: no constants to re-tune when a market re-rates,
a currency moves, or a new exchange is added.

WHY THE FLOOR MUST KNOW YOUR CAPITAL
------------------------------------
The cost model (cost_vs_edge.py) found the binding constraint is EXECUTION, not fees:
above ~15-20% of a name's average daily volume a position cannot be built in one day
near the quoted price. That threshold moves with how much money you deploy:

    $10k portfolio  -> $1k positions   -> almost everything is tradeable
    $250k portfolio -> $25k positions  -> ~15% of ADV on a $160k/day name: at the limit
    $10M portfolio  -> $1M positions   -> 607% of ADV: the trade does not exist

So a single global floor is wrong for everyone except the person it was tuned for. This
derives the floor from capital instead: min_ADV = position_size / MAX_ADV_PCT.

Rs 1 crore/day is preserved as the ABSOLUTE minimum regardless of capital — below it a
name is untradeable for anyone, and it is the user's standing gate.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Execution ceiling. Above this share of average daily volume a position cannot be built
# in one day near the quoted price, and the linear impact model understates cost exactly
# where it matters. Measured, not assumed: at 60.8% of ADV the model still reports a
# positive net edge (+3.2%) for a trade nobody can place — which is why the ceiling is a
# SEPARATE rule and not a cost term.
MAX_ADV_PCT = 15.0

# The user's standing floor, in USD. Below this a name is untradeable at any size and
# is usually not an operating equity at all (in India this alone removed corporate debt,
# liquid-fund ETFs and REIT/InvITs without any instrument-type rule).
ABSOLUTE_FLOOR_USD = 120_000        # ~ Rs 1 crore/day

# Percentile cuts, applied WITHIN each market. Names below the floor are excluded before
# ranking, so the tiers describe the TRADEABLE universe rather than being dragged down by
# shells that were never candidates.
TIER_CUTS = ((80, "T1_MOST_LIQUID"), (60, "T2_LIQUID"), (40, "T3_MID"),
             (20, "T4_ILLIQUID"), (0, "T5_MOST_ILLIQUID"))


@dataclass
class Gate:
    market: str
    capital_usd: float
    positions: int

    @property
    def position_usd(self) -> float:
        return self.capital_usd / max(self.positions, 1)

    @property
    def min_adv_usd(self) -> float:
        """Smallest ADV this capital can trade without breaching the execution ceiling.

        Never below the absolute floor: a name too thin for anyone stays excluded even
        for a tiny account.
        """
        return max(self.position_usd / (MAX_ADV_PCT / 100.0), ABSOLUTE_FLOOR_USD)


def classify(df: pd.DataFrame, gate: Gate, adv_col: str = "adv_usd") -> pd.DataFrame:
    """Add `tradeable`, `adv_pct`, and a percentile `tier` to a per-symbol frame.

    `df` needs one row per symbol with average daily turnover in USD.

    Tiers are computed on the TRADEABLE subset only. Ranking the whole universe would let
    untradeable shells define the percentile boundaries, so "T5_MOST_ILLIQUID" would mean
    "illiquid among names you cannot buy" — a tier nobody can act on.
    """
    out = df.copy()
    out["adv_pct"] = out[adv_col].apply(
        lambda a: (gate.position_usd / a * 100) if a and a > 0 else float("inf"))
    out["tradeable"] = (out[adv_col] >= gate.min_adv_usd) & (out["adv_pct"] <= MAX_ADV_PCT)

    out["tier"] = None
    ok = out["tradeable"]
    if ok.sum() >= 10:
        pct = out.loc[ok, adv_col].rank(pct=True) * 100
        for lo, name in TIER_CUTS:
            out.loc[ok & (pct >= lo) & out["tier"].isna(), "tier"] = name
    return out


def capacity(df: pd.DataFrame, positions: int = 10, adv_col: str = "adv_usd") -> pd.DataFrame:
    """Largest portfolio each market supports, at a range of universe breadths.

    Answers the question the fixed floor cannot: not "is this stock liquid?" but "how much
    money can this market's illiquid tail actually absorb?" — which is what decides whether
    a premium found there is reachable.
    """
    rows = []
    for name, q in (("median name", 0.50), ("bottom quartile", 0.25),
                    ("bottom decile", 0.10)):
        adv = df[adv_col].quantile(q)
        rows.append({"universe_point": name, "adv_usd": adv,
                     "max_position_usd": adv * MAX_ADV_PCT / 100.0,
                     "max_portfolio_usd": adv * MAX_ADV_PCT / 100.0 * positions})
    return pd.DataFrame(rows)


def describe(df: pd.DataFrame, market: str, adv_col: str = "adv_usd") -> str:
    """One line per market. Makes cross-market comparison possible without constants."""
    d = df[df[adv_col] > 0]
    if not len(d):
        return f"  {market}: no data"
    return (f"  {market:8s} n={len(d):>6,}  ADV median ${d[adv_col].median()/1e6:>8.2f}M"
            f"  p10 ${d[adv_col].quantile(.10)/1e6:>7.3f}M"
            f"  p90 ${d[adv_col].quantile(.90)/1e6:>8.2f}M"
            f"  above Rs1cr floor: {(d[adv_col] >= ABSOLUTE_FLOOR_USD).mean()*100:>4.0f}%")
