#!/usr/bin/env python3
# fetch_market_ohlc.py
# ====================
# Fetch ~1yr daily OHLC for the markets that don't yet have a seed cache
# (Europe, Japan, Korea, Singapore, China) and write compact per-market seeds
# (cache_seed/cleaned_long_<MKT>.parquet) in the same format as IN/US.
#
# Universe sources (reused from existing scanners where available):
#   EU — EURO_STOXX_50_META           (full_european_market_scan)
#   JP — fetch_tse_universe_jpx()      (.T, full TSE)
#   KR — build_krx_universe()          (.KS/.KQ, KOSPI+KOSDAQ)
#   SG — SGX_ALL                       (.SI, SGX)
#   CN — CSI-large-cap curated list    (.SS Shanghai / .SZ Shenzhen)
#
# OHLC via stock_utils.bulk_download (rate-limit backoff) → clean_ohlcv → seed.
#
# Usage:  python3 fetch_market_ohlc.py EU JP KR SG CN     (default: all)

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

from stock_utils import bulk_download, clean_ohlcv

SEED_DIR = Path(__file__).parent / "cache_seed"

# ── China large-cap universe (Shanghai .SS / Shenzhen .SZ) ─────────────────────
# Curated CSI-100-style set of the most liquid A-shares (no akshare/tushare here).
CN_TICKERS = [
    # Shanghai (.SS)
    "600519.SS","601318.SS","600036.SS","601166.SS","600276.SS","600900.SS",
    "601398.SS","601288.SS","601988.SS","601857.SS","600028.SS","600030.SS",
    "601628.SS","601888.SS","600887.SS","603288.SS","600309.SS","600585.SS",
    "601012.SS","688981.SS","688111.SS","603259.SS","600031.SS","601668.SS",
    "601088.SS","600048.SS","601601.SS","601138.SS","600104.SS","600009.SS",
    "601225.SS","600406.SS","601919.SS","601766.SS","600438.SS","603501.SS",
    "688041.SS","688012.SS","600690.SS","601899.SS","603986.SS","600745.SS",
    "601985.SS","601658.SS","600089.SS","601390.SS","601111.SS","600050.SS",
    # Shenzhen (.SZ)
    "300750.SZ","000858.SZ","000333.SZ","002594.SZ","000651.SZ","002415.SZ",
    "300059.SZ","000001.SZ","002475.SZ","300760.SZ","000725.SZ","002714.SZ",
    "300124.SZ","002304.SZ","000568.SZ","002352.SZ","300014.SZ","002230.SZ",
    "000002.SZ","300015.SZ","002271.SZ","300274.SZ","000063.SZ","002241.SZ",
    "300433.SZ","002007.SZ","000100.SZ","002460.SZ","300782.SZ","000538.SZ",
]


def _tickers(market: str) -> list[str]:
    if market == "EU":
        from full_european_market_scan import EURO_STOXX_50_META
        return list(EURO_STOXX_50_META.keys())
    if market == "JP":
        jp = __import__("full_japan_market_scan")
        uni = []
        try:
            uni = jp.fetch_tse_universe_jpx()
        except Exception:
            uni = []
        if not uni:
            uni = jp.fetch_tse_universe_kabupy()
        # dicts carry 'code' (e.g. 1301) and/or a prebuilt 'yf_ticker'
        return [u.get("yf_ticker") or f"{u['code']}.T" for u in uni if u.get("code") or u.get("yf_ticker")]
    if market == "KR":
        uni = __import__("full_korea_market_scan").build_krx_universe()
        return [f"{u['code']}{u.get('yf_suffix', '.KS')}" for u in uni if u.get("code")]
    if market == "SG":
        from sg_stock_daily_report import SGX_ALL
        return list(dict.fromkeys(SGX_ALL))
    if market == "CN":
        return list(dict.fromkeys(CN_TICKERS))
    raise ValueError(f"unknown market {market}")


def _write_seed(market: str, hist: dict) -> dict:
    rows = []
    for sym, d in hist.items():
        d = clean_ohlcv(d, ticker=sym, min_bars=60)
        if d is None or d.empty:
            continue
        g = d.reset_index()
        g.columns = ["Date", "Open", "High", "Low", "Close", "Volume"][:len(g.columns)]
        for c in ("Open", "High", "Low", "Close"):
            g[c] = g[c].astype("float32")
        g["Volume"] = pd.to_numeric(g["Volume"], errors="coerce").fillna(0).astype("int64")
        g["Symbol"] = sym
        rows.append(g)
    if not rows:
        return {"market": market, "symbols": 0}
    long = pd.concat(rows, ignore_index=True).sort_values(["Symbol", "Date"])
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    path = SEED_DIR / f"cleaned_long_{market}.parquet"
    long.to_parquet(path, compression="zstd", compression_level=9, index=False)
    return {"market": market, "symbols": long["Symbol"].nunique(),
            "rows": len(long), "MB": round(path.stat().st_size / 1e6, 1), "file": path.name}


def run(markets: list[str]):
    summary = {}
    for mkt in markets:
        print(f"\n{'='*60}\n  {mkt} — fetching universe + OHLC\n{'='*60}")
        try:
            tickers = _tickers(mkt)
        except Exception as e:
            print(f"  universe fetch failed: {e}"); continue
        print(f"  {len(tickers)} tickers; downloading 1y OHLC …")
        hist = bulk_download(tickers, period="1y", batch_size=80,
                             min_bars=60, verbose=True)
        summary[mkt] = _write_seed(mkt, hist)
        print(f"  → {summary[mkt]}")
    print("\nDONE:", summary)
    return summary


if __name__ == "__main__":
    mkts = [m.upper() for m in sys.argv[1:]] or ["EU", "JP", "KR", "SG", "CN"]
    run(mkts)
