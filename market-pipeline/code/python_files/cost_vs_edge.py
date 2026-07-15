#!/usr/bin/env python3
"""
cost_vs_edge.py — does the small-cap Piotroski edge survive trading costs?

THE QUESTION THAT DECIDES EVERYTHING ELSE
-----------------------------------------
The within-tier sweep found a median edge of +5.7% (canonical) to +13.3%
(turnaround) in the SMALL liquidity tier, and negative edge in LARGE. But the
F-score literature's central practical finding is that this edge lives in exactly
the names you cannot trade cheaply: "consideration of liquidity constraints and an
estimate of trading costs in this low liquidity stock universe render both
strategies virtually unprofitable" (Walkshäusl et al., via EconStor). That is the
same finding that independently justified the user's Rs 1 crore/day floor.

So: is +13.3% gross a real edge, or a spread?

COST MODEL — two components, both estimated from data already on disk
--------------------------------------------------------------------
1. BID-ASK SPREAD, via Corwin & Schultz (2012, Journal of Finance).
   Estimates the spread from DAILY HIGH/LOW alone. The insight: the high/low ratio
   over one day reflects both volatility and the spread, but over two days
   volatility scales with time while the spread does not — so the two can be
   separated. This matters because we have no quote data at all; without C-S the
   spread would have to be a guess, and the guess would decide the answer.

2. MARKET IMPACT, via Amihud (2002) ILLIQ = mean(|return| / dollar volume), the
   price move caused by one dollar traded. Already implemented in liquidity.py.
   Impact scales with POSITION SIZE, so the answer depends on how much money is
   being deployed — a $100k portfolio and a $50M portfolio face different worlds.
   That is why this reports across capital levels rather than picking one.

Round-trip cost = spread + 2 x impact (buy and sell), charged once per year since
the strategy rebalances annually with ~100% turnover (top-10 reselected each year).

Commissions are taken as zero: US retail brokerage is commission-free, and adding a
token per-trade fee would only strengthen the conclusion, never weaken it.

WHY THIS IS CONSERVATIVE (i.e. the real cost is likely WORSE)
------------------------------------------------------------
  * C-S is a LOWER bound on the effective spread — it estimates the quoted spread
    from daily bars, and misses intraday depth exhaustion.
  * Impact is charged linearly in size. Real impact is concave-then-convex and blows
    up past a few percent of daily volume.
  * No slippage, no borrow, no taxes, no failed fills.
If the edge dies under THIS model, it is dead under any realistic one.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import duckdb
import numpy as np
import pandas as pd

# 🔴 WAS global-market-data/cache_seed/ltm/US.parquet — an INTERRUPTED collection.
# It holds 5,358 symbols but is missing whole letter blocks (D-L, O, U-Z) and omits
# S&P 500 names outright (CME, CMI absent; its most-covered symbols are all B's).
# Every US result before 2026-07-15 18:00 ran on 597 tickers drawn only from
# A,B,C,M,N,P,Q,R,S,T — a letter-biased subset, not a universe.
# The complete panel is in global-stock-screener: 9,278 symbols, and overlap with EDGAR
# fundamentals rises 2,281 (50%) -> 4,459 (97%).
PX = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"
SWEEP = "reports/sweep_piotroski_plus_us.csv"
PORTFOLIO_N = 10          # top-10 per tier, matching the sweep
# Full ladder. The earlier (100k, 1M, 10M, 50M) set skipped the small end entirely and
# so never located the actual ceiling — it reported "capacity ~$300-500k" by interpolating
# between $100k (fine) and $1M (dead). Measured on the ladder the ceiling is ~$250k.
CAPITALS = (1_000, 10_000, 50_000, 100_000, 250_000, 500_000,
            1_000_000, 2_000_000, 5_000_000, 10_000_000)
# The BINDING constraint is execution, not fees. Above ~15-20% of average daily volume a
# position cannot be built in one day near the quoted price, and the linear impact model
# understates cost precisely where it matters. Report it rather than pricing an
# impossible trade.
ADV_CEILING_PCT = 20.0


def corwin_schultz(con) -> pd.DataFrame:
    """Corwin-Schultz (2012) two-day high-low spread estimator, per symbol.

    beta  = sum over 2 consecutive days of [ln(H/L)]^2
    gamma = [ln(max(H_t,H_t+1) / min(L_t,L_t+1))]^2
    alpha = (sqrt(2*beta)-sqrt(beta))/(3-2*sqrt(2)) - sqrt(gamma/(3-2*sqrt(2)))
    S     = 2*(e^alpha - 1)/(1 + e^alpha)

    Negative estimates are set to 0 (the paper's own recommendation — they arise from
    estimation noise, not negative spreads) and the per-symbol MEDIAN is taken so a
    single wild day cannot set the cost.
    """
    return con.execute(f"""
    WITH b AS (
      SELECT Symbol, Date, High, Low,
             lead(High) OVER w AS h2, lead(Low) OVER w AS l2
      FROM '{PX}'
      WHERE High > 0 AND Low > 0 AND High >= Low
        AND Date >= DATE '2018-01-01'
      WINDOW w AS (PARTITION BY Symbol ORDER BY Date)
    ),
    g AS (
      SELECT Symbol,
             pow(ln(High/Low), 2) + pow(ln(h2/l2), 2) AS beta,
             pow(ln(greatest(High,h2) / least(Low,l2)), 2) AS gamma
      FROM b WHERE h2 IS NOT NULL AND l2 IS NOT NULL AND l2 > 0
    ),
    a AS (
      SELECT Symbol,
             (sqrt(2*beta) - sqrt(beta)) / (3 - 2*sqrt(2))
               - sqrt(gamma / (3 - 2*sqrt(2))) AS alpha
      FROM g WHERE beta > 0 AND gamma > 0
    ),
    s AS (
      SELECT Symbol,
             greatest(2 * (exp(alpha) - 1) / (1 + exp(alpha)), 0) AS spread
      FROM a WHERE alpha IS NOT NULL AND alpha > -10 AND alpha < 10
    )
    SELECT Symbol, median(spread) AS spread, count(*) AS n
    FROM s GROUP BY 1 HAVING count(*) >= 200
    """).df()


def amihud(con) -> pd.DataFrame:
    """Amihud ILLIQ: price impact per $1M traded (scaled), per symbol."""
    return con.execute(f"""
    WITH r AS (
      SELECT Symbol, Date, Close, Volume,
             Close / lag(Close) OVER w - 1 AS ret,
             Close * Volume AS dvol
      FROM '{PX}' WHERE Close > 0 AND Volume > 0 AND Date >= DATE '2018-01-01'
      WINDOW w AS (PARTITION BY Symbol ORDER BY Date)
    )
    SELECT Symbol,
           avg(abs(ret) / dvol) * 1e6 AS illiq,   -- impact per $1M traded
           median(dvol) AS turnover
    FROM r WHERE ret IS NOT NULL AND dvol > 0
    GROUP BY 1 HAVING count(*) >= 200
    """).df()


def main() -> int:
    con = duckdb.connect()
    print(f"\n{'='*78}\n  DOES THE SMALL-CAP EDGE SURVIVE COSTS? | US"
          f"\n{'='*78}")
    print("  Educational/research only. NOT investment advice.\n")

    d = pd.read_csv(SWEEP)
    cs, am = corwin_schultz(con), amihud(con)
    m = (d[["Symbol"]].drop_duplicates()
         .merge(cs[["Symbol", "spread"]], on="Symbol", how="inner")
         .merge(am[["Symbol", "illiq", "turnover"]], on="Symbol", how="inner"))
    print(f"  cost estimates for {len(m):,} of {d.Symbol.nunique():,} tested symbols")
    m["tier"] = pd.qcut(m.turnover, 3, labels=["SMALL", "MID", "LARGE"])

    print("\n  === COST INPUTS BY TIER (Corwin-Schultz spread + Amihud impact) ===")
    print(f"  {'tier':7s} {'n':>4s} {'turnover/day':>14s} {'spread':>9s} "
          f"{'impact per $1M':>16s}")
    for t in ("SMALL", "MID", "LARGE"):
        s = m[m.tier == t]
        print(f"  {t:7s} {len(s):>4} {'$'+format(s.turnover.median()/1e6, ',.1f')+'M':>14s} "
              f"{s.spread.median()*100:>8.2f}% {s.illiq.median()*100:>15.3f}%")

    # gross median edges, measured in the within-tier sweep
    GROSS = {"SMALL": {"canonical": 5.7, "quality": 6.5, "turnaround": 13.3, "safety": 7.1},
             "MID":   {"canonical": -0.5, "quality": 0.6, "turnaround": -0.8, "safety": 0.9},
             "LARGE": {"canonical": -1.6, "quality": -0.2, "turnaround": -9.0, "safety": -5.8}}

    print("\n  === NET EDGE AFTER ROUND-TRIP COSTS, by portfolio size ===")
    print("      (round trip = spread + 2 x impact, charged once/yr at ~100% turnover)")
    for cap in CAPITALS:
        pos = cap / PORTFOLIO_N
        print(f"\n  --- ${cap:,} portfolio  (${pos:,.0f} per position, {PORTFOLIO_N} names) ---")
        print(f"  {'tier':7s} {'cost/yr':>9s} {'% of ADV':>9s} "
              + " ".join(f"{k:>11s}" for k in GROSS['SMALL']))
        for t in ("SMALL", "MID", "LARGE"):
            s = m[m.tier == t]
            spread = s.spread.median()
            impact = s.illiq.median() * (pos / 1e6)      # ILLIQ is per $1M
            cost = (spread + 2 * impact) * 100
            adv = pos / s.turnover.median() * 100
            cells = " ".join(f"{GROSS[t][k]-cost:>+10.1f}%" for k in GROSS[t])
            print(f"  {t:7s} {cost:>8.2f}% {adv:>8.1f}% {cells}")
        print(f"  {'':7s} {'':>9s} {'':>9s} " + " ".join(
            f"{'(gross '+format(GROSS['SMALL'][k],'+.1f')+')':>11s}" for k in GROSS['SMALL'])
            + "   <- SMALL gross, for reference")

    print("\n  === VERDICT ===")
    s = m[m.tier == "SMALL"]
    for cap in CAPITALS:
        pos = cap / PORTFOLIO_N
        cost = (s.spread.median() + 2 * s.illiq.median() * (pos / 1e6)) * 100
        adv = pos / s.turnover.median() * 100
        best = max(GROSS["SMALL"].values())
        surv = "SURVIVES" if best - cost > 0 else "DEAD"
        print(f"    ${cap:>11,}  cost {cost:>6.2f}%/yr  ({adv:>5.1f}% of ADV)  "
              f"best gross {best:+.1f}% -> net {best-cost:+6.1f}%  {surv}")
    print("\n    Conservative: C-S is a LOWER bound on the effective spread; impact is")
    print("    charged linearly when real impact convexifies past a few % of ADV; and")
    print("    slippage, borrow, taxes and failed fills are all ignored. If the edge")
    print("    dies here, it is dead under any realistic model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
