#!/usr/bin/env python3
# warehouse_catalog.py
# ====================
# Classify every dataset on this machine by TYPE, MARKET and AUTHORITY, so the
# question "which file should I actually read for X?" has one answer.
#
# WHY THIS EXISTS
# ───────────────
# The data is spread over ~7.3 GB in eight trees with no stated hierarchy, and
# that ambiguity has produced real, costly errors — every one of these was a
# wrong file being read, not a wrong algorithm:
#
#   * Two US price panels. `global-market-data/ltm/US.parquet` is an interrupted
#     alphabetical collection; `global-stock-screener/ltm/US.parquet` has 9,278
#     symbols. A whole day's results ran on the truncated one.
#   * Two India price sources with 100x different depth. The bhavcopy LMDB holds
#     ~36 bars (a rolling window for the daily scan); the LFS ltm panel holds
#     10.5 years. A 3-year return computed from the LMDB silently reports a
#     36-day move.
#   * ~/Downloads is a near-exact stale DUPLICATE of ~/market-pipeline (7,656 vs
#     7,657 OHLC files). It is also TCC-blocked from launchd, so reading it from
#     a scheduled job fails outright — which is how the US scan died.
#   * screener.in keys some India tickers by numeric BSE code, the price panels
#     by NSE symbol. 270 of 428 tickers silently dropped out of a return join.
#
# AUTHORITY is therefore the point of this catalog, not inventory. For each
# (type, market) it names ONE canonical file and marks the rest as duplicate,
# stale, or narrower — with the measured reason.
#
#   warehouse_catalog.py                 # full catalog
#   warehouse_catalog.py --type prices
#   warehouse_catalog.py --canonical     # just the one-file-per-purpose answer
#   warehouse_catalog.py --json

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

HOME = Path.home()
PIPE = HOME / "market-pipeline" / "code" / "python_files"
GSS = HOME / "repos" / "global-stock-screener"
GMD = HOME / "repos" / "global-market-data"

# Data TYPES. The distinction that matters is what question each answers —
# mixing them is how a fundamentals gap gets mistaken for a price gap.
TYPES = {
    "prices": "OHLC time series — the input to any return calculation",
    "fundamentals": "filed financial statements — the input to quality factors",
    "events": "dated corporate events (earnings announcements) — the input to PEAD",
    "signals": "screener output — what a scan decided on a given day",
    "reference": "identity and mapping — tickers, names, sectors, universes",
    "results": "backtest and analysis output — conclusions, not inputs",
}


@dataclass
class Entry:
    path: Path
    dtype: str
    market: str
    role: str          # canonical | duplicate | stale | narrower | unknown
    note: str = ""
    _size: Optional[int] = field(default=None, repr=False)

    def exists(self) -> bool:
        return self.path.exists()

    def size_mb(self) -> float:
        if not self.exists():
            return 0.0
        if self.path.is_file():
            return self.path.stat().st_size / 1e6
        tot = 0
        for r, _, fs in os.walk(self.path):
            for f in fs:
                try:
                    tot += (Path(r) / f).stat().st_size
                except OSError:
                    pass
        return tot / 1e6

    def n_files(self) -> int:
        if not self.exists():
            return 0
        if self.path.is_file():
            return 1
        return sum(len(fs) for _, _, fs in os.walk(self.path))


