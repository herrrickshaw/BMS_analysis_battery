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

# ── country floors ────────────────────────────────────────────────────────────
# 🔴 THE PREVIOUS VERSION OF THIS BLOCK WAS FABRICATED. It set US $475k / JP $381k /
# KR $349k, each claimed to be "the 47th percentile of its own market — the same
# stringency as India's Rs 1 crore gate". Adversarial validation could not reproduce
# three of the four, and re-measurement shows why. The universe definition swings the
# answer 3x:
#
#     mkt   ALL names   LIVE only   LIVE+traded   claimed
#     US      $300k       $300k       $896k        $475k    <- matches NOTHING
#     IN      $110k       $284k       $284k        $120k
#     JP      $364k       $364k       $365k        $381k
#     KR      $311k       $311k       $342k        $349k
#
#   * US: 1,476 of 9,278 symbols are zero-turnover SPAC units, warrants and OTC
#     ordinaries. Counting them -> $300k, dropping them -> $896k. $475k reproduces under
#     NO definition — it cannot be reconstructed, so it was not measured.
#   * IN: Rs 1 crore looked like "the 47th percentile" ONLY because 1,079 of 3,476 names
#     in the panel are DELISTED. On the live universe it is the ~35th. The anchor the
#     whole construction rested on was an artifact of counting corpses.
#
# AND THE PREMISE WAS WRONG TOO, not just the arithmetic. Exporting "India's percentile"
# to three other markets exports an arbitrary choice and dresses it as a principle.
# Rs 1 crore is a POLICY CHOICE the user made for India. It is not a law of markets, and
# there is no reason Korea should inherit it.
#
# So the floors are gone. What remains is the rule that was always doing the real work:
#     CAPITAL floor  = position / MAX_ADV_PCT  — universal RULE, market-specific OUTCOME
# plus a per-market POLICY floor only where a human actually chose one.
#
# The reconciliation two validators arrived at independently, and the reason this is
# computed on the LIVE universe: delisted names BELONG in a backtest panel (they are what
# makes it survivorship-free) and MUST NOT be in a live-tradeability percentile. Same
# panel, two uses, two filters.
# THREE FLOORS, THREE JOBS. Collapsing them into one constant is what produced the
# fabricated numbers — a single $120k did all three jobs badly and answered none of the
# questions honestly.
#
#   1. STRUCTURAL — "is this a traded security at all?"  Absolute, tiny, universal.
#      Measured: removing any floor admits 3,106 US names of which 1,343 trade under
#      $10k/day (SPAC units, warrants, dormant shells). Below ~$10k/day a listing is not
#      something anyone transacts in, in ANY market. This is a weak claim about
#      existence, not a strong claim about investability — which is why it can be one
#      number for everywhere while a POLICY floor cannot.
#
#   2. POLICY — "what does the owner of this repo refuse to buy?"  Per market, and ONLY
#      where a human actually chose. India = Rs 1 crore. There is no US policy because
#      nobody set one, and inventing it is the bug this replaced.
#
#   3. CAPITAL — "can MY money build this position?"  position / MAX_ADV_PCT. The
#      constraint that actually binds, and the one a SCAN cannot apply because a scan
#      does not know your capital. It belongs to the consumer (Gate.min_adv_usd).
#
# A scan applies max(STRUCTURAL, POLICY) and stops. Capital is filtered downstream.
STRUCTURAL_FLOOR_USD = 10_000

MARKET_FLOOR_USD = {
    # India only, because India is the only market where a floor was actually chosen.
    # Rs 1 crore/day. Stated as a policy choice, NOT as a percentile — on the live
    # universe it happens to sit near the 35th, and that number is a consequence of the
    # choice, not a justification for it.
    "IN": 120_000,
}


def scan_floor(market: str) -> float:
    """Floor a SCAN should apply: structural, plus policy where one was chosen.

    Deliberately EXCLUDES the capital floor. A scan produces a universe; only the
    consumer knows how much money is being deployed. Baking a capital assumption into a
    scan is how one person's portfolio size became four markets' definition of
    "liquid".
    """
    return max(STRUCTURAL_FLOOR_USD, market_floor(market))
