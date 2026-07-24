#!/usr/bin/env python3
# backtest_zone_rules.py
# ======================
# WHICH buy/hold/sell rule works in WHICH market? (user, 2026-07-23)
#
# The digest uses ONE zone rule everywhere: BUY = close>EMA20>EMA50,
# SELL = close<EMA50 (trend-following). The literature says that is wrong to
# apply uniformly:
#   * Balvers & Wu (2005), 18 developed markets: momentum AND mean-reversion
#     coexist; the winning combination differs by market.
#   * Emerging markets mean-revert FASTER than developed (Chaudhuri/Wu; the
#     TEDE emerging-vs-developed study) — short-horizon reversal dominates.
#   * Korea/KOSDAQ: retail-driven, documented short-term REVERSAL and
#     contrarian flow (KOSPI-200 recovery-contrarian factor literature; the
#     2026 inverse-ETF retail behaviour).
#   * India: our own signal-effectiveness analysis found breakout momentum
#     LOSES (−0.46%/5d excess) while sector-relative value wins.
#
# So rather than import a verdict, TEST each candidate rule on each market's
# own 10y panel and let the data pick. Candidate BUY-zone definitions, each
# scored by the forward 10-day return of the names it flags BUY vs the names
# it flags SELL (the spread is the rule's discriminating power):
#
#   trend     BUY close>EMA20>EMA50 / SELL close<EMA50          (current rule)
#   revert    BUY 5d return in bottom tercile (oversold) /
#             SELL top tercile (overbought)                      (mean-reversion)
#   mom126    BUY 6-month return top tercile / SELL bottom       (classic momentum)
#   mom_st    BUY 21-day return top tercile / SELL bottom        (short momentum)
#
# For each market × rule: forward-10d mean return of BUY minus SELL, averaged
# over weekly formation dates, with a de-overlapped t-stat. The rule with the
# largest positive, significant spread is the one that market's zone logic
# should use. Output: reports/zone_rules_by_market.md + a machine-readable
# cache_seed/zone_rules.json the digest can consume.

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WH = os.environ.get("MARKET_WH", "/Users/umashankar/repos/global-market-data/warehouse/ohlcv")
OUT_MD = HERE / "reports" / "zone_rules_by_market.md"
OUT_JSON = HERE / "cache_seed" / "zone_rules.json"

MARKETS = ("IN", "US", "JP", "KR", "EU")
FWD = 10                       # forward horizon (trading days)
START = "2018-01-01"           # 2y warmup for the 126d/EMA50 lookbacks
MIN_NAMES = 60                 # names a formation date needs
TERCILE = 1 / 3.0


