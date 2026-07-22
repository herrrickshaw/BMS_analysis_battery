#!/usr/bin/env python3
# scan_bhavcopy.py
# ================
# Full NSE+BSE screener run sourced ENTIRELY from official exchange bhavcopy
# (via bhavcopy_history.py) — no Yahoo Finance, so no rate limiting.
#
# Price screeners (Darvas Box, Golden Crossover, volume) are computed fresh from
# the bhavcopy OHLCV. Fundamentals (Piotroski F-Score, Coffee Can) are quarterly
# and do not change day-to-day, so they are reused from the most recent existing
# full-scan workbook. Triple Hits are then RE-derived from the fresh Darvas
# breakouts combined with those fundamentals.
#
# Output matches the schema daily_combined_report.py expects:
#   sheets: All_Stocks, Darvas_Signals, Fundamentals, Triple_Hits, IPO_New_Listings
#   file:   indian_full_scan/indian_full_scan_<YYYYMMDD_HHMM>.xlsx

from __future__ import annotations

import glob
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

from bhavcopy_history import fetch_history
from full_indian_market_scan import compute_darvas_box, compute_golden_crossover
from stock_utils import parallel_map, pct_change

# ── percentile re-tier (adaptive_liquidity) ──────────────────────────────────
# scan_gate() assigned ABSOLUTE tiers, which cannot discriminate within a market:
# the first US sweep landed 94% of its sample in one tier because bands tuned to
# India's Rs 1cr floor cannot separate US stocks from each other. The floor stays
# absolute (correct, and per-symbol); tiers become PERCENTILE so "illiquid" means
# the same thing in every market and each market self-calibrates.
# Percentiles need the whole universe, so this runs once on the assembled frame
# rather than inside the per-symbol map.
def _retier(_df, _col):
    try:
        import adaptive_liquidity as _AL
        return _AL.retier(_df, turnover_col=_col)
    except Exception as _e:      # never let tiering break a scan
        print(f"  retier skipped: {str(_e)[:60]}")
        return _df


OUT_DIR = Path("indian_full_scan"); OUT_DIR.mkdir(exist_ok=True)


# ── liquidity gate + tiers ────────────────────────────────────────────────────
# WHY: without a liquidity floor the screener recommends stocks you cannot buy.
# On 2026-07-15, 5 of 13 golden-cross picks were untradeable — AUSTENG led the
# brief on a +16% move while turning over Rs 2.1 LAKH/day, and GKCONS turned over
# Rs 18,658/day. At that size a handful of trades sets the price, so the "signal"
# is noise. A Rs 1 crore/day floor also removes, without any instrument-type rule:
# corporate debt (875NHAI29 Rs 2.7L/day, 1018GS2026 Rs 10.8K), liquid-fund ETFs
# (LIQUIDSBI Rs 35L), and REIT/InvITs (EMBASSY Rs 55L, INDIGRID Rs 51L).
#
# Turnover is derived as Close x Volume rather than read from the bhavcopy's
# TtlTrfVal, so no schema change is needed. Validated against TtlTrfVal: 0.19%
# error on RELIANCE, 0.80% on 360ONE, 1.05% on DATAMATICS, and at the Rs 1cr gate
# the two disagree on just 1 of 7,838 symbols (1,344 vs 1,345 pass).
#
# Median (not mean) so a single block deal can't lift a dead stock over the bar.
LIQ_FLOOR = 10_000_000               # Rs 1 crore/day median turnover -> 1,344 of 7,838
LIQ_TIERS = ((1_000_000_000, "T1_MEGA"),    # >= Rs 100 cr/day   (61 symbols)
             (250_000_000,   "T2_LARGE"),   #    Rs 25-100 cr    (212)
             (50_000_000,    "T3_MID"),     #    Rs 5-25 cr      (405)
             (0,             "T4_SMALL"))   #    Rs 1-5 cr       (666)


def _liquidity(df):
    """(median daily turnover in Rs, tier) — tier is None when below the floor."""
    if df is None or "Volume" not in df.columns or "Close" not in df.columns:
        return 0.0, None
    tv = (df["Close"] * df["Volume"]).median()
    if tv is None or not (tv >= LIQ_FLOOR):
        return float(tv or 0), None
    for lo, name in LIQ_TIERS:
        if tv >= lo:
            return float(tv), name
    return float(tv), "T4_SMALL"