# No default floor. An unmeasured market gets the CAPITAL floor only — which is the
# honest answer, because we have not chosen a policy for it. Inventing a constant is
# what produced the fabricated numbers above.
DEFAULT_FLOOR_USD = 0.0


def market_floor(market: str) -> float:
    """Policy floor for one market in USD/day, or 0 where no policy was chosen.

    Returns 0 rather than guessing. A market with no floor is not unconstrained: the
    CAPITAL floor in Gate.min_adv_usd still applies, and it is the constraint that
    actually binds (above ~15-20% of ADV a position cannot be built at the quoted price).
    """
    return MARKET_FLOOR_USD.get((market or "").strip().upper()[:2], DEFAULT_FLOOR_USD)


# Kept for callers that predate market_floor(). It is India's gate — do not treat it as
# universal.
ABSOLUTE_FLOOR_USD = MARKET_FLOOR_USD["IN"]

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

        Two rules, both binding, and they answer different questions:
          * CAPITAL floor (universal rule, market-specific outcome): position / 15% ADV.
            "Can I build this position?" The RULE is the same everywhere; the set of
            names it admits differs by market because the distributions differ. That is
            the right kind of universality.
          * MARKET floor (country-specific): the depth below which a name is not a
            sensible candidate IN ITS OWN MARKET. India's Rs 1cr gate is one of these,
            not a global constant.

        max() of the two: a name must clear both your execution constraint AND its own
        market's floor.
        """
        return max(self.position_usd / (MAX_ADV_PCT / 100.0), market_floor(self.market))


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


def retier(df: pd.DataFrame, turnover_col: str = "Median_Turnover",
           tier_col: str = "Liquidity_Tier") -> pd.DataFrame:
    """Replace a scan's ABSOLUTE tiers with PERCENTILE tiers, in one post-pass.

    Wiring note — why this is a post-pass and not a change to scan_gate():
    scan_gate() is per-symbol and stateless, called inside each scan's parallel map. A
    percentile needs the whole universe, so it CANNOT be computed there. Rather than
    restructure five scans, the split is:
        scan_gate()  -> keeps the FLOOR (per-symbol, absolute, correct as-is)
        retier()     -> assigns TIERS once the frame exists

    Rows the floor already rejected are absent, and "UNKNOWN" rows (liquidity
    unmeasurable — scan_gate fails OPEN by design so a schema change cannot silently
    empty a scan) keep their label rather than being ranked. Ranking an unmeasurable
    row would invent a tier from a missing number.

    Leaves the frame untouched if there are too few rows to rank meaningfully.
    """
    if turnover_col not in df.columns or tier_col not in df.columns:
        return df
    out = df.copy()
    rankable = out[turnover_col].notna() & (out[turnover_col] > 0) & (out[tier_col] != "UNKNOWN")
    if int(rankable.sum()) < 20:
        return df                       # too few to form percentiles; keep absolute tiers
    pct = out.loc[rankable, turnover_col].rank(pct=True) * 100
    new = pd.Series(index=out.index, dtype=object)
    for lo, name in TIER_CUTS:
        new.loc[rankable & (pct >= lo) & new.isna()] = name
    out.loc[rankable, tier_col] = new.loc[rankable]
    return out


def describe(df: pd.DataFrame, market: str, adv_col: str = "adv_usd") -> str:
    """One line per market. Makes cross-market comparison possible without constants."""
    d = df[df[adv_col] > 0]
    if not len(d):
        return f"  {market}: no data"
    return (f"  {market:8s} n={len(d):>6,}  ADV median ${d[adv_col].median()/1e6:>8.2f}M"
            f"  p10 ${d[adv_col].quantile(.10)/1e6:>7.3f}M"
            f"  p90 ${d[adv_col].quantile(.90)/1e6:>8.2f}M"
            f"  above Rs1cr floor: {(d[adv_col] >= ABSOLUTE_FLOOR_USD).mean()*100:>4.0f}%")
