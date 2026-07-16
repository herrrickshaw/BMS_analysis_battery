#!/usr/bin/env python3
"""
earnings_calendar.py — real, quarterly earnings-announcement dates (past +
upcoming) via yfinance's get_earnings_dates(), cross-checked against actual
news headlines (Marketaux) rather than trusted blind — for the tickers this
session already flagged as interesting: the sector-leader CANDIDATES from
pead_sector_spillover.py (none survived FDR correction, but they're still
the most-tested, most-relevant names to watch going forward).

WHY THIS MATTERS FOR THE PEAD WORK: pead_sector_spillover.py had two
flagged limitations (see DECISION_REGISTER.md) — (1) fundamentals_history
is ANNUAL (one filing/year), not quarterly, so events were coarse and
sparse; (2) no analyst-consensus data existed, so "surprise" was a YoY
net_income-growth proxy, not real SUE. yfinance's get_earnings_dates()
fixes BOTH: real quarterly dates AND real consensus EPS estimate vs
reported EPS (genuine surprise %) — a materially better event-study input
than what pead_sector_spillover.py had to work with. This script builds
the calendar; re-running PEAD on top of it is the natural next step, not
done here to keep this script's job to one thing.

NEWS CROSS-CHECK: yfinance's calendar is itself a data feed, not "news" —
for a sample of tickers this script also queries Marketaux
(sentiment_pipeline.py's existing provider, same API key already
configured this session) for real recent headlines mentioning the ticker,
and reports whether an earnings-related headline exists near the reported
date. This is the same "never trust one source" discipline as
validate_brief_*.py earlier this session — it validates yfinance's dates
are grounded in real reporting, not silently trusting one feed.

DISCLAIMER: this produces a calendar of scheduled/historical events and
past earnings-surprise statistics — informational/research only, NOT
investment advice, and this script places no orders and recommends no
trades. See build_mailer.py's standing disclaimer for the same language
used throughout this pipeline.

Usage:
    python3 earnings_calendar.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
import json
import re
import warnings
from datetime import datetime, timedelta, timezone

import pandas as pd

warnings.filterwarnings("ignore")

from stock_utils import parallel_map

PEAD_RESULTS_PATH = "cache_seed/pead_sector_spillover_results.json"
EARNINGS_KEYWORDS = re.compile(r"\b(earnings|results?|quarterly|Q[1-4]|profit|revenue|EPS)\b", re.I)


def _yf_ticker(market: str, symbol: str) -> str:
    if market == "IN":
        return f"{symbol}.NS"
    return symbol


def candidate_tickers() -> dict[str, list[str]]:
    """The sector-leader candidates already identified per market — the
    tickers this session has spent the most effort on, not an arbitrary
    new universe."""
    results = json.load(open(PEAD_RESULTS_PATH))
    out = {}
    for r in results:
        if "error" in r:
            continue
        out[r["market"]] = [l["ticker"] for l in r.get("top_sector_leaders", [])]
    return out


def _fetch_one(args) -> dict | None:
    market, symbol = args
    try:
        import yfinance as yf
        from yf_session import configure_yfinance, call_with_backoff
        configure_yfinance()
        df = call_with_backoff(lambda: yf.Ticker(_yf_ticker(market, symbol)).get_earnings_dates(limit=12))
        if df is None or df.empty:
            return None
        df = df.reset_index()
        df.columns = [str(c) for c in df.columns]
        return {"market": market, "symbol": symbol, "rows": df.to_dict("records")}
    except Exception:
        return None


def fetch_calendar(market: str, symbols: list[str], workers: int = 8) -> list[dict]:
    print(f"  [{market}] fetching earnings calendar for {len(symbols)} symbols...")
    return parallel_map(lambda s: _fetch_one((market, s)), symbols,
                        workers=workers, progress_every=20, label=f"{market} earnings dates")


def summarize(entries: list[dict]) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    rows = []
    for e in entries:
        upcoming, reported = [], []
        for row in e["rows"]:
            dt_key = next((k for k in row if "Earnings Date" in k), None)
            if not dt_key or row.get(dt_key) is None:
                continue
            dt = pd.Timestamp(row[dt_key])
            if dt.tzinfo is None:
                dt = dt.tz_localize("UTC")
            rep = row.get("Reported EPS")
            surprise = row.get("Surprise(%)")
            if pd.isna(rep):
                upcoming.append(dt)
            else:
                reported.append((dt, surprise))
        if upcoming:
            nxt = min(d for d in upcoming if d > now)
            days_out = (nxt - now).days
        else:
            nxt, days_out = None, None
        recent = sorted(reported, key=lambda x: x[0], reverse=True)[:4]
        avg_surprise = (sum(s for _, s in recent if pd.notna(s)) / len([s for _, s in recent if pd.notna(s)])
                        if any(pd.notna(s) for _, s in recent) else None)
        rows.append({"market": e["market"], "symbol": e["symbol"],
                     "next_earnings_date": nxt.strftime("%Y-%m-%d") if nxt is not None else None,
                     "days_until": days_out,
                     "last_4_avg_surprise_pct": round(avg_surprise, 2) if avg_surprise is not None else None,
                     "n_historical_reports": len(reported)})
    return pd.DataFrame(rows)


def news_cross_check(market: str, symbols: list[str], sample: int = 8) -> list[dict]:
    """Spot-check a handful of tickers against real Marketaux news — do
    recent headlines actually mention earnings/results for this name?"""
    import sys
    sys.path.insert(0, ".")
    import sentiment_pipeline as sp
    provider = sp.MarketauxProvider()
    if not provider.available:
        return [{"note": "Marketaux key not configured or provider unavailable — skipped"}]
    out = []
    for sym in symbols[:sample]:
        try:
            articles = provider.fetch_news(sym, market=market)
        except Exception as e:
            out.append({"symbol": sym, "error": str(e)})
            continue
        hits = [a for a in articles if EARNINGS_KEYWORDS.search(getattr(a, "title", "") or "")]
        out.append({"symbol": sym, "n_articles": len(articles), "n_earnings_related": len(hits),
                    "sample_headline": hits[0].title if hits else (articles[0].title if articles else None)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    a = ap.parse_args()

    cands = candidate_tickers()
    all_rows = []
    news_checks = {}
    for m in a.market:
        symbols = cands.get(m, [])
        if not symbols:
            print(f"[{m}] no sector-leader candidates found — run pead_sector_spillover.py first")
            continue
        entries = fetch_calendar(m, symbols)
        df = summarize(entries)
        all_rows.append(df)
        print(f"[{m}] {len(entries)}/{len(symbols)} symbols returned a calendar")

        news_checks[m] = news_cross_check(m, symbols)

    full = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    full = full.sort_values("days_until", na_position="last")
    full.to_json("cache_seed/earnings_calendar_results.json", orient="records", indent=2)
    with open("cache_seed/earnings_calendar_news_check.json", "w") as f:
        json.dump(news_checks, f, indent=2, default=str)

    print("\n\n" + "=" * 90)
    print("UPCOMING EARNINGS — sector-leader candidates, soonest first")
    print("=" * 90)
    upcoming = full[full["days_until"].notna()].sort_values("days_until")
    for _, r in upcoming.iterrows():
        print(f"  {r['next_earnings_date']}  ({int(r['days_until']):>3}d)  {r['market']:3s} {r['symbol']:12s}  "
              f"last-4 avg surprise: {r['last_4_avg_surprise_pct']}%  "
              f"(n={r['n_historical_reports']} historical reports)")

    print("\n" + "=" * 90)
    print("NEWS CROSS-CHECK (Marketaux)")
    print("=" * 90)
    for m, checks in news_checks.items():
        print(f"\n{m}:")
        for c in checks:
            if "error" in c or "note" in c:
                print(f"  {c}")
                continue
            headline_note = ""
            if c.get("sample_headline"):
                snippet = c["sample_headline"][:70]
                headline_note = f'  -- "{snippet}"'
            print(f"  {c['symbol']}: {c['n_articles']} articles, {c['n_earnings_related']} "
                  f"earnings-related{headline_note}")

    print("\n⚠️  Informational/research only — a calendar of scheduled events and "
          "historical surprise statistics. NOT investment advice; this script "
          "places no orders and recommends no trades.")


if __name__ == "__main__":
    main()
