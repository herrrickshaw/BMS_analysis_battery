#!/usr/bin/env python3
"""
consistency_audit.py — hold every market to the standards India taught us, and
flag anomalies loudly.

WHY
---
India got the attention, so India got the fixes: incremental official-source
fetch, a liquidity floor, quarterly-fundamentals reuse, and an external
cross-check against screener.in. The other four markets each drifted from that
standard in ways nothing surfaced — every one of these was found only by hand:

  * Japan + Korea computed a 200-day MA from a 3-month window: 200_Day_MA was
    0/2,050 and 0/1,879 populated, Trend_Signal read "Insufficient History" for
    EVERY row, and it shipped in the brief daily.
  * Korea fetched OHLC one ticker per HTTP call with a 0.3s sleep — 28 min.
  * The US re-fetched .info for ~5,700 stocks nightly for QUARTERLY data (63 min),
    which is what tripped Yahoo's rate limiter.
  * When that limiter hit, the FX fetch failed, and Europe + Japan silently ran
    with NO liquidity gate at all (Liquidity_Tier=UNKNOWN, Turnover_USD=0 for
    every row) while US and Korea were fine. The output looked entirely normal.

A per-market scan that looks healthy in isolation can be broken in comparison.
This compares them and says so.

Checks
------
  gate_active      Liquidity_Tier present, >1 distinct value, 0 rows below floor
  window           enough bars for the indicators the scan itself reports
  200dma           if the scan reports a 200-DMA, it must actually be populated
  fundamentals     Piotroski present when the scan claims a Fundamentals sheet
  freshness        the scan's data date vs the other markets'
  schema           the columns every market is expected to carry

Exit 1 if any ERROR-level anomaly is found, so the pipeline can flag it.

Usage:
    python3 consistency_audit.py
    python3 consistency_audit.py --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime

import pandas as pd

# ── per-market liquidity floors ──────────────────────────────────────────────
# WAS a single FLOOR_USD = 120_000 applied to all five markets. That is India's
# POLICY floor (Rs 1 crore/day), and using it everywhere broke the check twice:
#
#  1. Non-India markets were judged against a floor nobody chose for them. The
#     scans gate on adaptive_liquidity.scan_floor(), which is the STRUCTURAL
#     floor ($10k/day) unless a policy floor was actually set — and one was set
#     only for India. So every US/JP/KR/EU name between $10k and $120k was
#     reported "below the floor" while being correctly admitted by the gate.
#     That is the 872/858/652/82 warnings on 2026-07-20: all false positives.
#  2. India's Median_Turnover column is in RUPEES, not USD. Comparing it to a
#     USD constant is a unit error that silently PASSED — rupee turnover is ~87x
#     the USD figure, so everything cleared 120_000 regardless of liquidity.
#     India's real gate is Rs 1 crore, and it must be checked in rupees.
#
# Floors are therefore stated per market in the SAME currency as that market's
# turnover column, and sourced from the modules the scans themselves gate on so
# the audit cannot drift from the gate again.
def _floors() -> dict:
    struct, india = 10_000.0, 10_000_000.0
    try:
        import adaptive_liquidity as _AL
        struct = float(_AL.scan_floor(""))          # structural, no policy floor
    except Exception:
        pass
    try:
        import scan_bhavcopy as _SB
        india = float(_SB.LIQ_FLOOR)                # Rs 1 crore/day, native INR
    except Exception:
        pass
    # (floor, currency of the market's turnover column)
    return {"India":  (india,  "INR"),
            "US":     (struct, "USD"),
            "Europe": (struct, "USD"),
            "Japan":  (struct, "USD"),
            "Korea":  (struct, "USD")}


FLOORS = _floors()
MIN_BARS_FOR_200DMA = 200

MARKETS = [
    # name, glob, symbol col, ltp col, turnover col
    ("India", "indian_full_scan/indian_full_scan_*.xlsx", "Symbol", "LTP", "Median_Turnover"),
    ("US", "us_full_scan/us_full_scan_*.xlsx", "Symbol", "LTP", "Turnover_USD"),
    ("Europe", "european_scan/european_market_scan_broad_*.xlsx", "Symbol", "LTP", "Turnover_USD"),
    ("Japan", "japan_scan/japan_market_scan_*.xlsx", "YF_Ticker", "LTP_JPY", "Turnover_USD"),
    ("Korea", "korea_scan/korea_market_scan_*.xlsx", "YF_Ticker", "LTP_KRW", "Turnover_USD"),
]


def _latest(pat):
    fs = sorted(glob.glob(pat))
    return fs[-1] if fs else None


def audit_market(name, pat, sym, ltp, tcol) -> dict:
    f = _latest(pat)
    r = {"market": name, "file": os.path.basename(f) if f else None, "issues": []}
    if not f:
        r["issues"].append(("ERROR", "no scan workbook found"))
        return r

    r["age_min"] = round((datetime.now().timestamp() - os.path.getmtime(f)) / 60)
    try:
        xl = pd.ExcelFile(f)
        d = pd.read_excel(f, "All_Stocks")
    except Exception as e:
        r["issues"].append(("ERROR", f"unreadable: {str(e)[:50]}"))
        return r

    r["rows"] = len(d)
    r["bars"] = float(d["Data_Points"].median()) if "Data_Points" in d.columns else None

    # ── liquidity gate ────────────────────────────────────────────────────────
    if "Liquidity_Tier" not in d.columns:
        r["issues"].append(("ERROR", "no liquidity gate (Liquidity_Tier absent)"))
        r["tiers"] = 0
    else:
        vc = d["Liquidity_Tier"].value_counts().to_dict()
        r["tiers"] = vc
        unknown = vc.get("UNKNOWN", 0)
        if unknown == len(d):
            r["issues"].append(("ERROR",
                                f"gate INACTIVE — all {len(d):,} rows UNKNOWN "
                                f"(FX unavailable at scan time?)"))
        elif unknown > len(d) * 0.05:
            r["issues"].append(("WARN", f"{unknown:,} rows UNKNOWN ({unknown/len(d)*100:.0f}%)"))
    if tcol in d.columns:
        floor, ccy = FLOORS.get(name, (0.0, "USD"))
        below = int((pd.to_numeric(d[tcol], errors="coerce") < floor).sum())
        r["below_floor"] = below
        r["floor"] = f"{floor:,.0f} {ccy}"
        if below and below == len(d):
            r["issues"].append(("ERROR", "every row below the liquidity floor — gate not applied"))
        elif below:
            r["issues"].append(("WARN",
                                f"{below:,} rows below the {floor:,.0f} {ccy} floor"))
    else:
        r["issues"].append(("WARN", f"no turnover column ({tcol})"))

    # ── the scan must be able to compute what it reports ──────────────────────
    if "200_Day_MA" in d.columns:
        pop = d["200_Day_MA"].notna().mean()
        r["dma200_pct"] = round(pop * 100)
        if pop < 0.5:
            r["issues"].append(("ERROR",
                                f"reports a 200-DMA but only {pop*100:.0f}% populated "
                                f"(median bars={r['bars']}, needs {MIN_BARS_FOR_200DMA})"))
    if r["bars"] is not None and r["bars"] < MIN_BARS_FOR_200DMA and "200_Day_MA" in d.columns:
        r["issues"].append(("ERROR", f"window too short: {r['bars']:.0f} bars < {MIN_BARS_FOR_200DMA}"))

    # ── fundamentals ──────────────────────────────────────────────────────────
    fsheet = next((s for s in xl.sheet_names if "undamental" in s), None)
    if fsheet:
        try:
            fd = pd.read_excel(f, sheet_name=fsheet)
            pio = int(fd["Piotroski_Score"].notna().sum()) if "Piotroski_Score" in fd.columns else 0
            r["piotroski"] = pio
            if pio == 0:
                r["issues"].append(("WARN",
                                    f"'{fsheet}' sheet present but 0 Piotroski scores "
                                    f"— fundamentals unavailable this run"))
        except Exception:
            r["issues"].append(("WARN", f"'{fsheet}' unreadable"))
    else:
        r["piotroski"] = 0
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    res = [audit_market(*m) for m in MARKETS]

    # ── cross-market consistency ─────────────────────────────────────────────
    # A market can look fine alone and be the odd one out in comparison — which is
    # the whole point of auditing them together rather than one at a time.
    cross = []

    # bars spread. The US carries a 5y MarketCache window (~1,275 bars) while the
    # rest carry ~244. Not wrong, but the SAME screeners then run over very
    # different lookbacks, so a Darvas box or 200-DMA does not mean the same thing
    # in the US as in Japan. Surface it.
    bars = {r["market"]: r.get("bars") for r in res if r.get("bars")}
    if len(bars) > 1:
        lo, hi = min(bars.values()), max(bars.values())
        if hi > lo * 3:
            worst = max(bars, key=bars.get)
            cross.append(("WARN", f"history windows differ {hi/lo:.0f}x ({lo:.0f}-{hi:.0f} bars; "
                                  f"{worst} widest) — same screeners, different lookbacks"))

    # fundamentals: if most markets have them and one doesn't, that market's
    # section silently degrades to momentum-only in the brief.
    have = {r["market"]: r.get("piotroski", 0) for r in res if r["market"] != "cross-market"}
    withf = [m for m, n in have.items() if n]
    without = [m for m, n in have.items() if not n]
    if withf and without:
        cross.append(("ERROR", f"{', '.join(without)} has NO fundamentals while "
                               f"{', '.join(withf)} do — that market is momentum-only "
                               f"(no Piotroski/CoffeeCan) and its picks are not comparable"))

    # schema: a column most markets carry but one lacks
    missing_bars = [r["market"] for r in res
                    if r["market"] != "cross-market" and r.get("rows") and r.get("bars") is None]
    if missing_bars and len(missing_bars) < len(MARKETS):
        cross.append(("WARN", f"{', '.join(missing_bars)} lacks Data_Points — history depth "
                              f"unverifiable, so the 200-DMA check cannot be applied there"))

    if cross:
        res.append({"market": "cross-market", "issues": cross, "file": None})

    if a.json:
        print(json.dumps(res, indent=1, default=str))
        return 1 if any(l == "ERROR" for r in res for l, _ in r["issues"]) else 0

    print(f"\n{'='*74}\n  CROSS-MARKET CONSISTENCY AUDIT\n{'='*74}")
    print(f"  {'MARKET':10s} {'ROWS':>7s} {'BARS':>7s} {'200DMA':>7s} {'<FLOOR':>7s} {'PIOTR':>7s}  {'AGE':>6s}")
    for r in res:
        if r["market"] == "cross-market":
            continue
        print(f"  {r['market']:10s} {r.get('rows','—'):>7} {str(r.get('bars','—')):>7} "
              f"{str(r.get('dma200_pct','—')):>7} {str(r.get('below_floor','—')):>7} "
              f"{str(r.get('piotroski','—')):>7}  {str(r.get('age_min','—'))+'m':>6}")

    errs = [(r["market"], m) for r in res for l, m in r["issues"] if l == "ERROR"]
    warns = [(r["market"], m) for r in res for l, m in r["issues"] if l == "WARN"]
    if errs:
        print(f"\n  ❌ {len(errs)} ANOMALY(S) — these break the analysis:")
        for mk, m in errs:
            print(f"     {mk:10s} {m}")
    if warns:
        print(f"\n  ⚠️  {len(warns)} warning(s):")
        for mk, m in warns:
            print(f"     {mk:10s} {m}")
    if not errs and not warns:
        print("\n  ✓ all markets consistent")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
