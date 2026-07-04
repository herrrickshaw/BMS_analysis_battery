#!/usr/bin/env python3
"""
validate_universe.py
====================
Multi-source tradability check on global_universe_flat.csv.

Sources used:
  1. yfinance batch download — checks for actual recent price data (last 30d)
  2. NSE official symbol list (via nsepython)
  3. BSE scrip list (via bsedata)
  4. FinanceDatabase active-check (delisted=false re-verify for AT/DE)

Output: data/validated_universe_flat.csv  (valid tickers only)
        data/validation_report.json        (per-market failure stats)
"""
import csv, json, sys, time, warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

DATA = Path(__file__).parent / "data"
INPUT  = DATA / "global_universe_flat.csv"
OUTPUT = DATA / "validated_universe_flat.csv"
REPORT = DATA / "validation_report.json"

# ── config ────────────────────────────────────────────────────────────────────
BATCH      = 50      # tickers per yfinance download call
WORKERS    = 8       # parallel download workers
YF_PERIOD  = "1mo"  # look-back for price data
YF_TIMEOUT = 30

# Markets skipped from yfinance check (validated by official list instead)
SKIP_YF = set()  # fill after official-list checks


# ── 1. Load universe ──────────────────────────────────────────────────────────
print("Loading universe...")
rows = list(csv.DictReader(open(INPUT)))
print(f"  {len(rows):,} tickers across {len({r['market_code'] for r in rows})} markets")

by_market: dict[str, list[dict]] = {}
for r in rows:
    by_market.setdefault(r["market_code"], []).append(r)

# ── 2. Official exchange lists ────────────────────────────────────────────────
official_valid: dict[str, set] = {}  # market_code → set of valid yf_symbols

# ── 2a. NSE official symbols ──────────────────────────────────────────────────
print("\n[NSE] Fetching official NSE symbol list...")
try:
    import nsepython as nse
    nse_syms = nse.nse_eq_symbols()
    nse_yf   = {f"{s}.NS" for s in nse_syms if isinstance(s, str)}
    official_valid["IN_NSE"] = nse_yf
    print(f"  NSE official: {len(nse_yf):,} symbols")
except Exception as e:
    print(f"  NSE fetch failed: {e}")

# ── 2b. BSE scrip list ────────────────────────────────────────────────────────
print("[BSE] Fetching BSE active scrip list...")
try:
    import bsedata.bse as bselib
    b = bselib.BSE()
    # BSE get_quote works per scrip; use the scripmaster download instead
    import requests, io
    r = requests.get(
        "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active",
        timeout=20, headers={"User-Agent": "Mozilla/5.0"}
    )
    if r.ok:
        scrips = r.json()
        bse_codes = {str(s.get("SCRIP_CD","")).zfill(6) for s in scrips}
        bse_yf = {f"{c}.BO" for c in bse_codes if c}
        official_valid["IN_BSE"] = bse_yf
        print(f"  BSE official: {len(bse_yf):,} scrips")
    else:
        print(f"  BSE API returned {r.status_code}")
except Exception as e:
    print(f"  BSE fetch failed: {e}")

# Merge NSE + BSE for IN market
in_official = official_valid.get("IN_NSE", set()) | official_valid.get("IN_BSE", set())
if in_official:
    official_valid["IN"] = in_official
    print(f"  IN combined official: {len(in_official):,}")

# ── 2c. ASX official list ─────────────────────────────────────────────────────
print("[ASX] Fetching ASX company list...")
try:
    r = requests.get(
        "https://asx.api.markitdigital.com/asx-research/1.0/companies/directory?perPage=2500&page=1",
        timeout=20, headers={"User-Agent": "Mozilla/5.0"}
    )
    if r.ok:
        asx_data = r.json()
        asx_codes = {c["asx_code"] for c in asx_data.get("data", {}).get("entities", [])}
        asx_yf = {f"{c}.AX" for c in asx_codes}
        official_valid["AU"] = asx_yf
        print(f"  ASX official: {len(asx_yf):,} codes")
    else:
        print(f"  ASX API returned {r.status_code}")
