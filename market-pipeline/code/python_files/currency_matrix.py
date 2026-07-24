#!/usr/bin/env python3
"""
currency_matrix.py — historical FX conversion layer for the multi-currency book.

The panels, ADV, market caps and P&L live in local currency (INR/JPY/KRW/EUR/GBP);
converting them with a single spot rate is wrong across a 10y backtest (the INR
went 66->83 /USD, the JPY 100->150). This builds a DATED currency matrix from
yfinance FX history and exposes:

    usd_per(ccy, date)            USD value of 1 unit of ccy on a date
    convert(amount, frm, to, date)
    matrix(date)                  full N×N cross-rate matrix (units of col per unit of row)

Cached to cache_seed/fx_matrix.parquet (date × currency = USD per unit), forward-
filled to business days. Refresh with --refresh.

Output on run: reports/currency_matrix.md (latest matrix + a few historical snapshots).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache_seed" / "fx_matrix.parquet"
# yfinance FX ticker -> (currency, orientation). "INR=X" is USD/INR (INR per USD);
# "EURUSD=X" is USD per EUR. We normalise everything to USD-per-1-unit.
PAIRS = {
    "USD": None,                       # numeraire, = 1.0
    "INR": ("INR=X", "per_usd"),       # INR per USD  -> usd_per = 1/rate
    "JPY": ("JPY=X", "per_usd"),
    "KRW": ("KRW=X", "per_usd"),
    "CNY": ("CNY=X", "per_usd"),
    "EUR": ("EURUSD=X", "usd_per"),    # USD per EUR  -> usd_per = rate
    "GBP": ("GBPUSD=X", "usd_per"),
    "CHF": ("CHF=X", "per_usd"),
    "SEK": ("SEK=X", "per_usd"),
    "HKD": ("HKD=X", "per_usd"),
}
# desk/local-currency map for the equity panels
DESK_CCY = {"IN": "INR", "US": "USD", "JP": "JPY", "KR": "KRW", "EU": "EUR", "CN": "CNY"}


def build(period="10y") -> pd.DataFrame:
    import yfinance as yf
    cols = {}
    for ccy, spec in PAIRS.items():
        if spec is None:
            continue
        tk, orient = spec
        try:
            h = yf.Ticker(tk).history(period=period)["Close"]
            h.index = pd.to_datetime(h.index).tz_localize(None)
            cols[ccy] = (1.0 / h) if orient == "per_usd" else h
        except Exception as e:
            print(f"  {ccy} ({tk}) failed: {e}")
    fx = pd.DataFrame(cols).sort_index()
    fx["USD"] = 1.0
    fx = fx.asfreq("B").ffill()
    return fx[[c for c in PAIRS if c in fx.columns]]


def load() -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    fx = build(); fx.to_parquet(CACHE); return fx


_FX = None
def _fx():
    global _FX
    if _FX is None:
        _FX = load()
    return _FX


def usd_per(ccy: str, date=None) -> float:
    """USD value of 1 unit of `ccy` on `date` (latest if None)."""
    fx = _fx()
    if ccy not in fx.columns:
        return float("nan")
    s = fx[ccy]
    if date is None:
        return float(s.iloc[-1])
    d = pd.Timestamp(date)
    s = s[s.index <= d]
    return float(s.iloc[-1]) if len(s) else float(s.iloc[0])


def convert(amount: float, frm: str, to: str, date=None) -> float:
    return amount * usd_per(frm, date) / usd_per(to, date)


def matrix(date=None) -> pd.DataFrame:
    """N×N cross-rate matrix: entry [row, col] = units of `col` per 1 unit of `row`."""
    fx = _fx()
    ccys = list(fx.columns)
    up = {c: usd_per(c, date) for c in ccys}
    return pd.DataFrame({col: {row: up[row]/up[col] for row in ccys} for col in ccys})


def main() -> int:
    if "--refresh" in sys.argv or not CACHE.exists():
        print("building FX history from yfinance…")
        fx = build(); fx.to_parquet(CACHE)
        print(f"  wrote {CACHE} ({fx.shape[0]} days × {fx.shape[1]} ccys, "
              f"{fx.index.min().date()}→{fx.index.max().date()})")
    fx = load()
    L = ["# Historical currency matrix", "",
         f"USD-per-unit FX from yfinance, {fx.index.min().date()}→{fx.index.max().date()} "
         f"(business-day, forward-filled). Cached `cache_seed/fx_matrix.parquet`.", "",
         "## USD per 1 unit — snapshots", "",
         "| date | " + " | ".join(fx.columns) + " |", "|---|" + "--:|"*len(fx.columns)]
    for d in [fx.index[0], fx.index[len(fx)//2], fx.index[-1]]:
        L.append(f"| {d.date()} | " + " | ".join(f"{fx.loc[d,c]:.5f}" for c in fx.columns) + " |")
    m = matrix()
    L += ["", "## Latest cross-rate matrix (units of column per 1 unit of row)", "",
          "| per→ | " + " | ".join(m.columns) + " |", "|---|" + "--:|"*len(m.columns)]
    for row in m.index:
        L.append(f"| **{row}** | " + " | ".join(f"{m.loc[row,c]:.3f}" for c in m.columns) + " |")
    L += ["", "## Historical drift (USD per unit, then vs now)", "",
          "| ccy | 10y ago | now | move |", "|---|--:|--:|--:|"]
    for c in fx.columns:
        if c == "USD": continue
        old, new = fx[c].iloc[0], fx[c].iloc[-1]
        L.append(f"| {c} | {old:.5f} | {new:.5f} | {(new/old-1)*100:+.1f}% |")
    L += ["", "> Use `usd_per(ccy, date)` / `convert(amt, frm, to, date)` in any "
          "multi-currency calc (ADV→USD, market cap, cross-desk P&L, carry legs) so "
          "conversions use the period-correct rate, not a single spot."]
    (HERE / "reports" / "currency_matrix.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote reports/currency_matrix.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
