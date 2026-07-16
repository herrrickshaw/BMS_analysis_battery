#!/usr/bin/env python3
"""
earnings_dates_nse.py — real earnings-related dates sourced directly from
NSE India (National Stock Exchange), as a SECOND, INDEPENDENT source
alongside earnings_dates_cache.py / earnings_key_dates.py /
pead_sector_spillover_v2.py, which all source dates from yfinance's
get_earnings_dates().

WHY A SECOND SOURCE: yfinance's get_earnings_dates() is (a) Yahoo-rate-
limited (the recurring failure mode that made earnings_dates_cache.py
resumable-by-design in the first place) and (b) largely an
ESTIMATED/derived date — Yahoo infers a quarter's release date from prior-
year timing plus third-party analyst calendars, not from the regulatory
filing itself. For India, NSE is the PRIMARY source: under SEBI LODR
Reg. 29/33, every NSE-listed company must (1) notify NSE in advance of the
board meeting date at which quarterly/annual results will be considered,
and (2) file the actual audited/unaudited results with NSE once the board
has met. Every third-party India earnings calendar (Screener.in,
Trendlyne, Moneycontrol, and by extension yfinance's India coverage) is
ultimately built FROM this NSE feed — this script goes to that primary
source directly instead of a re-aggregation of it.

TWO EVENT TYPES, from two endpoints confirmed live on 2026-07-16:

  event_type="board_meeting"
      https://www.nseindia.com/api/corporate-board-meetings
      Forward-looking (and recent-past) company notifications of the
      board meeting date on which results will be CONSIDERED. This is
      usually announced ~2-7 business days ahead of the meeting itself
      per NSE listing rules, so it is the best "expected event" date for
      an event-study estimation-window cutoff.

  event_type="actual_result"
      https://www.nseindia.com/api/corporates-financial-results
      The ACTUAL date results were filed with NSE (filingDate) after the
      board meeting concluded — the true ex-post "results were now
      public" timestamp, which is the correct t=0 for a PEAD / abnormal-
      return event study (more precise than a Yahoo-estimated date).

SESSION / ANTI-BOT NOTE (the "common trap" flagged going in): nseindia.com
fronts its site with a bot-detection layer. Confirmed live 2026-07-16:
a bare `requests.Session().get("https://www.nseindia.com/")` returns
HTTP 403 EVEN WITH full browser-like headers (Chrome UA, Accept-Language,
Referer) — no combination of headers made the homepage itself return 200
in testing. BUT the underlying JSON API endpoints (/api/corporate-board-
meetings, /api/corporates-financial-results) return 200 with real data
regardless, as long as the request looks like an XHR call from a browser
(Accept: application/json, X-Requested-With: XMLHttpRequest, and a
Referer pointing at an nseindia.com page). This script still does the
homepage priming GET first (it seeds cookies some endpoints do check) but
does NOT treat that GET's status code as fatal — only the API call's
status matters. If NSE tightens this in the future, the first symptom
will be the API calls themselves (not just the homepage) returning
403/401; _get_json() already re-primes the session and retries once when
that happens.

RATE LIMITING: NSE publishes an informal ~3 req/sec throttle. This
proof-of-concept is deliberately SEQUENTIAL (not the thread-pool
parallel_map() pattern used by earnings_dates_cache.py) with a fixed
SLEEP_SECONDS pause between calls — 2 requests/symbol (board meetings +
financial results) is already enough that even modest concurrency risks
tripping the block. Scale this out (more workers, larger symbol lists)
only after separately validating NSE tolerates it.

CACHING / RESUMABILITY: results are cached to
cache_seed/earnings_dates_nse/IN.parquet, deduplicated on
(symbol, event_type, event_date). Re-running only fetches symbols not
already present in the cache (--force to refetch everything) — same
resumability contract as earnings_dates_cache.py.

RECONCILING AGAINST cache_seed/earnings_dates_cache/IN.parquet
(the existing yfinance-sourced cache):
  The two feeds answer overlapping but different questions, so this is a
  CROSS-CHECK + PRIORITY-ORDER exercise, not a straight merge:
    - yfinance's "Earnings Date" carries EPS Estimate / Reported EPS /
      Surprise(%) — real consensus data NSE's feed does not publish at
      all — but the date itself is Yahoo's estimate and can be off by a
      day or more, especially for smaller caps.
    - NSE's board_meeting.event_date is the PRIMARY, company-filed date
      for when results will be considered.
    - NSE's actual_result.event_date (filingDate) is the PRIMARY, exact
      date results became public with NSE.
  Suggested reconciliation when both sources have a symbol+quarter:
    1. Match rows on (symbol, quarter), using NSE's financial_year +
       period fields against yfinance's quarter-end implied by its
       Earnings Date.
    2. Prefer NSE's actual_result.event_date as the ground-truth event
       date whenever present — it is a regulatory filing timestamp, not
       an estimate.
    3. Fall back to yfinance's Earnings Date only when NSE has no record
       for that symbol+quarter, and keep using yfinance's EPS
       Estimate/Reported EPS/Surprise(%) regardless (NSE's feed has no
       equivalent).
    4. Flag any case where |NSE.event_date - yfinance."Earnings Date"| >
       1 trading day as a cross-check discrepancy worth a manual look —
       the same two-independent-sources discipline already required by
       feedback_validate_scan_before_mailer.md before anything ships.

Usage:
    python3 earnings_dates_nse.py --symbols RELIANCE TCS INFY HDFCBANK
    python3 earnings_dates_nse.py --from-sector-cache --limit 15
    python3 earnings_dates_nse.py --force --symbols RELIANCE
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path("cache_seed/earnings_dates_nse")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = CACHE_DIR / "IN.parquet"

BASE_URL = "https://www.nseindia.com"
API_BASE = f"{BASE_URL}/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE_URL}/companies-listing/corporate-filings-announcements",
    "Connection": "keep-alive",
    "X-Requested-With": "XMLHttpRequest",
}

SLEEP_SECONDS = 0.6  # ~1.7 req/sec, under NSE's informal ~3 req/sec throttle
DEFAULT_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "WIPRO", "TECHM", "HAVELLS"]


def _new_session() -> requests.Session:
    """Prime a requests.Session with browser-like headers + NSE cookies.

    See module docstring's ANTI-BOT NOTE: the homepage priming GET below
    frequently returns 403 (confirmed live 2026-07-16) even with full
    browser headers, but that is NOT fatal — the /api/* endpoints accept
    the follow-up calls anyway. We still do the priming GET because it
    seeds cookies some endpoints check.
    """
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        r = s.get(BASE_URL + "/", timeout=15)
        if r.status_code != 200:
            print(f"  [nse] homepage priming GET returned {r.status_code} "
                  f"(non-fatal — API calls often still succeed)")
    except requests.RequestException as e:
        print(f"  [nse] homepage priming GET failed ({e}) — continuing anyway")
    return s


def _get_json(session: requests.Session, path: str, params: dict, retries: int = 2):
    """GET an NSE /api/<path> endpoint, re-priming the session once on 401/403."""
    url = f"{API_BASE}/{path}"
    for attempt in range(retries + 1):
        try:
            r = session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            if attempt == retries:
                return None, f"request_error:{e}"
            time.sleep(1.5)
            continue
        if r.status_code == 200:
            try:
                return r.json(), None
            except ValueError:
                return None, "invalid_json"
        if r.status_code in (401, 403) and attempt < retries:
            session.cookies.clear()
            try:
                session.get(BASE_URL + "/", timeout=15)
            except requests.RequestException:
                pass
            time.sleep(1.0)
            continue
        return None, f"http_{r.status_code}"
    return None, "exhausted_retries"


def fetch_board_meetings(session: requests.Session, symbol: str) -> list[dict]:
    data, err = _get_json(session, "corporate-board-meetings",
                           {"index": "equities", "symbol": symbol})
    if err:
        print(f"  [{symbol}] board-meetings error: {err}")
        return []
    rows = []
    for r in data or []:
        rows.append({
            "symbol": symbol,
            "event_date": r.get("bm_date"),
            "event_type": "board_meeting",
            "source": "nse",
            "purpose": r.get("bm_purpose"),
            "description": r.get("bm_desc"),
            "announced_at": r.get("bm_timestamp"),
            "isin": r.get("sm_isin"),
        })
    return rows


def fetch_financial_results(session: requests.Session, symbol: str,
                             period: str = "Quarterly") -> list[dict]:
    data, err = _get_json(session, "corporates-financial-results",
                           {"index": "equities", "symbol": symbol, "period": period})
    if err:
        print(f"  [{symbol}] financial-results error: {err}")
        return []
    rows = []
    for r in data or []:
        rows.append({
            "symbol": symbol,
            "event_date": r.get("filingDate"),
            "event_type": "actual_result",
            "source": "nse",
            "period": r.get("period"),
            "relating_to": r.get("relatingTo"),
            "financial_year": r.get("financialYear"),
            "consolidated": r.get("consolidated"),
            "audited": r.get("audited"),
            "broadcast_date": r.get("broadCastDate"),
            "isin": r.get("isin"),
        })
    return rows


def _load_cached() -> pd.DataFrame:
    if CACHE_PATH.exists():
        return pd.read_parquet(CACHE_PATH)
    return pd.DataFrame(columns=["symbol", "event_date", "event_type", "source"])


def fetch_and_cache(symbols: list[str], force: bool = False) -> pd.DataFrame:
    have = _load_cached()
    already = set(have["symbol"].unique()) if not have.empty and not force else set()
    missing = [s for s in symbols if s not in already]

    print(f"[nse] {len(symbols)} symbols requested, {len(already)} already cached, "
          f"{len(missing)} to fetch...")

    if not missing:
        return have

    session = _new_session()
    new_rows = []
    for i, sym in enumerate(missing, 1):
        bm_rows = fetch_board_meetings(session, sym)
        time.sleep(SLEEP_SECONDS)
        fr_rows = fetch_financial_results(session, sym)
        time.sleep(SLEEP_SECONDS)
        print(f"  [{i}/{len(missing)}] {sym}: {len(bm_rows)} board meetings, "
              f"{len(fr_rows)} financial-result filings")
        new_rows.extend(bm_rows)
        new_rows.extend(fr_rows)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined = pd.concat([have, new_df], ignore_index=True) if not have.empty else new_df
        combined = combined.drop_duplicates(subset=["symbol", "event_type", "event_date"])
        combined.to_parquet(CACHE_PATH, index=False)
        have = combined
    else:
        print("[nse] no new rows fetched (all requests errored — see per-symbol messages above)")

    return have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=None,
                     help="NSE symbols (bare, no .NS suffix), e.g. RELIANCE TCS INFY")
    ap.add_argument("--from-sector-cache", action="store_true",
                     help="Pull symbols from cache_seed/sector_map_cache.json IN: entries")
    ap.add_argument("--limit", type=int, default=None,
                     help="Cap the number of symbols (useful with --from-sector-cache)")
    ap.add_argument("--force", action="store_true", help="Refetch even if already cached")
    a = ap.parse_args()

    if a.from_sector_cache:
        cache = json.load(open("cache_seed/sector_map_cache.json"))
        symbols = [k[len("IN:"):] for k in cache if k.startswith("IN:")]
    elif a.symbols:
        symbols = a.symbols
    else:
        symbols = DEFAULT_SYMBOLS

    if a.limit:
        symbols = symbols[:a.limit]

    df = fetch_and_cache(symbols, force=a.force)
    n_symbols = df["symbol"].nunique() if not df.empty else 0
    print(f"\n[nse] cache now holds {len(df)} rows across {n_symbols} symbols -> {CACHE_PATH}")
    if not df.empty:
        print(df.sort_values("event_date", ascending=False).head(20).to_string(index=False))


if __name__ == "__main__":
    main()
