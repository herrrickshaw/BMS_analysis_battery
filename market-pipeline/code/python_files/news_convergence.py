#!/usr/bin/env python3
"""
news_convergence.py — do the news agree with what the filters said?

For every stock that passed a filter today, pull Moneycontrol/ET/Mint coverage
and report CONVERGENCE or DIVERGENCE against the filter's verdict.

🔴 WHAT THIS IS FOR, AND WHAT IT IS NOT
---------------------------------------
The tempting framing is "the filter picked it AND the news is good, so the
filter worked". That is confirmation bias with a report attached, and it would
make every filter look good on the days the market rose. News agreeing with a
pick is not evidence the pick is right.

The value runs the other way. A stock that is technically immaculate — grade A
breakout, above a rising EMA-50 — while the tape carries a fraud probe, an
auditor resignation or a guidance cut is a stock the price has not repriced
YET. That is a DIVERGENCE, and it is the only output here worth acting on.

So:
    DIVERGENT   filter says buy, news is materially negative   <- the signal
    CONVERGENT  filter says buy, news is positive              <- weak evidence
    NEUTRAL     filter says buy, coverage is routine           <- the normal case
    NO_NEWS     no company-specific coverage found             <- NOT good news

Only forward returns can say whether a filter works; signal_tracker.py does
that. This says whether anything is publicly known that the filter cannot see.

🔴 ABSENCE OF NEWS IS NOT CONFIRMATION. Most Indian small caps have no daily
coverage at all. NO_NEWS is reported as its own category, never folded into
NEUTRAL, because "nothing bad was written" and "nobody was looking" are
different facts and only one of them is reassuring.

🔴 WHY THE MATCHING IS STRICTER THAN sentiment_pipeline's
The RSS feeds are MARKET-WIDE, not per-ticker. The default matcher accepts a
mention anywhere in title or summary, which on 2026-07-21 scored RELIANCE
POSITIVE off two copies of "Market wrap: Top gainers and losers on Nifty and
Sensex today" — a market-wrap headline that names dozens of companies and says
nothing about any of them. Attributing that to a ticker manufactures a
confident number out of noise.

Here a headline counts only if the company is named in the TITLE, generic
market-wrap headlines are excluded outright, and duplicates are collapsed.
That trades recall for precision on purpose: a missed headline costs nothing,
a fabricated sentiment reading costs a decision.

    news_convergence.py                    # today's passes, India
    news_convergence.py --top 25 --out reports/news_convergence.csv
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "cache_seed" / "signal_ledger.parquet"

# Headlines that name many companies and characterise none. Scoring these
# against a ticker is how a market-wide mood becomes a company-specific claim.
GENERIC = re.compile(
    r"market wrap|top gainers|gainers and losers|sensex|nifty (?:closes|ends|today|opens)"
    r"|market (?:live|today|close|open)|stocks to watch|buzzing stocks"
    r"|trade setup|f&o (?:ban|cues)|closing bell|opening bell",
    re.I)

# Words that make a headline MATERIAL regardless of its VADER score. VADER is a
# general-purpose sentiment model: "SEBI probe" and "CFO resigns" are close to
# neutral in ordinary English, and those are exactly the headlines that matter.
RED_FLAG = re.compile(
    r"\b(fraud|probe|investigat\w+|raid|sebi|insolven\w+|nclt|default\w*|downgrade[ds]?"
    r"|resign\w+|auditor|qualified opinion|impair\w+|writ[e-]?off|fine[ds]?|penalt\w+"
    r"|lawsuit|litigation|delist\w*|pledge[ds]?|fell short|guidance cut|profit warning)\b",
    re.I)


def _clean_name(sym: str) -> str:
    """Company name for `sym`, for title matching. Falls back to the symbol."""
    try:
        from symbol_master import clean_name_for
        n = clean_name_for(sym)
        return (n or sym).strip()
    except Exception:
        return sym


def _tokens(sym: str, name: str) -> list:
    """Distinctive tokens that must appear in a TITLE to count as a match.

    Drops corporate-form words: "India Ltd" would otherwise match half the feed.
    """
    stop = {"ltd", "limited", "india", "indian", "corp", "corporation", "company",
            "industries", "enterprises", "holdings", "group", "the", "and", "of",
            "services", "technologies", "products", "international"}
    toks = [t for t in re.split(r"[^A-Za-z0-9]+", f"{name}") if len(t) > 3]
    toks = [t for t in toks if t.lower() not in stop]
    return sorted({*toks, sym}, key=len, reverse=True)


def _articles_for(sym: str, entries: list) -> list:
    """Company-specific headlines only: named in the title, not a market wrap."""
    name = _clean_name(sym)
    toks = _tokens(sym, name)
    seen, out = set(), []
    for e in entries:
        title = (e.get("title") or "").strip()
        if not title or GENERIC.search(title):
            continue
        key = title.lower()
        if key in seen:
            continue
        if any(re.search(rf"\b{re.escape(t)}\b", title, re.I) for t in toks):
            seen.add(key)
            out.append({"title": title, "link": e.get("link", ""),
                        "published": e.get("published", "")})
    return out


def classify(arts: list) -> tuple:
    """(verdict, score, n, why) for one stock's headlines."""
    if not arts:
        return "NO_NEWS", float("nan"), 0, "no company-specific coverage"
    try:
        from sentiment_pipeline import score_text
    except Exception:
        return "NO_SCORER", float("nan"), len(arts), "sentiment_pipeline unavailable"

    scores = [score_text(a["title"]) for a in arts]
    avg = sum(scores) / len(scores)
    flags = [a["title"] for a in arts if RED_FLAG.search(a["title"])]

    # A red-flag headline outranks the average. Three routine positives should
    # not bury one auditor resignation — averaging is what makes that happen.
    if flags:
        return "DIVERGENT", avg, len(arts), f"material: {flags[0][:70]}"
    if avg <= -0.15:
        return "DIVERGENT", avg, len(arts), "negative coverage"
    if avg >= 0.15:
        return "CONVERGENT", avg, len(arts), "positive coverage"
    return "NEUTRAL", avg, len(arts), "routine coverage"


