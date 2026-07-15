#!/usr/bin/env python3
# compare_screener_vs_yfinance.py
# ================================
# Empirically compares, for the same NSE stock on the same day, the fundamental
# ratios screener.in reports (scraped from its public company page's "top ratios"
# block) against the equivalent yfinance `.info` fields.
#
# This turns the *documented* structural differences (see ASSUMPTIONS.md,
# SCREENER_LITERATURE_LOG.md, feedback_yfinance_api memory) into a measured,
# per-ticker discrepancy table: same metric, two sources, how far apart are they.
#
#   from compare_screener_vs_yfinance import run_comparison
#   df = run_comparison(["RELIANCE", "TCS", "INFY"])
#
# screener.in has no public API and throttles hard (~2.6 req/min before a block
# per prior sessions' findings) — this script is single-threaded with a
# deliberate delay between requests. Do not parallelize against screener.in.

from __future__ import annotations

import argparse
import re
import time
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

warnings.filterwarnings("ignore")

_UA = {"User-Agent": "Mozilla/5.0 (research)"}
_COMPANY_URL = "https://www.screener.in/company/{symbol}/consolidated/"

_yf_session = None  # lazily-built, reused across all yfinance calls in this run


def _get_yf_session():
    """Chrome-impersonated curl_cffi session — the documented throttle bypass
    for Yahoo's datacenter-IP/bot-detection block (see project memory: 'curl_cffi
    ... is the throttle bypass for all collectors'). Falls back to yfinance's
    default session if curl_cffi isn't installed, so this stays optional."""
    global _yf_session
    if _yf_session is None:
        try:
            from curl_cffi import requests as cffi_requests

            _yf_session = cffi_requests.Session(impersonate="chrome")
        except ImportError:
            _yf_session = False  # sentinel: "tried, not available"
    return _yf_session or None
_LI_RE = re.compile(r'<li class="flex flex-space-between"[^>]*>(.*?)</li>', re.S)
_NAME_RE = re.compile(r'<span class="name">\s*(.*?)\s*</span>', re.S)
_NUM_RE = re.compile(r'<span class="number">([^<]*)</span>')

# screener.in "top ratios" label -> our column name
_SCREENER_FIELD_MAP = {
    "market cap": "market_cap_cr",
    "current price": "cmp",
    "stock p/e": "pe",
    "book value": "book_value",
    "dividend yield": "div_yield_pct",
    "roce": "roce_pct",
    "roe": "roe_pct",
    "face value": "face_value",
}


