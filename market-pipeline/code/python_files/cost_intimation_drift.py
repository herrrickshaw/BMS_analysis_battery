#!/usr/bin/env python3
"""
cost_intimation_drift.py — does the intimation→ex-date drift survive costs?

Applies the cost_vs_edge.py model (Corwin-Schultz 2012 spread from High/Low +
Amihud 2002 impact) to the india-ca-intimation-drift claim, PER EVENT and
POINT-IN-TIME: each event's spread and ILLIQ are estimated from the 120
trading days ENDING THE DAY BEFORE its intimation — exactly the information a
trader had at entry.

Round trip per event = spread + 2 x (ILLIQ x position size). One round trip
per event (enter intimation+2, exit ex-1). Commissions ~0.2% round trip for
India retail (brokerage+STT+stamp) added flat — unlike the US study these are
not zero here.

Reported across POSITION sizes (per event, not book): Rs 1L / 10L / 50L / 2Cr.
With ~50-100 events/yr and 35-50td holding, a book runs ~10-20 concurrent
positions — multiply accordingly.

OUTPUT: reports/COST_INTIMATION_DRIFT.md + rows appended to stdout.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import duckdb
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
ADJ = os.path.expanduser(
    "~/repos/global-market-data/warehouse/ohlcv_adj/IN/*.parquet")
EVENTS = os.path.join(BASE, "reports", "pit_event_studies.parquet")
OUT_MD = os.path.join(BASE, "reports", "COST_INTIMATION_DRIFT.md")

POSITIONS_RS = {"Rs 1L": 1e5, "Rs 10L": 1e6, "Rs 50L": 5e6, "Rs 2Cr": 2e7}
COMMISSION_RT = 0.002   # ~0.2% round trip: brokerage + STT + stamp, India retail
LOOKBACK = 120          # trading days before intimation


def main() -> int:
    ev = pd.read_parquet(EVENTS)
    ev = ev[(ev["study"] == "post_ca_intimation")
            & ev["car_drift_ex"].notna()].copy()
    if ev.empty:
        print("no intimation events — run pit_event_studies.py first")
        return 1
    print(f"{len(ev)} intimation events")

    con = duckdb.connect()
    con.sql(f"""
    CREATE TEMP TABLE px AS
    SELECT Symbol AS symbol, Date AS date, High, Low, Close, Volume,
           row_number() OVER (PARTITION BY Symbol ORDER BY Date) AS rn
    FROM read_parquet('{ADJ}')
    WHERE Close > 0 AND High > 0 AND Low > 0 AND High >= Low
    """)
    con.register("ev", ev[["event_id", "symbol", "rn_ann"]])

    # per-event Corwin-Schultz over [rn_ann-LOOKBACK, rn_ann-1]
    liq = con.sql(f"""
    WITH w AS (
      SELECT e.event_id, p.symbol, p.rn, p.High, p.Low, p.Close, p.Volume,
             lead(p.High) OVER (PARTITION BY e.event_id ORDER BY p.rn) AS h2,
             lead(p.Low)  OVER (PARTITION BY e.event_id ORDER BY p.rn) AS l2,
             p.Close / lag(p.Close) OVER (PARTITION BY e.event_id ORDER BY p.rn) - 1 AS ret
      FROM ev e
      JOIN px p ON p.symbol = e.symbol
              AND p.rn BETWEEN e.rn_ann - {LOOKBACK} AND e.rn_ann - 1
    ),
    cs AS (
      SELECT event_id,
             pow(ln(High/Low),2) + pow(ln(h2/l2),2) AS beta,
             pow(ln(greatest(High,h2)/least(Low,l2)),2) AS gamma,
             abs(ret) / nullif(Close*Volume,0) AS impact_per_rs,
             Close*Volume AS turnover
      FROM w WHERE h2 IS NOT NULL AND l2 > 0
    ),
    a AS (
      SELECT event_id,
             CASE WHEN beta > 0 AND gamma > 0 THEN
               (sqrt(2*beta)-sqrt(beta))/(3-2*sqrt(2)) - sqrt(gamma/(3-2*sqrt(2)))
             END AS alpha,
             impact_per_rs, turnover
      FROM cs
    )
    SELECT event_id,
           median(greatest(2*(exp(alpha)-1)/(1+exp(alpha)), 0)) AS spread,
           avg(impact_per_rs) * 1e6 AS illiq_per_rs1m,
           median(turnover) AS med_turnover,
           count(*) AS n_days
    FROM a WHERE alpha IS NOT NULL AND alpha BETWEEN -10 AND 10
    GROUP BY 1 HAVING count(*) >= 60
    """).df()
    ev = ev.merge(liq, on="event_id", how="inner")
    print(f"{len(ev)} events with >=60d liquidity history")

    lines = [
        f"# Cost-adjusted intimation drift — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Per-event, PIT costs: Corwin-Schultz spread + Amihud impact from the",
        f"{LOOKBACK} trading days before each intimation; commissions "
        f"{COMMISSION_RT:.1%} round trip. Gross = CAR drift [+2, ex-1]",
        "(abnormal vs market median — the universe-level bias caveat from",
        "PIT_EVENT_STUDIES.md applies to gross AND net alike).",
        "",
        "A position is EXECUTABLE in an event only if it is <=10% of that",
        "name's median daily turnover (standard participation cap) — linear",
        "impact estimates past that are fiction, and so is the fill. Skipped",
        "events are reported, not averaged in.",
        "",
        "| kind | position | executable | gross (med) | cost (med) "
        "| net (med) | net hit% | skipped (>10% ADV) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for kind, grp in ev.groupby("kind"):
        for label, pos in POSITIONS_RS.items():
            g = grp.copy()
            g["adv_frac"] = pos / g["med_turnover"]
            ok = g[g["adv_frac"] <= 0.10].copy()
            skipped = len(g) - len(ok)
            if ok.empty:
                lines.append(f"| {kind} | {label} | 0 | — | — | — | — "
                             f"| {skipped}/{len(g)} |")
                continue
            ok["cost"] = (ok["spread"] + 2 * ok["illiq_per_rs1m"] * (pos / 1e6)
                          + COMMISSION_RT)
            ok["net"] = ok["car_drift_ex"] - ok["cost"]
            lines.append(
                f"| {kind} | {label} | {len(ok)} "
                f"| {ok['car_drift_ex'].median():+.2%} "
                f"| {ok['cost'].median():.2%} "
                f"| {ok['net'].median():+.2%} | {(ok['net'] > 0).mean():.0%} "
                f"| {skipped}/{len(g)} |")
    med_spread = ev["spread"].median()
    lines += [
        "",
        f"Median PIT Corwin-Schultz spread across events: {med_spread:.2%} · "
        f"median daily turnover: Rs {ev['med_turnover'].median()/1e7:.1f}Cr",
        "",
        "Reading: cost has three parts — spread (size-independent), impact",
        "(scales with position), commissions (flat). Where net stays near",
        "gross at small size but dies at Rs 2Cr, the edge is real but",
        "capacity-constrained (the illiquid-name pattern again). Where net",
        "is negative even at Rs 1L, the spread alone eats the drift.",
    ]
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
