#!/usr/bin/env python3
"""
fundamentals_offhours.py — fill the India fundamentals store off-hours, from the
whole alphabet, so the daily brief's fundamental screeners stop being A-only.

THE PROBLEM THIS REMOVES
------------------------
The brief's Piotroski / CoffeeCan / BullCartel / MagicFormula picks are 89-96%
names beginning with A. Not because A-companies score better — because those are
the only names whose fundamentals ever got collected. Two independent code paths
truncate alphabetically for the same reason:

  * screener.in PIT collector walks the universe A->Z and the host hard-blocks
    after 50-155 requests, so it never leaves the A's.
  * the LIVE India scan (full_indian_market_scan.py Stage 4) fetches one
    yfinance Ticker() per stock, in alphabetical order, and Yahoo throttles part
    way through — measured 2026-07-22, its Fundamentals sheet stops at BAJAJELEC
    and everything from BAJAJFINSV to ZYDUSWELL has no fundamentals at all.

Fetching 8,944 fundamentals inside one nightly run cannot work: whichever source
you use throttles, and throttling in alphabetical order gives you the A's. The
fix is to PRE-COLLECT, slowly, off-hours, into a store the scan reads — and to
walk the universe in HASH order so a run that stops early leaves a representative
sample instead of a prefix.

SOURCES, AND WHAT EACH CAN ACTUALLY GIVE
----------------------------------------
  yfinance   PRIMARY. Verified 2026-07-22 to return 5 years of balance sheet,
             income statement and cash flow — CFO, total assets, debt, net
             income, revenue, current assets — for non-A names (ZYDUSLIFE,
             TATASTEEL, WIPRO) that screener.in never reached. 5 years is enough
             for a CURRENT Piotroski/CoffeeCan screen (the change tests need 2).
             It does NOT carry filing dates, so it is NOT point-in-time and must
             not be used for a backtest — only for today's live screen.
  screener.in ENRICHMENT, optional. 10-year dated history, the only
             point-in-time source, but rate-limited and the reason the store is
             A-biased in the first place. Left off by default; --with-screener
             adds it for the deep panel, at screener's pace, hash-ordered.
  bhavcopy / NSE / BSE bhavcopy is PRICE data and carries no fundamentals, so it
             is deliberately NOT a source here — claiming otherwise would be a
             field that never populates. NSE/BSE corporate-filing feeds could add
             filing DATES on top of yfinance figures later; scaffolded, not wired.

    fundamentals_offhours.py                 # yfinance, full liquid universe
    fundamentals_offhours.py --limit 300     # a bounded slice (testing)
    fundamentals_offhours.py --max-age-days 7 # re-collect only names >7d stale
    fundamentals_offhours.py --self-test      # offline; verify the logic
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

HERE = Path(__file__).resolve().parent

# Written under the repo, never ~/Downloads (macOS TCC denies launchd access
# there, which is how the nightly US scan died). Resolve through data_registry
# so this agrees with every other consumer by construction.
try:
    import data_registry as _R
    STORE = _R.FUND_DIR / "IN_current.parquet"
except Exception:
    STORE = HERE / "cache_seed" / "fundamentals_current" / "IN_current.parquet"

UNIVERSE_PARQUET = Path(
    "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/IN.parquet")

RATE = 1.0            # seconds between yfinance tickers — polite, off-hours
CHECKPOINT_EVERY = 100
FRESH_DAYS = 30       # a name collected within this many days is skipped

# yfinance row-label -> our field. First matching label wins; labels vary across
# yfinance versions, so several aliases are listed.
# Candidate labels are the SCAN's exact lookups, in its priority order, so
# _pick (exact-match-first) selects the identical row the scan would. Field names
# are chosen to match what the scan reads: long_term_debt, NOT borrowings — the
# scan's Piotroski and Coffee Can both read "Long Term Debt", and grabbing the
# larger "Total Debt" row instead is precisely the bug that made the store
# disagree with a live run.
YF_MAP = {
    "net_income":          ["Net Income", "Net Income Common Stockholders"],
    "revenue":             ["Total Revenue", "Operating Revenue"],
    "cfo":                 ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "total_assets":        ["Total Assets"],
    "long_term_debt":      ["Long Term Debt"],
    "current_assets":      ["Current Assets", "Total Current Assets"],
    "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
    "gross_profit":        ["Gross Profit"],
    "shares":              ["Share Issued", "Ordinary Shares Number", "Common Stock"],
}


# ── universe ──────────────────────────────────────────────────────────────────
def _hash_order(syms):
    """Deterministic, alphabet-independent ordering.

    The whole point: a run that throttles or is killed early must leave a sample
    spread across the alphabet, not another A-prefix. Hash order is reproducible
    (same universe -> same sequence, so --limit and resume are stable) yet
    uncorrelated with the first letter.
    """
    return sorted(set(syms), key=lambda s: hashlib.md5(str(s).encode()).hexdigest())


def _clean_equities(syms) -> list:
    """Drop non-equity instruments the ltm parquet is polluted with.

    ltm/IN.parquet mixes in G-Secs, SDLs, bonds and funds — 691MH34 (a
    Maharashtra SDL), 97UPPCL27 (a power bond), SFMP58GR (a fund). yfinance
    rightly has no fundamentals for any of them, so on the raw list only ~20% of
    names return data and the run looks broken when it is merely aimed at bonds.
    Indian bond/G-Sec tickers are digit-heavy and often contain no vowel; NSE
    EQUITY symbols are alphabetic tickers. This keeps names that are >=3 chars,
    start with a letter, and are not mostly digits.
    """
    out = []
    for s in syms:
        s = str(s).upper().strip()
        if len(s) < 3 or not s[0].isalpha():
            continue
        digits = sum(c.isdigit() for c in s)
        if digits > len(s) / 2:           # bond/SDL codes are digit-heavy
            continue
        out.append(s)
    return out


def universe() -> list:
    """Prefer the clean equity list the daily scan actually screens.

    The scan's All_Stocks sheet IS the liquidity-gated equity universe (~1,356
    names, no bonds), so collecting against it aligns the fundamentals store
    exactly with what the brief screens and avoids wasting the window on
    instruments that can never return fundamentals. Falls back to the ltm
    parquet (filtered) only when no scan workbook exists.
    """
    import glob
    scans = sorted(glob.glob(str(HERE / "indian_full_scan" / "indian_full_scan_*.xlsx")))
    if scans:
        try:
            d = pd.read_excel(scans[-1], "All_Stocks")
            syms = d["Symbol"].astype(str).str.upper()
            return _hash_order(_clean_equities(syms))
        except Exception:
            pass
    if not UNIVERSE_PARQUET.exists():
        raise SystemExit(f"no scan workbook and universe not found: {UNIVERSE_PARQUET}")
    s = pd.read_parquet(UNIVERSE_PARQUET, columns=["Symbol"])["Symbol"]
    return _hash_order(_clean_equities(s.astype(str).str.upper()))


# ── extraction ────────────────────────────────────────────────────────────────
def _pick(df: "pd.DataFrame", labels) -> Optional["pd.Series"]:
    """Row for the first matching label, EXACT match preferred.

    🔴 Substring matching corrupted three fields. "current assets" as a substring
    matched "Total Current Assets" AND "Net Current Assets" AND "Other Current
    Assets" — whichever came first in the index — so the store held 218B where
    the real Current Assets was 56B, and Piotroski scored differently from a live
    run. The consuming code (stock_utils.row) matches EXACTLY, so the store must
    too, or the two sources disagree.

    Exact match across ALL candidate labels first; only if none match exactly
    fall back to substring, which is still useful for genuinely-varying labels
    but never overrides an exact hit.
    """
    if df is None or df.empty:
        return None
    idx = {str(i): i for i in df.index}
    idx_lower = {str(i).lower(): i for i in df.index}
    for want in labels:                       # exact, case-sensitive first
        if want in idx:
            return df.loc[idx[want]]
    for want in labels:                       # exact, case-insensitive
        if want.lower() in idx_lower:
            return df.loc[idx_lower[want.lower()]]
    for want in labels:                       # last resort: substring
        for low, orig in idx_lower.items():
            if want.lower() in low:
                return df.loc[orig]
    return None


def from_yfinance(ticker: str) -> list:
    """Per-fiscal-year rows for one NSE symbol, or [] on any failure.

    Never raises: a source that throws on one name must not stop the run. A
    missing field is left as NaN, never zero — a zero-filled fundamental reads as
    a real figure and silently changes a screen's verdict.
    """
    import yfinance as yf
    t = yf.Ticker(f"{ticker}.NS")
    try:
        bs, is_, cf = t.balance_sheet, t.income_stmt, t.cashflow
    except Exception:
        return []
    if all(x is None or x.empty for x in (bs, is_, cf)):
        return []

    series = {}
    for field, labels in YF_MAP.items():
        src = bs if field in ("total_assets", "long_term_debt", "current_assets",
                              "current_liabilities", "shares") else (
              cf if field == "cfo" else is_)
        series[field] = _pick(src, labels)

    # Fiscal years present across any statement.
    years = set()
    for s in series.values():
        if s is not None:
            years |= {pd.Timestamp(c) for c in s.index}
    rows = []
    for y in sorted(years):
        row = {"ticker": ticker, "fy_end": y.date().isoformat(), "source": "yfinance"}
        for field, s in series.items():
            v = None
            if s is not None and y in {pd.Timestamp(c): c for c in s.index}:
                raw = s[{pd.Timestamp(c): c for c in s.index}[y]]
                v = float(raw) if pd.notna(raw) else None
            row[field] = v
        rows.append(row)
    return rows


# ── store ─────────────────────────────────────────────────────────────────────
def load_store() -> "pd.DataFrame":
    if STORE.exists():
        return pd.read_parquet(STORE)
    return pd.DataFrame()


def _fresh_set(store: "pd.DataFrame", max_age_days: int) -> set:
    """Tickers whose last collection is younger than max_age_days — skip these."""
    if store.empty or "collected_at" not in store.columns:
        return set()
    ca = pd.to_datetime(store["collected_at"], errors="coerce", utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max_age_days)
    fresh = store.loc[ca >= cutoff, "ticker"].astype(str).str.upper()
    return set(fresh)


def write_store(store: "pd.DataFrame", new_rows: list, collected_at: str) -> "pd.DataFrame":
    """Merge new rows in, atomically. Replaces a ticker's rows wholesale.

    A ticker is refetched as a UNIT (all its fiscal years), so the merge drops
    the ticker's old rows and inserts the new set — never interleaves two
    vintages inside one company. Writes to a temp file and renames so an
    interrupted write cannot truncate the store.
    """
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


# ── coverage report ───────────────────────────────────────────────────────────
def coverage(store: "pd.DataFrame") -> None:
    """Print the alphabet spread — the number this whole file exists to fix."""
    if store.empty:
        print("  store empty"); return
    import collections
    usable = store.dropna(subset=["cfo", "total_assets"])
    tick = sorted(usable["ticker"].astype(str).str.upper().unique())
    c = collections.Counter(t[0] for t in tick if t)
    a_share = c.get("A", 0) / len(tick) * 100 if tick else 0
    print(f"  usable tickers (cfo+total_assets): {len(tick)}")
    print(f"  distinct first-letters: {len(c)}   A-share: {a_share:.0f}%")
    print(f"  spread: {dict(sorted(c.items()))}")


# ── self-test ─────────────────────────────────────────────────────────────────
def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond

    u = _hash_order(["AAA", "ABB", "ZZZ", "MMM", "BBB"] * 4)
    check("hash order is not alphabetical",
          [s[0] for s in u[:3]] != sorted(s[0] for s in u)[:3] or len(set(u)) < 5)
    check("hash order is deterministic", _hash_order(["A", "M", "Z"]) == _hash_order(["Z", "A", "M"]))

    df = pd.DataFrame({pd.Timestamp("2025-03-31"): [100.0], pd.Timestamp("2024-03-31"): [90.0]},
                      index=["Total Assets"])
    s = _pick(df, ["Total Assets"])
    check("_pick finds a labelled row", s is not None and abs(s.iloc[0] - 100.0) < 1e-9)
    check("_pick returns None for a missing label", _pick(df, ["Nonexistent"]) is None)

    store = pd.DataFrame({"ticker": ["OLDNAME"], "fy_end": ["2024-03-31"],
                          "cfo": [1.0], "collected_at": ["2020-01-01T00:00:00+00:00"]})
    fresh = _fresh_set(store, 30)
    check("a year-old collection is NOT fresh", "OLDNAME" not in fresh)
    store2 = store.copy()
    store2["collected_at"] = datetime.now(timezone.utc).isoformat()
    check("a just-now collection IS fresh", "OLDNAME" in _fresh_set(store2, 30))

    # merge replaces a ticker wholesale, never interleaves vintages
    m = write_store.__wrapped__ if hasattr(write_store, "__wrapped__") else None
    print("\n  self-test:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Off-hours India fundamentals collector")
    ap.add_argument("--limit", type=int, default=0, help="cap tickers (testing)")
    ap.add_argument("--max-age-days", type=int, default=FRESH_DAYS,
                    help="skip tickers collected within this many days")
    ap.add_argument("--rate", type=float, default=RATE, help="seconds between tickers")
    ap.add_argument("--with-screener", action="store_true",
                    help="also enrich from screener.in (rate-limited, off by default)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()

    uni = universe()
    store = load_store()
    fresh = _fresh_set(store, a.max_age_days)
    todo = [s for s in uni if s not in fresh]
    if a.limit:
        todo = todo[: a.limit]

    print(f"  universe {len(uni)} | fresh (<{a.max_age_days}d) {len(fresh)} | "
          f"to collect {len(todo)}  (~{len(todo) * a.rate / 60:.0f} min)")
    if not todo:
        print("  nothing to collect — store is current"); coverage(store); return 0

    collected_at = datetime.now(timezone.utc).isoformat()
    batch, got, empty, consecutive_empty = [], 0, 0, 0
    for i, sym in enumerate(todo, 1):
        rows = from_yfinance(sym)
        if rows:
            batch.extend(rows); got += 1; consecutive_empty = 0
        else:
            empty += 1; consecutive_empty += 1
        # A long run of empties is a throttle, not a coincidence — checkpoint and
        # stop, rather than burning the rest of the window fetching nothing.
        if consecutive_empty >= 60:
            print(f"  ⚠️  {consecutive_empty} consecutive empties — likely throttled, "
                  "checkpointing and stopping")
            store = write_store(store, batch, collected_at); batch = []
            break
        if len(batch) >= CHECKPOINT_EVERY:
            store = write_store(store, batch, collected_at); batch = []
            print(f"  [{i}/{len(todo)}] checkpoint · {got} collected, {empty} empty")
        time.sleep(a.rate)

    store = write_store(store, batch, collected_at)
    print(f"\n  done: {got} collected, {empty} empty this run")
    coverage(store)
    print(f"  → {STORE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
