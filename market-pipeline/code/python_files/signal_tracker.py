#!/usr/bin/env python3
"""
signal_tracker.py — record filter passes on the day they happen, then measure
what actually followed.

WHY THIS IS WORTH MORE THAN ANOTHER BACKTEST
--------------------------------------------
Every backtest in this repo carries the same three wounds, and all three push
results in the flattering direction:

  * SURVIVORSHIP — screener.in and yfinance serve companies that still exist, so
    the names a quality screen should have avoided are invisible.
  * LOOKAHEAD RISK — a filing date proxy that is wrong by a month hands the
    strategy information it did not have.
  * SELECTION — the universe is whatever happened to be collected.

Forward tracking has none of them. A pick is written down TODAY, with today's
price, before the outcome exists. Nothing can be quietly dropped later, because
the record was made first. It is slow — a year of tracking buys one year of
evidence — but it is the only evidence here that cannot be talked up.

🔴 THE ONE RULE: signal_date is NEVER backfilled.
The moment a signal can be recorded with a past date, the whole exercise decays
into another backtest with the same wounds. `record` only ever stamps today.
A missed day is a gap in the record, and a gap is honest; a reconstructed entry
is not.

WHAT COUNTS AS A PASS
  technical  Quality_Grade A/B AND above a RISING EMA-50 AND a recomputed
             BREAKOUT_BUY (see breakout_quality.py — the stored Darvas_Signal
             was corrupt until 2026-07-21 and is not trusted here)
  fundamental  piotroski / roce_plus / debt_reduction from the India factor
             panel, and their combinations

    signal_tracker.py --record        # stamp today's passes (idempotent)
    signal_tracker.py --report        # performance since each signal date
    signal_tracker.py --report --min-days 21
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "cache_seed" / "signal_ledger.parquet"
PANELS = {
    "IN": Path("/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"),
    "US": Path("/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"),
}
BENCH = {"IN": "NIFTYBEES", "US": "SPY"}
GOOD_GRADES = {"A", "B"}

SCAN_DIRS = {
    "IN": ("indian_full_scan", "indian_full_scan_*.xlsx"),
    "US": ("us_full_scan", "us_full_scan_*.xlsx"),
    "KR": ("korea_scan", "korea_market_scan_*.xlsx"),
    "JP": ("japan_scan", "japan_market_scan_*.xlsx"),
    "EU": ("european_scan", "european_market_scan_broad_*.xlsx"),
}


def _latest(d: str, pat: str) -> Optional[Path]:
    fs = sorted((HERE / d).glob(pat))
    return fs[-1] if fs else None


def harvest_technical() -> pd.DataFrame:
    """Today's high-quality breakouts across every market that scanned."""
    rows = []
    for mkt, (d, pat) in SCAN_DIRS.items():
        f = _latest(d, pat)
        if not f:
            continue
        try:
            s = pd.read_excel(f, "All_Stocks")
        except Exception:
            continue
        if "Quality_Grade" not in s.columns:
            continue          # scan predates breakout_quality
        sym_col = "Symbol" if "Symbol" in s.columns else "Code"
        ok = s[
            s["Quality_Grade"].isin(GOOD_GRADES)
            & s.get("Above_EMA50", pd.Series(False, index=s.index)).fillna(False).astype(bool)
            & s.get("EMA50_Rising", pd.Series(False, index=s.index)).fillna(False).astype(bool)
            & (s.get("Recomputed_Signal", pd.Series("", index=s.index)) == "BREAKOUT_BUY")
        ]
        for _, r in ok.iterrows():
            rows.append({
                "symbol": str(r[sym_col]).strip().upper(), "market": mkt,
                "filter": "technical", "detail": f"grade {r['Quality_Grade']}",
                "score": float(r.get("Quality_Score") or np.nan),
                "price_at_signal": pd.to_numeric(
                    pd.Series([r.get("LTP") or r.get("LTP_KRW") or r.get("LTP_JPY")]),
                    errors="coerce").iloc[0],
                "source": f.name,
            })
    return pd.DataFrame(rows)


