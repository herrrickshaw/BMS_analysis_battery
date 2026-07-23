#!/usr/bin/env python3
"""
recurring_movers.py — the distilled daily watchlist: mailer/shortlist picks that
keep RECURRING across briefs and are actually MOVING since first flagged.

WHY RECURRENCE × MOVEMENT
-------------------------
signal_tracker.py records every pass into the signal ledger and promotes the
day's strongest to watchlist `signal` tier — but one strong day is one strong
day. A name that re-passes on multiple *distinct dates* while its price climbs
since the first flag is a different animal: the setup persisted and the market
agreed. That intersection is this list. It is rebuilt daily from the ledger, so
it updates itself as briefs come and go — nothing here is hand-curated.

RULES (deliberately few, all visible in the output):
  * window: last WINDOW_DAYS of ledger entries
  * recurrence: >= MIN_DATES distinct signal dates
  * moving: move since FIRST signal >= MIN_MOVE_PCT (uses the ledger's own
    price_at_signal as entry — the price the brief actually quoted)
  * source hygiene: india_factor_panel entries are EXCLUDED — that panel is a
    documented alphabetical sample (2026-07-21 CHANGELOG); recurrence from a
    biased sampler measures the bias, not the stock
  * liquidity: current price comes from today's scan workbook All_Stocks;
    names in T5_MOST_ILLIQUID (where tiers exist) are dropped

OUTPUTS
  * reports/recurring_movers.csv        full ranked table, rebuilt each run
  * watchlist.csv                       qualifying names ADDED as `signal` tier
                                        (existing rows never touched — same
                                        contract as signal_tracker.sync)
Usage:
    recurring_movers.py                # build + sync watchlist
    recurring_movers.py --no-sync      # build only, don't touch watchlist.csv
    recurring_movers.py --min-dates 3 --min-move 5
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "cache_seed" / "signal_ledger.parquet"
WATCHLIST = HERE / "watchlist.csv"
OUT = HERE / "reports" / "recurring_movers.csv"

WINDOW_DAYS = 30
MIN_DATES = 2          # distinct signal dates to count as "recurring"
MIN_MOVE_PCT = 2.0     # move since first signal to count as "moving"
EXCLUDED_SOURCES = ("india_factor_panel",)   # A-biased sampler — see docstring

# latest All_Stocks workbook per market -> (glob, symbol col, price col)
WORKBOOKS = {
    "IN": ("indian_full_scan/indian_full_scan_*.xlsx", "Symbol", "LTP"),
    "US": ("us_full_scan/us_full_scan_*.xlsx", "Symbol", "LTP"),
    "EU": ("european_scan/european_market_scan*.xlsx", "Symbol", "LTP"),
    "JP": ("japan_scan/japan_market_scan_*.xlsx", "YF_Ticker", "LTP_JPY"),
    "KR": ("korea_scan/korea_market_scan_*.xlsx", "YF_Ticker", "LTP_KRW"),
}


def _norm(sym: str, market: str) -> str:
    """Ledger vs workbook symbol normalisation. KR codes lose leading zeros in
    the ledger ('400' vs '000400'); JP/KR yf tickers carry suffixes."""
    s = str(sym).upper().strip()
    for suf in (".T", ".KS", ".KQ"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    if market == "KR":
        s = s.lstrip("0") or "0"
    return s


def current_prices(market: str) -> pd.DataFrame:
    """(symbol_norm, price, tier) from the newest scan workbook's All_Stocks."""
    glob, scol, pcol = WORKBOOKS[market]
    files = sorted(HERE.glob(glob))
    if not files:
        return pd.DataFrame(columns=["symbol_norm", "price", "tier"])
    df = pd.read_excel(files[-1], sheet_name="All_Stocks")
    tier = df["Liquidity_Tier"] if "Liquidity_Tier" in df.columns else None
    name = df["Name"] if "Name" in df.columns else None
    out = pd.DataFrame({
        "symbol_norm": df[scol].map(lambda s: _norm(s, market)),
        "price": pd.to_numeric(df[pcol], errors="coerce"),
        "tier": tier if tier is not None else "",
        "name": name if name is not None else "",
    })
    return out.dropna(subset=["price"]).drop_duplicates("symbol_norm")


