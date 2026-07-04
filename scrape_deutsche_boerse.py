#!/usr/bin/env python3
"""
scrape_deutsche_boerse.py
=========================
Scrapes all German equity data from live.deutsche-boerse.com / boerse-frankfurt.de
via their undocumented REST API (same API used by the bf4py library).

Run on your LOCAL machine — this site is blocked in the sandbox.

Requirements:
    pip install requests

Output:
    data/de_instruments.csv      – ISIN, WKN, name, sector, market cap, exchange
    data/de_equity_details.csv   – extended: country, currency, indices, key ratios
    data/de_universe_enriched.csv – existing DE tickers + all new fields merged

Usage:
    python3 scrape_deutsche_boerse.py [--details] [--limit N]
"""
import csv, hashlib, json, re, sys, time, argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    sys.exit("Install requests first: pip install requests")

# ── Config ────────────────────────────────────────────────────────────────────
DATA       = Path(__file__).parent / "data"
OUT_INSTR  = DATA / "de_instruments.csv"
OUT_DETAIL = DATA / "de_equity_details.csv"
OUT_MERGED = DATA / "de_universe_enriched.csv"

HOME_URL   = "https://live.deutsche-boerse.com"
API_DATA   = "https://api.boerse-frankfurt.de/v1/data/"
API_SEARCH = "https://api.boerse-frankfurt.de/v1/search/"

HEADERS_BASE = {
    "authority":         "api.boerse-frankfurt.de",
    "origin":            "https://live.deutsche-boerse.com",
    "referer":           "https://live.deutsche-boerse.com/",
    "accept":            "application/json, text/plain, */*",
    "accept-language":   "en-US,en;q=0.9",
    "user-agent":        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36",
}

SEARCH_BATCH  = 50     # results per search request
DETAIL_BATCH  = 20     # ISINs per detail-fetch session
RATE_DELAY    = 0.2    # seconds between requests
MAX_INSTRUMENTS = None  # set to an int to cap (for testing)


# ── Security header generation ────────────────────────────────────────────────
_salt: str | None = None

def _get_salt(session: requests.Session) -> str:
    global _salt
    if _salt:
        return _salt
    print("  Fetching salt from live.deutsche-boerse.com JS...", end="", flush=True)
    resp = session.get(HOME_URL + "/en", headers={
        "user-agent": HEADERS_BASE["user-agent"]
    }, timeout=15)
    resp.raise_for_status()
    js_match = re.search(r'main\.\w+\.js', resp.text)
    if not js_match:
        raise RuntimeError("Could not find main JS file on homepage")
    js_url = f"{HOME_URL}/{js_match.group()}"
    js_resp = session.get(js_url, headers={"user-agent": HEADERS_BASE["user-agent"]}, timeout=20)
    js_resp.raise_for_status()
    salt_match = re.search(r'(?<=salt:")\w+', js_resp.text)
    if not salt_match:
        raise RuntimeError("Could not find salt in JS file")
    _salt = salt_match.group()
    print(f" salt={_salt[:8]}…")
    return _salt


def _security_headers(url: str, salt: str) -> dict:
    utc_now = datetime.now(timezone.utc)
    ts_ms = utc_now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_now.microsecond // 1000:03d}Z"
    local_now = datetime.now()
    traceid = hashlib.md5((ts_ms + url + salt).encode()).hexdigest()
    security = hashlib.md5(local_now.strftime("%Y%m%d%H%M").encode()).hexdigest()
    return {
        "client-date":      ts_ms,
        "x-client-traceid": traceid,
        "x-security":       security,
    }


def _headers(url: str, salt: str, content_json: bool = False) -> dict:
    h = dict(HEADERS_BASE)
    h.update(_security_headers(url, salt))
    if content_json:
        h["content-type"] = "application/json"
    return h


# ── API calls ─────────────────────────────────────────────────────────────────
def search_equities(session, salt, offset=0, limit=SEARCH_BATCH,
                    types=None, indices=None, country=None) -> dict:
    """POST /v1/search/equity_search — paginated list of all equities."""
    url = API_SEARCH + "equity_search"
    body = {
        "searchTerms":  [],
        "types":        types or ["AKTIE", "ETF", "FONDS", "ZERTIFIKAT"],
        "indices":      indices or [],
        "offset":       offset,
        "limit":        limit,
        "lang":         "en",
        "sorting":      "NAME",
        "sortOrder":    "ASC",
    }
    if country:
        body["countries"] = [country]

    resp = session.post(url, json=body, headers=_headers(url, salt, True), timeout=15)
    resp.raise_for_status()
    return resp.json()


def equity_master_data(session, salt, isin: str) -> dict:
    """GET /v1/data/equity_master_data — full detail for one ISIN."""
    url = API_DATA + "equity_master_data"
    full_url = url + "?" + urlencode({"isin": isin})
    resp = session.get(full_url, headers=_headers(full_url, salt), timeout=15)
    resp.raise_for_status()
    return resp.json()


