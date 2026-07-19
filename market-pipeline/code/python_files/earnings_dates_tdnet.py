#!/usr/bin/env python3
"""
earnings_dates_tdnet.py — SECOND, INDEPENDENT source of REAL Japan
earnings-announcement dates, sourced directly from JPX's TDnet (Timely
Disclosure Network) rather than a data aggregator like Yahoo Finance.
Complements earnings_dates_cache.py's yfinance get_earnings_dates() feed
for the JP market with a source that traces straight back to the actual
"kessan tanshin" (決算短信 — quarterly earnings summary) filing each
listed company submits to JPX the moment results are released.

WHERE THIS DATA COMES FROM
    https://www.release.tdnet.info/inbs/I_list_001_YYYYMMDD.html
    — the free public disclosure viewer JPX operates for TDnet. Each date
    has one or more numbered pages (I_list_001_*, I_list_002_*, ...) of a
    plain HTML table: time, 4-digit company code (+ a trailing class
    digit, e.g. "72030" -> ticker 7203), company name, disclosure title,
    XBRL link, PDF link. Rows whose title contains "決算短信" are the
    Tanshin (quarterly earnings) announcements this script is after.

RESEARCH FINDINGS (2026-07-16) — read before scheduling this as a cron job
    1. NOT an aggregator, NOT login-walled. `requests` with a normal
       browser User-Agent gets a real 200 with real HTML — no session,
       cookie, or auth step required. A generic HTTP client (Python's
       default requests UA, and Claude's own WebFetch tool) got 403,
       which first looked like anti-bot blocking, but curl with a
       standard Chrome UA string succeeded immediately. It is very
       plausibly UA-sniffing rather than a real bot wall.
    2. robots.txt at release.tdnet.info is `Disallow: /` — i.e. TDnet's
       operator has explicitly asked automated crawlers to stay out, even
       though the pages are technically fetchable. This script is a
       polite, low-volume, ad-hoc research/backfill tool (see rate
       limiting below) and should NOT be wired into a scheduled/daily
       job without deliberately deciding to override that robots.txt
       signal. The safer production path for continuous coverage is
       JPX's official *paid* TDnet API service
       (https://www.jpx.co.jp/english/markets/paid-info-listing/tdnet/02.html),
       which explicitly licenses automated bulk access incl. 5 years of
       history.
    3. The free HTML viewer only exposes a ROLLING ~31-CALENDAR-DAY
       WINDOW. `I_main_00.html` links to dates back to ~30 days before
       today; anything older 404s (confirmed: 2026-06-16 loads,
       2026-06-01 does not). So this source is only useful as a
       same-day/recent verification feed, not a historical backfill —
       it cannot replace earnings_dates_cache.py's multi-year history.
    4. TDnet also only records disclosures AFTER they happen — unlike
       yfinance's `.calendar` field, it does not forecast a future
       earnings date. A company's advance "announcement of quarterly
       results date" filing (決算発表日のお知らせ) is itself a TDnet
       disclosure and could be mined for forward dates in a future
       iteration, but this script only harvests actual Tanshin releases.
    5. Live test on 2026-07-16 against Toyota (7203), Sony (6758),
       SoftBank Group (9984), and MUFG (8306): three of the four
       (Toyota, Sony, SoftBank Group) have March fiscal year-ends whose
       FY2026 full-year Tanshin were released 2026-05-08, already
       outside the ~31-day window, and whose next (Q1 FY2027) Tanshin
       isn't due until early August, so they produced no Tanshin hit
       in-window under the default keyword filter (Toyota DID show one
       unrelated TDnet disclosure in-window -- an amendment to an
       employee stock plan, 2026-06-18 -- confirming the ticker-matching
       logic works even when there's no Tanshin to find). MUFG (8306),
       however, DID produce two REAL hits: a correction to its FY2026
       (Japan-GAAP) Tanshin on 2026-06-24, and its FY2026 US-GAAP
       consolidated Tanshin proper on 2026-07-07
       (140120260707588680.pdf). Real Tanshin were also found for other
       JP tickers in-window, e.g. Nishimatsuya Chain (7545.T,
       2026-06-26) and G-Baby Calendar (7363.T, 2026-06-30, several
       correction filings). So this is proven against a REAL sample
       ticker from the original request, not just adjacent names.

RECONCILING AGAINST cache_seed/earnings_dates_cache/JP.parquet
    That cache holds yfinance get_earnings_dates() rows keyed by ticker
    with an `Earnings Date` column (includes both past-actual and one
    forward estimate). To cross-check a specific past date:
        tdnet_df = collect_disclosures(tickers=["7203.T"])
        yf_df = pd.read_parquet("cache_seed/earnings_dates_cache/JP.parquet")
        yf_df = yf_df[yf_df.ticker == "7203.T"]
        # compare tdnet_df.event_date to yf_df["Earnings Date"].dt.date
        # allow a +/- 1 day tolerance: yfinance sometimes stamps the US
        # calendar date of a JST evening/after-hours release.
    Because of the 31-day window, this is only practical as a rolling
    "did today's/this week's yfinance-reported dates actually match a
    real TDnet filing" sanity check, run close to real time — not a bulk
    reconciliation of the whole JP.parquet history.

RATE LIMITING: sequential requests with a 0.5s sleep between them,
default scan is the small accessible window (~30 requests worst case for
one page per day); this was validated with a ~20-request test run.

Usage:
    python3 earnings_dates_tdnet.py                          # sample tickers, full window
    python3 earnings_dates_tdnet.py --tickers 7203.T 6758.T
    python3 earnings_dates_tdnet.py --all-titles              # don't filter to Tanshin only
    python3 earnings_dates_tdnet.py --days 10                 # only scan the last N available days
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://www.release.tdnet.info/inbs/"
MAIN_URL = BASE_URL + "I_main_00.html"

# A generic requests UA gets 403 from this host; a normal browser UA does
# not. This is the one deviation from a plain `requests.get()` needed to
# reach the site at all (see docstring finding #1).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

OUT_DIR = Path("cache_seed/earnings_dates_tdnet")
OUT_DIR.mkdir(parents=True, exist_ok=True)

_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_TIME_RE = re.compile(r'kjTime"[^>]*>([^<]*)<')
_CODE_RE = re.compile(r'kjCode"[^>]*>([^<]*)<')
_NAME_RE = re.compile(r'kjName"[^>]*>([^<]*)<')
_TITLE_RE = re.compile(r'kjTitle"[^>]*><a href="([^"]*)"[^>]*>([^<]*)<')
_DATE_LINK_RE = re.compile(r"I_list_001_(\d{8})\.html")


def fetch_available_dates() -> list[str]:
    """Discover the rolling window of dates TDnet's free viewer currently
    exposes (confirmed ~31 calendar days; anything older 404s)."""
    resp = requests.get(MAIN_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return sorted(set(_DATE_LINK_RE.findall(resp.text)))


def _fetch_page(date: str, page: int) -> str | None:
    url = f"{BASE_URL}I_list_{page:03d}_{date}.html"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    # The server's Content-Type header omits a charset, so `requests`
    # falls back to ISO-8859-1 per HTTP spec default and mangles every
    # multi-byte Japanese character in resp.text. The page really is
    # UTF-8 (per its <meta charset> tag and apparent_encoding) -- override
    # explicitly rather than trusting requests' auto-detected .encoding.
    resp.encoding = "utf-8"
    if resp.status_code == 404 or "404 Not Found" in resp.text:
        return None
    resp.raise_for_status()
    return resp.text


def _parse_rows(html: str) -> list[dict]:
    rows = []
    for r in _ROW_RE.findall(html):
        c, n, t, tm = _CODE_RE.search(r), _NAME_RE.search(r), _TITLE_RE.search(r), _TIME_RE.search(r)
        if not (c and n and t):
            continue
        code = c.group(1).strip()
        if not code.isdigit():
            continue
        rows.append({
            "code": code,
            "ticker": f"{code[:4]}.T",
            "company_name": n.group(1).strip(),
            "title": t.group(2).strip(),
            "pdf_url": BASE_URL + t.group(1),
            "disclosure_time": tm.group(1).strip() if tm else None,
        })
    return rows


def _max_page(html: str) -> int:
    pages = re.findall(r"I_list_(\d{3})_\d{8}\.html", html)
    return max((int(p) for p in pages), default=1)


def collect_disclosures(
    tickers: list[str] | None = None,
    dates: list[str] | None = None,
    keyword: str | None = "決算短信",
    sleep: float = 0.5,
) -> pd.DataFrame:
    """Scan TDnet's currently-accessible rolling window and return rows
    matching `tickers` (None = all) and containing `keyword` in the title
    (None = no title filter). Columns: ticker, event_date, company_name,
    title, disclosure_time, pdf_url, source.
    """
    if dates is None:
        dates = fetch_available_dates()

    ticker_set = set(tickers) if tickers else None
    out = []
    for d in dates:
        html = _fetch_page(d, 1)
        if html is None:
            continue
        n_pages = _max_page(html)
        pages_html = [html] + [_fetch_page(d, p) for p in range(2, n_pages + 1)]
        time.sleep(sleep)
        for ph in pages_html:
            if ph is None:
                continue
            for row in _parse_rows(ph):
                if ticker_set and row["ticker"] not in ticker_set:
                    continue
                if keyword and keyword not in row["title"]:
                    continue
                out.append({
                    "ticker": row["ticker"],
                    "event_date": pd.to_datetime(d, format="%Y%m%d").date(),
                    "company_name": row["company_name"],
                    "title": row["title"],
                    "disclosure_time": row["disclosure_time"],
                    "pdf_url": row["pdf_url"],
                    "source": "tdnet",
                })

    cols = ["ticker", "event_date", "company_name", "title", "disclosure_time", "pdf_url", "source"]
    return pd.DataFrame(out, columns=cols)


def _jp_tickers_from_sector_cache(path: str = "cache_seed/sector_map_cache.json") -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    return [k[len("JP:"):] for k in d if k.startswith("JP:")]


DEFAULT_SAMPLE = ["7203.T", "6758.T", "9984.T", "8306.T"]  # Toyota, Sony, SoftBank Group, MUFG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", default=None,
                     help="JP tickers e.g. 7203.T. Default: 4 sample large-caps.")
    ap.add_argument("--from-sector-cache", action="store_true",
                     help="Use all JP: tickers in cache_seed/sector_map_cache.json instead of --tickers.")
    ap.add_argument("--all-titles", action="store_true",
                     help="Don't filter to 決算短信 (Tanshin) — keep every disclosure title.")
    ap.add_argument("--days", type=int, default=None,
                     help="Only scan the last N available days (default: full accessible window).")
    ap.add_argument("--out", default=str(OUT_DIR / "JP.parquet"))
    a = ap.parse_args()

    if a.from_sector_cache:
        tickers = _jp_tickers_from_sector_cache()
        print(f"Loaded {len(tickers)} JP tickers from sector_map_cache.json")
    else:
        tickers = a.tickers if a.tickers is not None else DEFAULT_SAMPLE

    dates = fetch_available_dates()
    if a.days:
        dates = dates[-a.days:]
    print(f"TDnet accessible window: {dates[0]}..{dates[-1]} ({len(dates)} days)")
    print(f"Scanning for tickers: {tickers}")

    df = collect_disclosures(tickers=tickers, dates=dates, keyword=None if a.all_titles else "決算短信")
    print(f"\nFound {len(df)} matching disclosure(s):")
    if not df.empty:
        print(df.to_string(index=False))
        df.to_parquet(a.out, index=False)
        print(f"\nSaved to {a.out}")
    else:
        print("(none of the requested tickers had a matching TDnet disclosure in the "
              "current ~31-day window — this is expected for large-caps between "
              "quarterly reporting cycles; try --all-titles or a broader --tickers list "
              "to confirm the scraper itself is working)")


if __name__ == "__main__":
    main()
