#!/usr/bin/env python3
# data_sources.py
# ===============
# Redundant OHLC sourcing with an ordered fallback chain, so a Yahoo Finance
# rate-limit (429 / "Invalid Crumb") no longer breaks data collection.
#
# Chain (first that returns data for a ticker wins):
#   1. Stooq        — free, no key, global EOD CSV (https://stooq.com)         [backup]
#   2. Yahoo        — yfinance bulk download                                   [primary]
#   (India is sourced separately from official NSE/BSE bhavcopy — see
#    bhavcopy_history.py — and does not go through this chain.)
#
# fetch() runs the requested order, collects misses after each source, and tries
# the next source only for the still-missing tickers. Returns {ticker: OHLCV df}.
#
# Government/official EOD-by-exchange endpoints (NSE/BSE bhavcopy, SGX, KRX, JPX)
# are the most reliable primaries; this module focuses on the cross-market price
# backups that need no API key. Add keyed providers (Tiingo/AlphaVantage) below.

from __future__ import annotations

import io
import warnings
from typing import Dict, List

import pandas as pd
import requests

warnings.filterwarnings("ignore")

try:
    from stock_utils import bulk_download as _yahoo_bulk, clean_ohlcv
except ImportError:
    _yahoo_bulk = None
    clean_ohlcv = None

_UA = {"User-Agent": "Mozilla/5.0 (market-research)"}


# ── Stooq (free, no key) ───────────────────────────────────────────────────────
def _stooq_symbol(t: str) -> str | None:
    """Map a yfinance ticker to a Stooq symbol (covers the markets Stooq carries)."""
    suffix_map = {".T": ".jp", ".L": ".uk", ".DE": ".de", ".F": ".de", ".PA": ".fr",
                  ".AS": ".nl", ".BR": ".be", ".MI": ".it", ".MC": ".es", ".HK": ".hk",
                  ".SW": ".ch", ".ST": ".se"}
    for yf_suf, st_suf in suffix_map.items():
        if t.endswith(yf_suf):
            return t[:-len(yf_suf)].lower() + st_suf
    if "." not in t:                       # bare ticker → US
        return t.lower() + ".us"
    return None                            # unsupported on Stooq (e.g. .NS/.SI/.SS/.KS)


def stooq_fetch(tickers: List[str], min_bars: int = 60,
                verbose: bool = True) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    sess = requests.Session(); sess.headers.update(_UA)
    for t in tickers:
        s = _stooq_symbol(t)
        if not s:
            continue
        try:
            r = sess.get(f"https://stooq.com/q/d/l/?s={s}&i=d", timeout=20)
            if r.status_code != 200 or not r.text.startswith("Date"):
                continue                   # HTML / limit page → treat as miss
            df = pd.read_csv(io.StringIO(r.text))
            if df.empty or "Close" not in df.columns:
                continue
            df = df.rename(columns=str.capitalize)
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
            if clean_ohlcv is not None:
                df = clean_ohlcv(df, ticker=t, min_bars=min_bars)
            if df is not None and len(df) >= min_bars:
                out[t] = df
        except Exception:
            continue
    if verbose:
        print(f"    stooq: {len(out)}/{len(tickers)} fetched")
    return out


# ── Yahoo ──────────────────────────────────────────────────────────────────────
def yahoo_fetch(tickers: List[str], period: str = "1y", min_bars: int = 60,
                verbose: bool = True) -> Dict[str, pd.DataFrame]:
    if _yahoo_bulk is None:
        return {}
    return _yahoo_bulk(tickers, period=period, batch_size=80,
                       min_bars=min_bars, verbose=verbose)


SOURCES = {"stooq": stooq_fetch, "yahoo": yahoo_fetch}


def fetch(tickers: List[str], order=("yahoo", "stooq"), period: str = "1y",
          min_bars: int = 60, verbose: bool = True) -> Dict[str, pd.DataFrame]:
    """Fetch OHLC with fallback. Tries sources in `order`; each source only
    handles the tickers still missing after the previous one."""
    result: Dict[str, pd.DataFrame] = {}
    pending = list(dict.fromkeys(tickers))
    for src in order:
        if not pending:
            break
        fn = SOURCES.get(src)
        if fn is None:
            continue
        if verbose:
            print(f"  source '{src}': attempting {len(pending)} tickers …")
        kw = dict(min_bars=min_bars, verbose=verbose)
        if src == "yahoo":
            kw["period"] = period
        got = fn(pending, **kw)
        result.update(got)
        pending = [t for t in pending if t not in result]
    if verbose:
        print(f"  multi-source total: {len(result)}/{len(tickers)} "
              f"({len(pending)} unresolved)")
    return result


if __name__ == "__main__":
    import sys
    ts = sys.argv[1:] or ["AAPL", "MSFT", "7203.T"]
    h = fetch(ts, order=("yahoo", "stooq"), period="6mo", min_bars=30)
    for t, d in h.items():
        print(f"  {t}: {len(d)} bars, last {str(d.index[-1])[:10]} {d['Close'].iloc[-1]:.2f}")
