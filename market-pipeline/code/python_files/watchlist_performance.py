#!/usr/bin/env python3
"""
watchlist_performance.py — multi-horizon performance for the watchlist.

1M / 3M / 6M / 1Y / 3Y / 5Y, absolute AND versus the market, per name and
aggregated by tier (held / watch / exited).

WHY THIS USES THE LFS PANELS, NOT THE DAILY CACHES
--------------------------------------------------
watchlist_digest.py reads market_cache (US) and the bhavcopy LMDB (India),
which is right for a 1-day move and wrong for anything longer. Measured
2026-07-21:

    US market_cache   ~1,278 bars/ticker   ≈ 5.1 years   (5Y is at the edge)
    India LMDB        ~36 bars/ticker      ≈ 0.1 years   (unusable past ~1M)
    IN  LFS ltm       2016-01 → 2026-07    10.5 years
    US  LFS ltm       2016-06 → 2026-07    10.0 years

The India LMDB is a short rolling window kept for the daily scan, not a history
store. Asking it for a 3-year return returns nothing, and a version of this that
silently fell back to "whatever bars exist" would report a 36-day move in the 3Y
column. So the LFS panels are the source here and shallow data is reported as
"—", never as a number.

WHY BENCHMARK-RELATIVE MATTERS MORE AS THE HORIZON GROWS
-------------------------------------------------------
Over a day, absolute and relative barely differ. Over five years the index may
have doubled, so +50% is a LOSS against simply holding the index. Both are
shown; the vs-market column is the one that answers "was owning this worth it".

    watchlist_performance.py
    watchlist_performance.py --tier held
    watchlist_performance.py --out perf.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PANELS = {
    "IN": Path("/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"),
    "US": Path("/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"),
}
BENCH = {"IN": "NIFTYBEES", "US": "SPY"}

# Trading days. 3Y/5Y are approximate by construction — calendar years contain
# ~252 sessions, and holidays differ by market. Close enough for a return
# horizon, and stated so nobody reads 1260 as exact.
HORIZONS = [("1M", 21), ("3M", 63), ("6M", 126),
            ("1Y", 252), ("3Y", 756), ("5Y", 1260)]


def _load(market: str):
    p = PANELS.get(market)
    if not p or not p.exists():
        return None, None
    px = pd.read_parquet(p, columns=["Date", "Symbol", "Close"])
    px["Symbol"] = px["Symbol"].astype(str).str.upper()
    px["Date"] = pd.to_datetime(px["Date"])
    wide = px.pivot_table(index="Date", columns="Symbol", values="Close",
                          aggfunc="last").sort_index()
    b = BENCH.get(market)
    bench = wide[b] if b in wide.columns else wide.median(axis=1)
    return wide, bench


def _ret(series: pd.Series, bars: int) -> Optional[float]:
    """Percent return over `bars` sessions, or None if history is too short.

    None — not 0, not the longest-available window. A watchlist that quietly
    substitutes a 36-day move for a 3-year one is worse than one that admits
    it does not know.
    """
    s = series.dropna()
    if len(s) < bars + 1:
        return None
    a, b = s.iloc[-1 - bars], s.iloc[-1]
    if not a or a <= 0:
        return None
    return float((b / a - 1) * 100)


def build(watchlist: pd.DataFrame) -> pd.DataFrame:
    # BSE-code bridge, same as the factor panel: screener/broker exports key some
    # India names by numeric BSE code while the price panel uses NSE symbols.
    bse2nse = {}
    try:
        xl = pd.read_excel("/Users/umashankar/Library/Mobile Documents/"
                           "com~apple~CloudDocs/Desktop/xlsx/Stock_List_NSE_BSE_1.xlsx",
                           sheet_name="Stock List")
        xl.columns = [str(c).strip() for c in xl.columns]
        for _, r in xl.iterrows():
            if pd.notna(r.get("BSE Code")) and pd.notna(r.get("NSE Symbol")):
                bse2nse[str(int(r["BSE Code"]))] = str(r["NSE Symbol"]).strip().upper()
    except Exception:
        pass

    cache = {}
    rows = []
    for _, w in watchlist.iterrows():
        sym = str(w["symbol"]).strip().upper()
        mkt = str(w.get("market") or "US").strip().upper()
        mkt = "IN" if mkt in ("IN", "INDIA", "NS") else "US"
        if mkt not in cache:
            cache[mkt] = _load(mkt)
        wide, bench = cache[mkt]
        rec = {"symbol": sym, "market": mkt,
               "status": str(w.get("status") or "held").lower()}
        if wide is None:
            rows.append(rec); continue

        key = bse2nse.get(sym, sym)
        # Class shares: BRK.B in filings, BRK-B in price data.
        for cand in (key, key.replace(".", "-")):
            if cand in wide.columns:
                key = cand
                break
        else:
            rec["missing"] = True
            rows.append(rec); continue

        s = wide[key]
        for label, bars in HORIZONS:
            r = _ret(s, bars)
            bmk = _ret(bench, bars)
            rec[label] = r
            rec[f"{label}_vs"] = (r - bmk) if (r is not None and bmk is not None) else None
        rec["bars"] = int(s.dropna().shape[0])
        rows.append(rec)
    return pd.DataFrame(rows)


def _fmt(v) -> str:
    return "—" if v is None or (isinstance(v, float) and v != v) else f"{v:+.1f}"


def report(df: pd.DataFrame, tier: Optional[str]) -> None:
    d = df if not tier else df[df["status"] == tier]
    have = d[~d.get("missing", pd.Series(False, index=d.index)).fillna(False)]
    print("=" * 92)
    print(f"  WATCHLIST PERFORMANCE{' — ' + tier if tier else ''}")
    print("=" * 92)
    print(f"  {len(d)} names · {len(have)} with price history · "
          f"{len(d) - len(have)} not in the panels\n")

    labels = [h[0] for h in HORIZONS]
    print(f"  {'tier':<8} {'n':>4} " + " ".join(f"{l:>17}" for l in labels))
    print("  " + "-" * 88)
    for t in ("held", "watch", "sold"):
        sub = have[have["status"] == t]
        if sub.empty:
            continue
        cells = []
        for l in labels:
            med = sub[l].median(skipna=True)
            medv = sub[f"{l}_vs"].median(skipna=True)
            n = int(sub[l].notna().sum())
            cells.append(f"{_fmt(med):>7}/{_fmt(medv):>6}({n:>3})" if n else f"{'—':>17}")
        print(f"  {t:<8} {len(sub):>4} " + " ".join(cells))
    print("\n  cells are  median_absolute% / median_vs_market%  (n with enough history)")
    print("  vs-market uses NIFTYBEES for India, SPY for US.\n")

    held = have[have["status"] == "held"]
    if not held.empty and held["1Y"].notna().any():
        print("  HELD — best and worst on 1Y vs market:")
        h = held.dropna(subset=["1Y_vs"]).sort_values("1Y_vs", ascending=False)
        for _, r in pd.concat([h.head(5), h.tail(5)]).iterrows():
            print(f"     {r['symbol']:<12} {r['market']}  1Y {_fmt(r['1Y']):>7}%  "
                  f"vs mkt {_fmt(r['1Y_vs']):>7}pp   5Y {_fmt(r.get('5Y')):>8}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-horizon watchlist performance")
    ap.add_argument("--watchlist", default=str(HERE / "watchlist.csv"))
    ap.add_argument("--tier", choices=["held", "watch", "sold"])
    ap.add_argument("--out", help="write the per-name table to CSV")
    a = ap.parse_args()

    wl = pd.read_csv(a.watchlist)
    df = build(wl)
    report(df, a.tier)
    if a.out:
        df.to_csv(a.out, index=False)
        print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
