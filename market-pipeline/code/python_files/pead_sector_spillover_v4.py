#!/usr/bin/env python3
"""
pead_sector_spillover_v4.py — PEAD + sector-spillover run on top of
earnings_price_dataset.py's consolidated event table, instead of
pead_sector_spillover_v3.py's own separately-maintained yahooquery+yfinance
union.

WHY A v4 RATHER THAN PATCHING v3: v3 and earnings_price_dataset.py grew
independently in the same session and ended up with two DIFFERENT,
DUPLICATED event-cleaning pipelines over the same underlying yahooquery/
yfinance parquet files:

  - v3's _from_yahooquery()/_from_yfinance_cache() apply NO bound on
    surprise_pct. earnings_price_dataset.py's load_all_events() applies
    SURPRISE_PCT_SANITY_BOUND=500.0 specifically because Korea showed
    -6902%/-5097%/-3618% near-zero-denominator artifacts. Those same
    artifacts have been flowing UNFILTERED into every pead_sector_
    spillover_v3.py run this session — the sign() bucketing they feed
    isn't necessarily wrong (a corrupted MAGNITUDE doesn't always flip the
    SIGN), but a near-zero denominator is exactly the case where a sign
    flip becomes likely too, so this was a real, previously-uncaught gap.
  - earnings_price_dataset.py additionally unions in NSE (India) and
    SEC-8K (US) date-only filings as a date cross-check, which v3 never
    saw. v3 only got Korea's DART date refinement, added ad hoc last run.

RATHER than layer a THIRD ad hoc date-override (as was just done for
Korea/DART in v3), this version delegates event construction entirely to
earnings_price_dataset.load_all_events() — the single canonical,
already-deduplicated, already-sanity-bounded, already-multi-source-unioned
table — so there is exactly ONE place events get cleaned, not two that can
silently drift apart. Everything downstream (sector-adjusted CAR,
leave-one-out sector benchmark, Benjamini-Hochberg FDR at q=0.10) is the
UNCHANGED core from pead_sector_spillover.py, exactly like v1/v2/v3.

WHAT THIS DOES NOT CHANGE: earnings_price_dataset.py's own-stock 1d/5d/21d
price-change columns are NOT used here — this script only borrows its
EVENT table (ticker, date, surprise). The sector-adjusted CAR windows
(1mo/2mo/3mo = 21/42/63 trading days) are computed by pead_sector_
spillover.py's own machinery, same as every prior version, because that
sector-adjustment is what makes this a PEAD test rather than a raw
price-change table.

WHAT THIS DOES NOT FIX: earnings_price_dataset.py's date-only sources
(NSE/SEC-8K/DART) still can't feed the surprise-conditioned PEAD/spillover
test directly — no surprise number, no sign to bucket on — so the
classified-universe event COUNT here is bounded by the same yahooquery+
yfinance surprise-bearing coverage v3 already had. The value added is
CLEANLINESS (sanity bound) and, for India/US specifically, date precision
via NSE/SEC-8K's weekly-bucket de-dup preference in load_all_events()
(mirrors what DART gave Korea in v3, but sourced from the same pipeline
rather than a bolted-on override).

Usage:
    python3 pead_sector_spillover_v4.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
import json
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import earnings_price_dataset as epd
import pead_sector_spillover as pss


def load_consolidated_events(market: str, symbols: set[str]) -> pd.DataFrame:
    df = epd.load_all_events(market)
    df = df.dropna(subset=["surprise_pct"]).copy()   # date-only sources can't feed a signed test
    df = df[df["ticker"].isin(symbols)]
    df["event_date"] = pd.to_datetime(df["earnings_date"]).dt.tz_localize(None)
    df["surprise"] = df["surprise_pct"] / 100.0
    df["surprise_sign"] = np.sign(df["surprise"])
    df["date_is_proxy"] = False
    return df[["ticker", "event_date", "surprise", "surprise_sign", "date_is_proxy"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    a = ap.parse_args()

    results = []
    for m in a.market:
        r = pss.run_market(m, events_loader=load_consolidated_events)
        results.append(r)
        print(f"\n[{m}] DONE (v4, earnings_price_dataset-consolidated events): "
              f"{json.dumps({k: v for k, v in r.items() if k != 'top_sector_leaders'}, indent=2, default=str)[:2000]}")

    with open("cache_seed/pead_sector_spillover_v4_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n\n" + "=" * 78)
    print("PEAD v4 (CONSOLIDATED VIA earnings_price_dataset.py) SUMMARY")
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
        print(f"  'good performer moves peers' candidates tested: {r['n_leader_candidates_tested']}, "
              f"FDR-significant (q=0.10): {r['n_leaders_fdr_significant_q10']}")
        for l in r["top_sector_leaders"][:8]:
            sig = "***" if l["fdr_significant"] else ""
            print(f"    {l['ticker']:12s} ({l['sector']}) n={l['n_events']} "
                  f"same_dir_hit={l['same_direction_hit_rate']:.1%} p={l['binomial_pvalue']} {sig}")


if __name__ == "__main__":
    main()