def load_closes(mkt: str) -> pd.DataFrame:
    parts = sorted(glob.glob(f"{WH}/{mkt}/year=*.parquet"))
    df = pd.concat((pd.read_parquet(p, columns=["Date", "Symbol", "Close"])
                    for p in parts), ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"])
    w = df.pivot_table(index="Date", columns="Symbol", values="Close",
                       aggfunc="last").sort_index()
    # weekly (Friday) formation grid to cut overlap and cost
    return w.asfreq("B").ffill(limit=2).resample("W-FRI").last()


def zone_signals(w: pd.DataFrame) -> dict:
    """Per-rule DataFrame of +1 (BUY) / −1 (SELL) / 0 (HOLD) aligned to w."""
    ema20 = w.ewm(span=20 // 5, adjust=False).mean()    # weekly bars ≈ /5
    ema50 = w.ewm(span=50 // 5, adjust=False).mean()
    r5 = w.pct_change(1, fill_method=None)              # 1 week ≈ 5 sessions
    r21 = w.pct_change(4, fill_method=None)
    r126 = w.pct_change(25, fill_method=None)

    def tercile_sig(r):
        lo = r.rank(axis=1, pct=True)
        return (lo >= 1 - TERCILE).astype(int) - (lo <= TERCILE).astype(int)

    trend = ((w > ema20) & (ema20 > ema50)).astype(int) - (w < ema50).astype(int)
    revert = -tercile_sig(r5)          # oversold → BUY: invert
    mom126 = tercile_sig(r126)
    mom_st = tercile_sig(r21)
    return {"trend": trend, "revert": revert, "mom126": mom126, "mom_st": mom_st}


def score(w: pd.DataFrame, sig: pd.DataFrame, wprice: pd.DataFrame) -> tuple:
    """(mean BUY−SELL fwd spread, de-overlapped t) for one rule.

    Forward returns winsorized at ±40% and computed only on names priced
    above a small floor — the US/EU panels carry sub-$1 SPAC/warrant names
    whose 2-week pct_change reaches +900%, which otherwise dominates the mean
    (the −740% blowup on the first run)."""
    fwd = (w.shift(-FWD // 5) / w - 1).clip(-0.40, 0.40)
    tradeable = wprice >= 1.0               # local-currency floor, penny cut
    spreads = []
    for t in w.index[w.index >= START]:
        s = sig.loc[t]
        f = fwd.loc[t].where(tradeable.loc[t])
        buys = f[s == 1].dropna()
        sells = f[s == -1].dropna()
        if len(buys) >= MIN_NAMES // 2 and len(sells) >= MIN_NAMES // 2:
            spreads.append(buys.mean() - sells.mean())
    sp = pd.Series(spreads)
    if len(sp) < 10:
        return np.nan, np.nan
    # 2-week fwd on weekly grid → overlap ~2; de-overlap by every-2nd
    t = sp.iloc[::2]
    return float(sp.mean() * 100), float(t.mean() / t.std() * np.sqrt(len(t)))


def main() -> int:
    rules = ["trend", "revert", "mom126", "mom_st"]
    label = {"trend": "Trend-follow (close>EMA20>EMA50)",
             "revert": "Mean-revert (buy oversold)",
             "mom126": "6-month momentum",
             "mom_st": "1-month momentum"}
    lines = ["# Buy/Hold/Sell rule by market — what each market's data prefers", "",
             "Each candidate zone rule scored by the forward-10d return SPREAD "
             "between the names it calls BUY and SELL, on each market's own 10y "
             "weekly panel (2018→). The rule with the largest positive, "
             "significant spread is what that market's zone logic should use — "
             "rather than the one trend rule applied everywhere.", "",
             "| market | " + " | ".join(label[r] for r in rules) + " | winner |",
             "|---|" + "---|" * (len(rules) + 1)]
    best = {}
    for mkt in MARKETS:
        try:
            w = load_closes(mkt)
        except Exception as e:
            lines.append(f"| {mkt} | load failed: {str(e)[:40]} |")
            continue
        sigs = zone_signals(w)
        cells, scores = [], {}
        for r in rules:
            sp, t = score(w, sigs[r], w)
            scores[r] = (sp, t)
            star = "**" if (not np.isnan(t) and abs(t) >= 2) else ""
            cells.append(f"{star}{sp:+.2f}% (t{t:+.1f}){star}"
                         if not np.isnan(sp) else "—")
        valid = {r: v for r, v in scores.items()
                 if not np.isnan(v[0]) and v[0] > 0 and abs(v[1]) >= 1.5}
        win = max(valid, key=lambda r: valid[r][0]) if valid else "trend"
        best[mkt] = {"rule": win, "spread_pct": round(scores[win][0], 3),
                     "t": round(scores[win][1], 2),
                     "all": {r: [round(scores[r][0], 3), round(scores[r][1], 2)]
                             for r in rules}}
        lines.append(f"| **{mkt}** | " + " | ".join(cells) +
                     f" | **{label[win].split(' (')[0]}** |")

    lines += ["", "**Bold** = |t| ≥ 2. Winner = largest positive spread with "
              "|t| ≥ 1.5, else defaults to trend (the incumbent). This is the "
              "spread a long-BUY/short-SELL book would have earned per 2 weeks — "
              "not a live strategy (no costs, weekly rebalance), but a clean "
              "read on which signal DISCRIMINATES in each market.", "",
              "## How this maps to the digest",
              "The zone engine can switch rule by market: a name is BUY if it "
              "passes its market's winning rule, SELL if it fails it, HOLD "
              "between. Eviction still runs off the SELL state, so a market "
              "whose winner is mean-reversion will evict on overbought-and-"
              "fading rather than below-EMA50 — which is what the literature "
              "(Balvers-Wu; emerging-market fast reversion; KOSPI contrarian) "
              "and our own signal-effectiveness analysis both point to."]
    OUT_MD.write_text("\n".join(lines))
    OUT_JSON.write_text(json.dumps(best, indent=1))
    print("\n".join(lines))
    print(f"\nwrote {OUT_MD} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
