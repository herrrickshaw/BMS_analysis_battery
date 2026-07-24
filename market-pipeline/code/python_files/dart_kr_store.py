#!/usr/bin/env python3
"""
dart_kr_store.py — build the Korea fundamentals store from DART filings.

Bridges dart_fundamentals.piotroski_inputs (official FSS filings, IFRS-tagged)
into market_cache/fundamentals/KR_current.parquet with the same schema the
india/us stores use, so financial_ratios.py picks Korea up as just another
market. Two rows per ticker (current + prior FY) so revenue_growth works.

Shares outstanding come from DART's stockTotqySttus endpoint (the statement
endpoint carries none) — cached like the filings. That unlocks mcap/pe/pb.

Field decisions (logged in CHANGELOG):
  * ebit, free_cash_flow, total_debt are left NULL — DART's single-account
    endpoint has no borrowings/EBIT tag set; mapping total_liabs to debt would
    mislabel provisions+deferred tax as debt and overstate D/E. Better absent
    than wrong. roce/operating_margin/fcf_yield stay NULL for Korea.

Usage:  /usr/bin/python3 dart_kr_store.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import dart_fundamentals as dartf

FUND_DIR = Path("/Users/umashankar/market-pipeline/market_cache/fundamentals")
SYMBOL_MASTER = Path("/Users/umashankar/market-pipeline/market_cache/symbol_master.parquet")
OUT = FUND_DIR / "KR_current.parquet"
SHARES_DIR = dartf._CACHE_ROOT / "shares"
SHARES_DIR.mkdir(parents=True, exist_ok=True)


def shares_outstanding(corp_code: str, year: str):
    """Issued common shares from stockTotqySttus, cached like the filings."""
    cache = SHARES_DIR / f"{corp_code}_{year}.json"
    if dartf._fresh(cache, dartf.CACHE_DAYS):
        d = json.loads(cache.read_text())
    else:
        url = f"{dartf.BASE}/stockTotqySttus.json?" + urllib.parse.urlencode({
            "crtfc_key": dartf._key(), "corp_code": corp_code,
            "bsns_year": year, "reprt_code": dartf.REPRT_ANNUAL})
        try:
            d = json.loads(dartf._get(url))
        except Exception:
            return None
        cache.write_text(json.dumps(d))
        time.sleep(dartf.SLEEP)
    if d.get("status") != "000":
        return None
    for row in d.get("list", []):
        if row.get("se", "").strip() in ("보통주", "합계"):  # common shares / total
            v = str(row.get("istc_totqy", "")).replace(",", "")
            if v.lstrip("-").isdigit() and int(v) > 0:
                return int(v)
    return None


def store_rows(yf_ticker: str, code: str):
    d = dartf.piotroski_inputs(code)
    if not d:
        return []
    year = int(d["year"])
    sh = shares_outstanding(d["corp_code"], d["year"])
    rows = []
    for suf, fy in (("_1", year - 1), ("_0", year)):
        if d.get(f"total_assets{suf}") is None and d.get(f"revenue{suf}") is None:
            continue
        rows.append({
            "ticker": yf_ticker,
            "fy_end": f"{fy}-12-31",
            "shares": float(sh) if (sh and suf == "_0") else None,
            "stockholders_equity": d.get(f"equity{suf}"),
            "net_income": d.get(f"net_income{suf}"),
            "revenue": d.get(f"revenue{suf}"),
            "total_assets": d.get(f"total_assets{suf}"),
            "gross_profit": d.get(f"gross_profit{suf}"),
            "cfo": d.get(f"operating_cf{suf}"),
            "current_assets": d.get(f"current_assets{suf}"),
            "current_liabilities": d.get(f"current_liabs{suf}"),
            "ebit": None, "free_cash_flow": None, "total_debt": None,
            "long_term_debt": None,
            "source": "dart",
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    sm = pd.read_parquet(SYMBOL_MASTER)
    kr = sm[sm["exchange"].isin(["KOSPI", "KOSDAQ"])][["symbol", "yf_symbol"]]
    cmap = dartf.corp_map()
    todo = []
    for _, r in kr.iterrows():
        code = str(r["symbol"]).split(".")[0].zfill(6)
        if code in cmap:
            todo.append((r["yf_symbol"] or r["symbol"], code))
    if args.limit:
        todo = todo[:args.limit]
    print(f"KR universe {len(kr)}, in DART corp_map: {len(todo)}")

    all_rows, misses = [], 0
    t0 = time.time()
    for i, (yft, code) in enumerate(todo):
        try:
            rows = store_rows(yft, code)
        except Exception as e:
            print(f"  ERR {yft}: {e}", file=sys.stderr)
            rows = []
        if rows:
            all_rows += rows
        else:
            misses += 1
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(todo)}] rows={len(all_rows)} "
                  f"no_filing={misses} {(time.time()-t0)/60:.1f}m", flush=True)

    df = pd.DataFrame(all_rows)
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    tmp.replace(OUT)
    with_shares = df[df["shares"].notna()]["ticker"].nunique() if not df.empty else 0
    print(f"wrote {OUT}: {len(df)} rows, {df['ticker'].nunique() if not df.empty else 0} "
          f"tickers ({with_shares} with shares), no_filing={misses}")


if __name__ == "__main__":
    main()