def harvest_fundamental() -> pd.DataFrame:
    """Most recent rebalance's factor passes from the India panel."""
    p = HERE / "cache_seed" / "india_factor_panel.parquet"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_parquet(p)
    d = d[d["year"] == d["year"].max()]
    combos = [
        ("piotroski", d["piotroski"]),
        ("roce_plus", d["roce_plus"]),
        ("debt_reduction", d["debt_reduction"]),
        ("piotroski+debt", d["piotroski"] & d["debt_reduction"]),
        ("piotroski+roce", d["piotroski"] & d["roce_plus"]),
        ("triple", d["piotroski"] & d["roce_plus"] & d["debt_reduction"]),
    ]
    rows = []
    for name, mask in combos:
        for _, r in d[mask.fillna(False)].iterrows():
            rows.append({"symbol": str(r["ticker"]).strip().upper(), "market": "IN",
                         "filter": name, "detail": f"F={r.get('f_score')}",
                         "score": float(r.get("f_score") or np.nan),
                         "price_at_signal": np.nan, "source": "india_factor_panel"})
    return pd.DataFrame(rows)


WATCHLIST = HERE / "watchlist.csv"
# Filters strong enough to earn a watchlist slot. Recording EVERY pass would add
# ~50 debt_reduction names a day and drown the list within a week — the ledger
# tracks all of them regardless, so nothing is lost by being selective here.
WATCHLIST_FILTERS = {"triple", "piotroski+debt", "piotroski+roce", "technical"}


def sync_watchlist(new: pd.DataFrame) -> int:
    """Add today's strongest passes to watchlist.csv as the `signal` tier.

    Existing rows are never touched: a name already held or sold keeps that
    status. A stock you own that re-passes a filter is still a holding, and
    demoting it to `signal` would lose the more important fact.
    """
    if new.empty or not WATCHLIST.exists():
        return 0
    wl = pd.read_csv(WATCHLIST)
    have = {(str(r["symbol"]).upper(), str(r["market"]).upper())
            for _, r in wl.iterrows()}
    rows = [list(r) for r in wl.itertuples(index=False, name=None)]
    added = 0
    for _, r in new[new["filter"].isin(WATCHLIST_FILTERS)].iterrows():
        k = (r["symbol"], r["market"])
        if k in have:
            continue
        rows.append([r["symbol"], r["market"], "signal",
                     f"{r['filter']} {pd.Timestamp(r['signal_date']):%Y-%m-%d}"])
        have.add(k); added += 1
    if added:
        import csv
        with WATCHLIST.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["symbol", "market", "status", "note"])
            w.writerows(rows)
    return added


def record() -> int:
    today = pd.Timestamp(date.today())
    new = pd.concat([harvest_technical(), harvest_fundamental()], ignore_index=True)
    if new.empty:
        print("  no filter passes today"); return 0
    new["signal_date"] = today

    # Fill missing entry prices from the price panel, but ONLY as of today.
    for mkt, grp in new.groupby("market"):
        p = PANELS.get(mkt)
        if not p or not p.exists():
            continue
        px = pd.read_parquet(p, columns=["Date", "Symbol", "Close"])
        px["Symbol"] = px["Symbol"].astype(str).str.upper()
        last = px.sort_values("Date").groupby("Symbol")["Close"].last()
        miss = new["price_at_signal"].isna() & (new["market"] == mkt)
        new.loc[miss, "price_at_signal"] = new.loc[miss, "symbol"].map(last)

    old = pd.read_parquet(LEDGER) if LEDGER.exists() else pd.DataFrame()
    if not old.empty:
        # Idempotent per day: re-running must not duplicate or re-stamp. An
        # existing (symbol, filter, date) row is left exactly as first written.
        key = ["symbol", "filter", "signal_date"]
        merged = pd.concat([old, new], ignore_index=True)
        before = len(merged)
        merged = merged.drop_duplicates(subset=key, keep="first")
        added = len(merged) - len(old)
        print(f"  {len(new)} passes today; {added} new, "
              f"{before - len(merged)} already recorded")
    else:
        merged, added = new, len(new)
        print(f"  {added} passes recorded (ledger created)")

    LEDGER.parent.mkdir(exist_ok=True)
    merged.to_parquet(LEDGER, index=False)
    for f, n in new["filter"].value_counts().items():
        print(f"     {f:<18} {n}")
    print(f"  → {LEDGER}  ({len(merged)} total entries)")

    n_wl = sync_watchlist(new)
    print(f"  watchlist: +{n_wl} signal name(s)"
          if n_wl else "  watchlist: no new names (all already tracked)")
    return 0


