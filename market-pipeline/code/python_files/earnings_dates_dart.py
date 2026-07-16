#!/usr/bin/env python3
"""
earnings_dates_dart.py — Korea earnings/filing dates from OpenDART
(opendart.fss.or.kr), the Financial Supervisory Service's official REST API
over DART (Data Analysis, Retrieval and Transfer System), Korea's mandatory
corporate-disclosure system.

WHY THIS EXISTS: Korea is the worst-covered market in the
earnings_dates_cache.py / earnings_key_dates.py pipeline — only 68/579
classified KR tickers (12%) have any cached data, because Yahoo Finance
(get_earnings_dates(), used by earnings_dates_cache.py) has rate-limited
Korea harder and longer than IN/US/JP, which recovered to 55-79% coverage
after retries while KR stayed at 0 across three backoff-protected attempts.
This module is a wholly independent path: real filing dates sourced
directly from the Korean regulator, not another yfinance-dependent fetch.

BLOCKED ON A MISSING CREDENTIAL — READ BEFORE RUNNING
This script needs a DART_KEY (a 40-char "crtfc_key") in this directory's
.env. As of this build, .env has ALPHAVANTAGE_KEY / EODHD_KEY /
MARKETAUX_KEY / NEWSAPI_KEY / NEWSDATA_KEY but NO DART_KEY — nobody has
set this up before. Getting one requires REGISTERING AN ACCOUNT
(email + password) at https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do
— that is account creation with a password, which is outside what an
automated agent is allowed to do on a human's behalf. A human needs to:
    1. Go to https://opendart.fss.or.kr/ -> "인증키 신청" (API key
       request). Individual accounts are issued INSTANTLY (no approval
       wait); corporate accounts take 1-2 business days.
    2. Register with an email + password (own choice), confirm the email.
    3. Copy the issued 40-character key into this directory's .env as:
           DART_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    4. Re-run this script — no code changes needed, it picks up DART_KEY
       from .env automatically (same _load_dotenv() convention as
       sentiment_pipeline.py).
Confirmed LIVE and reachable without a key: an unauthenticated call to
list.json returns a real, structured error —
    {"status":"010","message":"등록되지 않은 인증키입니다."}   (Korean for
    "unregistered authentication key") — proving the endpoint, network
    path, and JSON contract all work; the ONLY missing piece is the key
    itself. corpCode.xml behaves identically (same status:010 XML body).
DO NOT paste a real crtfc_key into chat/logs if a human sets one up and
hands credentials over verbally — have them add it straight to .env instead.

WHAT THIS SCRIPT DOES ONCE A KEY IS PRESENT:
  1. fetch_corp_code_map() — downloads OpenDART's bulk corp_code.xml
     (a ~3MB zip of EVERY DART-registered entity: corp_code, corp_name,
     stock_code, modify_date), caches it locally
     (cache_seed/dart_corp_code_map.parquet, refreshed if >7 days old —
     DART updates this file roughly daily but full churn is rare), and
     builds a {6-digit KRX stock_code -> 8-digit DART corp_code} lookup.
     KRX tickers in this repo's convention (e.g. "005930.KS") need their
     ".KS"/".KQ" suffix stripped to match stock_code; DART's stock_code is
     already zero-padded to 6 digits so no further padding is needed.
  2. fetch_filings(corp_code, bgn_de, end_de) — calls list.json filtered to
     pblntf_ty="A" (정기공시 / periodic reports: 사업보고서 annual,
     반기보고서 half-year, 분기보고서 quarterly — real filing dates, not
     estimates) across a date window, paginated at page_count=100 (DART's
     max per page).
  3. collect(tickers, years_back=2) — resolves each ticker to a corp_code,
     pulls its periodic-report filing history, and returns/saves a
     DataFrame: ticker, corp_code, filing_date, report_name, source="dart".

RATE LIMITS: OpenDART's docs don't publish a per-second cap; the
documented failure mode is error code 020 ("요청 제한을 초과하였습니다" /
request limit exceeded), observed in practice around ~20,000 requests/day
per key. This script stays well inside that with a REQUEST_DELAY_SEC
throttle between calls (default 0.3s) and by caching corp_code_map to
avoid re-downloading the bulk file every run.

RECONCILING AGAINST THE YFINANCE CACHE: once real data is fetched, treat
this as KOREA'S PRIMARY earnings-date source (it has real filing dates for
any KR corp with a stock_code, vs. yfinance's ~12% coverage) and
cache_seed/earnings_dates_cache/KR.parquet as a secondary cross-check:
  - Join on ticker (strip .KS/.KQ from the yfinance side to compare against
    this module's bare-ticker rows, or add the suffix back to this
    module's output — pick ONE convention and keep it consistent with
    earnings_key_dates.py's `symbol` column, which is suffixed).
  - DART's filing_date is the date the periodic report was FILED (after
    the quarter/half/year closed), which is NOT the same event as
    yfinance's "Earnings Date" (the announcement/call date, which in
    Korea sometimes precedes formal filing and sometimes follows it, e.g.
    preliminary earnings release via 주요사항보고서 (pblntf_ty="B") often
    lands before the formal 사업보고서/분기보고서). Where both sources
    have a date for the same ticker/quarter, expect a lag of days-to-weeks,
    not an exact match — don't treat a mismatch as a bug in either source.
  - For PEAD-style event studies (pead_sector_spillover_v2.py), the
    earlier of the two dates (often DART's 주요사항보고서 preliminary
    release, if fetched — see the pblntf_ty="B" TODO below) is closer to
    the true market-moving event than the formal periodic-report filing
    date; this module currently only fetches pblntf_ty="A" (formal
    periodic reports) — extending to "B" (주요사항보고서) is a follow-up,
    not yet implemented here.

Usage:
    python3 earnings_dates_dart.py --self-test        # prove connectivity,
                                                        # no key needed
    python3 earnings_dates_dart.py --sample            # fetch real data for
                                                        # a handful of KR
                                                        # tickers (needs
                                                        # DART_KEY)
    python3 earnings_dates_dart.py --tickers 005930.KS 000660.KS
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

# -- credential loading — same convention as sentiment_pipeline.py ----------
_ENV_PATHS = (
    Path(__file__).parent / ".env",
    Path.home() / "repos" / "global-stock-screener" / ".env",
    Path.home() / ".env",
)


def _load_dotenv() -> None:
    """Existing environment variables WIN over the file."""
    for envf in _ENV_PATHS:
        if not envf.exists():
            continue
        try:
            lines = envf.read_text().splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

DART_KEY = os.environ.get("DART_KEY", "")
BASE_URL = "https://opendart.fss.or.kr/api"
REQUEST_DELAY_SEC = 0.3  # throttle, well under the ~20k/day observed cap

CACHE_DIR = Path(__file__).parent / "cache_seed"
CORP_CODE_CACHE = CACHE_DIR / "dart_corp_code_map.parquet"
OUT_DIR = CACHE_DIR / "earnings_dates_dart"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REGISTER_URL = "https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do"
NO_KEY_MSG = f"""
DART_KEY is not set. OpenDART requires a free account (email + password)
registered at {REGISTER_URL} — an automated agent cannot create that
account on your behalf (it needs a real email + a chosen password).

