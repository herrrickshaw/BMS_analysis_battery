#!/usr/bin/env python3
"""
us_fundamentals_edgar.py — fill the US fundamentals store off-hours from SEC
EDGAR companyfacts, into the same shape as the India store, so US screeners and
ratios stop depending on throttled per-ticker yfinance calls.

WHY EDGAR AND NOT YFINANCE
--------------------------
The India store (fundamentals_offhours.py) uses yfinance because India has no
free official filings API. The US does: data.sec.gov serves every XBRL fact a
company ever filed, keyed by CIK, with FILING DATES — official, dated, and
rate-limited at a documented 10 req/s rather than an opaque throttle that
truncates alphabetically. One pass over ~7k tickers takes ~35 min at the polite
default rate; after that a run only refetches names >FRESH_DAYS stale.

STORE SHAPE = IN_current.parquet EXACTLY (ticker, fy_end, source, <fields>,
collected_at) so every consumer that reads the India store can read
US_current.parquet unchanged. Values are as-filed USD; India's are INR — the
ratio layer (financial_ratios.py) never mixes currencies across markets.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
* No fuzzy tag matching. Each field lists exact us-gaap tags in priority order
  (first present wins, same discipline as YF_MAP). A company using none of the
  listed tags gets NaN — visible in coverage — rather than a silently wrong row.
* Quarterly/TTM: companyfacts carries it, but the India quarterly store is
  revenue+NI only and nothing consumes a US quarterly yet. Scaffold later if a
  screener needs it.

Usage:
    us_fundamentals_edgar.py                  # full universe, skip fresh names
    us_fundamentals_edgar.py --limit 300      # bounded slice (one off-hours session)
    us_fundamentals_edgar.py --max-age-days 7 # re-collect only names >7d stale
    us_fundamentals_edgar.py --self-test      # offline; verify parsing logic
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent

try:
    import data_registry as _R
    FUND_DIR = _R.FUND_DIR
    BHAV_CACHE = Path(_R.BHAV_CACHE) if hasattr(_R, "BHAV_CACHE") else \
        Path("/Users/umashankar/market-pipeline/data/bhavcopy_cache")
except Exception:
    FUND_DIR = HERE / "cache_seed" / "fundamentals_current"
    BHAV_CACHE = Path("/Users/umashankar/market-pipeline/data/bhavcopy_cache")

STORE = FUND_DIR / "US_current.parquet"
CIK_CACHE = FUND_DIR / "company_tickers.json"
UNIVERSE_PARQUET = BHAV_CACHE / "ohlcv_US.parquet"

# SEC asks for a descriptive UA with contact; anonymous UAs get 403'd.
UA = {"User-Agent": "umashankar market-pipeline umashankartd1991@gmail.com"}
RATE = 0.25           # seconds between requests — well under SEC's 10 req/s cap
CHECKPOINT_EVERY = 50
FRESH_DAYS = 30
N_YEARS = 5           # match the India store: last 5 fiscal years per ticker

# field -> us-gaap tags, priority order, first present wins. Field names are the
# India store's, verbatim — that equality is the whole point of this file.
GAAP_MAP = {
    "net_income":          ["NetIncomeLoss", "ProfitLoss"],
    "revenue":             ["Revenues",
                            "RevenueFromContractWithCustomerExcludingAssessedTax",
                            "RevenueFromContractWithCustomerIncludingAssessedTax",
                            "SalesRevenueNet"],
    "cfo":                 ["NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "total_assets":        ["Assets"],
    "long_term_debt":      ["LongTermDebtNoncurrent", "LongTermDebt"],
    "current_assets":      ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "gross_profit":        ["GrossProfit"],
    "stockholders_equity": ["StockholdersEquity",
                            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "ebit":                ["OperatingIncomeLoss"],
    "capex":               ["PaymentsToAcquirePropertyPlantAndEquipment",
                            "PaymentsToAcquireProductiveAssets"],
    "total_debt":          ["DebtLongtermAndShorttermCombinedAmount",
                            "LongTermDebt", "LongTermDebtNoncurrent"],
    "cash":                ["CashAndCashEquivalentsAtCarryingValue",
                            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
}
# balance-sheet tags are instants (end only); flows must span ~a fiscal year,
# or the comparative quarterly rows inside a 10-K leak in as annual figures.
INSTANT = {"total_assets", "long_term_debt", "current_assets",
           "current_liabilities", "stockholders_equity", "total_debt", "cash"}
ANNUAL_DAYS = (330, 380)


def _hash_order(syms):
    """Same rationale as the India collector: a run killed early must leave a
    representative sample, not an alphabetical prefix."""
    return sorted(set(syms), key=lambda s: hashlib.md5(str(s).encode()).hexdigest())


# ── ticker -> CIK ─────────────────────────────────────────────────────────────
def load_cik_map(refresh_days: int = 7) -> dict:
    """company_tickers.json, cached; SEC regenerates it daily."""
    if CIK_CACHE.exists():
        age = (time.time() - CIK_CACHE.stat().st_mtime) / 86400
        if age < refresh_days:
            raw = json.loads(CIK_CACHE.read_text())
            return {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers=UA, timeout=30)
    r.raise_for_status()
    CIK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CIK_CACHE.write_text(r.text)
    raw = r.json()
    return {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}


# ── companyfacts parsing ──────────────────────────────────────────────────────
def _annual_series(fact_units: dict, instant: bool) -> dict:
    """{fy_end_date: value} from one tag's unit list, FY figures only,
    deduped by period end keeping the LATEST filing (10-Ks restate prior
    years as comparatives; the most recent filing is the corrected one)."""
    rows = []
    for unit, entries in fact_units.items():
        if unit not in ("USD", "shares"):
            continue
        for e in entries:
            form = e.get("form", "")
            if not (form.startswith("10-K") or form.startswith("20-F")
                    or form.startswith("40-F")):
                continue
            end = e.get("end")
            if not end:
                continue
            if not instant:
                start = e.get("start")
                if not start:
                    continue
                span = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
                if not (ANNUAL_DAYS[0] <= span <= ANNUAL_DAYS[1]):
                    continue
            rows.append((end, e.get("filed", ""), e.get("val")))
    out = {}
    for end, filed, val in sorted(rows, key=lambda r: (r[0], r[1])):
        out[end] = val          # later (higher `filed`) overwrites earlier
    return out


def parse_companyfacts(doc: dict) -> list[dict]:
    """companyfacts JSON -> list of per-FY rows in the India-store shape."""
    gaap = doc.get("facts", {}).get("us-gaap", {})
    dei = doc.get("facts", {}).get("dei", {})
    per_field: dict[str, dict] = {}
    for field, tags in GAAP_MAP.items():
        for tag in tags:
            if tag in gaap:
                s = _annual_series(gaap[tag]["units"], field in INSTANT)
                if s:
                    per_field[field] = s
                    break
    # shares: dei instant, take the value nearest each fiscal year end
    shares_series = {}
    for tag in ("EntityCommonStockSharesOutstanding",):
        if tag in dei:
            for e in dei[tag]["units"].get("shares", []):
                if e.get("end"):
                    shares_series[e["end"]] = e.get("val")

    # Future-dated instants are debt MATURITY schedules, not fiscal years —
    # PMTV reported LongTermDebt repayments due 2026-2029 as instants with
    # future `end` dates, which minted phantom FY rows. A fiscal year that
    # hasn't ended yet cannot have been filed.
    today = dt.date.today().isoformat()
    ends = sorted({e for s in per_field.values() for e in s if e <= today})[-N_YEARS:]
    rows = []
    for end in ends:
        row = {"fy_end": end, "source": "edgar"}
        for field in GAAP_MAP:
            row[field] = per_field.get(field, {}).get(end)
        # capex is reported as cash PAID (positive); store it negative to match
        # the yfinance convention the India store uses, and derive FCF the same
        # way the scan would: cfo + capex.
        if row.get("capex") is not None:
            row["capex"] = -abs(row["capex"])
        cfo, capex = row.get("cfo"), row.get("capex")
        row["free_cash_flow"] = (cfo + capex) if (cfo is not None and capex is not None) else None
        if shares_series:
            near = min(shares_series, key=lambda d: abs(
                dt.date.fromisoformat(d) - dt.date.fromisoformat(end)))
            row["shares"] = shares_series[near]
        else:
            row["shares"] = None
        rows.append(row)
    return rows


def fetch_companyfacts(cik: int, session: requests.Session) -> dict | None:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    r = session.get(url, headers=UA, timeout=30)
    if r.status_code == 404:        # no XBRL facts (funds, some ADRs) — real answer
        return None
    r.raise_for_status()
    return r.json()


# ── store I/O (same atomic pattern as the India collector) ────────────────────
def load_store() -> pd.DataFrame:
    return pd.read_parquet(STORE) if STORE.exists() else pd.DataFrame()


def save_store(store: pd.DataFrame, new_rows: list, collected_at: str) -> pd.DataFrame:
    if not new_rows:
        return store
    nd = pd.DataFrame(new_rows)
    nd["collected_at"] = collected_at
    if not store.empty:
        store = store[~store["ticker"].astype(str).str.upper().isin(
            nd["ticker"].astype(str).str.upper())]
    merged = pd.concat([store, nd], ignore_index=True)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    if STORE.exists():
        shutil.copy2(STORE, STORE.with_suffix(".parquet.bak"))
    tmp = STORE.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    tmp.replace(STORE)
    return merged


def universe() -> list[str]:
    import duckdb  # only needed here; the venv runner may lack it — fall back
    try:
        con = duckdb.connect()
        syms = [r[0] for r in con.execute(
            f"SELECT DISTINCT Symbol FROM read_parquet('{UNIVERSE_PARQUET}')").fetchall()]
        return [s for s in syms if s]
    except Exception:
        pass
    return []


def _universe_fallback() -> list[str]:
    """pandas fallback when duckdb isn't importable in this interpreter."""
    df = pd.read_parquet(UNIVERSE_PARQUET, columns=["Symbol"])
    return sorted(df["Symbol"].dropna().unique().tolist())