def build(window_days: int, min_dates: int, min_move: float) -> pd.DataFrame:
    led = pd.read_parquet(LEDGER)
    led["signal_date"] = pd.to_datetime(led["signal_date"]).dt.date
    cutoff = date.today() - timedelta(days=window_days)
    led = led[led["signal_date"] >= cutoff]
    excl = led["source"].isin(EXCLUDED_SOURCES)
    if excl.any():
        print(f"  excluded {excl.sum()} ledger rows from biased source(s): "
              f"{', '.join(EXCLUDED_SOURCES)}")
    led = led[~excl].copy()
    led["symbol_norm"] = [_norm(s, m) for s, m in zip(led["symbol"], led["market"])]

    grouped = (
        led.sort_values("signal_date")
        .groupby(["symbol_norm", "market"])
        .agg(symbol=("symbol", "last"),
             appearances=("signal_date", "nunique"),
             filters=("filter", lambda f: "+".join(sorted(set(f)))),
             best_detail=("detail", "last"),
             first_signal=("signal_date", "min"),
             last_signal=("signal_date", "max"),
             entry_price=("price_at_signal", "first"))
        .reset_index()
    )
    grouped = grouped[grouped["appearances"] >= min_dates]

    frames = []
    for mkt, g in grouped.groupby("market"):
        px = current_prices(mkt)
        g = g.merge(px, on="symbol_norm", how="left")
        frames.append(g)
    df = pd.concat(frames, ignore_index=True) if frames else grouped.assign(price=None, tier="")

    df = df[df["tier"].fillna("") != "T5_MOST_ILLIQUID"]
    df["move_pct"] = (df["price"] / df["entry_price"] - 1.0) * 100
    df = df.dropna(subset=["move_pct"])
    df = df[df["move_pct"] >= min_move]
    # recurrence first, then magnitude — a 3-date +5% beats a 2-date +12%
    df = df.sort_values(["appearances", "move_pct"], ascending=[False, False])
    cols = ["symbol", "name", "market", "appearances", "move_pct", "entry_price",
            "price", "first_signal", "last_signal", "filters", "best_detail", "tier"]
    return df[cols].reset_index(drop=True)


def sync_watchlist(df: pd.DataFrame, top: int) -> int:
    """Add the TOP qualifiers as `signal` tier. Existing rows are NEVER touched
    — a held/sold name keeps its status (same contract as signal_tracker).
    Capped: on a young ledger 100+ names qualify at 2 appearances; flooding the
    watchlist buries the curated tiers. The full ranked list is always in the
    CSV; only the head is promoted."""
    df = df.head(top)
    if df.empty or not WATCHLIST.exists():
        return 0
    wl = pd.read_csv(WATCHLIST)
    have = {(str(r["symbol"]).upper(), str(r["market"]).upper())
            for _, r in wl.iterrows()}
    added = 0
    rows = []
    for _, r in df.iterrows():
        k = (str(r["symbol"]).upper(), str(r["market"]).upper())
        if k in have:
            continue
        px = pd.to_numeric(r.get("entry_price"), errors="coerce")
        rows.append({"symbol": r["symbol"], "market": r["market"],
                     "status": "signal",
                     "note": f"recurring x{r['appearances']} "
                             f"{r['move_pct']:+.1f}% since {r['first_signal']}",
                     # stamped at add time for the digest's since-entry column
                     "entry_date": str(r.get("first_signal") or "")[:10] or None,
                     "entry_price": round(float(px), 4) if pd.notna(px) else None})
        have.add(k); added += 1
    if added:
        pd.concat([wl, pd.DataFrame(rows)], ignore_index=True).to_csv(
            WATCHLIST, index=False)
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=WINDOW_DAYS)
    ap.add_argument("--min-dates", type=int, default=MIN_DATES)
    ap.add_argument("--min-move", type=float, default=MIN_MOVE_PCT)
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--sync-top", type=int, default=25,
                    help="max names promoted to watchlist.csv per run")
    a = ap.parse_args()

    df = build(a.window, a.min_dates, a.min_move)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"\n=== RECURRING MOVERS — {len(df)} names "
          f"(>= {a.min_dates} dates, >= {a.min_move:+.1f}% since first signal, "
          f"window {a.window}d) ===")
    if df.empty:
        print("  none qualify today")
    else:
        show = df.head(25).copy()
        show["move_pct"] = show["move_pct"].map(lambda v: f"{v:+.1f}%")
        print(show.to_string(index=False))
        if len(df) > 25:
            print(f"  … {len(df)-25} more in {OUT.name}")
    print(f"  -> {OUT}")

    if not a.no_sync:
        added = sync_watchlist(df, a.sync_top)
        print(f"  watchlist.csv: +{added} new `signal` names "
              f"(top {a.sync_top} only; existing rows untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
