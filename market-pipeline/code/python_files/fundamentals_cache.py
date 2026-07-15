#!/usr/bin/env python3
"""
fundamentals_cache.py — reuse quarterly fundamentals instead of refetching nightly.

WHY
---
Fundamentals (Piotroski, Coffee Can, Magic Formula, sector) come from quarterly
filings. They do not change day to day. Refetching them every night costs one
yf.Ticker(...).info call PER STOCK — which is the single most expensive thing this
pipeline does and the reason it trips Yahoo's rate limiter (surfacing as
"Invalid Crumb"/YFRateLimitError, which then breaks *other* markets' FX and their
liquidity gates).

Measured 2026-07-15: the US Stage 4 ran .info across ~5,700 stocks nightly —
62m54s, 2.3x the next-slowest step. Reusing the previous workbook took it to 4s.
India documented this rationale years ago ("fundamentals are quarterly and do not
change day-to-day, so they are reused from the most recent existing full-scan
workbook") — but only India and, since today, the US actually did it. Europe,
Japan and Korea still refetched everything, every night.

SHEET NAMING IS INCONSISTENT and silently breaks reuse:
    full_indian_market_scan.py -> "All_Fundamentals"
    scan_bhavcopy.py           -> reads "Fundamentals"   (never matches!)
    full_us_market_scan.py     -> "All_Fundamentals"
    Europe / Japan / Korea     -> "Fundamentals"
India's reuse was therefore structurally impossible: its seeder writes one name and
its consumer reads the other. This helper accepts either, so a rename cannot
silently disable reuse again.

Usage:
    import fundamentals_cache as fc
    cached, src = fc.load("japan_scan/japan_market_scan_*.xlsx", key="Code")
    need = [s for s in symbols if s not in cached]
"""
from __future__ import annotations

import glob
import os
import time
from typing import Dict, Optional, Tuple

import pandas as pd

# Quarterly data: a week-old score is the same score. Beyond that, refresh.
REUSE_DAYS = 7
SHEET_NAMES = ("All_Fundamentals", "Fundamentals")


# ── Pipeline B: the point-in-time warehouse ───────────────────────────────────
# The daily brief (Pipeline A) has always read fundamentals from its OWN Excel
# workbooks, while the research stack (Pipeline B) reads EDGAR/screener.in parquets.
# The two never reconcile, and that is a real defect rather than an inefficiency:
# today's lender-ROCE fix landed in the Pipeline B collector, so the BRIEF is still
# wrong. One fix, two pipelines, one still broken.
#
# The two hold different KINDS of thing, which is why this is not a path change:
#     workbooks -> COMPUTED SCORES  (Piotroski_Score, CoffeeCan)
#     parquets  -> RAW LINE ITEMS   (net_income, cfo, ebit, revenue)
# So the brief must SCORE from raw inputs via piotroski_plus, which is the right
# architecture: one scorer, one source of truth, fixes propagate automatically.
#
# ⚠️ US ONLY, deliberately. Measured coverage:
#     US  workbook 6,278 tickers | parquet 5,016  -> a 20% cost for point-in-time
#                                                    correctness and REAL filing dates
#     IN  workbook   248 tickers | parquet    31  -> an 87% LOSS. India's parquet is the
#                                                    wreckage of a collection screener.in
#                                                    blocked at 1.3%. It is not a source yet.
# Switching India today would take the brief from 3 Triple Hits to ~0. Wire it after a
# clean collection, not before.
WAREHOUSE = {
    "US": "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet",
    # "IN": ... — deliberately absent until the collection succeeds. See above.
}


