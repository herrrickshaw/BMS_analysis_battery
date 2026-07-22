#!/usr/bin/env python3
"""
pead_sector_spillover_v2.py — re-run of pead_sector_spillover.py's PEAD +
sector-spillover event study, with the two limitations flagged in
DECISION_REGISTER.md's "known gaps" now fixed:
  1. REAL quarterly earnings dates (yfinance get_earnings_dates(), cached
     by earnings_dates_cache.py) instead of ANNUAL SEC/screener.in filing
     dates — ~4x the events per ticker, and the true announcement date
     rather than a filing date that can lag the actual press release/call
     by days to weeks.
  2. REAL analyst-consensus EPS surprise (Surprise(%), the actual
     Reported-vs-Estimate gap) instead of the YoY net_income-growth proxy
     v1 had to use in the absence of any consensus-estimate data source.

Every downstream statistical step — sector-adjusted CAR construction,
leave-one-out sector benchmark, Benjamini-Hochberg FDR correction on the
sector-leader candidates — is the EXACT SAME CODE as v1
(pead_sector_spillover.run_market(), called here with a different
events_loader). This is deliberate: if v2's results differ from v1's, the
difference is attributable to the better event data, not to two
independently-written pipelines that might silently diverge in some
methodological detail.

Usage (run AFTER earnings_dates_cache.py has populated
cache_seed/earnings_dates_cache/{market}.parquet):
    python3 pead_sector_spillover_v2.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
import json
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import pead_sector_spillover as pss
import earnings_dates_cache as edc


def load_real_events(market: str, symbols: set[str]) -> pd.DataFrame:
    df = edc._load_cached(market)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "event_date", "surprise", "surprise_sign", "date_is_proxy"])
    df = df[df["ticker"].isin(symbols)].copy()
    df["Reported EPS"] = pd.to_numeric(df["Reported EPS"], errors="coerce")
    df["Surprise(%)"] = pd.to_numeric(df["Surprise(%)"], errors="coerce")
    df = df.dropna(subset=["Reported EPS", "Surprise(%)"])   # only REPORTED (past) events have a real surprise
    df = df[np.isfinite(df["Surprise(%)"])]
    df["event_date"] = pd.to_datetime(df["Earnings Date"]).dt.tz_localize(None)
    df["surprise"] = df["Surprise(%)"] / 100.0
    df["surprise_sign"] = np.sign(df["surprise"])
    df["date_is_proxy"] = False   # always real for v2 — that's the whole point
    return df[["ticker", "event_date", "surprise", "surprise_sign", "date_is_proxy"]].drop_duplicates()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    a = ap.parse_args()

    results = []
    for m in a.market:
        cached = edc._load_cached(m)
        if cached.empty:
            print(f"[{m}] no earnings-dates cache yet — run earnings_dates_cache.py first, skipping")
            results.append({"market": m, "error": "no earnings-dates cache"})
            continue
        r = pss.run_market(m, events_loader=load_real_events)
        results.append(r)
        print(f"\n[{m}] DONE (v2, real quarterly dates): {json.dumps(r, indent=2, default=str)[:2500]}")

    with open("cache_seed/pead_sector_spillover_v2_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n\n" + "=" * 78)
    print("PEAD v2 (REAL QUARTERLY DATES) SUMMARY — compare against v1")
    print("=" * 78)
    for r in results:
        if "error" in r:
            print(f"{r['market']}: {r['error']}")
            continue
        print(f"\n{r['market']}  ({r['n_symbols']} symbols, {r['n_events']} events)")
        for k, v in r["pead_summary"].items():
            if isinstance(v, dict):
                print(f"  PEAD {k}: n={v['n_events']} car={v['mean_car_pct']:+.3f}% t={v['tstat']} hit={v['hit_rate']:.1%}")
            else:
                print(f"  {k}: {v:+.4f}%")
        print(f"  sector-leader candidates tested: {r['n_leader_candidates_tested']}, "
              f"FDR-significant (q=0.10): {r['n_leaders_fdr_significant_q10']}")
        for l in r["top_sector_leaders"][:5]:
            sig = "***" if l["fdr_significant"] else ""
            print(f"    {l['ticker']:12s} ({l['sector']}) n={l['n_events']} "
                  f"same_dir_hit={l['same_direction_hit_rate']:.1%} p={l['binomial_pvalue']} {sig}")


if __name__ == "__main__":
    main()
