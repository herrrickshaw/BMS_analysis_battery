#!/usr/bin/env python3
"""
earnings_dates_bse.py — real financial-results filing dates sourced
directly from BSE India (Bombay Stock Exchange), as a THIRD independent
source alongside earnings_dates_nse.py and yfinance/yahooquery.

WHY BSE SPECIFICALLY: confirmed empirically this session (2026-07-16) that
a large chunk of India's "stuck" (zero earnings info anywhere) universe
isn't a Yahoo rate-limit problem at all — direct probes of stuck tickers
returned real, unthrottled 200 responses with genuinely empty earnings
history. Checking WHY surfaced a second, distinct gap: many small/mid-cap
India companies are BSE-listed but either NOT on NSE at all, or are on
NSE but their results get filed/discovered through BSE's own disclosure
system independently of NSE's. bsedata (the existing PyPI package) was
checked first and confirmed to be quote/Bhavcopy-only (getBhavCopyData,
getQuote, topGainers/topLosers) with NO corporate-announcements or
financial-results endpoint — same "price library, not an earnings
library" gap already hit with Korea's pykrx/finance-datareader/krxreader.
This script goes directly to BSE's own JSON API instead, mirroring
earnings_dates_nse.py's architecture (confirmed via bsedata's own
getScripCodes() pointing at api.bseindia.com, then reverse-engineered the
specific announcement endpoint directly).

TWO ENDPOINTS, confirmed live 2026-07-16:

  ListofScripData — the full ACTIVE BSE equity universe in ONE call
      https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w
      Returns SCRIP_CD, scrip_id (trading symbol), ISIN_NUMBER, Status,
      Segment, Mktcap for ~4,900 active equity scrips. ISIN_NUMBER is the
      SAME key earnings_dates_nse.py already captures per filing, so this
      is how BSE-exclusive companies (ISIN not seen in the NSE collection)
      get identified rather than fuzzy-matching by company name.

  AnnSubCategoryGetData — financial-results announcements, per scrip
      https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w
      ?strCat=Result&strScrip=<SCRIP_CD>&strPrevDate=YYYYMMDD
      &strToDate=YYYYMMDD&strSearch=P&strType=C
      Confirmed: a WIDE date range (2.5+ years) works fine when scoped to
      ONE scrip via strScrip -- an unscoped (all-scrips) query with the
      same range gets rejected ("Date range exceeded threshold"), so this
      collector always queries per-scrip, never the full feed at once.

NO ANTI-BOT WALL FOUND (unlike NSE): api.bseindia.com's endpoints
responded 200 with real JSON on a bare requests.Session with just a
Referer header and no homepage-priming GET needed in testing -- kept the
priming GET anyway for parity/future-proofing, same non-fatal treatment
as earnings_dates_nse.py's.

NO SURPRISE% HERE EITHER: like earnings_dates_nse.py, this is a DATE +
actual-headline source, not a consensus-estimate source -- BSE doesn't
publish analyst estimates any more than NSE does. Feeds into
earnings_price_dataset.py as a date-only cross-check source, same role as
NSE/SEC-8K/DART.

Usage:
    python3 earnings_dates_bse.py --all-active            # ~4,900 scrips
    python3 earnings_dates_bse.py --bse-only-vs-nse        # only ISINs NOT
                                                            # already seen
                                                            # in the NSE
                                                            # collection
    python3 earnings_dates_bse.py --scrips 500325 500002
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path("cache_seed/earnings_dates_bse")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = CACHE_DIR / "IN.parquet"
SCRIP_LIST_CACHE = CACHE_DIR / "scrip_list.parquet"

BASE_URL = "https://www.bseindia.com"
API_BASE = "https://api.bseindia.com/BseIndiaAPI/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE_URL}/",
    "Connection": "keep-alive",
}

SLEEP_SECONDS = 2.0  # BSE's block triggers much faster than NSE's -- a
                     # handful of ad hoc test calls over ~5 min was enough
                     # to get a "Document Moved" soft-block (HTTP 200,
                     # decoy HTML, not a real 403), confirmed to persist
                     # for at least 2+ minutes after. Raised well above
                     # NSE's 0.6s until real behavior at scale is known.
CHECKPOINT_EVERY = 50
DATE_FROM = "20160101"  # matches this repo's other India collectors' depth
CONSECUTIVE_BLOCK_THRESHOLD = 5   # this many invalid_json in a row is
                                  # treated as "currently blocked", not
                                  # "these 5 scrips happen to have no data"
BLOCK_COOLDOWN_SECONDS = 180      # matches the 3-minute pacing that worked
                                  # for yahooquery's own rate-limit recovery


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        r = s.get(BASE_URL + "/", timeout=15)
        if r.status_code != 200:
            print(f"  [bse] homepage priming GET returned {r.status_code} (non-fatal)")
    except requests.RequestException as e:
        print(f"  [bse] homepage priming GET failed ({e}) — continuing anyway")
    return s


def _get_json(session: requests.Session, path: str, params: dict, retries: int = 2):
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
            time.sleep(1.0)
            continue
        return None, f"http_{r.status_code}"
    return None, "exhausted_retries"


def fetch_scrip_list(session: requests.Session, force: bool = False) -> pd.DataFrame:
    """Full active BSE equity universe, one call. Cached separately from
    the announcements cache since it's a static-ish reference list, not
    per-symbol event data."""
    if SCRIP_LIST_CACHE.exists() and not force:
        return pd.read_parquet(SCRIP_LIST_CACHE)
    data, err = _get_json(session, "ListofScripData/w",
                           {"Group": "", "Scripcode": "", "industry": "",
                            "segment": "Equity", "status": "Active"})
    if err:
        raise RuntimeError(f"BSE scrip list fetch failed: {err}")
    df = pd.DataFrame(data)
    df.to_parquet(SCRIP_LIST_CACHE, index=False)
    print(f"[bse] scrip list: {len(df)} active equity scrips -> {SCRIP_LIST_CACHE}")
    return df


def fetch_financial_results(session: requests.Session, scrip_cd: str) -> tuple[list[dict], str | None]:
    data, err = _get_json(session, "AnnSubCategoryGetData/w", {
        "strCat": "Result", "strScrip": scrip_cd, "strPrevDate": DATE_FROM,
        "strToDate": pd.Timestamp.now().strftime("%Y%m%d"),
        "strSearch": "P", "strType": "C",
    })
    if err:
        print(f"  [{scrip_cd}] financial-results error: {err}")
        return [], err
    rows = []
    for r in (data or {}).get("Table", []):
        rows.append({
            "scrip_cd": scrip_cd,
            "event_date": r.get("NEWS_DT") or r.get("DT_TM"),
            "event_type": "actual_result",
            "source": "bse",
            "headline": r.get("HEADLINE"),
            "category": r.get("CATEGORYNAME"),
            "subcategory": r.get("SUBCATNAME"),
        })
    return rows, None


def _load_cached() -> pd.DataFrame:
    if CACHE_PATH.exists():
        return pd.read_parquet(CACHE_PATH)
    return pd.DataFrame(columns=["scrip_cd", "event_date", "event_type", "source"])


def fetch_and_cache(scrip_codes: list[str], force: bool = False) -> pd.DataFrame:
    have = _load_cached()
    already = set(have["scrip_cd"].astype(str).unique()) if not have.empty and not force else set()
    missing = [s for s in scrip_codes if str(s) not in already]

    print(f"[bse] {len(scrip_codes)} scrips requested, {len(already)} already cached, "
          f"{len(missing)} to fetch...")
    if not missing:
        return have

    session = _new_session()
    new_rows = []
    consecutive_invalid_json = 0
    for i, scrip in enumerate(missing, 1):
        rows, err = fetch_financial_results(session, str(scrip))
        time.sleep(SLEEP_SECONDS)
        print(f"  [{i}/{len(missing)}] {scrip}: {len(rows)} financial-result filings")
        new_rows.extend(rows)

        if err == "invalid_json":
            consecutive_invalid_json += 1
            if consecutive_invalid_json >= CONSECUTIVE_BLOCK_THRESHOLD:
                # a real BSE soft-block returns HTTP 200 with decoy HTML
                # instead of JSON -- indistinguishable per-request from a
                # genuine parse hiccup, but 5 in a row is a block, not
                # coincidence. Checkpoint what's collected so far, cool
                # down, then re-prime a fresh session before continuing.
                if new_rows:
                    new_df = pd.DataFrame(new_rows)
                    combined = pd.concat([have, new_df], ignore_index=True) if not have.empty else new_df
                    combined = combined.drop_duplicates(subset=["scrip_cd", "event_date", "headline"])
                    combined.to_parquet(CACHE_PATH, index=False)
                    have = combined
                    new_rows = []
                print(f"  [bse] {consecutive_invalid_json} consecutive invalid_json responses -- "
                      f"treating as blocked, cooling down {BLOCK_COOLDOWN_SECONDS}s before retrying...")
                time.sleep(BLOCK_COOLDOWN_SECONDS)
                session = _new_session()
                consecutive_invalid_json = 0
        else:
            consecutive_invalid_json = 0

        if new_rows and i % CHECKPOINT_EVERY == 0:
            new_df = pd.DataFrame(new_rows)
            combined = pd.concat([have, new_df], ignore_index=True) if not have.empty else new_df
            combined = combined.drop_duplicates(subset=["scrip_cd", "event_date", "headline"])
            combined.to_parquet(CACHE_PATH, index=False)
            have = combined
            new_rows = []
            print(f"  [bse] checkpoint: {len(have)} total rows saved ({i}/{len(missing)} scrips done)")

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined = pd.concat([have, new_df], ignore_index=True) if not have.empty else new_df
        combined = combined.drop_duplicates(subset=["scrip_cd", "event_date", "headline"])
        combined.to_parquet(CACHE_PATH, index=False)
        have = combined
    elif have.empty:
        print("[bse] no new rows fetched (all requests errored — see per-scrip messages above)")

    return have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrips", nargs="+", default=None, help="BSE scrip codes, e.g. 500325 500002")
    ap.add_argument("--all-active", action="store_true", help="All ~4,900 active BSE equity scrips")
    ap.add_argument("--bse-only-vs-nse", action="store_true",
                     help="Only scrips whose ISIN is NOT already present in "
                          "cache_seed/earnings_dates_nse/IN.parquet -- the "
                          "genuinely BSE-exclusive population")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    session = _new_session()
    scrip_list = fetch_scrip_list(session, force=False)

    if a.scrips:
        codes = a.scrips
    elif a.bse_only_vs_nse:
        nse_path = Path("cache_seed/earnings_dates_nse/IN.parquet")
        nse_isins = set()
        if nse_path.exists():
            nse = pd.read_parquet(nse_path)
            if "isin" in nse.columns:
                nse_isins = set(nse["isin"].dropna().unique())
        mask = ~scrip_list["ISIN_NUMBER"].isin(nse_isins)
        codes = scrip_list.loc[mask, "SCRIP_CD"].tolist()
        print(f"[bse] {len(scrip_list)} active BSE scrips, {len(nse_isins)} ISINs already "
              f"in NSE collection, {len(codes)} BSE-exclusive scrips selected")
    elif a.all_active:
        codes = scrip_list["SCRIP_CD"].tolist()
    else:
        codes = ["500325", "500002", "500003"]  # RIL, ABB India, Aegis Logistics (smoke test)

    if a.limit:
        codes = codes[:a.limit]

    df = fetch_and_cache(codes, force=a.force)
    n_scrips = df["scrip_cd"].nunique() if not df.empty else 0
    print(f"\n[bse] cache now holds {len(df)} rows across {n_scrips} scrips -> {CACHE_PATH}")


if __name__ == "__main__":
    main()