def load_from_warehouse(market: str = "US", asof=None, verbose: bool = True):
    """({symbol: row}, source) scored from Pipeline B's point-in-time parquet.

    Same return shape as load(), so a caller cannot tell the two apart.

    Gated on EDGAR's REAL `filed` date, not fiscal-year-end plus an assumed lag: only
    fundamentals actually public at `asof` are used. The workbook path has no such
    guarantee — it carries whatever the last scan computed, from whenever.
    """
    import pandas as _pd

    path = WAREHOUSE.get((market or "").upper())
    if not path or not os.path.exists(path):
        if verbose:
            print(f"  warehouse: no parquet for {market} — falling back to workbooks")
        return {}, None
    try:
        import duckdb
        import piotroski_plus as PP
    except Exception as e:
        if verbose:
            print(f"  warehouse: unavailable ({str(e)[:50]}) — falling back")
        return {}, None

    asof = _pd.Timestamp(asof) if asof is not None else _pd.Timestamp.today()
    try:
        con = duckdb.connect()
        f = con.execute(f"""
            SELECT ticker, CAST(fy_end AS DATE) fy_end, CAST(filed AS DATE) filed,
                   net_income, cfo, total_assets, current_assets, current_liabilities,
                   long_term_debt, shares, revenue, gross_profit, ebit
            FROM '{path}'
            WHERE net_income IS NOT NULL AND total_assets > 0
              AND CAST(filed AS DATE) <= DATE '{asof.date()}'
              AND date_diff('day', CAST(fy_end AS DATE), CAST(filed AS DATE))
                  BETWEEN 0 AND 400
            ORDER BY ticker, fy_end
        """).df()
    except Exception as e:
        if verbose:
            print(f"  warehouse: read failed ({str(e)[:50]}) — falling back")
        return {}, None
    if f.empty:
        return {}, None

    PURE = {n: 1.0 for n in PP.PIOTROSKI_TESTS}
    out = {}
    for tk, g in f.groupby("ticker"):
        if len(g) < 2:
            continue                       # a delta needs a prior year
        cur, prv = g.iloc[-1], g.iloc[-2]
        d = {}
        ta, ta_p = cur.total_assets, prv.total_assets
        roa = cur.net_income / ta if ta else None
        roa_p = prv.net_income / ta_p if ta_p else None
        d["1_roa_positive"] = bool(roa > 0) if roa is not None else None
        d["2_cfo_positive"] = bool(cur.cfo > 0) if _pd.notna(cur.cfo) else None
        d["3_roa_improving"] = bool(roa > roa_p) if None not in (roa, roa_p) else None
        d["4_accruals_cfo_gt_roa"] = (bool(cur.cfo / ta > roa)
                                      if _pd.notna(cur.cfo) and ta and roa is not None else None)
        d["5_leverage_falling"] = (bool(cur.long_term_debt / ta < prv.long_term_debt / ta_p)
                                   if _pd.notna(cur.long_term_debt) and _pd.notna(prv.long_term_debt)
                                   and ta and ta_p else None)
        d["6_current_ratio_rising"] = (
            bool(cur.current_assets / cur.current_liabilities
                 > prv.current_assets / prv.current_liabilities)
            if _pd.notna(cur.current_assets) and _pd.notna(prv.current_assets)
            and cur.current_liabilities and prv.current_liabilities else None)
        d["7_no_dilution"] = (bool(cur.shares <= prv.shares * 1.01)
                              if _pd.notna(cur.shares) and _pd.notna(prv.shares) and prv.shares else None)
        d["8_gross_margin_rising"] = (
            bool(cur.gross_profit / cur.revenue > prv.gross_profit / prv.revenue)
            if _pd.notna(cur.gross_profit) and _pd.notna(prv.gross_profit)
            and cur.revenue and prv.revenue else None)
        d["9_asset_turnover_rising"] = (bool(cur.revenue / ta > prv.revenue / ta_p)
                                        if _pd.notna(cur.revenue) and ta and ta_p else None)
        w = PP.weigh(d, PURE)
        if w["pct"] is None or w["possible"] < 6:
            continue                       # too sparse to be a score
        f9 = round(w["pct"] / 100 * 9, 1)
        out[str(tk)] = {
            "Symbol": str(tk),
            "Piotroski_Score": f9,
            "Piotroski_Strong": "YES" if f9 >= 7 else "NO",
            "fy_end": str(cur.fy_end),
            "filed": str(cur.filed),        # the REAL as-of, carried through
            "f_tested": int(w["possible"]),
            "source": "warehouse",
        }
    if verbose and out:
        print(f"  fundamentals: {len(out):,} scored from the point-in-time warehouse "
              f"({market}, as-of {asof.date()}, gated on real filing dates)")
    return out, f"warehouse:{os.path.basename(path)}"


def load(pattern: str, key: str = "Symbol", reuse_days: int = REUSE_DAYS,
         verbose: bool = True) -> Tuple[Dict[str, dict], Optional[str]]:
    """({symbol: fundamentals_row}, source_filename) from the newest usable workbook.

    Returns ({}, None) when nothing is reusable — caller then does a full fetch.
    Walks backwards through recent workbooks: the newest file may be from a run
    that produced no fundamentals (e.g. a momentum-only pass), and stopping at the
    first miss would discard perfectly good data one file back.
    """
    files = sorted(glob.glob(pattern))
    if not files:
        return {}, None

    for f in reversed(files[-6:]):
        age_d = (time.time() - os.path.getmtime(f)) / 86400
        if age_d > reuse_days:
            if verbose:
                print(f"  fundamentals: newest cache {age_d:.1f}d old "
                      f"(> {reuse_days}d) — full refresh")
            return {}, None
        try:
            sheets = pd.ExcelFile(f).sheet_names
        except Exception:
            continue
        name = next((s for s in SHEET_NAMES if s in sheets), None)
        if not name:
            continue                       # this run produced none; try older
        try:
            fd = pd.read_excel(f, sheet_name=name)
        except Exception:
            continue
        if fd.empty or key not in fd.columns:
            continue
        out = {}
        for _, r in fd.iterrows():
            k = str(r.get(key, "")).strip()
            if k and k.lower() != "nan":
                out[k] = r.to_dict()
        if out:
            if verbose:
                print(f"  fundamentals: reusing {len(out):,} rows from "
                      f"{os.path.basename(f)}:{name} ({age_d:.1f}d old)")
            return out, f"{os.path.basename(f)}:{name}"
    if verbose:
        print("  fundamentals: no usable cache — full refresh")
    return {}, None


def merge(cached: dict, symbols: list, price_map: dict, price_fields: tuple) -> list:
    """Rows for symbols served from cache, with price fields refreshed from today.

    The caller's fetch loop only runs the symbols NOT in cache, so without this the
    reused ones vanish from the output entirely — trading a slow scan for a
    truncated one. Only the quarterly fields come from cache; anything
    price-derived is overwritten with today's values.
    """
    rows = []
    for s in symbols:
        cr = cached.get(s)
        if cr is None:
            continue
        today = price_map.get(s)
        if today is None:
            continue                       # not in today's gated universe
        row = dict(cr)
        for fld in price_fields:
            if fld in today:
                row[fld] = today[fld]
        rows.append(row)
    return rows
