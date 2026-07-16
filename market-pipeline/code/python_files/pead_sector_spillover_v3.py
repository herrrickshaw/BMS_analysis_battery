#!/usr/bin/env python3
"""
pead_sector_spillover_v3.py — PEAD + sector-spillover ("does a good
performer move its sector peers") evaluated across the FULL classified
universe of each market, using the UNION of every real earnings-date
source gathered this session, not any single one:

  yahooquery   batch-fetched via Yahoo's official quoteSummary endpoint —
               best combined coverage for JP (100%) and the biggest single
               improvement for KR (12% -> 40%), real reportedDate + real
               analyst-consensus surprisePct together in one call.
  yfinance     the original earnings_dates_cache.py per-ticker source —
               still independently useful where IT has a ticker
               yahooquery's batch call missed (they don't fail on exactly
               the same tickers).

MERGE RULE: union by (ticker, period_end/quarter), yahooquery's row wins
when both sources cover the same ticker+quarter (fresher batch call, and
carries reportedDate at day-level precision vs yfinance's date-only
field); yfinance fills in any ticker+quarter yahooquery's batch didn't
return. NSE (India) and SEC 8-K (US) — this session's two regulator-direct
sources — are NOT merged into the numeric events table, because neither
carries a consensus-surprise number (SEC's 8-K items and NSE's board-
meeting/result filings tell you an event happened, not whether it beat or
missed estimates) and the PEAD/spillover methodology below needs a
surprise SIGN to condition on. They remain independent date-only
cross-checks (see earnings_dates_nse.py / earnings_dates_sec_8k.py
docstrings) rather than inputs to this specific analysis.

Every downstream statistical step is UNCHANGED from pead_sector_spillover.py
(imported and reused, not reimplemented) — sector-adjusted CAR via
leave-one-out sector benchmark, Benjamini-Hochberg FDR correction on
"good performer moves its peers" candidates. Only the events_loader differs,
so v1/v2/v3 stay apples-to-apples comparable.

Usage:
    python3 pead_sector_spillover_v3.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
import json
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import pead_sector_spillover as pss

YQ_DIR = "cache_seed/earnings_dates_yahooquery"
YQ_FULL_DIR = "cache_seed/earnings_dates_yahooquery_full"   # different retry timing -> different gaps filled
YF_DIR = "cache_seed/earnings_dates_cache"
DART_PATH = "cache_seed/earnings_dates_dart/KR.parquet"       # Korea only, date-only (no surprise)
DART_MATCH_WINDOW_DAYS = 60   # DART periodic reports are annual/half-year/quarterly,
                              # not calendar-aligned like a US 10-Q -- match to the
                              # nearest DART filing within this window of the
                              # yahooquery/yfinance quarter's period end, not an
                              # exact date match


def _from_yahooquery(market: str) -> pd.DataFrame:
    frames = []
    for path in (f"{YQ_DIR}/{market}.parquet", f"{YQ_FULL_DIR}/{market}.parquet"):
        try:
            frames.append(pd.read_parquet(path))
        except FileNotFoundError:
            continue
    if not frames:
        return pd.DataFrame(columns=["ticker", "event_date", "surprise", "surprise_sign", "quarter_key"])
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["reported_date", "surprise_pct"]).copy()
    df["surprise"] = df["surprise_pct"] / 100.0
    df["surprise_sign"] = np.sign(df["surprise"])
    df["event_date"] = pd.to_datetime(df["reported_date"]).dt.tz_localize(None)
    # intra-source dedup key (classified-subset vs full-universe overlap, BOTH
    # yahooquery -- period_end_date is a fair match here since it's the same
    # provider's own field on both sides)
    df["_period_key"] = df["ticker"] + "_" + pd.to_datetime(df["period_end_date"]).dt.strftime("%Y-%m")
    df = df.drop_duplicates(subset=["ticker", "_period_key"])
    # cross-source dedup key (load_combined_events matches this against
    # _from_yfinance_cache's quarter_key below) -- MUST use the same date
    # field (event_date's calendar quarter) on both sides, or the two
    # sources' differently-formatted keys never collide and every shared
    # event gets double-counted instead of deduplicated (confirmed bug,
    # caught by code review: yahooquery was keying off period_end_date
    # formatted "%Y-%m" while yfinance keys off event_date's to_period("Q")
    # -- two representations of DIFFERENT underlying dates that can never
    # string-match even for the same real announcement).
    df["quarter_key"] = df["ticker"] + "_" + df["event_date"].dt.to_period("Q").astype(str)
    df["_src"] = "yahooquery"
    return df[["ticker", "event_date", "surprise", "surprise_sign", "quarter_key", "_src"]]


def _dart_date_override(market: str, combined: pd.DataFrame) -> pd.DataFrame:
    """Korea only: DART periodic-report filing_date is a real regulatory
    timestamp, more authoritative than yahooquery's/yfinance's own
    'reportedDate' (itself a Yahoo-side scrape/estimate) -- but DART carries
    NO consensus-surprise number, so it can only REFINE the date of an
    event that already has a surprise sign from another source, never add
    a new event on its own. For each Korea event, if a DART filing exists
    within DART_MATCH_WINDOW_DAYS of the event's own date, swap in DART's
    date as the more precise t=0 for the CAR/spillover event study."""
    if market != "KR" or combined.empty:
        return combined
    try:
        dart = pd.read_parquet(DART_PATH)
    except FileNotFoundError:
        return combined
    dart = dart.dropna(subset=["filing_date"]).copy()
    dart["filing_date"] = pd.to_datetime(dart["filing_date"]).dt.tz_localize(None)
    dart = dart.sort_values("filing_date")

    combined = combined.sort_values("event_date").reset_index(drop=True)
    out_dates = combined["event_date"].copy()
    n_overridden = 0
    for tk, g in combined.groupby("ticker"):
        d = dart[dart["ticker"] == tk]
        if d.empty:
            continue
        dart_dates = d["filing_date"].values
        for idx, ev_date in zip(g.index, g["event_date"]):
            diffs = np.abs((dart_dates - np.datetime64(ev_date)) / np.timedelta64(1, "D"))
            j = diffs.argmin()
            if diffs[j] <= DART_MATCH_WINDOW_DAYS:
                out_dates.loc[idx] = pd.Timestamp(dart_dates[j])
                n_overridden += 1
    combined = combined.copy()
    combined["event_date"] = out_dates
    print(f"[{market}] DART date-precision override: {n_overridden}/{len(combined)} events "
          f"got a more authoritative regulatory filing_date (within {DART_MATCH_WINDOW_DAYS}d)")
    return combined


def _from_yfinance_cache(market: str) -> pd.DataFrame:
    try:
        df = pd.read_parquet(f"{YF_DIR}/{market}.parquet")
    except FileNotFoundError:
        return pd.DataFrame(columns=["ticker", "event_date", "surprise", "surprise_sign", "quarter_key"])
    df = df.copy()
    df["Reported EPS"] = pd.to_numeric(df["Reported EPS"], errors="coerce")
    df["Surprise(%)"] = pd.to_numeric(df["Surprise(%)"], errors="coerce")
    df = df.dropna(subset=["Reported EPS", "Surprise(%)"])
    df = df[np.isfinite(df["Surprise(%)"])]
    df["event_date"] = pd.to_datetime(df["Earnings Date"]).dt.tz_localize(None)
    df["surprise"] = df["Surprise(%)"] / 100.0
    df["surprise_sign"] = np.sign(df["surprise"])
    df["quarter_key"] = df["ticker"] + "_" + df["event_date"].dt.to_period("Q").astype(str)
    df["_src"] = "yfinance"
    return df.rename(columns={"ticker": "ticker"})[["ticker", "event_date", "surprise", "surprise_sign", "quarter_key", "_src"]]


def load_combined_events(market: str, symbols: set[str]) -> pd.DataFrame:
    yq = _from_yahooquery(market)
    yf = _from_yfinance_cache(market)
    combined = pd.concat([yq, yf], ignore_index=True)
    combined = combined[combined["ticker"].isin(symbols)]
    # yahooquery wins on quarter_key collisions (listed first -> keep='first')
    combined = combined.sort_values("_src", key=lambda s: s.map({"yahooquery": 0, "yfinance": 1}))
    combined = combined.drop_duplicates(subset=["ticker", "quarter_key"], keep="first")
    combined = _dart_date_override(market, combined)
    combined["date_is_proxy"] = False
    return combined[["ticker", "event_date", "surprise", "surprise_sign", "date_is_proxy"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    a = ap.parse_args()

    results = []
    for m in a.market:
        r = pss.run_market(m, events_loader=load_combined_events)
        results.append(r)
        print(f"\n[{m}] DONE (v3, combined yahooquery+yfinance): "
              f"{json.dumps({k: v for k, v in r.items() if k != 'top_sector_leaders'}, indent=2, default=str)[:2000]}")

    with open("cache_seed/pead_sector_spillover_v3_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n\n" + "=" * 78)
    print("PEAD v3 (COMBINED SOURCES, FULL UNIVERSE) SUMMARY")
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