To unblock:
  1. Register at https://opendart.fss.or.kr/ ("인증키 신청" / API key
     request). Individual accounts are issued INSTANTLY (no approval
     wait); corporate accounts take 1-2 business days.
  2. Add the issued 40-char key to this directory's .env as:
         DART_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  3. Re-run this script.
""".strip()


def _bare_krx(ticker: str) -> str:
    """'005930.KS' -> '005930'; already-bare input passes through."""
    return ticker.split(".")[0]


def _check(resp_json: dict, context: str) -> None:
    status = resp_json.get("status")
    if status == "013":
        return  # "no data found for the given search" — not an error, just empty
    if status not in ("000",):
        msg = resp_json.get("message", "")
        raise RuntimeError(f"DART API error during {context}: status={status} message={msg}")


def self_test() -> bool:
    """Proves the endpoint is reachable and the JSON/XML contract is what
    this module expects — WITHOUT needing a valid key. Confirmed live on
    2026-07-16: an invalid-key call returns
    {"status":"010","message":"등록되지 않은 인증키입니다."} (Korean for
    "unregistered authentication key"), not a network failure or CAPTCHA.
    Returns True if the endpoint behaved as expected (key required and
    absent/invalid), False on any unexpected network/shape failure."""
    print("[self-test] Calling list.json with a deliberately invalid key "
          "to confirm connectivity + response contract (no real key needed)...")
    try:
        r = requests.get(f"{BASE_URL}/list.json", params={
            "crtfc_key": "0" * 40,
            "corp_code": "00126380",  # Samsung Electronics' known corp_code
            "bgn_de": "20260101",
            "end_de": "20260716",
        }, timeout=15)
        r.raise_for_status()
        body = r.json()
        print(f"[self-test] HTTP {r.status_code}, body={body}")
        if body.get("status") == "010":
            print("[self-test] PASS: endpoint live, JSON contract as expected, "
                  "key is the only missing piece.")
            return True
        print(f"[self-test] UNEXPECTED status (not '010' unregistered-key): {body}")
        return False
    except Exception as e:
        print(f"[self-test] FAIL: {type(e).__name__}: {e}")
        return False


def fetch_corp_code_map(force: bool = False) -> pd.DataFrame:
    """Downloads+parses OpenDART's bulk corp_code.xml (zip of EVERY
    DART-registered entity). Cached locally; refreshed if the cache is
    missing or >7 days old. Returns columns: corp_code, corp_name,
    stock_code, modify_date. Requires DART_KEY."""
    if not force and CORP_CODE_CACHE.exists():
        age_days = (time.time() - CORP_CODE_CACHE.stat().st_mtime) / 86400
        if age_days < 7:
            return pd.read_parquet(CORP_CODE_CACHE)

    if not DART_KEY:
        raise RuntimeError(NO_KEY_MSG)

    print("[corp_code] downloading bulk corp_code.xml from OpenDART...")
    r = requests.get(f"{BASE_URL}/corpCode.xml", params={"crtfc_key": DART_KEY}, timeout=60)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "")
    if "zip" not in ctype and r.content[:2] != b"PK":
        # Not a zip -> almost certainly a JSON/XML error body instead
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]
        raise RuntimeError(f"DART corpCode.xml did not return a zip (got {ctype}): {body}")

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    xml_bytes = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml_bytes)

    rows = []
    for item in root.findall("list"):
        rows.append({
            "corp_code": (item.findtext("corp_code") or "").strip(),
            "corp_name": (item.findtext("corp_name") or "").strip(),
            "stock_code": (item.findtext("stock_code") or "").strip(),
            "modify_date": (item.findtext("modify_date") or "").strip(),
        })
    df = pd.DataFrame(rows)
    df.to_parquet(CORP_CODE_CACHE, index=False)
    n_listed = int((df["stock_code"] != "").sum())
    print(f"[corp_code] cached {len(df)} entities ({n_listed} with a KRX stock_code) "
          f"-> {CORP_CODE_CACHE}")
    return df


def resolve_corp_codes(tickers: list[str]) -> dict[str, str | None]:
    """{'005930.KS': '00126380', ...}; None where no DART match was found."""
    cmap = fetch_corp_code_map()
    by_stock_code = dict(zip(cmap["stock_code"], cmap["corp_code"]))
    out = {}
    for t in tickers:
        out[t] = by_stock_code.get(_bare_krx(t))
    return out


def fetch_filings(corp_code: str, bgn_de: str, end_de: str, pblntf_ty: str = "A") -> list[dict]:
    """One ticker's periodic-report filing list (list.json), paginated.
    pblntf_ty='A' = 정기공시 (periodic reports: annual/half-year/quarterly).
    Returns raw DART rows (rcept_no, report_nm, rcept_dt, ...)."""
    if not DART_KEY:
        raise RuntimeError(NO_KEY_MSG)

    all_rows = []
    page = 1
    while True:
        r = requests.get(f"{BASE_URL}/list.json", params={
            "crtfc_key": DART_KEY,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "pblntf_ty": pblntf_ty,
            "page_no": page,
            "page_count": 100,
        }, timeout=20)
        r.raise_for_status()
        body = r.json()
        _check(body, context=f"list.json corp_code={corp_code} page={page}")
        rows = body.get("list", []) or []
        all_rows.extend(rows)
        total_page = int(body.get("total_page", 1) or 1)
        if page >= total_page or not rows:
            break
        page += 1
        time.sleep(REQUEST_DELAY_SEC)
    return all_rows


def collect(tickers: list[str], years_back: int = 2) -> pd.DataFrame:
    """Full pipeline: ticker -> corp_code -> periodic-report filing dates.
    Returns columns: ticker, corp_code, filing_date, report_name, source."""
    if not DART_KEY:
        print(NO_KEY_MSG)
        return pd.DataFrame(columns=["ticker", "corp_code", "filing_date", "report_name", "source"])

    corp_codes = resolve_corp_codes(tickers)
    unresolved = [t for t, c in corp_codes.items() if not c]
    if unresolved:
        print(f"[collect] {len(unresolved)}/{len(tickers)} tickers had no DART corp_code match: "
              f"{unresolved}")

    end_de = datetime.now().strftime("%Y%m%d")
    bgn_de = (datetime.now() - timedelta(days=365 * years_back)).strftime("%Y%m%d")

    rows = []
    for t, corp_code in corp_codes.items():
        if not corp_code:
            continue
        try:
            filings = fetch_filings(corp_code, bgn_de, end_de, pblntf_ty="A")
        except Exception as e:
            print(f"[collect] {t} (corp_code={corp_code}): FAILED — {type(e).__name__}: {e}")
            continue
        print(f"[collect] {t} (corp_code={corp_code}): {len(filings)} periodic-report filings")
        for f in filings:
            rows.append({
                "ticker": t,
                "corp_code": corp_code,
                "filing_date": f.get("rcept_dt"),   # YYYYMMDD
                "report_name": f.get("report_nm"),
                "source": "dart",
            })
        time.sleep(REQUEST_DELAY_SEC)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["filing_date"] = pd.to_datetime(df["filing_date"], format="%Y%m%d", errors="coerce")
    return df


def _sample_tickers(n: int = 10) -> list[str]:
    """Pulls real KR: tickers out of cache_seed/sector_map_cache.json
    (the classified universe earnings_dates_cache.py also draws from) so
    the sample isn't hand-picked/fabricated."""
    sector_cache = CACHE_DIR / "sector_map_cache.json"
    known_good = ["005930.KS", "000660.KS", "035420.KS"]  # Samsung, SK Hynix, NAVER
    if not sector_cache.exists():
        return known_good[:n]
    d = json.loads(sector_cache.read_text())
    kr = sorted(k[3:] for k in d if k.startswith("KR:"))
    # keep the well-known names first (readable proof-of-life), then pad with
    # real cache entries
    sample = [t for t in known_good if t in kr]
    sample += [t for t in kr if t not in sample]
    return sample[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true",
                     help="prove connectivity/contract without needing a key")
    ap.add_argument("--sample", action="store_true",
                     help="fetch real filing dates for a small sample of KR tickers")
    ap.add_argument("--tickers", nargs="+", default=None,
                     help="explicit KRX tickers, e.g. 005930.KS 000660.KS")
    ap.add_argument("--n", type=int, default=10, help="sample size for --sample")
    a = ap.parse_args()

    if a.self_test:
        ok = self_test()
        raise SystemExit(0 if ok else 1)

    if not DART_KEY:
        print(NO_KEY_MSG)
        raise SystemExit(1)

    tickers = a.tickers if a.tickers else _sample_tickers(a.n)
    print(f"Fetching DART periodic-report filing dates for {len(tickers)} tickers: {tickers}")
    df = collect(tickers)
    if df.empty:
        print("No rows fetched (see per-ticker errors above).")
        raise SystemExit(1)

    out_path = OUT_DIR / "KR.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nSaved {len(df)} rows -> {out_path}\n")
    print(df.sort_values(["ticker", "filing_date"]).to_string(index=False))


if __name__ == "__main__":
    main()
