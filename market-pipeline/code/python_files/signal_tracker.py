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
# Warehouse dirs (year-partitioned parquet) — pd.read_parquet reads a directory
# natively. Replaces the monolithic ltm panels and the per-market folklore of
# which repo held the good copy (the other US.parquet is the broken
# alphabetical collection).
PANELS = {
    "IN": Path("/Users/umashankar/repos/global-market-data/warehouse/ohlcv/IN"),
    "US": Path("/Users/umashankar/repos/global-market-data/warehouse/ohlcv/US"),
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

# `technical` needs a HARD CAP that the fundamental filters do not.
#
# It fired 110 times on 2026-07-21 while only the Korea scanner emitted
# Quality_Grade. Once breakout_quality was wired into the other four scanners
# the same filter returned 2,110 passes in one run and pushed the watchlist from
# 775 rows to 2,703 — a "watchlist" nobody can act on. The filter is not broken:
# 2,110 of ~15,000 names is a ~14% hit rate, which is what a grade-A/B breakout
# screen should return. It is simply not a shortlist.
#
# Grade alone is not enough of a bar — grade A is still 595 names/day, and any
# daily intake compounds. So: rank by quality score and take the best few PER
# MARKET. Per-market, not global, because a global top-N would hand the whole
# list to whichever market happened to scan the most names — the Korea skew
# again, pointed the other way (US alone was 1,044 of the 2,110).
#
# The ledger still records every pass, so nothing is lost for analysis; this
# bounds only what earns a tracked watchlist slot.
TECHNICAL_MIN_GRADE = {"grade A"}     # detail string as harvest_technical writes it
TECHNICAL_TOP_PER_MARKET = 5


def _cap_technical(new: pd.DataFrame) -> pd.DataFrame:
    """Keep only the strongest few `technical` passes per market."""
    if new.empty or "filter" not in new.columns:
        return new
    tech = new[new["filter"] == "technical"]
    rest = new[new["filter"] != "technical"]
    if tech.empty:
        return new
    keep = (tech[tech["detail"].isin(TECHNICAL_MIN_GRADE)]
            .sort_values("score", ascending=False)
            .groupby("market", group_keys=False)
            .head(TECHNICAL_TOP_PER_MARKET))
    return pd.concat([rest, keep], ignore_index=True)


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
    new = _cap_technical(new)
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


def _track_via_yf(grp: pd.DataFrame, mkt: str, min_days: int) -> list:
    """Forward-track EU/JP/KR signals from yfinance — markets with no local panel.

    Symbol conventions are the watchlist's, reused rather than re-derived:
    Korea's bare codes have lost their leading zeros (38880 is 038880) and need
    re-padding plus a .KS/.KQ board suffix; Japan needs .T; EU symbols already
    carry their exchange suffix.

    No benchmark: there is no index series for these markets in any local store,
    and inventing one from the handful of shortlisted names would compare each
    signal against itself. `xret_pct` stays NaN and the summary shows it as such.
    """
    try:
        import yfinance as yf
        from watchlist_pnl import _yf_candidates
    except ImportError:
        return []
    # Drop entries that cannot possibly have a forward bar BEFORE hitting the
    # network. 1,069 of the 1,119 EU/JP/KR entries are stamped today, so fetching
    # the whole group would make 1,119 sequential requests to track 50.
    grp = grp[pd.to_datetime(grp["signal_date"]) < pd.Timestamp(date.today())]
    out = []
    for _, r in grp.iterrows():
        sd = pd.Timestamp(r["signal_date"])
        entry_px = r.get("price_at_signal")
        for t in _yf_candidates(mkt, str(r["symbol"])):
            try:
                h = yf.Ticker(t).history(start=(sd - pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
                                         auto_adjust=False)
            except Exception:
                continue
            if h is None or h.empty or "Close" not in h.columns:
                continue
            c = pd.to_numeric(h["Close"], errors="coerce").dropna()
            if c.empty:
                continue
            idx = pd.to_datetime(c.index).tz_localize(None)
            after = c[idx >= sd]
            if after.empty:
                break                     # resolved, but no bar since the signal
            entry, basis = entry_px, "signal-price"
            if entry != entry or not entry:
                prior = c[idx <= sd]
                if prior.empty:
                    break
                entry, basis = float(prior.iloc[-1]), "panel-close"
            last_dt = pd.to_datetime(after.index[-1]).tz_localize(None)
            out.append({**r.to_dict(), "entry_used": entry, "basis": basis,
                        "as_of": last_dt, "benchmark": None,
                        "held_days": (last_dt - sd).days,
                        "ret_pct": (float(after.iloc[-1]) / entry - 1) * 100,
                        "xret_pct": np.nan})
            break
    return out


def report(min_days: int, fetch_missing: bool = False) -> int:
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

    # Why an entry drops out matters as much as the return, so count the reasons
    # rather than silently `continue`. The old version skipped anything without a
    # price_at_signal and printed "no aged entries could be priced" — which was
    # true but useless: ALL 121 trackable entries were backfilled golden_cross
    # rows that never recorded an entry price, so the report was structurally
    # empty and looked like a data outage.
    rows, skipped = [], {"no_panel": 0, "not_in_panel": 0, "signal_after_panel": 0,
                         "no_entry_price": 0}
    bench_notes = []
    for mkt, grp in ready.groupby("market"):
        p = PANELS.get(mkt)
        if not p or not p.exists():
            # EU/JP/KR have no persisted panel — their scans fetch live and keep
            # nothing. That is 1,119 of the ledger's entries, i.e. most of the
            # shortlist, invisible to tracking. --fetch-missing pulls them from
            # yfinance; off by default because this is otherwise a pure read of
            # local stores.
            if fetch_missing:
                got = _track_via_yf(grp, mkt, min_days)
                rows.extend(got)
                skipped["no_panel"] += len(grp) - len(got)
            else:
                skipped["no_panel"] += len(grp)
            continue
        px = pd.read_parquet(p, columns=["Date", "Symbol", "Close"])
        px["Symbol"] = px["Symbol"].astype(str).str.upper()
        wide = px.pivot_table(index="Date", columns="Symbol", values="Close",
                              aggfunc="last").sort_index()
        panel_end = wide.index.max()
        # BENCHMARK, with a staleness check.
        #
        # NIFTYBEES is in the IN panel but its last bar is 2026-07-13, a week
        # behind the panel itself: it is an ETF (ISIN prefix INF) and the
        # equity-only bhavcopy filter — added after an ETF shipped as a
        # golden-cross pick — stopped updating it. Using it regardless yields a
        # benchmark window of <2 bars for every recent signal, so `vs mkt` came
        # out NaN for all 52 India entries with no explanation.
        #
        # Falling back to the panel's cross-sectional median is a DIFFERENT
        # benchmark — equal-weighted market, not NIFTY 50 — so it is labelled
        # rather than silently substituted.
        b = BENCH.get(mkt)
        bench, bench_name = None, None
        if b in wide.columns:
            cand = wide[b].dropna()
            if len(cand) and cand.index.max() >= panel_end - pd.Timedelta(days=3):
                bench, bench_name = cand, b
        if bench is None:
            bench, bench_name = wide.median(axis=1), "panel-median (equal-wt)"
            if b in wide.columns:
                stale_to = wide[b].dropna().index.max()
                bench_notes.append(
                    f"{mkt}: {b} last bar {stale_to:%Y-%m-%d} vs panel {panel_end:%Y-%m-%d}"
                    f" — using {bench_name}")
        for _, r in grp.iterrows():
            sym = str(r["symbol"]).upper()
            if sym not in wide.columns:
                skipped["not_in_panel"] += 1
                continue
            # A signal stamped today has no forward price yet. That is not a
            # failure — it is what forward tracking means — but it must be
            # reported as "too early", never folded into the sample.
            if pd.Timestamp(r["signal_date"]) > panel_end:
                skipped["signal_after_panel"] += 1
                continue
            s = wide[sym].dropna()
            after = s[s.index >= r["signal_date"]]
            if after.empty:
                skipped["signal_after_panel"] += 1
                continue

            # ENTRY PRICE, with its provenance labelled — the watchlist model.
            #   signal-price = recorded when the filter fired (a record)
            #   panel-close  = the panel's close on the signal date (an estimate:
            #                  no fill, no slippage, and for a backfilled row it
            #                  is only close to what the brief actually quoted)
            entry, basis = r.get("price_at_signal"), "signal-price"
            if entry != entry or not entry:
                prior = s[s.index <= r["signal_date"]]
                if prior.empty:
                    skipped["no_entry_price"] += 1
                    continue
                entry, basis = float(prior.iloc[-1]), "panel-close"

            ret = (after.iloc[-1] / entry - 1) * 100
            ba = bench[bench.index >= r["signal_date"]].dropna()
            bret = ((ba.iloc[-1] / ba.iloc[0] - 1) * 100) if len(ba) > 1 else np.nan
            rows.append({**r.to_dict(), "entry_used": entry, "basis": basis,
                         "as_of": after.index[-1], "benchmark": bench_name,
                         "held_days": (after.index[-1] - pd.Timestamp(r["signal_date"])).days,
                         "ret_pct": ret,
                         "xret_pct": ret - bret if bret == bret else np.nan})

    if not rows:
        print("\n  no aged entries could be priced. Why:")
        for k, v in skipped.items():
            if v:
                print(f"     {k:<20} {v:>5}")
        return 0
    r = pd.DataFrame(rows)
    print(f"\n  TRACKED: {len(r)} of {len(ready)} entries, each from its own shortlist date\n")

    print(f"  {'filter':<18} {'market':<7} {'n':>4} {'med ret':>9} {'med vs mkt':>11} "
          f"{'win%':>6} {'med days':>9}  basis")
    print("  " + "-" * 78)
    for (f, m), g in r.groupby(["filter", "market"]):
        bases = "/".join(sorted(g["basis"].unique()))
        xr = g["xret_pct"].dropna()
        print(f"  {f:<18} {m:<7} {len(g):>4} {g['ret_pct'].median():>8.2f}% "
              f"{(xr.median() if len(xr) else float('nan')):>10.2f}% "
              f"{((xr > 0).mean()*100 if len(xr) else float('nan')):>5.0f}% "
              f"{g['held_days'].median():>8.0f}  {bases}")

    if bench_notes:
        print("\n  benchmark substitutions:")
        for n in bench_notes:
            print(f"     {n}")

    if any(skipped.values()):
        print(f"\n  NOT TRACKED — {sum(skipped.values())} entries, by reason:")
        labels = {
            "signal_after_panel": "signalled today / after the panel's last bar — too early, "
                                  "by design",
            "no_panel":           "market has no price panel (EU/JP/KR are not configured)",
            "not_in_panel":       "symbol absent from its market's panel",
            "no_entry_price":     "no entry price and no panel bar on the signal date",
        }
        for k, v in skipped.items():
            if v:
                print(f"     {v:>5}  {labels[k]}")

    n_est = int((r["basis"] == "panel-close").sum())
    if n_est:
        print(f"\n  ⚠ {n_est} of {len(r)} use a panel-close entry, not a recorded signal price.")
        print("    Backfilled rows never stored what the brief quoted, so their entry is")
        print("    the panel's close that day — close to it, but not the same number.")
    print("\n  'med vs mkt' is the number that matters — beating the index, not the")
    print("  sign of the raw return. n is small early on; treat it as a diary, not")
    print("  a result, until each filter has dozens of entries across many dates.")

    out = HERE / "reports" / "signal_tracking.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["symbol", "market", "filter", "detail", "score", "signal_date", "as_of",
            "held_days", "entry_used", "basis", "ret_pct", "xret_pct", "provenance", "source"]
    r[[c for c in cols if c in r.columns]].sort_values(
        ["market", "signal_date", "ret_pct"], ascending=[True, True, False]
    ).to_csv(out, index=False)
    print(f"\n  → {out.relative_to(HERE)}  ({len(r)} rows, one per shortlisted name)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Forward-track filter passes")
    ap.add_argument("--record", action="store_true", help="stamp today's passes")
    ap.add_argument("--report", action="store_true", help="performance since signal")
    ap.add_argument("--min-days", type=int, default=5)
    ap.add_argument("--fetch-missing", action="store_true",
                    help="track EU/JP/KR from yfinance (no local panel)")
    a = ap.parse_args()
    if a.record:
        return record()
    if a.report:
        return report(a.min_days, a.fetch_missing)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
