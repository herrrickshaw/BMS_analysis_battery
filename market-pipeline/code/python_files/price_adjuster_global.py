#!/usr/bin/env python3
"""
price_adjuster_global.py — heuristic split adjustment for the non-India warehouse
markets (JP / KR / CN / EU / US), validated against yfinance's independent
adjustment. Companion to price_adjuster.py (India, which has a real corporate-
actions feed; these markets do not, so events are DETECTED from the panels).

THE DEFECT (same as India's): the warehouse holds RAW closes. Through a 4:1
split a raw series shows -75% overnight — a fake crash that corrupts momentum,
breakout, and illiquidity conclusions (measured cost on IN: a fake +12.2%
illiquid premium, 248% sd). India was properly fixed 2026-07-21 via
warehouse/ohlcv_adj/IN; every other market still reads raw. This closes that gap.

DETECTION (per symbol, adjacent sessions <=14 calendar days apart):
    r = Close_t / Close_{t-1} snapped to a known split ratio
      forward:  1/2 1/3 1/4 1/5 1/6 1/8 1/10 1/20 1/25 1/50 1/100  (+3:2, 5:4)
      reverse:  2 3 4 5 6 8 10 20 25 50 100
    confirmed only if BOTH:
      persistence: median(Close t..t+4) / median(Close t-5..t-1) stays at the
                   new level (within 25% of r) — crashes keep moving, splits don't
      corroboration: ratio within 2% of exact, OR volume shifts the opposite way
                   (median vol ratio > 1.3 for forward, < 0.77 for reverse)

OUTPUT (same layout as India):
    warehouse/ohlcv_adj/<MKT>/year=YYYY.parquet    adjusted OHLC + adj_factor
    warehouse/adjustment_factors_heuristic.parquet (market, symbol, ex_date,
                                                    kind, factor, obs_ratio)

    price_adjuster_global.py                       # detect + build all markets
    price_adjuster_global.py --markets JP KR       # subset
    price_adjuster_global.py --validate 5          # yfinance cross-check/market
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

WH = Path("/Users/umashankar/repos/global-market-data/warehouse")
MARKETS = ["JP", "KR", "CN", "EU", "US"]
FACTORS_PQ = WH / "adjustment_factors_heuristic.parquet"

# ratio universe: forward splits divide the price, reverse splits multiply it.
# Integer ratios >=2 ONLY: sub-2 ratios (3:2, 5:4) are indistinguishable from
# ordinary crash days (a first run flagged 3,002 fake "5:4 splits" on -20% days).
# In JP/KR/CN daily price limits make >=2:1 overnight moves impossible without a
# corporate event, so this restriction buys near-perfect precision there.
_FWD = [2, 3, 4, 5, 6, 8, 10, 20, 25, 50, 100]
RATIOS = sorted([1 / k for k in _FWD] + [float(k) for k in _FWD])
TOL = 0.06          # snap tolerance around each ratio
EXACT = 0.02        # "exact" ratio => volume corroboration not required
PERSIST_TOL = 0.25  # post/pre median level must stay within 25% of r
RANGE_TOL = 0.12    # split day trades calmly at the new level (High/Low near it)
MAX_GAP_DAYS = 5    # sparse OTC names gap for weeks; their "overnight" moves lie
# liquidity gate on median daily TURNOVER (close x volume, local currency) —
# a share-count gate wrongly killed 7946.T (3,600 shares/day but ¥13M turnover;
# real, calendar-confirmed 5:1). Turnover separates thin-but-real JP/KR names
# from the OTC noise that fakes 2:1 moves.
MIN_TURNOVER = {"US": 5e4, "EU": 5e4, "JP": 5e6, "KR": 5e7, "CN": 5e5}
# min prior close in local currency — sub-dollar/penny names are where a $0.02
# -> $0.04 tick reads as a "2:1 split" (11/12 of first-run US hits were this)
MIN_CLOSE = {"US": 1.0, "EU": 0.5, "JP": 50.0, "KR": 500.0, "CN": 1.0}


def _candidates(market: str) -> pd.DataFrame:
    """Window-function pass over one market's panel: overnight ratio + local
    medians around each bar. Returns only bars whose ratio lands near a known
    split ratio — a few hundred rows out of millions."""
    con = duckdb.connect()
    ratio_pred = " OR ".join(
        f"(r BETWEEN {r * (1 - TOL)} AND {r * (1 + TOL)})" for r in RATIOS
    )
    q = f"""
    WITH p AS (
      SELECT Symbol, Date, Close, Volume, High, Low,
             lag(Date)  OVER w AS pdate,
             lag(Close) OVER w AS pclose,
             median(Close)  OVER (w ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS pre_med,
             median(Close)  OVER (w ROWS BETWEEN CURRENT ROW AND 4 FOLLOWING) AS post_med,
             median(Volume) OVER (w ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS pre_vol,
             median(Volume) OVER (w ROWS BETWEEN CURRENT ROW AND 4 FOLLOWING) AS post_vol
      FROM read_parquet('{WH}/ohlcv/{market}/*.parquet')
      WINDOW w AS (PARTITION BY Symbol ORDER BY Date)
    ),
    q AS (
      SELECT *, Close / pclose AS r
      FROM p
      WHERE pclose >= {MIN_CLOSE.get(market, 1.0)} AND Close > 0
        AND pclose * pre_vol >= {MIN_TURNOVER.get(market, 5e4)}
        AND Close * post_vol >= {MIN_TURNOVER.get(market, 5e4)}
        AND date_diff('day', pdate, Date) <= {MAX_GAP_DAYS}
    )
    SELECT Symbol, Date, Close, pclose, High, Low,
           pre_med, post_med, pre_vol, post_vol, r
    FROM q
    WHERE {ratio_pred}
    """
    return con.execute(q).df()


def detect(market: str) -> pd.DataFrame:
    c = _candidates(market)
    if c.empty:
        return pd.DataFrame()
    ratios = np.array(RATIOS)
    snapped = ratios[np.abs(np.log(c["r"].values[:, None] / ratios)).argmin(axis=1)]
    c["factor"] = snapped
    c["exact"] = np.abs(c["r"] / snapped - 1) < EXACT

    # persistence: the level shift must hold across the surrounding 5-day medians
    lvl = c["post_med"] / c["pre_med"]
    c = c[np.abs(np.log(lvl / c["r"])) < np.log(1 + PERSIST_TOL)]

    # calm-day guard: on a real split the WHOLE day trades near pclose*factor;
    # a crash day opens higher / ranges wide and fails this band
    new_lvl = c["pclose"] * c["factor"]
    c = c[(c["High"] <= new_lvl * (1 + RANGE_TOL)) &
          (c["Low"] >= new_lvl * (1 - RANGE_TOL))]

    # corroboration: exact ratio, or volume moving inversely to price
    vr = c["post_vol"] / c["pre_vol"].replace(0, np.nan)
    fwd = c["factor"] < 1
    vol_ok = np.where(fwd, vr > 1.3, vr < 0.77)
    c = c[c["exact"] | pd.Series(vol_ok, index=c.index).fillna(False)]

    out = c.rename(columns={"Date": "ex_date", "Symbol": "symbol", "r": "obs_ratio"})
    out["market"] = market
    out["kind"] = np.where(out["factor"] < 1, "split", "reverse_split")
    return out[["market", "symbol", "ex_date", "kind", "factor", "obs_ratio"]]


def confirm(factors: pd.DataFrame) -> pd.DataFrame:
    """Cross-check every detected event against yfinance's split calendar.
    Only calendar-confirmed events may adjust prices; unconfirmed ones are kept
    in the factors file (confirmed=False) as an audit trail."""
    import yfinance as yf
    out = []
    for sym, ev in factors.groupby("symbol"):
        try:
            s = yf.Ticker(sym).splits
            s.index = pd.to_datetime(s.index).tz_localize(None)
        except Exception:
            s = pd.Series(dtype=float)
        for _, e in ev.iterrows():
            near = s[(s.index >= e.ex_date - pd.Timedelta(days=7))
                     & (s.index <= e.ex_date + pd.Timedelta(days=7))] if len(s) else s
            row = e.to_dict()
            if len(near):
                # yfinance ratio is new/old shares; our factor is new/old price.
                # The calendar CONFIRMS the event only — the panel's own break
                # date (detected ex_date) governs where scaling applies: panel
                # increments can rebase days before the official ex-date, and
                # snapping to the calendar date wrongly re-scales those rows.
                yf_factor = 1.0 / near.iloc[0]
                row["confirmed"] = abs(np.log(yf_factor / e.factor)) < np.log(1.5)
                row["yf_factor"] = yf_factor
            else:
                row["confirmed"] = False
                row["yf_factor"] = np.nan
            out.append(row)
    c = pd.DataFrame(out)
    if len(c):
        c = c.drop_duplicates(subset=["market", "symbol", "ex_date"])
    return c


def build_adjusted(market: str, factors: pd.DataFrame) -> None:
    """SPARSE overlay (unlike India's full copy): the non-IN panels are already
    yfinance-adjusted as of their last assembly, so only the symbols with
    CONFIRMED residual breaks are written, full-history, corrected. Consumers
    read overlay-first: a symbol present in ohlcv_adj/<MKT> supersedes its
    ohlcv/<MKT> rows. Same compounding as price_adjuster.py: each event scales
    all bars BEFORE its ex_date; volume scales inversely."""
    ev_m = factors[(factors["market"] == market) & factors["confirmed"]]
    dst = WH / "ohlcv_adj" / market
    if ev_m.empty:
        print(f"  {market}: no confirmed events — no overlay written")
        return
    syms = sorted(ev_m["symbol"].unique())
    con = duckdb.connect()
    sym_list = ",".join(f"'{s}'" for s in syms)
    d = con.execute(
        f"SELECT * FROM read_parquet('{WH}/ohlcv/{market}/*.parquet') "
        f"WHERE Symbol IN ({sym_list}) ORDER BY Symbol, Date"
    ).df()
    d["Date"] = pd.to_datetime(d["Date"])
    d["adj_factor"] = 1.0
    for sym, ev in ev_m.groupby("symbol"):
        mask = d["Symbol"] == sym
        dates = d.loc[mask, "Date"]
        f = np.ones(len(dates))
        for _, e in ev.iterrows():
            # yfinance calendar factor is authoritative once confirmed
            use = e["yf_factor"] if np.isfinite(e.get("yf_factor", np.nan)) else e["factor"]
            f = np.where(dates < e["ex_date"], f * use, f)
        d.loc[mask, "adj_factor"] = f

    for c in ("Open", "High", "Low", "Close"):
        d[c] = d[c] * d["adj_factor"]
    d["Volume"] = np.where(d["adj_factor"] > 0, d["Volume"] / d["adj_factor"], d["Volume"])

    dst.mkdir(parents=True, exist_ok=True)
    p = dst / "corrected_symbols.parquet"
    tmp = p.with_suffix(".parquet.tmp")
    d.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(p)
    touched = (d["adj_factor"] != 1.0).sum()
    print(f"  {market}: {len(ev_m)} confirmed events, {len(syms)} symbols, "
          f"{touched:,} bars re-scaled -> {p}")


def validate(markets: list[str], n: int) -> int:
    """Cross-check detected events against yfinance auto_adjust, across each
    ex-date (same common-dates protocol as price_adjuster.py --validate)."""
    import yfinance as yf
    f = pd.read_parquet(FACTORS_PQ)
    ok = bad = 0
    for market in markets:
        fm = f[(f.market == market) & (f.ex_date > "2024-01-01")]
        if fm.empty:
            print(f"  {market}: no recent events to validate")
            continue
        adj = pd.read_parquet(WH / "ohlcv_adj" / market)
        adj["Date"] = pd.to_datetime(adj["Date"])
        for _, e in fm.sort_values("ex_date", ascending=False).head(n).iterrows():
            sym, ex = e.symbol, pd.Timestamp(e.ex_date)
            a = adj[adj.Symbol == sym].set_index("Date")["Close"].sort_index()
            try:
                y = yf.Ticker(sym).history(
                    start=(ex - pd.Timedelta(days=25)).strftime("%Y-%m-%d"),
                    end=(ex + pd.Timedelta(days=25)).strftime("%Y-%m-%d"),
                    auto_adjust=True)["Close"]
                y.index = pd.to_datetime(y.index).tz_localize(None)
            except Exception:
                continue
            common = a.index.intersection(y.index)
            common = common[(common > ex - pd.Timedelta(days=20)) &
                            (common < ex + pd.Timedelta(days=20))]
            if len(common) < 6 or not (common < ex).any() or not (common >= ex).any():
                continue
            ra = a.loc[common].iloc[-1] / a.loc[common].iloc[0] - 1
            ry = y.loc[common].iloc[-1] / y.loc[common].iloc[0] - 1
            good = abs(ra - ry) < 0.05
            ok += good; bad += not good
            print(f"  {'OK ' if good else 'DIFF'} {market} {sym:12} {e.kind:13} "
                  f"ex {ex.date()} factor {e.factor:.4g} "
                  f"| adj {ra:+.1%} vs yf {ry:+.1%}")
    print(f"\n  {ok} OK · {bad} DIFF")
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", nargs="+", default=MARKETS)
    ap.add_argument("--validate", type=int, default=0)
    ap.add_argument("--detect-only", action="store_true")
    a = ap.parse_args()

    if a.validate:
        return validate(a.markets, a.validate)

    frames = []
    for m in a.markets:
        ev = detect(m)
        frames.append(ev)
        print(f"  {m}: {len(ev)} events detected "
              f"({(ev['kind'] == 'split').sum() if len(ev) else 0} splits, "
              f"{(ev['kind'] == 'reverse_split').sum() if len(ev) else 0} reverse)")
    factors = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if not a.detect_only and len(factors):
        print(f"  confirming {len(factors)} events against yfinance split calendar…")
        factors = confirm(factors)
        n_ok = int(factors["confirmed"].sum())
        print(f"  confirmed: {n_ok} / {len(factors)}")

    # merge with any previously-processed markets not in this run
    if FACTORS_PQ.exists():
        old = pd.read_parquet(FACTORS_PQ)
        old = old[~old["market"].isin(a.markets)]
        factors = pd.concat([old, factors], ignore_index=True)
    tmp = FACTORS_PQ.with_suffix(".parquet.tmp")
    factors.to_parquet(tmp, index=False)
    tmp.replace(FACTORS_PQ)
    print(f"  factors -> {FACTORS_PQ.name} ({len(factors)} total)")

    if not a.detect_only:
        for m in a.markets:
            build_adjusted(m, factors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
