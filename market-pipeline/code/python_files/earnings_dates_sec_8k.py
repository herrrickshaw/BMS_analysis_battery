#!/usr/bin/env python3
"""
earnings_dates_sec_8k.py — SECOND, INDEPENDENT source of REAL US
earnings-announcement dates, sourced directly from SEC EDGAR (the regulator
itself), to sit alongside the yfinance get_earnings_dates()-based pipeline
(earnings_dates_cache.py -> earnings_key_dates.py -> pead_sector_spillover_v2.py),
which works but is Yahoo-rate-limited (a full batch can silently return 0
results — see earnings_dates_cache.py's docstring).

WHY 8-Ks: US public companies almost universally furnish an 8-K with Item 2.02
("Results of Operations and Financial Condition") on or within a day of their
quarterly earnings press release. That 8-K is filed BEFORE the 10-Q/10-K, so
it sits much closer to the true announcement date than the annual 10-K
`filed` dates sec_history_collector.py already collects into
cache_seed/fundamentals_history/US.parquet (global-stock-screener repo).

DATA SOURCE, CONFIRMED LIVE (2026-07-16) AGAINST data.sec.gov:
    https://data.sec.gov/submissions/CIK##########.json
This is the same per-company filing-history endpoint the task suggested, and
it turned out BETTER than the pessimistic case the task flagged as likely:
the JSON's "filings.recent" block carries an "items" array, parallel to
"form"/"filingDate", that exposes the Item numbers disclosed on each 8-K's
cover page directly — e.g. "2.02,9.01" — with NO NEED to fetch/parse the
actual filing document. Verified on AAPL's live submissions JSON:
    2026-04-30  8-K  items=2.02,9.01   (earnings 8-K)
    2026-04-20  8-K  items=5.02        (exec appointment, NOT earnings)
    2026-01-29  8-K  items=2.02,9.01   (earnings 8-K)
So Item-level filtering to earnings-specific 8-Ks IS cheaply achievable from
structured JSON alone — this collector reports BOTH the item-filtered
earnings_only=True subset AND the full raw 8-K list (an item-unfiltered 8-K
list is still useful signal per the task brief; here it turned out
unnecessary to fall back to it, but the column is kept for tickers where a
filer's "items" field is empty/missing, which does happen for older filings).

CIK MAPPING: reuses the exact pattern already established in this repo's
SEC collector, global-stock-screener/sec_history_collector.py::_ticker_cik()
    https://www.sec.gov/files/company_tickers.json  ->  {TICKER: zero-padded CIK10}
Same source, same User-Agent contract, so a ticker resolves to the identical
CIK whichever collector looks it up.

COVERAGE CAVEAT: "filings.recent" holds only the most recent ~1000 filings
per company. For AAPL (checked live) that reaches back to 2015-05-29 —
comfortably covering the reconciliation window against
cache_seed/earnings_dates_cache/US.parquet, whose earliest AAPL row is 2016.
Older filings live in separate paginated archive files listed under
filings.files (e.g. CIK0000320193-submissions-001.json); this collector does
NOT follow that pagination. Fine for reconciling against the yfinance cache
(which doesn't go back further either) or for forward-looking tracking; NOT
a source of pre-2015 history without extending _fetch_submissions().

SEC FAIR ACCESS: 10 req/s max. This collector sleeps _RATE=0.15s between
data.sec.gov calls (~6.5 req/s, sequential — no threading) and sets a
descriptive User-Agent, matching sec_history_collector.py's posture
(_RATE=0.13, ~8 req/s there).

OUTPUT: cache_seed/earnings_dates_sec_8k/US.parquet — columns:
    ticker, filing_date, form_type, items, is_earnings_8k, accession, source
"source" is always "sec_8k" per the task spec. is_earnings_8k is True when
"2.02" appears in the filing's items string, False when items is present but
lacks 2.02, and pandas NA when SEC supplied no items field at all (mostly
pre-2004ish filings, before item-number-in-cover-page reporting existed).

RECONCILIATION with cache_seed/earnings_dates_cache/US.parquet (the existing
yfinance-based cache: ticker, Earnings Date, EPS Estimate, Reported EPS,
Surprise(%)):
  - INDEPENDENT CROSS-CHECK: join on ticker + date within +/-1 day (an 8-K
    can be filed the calendar day after an after-market press release, and
    yfinance's own Earnings Date sometimes lands on the adjacent day) to
    confirm a yfinance date is real, not a stale/rate-limited placeholder.
  - GAP-FILLING: when a ticker's yfinance fetch was rate-limited (batches
    can return 0 results, not a partial — see earnings_dates_cache.py), the
    Item-2.02-filtered dates here are a usable substitute for "which
    quarters had a real earnings event," at the cost of no EPS
    estimate/surprise (SEC's structured data doesn't carry consensus
    numbers — that's Yahoo's value-add, not the regulator's).
  - Deliberately does NOT import or modify earnings_dates_cache.py: this is
    a standalone second opinion, not a patch to the first source. Combine
    downstream (e.g. in pead_sector_spillover_v2.py) by reading both
    parquet files and joining on ticker+date, not by merging the modules.

Usage:
    python3 earnings_dates_sec_8k.py --tickers AAPL MSFT MCHP ANET WDAY NFLX
    python3 earnings_dates_sec_8k.py --sample 25       # random US tickers from sector_map_cache.json
    python3 earnings_dates_sec_8k.py --tickers AAPL --earnings-only   # print Item 2.02 rows only
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = Path(_HERE) / "cache_seed" / "earnings_dates_sec_8k"
OUT = OUT_DIR / "US.parquet"
SECTOR_CACHE = Path(_HERE) / "cache_seed" / "sector_map_cache.json"

# SEC requires a descriptive, contactable User-Agent on every data.sec.gov /
# www.sec.gov call or it will 403 the request. Same contact used by
# sec_history_collector.py in the global-stock-screener repo.
_UA = {"User-Agent": "market-research umashankartd1991@gmail.com"}
_RATE = 0.15  # ~6.5 req/s, under SEC's 10 req/s fair-access ceiling


def _ticker_cik(sess: requests.Session) -> dict[str, str]:
    """TICKER -> zero-padded 10-digit CIK, from SEC's own ticker map.
    Identical source/shape to sec_history_collector.py's _ticker_cik(), so a
    ticker resolves to the same CIK across both collectors."""
    r = sess.get("https://www.sec.gov/files/company_tickers.json", headers=_UA, timeout=30)
    r.raise_for_status()
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in r.json().values()}


def _fetch_submissions(sess: requests.Session, cik: str) -> dict | None:
    r = sess.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=_UA, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()


def collect_ticker_8ks(sess: requests.Session, ticker: str, cik: str) -> list[dict]:
    """All 8-K filings from the 'recent' window of the submissions JSON,
    with the Item 2.02 (earnings) flag read straight off SEC's own
    structured 'items' field — no filing-document fetch needed."""
    data = _fetch_submissions(sess, cik)
    if not data:
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    items = recent.get("items", [])
    accns = recent.get("accessionNumber", [])
    rows = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        item_str = items[i] if i < len(items) else ""
        if item_str:
            is_earnings = "2.02" in [x.strip() for x in item_str.split(",")]
        else:
            is_earnings = pd.NA  # SEC gave no item-level data for this filing
        rows.append({
            "ticker": ticker,
            "filing_date": dates[i] if i < len(dates) else None,
            "form_type": form,
            "items": item_str or None,
            "is_earnings_8k": is_earnings,
            "accession": accns[i] if i < len(accns) else None,
            "source": "sec_8k",
        })
    return rows


def _sample_us_tickers(n: int) -> list[str]:
    with open(SECTOR_CACHE) as f:
        d = json.load(f)
    us = [k[3:] for k in d.keys() if k.startswith("US:")]
    return us[:n]


def run(tickers: list[str]) -> pd.DataFrame:
    sess = requests.Session()
    print(f"resolving {len(tickers)} tickers against SEC's ticker->CIK map...")
    cik_map = _ticker_cik(sess)
    missing = [t for t in tickers if t.upper() not in cik_map]
    if missing:
        print(f"  no CIK found (skipped): {missing}")
    tickers = [t for t in tickers if t.upper() in cik_map]

    all_rows = []
    for i, tk in enumerate(tickers, 1):
        time.sleep(_RATE)
        cik = cik_map[tk.upper()]
        try:
            rows = collect_ticker_8ks(sess, tk.upper(), cik)
            all_rows.extend(rows)
            n_earn = sum(1 for r in rows if r["is_earnings_8k"] is True)
            print(f"  [{i}/{len(tickers)}] {tk}: {len(rows)} 8-Ks total, {n_earn} tagged Item 2.02")
        except Exception as e:
            print(f"  [{i}/{len(tickers)}] {tk}: FAILED ({e})")

    df = pd.DataFrame(all_rows, columns=[
        "ticker", "filing_date", "form_type", "items", "is_earnings_8k", "accession", "source",
    ])
    if not df.empty:
        df["filing_date"] = pd.to_datetime(df["filing_date"])
        df = df.sort_values(["ticker", "filing_date"]).reset_index(drop=True)
    return df


def save(df: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        df = (pd.concat([prev, df], ignore_index=True)
                .drop_duplicates(subset=["ticker", "accession"], keep="last"))
    df.to_parquet(OUT, index=False)
    print(f"-> {OUT} ({len(df)} rows, {df['ticker'].nunique()} tickers)")


def main():
    ap = argparse.ArgumentParser(description="Independent SEC EDGAR 8-K earnings-date collector")
    ap.add_argument("--tickers", nargs="*", default=["AAPL", "MSFT", "MCHP", "ANET", "WDAY", "NFLX"])
    ap.add_argument("--sample", type=int, default=0,
                     help="pull N tickers from cache_seed/sector_map_cache.json's US: list instead")
    ap.add_argument("--earnings-only", action="store_true",
                     help="print only Item-2.02-tagged rows in the console summary")
    args = ap.parse_args()

    tickers = _sample_us_tickers(args.sample) if args.sample else args.tickers
    df = run(tickers)
    if df.empty:
        print("no rows collected")
        return
    save(df)

    view = df
    if args.earnings_only:
        view = df[df["is_earnings_8k"] == True]  # noqa: E712 (nullable bool -> explicit compare)
    for tk in df["ticker"].unique():
        sub = view[view["ticker"] == tk]
        print(f"\n{tk} — {len(sub)} filing(s) shown:")
        for _, row in sub.iterrows():
            tag = "EARNINGS(2.02)" if row["is_earnings_8k"] is True else (
                  "no-2.02" if row["is_earnings_8k"] is False else "items-unknown")
            print(f"    {row['filing_date'].date()}  items={row['items']}  [{tag}]")


if __name__ == "__main__":
    main()
