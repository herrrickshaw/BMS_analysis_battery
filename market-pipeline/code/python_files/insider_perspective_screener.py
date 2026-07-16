#!/usr/bin/env python3
"""
insider_perspective_screener.py — a corrected-logic rebuild of screener.in's
"Insider perspective" screen (screens/3199460), using data already in this
pipeline where possible.

THE BUG THIS FIXES: the source screen's formula, written without
parentheses —

    Profit growth 3Years > 10 OR
    Profit growth 5Years > 15 OR
    Profit growth 7Years > 20 AND
    Dividend last year > 0 AND
    Return on capital employed > 10% AND
    PB X PE <25 AND
    Change in DII holding 3Years > 1 AND
    Change in FII holding 3Years >1 AND
    Return on capital employed >25%

— gets parsed by screener.in's left-to-right OR/AND chaining as
    A OR B OR (C AND D AND E AND F AND G AND H AND I)
not the intended
    (A OR B OR C) AND D AND E AND F AND G AND H AND I
so the 3-year and 5-year growth branches carry NO other condition at all.
Confirmed empirically: the live screen returns 3,394 of ~5,000 NSE/BSE
stocks (~68% of the exchange), and includes names like Energy InfrTrust
(ROCE 5.39%) and Vedanta (ROCE 16.08%) that fail BOTH ROCE thresholds in
the formula — they could only appear via the unconstrained OR branches.

THIS SCRIPT implements the INTENDED logic instead:
    (3Y growth > 10% OR 5Y growth > 15% OR 7Y growth > 20%)
    AND dividend paid last year
    AND ROCE > 25%                 (the redundant ">10%" clause is dropped —
                                     it's strictly dominated by ">25%" ANDed
                                     onto the same variable, dead weight even
                                     in a correctly-grouped reading)
    AND PB * PE < 25

KNOWN GAP: Change in DII/FII holding (3-year) is NOT implemented — this
repo has no NSE shareholding-pattern collector (a genuinely different data
source from anything built this session: quarterly disclosure filings of
promoter/DII/FII/public holding %, not covered by earnings_dates_nse.py,
which only pulls board-meeting/results dates). Flagged here rather than
faked; a real follow-up would extend earnings_dates_nse.py's pattern to
NSE's shareholding-pattern API.

DATA: cache_seed/fundamentals_history/IN.parquet (screener.in-derived,
already has `roce` computed) for growth/ROCE — only 75 tickers, the same
screener.in-collection-blocked limitation flagged throughout this session
(project memory). PE/PB/dividend fetched live via yahooquery for the same
75 tickers (cheap — one small batch, not the multi-thousand-symbol scale
of the earlier PEAD work).

Usage:
    python3 insider_perspective_screener.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FUND_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/IN.parquet"

GROWTH_HURDLES = {3: 0.10, 5: 0.15, 7: 0.20}   # years -> CAGR hurdle
ROCE_HURDLE = 0.25            # the single non-redundant ROCE bar
PB_X_PE_CAP = 25.0


def _cagr(df: pd.DataFrame, years: int) -> pd.Series:
    """Trailing N-fiscal-year net_income CAGR per ticker, using whatever
    fy_end rows are available (screener.in-derived, annual granularity)."""
    df = df.sort_values(["ticker", "fy_end"])
    g = df.groupby("ticker")
    first = g["net_income"].shift(years - 1)
    last = df["net_income"]
    n_periods = years - 1
    with np.errstate(invalid="ignore", divide="ignore"):
        cagr = np.where((first > 0) & (last > 0), (last / first) ** (1 / n_periods) - 1, np.nan)
    return pd.Series(cagr, index=df.index)


def build_fundamentals_side() -> pd.DataFrame:
    df = pd.read_parquet(FUND_PATH)
    for c in ["net_income", "roce"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["ticker", "fy_end"])

    df["cagr_3y"] = _cagr(df, 3)
    df["cagr_5y"] = _cagr(df, 5)
    df["cagr_7y"] = _cagr(df, 7)

    latest = df.groupby("ticker").last().reset_index()
    growth_pass = (
        (latest["cagr_3y"] > GROWTH_HURDLES[3]) |
        (latest["cagr_5y"] > GROWTH_HURDLES[5]) |
        (latest["cagr_7y"] > GROWTH_HURDLES[7])
    )
    roce_pass = latest["roce"] > ROCE_HURDLE * 100 if latest["roce"].max() > 1.5 else latest["roce"] > ROCE_HURDLE

    out = latest[["ticker", "fy_end", "cagr_3y", "cagr_5y", "cagr_7y", "roce"]].copy()
    out["growth_pass"] = growth_pass.values
    out["roce_pass"] = roce_pass.values
    return out


def fetch_market_side(tickers: list[str]) -> pd.DataFrame:
    """trailingPE + dividendYield live in .summary_detail; priceToBook lives
    in .key_stats (a separate yahooquery endpoint/call) — confirmed live,
    summary_detail's own 'priceToBook'-shaped keys are always null."""
    from yahooquery import Ticker
    yf_syms = [f"{t}.NS" for t in tickers]
    t = Ticker(yf_syms, asynchronous=True, max_workers=8)
    summary = t.summary_detail
    key_stats = t.key_stats
    rows = []
    for sym, orig in zip(yf_syms, tickers):
        sdata = summary.get(sym) if isinstance(summary, dict) else None
        kdata = key_stats.get(sym) if isinstance(key_stats, dict) else None
        pe = sdata.get("trailingPE") if isinstance(sdata, dict) else None
        div = sdata.get("dividendYield") if isinstance(sdata, dict) else None
        pb = kdata.get("priceToBook") if isinstance(kdata, dict) else None
        rows.append({"ticker": orig, "pe": pe, "pb": pb, "dividend_yield": div})
    return pd.DataFrame(rows)