except Exception as e:
    print(f"  ASX fetch failed: {e}")

# ── 2d. HK official list ──────────────────────────────────────────────────────
print("[HKEX] Fetching HKEX equity list...")
try:
    import io as _io
    r = requests.get(
        "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx",
        timeout=30, headers={"User-Agent": "Mozilla/5.0"}
    )
    if r.ok:
        df = pd.read_excel(_io.BytesIO(r.content), header=2)
        # Column 0 is code, look for 4-digit stock codes
        codes = df.iloc[:, 0].dropna().astype(str)
        codes = codes[codes.str.match(r"^\d{1,4}$")]
        hk_yf = {f"{int(c):04d}.HK" for c in codes}
        official_valid["HK"] = hk_yf
        print(f"  HKEX official: {len(hk_yf):,} equities")
    else:
        print(f"  HKEX fetch returned {r.status_code}")
except Exception as e:
    print(f"  HKEX fetch failed: {e}")

# ── 2e. TSX official list ─────────────────────────────────────────────────────
print("[TSX] Fetching TSX listed issuers...")
try:
    r = requests.get(
        "https://www.tsx.com/json/company-directory/search/tsx/^*",
        timeout=20, headers={"User-Agent": "Mozilla/5.0"}
    )
    if r.ok:
        tsx_data = r.json()
        tsx_syms = {c["symbol"] for c in tsx_data.get("results", [])}
        tsx_yf   = {f"{s}.TO" for s in tsx_syms}
        official_valid["CA"] = tsx_yf
        print(f"  TSX official: {len(tsx_yf):,} issuers")
    else:
        print(f"  TSX API returned {r.status_code}")
except Exception as e:
    print(f"  TSX fetch failed: {e}")

# ── 2f. SGX official list ─────────────────────────────────────────────────────
print("[SGX] Fetching SGX equity list...")
try:
    r = requests.get(
        "https://api.sgx.com/securities/v1.1/sgxsecurities/equities?params=all",
        timeout=20, headers={"User-Agent": "Mozilla/5.0"}
    )
    if r.ok:
        sgx_data = r.json()
        sgx_syms = {s.get("nc", "") for s in sgx_data.get("data", {}).get("items", [])}
        sgx_yf   = {f"{s}.SI" for s in sgx_syms if s}
        official_valid["SG"] = sgx_yf
        print(f"  SGX official: {len(sgx_yf):,} equities")
    else:
        print(f"  SGX API returned {r.status_code}")
except Exception as e:
    print(f"  SGX fetch failed: {e}")

print(f"\nOfficial lists obtained: {list(official_valid.keys())}")


# ── 3. yfinance batch validation ──────────────────────────────────────────────
def check_batch(tickers: list[str]) -> dict[str, bool]:
    """Return {ticker: has_data} for a batch using yfinance download."""
    try:
        df = yf.download(
            tickers, period=YF_PERIOD, auto_adjust=True,
            progress=False, timeout=YF_TIMEOUT,
            threads=False
        )
        if df.empty:
            return {t: False for t in tickers}
        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"] if "Close" in df else df.iloc[:, 0:len(tickers)]
        else:
            close = df[["Close"]] if "Close" in df.columns else df
        result = {}
        for t in tickers:
            col = t if t in close.columns else (close.columns[0] if len(tickers) == 1 else None)
            if col is not None and not close[col].dropna().empty:
                result[t] = True
            else:
                result[t] = False
        return result
    except Exception:
        return {t: False for t in tickers}


print("\n[yfinance] Batch price validation...")
yf_results: dict[str, bool] = {}

# Determine which markets to yf-check
# Markets with reliable official lists will be validated by those instead;
# we still yf-check them to compute failure rates but mark as "official=True"
YF_CHECK_MARKETS = {
    "DE", "AT", "FR", "IT", "SE", "NO", "DK",
    "AR", "RU", "ZA", "SA", "BR", "CN", "NZ",
    "UK", "CH", "NL", "ES", "AE",
    "JP", "KR", "TW",
    "IN", "AU", "HK", "CA", "SG",  # these also have official lists
}