def equity_key_data(session, salt, isin: str) -> dict:
    """GET /v1/data/equity_key_data — key ratios for one ISIN."""
    url = API_DATA + "equity_key_data"
    full_url = url + "?" + urlencode({"isin": isin})
    resp = session.get(full_url, headers=_headers(full_url, salt), timeout=15)
    resp.raise_for_status()
    return resp.json()


def data_sheet_header(session, salt, isin: str) -> dict:
    """GET /v1/data/data_sheet_header — WKN, name, type for one ISIN."""
    url = API_DATA + "data_sheet_header"
    full_url = url + "?" + urlencode({"isin": isin})
    resp = session.get(full_url, headers=_headers(full_url, salt), timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Field extractors ──────────────────────────────────────────────────────────
def _str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return v.get("originalValue") or v.get("value") or ""
    return str(v)


def _parse_search_item(item: dict) -> dict:
    """Extract flat row from one search result item."""
    name = item.get("name", {})
    return {
        "isin":         _str(item.get("isin")),
        "wkn":          _str(item.get("wkn")),
        "name":         name.get("originalValue") or name.get("translations", {}).get("en") or name.get("translations", {}).get("others") or "",
        "instrument_type": _str(item.get("type")),
        "exchange_symbol": _str(item.get("exchangeSymbol")),
        "currency":     _str(item.get("currency")),
        "country":      _str(item.get("country")),
        "sector":       _str(item.get("sector")),
        "market_cap_eur": _str(item.get("marketCapitalizationEuro")),
        "market_cap_cat": _str(item.get("marketCapitalizationCategory")),
    }


def _parse_master(data: dict) -> dict:
    """Flatten equity_master_data response."""
    return {
        "isin":          _str(data.get("isin")),
        "wkn":           _str(data.get("wkn")),
        "name":          _str(data.get("instrumentName")),
        "instrument_type": _str(data.get("instrumentTypeKey")),
        "exchange_symbol": _str(data.get("exchangeSymbol")),
        "currency":      _str(data.get("currency")),
        "country":       _str(data.get("countryOfIncorporation")),
        "sector":        _str(data.get("sector")),
        "industry":      _str(data.get("industry")),
        "sub_industry":  _str(data.get("subIndustry")),
        "founding_year": _str(data.get("foundingYear")),
        "employees":     _str(data.get("numberOfEmployees")),
        "website":       _str(data.get("website")),
        "description":   _str(data.get("companyDescription")),
    }


# ── Main scrape ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--details",   action="store_true", help="Also fetch per-ISIN master data (slower)")
    parser.add_argument("--stocks-only", action="store_true", help="Only AKTIE type (skip ETFs/funds)")
    parser.add_argument("--limit",     type=int, default=0,  help="Stop after N instruments (0=all)")
    parser.add_argument("--xetra-only", action="store_true", help="Filter to XETR exchange only")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    types = ["AKTIE"] if args.stocks_only else None

    session = requests.Session()
    session.headers.update({"user-agent": HEADERS_BASE["user-agent"]})

    print("=" * 60)
    print("Deutsche Börse / Boerse Frankfurt Scraper")
    print("=" * 60)

    # Get salt
    try:
        salt = _get_salt(session)
    except Exception as e:
        sys.exit(f"Could not obtain salt: {e}")

    # ── Step 1: Fetch all instruments via search ───────────────────────────────
    print("\n[Step 1] Fetching instrument list from equity_search...")
    all_items: list[dict] = []
    offset = 0
    total = None

    while True:
        try:
            data = search_equities(session, salt, offset=offset, limit=SEARCH_BATCH, types=types)
        except requests.HTTPError as e:
            print(f"  HTTP {e.response.status_code} at offset {offset} — stopping")
            break
        except Exception as e:
            print(f"  Error at offset {offset}: {e} — stopping")
            break

        items = data.get("list", data.get("instruments", []))
        if total is None:
            total = data.get("totalCount", "?")
            print(f"  Total instruments reported: {total}")

        for item in items:
            row = _parse_search_item(item)
            if args.xetra_only and row["exchange_symbol"] not in ("", "XETR", "XFRA"):
                continue
            all_items.append(row)

        print(f"  offset={offset:5d}  fetched so far: {len(all_items):,}", flush=True)

        if not items or len(items) < SEARCH_BATCH:
            break
        offset += SEARCH_BATCH
        if args.limit and len(all_items) >= args.limit:
            all_items = all_items[:args.limit]
            break
        time.sleep(RATE_DELAY)

    print(f"\n  Collected {len(all_items):,} instruments")

    # Save instrument list
    if all_items:
        fields = list(all_items[0].keys())
        with open(OUT_INSTR, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(all_items)
        print(f"  Saved: {OUT_INSTR.name}")

    # ── Step 2 (optional): Fetch per-ISIN master data ─────────────────────────
    if args.details and all_items:
        print(f"\n[Step 2] Fetching master data for {len(all_items):,} ISINs...")
        detail_rows: list[dict] = []
        errors = 0

        for i, item in enumerate(all_items):
            isin = item["isin"]
            if not isin:
                continue
            try:
                md = equity_master_data(session, salt, isin)
                row = _parse_master(md)
                detail_rows.append(row)
            except requests.HTTPError as e:
                errors += 1
                if errors <= 5:
                    print(f"  HTTP {e.response.status_code} for {isin}")
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  Error for {isin}: {e}")

            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(all_items)} done, {errors} errors", flush=True)
            time.sleep(RATE_DELAY)

        if detail_rows:
            fields = list(detail_rows[0].keys())
            with open(OUT_DETAIL, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(detail_rows)
            print(f"  Saved: {OUT_DETAIL.name}  ({len(detail_rows):,} rows, {errors} errors)")

    # ── Step 3: Merge with existing DE universe ────────────────────────────────
    universe_file = DATA / "validated_universe_flat.csv"
    if not universe_file.exists():
        universe_file = DATA / "global_universe_flat.csv"

    if universe_file.exists() and all_items:
        print(f"\n[Step 3] Merging with {universe_file.name}...")
        # Build lookup: exchange_symbol → instrument row
        lookup_sym: dict[str, dict] = {}
        lookup_isin: dict[str, dict] = {}
        for row in all_items:
            sym = row.get("exchange_symbol", "").strip()
            isin = row.get("isin", "").strip()
            if sym:
                lookup_sym[sym] = row
                # Also without suffix
                for sfx in (".DE", ".F", ".XETR"):
                    lookup_sym[sym.replace(sfx, "")] = row
            if isin:
                lookup_isin[isin] = row

        # If detail rows exist, merge them in
        detail_lookup: dict[str, dict] = {}
        if OUT_DETAIL.exists():
            for row in csv.DictReader(open(OUT_DETAIL)):
                detail_lookup[row["isin"]] = row

        universe_rows = list(csv.DictReader(open(universe_file)))
        de_rows = [r for r in universe_rows if r["market_code"] == "DE"]
        non_de = [r for r in universe_rows if r["market_code"] != "DE"]

        enriched = []
        matched = 0
        for r in de_rows:
            yf_sym = r["yf_symbol"]
            # Try matching by stripping suffix
            ticker_bare = re.sub(r'\.(DE|F|XETR)$', '', yf_sym, flags=re.I)
            match = lookup_sym.get(yf_sym) or lookup_sym.get(ticker_bare)
            new_row = dict(r)
            if match:
                matched += 1
                new_row["isin"]          = match.get("isin", "")
                new_row["wkn"]           = match.get("wkn", "")
                new_row["company_name"]  = match.get("name", "")
                new_row["sector"]        = match.get("sector", "")
                new_row["instrument_type"] = match.get("instrument_type", "")
                new_row["currency"]      = match.get("currency", "")
                new_row["country"]       = match.get("country", "")
                new_row["market_cap_cat"] = match.get("market_cap_cat", "")
                # Merge detail if available
                isin = match.get("isin", "")
                if isin and isin in detail_lookup:
                    d = detail_lookup[isin]
                    new_row["industry"]    = d.get("industry", "")
                    new_row["sub_industry"] = d.get("sub_industry", "")
                    new_row["employees"]   = d.get("employees", "")
                    new_row["website"]     = d.get("website", "")
            enriched.append(new_row)

        # Write enriched DE + unchanged non-DE
        sample_de = enriched[0] if enriched else {}
        all_fields = list(sample_de.keys()) if sample_de else ["market_code","market_name","exchange","yf_symbol"]
        base_fields = ["market_code","market_name","exchange","yf_symbol"]
        extra_fields = [f for f in all_fields if f not in base_fields]

        with open(OUT_MERGED, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=base_fields + extra_fields, extrasaction="ignore")
            w.writeheader()
            for r in non_de:
                w.writerow({k: r.get(k, "") for k in base_fields + extra_fields})
            for r in enriched:
                w.writerow({k: r.get(k, "") for k in base_fields + extra_fields})

        print(f"  DE tickers: {len(de_rows):,}, matched: {matched:,} ({100*matched/max(1,len(de_rows)):.1f}%)")
        print(f"  Saved: {OUT_MERGED.name}  ({len(universe_rows):,} total rows)")

    print(f"""
═══════════════════════════════════════════════════════
 DONE
 Instruments collected : {len(all_items):,}
 Saved to              : {OUT_INSTR}
{'                  Details : ' + str(OUT_DETAIL) if args.details else ''}
 Merged universe       : {OUT_MERGED}
═══════════════════════════════════════════════════════
""")


if __name__ == "__main__":
    main()