def _screen_one(item):
    """Run the price screeners on one symbol's bhavcopy OHLCV frame."""
    sym, df = item
    if df is None or len(df) < 60:
        return None
    turnover, tier = _liquidity(df)
    if tier is None:
        return None                  # below the liquidity floor — not tradeable
    d = compute_darvas_box(df)
    gc = compute_golden_crossover(df)
    ltp = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df) > 1 else ltp
    return {
        "Symbol": sym,
        "LTP": round(ltp, 2),
        "Prev_Close": round(prev, 2),
        "Change%": round(pct_change(ltp, prev) or 0, 2),
        "Darvas_Signal": d.get("signal"),
        "Box_Top": d.get("box_top"),
        "Box_Bottom": d.get("box_bottom"),
        "Upside_to_Top%": d.get("upside_to_top_pct"),
        "Position_in_Box%": d.get("position_in_box_pct"),
        "GC_Signal": "GOLDEN_CROSS" if gc.get("gc_signal") else "",
        "DMA50_above_200": gc.get("dma50_above_200"),
        "Median_Turnover": round(turnover),
        "Liquidity_Tier": tier,
        "Data_Points": len(df),
    }


def main():
    print(f"\n{'#'*72}\n  BHAVCOPY SCREENER — NSE + BSE (official EOD, no Yahoo)\n{'#'*72}")
    print("  Educational/research only. NOT investment advice.\n")

    print("Stage 1 — Assemble 1-year OHLCV history from bhavcopy …")
    hist = fetch_history(n_days=400, min_bars=200, verbose=True)
    print(f"  {len(hist)} symbols ready\n")

    print("Stage 2 — Price screeners (Darvas + Golden Cross) …")
    rows = parallel_map(_screen_one, list(hist.items()), workers=8,
                        label="stocks", progress_every=1000)
    all_df = pd.DataFrame([r for r in rows if r])
    all_df = _retier(all_df, "Median_Turnover")
    darvas_df = all_df[all_df["Darvas_Signal"].isin(["BREAKOUT_BUY", "BREAKDOWN_SELL"])]
    gc_n = int((all_df["GC_Signal"] == "GOLDEN_CROSS").sum())
    print(f"  {len(all_df)} screened | {len(darvas_df)} Darvas signals | {gc_n} golden crosses\n")

    print("Stage 3 — Fundamentals from the off-hours store …")
    # This used to REUSE the previous workbook's Fundamentals sheet
    # (fundamentals_cache), because computing them live cost one throttled
    # yfinance call per stock (~an hour). That reuse had a vicious side effect:
    # the sheet was seeded once by a throttled run that only reached the A's
    # (248 names, 94% A, stopping at BAJAJELEC), and the reuse then copied that
    # alphabet-truncated sheet forward VERBATIM, night after night. The brief's
    # "fundamental picks" were a photocopy of one bad run.
    #
    # The off-hours store (fundamentals_offhours.py) removes the reason reuse
    # existed: a store-served fundamental_scan takes ~20ms per stock, so the
    # WHOLE universe computes fresh in under a minute, alphabet-complete.
    # Store MISSES are skipped, not fetched live — a nightly path must never
    # contend with yfinance's rate limiter; a missing name simply carries no
    # fundamentals, exactly as before.
    fund_df = pd.DataFrame()
    try:
        import fundamentals_store_reader as _fsr
        from full_indian_market_scan import fundamental_scan as _fscan
        rows = []
        for _, _r in all_df.iterrows():
            _sym = str(_r["Symbol"]).upper()
            if not _fsr.has(_sym):
                continue                     # store miss -> no fundamentals, no live call
            res = _fscan(_sym, price=_r.get("LTP"))
            rows.append({
                "Symbol": _sym, "Suffix": ".NS",
                "LTP": _r.get("LTP"), "Change%": _r.get("Change%"),
                "Darvas_Signal": _r.get("Darvas_Signal"),
                "Box_Top": _r.get("Box_Top"), "Box_Bottom": _r.get("Box_Bottom"),
                "Upside_to_Top%": _r.get("Upside_to_Top%"),
                "GC_Signal": _r.get("GC_Signal"),
                "DMA50": _r.get("DMA50"), "DMA200": _r.get("DMA200"),
                "Piotroski_Score": res.get("f_score"),
                "Piotroski_Strong": "YES" if res.get("f_strong") else "NO",
                "CoffeeCan": "PASS" if res.get("qualifies_cc") else "FAIL",
                "CC_Score": res.get("cc_score"),
                "Revenue_CAGR_%": res.get("Revenue_CAGR_%"),
                "ROCE_avg_%": res.get("ROCE_avg_%"),
                "MagicFormula": "PASS" if res.get("qualifies_mf") else "FAIL",
                "ROIC_%": res.get("ROIC_%"),
                "Earnings_Yield_%": res.get("Earnings_Yield_%"),
                "BullCartel": "PASS" if res.get("qualifies_bc") else "FAIL",
                "Sales_Growth_YoY_%": res.get("Sales_Growth_YoY_%"),
                "Profit_Growth_YoY_%": res.get("Profit_Growth_YoY_%"),
                "Net_Profit_Cr": res.get("Net_Profit_Cr"),
                "Error": res.get("error", ""),
            })
        fund_df = pd.DataFrame(rows)
        n_store = sum(1 for r in rows if not r["Error"])
        print(f"  {len(fund_df)} names computed fresh from the store "
              f"({len(all_df) - len(fund_df)} not in store, skipped — no live calls)")
    except Exception as e:
        print(f"  store fundamentals failed ({type(e).__name__}: {str(e)[:60]}) — "
              "falling back to workbook reuse")
        try:
            import fundamentals_cache as _fc
            cached, src = _fc.load("indian_full_scan/*_full_scan_*.xlsx", key="Symbol")
            if cached:
                fund_df = pd.DataFrame(list(cached.values()))
        except Exception as e2:
            print(f"  no fundamentals reused either: {str(e2)[:70]}")
    if fund_df.empty:
        print("  ⚠️  India has NO fundamentals this run")

    fresh_darvas = dict(zip(all_df["Symbol"], all_df["Darvas_Signal"]))
    fresh_ltp = dict(zip(all_df["Symbol"], all_df["LTP"]))
    triple_rows = []
    if not fund_df.empty:
        # refresh each fundamental row's Darvas signal + LTP with today's bhavcopy
        fund_df["Darvas_Signal"] = fund_df["Symbol"].map(fresh_darvas).fillna(fund_df.get("Darvas_Signal"))
        if "LTP" in fund_df.columns:
            fund_df["LTP"] = fund_df["Symbol"].map(fresh_ltp).fillna(fund_df["LTP"])
        for _, r in fund_df.iterrows():
            cc = str(r.get("CoffeeCan", "")).upper() == "PASS"
            pio = str(r.get("Piotroski_Strong", "")).upper() == "YES"
            brk = str(r.get("Darvas_Signal", "")).upper() == "BREAKOUT_BUY"
            if cc and pio and brk:
                triple_rows.append(r)
    triple_df = pd.DataFrame(triple_rows)
    print(f"  {len(triple_df)} Triple Hits (CoffeeCan + Piotroski≥7 + fresh Darvas breakout)\n")

    # merge Piotroski into All_Stocks for Golden-Cross pick enrichment
    if not fund_df.empty and "Piotroski_Score" in fund_df.columns:
        pio_map = dict(zip(fund_df["Symbol"], fund_df["Piotroski_Score"]))
        all_df["Piotroski_Score"] = all_df["Symbol"].map(pio_map)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out = OUT_DIR / f"indian_full_scan_{ts}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        all_df.sort_values("Change%", ascending=False).to_excel(xw, "All_Stocks", index=False)
        darvas_df.sort_values("Upside_to_Top%", ascending=False, na_position="last")\
                 .to_excel(xw, "Darvas_Signals", index=False)
        if not fund_df.empty:
            fund_df.to_excel(xw, "Fundamentals", index=False)
        if not triple_df.empty:
            triple_df.to_excel(xw, "Triple_Hits", index=False)
    print(f"📄 → {out}")
    print(f"   Source: NSE+BSE bhavcopy (official EOD). Triple Hits: "
          f"{', '.join(triple_df['Symbol'].astype(str)) if not triple_df.empty else 'none today'}")
    return out


if __name__ == "__main__":
    main()
