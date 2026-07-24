#!/usr/bin/env python3
"""
execution_cost_model.py — impact-aware execution & capacity, from the AT/HFT
execution-algorithm literature (Gomber et al. 2011; Almgren-Chriss).

The backtests charged a FLAT round-trip bps regardless of size — fine for a
$5M book, wrong for a levered one. This replaces it with the standard
square-root market-impact model and a participation-rate (%ADV) cap, so we can
answer the question the AWS leverage/carry sweep actually needs:

    at what AUM does market impact eat the strategy's edge? (capacity)

Cost per round trip (bps of notional), per Almgren-Chriss / Kissell:
    cost = half_spread + η · σ_daily · sqrt( Q / ADV )
where Q = $ traded in the name, ADV = $ average daily volume, σ_daily = daily
return vol, η ≈ 1 (impact coefficient). A participation cap p (=15% ADV/day)
turns a Q > p·ADV order into a multi-day schedule (Almgren timing risk), which
we surface as the days-to-liquidate.

This is the AT "execution layer" the report says HFT is really about — applied
to our weekly rebalance, not to microsecond quoting.

Output: reports/execution_capacity.md + reports/execution_capacity.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
import strategy_regime_survival as S
import currency_matrix as CM

HERE = Path(__file__).resolve().parent
ETA = 1.0            # Almgren impact coefficient (bps per unit of σ·√participation)
HALF_SPREAD = {"IN": 8, "US": 3, "EU": 6, "JP": 5, "KR": 10}   # bps, per market
PART_CAP = 0.15      # max 15% of ADV per day (participation-rate algorithm)
N_POSITIONS = 40     # names the book holds per desk (equal-weight)
ADV_PCTL = 0.80      # a 40-name book concentrates in the MORE-liquid names, not the median


def desk_liquidity(mkt: str) -> dict:
    """Median ADV ($) and daily vol of the liquid (HIGH+MEDIUM) universe."""
    close, turn = S.load_panel(mkt)
    ret = close.pct_change(fill_method=None)
    sigma = ret.tail(52).std().median()                      # typical daily vol
    liq = turn.rank(axis=1, pct=True) >= 1/3.0
    adv_local = turn.where(liq).iloc[-1].quantile(ADV_PCTL)  # ADV of the names a book holds
    ccy = CM.DESK_CCY[mkt]
    adv_usd = adv_local * CM.usd_per(ccy)                    # historical currency matrix -> USD
    return {"adv_usd": float(adv_usd), "sigma": float(sigma)}


def impact_bps(q_usd, adv_usd, sigma, mkt):
    """Round-trip cost in bps for trading q_usd in a name of adv_usd, sigma."""
    part = q_usd / adv_usd if adv_usd else np.inf
    sqrt_impact = ETA * sigma * np.sqrt(part) * 1e4          # σ·√participation in bps
    return HALF_SPREAD[mkt] + sqrt_impact, part


def main() -> int:
    # per-desk edge (gross excess, bps/2wk) — from the survival backtest, bull book
    EDGE_BPS = {"IN": 44, "US": 21, "EU": 15, "JP": 15, "KR": 66}   # bull excess, bps/2wk
    AUM_GRID = [1e6, 5e6, 1e7, 2.5e7, 5e7, 1e8, 2.5e8, 5e8]
    rows = []
    liq = {}
    for mkt in S.MARKETS:
        liq[mkt] = desk_liquidity(mkt)
        print(f"  {mkt}: ADV(p{int(ADV_PCTL*100)} liquid) ${liq[mkt]['adv_usd']/1e6:.2f}M, "
              f"daily σ {liq[mkt]['sigma']*100:.1f}%")
    for mkt in S.MARKETS:
        adv, sigma = liq[mkt]["adv_usd"], liq[mkt]["sigma"]
        for aum in AUM_GRID:
            q = aum / N_POSITIONS                             # $ per position
            cost, part = impact_bps(q, adv, sigma, mkt)
            days = max(1.0, part / PART_CAP)                  # days to liquidate at 15% ADV
            net = EDGE_BPS[mkt] - cost                        # net edge after round-trip cost
            rows.append({"market": mkt, "aum_$M": aum/1e6, "pos_$M": q/1e6,
                         "%ADV": round(part*100, 1), "impact_bps": round(cost, 1),
                         "days_to_exit": round(days, 1), "gross_edge_bps": EDGE_BPS[mkt],
                         "net_edge_bps": round(net, 1)})
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "reports" / "execution_capacity.csv", index=False)

    # capacity = AUM where net edge crosses zero, per desk
    cap = {}
    for mkt in S.MARKETS:
        m = df[df.market == mkt].sort_values("aum_$M")
        pos = m[m.net_edge_bps > 0]
        cap[mkt] = float(pos["aum_$M"].max()) if not pos.empty else 0.0

    L = ["# Impact-aware execution & capacity (Almgren-Chriss square-root model)", "",
         "Replaces the flat-bps cost with `half_spread + η·σ·√(Q/ADV)` and a 15%-ADV "
         "participation cap. Book holds ~40 names/desk. `net_edge` = the bull-regime "
         "gross excess minus round-trip impact — where it crosses 0 is the desk's "
         "capacity (the AUM ceiling before impact eats the edge).", "",
         "| market | AUM $M | $/pos | %ADV | impact bps | days to exit | net edge bps |",
         "|---|--:|--:|--:|--:|--:|--:|"]
    for _, r in df.iterrows():
        flag = "" if r.net_edge_bps > 0 else " ❌"
        L.append(f"| {r.market} | {r['aum_$M']:.0f} | {r['pos_$M']:.2f} | {r['%ADV']} | "
                 f"{r.impact_bps} | {r.days_to_exit} | {r.net_edge_bps}{flag} |")
    L += ["", "## Capacity per desk (AUM where net edge → 0)", "",
          "| desk | gross edge bps/2wk | ~capacity ($M AUM) |", "|---|--:|--:|"]
    for mkt in S.MARKETS:
        L.append(f"| {mkt} | {EDGE_BPS[mkt]} | {cap[mkt]:.0f} |")
    L += ["", "> The edge is a small-money edge: India's +44bps/2wk survives to a few "
          "tens of $M, then impact erases it. This is the hard ceiling on how much the "
          "JPY-carry leverage can deploy — leverage multiplies ROE only until AUM hits "
          "capacity, then impact dominates. Half-spread/σ are desk medians; illustrative. "
          "Not investment advice."]
    (HERE / "reports" / "execution_capacity.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\nwrote reports/execution_capacity.{md,csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
