#!/usr/bin/env python3
"""
price_adjuster.py — split/bonus-adjusted prices for the India warehouse,
validated against yfinance's independent adjustment.

THE DEFECT THIS FIXES
---------------------
The warehouse holds RAW closes (official bhavcopy, as printed). Through a 10:1
face-value split, a raw series shows the price dividing by 5 overnight — which a
return computation reads as an -80% crash, and a screener reads as a breakdown.
Measured cost (reference_deep_10y_market_data): splits faked a +12.2% illiquid
premium with 248% sd in one backtest; the filter collapsed it to 29%.

FACTORS, from the harvested corporate-actions history (23,480 actions to 2015):
    split "From Rs F To Rs T"  -> pre-ex prices x (T/F)     (10->2 = x0.2)
    bonus "m:n"                -> pre-ex prices x n/(m+n)   (1:1  = x0.5)
Factors COMPOUND walking backward: a 2019 split and a 2023 bonus both scale a
2018 price. Dividends are NOT adjusted (that is a total-return series — a
different, later artifact); splits and bonuses are the return-CORRUPTING events.

VALIDATION IS THE POINT
-----------------------
Every adjusted symbol with an event can be cross-checked against yfinance's
independently-adjusted series: the cumulative return ACROSS the ex-date must
match between our adjusted series and yfinance's Adj-style closes. --validate
does exactly that on the symbols with recent events. Raw returns across the
same window will disagree wildly — that disagreement is the bug being fixed.

OUTPUT
    warehouse/ohlcv_adj/IN/year=YYYY.parquet   adjusted OHLC + factor column
    warehouse/adjustment_factors.parquet       (symbol, ex_date, kind, factor)

    price_adjuster.py                  # build factors + adjusted partitions
    price_adjuster.py --validate 5     # cross-check vs yfinance across events
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import data_registry as _R
    CA = _R.MARKET_CACHE / "exchange_extras" / "corp_actions_history.parquet"
except Exception:
    CA = Path("cache_seed/exchange_extras/corp_actions_history.parquet")

WH = Path("/Users/umashankar/repos/global-market-data/warehouse")
SRC = WH / "ohlcv" / "IN"
DST = WH / "ohlcv_adj" / "IN"
FACTORS_PQ = WH / "adjustment_factors.parquet"

SPLIT_RE = re.compile(
    r"From\s+R[se]\.?\s*([\d.]+)/?-?\s*(?:Per Share)?\s*To\s+R[se]\.?\s*([\d.]+)", re.I)
BONUS_RE = re.compile(r"Bonus\s+(\d+)\s*:\s*(\d+)", re.I)


def build_factors() -> pd.DataFrame:
    ca = pd.read_parquet(CA)
    ca["exDate"] = pd.to_datetime(ca["exDate"], format="%d-%b-%Y", errors="coerce")
    rows = []
    for _, r in ca.iterrows():
        subj = str(r.get("subject", ""))
        sym = str(r.get("symbol", "")).upper()
        ex = r["exDate"]
        if not sym or pd.isna(ex):
            continue
        m = SPLIT_RE.search(subj)
        if m and ("split" in subj.lower() or "sub-division" in subj.lower()):
            f, t = float(m.group(1)), float(m.group(2))
            if f > 0 and t > 0 and t < f:          # a REVERSE split (t>f) is rare
                rows.append({"symbol": sym, "ex_date": ex, "kind": "split",
                             "factor": t / f, "subject": subj[:80]})
            elif f > 0 and t > f:                  # consolidation: prices multiply
                rows.append({"symbol": sym, "ex_date": ex, "kind": "reverse_split",
                             "factor": t / f, "subject": subj[:80]})
            continue
        m = BONUS_RE.search(subj)
        if m and "bonus" in subj.lower():
            b, held = int(m.group(1)), int(m.group(2))
            if b > 0 and held > 0:
                rows.append({"symbol": sym, "ex_date": ex, "kind": "bonus",
                             "factor": held / (held + b), "subject": subj[:80]})
    f = pd.DataFrame(rows).drop_duplicates(subset=["symbol", "ex_date", "kind"])
    tmp = FACTORS_PQ.with_suffix(".parquet.tmp")
    FACTORS_PQ.parent.mkdir(parents=True, exist_ok=True)
    f.to_parquet(tmp, index=False); tmp.replace(FACTORS_PQ)
    print(f"  factors: {len(f)} events "
          f"({(f.kind == 'split').sum()} splits, {(f.kind == 'bonus').sum()} bonuses, "
          f"{(f.kind == 'reverse_split').sum()} reverse) -> {FACTORS_PQ.name}")
    return f


def build_adjusted(factors: pd.DataFrame) -> None:
    """Adjusted partitions. Only symbols WITH events differ from raw; the rest
    are copied through with factor=1 so consumers can read one place."""
    d = pd.read_parquet(SRC)
    d["Date"] = pd.to_datetime(d["Date"])
    d["Symbol"] = d["Symbol"].astype(str).str.upper()

    # cumulative factor per (symbol, date): product of factors of all events
    # with ex_date AFTER the bar's date
    d["adj_factor"] = 1.0
    n_sym = 0
    for sym, ev in factors.groupby("symbol"):
        mask = d["Symbol"] == sym
        if not mask.any():
            continue
        n_sym += 1
        dates = d.loc[mask, "Date"]
        f = np.ones(len(dates))
        for _, e in ev.iterrows():
            f = np.where(dates < e["ex_date"], f * e["factor"], f)
        d.loc[mask, "adj_factor"] = f

    for c in ("Open", "High", "Low", "Close"):
        d[c] = d[c] * d["adj_factor"]
    # volume scales inversely: a 10:1 split multiplies share count
    d["Volume"] = np.where(d["adj_factor"] > 0,
                           d["Volume"] / d["adj_factor"], d["Volume"])

    DST.mkdir(parents=True, exist_ok=True)
    for y, g in d.groupby(d["Date"].dt.year):
        p = DST / f"year={y}.parquet"
        tmp = p.with_suffix(".parquet.tmp")
        g.drop(columns=[]).to_parquet(tmp, compression="zstd", index=False)
        tmp.replace(p)
    touched = (d["adj_factor"] != 1.0).sum()
    print(f"  adjusted: {len(d):,} rows written, {n_sym} symbols with events, "
          f"{touched:,} bars re-scaled -> {DST}")


def validate(n: int) -> int:
    """Cross-check vs yfinance's independent adjustment, ACROSS each event.

    For a symbol with an ex-date E, compute the return from E-10td to E+10td on
    (a) our adjusted series and (b) yfinance (auto_adjust=True). They must agree
    within tolerance; the RAW series across the same window will not — that gap
    is the artifact being removed.
    """
    import yfinance as yf
    f = pd.read_parquet(FACTORS_PQ)
    f = f[f.kind.isin(["split", "bonus"])]
    recent = f[(f.ex_date > "2024-01-01") & (f.ex_date < "2026-06-01")]
    adj = pd.read_parquet(DST)
    adj["Date"] = pd.to_datetime(adj["Date"])
    raw = pd.read_parquet(SRC)
    raw["Date"] = pd.to_datetime(raw["Date"])
    ok = bad = 0
    for _, e in recent.sort_values("ex_date", ascending=False).head(n).iterrows():
        sym, ex = e.symbol, e.ex_date
        a = adj[adj.Symbol == sym].set_index("Date")["Close"].sort_index()
        r = raw[raw.Symbol == sym].set_index("Date")["Close"].sort_index()
        try:
            y = yf.Ticker(f"{sym}.NS").history(
                start=(ex - pd.Timedelta(days=25)).strftime("%Y-%m-%d"),
                end=(ex + pd.Timedelta(days=25)).strftime("%Y-%m-%d"),
                auto_adjust=True)["Close"]
            y.index = pd.to_datetime(y.index).tz_localize(None)
        except Exception:
            continue
        # COMMON DATES ONLY. Returns over different endpoints are different
        # returns: our window and yfinance's fetch window started/ended on
        # different trading days, which alone produced 5-9pp of fake "DIFF" on
        # the first run. Both series are cut to their shared dates spanning the
        # ex-date, so the comparison is the same span on both sides.
        common = a.index.intersection(y.index)
        common = common[(common > ex - pd.Timedelta(days=20)) &
                        (common < ex + pd.Timedelta(days=20))]
        if len(common) < 6 or not (common < ex).any() or not (common >= ex).any():
            continue
        win_a, win_y = a.loc[common], y.loc[common]
        win_r = r.reindex(common).dropna()
        ra = win_a.iloc[-1] / win_a.iloc[0] - 1
        ry = win_y.iloc[-1] / win_y.iloc[0] - 1
        rr = (win_r.iloc[-1] / win_r.iloc[0] - 1) if len(win_r) > 1 else float("nan")
        good = abs(ra - ry) < 0.03
        ok += 1 if good else 0
        bad += 0 if good else 1
        print(f"  {'OK ' if good else 'DIFF'} {sym:12} {e.kind:6} ex {ex.date()} "
              f"factor {e.factor:.3f} | adj {ra:+.1%} vs yf {ry:+.1%} "
              f"| RAW would say {rr:+.1%}")
    print(f"\n  {ok} OK · {bad} DIFF  (raw-vs-adjusted gap = the artifact removed)")
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", type=int, default=0)
    a = ap.parse_args()
    f = build_factors()
    build_adjusted(f)
    if a.validate:
        return validate(a.validate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
