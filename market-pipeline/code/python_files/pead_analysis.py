#!/usr/bin/env python3
"""
pead_analysis.py — post-earnings announcement drift, India and US.

THE HYPOTHESIS
--------------
Prices under-react to earnings news, so a positive surprise keeps drifting up
for weeks after the announcement. If true, the top surprise quintile should
out-return the bottom over 5-21 days, and the gap should WIDEN with horizon —
that widening is what separates drift from a one-day repricing.

WHY THIS IS MORE ANSWERABLE THAN THE FACTOR WORK
------------------------------------------------
The Piotroski/ROCE tests had ~9-17 annual rebalances, so the real sample size
was the year count and nothing could reach significance. PEAD is measured in
EVENT time: 9,922 usable Indian announcements across 2,490 tickers and 20 years.
Events within a quarter still co-move, so results are clustered by year — but
there are far more independent observations than an annual rebalance provides.

🔴 SOURCE PURITY — the reason this file filters before it computes
------------------------------------------------------------------
`surprise_pct` in earnings_price_dataset is assembled from three sources, and
they are NOT the same quantity. Measured 2026-07-21 on the India panel:

    source            n      median    p10       p90
    nse_eps_yoy    1,470     +2.77    -95.41   +132.37
    yahooquery     3,052     -0.75    -49.91    +37.76
    yfinance       6,870     +0.17    -44.23    +46.38

A real surprise is centred near zero, because expectations are roughly unbiased
— the two yahoo-derived sources are. `nse_eps_yoy` is centred positive with much
fatter tails, which is the signature of YEAR-OVER-YEAR EPS GROWTH, not surprise
versus expectation. Companies grow; that is not news. Pooling them would sort
quintiles on a mixture of two different measurements and call the result drift.
So nse_eps_yoy is EXCLUDED by default (--include-yoy overrides, for comparison
only).

    pead_analysis.py                    # India
    pead_analysis.py --market US
    pead_analysis.py --include-yoy      # show the contamination explicitly
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PANEL = HERE / "cache_seed" / "earnings_price_dataset"

# Surprise measures that mean "actual vs expected". nse_eps_yoy is growth.
CLEAN_SOURCES = {"yahooquery_full", "yfinance_cache", "yahooquery", "yfinance"}
HORIZONS = ["price_change_1d", "price_change_5d", "price_change_21d"]
N_BUCKETS = 5
MIN_PER_BUCKET = 30


def year_clustered(df: pd.DataFrame, col: str) -> dict:
    """Median within year, then across years — the year is the observation.

    Announcements inside one year share macro conditions, so pooling every event
    as independent inflates t by roughly sqrt(events per year).
    """
    if df.empty or col not in df:
        return {}
    per_year = df.groupby("year")[col].median().dropna()
    n = len(per_year)
    if n < 2:
        return {"n_years": n}
    m, sd = float(per_year.mean()), float(per_year.std(ddof=1))
    se = sd / np.sqrt(n) if sd > 0 else np.nan
    return {"mean": m, "n_years": n, "t": (m / se) if se and se == se else np.nan,
            "years_positive": int((per_year > 0).sum())}


def run(market: str, include_yoy: bool) -> int:
    p = PANEL / f"{market}.parquet"
    if not p.exists():
        print(f"no panel for {market}", file=sys.stderr)
        return 1
    d = pd.read_parquet(p)
    total = len(d)
    d = d[d["surprise_pct"].notna()].copy()

    if not include_yoy:
        before = len(d)
        d = d[d["source"].isin(CLEAN_SOURCES)]
        print(f"  source filter: kept {len(d):,}/{before:,} "
              f"(dropped {before - len(d):,} nse_eps_yoy — YoY growth, not surprise)")

    d["earnings_date"] = pd.to_datetime(d["earnings_date"], errors="coerce")
    d = d[d["earnings_date"].notna()]
    d["year"] = d["earnings_date"].dt.year

    print("=" * 84)
    print(f"  PEAD — {market}   ({len(d):,} usable of {total:,} events, "
          f"{d['ticker'].nunique():,} tickers, {d['year'].nunique()} years)")
    print("=" * 84)

    for hz in HORIZONS:
        sub = d[d[hz].notna()].copy()
        if len(sub) < N_BUCKETS * MIN_PER_BUCKET:
            print(f"\n  {hz}: only {len(sub):,} events — too few to bucket")
            continue
        # Quintile WITHIN year, so a year with unusually large surprises does not
        # dominate the top bucket and turn a market move into a factor result.
        sub["q"] = sub.groupby("year")["surprise_pct"].transform(
            lambda s: pd.qcut(s, N_BUCKETS, labels=False, duplicates="drop"))
        sub = sub[sub["q"].notna()]
        print(f"\n  ── {hz} ──")
        print(f"     {'bucket':<10} {'n':>7} {'med surprise':>13} {'med return':>12} "
              f"{'t':>7} {'yrs+':>7}")
        stats = {}
        for q in sorted(sub["q"].unique()):
            g = sub[sub["q"] == q]
            st = year_clustered(g, hz)
            stats[q] = st
            label = {0: "Q1 (worst)", N_BUCKETS - 1: f"Q{N_BUCKETS} (best)"}.get(q, f"Q{int(q)+1}")
            print(f"     {label:<10} {len(g):>7,} {g['surprise_pct'].median():>13.2f} "
                  f"{st.get('mean', float('nan')):>11.2f}% {st.get('t', float('nan')):>7.2f} "
                  f"{st.get('years_positive', 0):>3}/{st.get('n_years', 0)}")
        lo, hi = stats.get(0, {}), stats.get(N_BUCKETS - 1, {})
        if lo.get("mean") is not None and hi.get("mean") is not None:
            print(f"     {'SPREAD Q5-Q1':<10} {'':>7} {'':>13} "
                  f"{hi['mean'] - lo['mean']:>11.2f}%")

    print("\n  READING THIS")
    print("  ------------")
    print("  PEAD predicts a POSITIVE Q5-Q1 spread that GROWS from 1d to 21d. A spread")
    print("  that is large at 1d and flat after is immediate repricing, not drift —")
    print("  and not tradeable, because you cannot act before the print.")
    print("  'yrs+' counts years the bucket's median was positive; on ~20 years it is")
    print("  more informative than t, which a single strong year can inflate.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-earnings announcement drift")
    ap.add_argument("--market", default="IN")
    ap.add_argument("--include-yoy", action="store_true",
                    help="also include nse_eps_yoy (a GROWTH measure) — for comparison only")
    a = ap.parse_args()
    return run(a.market, a.include_yoy)


if __name__ == "__main__":
    sys.exit(main())
