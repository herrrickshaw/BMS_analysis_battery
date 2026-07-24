#!/usr/bin/env python3
"""
sell_news.py — link a SELL signal to the news flow so an exit is news-aware.

When the digest recommends SELL (or a name is being evicted), a purely technical
signal is worth more if the tape agrees. This reverse-matches the holding's name
against the live RSS pool (same machinery as news_picks.py) and classifies the
exit:

  news-confirmed    — negative headlines back the technical sell  (high-conviction exit)
  technical-only    — no news catalyst; the sell is pure price action
  news-contradicts  — positive headlines despite the sell         (maybe transient — reconsider)

RSS pools exist for IN and US only; other markets return technical-only.
Everything is wrapped so a news/network failure never breaks the mailer.

    from sell_news import annotate_sell_news
    annotate_sell_news(rows)     # sets r['sell_news'] and r['sell_catalyst']
"""
from __future__ import annotations
from typing import Optional

_NEWS_MARKETS = ("IN", "US")
_INDEX_CACHE: dict = {}          # market -> list[{title, up, score, outlet}]


def _index(market: str) -> list:
    """Scored article pool for a market, built once per process."""
    if market in _INDEX_CACHE:
        return _INDEX_CACHE[market]
    arts: list = []
    try:
        from sentiment_pipeline import SentimentPipeline, score_text
        sp = SentimentPipeline()
        rss = sp._rss_us if market == "US" else (sp._rss_in if market == "IN" else None)
        if rss is not None:
            for e in rss._all_entries() or []:
                title = e.get("title", "")
                raw = f"{title}. {e.get('summary', '')}"
                arts.append({"title": title, "up": title.upper(),
                             "score": score_text(raw), "outlet": e.get("outlet", "")})
    except Exception:
        arts = []
    _INDEX_CACHE[market] = arts
    return arts


def news_for(name: str, market: str, symbol: Optional[str] = None) -> Optional[dict]:
    """Most-relevant (for an exit: most NEGATIVE) headline mentioning the name,
    plus the average sentiment across all its title mentions. None if no match."""
    arts = _index(market)
    if not arts:
        return None
    try:
        from news_picks import _distinctive_phrase
        from sentiment_pipeline import label_of
    except Exception:
        return None
    pat, _ = _distinctive_phrase(name or symbol or "")
    if pat is None:
        return None
    hits = [a for a in arts if pat.search(a["up"])]
    if not hits:
        return None
    worst = min(hits, key=lambda a: a["score"])       # the sell-relevant headline
    avg = sum(a["score"] for a in hits) / len(hits)
    return {"headline": worst["title"][:120], "outlet": worst["outlet"],
            "score": round(avg, 2), "worst_score": round(worst["score"], 2),
            "label": label_of(avg), "mentions": len(hits)}


def _catalyst(nf: Optional[dict]) -> str:
    if nf is None:
        return "technical-only"
    if nf["score"] < -0.05:
        return "news-confirmed"
    if nf["score"] > 0.15:
        return "news-contradicts"
    return "mixed"


def annotate_sell_news(rows: list, markets=_NEWS_MARKETS) -> None:
    """For every row the digest wants to exit (rec==SELL or status==evicted),
    attach r['sell_news'] (dict or None) and r['sell_catalyst'] (str). Never
    raises — a failed lookup just yields 'technical-only'."""
    for r in rows:
        try:
            if r.get("market") not in markets:
                continue
            rec = str(r.get("rec", "")).upper()
            status = str(r.get("status", "")).lower()
            if rec != "SELL" and status != "evicted":
                continue
            nf = news_for(r.get("name") or r.get("symbol"), r["market"], r.get("symbol"))
            r["sell_news"] = nf
            r["sell_catalyst"] = _catalyst(nf)
        except Exception:
            r["sell_catalyst"] = "technical-only"


if __name__ == "__main__":
    # smoke test: classify a couple of names against today's IN/US news pool
    for mkt, nm, sym in [("IN", "Reliance Industries", "RELIANCE"),
                         ("US", "Nvidia", "NVDA")]:
        print(mkt, sym, "->", news_for(nm, mkt, sym))