def main() -> int:
    ap = argparse.ArgumentParser(description="News convergence for today's filter passes")
    ap.add_argument("--market", default="IN", help="Moneycontrol/ET/Mint cover India")
    ap.add_argument("--top", type=int, default=30, help="cap names checked")
    ap.add_argument("--date", help="signal date (default: today)")
    ap.add_argument("--out")
    a = ap.parse_args()

    if not LEDGER.exists():
        print("  no signal ledger — run signal_tracker.py --record first"); return 1
    led = pd.read_parquet(LEDGER)
    led["signal_date"] = pd.to_datetime(led["signal_date"])
    day = pd.Timestamp(a.date) if a.date else pd.Timestamp(date.today())
    sub = led[(led["signal_date"] == day) & (led["market"] == a.market.upper())]
    if sub.empty:
        print(f"  no {a.market} filter passes on {day:%Y-%m-%d}"); return 0

    # Strongest first — but TIE-BROKEN BY HASH, not by ledger order.
    #
    # Filter scores are coarse and heavily tied (41 of 102 names scored exactly
    # 7.0 on 2026-07-21). pandas' sort is STABLE, so within a tie it preserves
    # the input order, and the ledger inherits the factor panel's alphabetical
    # order. `head(25)` therefore returned twenty-five names beginning with A —
    # a clean alphabetical sample masquerading as "the strongest 25", which is
    # the same defect that made the US price panel unusable.
    #
    # A hash of the symbol is deterministic (same input, same sample — still
    # reproducible) but uncorrelated with the alphabet.
    sub = sub.drop_duplicates(subset=["symbol"]).copy()
    sub["_tie"] = sub["symbol"].astype(str).map(
        lambda s: int(hashlib.md5(s.encode()).hexdigest()[:8], 16))
    sub = sub.sort_values(["score", "_tie"], ascending=[False, True]).head(a.top)
    sub = sub.drop(columns="_tie")
    print(f"  {len(sub)} {a.market} names passed a filter on {day:%Y-%m-%d}; "
          f"fetching company-specific coverage …")

    try:
        from sentiment_pipeline import IndianRSSProvider
        entries = IndianRSSProvider()._all_entries()
    except Exception as e:
        print(f"  RSS unavailable ({type(e).__name__}: {e}) — cannot check news"); return 1
    print(f"  {len(entries)} headlines in today's market-wide feed pool\n")

    rows = []
    for _, r in sub.iterrows():
        arts = _articles_for(str(r["symbol"]), entries)
        verdict, score, n, why = classify(arts)
        rows.append({"symbol": r["symbol"], "market": r["market"], "filter": r["filter"],
                     "filter_score": r.get("score"), "news_n": n,
                     "news_score": score, "verdict": verdict, "why": why,
                     "headline": arts[0]["title"] if arts else ""})
    d = pd.DataFrame(rows)

    order = ["DIVERGENT", "CONVERGENT", "NEUTRAL", "NO_NEWS", "NO_SCORER"]
    d["_o"] = d["verdict"].apply(lambda v: order.index(v) if v in order else 9)
    d = d.sort_values(["_o", "filter_score"], ascending=[True, False]).drop(columns="_o")

    print(f"  {'symbol':<14} {'filter':<16} {'verdict':<11} {'n':>3}  why")
    print("  " + "-" * 84)
    for _, r in d.iterrows():
        print(f"  {r['symbol']:<14} {str(r['filter']):<16} {r['verdict']:<11} "
              f"{r['news_n']:>3}  {str(r['why'])[:44]}")

    print()
    for v in order:
        n = int((d["verdict"] == v).sum())
        if n:
            print(f"    {v:<11} {n:>3}")

    div = d[d["verdict"] == "DIVERGENT"]
    if len(div):
        print(f"\n  ⚠ {len(div)} DIVERGENT — technically strong, but the tape says otherwise:")
        for _, r in div.iterrows():
            print(f"     {r['symbol']:<12} {str(r['headline'])[:78]}")
    else:
        print("\n  No divergences. Note that this is the expected result on most days —")
        print("  it is not evidence the filters are working.")

    nn = int((d["verdict"] == "NO_NEWS").sum())
    if nn:
        print(f"\n  {nn} of {len(d)} have NO company-specific coverage. That is not a")
        print("  clean bill of health — most Indian small caps are simply never written")
        print("  about, so silence and safety look identical here.")

    print("\n  CONVERGENT does NOT mean the filter worked. Only forward returns can")
    print("  say that — see signal_tracker.py --report. This checks whether anything")
    print("  publicly known contradicts a pick the filter could not see.")

    if a.out:
        p = Path(a.out); p.parent.mkdir(parents=True, exist_ok=True)
        d.to_csv(p, index=False)
        print(f"\n  → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
