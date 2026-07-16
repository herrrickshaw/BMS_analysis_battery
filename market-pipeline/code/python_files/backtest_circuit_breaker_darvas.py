#!/usr/bin/env python3
"""
backtest_circuit_breaker_darvas.py — historic validation: were Darvas
breakout/breakdown days' 1-day price moves within each market's real
circuit-breaker limit (researched today, see build_mailer.py's
_CIRCUIT_BREAKER_PCT)?

Replicates strategies/darvas.py's EXACT box-detection algorithm (CONFIRM=3,
current bar excluded, no lookahead) as a single forward pass per symbol over
10.5y of daily OHLCV (2016-2026, global-market-data/cache_seed/ltm/*.parquet),
instead of the O(days^2) walk-forward the box function would imply if called
naively once per day. This is possible because a "confirmed pivot" in that
algorithm only depends on the 3 bars immediately following it (a fixed,
non-lookahead property of the series) — so pivot-highs/pivot-lows are
precomputed once per symbol, then day-by-day box_top/box_bottom are a
"last confirmed pivot at or before this day" scan, done in one O(n) pass.

CIRCUIT BOUNDS (see build_mailer.py's _CIRCUIT_BREAKER_PCT docstring + the
public-source research from this session):
  IN — 20% (NSE/BSE static band ceiling; F&O names use a 10% dynamic band
       instead, but 20% is the outer bound across all equity types)
  KR — 30% (KRX flat symmetric daily limit since 2015 — exact, not a heuristic)
  US — no daily price CAP exists (LULD pauses, doesn't limit) — reported as a
       distribution, not pass/fail
  JP — no flat %; TSE's limit is an absolute-yen table that varies by price
       tier (~20-50% width) — reported as a distribution, not pass/fail

CORPORATE-ACTION CAVEAT: this source stores raw Close, not split-adjusted
Close (known issue, see reference_deep_10y_market_data memory). A day whose
|change%| lands within ~3pp of a common split/bonus ratio (1:2 -> -50%,
1:3 -> -66.7%, 1:5 -> -80%, 1:10 -> -90%, bonus 1:1 -> -50%, reverse 2:1 ->
+100%, 3:1 -> +200%) is flagged SEPARATELY as "likely unadjusted corporate
action", not counted as a genuine circuit-limit violation — conflating the
two would overstate how often the exchange's own rule was "broken".

Usage:
    python3 backtest_circuit_breaker_darvas.py --market IN
    python3 backtest_circuit_breaker_darvas.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

CONFIRM = 3
LTM_DIR = "/Users/umashankar/repos/global-market-data/cache_seed/ltm"

CIRCUIT_PCT = {"IN": 20.0, "KR": 30.0}   # exact/near-exact flat bounds
NO_FIXED_CAP = {"US", "JP"}              # reported as distribution only

SPLIT_RATIOS = [-50.0, -66.7, -75.0, -80.0, -90.0, +100.0, +200.0, +300.0, +400.0]
SPLIT_TOL = 3.0   # pp tolerance for "looks like an unadjusted split/bonus"


def _confirmed_pivots(vals: np.ndarray, want_high: bool) -> np.ndarray:
    """confirmed[i] = True iff the 3 bars immediately after i are all
    strictly on the other side of vals[i] (mirrors _compute_box's per-
    candidate window test exactly, vectorized via shifts)."""
    n = len(vals)
    ok = np.zeros(n, dtype=bool)
    if n < CONFIRM + 1:
        return ok
    v1, v2, v3 = vals[1:n-2], vals[2:n-1], vals[3:n]
    base = vals[0:n-3]
    if want_high:
        cond = (base > v1) & (base > v2) & (base > v3)
    else:
        cond = (base < v1) & (base < v2) & (base < v3)
    ok[0:n-3] = cond
    return ok


def _last_true_at_or_before(mask: np.ndarray) -> np.ndarray:
    """out[k] = largest i<=k with mask[i] True, else -1. O(n) forward pass."""
    n = len(mask)
    out = np.full(n, -1, dtype=np.int64)
    last = -1
    for i in range(n):
        if mask[i]:
            last = i
        out[i] = last
    return out


def _next_true_at_or_after(mask: np.ndarray) -> np.ndarray:
    """out[k] = smallest i>=k with mask[i] True, else -1. O(n) backward pass."""
    n = len(mask)
    out = np.full(n, -1, dtype=np.int64)
    nxt = -1
    for i in range(n - 1, -1, -1):
        if mask[i]:
            nxt = i
        out[i] = nxt
    return out


def _scan_symbol(dates: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                  closes: np.ndarray) -> list[dict]:
    """Single O(n) forward pass replicating strategies/darvas.py's
    _compute_box() for every day t (using only bars [0, t-1], current bar t
    excluded — identical no-lookahead contract), returning one row per
    BREAKOUT_BUY / BREAKDOWN_SELL day.

    _compute_box() is O(history) PER DAY when called naively (as production
    scanners do, once for "today"); replaying it that way across 10.5y would
    be O(days^2) per symbol. Both confirmed-pivot conditions only look 3 bars
    AHEAD of a candidate index — a fixed property of the series, independent
    of "today" — so pivot confirmation is precomputed ONCE per symbol
    (_confirmed_pivots, vectorized), then each day's box_top/box_bottom is an
    O(1) index lookup into a precomputed "last/next confirmed pivot" array.
    """
    n = len(closes)
    if n < CONFIRM + 6:
        return []

    conf_top = _confirmed_pivots(highs, want_high=True)
    conf_bot = _confirmed_pivots(lows, want_high=False)
    last_top_at = _last_true_at_or_before(conf_top)   # last_top_at[k] -> box_top idx candidate
    next_bot_at = _next_true_at_or_after(conf_bot)    # next_bot_at[k] -> box_bottom idx candidate

    out = []
    # running min of lows, for the box_bottom fallback ("no confirmed low in
    # segment" -> min low from box_top_idx to hist_n-1). A prefix-min array
    # lets that fallback stay O(1) too: pmin[k] = min(lows[0..k]) requires a
    # *range* min (from box_top_idx to hist_n-1), so use a suffix structure —
    # cheapest correct approach: precompute prefix-min from the RIGHT once.
    lows_pos = np.where(lows > 0, lows, np.inf)

    for t in range(CONFIRM + 5, n):
        hist_n = t                        # bars [0, t-1] available; t excluded
        ceiling = hist_n - CONFIRM - 1     # i <= n - CONFIRM - 1 in _compute_box
        if ceiling < 0:
            continue
        j = last_top_at[ceiling]
        if j < 0:
            continue
        box_top = highs[j]

        cand = next_bot_at[j] if j < n else -1
        if 0 <= cand <= ceiling:
            box_bottom = lows[cand]
        else:
            seg = lows_pos[j:hist_n]
            m = seg.min() if len(seg) else np.inf
            box_bottom = float(m) if np.isfinite(m) else None
        if box_bottom is None:
            continue

        current = closes[t]
        prev_close = closes[t - 1]
        if prev_close <= 0 or current <= 0:
            continue
        signal = ("BREAKOUT_BUY" if current > box_top else
                  "BREAKDOWN_SELL" if current < box_bottom else None)
        if signal is None:
            continue
        chg = (current / prev_close - 1) * 100
        out.append({"date": dates[t], "signal": signal, "box_top": box_top,
                     "box_bottom": box_bottom, "close": current,
                     "prev_close": prev_close, "change_pct": chg})
    return out


def _looks_like_unadjusted_split(chg: float) -> bool:
    return any(abs(chg - r) <= SPLIT_TOL for r in SPLIT_RATIOS)


def backtest(market: str, symbol_cap: int | None = None) -> pd.DataFrame:
    path = f"{LTM_DIR}/{market}.parquet"
    df = pd.read_parquet(path, columns=["Date", "Symbol", "High", "Low", "Close"])
    df = df.dropna(subset=["High", "Low", "Close"])
    df = df.sort_values(["Symbol", "Date"])

    syms = df["Symbol"].unique()
    if symbol_cap:
        syms = syms[:symbol_cap]

    rows = []
    for i, sym in enumerate(syms):
        g = df[df["Symbol"] == sym]
        if len(g) < CONFIRM + 6:
            continue
        events = _scan_symbol(g["Date"].values, g["High"].values.astype(float),
                               g["Low"].values.astype(float), g["Close"].values.astype(float))
        for e in events:
            e["symbol"] = sym
            rows.append(e)
    res = pd.DataFrame(rows)
    if res.empty:
        return res
    res["market"] = market
    res["abs_chg"] = res["change_pct"].abs()
    res["likely_split"] = res["change_pct"].apply(_looks_like_unadjusted_split)
    return res


def report(market: str, res: pd.DataFrame):
    print(f"\n{'='*70}\n  {market} — {len(res)} breakout/breakdown days detected"
          f" ({res['symbol'].nunique()} symbols)\n{'='*70}")
    if res.empty:
        print("  no events")
        return
    clean = res[~res["likely_split"]]
    splits = res[res["likely_split"]]
    print(f"  flagged as likely unadjusted split/bonus: {len(splits)} "
          f"({len(splits)/len(res)*100:.1f}%)")
    print(f"  clean events analyzed: {len(clean)}")

    if market in CIRCUIT_PCT:
        bound = CIRCUIT_PCT[market]
        viol = clean[clean["abs_chg"] > bound]
        pct = len(viol) / len(clean) * 100 if len(clean) else 0
        print(f"  circuit bound: ±{bound}%  ->  violations: {len(viol)} "
              f"({pct:.3f}% of clean events)")
        if len(viol):
            print(f"  worst 8 violations:")
            for _, r in viol.reindex(viol["abs_chg"].sort_values(ascending=False).index).head(8).iterrows():
                print(f"    {r.date} {r.symbol:12s} {r.signal:14s} chg={r.change_pct:+8.2f}%  "
                      f"close={r.close:.2f} prev={r.prev_close:.2f}")
    else:
        print(f"  no flat circuit bound for {market} — distribution of clean |change%|:")
        q = clean["abs_chg"].quantile([0.5, 0.9, 0.99, 0.999, 1.0])
        for k, v in q.items():
            print(f"    p{k*100:.1f}: {v:.2f}%")
        extreme = clean[clean["abs_chg"] > 50]
        print(f"  events >50% (still plausible for {market}, no hard cap): {len(extreme)} "
              f"({len(extreme)/len(clean)*100:.3f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    ap.add_argument("--symbol-cap", type=int, default=None,
                     help="limit symbols per market (debug/speed)")
    a = ap.parse_args()
    for m in a.market:
        res = backtest(m, a.symbol_cap)
        report(m, res)
        if not res.empty:
            res.to_parquet(f"cache_seed/circuit_breaker_backtest_{m}.parquet", index=False)


if __name__ == "__main__":
    main()