def _to_number(raw: str) -> Optional[float]:
    """'17,53,627' / '22.5' / '' -> float or None."""
    raw = raw.replace(",", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def fetch_screener_ratios(symbol: str, timeout: int = 20) -> dict:
    """Scrape screener.in's top-ratios block for one NSE symbol.

    Returns {} on any failure (missing page, blocked, unexpected markup) rather
    than raising, so a bad ticker doesn't kill a batch run.
    """
    url = _COMPANY_URL.format(symbol=symbol.upper())
    try:
        r = requests.get(url, headers=_UA, timeout=timeout)
    except requests.RequestException as e:
        return {"_error": f"request failed: {e}"}
    if r.status_code != 200:
        return {"_error": f"HTTP {r.status_code}"}

    m = re.search(r'id="top-ratios".*?</ul>', r.text, re.S)
    if not m:
        return {"_error": "top-ratios block not found (blocked page or bad symbol?)"}
    block = m.group(0)

    out: dict = {}
    for li in _LI_RE.findall(block):
        name_m = _NAME_RE.search(li)
        if not name_m:
            continue
        label = re.sub(r"\s+", " ", name_m.group(1)).strip().lower()
        col = _SCREENER_FIELD_MAP.get(label)
        if col is None:
            continue
        nums = _NUM_RE.findall(li)
        if not nums:
            continue
        # "High / Low" is the only two-number field; nothing we map has two.
        out[col] = _to_number(nums[0])
    return out


def _pct(value) -> Optional[float]:
    """yfinance returns ratios like ROE as a 0-1 fraction; screener.in reports %."""
    if value is None:
        return None
    return round(value * 100, 4)


def fetch_yfinance_ratios(symbol: str) -> dict:
    """Equivalent ratios from yfinance `.info` for one NSE symbol (adds .NS)."""
    import yfinance as yf  # local import: keep this importable without yfinance too

    try:
        info = yf.Ticker(f"{symbol.upper()}.NS", session=_get_yf_session()).info
    except Exception as e:  # yfinance raises a variety of network/parse errors
        return {"_error": f"yfinance failed: {e}"}
    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        return {"_error": "empty/invalid yfinance info"}

    market_cap = info.get("marketCap")
    roe = info.get("returnOnEquity")

    out = {
        "market_cap_cr": round(market_cap / 1e7, 2) if market_cap else None,
        "cmp": info.get("currentPrice") or info.get("regularMarketPrice"),
        "pe": info.get("trailingPE"),
        "book_value": info.get("bookValue"),
        "div_yield_pct": _dividend_yield_pct(info.get("dividendYield")),
        "roce_pct": _yf_roce_pct(symbol),
        "roe_pct": _pct(roe),
        "face_value": None,  # yfinance has no equivalent field
    }
    return out


def _dividend_yield_pct(raw) -> Optional[float]:
    """yfinance has shipped dividendYield both as a 0-1 fraction and as a raw
    percent number across versions. Validated live against yfinance 1.2.0
    (2026-07): RELIANCE returned 0.46 (screener.in also says 0.46%) and TCS
    returned 3.14 (screener.in 2.93%) — i.e. this version already returns a
    percent, not a fraction. A real fraction would show as <0.02 for any
    plausible Indian-stock yield (>2% fraction = 200%+ yield), so only rescale
    in that narrow band; everything else is left as-is."""
    if raw is None:
        return None
    return round(raw * 100, 4) if raw < 0.02 else round(raw, 4)


def _yf_roce_pct(symbol: str) -> Optional[float]:
    """Best-effort ROCE = EBIT / (Total Assets - Current Liabilities) from
    yfinance's financial statements, so screener.in's ROCE (a number it computes
    internally) has something to be checked against rather than skipped.
    Returns None on any missing field — this is a bonus metric, not required."""
    import yfinance as yf

    try:
        t = yf.Ticker(f"{symbol.upper()}.NS", session=_get_yf_session())
        inc = _first_df(t, "income_stmt", "financials")
        bal = _first_df(t, "balance_sheet")
        if inc is None or bal is None:
            return None
        ebit = _first_row(inc, ["EBIT", "Operating Income"])
        total_assets = _first_row(bal, ["Total Assets"])
        current_liab = _first_row(bal, ["Current Liabilities", "Total Current Liabilities"])
        if ebit is None or total_assets is None or current_liab is None:
            return None
        capital_employed = total_assets - current_liab
        if not capital_employed:
            return None
        return round(ebit / capital_employed * 100, 4)
    except Exception:
        return None


def _first_df(ticker, *attrs):
    """Same pattern as the codebase's documented yfinance DataFrame-truthiness
    fix: never `or` two DataFrames, check is-not-None/not-empty explicitly."""
    for attr in attrs:
        df = getattr(ticker, attr, None)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            return df
    return None


def _first_row(df: pd.DataFrame, labels: list) -> Optional[float]:
    for label in labels:
        if label in df.index:
            val = df.loc[label].iloc[0]
            if pd.notna(val):
                return float(val)
    return None


_COMPARE_COLS = ["market_cap_cr", "cmp", "pe", "book_value", "div_yield_pct", "roce_pct", "roe_pct"]


def compare_ticker(symbol: str, delay: float = 3.0) -> dict:
    """One ticker, both sources, merged + diffed. `delay` is applied *before*
    the screener.in request (caller-side throttle), not after."""
    time.sleep(delay)
    screener = fetch_screener_ratios(symbol)
    yf_data = fetch_yfinance_ratios(symbol)

    row = {"symbol": symbol.upper()}
    row["screener_error"] = screener.get("_error")
    row["yfinance_error"] = yf_data.get("_error")

    for col in _COMPARE_COLS:
        s_val = screener.get(col)
        y_val = yf_data.get(col)
        row[f"{col}_screener"] = s_val
        row[f"{col}_yfinance"] = y_val
        if s_val is not None and y_val is not None:
            row[f"{col}_diff"] = round(y_val - s_val, 4)
            row[f"{col}_pct_diff"] = round((y_val - s_val) / s_val * 100, 2) if s_val else None
        else:
            row[f"{col}_diff"] = None
            row[f"{col}_pct_diff"] = None
    return row


def run_comparison(symbols: list, delay: float = 3.0, verbose: bool = True) -> pd.DataFrame:
    rows = []
    for i, sym in enumerate(symbols, 1):
        if verbose:
            print(f"  [{i}/{len(symbols)}] {sym} ...", end=" ", flush=True)
        row = compare_ticker(sym, delay=delay)
        rows.append(row)
        if verbose:
            errs = [e for e in (row["screener_error"], row["yfinance_error"]) if e]
            print("OK" if not errs else f"issues: {errs}")
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> None:
    """Print median absolute %-diff per metric across all tickers that had both
    sources populated — the headline "how far apart do these sources run"."""
    print("\nMedian |%diff| (yfinance vs screener.in), non-null pairs only:")
    for col in _COMPARE_COLS:
        pct_col = f"{col}_pct_diff"
        vals = df[pct_col].dropna().abs()
        n = len(vals)
        if n == 0:
            print(f"  {col:16s}  no comparable pairs")
            continue
        print(f"  {col:16s}  median={vals.median():6.2f}%   n={n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["RELIANCE", "TCS", "INFY", "HDFCBANK", "TATASTEEL"],
                     help="NSE symbols (bare, no .NS suffix)")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between screener.in requests")
    ap.add_argument("--out", default=None, help="output CSV path (default: cache_seed/screener_vs_yfinance.csv)")
    args = ap.parse_args()

    result = run_comparison(args.symbols, delay=args.delay)
    summarize(result)

    out_path = Path(args.out) if args.out else Path(__file__).parent / "cache_seed" / "screener_vs_yfinance.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    print(f"\nsaved -> {out_path}")
