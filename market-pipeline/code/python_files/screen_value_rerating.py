#!/usr/bin/env python3
# screen_value_rerating.py
# ========================
# The combined screen the PE backtests earned (2026-07-23):
#
#     CHEAP vs OWN SECTOR   (within-industry PE percentile ≤ 0.20)
#   ∩ RE-RATING             (12-month PE change > 0 — multiple expanding)
#
# Why this pair: backtest_pe_anomalies.py showed the two effects are SEPARATE
# and compatible — sector-relative cheapness corrects (+5.3% Q1−Q5 over 6M,
# t≈2.5) while PE TREND is momentum, not reversion (expanders beat
# compressors). A name that is still cheap against its industry but whose
# multiple has already started expanding sits in both winning cells.
#
# India-only (the backtest's market; the PIT fundamentals exist here).
# Liquidity-gated at source (₹1cr/day median turnover — the user's standing
# floor) so the digest never has to bury these below the floor.
#
# Writes top picks into watchlist.csv as `signal` tier with note
# "value_rerating YYYY-MM-DD" + entry stamps, following the writers' contract:
# existing rows are never touched, schema preserved via concat+to_csv, capped
# per run (the signal_tracker technical-flood lesson).

from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_pe_anomalies import (  # noqa: E402
    MIN_IND, PE_MAX, PE_MIN, PX_DIR, load_eps, load_prices, pit_eps_panel)

WATCHLIST = Path(__file__).resolve().parent / "watchlist.csv"
CHEAP_PCTILE = 0.20        # within-industry PE percentile ceiling
TOP_N = 15                 # max promotions per run — a shortlist, not a flood
FLOOR_INR = 1e7            # ₹1 crore/day median turnover (user's standing gate)


def median_turnover() -> pd.Series:
    """60d median ₹ turnover per symbol from the adjusted panel. Last-60d
    adjustment factors are ~1, so adjClose×Volume ≈ raw turnover there."""
    part = sorted(glob.glob(f"{PX_DIR}/year=*.parquet"))[-1]
    px = pd.read_parquet(part, columns=["Date", "Symbol", "Close", "Volume"])
    px["Date"] = pd.to_datetime(px["Date"])
    recent = px[px.Date >= px.Date.max() - pd.Timedelta(days=95)]
    to = recent.assign(t=recent.Close * recent.Volume)
    return to.groupby("Symbol").t.median()


def main() -> int:
    px = load_prices()                              # month-end adjusted closes
    eps, industry = load_eps()
    epsp = pit_eps_panel(eps, px.index)
    common = [c for c in px.columns if c in epsp.columns]
    px, epsp = px[common], epsp[common]
    pe = (px / epsp).where(lambda d: (d >= PE_MIN) & (d <= PE_MAX))

    t = pe.index[-1]                                # latest (partial) month-end
    row = pe.loc[t].dropna()
    if len(row) < 100:
        print("  too few names with valid PE today — no picks")
        return 0
    ind = industry.reindex(row.index)
    counts = ind.value_counts()
    sel = ind.isin(counts[counts >= MIN_IND].index)
    pct = row[sel].groupby(ind[sel]).rank(pct=True)

    lnpe = np.log(pe)
    if len(lnpe) < 13:
        print("  <13 months of PE history — no re-rating leg")
        return 0
    d12 = (lnpe.iloc[-1] - lnpe.iloc[-13]).reindex(pct.index)

    cand = pd.DataFrame({"pct": pct, "d12": d12}).dropna()
    cand = cand[(cand.pct <= CHEAP_PCTILE) & (cand.d12 > 0)]
    if cand.empty:
        print("  no names pass cheap-vs-sector ∩ re-rating today")
        return 0

    # liquidity gate at source
    turn = median_turnover().reindex(cand.index)
    cand = cand[turn >= FLOOR_INR]
    if cand.empty:
        print("  all passers below the ₹1cr/day floor — no picks")
        return 0

    # rank: cheapness and re-rating strength, equal-weight rank blend
    score = (1 - cand.pct).rank(pct=True) * 0.5 + cand.d12.rank(pct=True) * 0.5
    picks = score.sort_values(ascending=False).head(TOP_N)

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    wl = pd.read_csv(WATCHLIST)
    have = {(str(r["symbol"]).upper(), str(r["market"]).upper())
            for _, r in wl.iterrows()}
    add = []
    for sym in picks.index:
        if (sym, "IN") in have:
            continue
        add.append({"symbol": sym, "market": "IN", "status": "signal",
                    "note": f"value_rerating {today}",
                    "entry_date": today,
                    "entry_price": round(float(px[sym].iloc[-1]), 4)})
    if add:
        pd.concat([wl, pd.DataFrame(add)], ignore_index=True).to_csv(
            WATCHLIST, index=False)
    print(f"  value_rerating: {len(cand)} passers, promoted "
          f"{len(add)} new (cap {TOP_N}, {len(picks) - len(add)} already tracked)")
    for sym in picks.index:
        c = cand.loc[sym]
        star = "" if (sym, "IN") in have else " 🆕"
        print(f"    {sym:14s} PE-pctile {c.pct:.2f} in {industry.get(sym, '?')[:26]:26s} "
              f"12M ΔlnPE {c.d12:+.2f}{star}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
