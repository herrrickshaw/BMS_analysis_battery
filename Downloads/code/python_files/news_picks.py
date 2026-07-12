#!/usr/bin/env python3
"""
Share-market NEWS PICKS — stocks the street is actively talking about.

Instead of only matching news onto the fundamental screener picks (which fails
when the picks are obscure small-caps), this scans the live RSS news pool and
reverse-matches every headline against the ticker↔name symbol master, so the
report can surface the most-covered / most-positively-covered names directly
from the news flow — independent of the screeners and of convergence.

Returns a ranked list of dicts:
  {symbol, name, exchange, mentions, score, label, headline, outlet}

CLI:  python3 news_picks.py --market IN --top 12
"""
import argparse
import re

# Generic corporate-name tokens that carry no disambiguating power.
_STOP = {
    "LTD", "LIMITED", "INDIA", "INDIAN", "CORP", "CORPORATION", "COMPANY", "CO",
    "GROUP", "INDUSTRIES", "INDUSTRIES.", "INC", "INC.", "THE", "AND", "NEW",
    "INTERNATIONAL", "SERVICES", "SERVICE", "PVT", "PRIVATE", "HOLDINGS",
    "HOLDING", "ENTERPRISES", "ENTERPRISE", "FINANCE", "FINANCIAL", "TECH",
    "TECHNOLOGIES", "TECHNOLOGY", "SYSTEMS", "PRODUCTS", "PRODUCT", "PLC",
    "COMPANIES", "MOTOR", "GLOBAL", "GENERAL", "NATIONAL", "STANDARD",
}

_EXCH = {"IN": ["NSE", "BSE"], "US": ["NASDAQ", "NYSE"]}

# Single tokens that are indices/exchanges or shared group surnames — too
# ambiguous to match a specific stock on their own; require a 2-token phrase.
_AMBIG_SINGLE = {"NASDAQ", "SENSEX", "NIFTY", "MAHINDRA", "BAJAJ", "BIRLA",
                 "ADANI", "AMBANI", "TATA"}


def _load_english_words() -> set:
    """Common English words — a single-token company match on one of these
    (ENERGY, CAPITAL, POWER, MOTORS, STEEL, …) is almost always a false hit."""
    words = set()
    for p in ("/usr/share/dict/words", "/usr/dict/words"):
        try:
            with open(p) as f:
                for w in f:
                    w = w.strip().lower()
                    if len(w) >= 4:
                        words.add(w)
            break
        except OSError:
            continue
    # fallback / reinforcement — finance-common words that must never single-match
    words.update({
        "energy", "capital", "power", "motors", "motor", "steel", "bank",
        "finance", "financial", "invest", "investment", "investments", "cement",
        "chemicals", "chemical", "pharma", "auto", "metals", "metal", "mining",
        "textiles", "sugar", "paper", "oil", "gas", "petroleum", "solar",
        "infra", "infrastructure", "retail", "foods", "food", "agro", "life",
        "insurance", "housing", "realty", "estate", "media", "digital", "labs",
    })
    return words


_ENGLISH = _load_english_words()


def _distinctive_phrase(name: str):
    """Return (regex, key) for a company name, or (None, None) if too generic.

    Uses the first two ≥3-char non-stopword tokens as an adjacent phrase
    (precise: 'TATA MOTORS' matches 'Tata Motors Q4' but not 'Tata Steel').
    A single leftover token is used ONLY if it is ≥5 chars and NOT a common
    English word (keeps RELIANCE/INFOSYS/WIPRO/VEDANTA, drops ENERGY/CAPITAL).
    """
    toks = [t for t in re.findall(r"[A-Z0-9&]+", name.upper())
            if len(t) >= 3 and t not in _STOP]
    if not toks:
        return None, None
    if len(toks) >= 2:
        key = f"{toks[0]} {toks[1]}"
        rx = r"\b" + re.escape(toks[0]) + r"\s+" + re.escape(toks[1]) + r"\b"
    else:
        if (len(toks[0]) < 5 or toks[0].lower() in _ENGLISH
                or toks[0] in _AMBIG_SINGLE):
            return None, None
        key = toks[0]
        rx = r"\b" + re.escape(toks[0]) + r"\b"
    return re.compile(rx), key


def news_picks(market: str, top: int = 12, min_mentions: int = 1) -> list:
    from sentiment_pipeline import SentimentPipeline, score_text, label_of
    from symbol_master import load_master

    sp = SentimentPipeline()
    rss = sp._rss_us if market == "US" else sp._rss_in
    if rss is None:
        return []
    entries = rss._all_entries()
    if not entries:
        return []

    arts = []
    for e in entries:
        raw = f"{e['title']}. {e.get('summary', '')}"
        arts.append({
            "title": e["title"],
            "title_up": e["title"].upper(),
            "text": f"{e['title']} {e.get('summary', '')}".upper(),
            "score": score_text(raw),
            "outlet": e.get("outlet", ""),
        })

    df = load_master(auto_refresh=False)
    uni = df[df["exchange"].isin(_EXCH.get(market, []))]

    picks = {}   # key -> best row (dedup NSE/BSE dual listings by phrase key)
    for _, r in uni.iterrows():
        pat, key = _distinctive_phrase(str(r["name"]))
        if pat is None:
            continue
        # Count only TITLE matches — market-moving stock news names the stock in
        # the headline. This is the key precision lever: it removes incidental
        # body mentions and most conglomerate-surname / common-word collisions.
        hits = [a for a in arts if pat.search(a["title_up"])]
        if len(hits) < min_mentions:
            continue
        scores = [a["score"] for a in hits]
        avg = sum(scores) / len(scores)
        best = (max(hits, key=lambda a: a["score"]) if avg >= 0
                else min(hits, key=lambda a: a["score"]))
        cand = {
            "symbol": r["symbol"], "name": r["name"], "exchange": r["exchange"],
            "mentions": len(hits), "score": round(avg, 2), "label": label_of(avg),
            "headline": best["title"][:100], "outlet": best["outlet"],
        }
        prev = picks.get(key)
        # keep NSE over BSE; otherwise keep the one with more mentions
        if (prev is None or
                (cand["exchange"] == "NSE" and prev["exchange"] != "NSE") or
                (cand["exchange"] == prev["exchange"] and
                 cand["mentions"] > prev["mentions"])):
            picks[key] = cand

    ranked = sorted(picks.values(), key=lambda p: (-p["mentions"], -p["score"]))
    return ranked[:top]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Share-market news picks")
    ap.add_argument("--market", choices=["IN", "US"], default="IN")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()
    for p in news_picks(args.market, args.top):
        print(f"{p['mentions']:>2}× {p['label']:<8} {p['score']:+.2f}  "
              f"{p['symbol']:<12} [{p['exchange']}]  {p['headline']}")