def report(min_days: int) -> int:
    if not LEDGER.exists():
        print("  no ledger yet — run --record first"); return 1
    led = pd.read_parquet(LEDGER)
    led["signal_date"] = pd.to_datetime(led["signal_date"])
    today = pd.Timestamp(date.today())
    led["days_held"] = (today - led["signal_date"]).dt.days

    ready = led[led["days_held"] >= min_days]
    print("=" * 82)
    print(f"  SIGNAL TRACKER — {len(led)} entries, {led['signal_date'].nunique()} signal dates")
    print(f"  {led['signal_date'].min():%Y-%m-%d} → {led['signal_date'].max():%Y-%m-%d}")
    print("=" * 82)
    if ready.empty:
        print(f"\n  Nothing has aged {min_days}+ days yet.")
        print("  That is the point: this measures the FUTURE, so it starts empty and")
        print("  earns its evidence. Come back after the horizon has actually passed.")
        print(f"\n  oldest entry is {int(led['days_held'].max())} days old")
        for f, n in led["filter"].value_counts().items():
            print(f"     {f:<18} {n:>4} tracked")
        return 0

    rows = []
    for mkt, grp in ready.groupby("market"):
        p = PANELS.get(mkt)
        if not p or not p.exists():
            continue
        px = pd.read_parquet(p, columns=["Date", "Symbol", "Close"])
        px["Symbol"] = px["Symbol"].astype(str).str.upper()
        wide = px.pivot_table(index="Date", columns="Symbol", values="Close",
                              aggfunc="last").sort_index()
        b = BENCH.get(mkt)
        bench = wide[b] if b in wide.columns else wide.median(axis=1)
        for _, r in grp.iterrows():
            if r["symbol"] not in wide.columns or r["price_at_signal"] != r["price_at_signal"]:
                continue
            s = wide[r["symbol"]].dropna()
            after = s[s.index >= r["signal_date"]]
            if after.empty:
                continue
            ret = (after.iloc[-1] / r["price_at_signal"] - 1) * 100
            ba = bench[bench.index >= r["signal_date"]].dropna()
            bret = ((ba.iloc[-1] / ba.iloc[0] - 1) * 100) if len(ba) > 1 else np.nan
            rows.append({**r.to_dict(), "ret_pct": ret,
                         "xret_pct": ret - bret if bret == bret else np.nan})
    if not rows:
        print("\n  no aged entries could be priced"); return 0
    r = pd.DataFrame(rows)
    print(f"\n  {len(r)} entries aged >= {min_days}d\n")
    print(f"  {'filter':<18} {'n':>4} {'med ret':>9} {'med vs mkt':>11} {'win%':>6} {'med days':>9}")
    print("  " + "-" * 62)
    for f, g in r.groupby("filter"):
        print(f"  {f:<18} {len(g):>4} {g['ret_pct'].median():>8.2f}% "
              f"{g['xret_pct'].median():>10.2f}% "
              f"{(g['xret_pct'] > 0).mean()*100:>5.0f}% {g['days_held'].median():>8.0f}")
    print("\n  'med vs mkt' is the number that matters — beating the index, not the")
    print("  sign of the raw return. n is small early on; treat it as a diary, not")
    print("  a result, until each filter has dozens of entries across many dates.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Forward-track filter passes")
    ap.add_argument("--record", action="store_true", help="stamp today's passes")
    ap.add_argument("--report", action="store_true", help="performance since signal")
    ap.add_argument("--min-days", type=int, default=5)
    a = ap.parse_args()
    if a.record:
        return record()
    if a.report:
        return report(a.min_days)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