CATALOG: List[Entry] = [
    # ── PRICES ────────────────────────────────────────────────────────────────
    Entry(GMD / "cache_seed/ltm/IN.parquet", "prices", "IN", "canonical",
          "3,476 syms, 2016-01→2026-07 (10.5y). THE India price source for any "
          "horizon beyond ~1 month."),
    Entry(GSS / "cache_seed/ltm/US.parquet", "prices", "US", "canonical",
          "9,278 syms, 10y. Use THIS, not global-market-data/ltm/US.parquet."),
    Entry(GMD / "cache_seed/ltm/US.parquet", "prices", "US", "narrower",
          "🔴 INTERRUPTED alphabetical collection — CME/CMI absent, coverage "
          "skewed to early letters. A day of results once ran on this by mistake."),
    Entry(HOME / "market-pipeline/market_cache/ohlc", "prices", "US", "canonical",
          "7,657 per-ticker parquets, ~5.1y each. The daily scan's working store; "
          "shallower than the LFS panel, so prefer ltm/US.parquet past 5y."),
    Entry(HOME / "market-pipeline/data/bhavcopy_cache/ohlcv.lmdb", "prices", "IN", "narrower",
          "🔴 ~36 bars per symbol — a ROLLING WINDOW for the daily scan, not "
          "history. Anything past ~1 month must use the LFS panel."),
    Entry(HOME / "Downloads/market_cache/ohlc", "prices", "US", "duplicate",
          "🔴 stale copy of market-pipeline/market_cache/ohlc (7,656 vs 7,657 "
          "files) AND TCC-blocked from launchd. Reading it from a scheduled job "
          "raises PermissionError — this is what killed the US scan on 07-20."),

    # ── FUNDAMENTALS ──────────────────────────────────────────────────────────
    Entry(GSS / "cache_seed/fundamentals_history/IN.parquet", "fundamentals", "IN", "canonical",
          "screener.in annual statements. total_assets was UNMAPPED until "
          "2026-07-21 (row labelled 'Total'); re-collection in progress."),
    Entry(GSS / "cache_seed/fundamentals_history/IN_nse_results.parquet", "fundamentals", "IN", "narrower",
          "NSE results-comparison. REAL filing dates (variable 24-60d lag) but "
          "QUARTERLY INCOME STATEMENT ONLY — no balance sheet, no cash flow."),
    Entry(PIPE / "cache_seed/factorial_symbol_year_table_us.parquet", "fundamentals", "US", "canonical",
          "68,003 symbol-years, 7,164 tickers, 18y, WITH forward returns. "
          "The one panel that has answered a factor question."),
    Entry(PIPE / "cache_seed/factorial_symbol_year_table_IN_full.parquet", "fundamentals", "IN", "stale",
          "🔴 fundamental flags NEVER POPULATED — piotroski fires 2 times in "
          "18,719 rows, coffee_can 0. Technical screeners only."),

    # ── EVENTS ────────────────────────────────────────────────────────────────
    Entry(PIPE / "cache_seed/earnings_price_dataset/IN.parquet", "events", "IN", "canonical",
          "112,379 announcements, 2,490 tickers, 2005→2026, with 1d/5d/21d "
          "post-event returns. India's STRONGEST dataset — 8x the US equivalent."),
    Entry(PIPE / "cache_seed/earnings_price_dataset/US.parquet", "events", "US", "canonical",
          "14,059 announcements, 924 tickers."),
    Entry(PIPE / "cache_seed/earnings_dates_cache", "events", "ALL", "canonical",
          "announcement dates per market, from exchange filings (NSE/BSE/SEC 8-K/DART)."),

    # ── REFERENCE ─────────────────────────────────────────────────────────────
    Entry(HOME / "market-pipeline/market_cache/symbol_master.parquet", "reference", "ALL", "canonical",
          "21,825 rows: ticker ↔ name ↔ exchange ↔ yf suffix, 8 markets. "
          "🔴 holds NO numeric BSE codes — the BSE↔NSE bridge needs the xlsx."),
    Entry(HOME / "Library/Mobile Documents/com~apple~CloudDocs/Desktop/xlsx/Stock_List_NSE_BSE_1.xlsx",
          "reference", "IN", "canonical",
          "299 BSE-code → NSE-symbol pairs + ISIN. The ONLY bridge for the "
          "numeric BSE codes screener.in returns."),

    # ── SIGNALS ───────────────────────────────────────────────────────────────
    Entry(PIPE / "indian_full_scan", "signals", "IN", "canonical", "daily scan workbooks"),
    Entry(PIPE / "us_full_scan", "signals", "US", "canonical", "daily scan workbooks"),
    Entry(PIPE / "korea_scan", "signals", "KR", "canonical", "daily scan workbooks"),
    Entry(PIPE / "japan_scan", "signals", "JP", "canonical", "daily scan workbooks"),
    Entry(PIPE / "european_scan", "signals", "EU", "canonical", "daily scan workbooks"),

    # ── RESULTS ───────────────────────────────────────────────────────────────
    Entry(PIPE / "reports", "results", "ALL", "canonical", "analysis output"),
    Entry(PIPE / "cache_seed/india_factor_panel.parquet", "results", "IN", "stale",
          "🔴 built before the total_assets fix — piotroski=0 on all 3,405 rows. "
          "Rebuild after the current collection."),

    # ── STALE TREE ────────────────────────────────────────────────────────────
    Entry(HOME / "Downloads/data", "duplicate", "ALL", "duplicate",
          "🔴 ~2.5 GB stale mirror of market-pipeline/data. TCC-blocked from "
          "launchd. Kept only as an informal backup."),
]


def render(dtype: Optional[str], canonical_only: bool, as_json: bool) -> int:
    rows = [e for e in CATALOG
            if (not dtype or e.dtype == dtype)
            and (not canonical_only or e.role == "canonical")]
    if as_json:
        print(json.dumps([{
            "path": str(e.path), "type": e.dtype, "market": e.market,
            "role": e.role, "exists": e.exists(), "size_mb": round(e.size_mb(), 1),
            "files": e.n_files(), "note": e.note} for e in rows], indent=2))
        return 0

    print("=" * 96)
    print("  DATA WAREHOUSE CATALOG" + (f" — {dtype}" if dtype else ""))
    print("=" * 96)
    for t, desc in TYPES.items():
        sub = [e for e in rows if e.dtype == t]
        if not sub:
            continue
        print(f"\n  ▌{t.upper()} — {desc}")
        for e in sorted(sub, key=lambda x: (x.role != "canonical", x.market)):
            mark = {"canonical": "✅", "duplicate": "🔁", "stale": "⚠️ ",
                    "narrower": "◐", "unknown": "? "}.get(e.role, "  ")
            miss = "" if e.exists() else "  [MISSING]"
            print(f"    {mark} {e.market:<4} {e.size_mb():>8.1f}MB {e.n_files():>6} files  "
                  f"{str(e.path).replace(str(HOME), '~')}{miss}")
            if e.note:
                for line in _wrap(e.note, 84):
                    print(f"           {line}")
    dup = [e for e in CATALOG if e.role == "duplicate" and e.exists()]
    if dup and not dtype:
        tot = sum(e.size_mb() for e in dup)
        print(f"\n  ── reclaimable: {tot/1000:.1f} GB in {len(dup)} duplicate tree(s) ──")
        print("     Not deleted here. ~/Downloads is periodically wiped by another")
        print("     process, so it doubles as an informal backup — removing it is a")
        print("     judgement call, not a cleanup.")
    return 0


def _wrap(s: str, w: int) -> List[str]:
    out, cur = [], ""
    for word in s.split():
        if len(cur) + len(word) + 1 > w:
            out.append(cur); cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        out.append(cur)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Data warehouse catalog by type and authority")
    ap.add_argument("--type", choices=list(TYPES))
    ap.add_argument("--canonical", action="store_true",
                    help="only the one-file-per-purpose answer")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    return render(a.type, a.canonical, a.json)


if __name__ == "__main__":
    sys.exit(main())