def main():
    fund = build_fundamentals_side()
    print(f"Fundamentals side: {len(fund)} tickers, {fund['growth_pass'].sum()} pass the growth-OR "
          f"gate, {fund['roce_pass'].sum()} pass ROCE>25%")

    market = fetch_market_side(fund["ticker"].tolist())
    df = fund.merge(market, on="ticker", how="left")
    df["pb"] = pd.to_numeric(df["pb"], errors="coerce")
    df["pe"] = pd.to_numeric(df["pe"], errors="coerce")
    df["dividend_yield"] = pd.to_numeric(df["dividend_yield"], errors="coerce")

    df["pb_x_pe"] = df["pb"] * df["pe"]
    df["valuation_pass"] = (df["pb_x_pe"] > 0) & (df["pb_x_pe"] < PB_X_PE_CAP)
    df["dividend_pass"] = df["dividend_yield"].fillna(0) > 0

    df["PASSES_CORRECTED_SCREEN"] = (
        df["growth_pass"] & df["roce_pass"] & df["valuation_pass"] & df["dividend_pass"]
    )
    # For comparison: what the BUGGY left-to-right parse effectively returns
    # on this same universe (growth-only, no other condition)
    df["passes_buggy_growth_only"] = df["growth_pass"]

    print("\n" + "=" * 78)
    print(f"CORRECTED screen: {df['PASSES_CORRECTED_SCREEN'].sum()}/{len(df)} pass "
          f"(vs. buggy growth-only: {df['passes_buggy_growth_only'].sum()}/{len(df)})")
    print("=" * 78)
    passing = df[df["PASSES_CORRECTED_SCREEN"]].sort_values("roce", ascending=False)
    cols = ["ticker", "cagr_3y", "cagr_5y", "cagr_7y", "roce", "pe", "pb", "pb_x_pe", "dividend_yield"]
    if not passing.empty:
        print(passing[cols].to_string(index=False))
    else:
        print("(none — expected on a 75-ticker sample this thin; see caveats)")

    print("\nGap not implemented: Change in DII/FII holding (3Y) — no NSE shareholding-pattern "
          "collector exists in this repo yet. All results above are the growth+dividend+ROCE+"
          "valuation subset only.")
    df.to_csv("cache_seed/insider_perspective_screener_results.csv", index=False)


if __name__ == "__main__":
    main()