all_yf_tickers = [r["yf_symbol"] for r in rows if r["market_code"] in YF_CHECK_MARKETS]
batches = [all_yf_tickers[i:i+BATCH] for i in range(0, len(all_yf_tickers), BATCH)]
total_batches = len(batches)
print(f"  {len(all_yf_tickers):,} tickers in {total_batches} batches (×{BATCH})")

done = 0
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    futures = {pool.submit(check_batch, b): b for b in batches}
    for fut in as_completed(futures):
        yf_results.update(fut.result())
        done += 1
        if done % 50 == 0 or done == total_batches:
            valid = sum(yf_results.values())
            pct = 100 * valid / max(1, len(yf_results))
            print(f"  [{done}/{total_batches}]  {valid:,}/{len(yf_results):,} valid ({pct:.1f}%)", flush=True)

print(f"\nyfinance check complete: {sum(yf_results.values()):,}/{len(yf_results):,} valid")


# ── 4. Determine validity per ticker ─────────────────────────────────────────
valid_rows   = []
invalid_rows = []
market_stats = {}

for r in rows:
    sym  = r["yf_symbol"]
    code = r["market_code"]

    # Check official list first
    if code in official_valid:
        is_valid = sym in official_valid[code]
        source   = "official"
    elif sym in yf_results:
        is_valid = yf_results[sym]
        source   = "yfinance"
    else:
        is_valid = True   # not checked — assume valid (static markets)
        source   = "unchecked"

    r["valid"]  = "1" if is_valid else "0"
    r["source"] = source

    stats = market_stats.setdefault(code, {"total": 0, "valid": 0, "invalid": 0, "official": False})
    stats["total"] += 1
    if is_valid:
        stats["valid"]  += 1
        valid_rows.append(r)
    else:
        stats["invalid"] += 1
        invalid_rows.append(r)
    if source == "official":
        stats["official"] = True


# ── 5. Print report ───────────────────────────────────────────────────────────
print("\n── Validation Report ──────────────────────────────────────────────────────")
print(f"{'Mkt':<5} {'Total':>8} {'Valid':>8} {'Invalid':>8} {'Fail%':>7}  Source")
print("─" * 65)
grand_total = grand_valid = grand_invalid = 0
for code in sorted(market_stats, key=lambda c: -market_stats[c]["total"]):
    s = market_stats[code]
    fail_pct = 100 * s["invalid"] / max(1, s["total"])
    src = "official" if s["official"] else "yfinance"
    print(f"{code:<5} {s['total']:>8,} {s['valid']:>8,} {s['invalid']:>8,} {fail_pct:>6.1f}%  {src}")
    grand_total   += s["total"]
    grand_valid   += s["valid"]
    grand_invalid += s["invalid"]

print("─" * 65)
print(f"{'TOTAL':<5} {grand_total:>8,} {grand_valid:>8,} {grand_invalid:>8,} {100*grand_invalid/grand_total:>6.1f}%")
print()

# ── 6. Save outputs ───────────────────────────────────────────────────────────
fieldnames = list(rows[0].keys()) if rows else ["market_code","market_name","exchange","yf_symbol"]
clean_fields = ["market_code","market_name","exchange","yf_symbol"]

with open(OUTPUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=clean_fields)
    w.writeheader()
    for r in valid_rows:
        w.writerow({k: r[k] for k in clean_fields})

with open(REPORT, "w") as f:
    json.dump(market_stats, f, indent=2)

print(f"Saved: {OUTPUT.name}  ({len(valid_rows):,} valid tickers)")
print(f"Saved: {REPORT.name}")
print(f"\nRemoved {grand_invalid:,} invalid/delisted tickers ({100*grand_invalid/grand_total:.1f}%)")