def coverage(store: pd.DataFrame) -> None:
    if store.empty:
        print("  store empty"); return
    import collections
    usable = store.dropna(subset=["cfo", "total_assets"])
    tick = sorted(usable["ticker"].astype(str).str.upper().unique())
    c = collections.Counter(t[0] for t in tick if t)
    a_share = c.get("A", 0) / len(tick) * 100 if tick else 0
    print(f"  usable tickers (cfo+total_assets): {len(tick)}")
    print(f"  A-share: {a_share:.1f}%  letters: {dict(sorted(c.items()))}")


# ── self test (offline) ───────────────────────────────────────────────────────
def self_test() -> int:
    doc = {"facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [
            # comparative restated year: later filing must win
            {"start": "2023-01-01", "end": "2023-12-31", "val": 100, "form": "10-K", "filed": "2024-02-01"},
            {"start": "2023-01-01", "end": "2023-12-31", "val": 101, "form": "10-K", "filed": "2025-02-01"},
            {"start": "2024-01-01", "end": "2024-12-31", "val": 200, "form": "10-K", "filed": "2025-02-01"},
            # quarterly row inside the 10-K: must be excluded by span filter
            {"start": "2024-10-01", "end": "2024-12-31", "val": 999, "form": "10-K", "filed": "2025-02-01"},
        ]}},
        "Assets": {"units": {"USD": [
            {"end": "2023-12-31", "val": 1000, "form": "10-K", "filed": "2024-02-01"},
            {"end": "2024-12-31", "val": 1100, "form": "10-K", "filed": "2025-02-01"},
        ]}},
        # debt maturity schedule: future-dated instants must NOT mint FY rows
        "LongTermDebtNoncurrent": {"units": {"USD": [
            {"end": "2029-12-31", "val": 555, "form": "10-K", "filed": "2025-02-01"},
        ]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            {"start": "2024-01-01", "end": "2024-12-31", "val": 300, "form": "10-K", "filed": "2025-02-01"},
        ]}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
            {"start": "2024-01-01", "end": "2024-12-31", "val": 50, "form": "10-K", "filed": "2025-02-01"},
        ]}},
    }, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": "2025-01-15", "val": 10}]}}}}}
    rows = parse_companyfacts(doc)
    by_end = {r["fy_end"]: r for r in rows}
    assert by_end["2023-12-31"]["net_income"] == 101, "latest filing must win restatements"
    assert by_end["2024-12-31"]["net_income"] == 200
    assert all(r["net_income"] != 999 for r in rows), "quarterly span must be excluded"
    assert by_end["2024-12-31"]["capex"] == -50, "capex stored negative (yfinance convention)"
    assert by_end["2024-12-31"]["free_cash_flow"] == 250
    assert by_end["2024-12-31"]["shares"] == 10
    assert by_end["2024-12-31"]["total_assets"] == 1100
    assert "2029-12-31" not in by_end, "future maturity dates must not mint FY rows"
    print("self-test OK")
    return 0


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max tickers this run (0 = all)")
    ap.add_argument("--rate", type=float, default=RATE)
    ap.add_argument("--max-age-days", type=int, default=FRESH_DAYS)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    try:
        syms = universe() or _universe_fallback()
    except Exception as e:
        print(f"cannot load universe from {UNIVERSE_PARQUET}: {e}")
        return 1
    cik_map = load_cik_map()
    store = load_store()

    fresh: set[str] = set()
    if not store.empty and "collected_at" in store.columns:
        cutoff = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(days=a.max_age_days)).isoformat()
        fresh = set(store.loc[store["collected_at"] >= cutoff, "ticker"]
                    .astype(str).str.upper())

    todo = [s for s in _hash_order(syms)
            if s.upper() in cik_map and s.upper() not in fresh]
    no_cik = sum(1 for s in syms if s.upper() not in cik_map)
    if a.limit:
        todo = todo[: a.limit]
    print(f"universe {len(syms)} | no CIK {no_cik} | fresh-skip {len(fresh)} | fetching {len(todo)}")

    sess = requests.Session()
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat()
    pending: list[dict] = []
    done = failed = 0
    for i, sym in enumerate(todo, 1):
        try:
            doc = fetch_companyfacts(cik_map[sym.upper()], sess)
            if doc:
                for row in parse_companyfacts(doc):
                    row["ticker"] = sym
                    pending.append(row)
            done += 1
        except KeyboardInterrupt:
            print("\ninterrupted — checkpointing")
            break
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"  ! {sym}: {str(e)[:60]}")
        if i % CHECKPOINT_EVERY == 0:
            store = save_store(store, pending, collected_at)
            pending = []
            print(f"  {i}/{len(todo)} checkpointed ({len(store):,} store rows)")
        time.sleep(a.rate)

    store = save_store(store, pending, collected_at)
    print(f"done: {done} fetched, {failed} failed, store {len(store):,} rows "
          f"/ {store['ticker'].nunique() if not store.empty else 0} tickers")
    coverage(store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
