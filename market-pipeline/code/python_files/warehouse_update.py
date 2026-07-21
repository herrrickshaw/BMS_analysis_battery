#!/usr/bin/env python3
"""
warehouse_update.py — fold new bars from the daily stores into the deep panels.

THE PROBLEM THIS REMOVES
------------------------
Two price stores exist per market, with opposite strengths, and NOTHING merged
them:

    LFS ltm panel     10.5y deep   but 8-19 days STALE
    daily store       current      but ~36 bars (IN) / 5.1y (US)

Every analysis then had to pick, and picking wrong was silent. It went wrong
three separate times on 2026-07-21 alone:

  * A 3-year return computed from the India LMDB would have reported a 36-DAY
    move, because the LMDB is a rolling window and looks like a price history.
  * watchlist_pnl read BOTH entry and current price from the LFS panel, so
    anything added in the last 8 days had entry == ltp and printed "+0.0%" —
    which reads as "went nowhere", not "no time has passed".
  * Two US panels exist; one is an interrupted alphabetical collection missing
    CME/CMI, and a day of results ran on it.

The fix is not "remember which store to use". It is to make the deep panel
CURRENT, so there is one answer. History and freshness stop being a trade-off.

DESIGN
------
* APPEND-ONLY on (Symbol, Date). Existing bars are never rewritten — a
  corrected close from a vendor must not silently alter a price a past decision
  was made on. New dates only.
* IDEMPOTENT. Running twice adds nothing the second time.
* VERIFIED BEFORE WRITE. Row count must not fall and the last bar must not move
  backwards, or the write is refused. A merge that loses history is worse than a
  stale panel, because staleness is visible and truncation is not.
* ATOMIC. Writes to a temp file and renames, so an interrupted run cannot leave
  a half-written panel where a 10-year history used to be.

    warehouse_update.py                # update all configured markets
    warehouse_update.py --market IN
    warehouse_update.py --dry-run      # report what would change
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
PANELS = {
    "IN": Path("/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"),
    "US": Path("/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"),
}
COLS = ["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]


def _fresh_us() -> pd.DataFrame:
    """Per-ticker parquets from market_cache -> long frame."""
    try:
        import data_registry as R
    except Exception:
        return pd.DataFrame()
    out = []
    for f in R.OHLC_DIR.glob("*.parquet"):
        try:
            d = pd.read_parquet(f)
        except Exception:
            continue
        if d.empty or "Close" not in d.columns:
            continue
        d = d.reset_index()
        dcol = next((c for c in d.columns if str(c).lower() in ("date", "index")), None)
        if dcol is None:
            continue
        d = d.rename(columns={dcol: "Date"})
        d["Symbol"] = f.stem.upper()
        out.append(d[[c for c in COLS if c in d.columns]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _fresh_in() -> pd.DataFrame:
    """bhavcopy LMDB -> long frame."""
    try:
        import bhavcopy_store as bs
    except Exception:
        return pd.DataFrame()
    out = []
    for sym in bs.symbols():
        try:
            d = bs.get(sym)
        except Exception:
            continue
        if d is None or d.empty or "Close" not in d.columns:
            continue
        d = d.reset_index()
        dcol = next((c for c in d.columns if str(c).lower() in ("date", "index")), None)
        if dcol is None:
            continue
        d = d.rename(columns={dcol: "Date"})
        d["Symbol"] = str(sym).upper()
        out.append(d[[c for c in COLS if c in d.columns]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


FRESH = {"US": _fresh_us, "IN": _fresh_in}


def update(market: str, dry: bool) -> int:
    panel = PANELS.get(market)
    if not panel or not panel.exists():
        print(f"  {market}: no panel at {panel}"); return 1

    old = pd.read_parquet(panel)
    old["Date"] = pd.to_datetime(old["Date"])
    old["Symbol"] = old["Symbol"].astype(str).str.upper()
    last_old = old["Date"].max()
    print(f"  {market} panel: {len(old):,} rows, {old['Symbol'].nunique():,} symbols, "
          f"last bar {last_old.date()}")

    fresh = FRESH[market]()
    if fresh.empty:
        print(f"  {market}: no fresh data available — nothing to do"); return 0
    fresh["Date"] = pd.to_datetime(fresh["Date"])
    fresh["Symbol"] = fresh["Symbol"].astype(str).str.upper()
    print(f"  {market} fresh : {len(fresh):,} rows, {fresh['Symbol'].nunique():,} symbols, "
          f"last bar {fresh['Date'].max().date()}")

    # STRICTLY NEWER DATES ONLY. Re-importing an overlapping date would let a
    # vendor's revised close overwrite the price a past decision was recorded
    # against, silently changing history.
    new = fresh[fresh["Date"] > last_old].copy()
    if new.empty:
        print(f"  {market}: already current — 0 new bars"); return 0

    for c in COLS:
        if c not in new.columns:
            new[c] = pd.NA
    new = new[COLS]
    # Match the panel's dtypes so the concat does not silently widen float32 to
    # float64 and double the file.
    for c in ("Open", "High", "Low", "Close"):
        if c in old.columns:
            new[c] = new[c].astype(old[c].dtype, errors="ignore")

    merged = pd.concat([old[COLS], new], ignore_index=True)
    merged = merged.drop_duplicates(subset=["Symbol", "Date"], keep="first")
    merged = merged.sort_values(["Symbol", "Date"]).reset_index(drop=True)

    added = len(merged) - len(old)
    print(f"  {market}: +{added:,} bars across {new['Symbol'].nunique():,} symbols "
          f"({last_old.date()} -> {merged['Date'].max().date()})")

    # ── refuse a write that loses anything ────────────────────────────────────
    if len(merged) < len(old):
        print(f"  ❌ {market}: merge LOST rows ({len(old):,} -> {len(merged):,}) — refusing")
        return 1
    if merged["Date"].max() < last_old:
        print(f"  ❌ {market}: last bar moved BACKWARDS — refusing"); return 1
    lost = set(old["Symbol"]) - set(merged["Symbol"])
    if lost:
        print(f"  ❌ {market}: {len(lost)} symbols vanished — refusing"); return 1

    if dry:
        print(f"  {market}: dry-run, not written"); return 0

    bak = panel.with_suffix(".parquet.bak")
    shutil.copy2(panel, bak)
    tmp = panel.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    tmp.replace(panel)          # atomic; a crash cannot leave a partial panel
    print(f"  ✅ {market}: written ({len(merged):,} rows)  backup -> {bak.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fold fresh bars into the deep panels")
    ap.add_argument("--market", choices=list(PANELS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rc = 0
    for m in ([a.market] if a.market else list(PANELS)):
        rc |= update(m, a.dry_run)
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
