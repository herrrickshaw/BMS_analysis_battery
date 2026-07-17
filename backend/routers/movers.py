"""
/api/movers — major movers + news for India (NSE) and US markets.

Data strategy (in order):
  1. Read pre-computed JSON committed to GitHub by the Actions workflow
     (data/movers/<market>.json via raw.githubusercontent.com) — always works
     from restricted cloud deployments.
  2. Fall back to live yfinance fetch when running locally with open internet.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Query

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/movers', tags=['movers'])

_GH_RAW = (
    "https://raw.githubusercontent.com/herrrickshaw/herrrickshaw"
    "/claude/event-driven-stock-news-msv0cq/data/movers/{market}.json"
)

UNIVERSE_URL = (
    "https://raw.githubusercontent.com/herrrickshaw/global-ticker-universe"
    "/main/data/global_universe_flat.csv"
)

FALLBACK_TICKERS: Dict[str, List[str]] = {
    "india": [
        "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
        "HINDUNILVR.NS","ITC.NS","SBIN.NS","BAJFINANCE.NS","BHARTIARTL.NS",
        "AXISBANK.NS","KOTAKBANK.NS","LT.NS","ASIANPAINT.NS","MARUTI.NS",
        "SUNPHARMA.NS","TITAN.NS","ULTRACEMCO.NS","WIPRO.NS","HCLTECH.NS",
        "TECHM.NS","NTPC.NS","ONGC.NS","COALINDIA.NS","TATAMOTORS.NS",
        "TATASTEEL.NS","JSWSTEEL.NS","ADANIENT.NS","ADANIPORTS.NS",
        "BAJAJFINSV.NS","DRREDDY.NS","CIPLA.NS","HEROMOTOCO.NS","BPCL.NS",
    ],
    "us": [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","UNH",
        "XOM","V","LLY","JNJ","MA","PG","HD","AVGO","CVX","MRK",
        "ABBV","COST","PEP","ADBE","AMD","NFLX","INTC","CSCO","TMO",
        "WMT","BAC","MCD","CRM","ABT","NEE","QCOM","LIN","DHR",
    ],
}


# ── GitHub pre-computed data ───────────────────────────────────────────────

def _fetch_precomputed(market: str) -> Optional[Dict]:
    url = _GH_RAW.format(market=market)
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return json.loads(r.read())
    except Exception as exc:
        log.info("Pre-computed %s not available (%s) — falling back to live", market, exc)
        return None


# ── Live fetch (requires open internet) ─────────────────────────────────────

def _load_universe_tickers(market: str, limit: int = 150) -> List[str]:
    import csv, io
    code_map = {"india": "IN", "us": "US"}
    mc = code_map.get(market, market.upper())
    try:
        with urllib.request.urlopen(UNIVERSE_URL, timeout=10) as r:
            text = r.read().decode()
        reader = csv.DictReader(io.StringIO(text))
        tickers = [row["yf_symbol"] for row in reader
                   if row.get("market_code") == mc and row.get("yf_symbol")]
        if market == "india":
            ns = [t for t in tickers if t.endswith(".NS")]
            tickers = ns or tickers
        return tickers[:limit]
    except Exception:
        return FALLBACK_TICKERS.get(market, [])


def _live_fetch_sync(market: str, top_n: int, news_n: int) -> Dict:
    import yfinance as yf
    tickers = _load_universe_tickers(market)
    if not tickers:
        return {"error": "no tickers"}

    try:
        data = yf.download(tickers, period="2d", interval="1d",
                           group_by="ticker", auto_adjust=True,
                           progress=False, threads=True)
    except Exception as exc:
        return {"error": f"yfinance: {exc}"}

    moves = []
    for t in tickers:
        try:
            closes = (data["Close"] if len(tickers) == 1
                      else data[t]["Close"] if t in data.columns.get_level_values(0)
                      else None)
            if closes is None:
                continue
            closes = closes.dropna()
            if len(closes) < 2:
                continue
            prev, last = float(closes.iloc[-2]), float(closes.iloc[-1])
            if prev == 0:
                continue
            pct = (last - prev) / prev * 100
            moves.append({
                "ticker":     t,
                "pct_change": round(pct, 2),
                "prev_close": round(prev, 2),
                "last_close": round(last, 2),
            })
        except Exception:
            continue

    moves.sort(key=lambda x: x["pct_change"], reverse=True)
    gainers = moves[:top_n]
    losers  = moves[-top_n:][::-1]

    newsapi_key = os.environ.get("NEWSAPI_KEY")
    for m in gainers + losers:
        if news_n > 0:
            m["news"] = _fetch_news(m["ticker"], news_n, newsapi_key)

    return {
        "market":     market,
        "gainers":    gainers,
        "losers":     losers,
        "source":     "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_news(ticker: str, limit: int,
                newsapi_key: Optional[str] = None) -> List[Dict]:
    import urllib.parse
    bare = ticker.replace(".NS", "").replace(".BO", "")
    if newsapi_key:
        try:
            url = ("https://newsapi.org/v2/everything?" + urllib.parse.urlencode({
                "q": bare, "language": "en", "sortBy": "publishedAt",
                "pageSize": limit, "apiKey": newsapi_key,
            }))
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            arts = [
                {"title":     a.get("title",""),
                 "publisher": (a.get("source") or {}).get("name",""),
                 "link":      a.get("url",""),
                 "published": a.get("publishedAt","")}
                for a in data.get("articles",[])
            ]
            if arts:
                return arts
        except Exception:
            pass
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news or []
        return [
            {"title":     a.get("title",""),
             "publisher": a.get("publisher",""),
             "link":      a.get("link",""),
             "published": datetime.utcfromtimestamp(a["providerPublishTime"]).strftime(
                 "%Y-%m-%dT%H:%M:%SZ") if a.get("providerPublishTime") else ""}
            for a in raw[:limit]
        ]
    except Exception:
        return []


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.get('')
async def get_movers(
    markets: str = Query('india,us'),
    top:     int = Query(10, ge=1, le=30),
    news:    int = Query(5,  ge=0, le=10),
):
    """
    Return top gainers and losers with latest news.
    Reads GitHub-committed pre-computed results first; falls back to live
    yfinance fetch when running with open internet access.
    """
    selected = [m.strip() for m in markets.split(',')
                if m.strip() in ('india', 'us')]
    if not selected:
        return {'error': 'markets must be: india, us, or india,us'}

    result: Dict = {}
    for market in selected:
        # Try pre-computed first (works from restricted cloud env)
        pre = await asyncio.to_thread(_fetch_precomputed, market)
        if pre:
            pre["source"] = "precomputed"
            result[market] = pre
            continue
        # Live fetch fallback
        data = await asyncio.to_thread(_live_fetch_sync, market, top, news)
        result[market] = data

    return result
