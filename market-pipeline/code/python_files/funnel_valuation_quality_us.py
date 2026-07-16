#!/usr/bin/env python3
"""
funnel_valuation_quality_us.py — CURRENT snapshot of the 4-stage sequential screen
(quality -> health -> valuation -> cash quality) on the latest point-in-time US
fundamentals. This is NOT a backtest (see sweep_valuation_quality_us.py for the
historical forward-return test) — it answers "which stocks pass every gate TODAY",
reporting how many survive each stage and the final candidate list.

STAGE ORDER, and why each is a FILTER not a re-rank of the prior stage's survivors
-----------------------------------------------------------------------------------
  0. UNIVERSE            all tickers with usable latest-year fundamentals
  1. QUALITY (ROCE)       ROCE > 15%             (piotroski_plus.py's own hurdle)
  2. HEALTH (F-Score)     Piotroski F-score >= 7  (out of 9; canonical, unweighted)
  3. VALUE (Earnings Yld) top 20% by EBIT/EV, RANKED WITHIN the stage-2 survivors
  4. CASH QUALITY (Sloan) accrual ratio < 0

Ranking "top 20%" WITHIN each stage's surviving pool (not the full universe) is
deliberate: the framework's claim is a CONJUNCTION ("quality AND cheap"), and
ranking valuation across the whole universe first would let expensive-but-quality
names get cut before the quality gate even runs. sweep_valuation_quality_us.py
tests both orders explicitly (EY across ALL vs. EY WITHIN the quality-passed tier)
precisely because the two are not equivalent and this project doesn't assume it.

Altman Z-Score is NOT in this funnel yet — it is the next scoped step (the "full
4-factor stack"), not silently substituted or approximated here.

LATEST DATA, NOT "TODAY" IN THE POINT-IN-TIME SENSE: unlike the backtest, this
script does not gate on `filed <= some historical t` — it uses the MOST RECENT
filing per ticker and the MOST RECENT price, i.e. it answers "what would the
screen say right now", not "what did it say as-of some past date". That is the
correct construct for a recommendation, and the wrong one for a backtest — the
two scripts are not interchangeable.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import duckdb
import numpy as np
import pandas as pd

import factor_valuation_quality as FV
import piotroski_plus as PP

FUND = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet"
PX = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"
ROCE_HURDLE = 0.15
F_HURDLE = 7.0
EY_TOP_PCT = 0.20
PURE9 = {n: 1.0 for n in PP.PIOTROSKI_TESTS}


def _f9(cur, prv) -> float | None:
    """Canonical unweighted Piotroski F, scaled to /9 when a test was skipped —
    same scaling fundamentals_cache.py already uses for the daily brief."""
    d = {}
    roa, roa_p = cur.net_income / cur.total_assets, prv.net_income / prv.total_assets
    d["1_roa_positive"] = bool(roa > 0)
    d["2_cfo_positive"] = bool(cur.cfo > 0)
    d["3_roa_improving"] = bool(roa > roa_p)
    d["4_accruals_cfo_gt_roa"] = bool(cur.cfo / cur.total_assets > roa)
    d["5_leverage_falling"] = (
        bool(cur.long_term_debt / cur.total_assets < prv.long_term_debt / prv.total_assets)
        if pd.notna(cur.long_term_debt) and pd.notna(prv.long_term_debt) else None)
    d["6_current_ratio_rising"] = bool(cur.current_assets / cur.current_liabilities
                                       > prv.current_assets / prv.current_liabilities)
    d["7_no_dilution"] = bool(cur.shares <= prv.shares * 1.01)
    d["8_gross_margin_rising"] = (
        bool(cur.gross_profit / cur.revenue > prv.gross_profit / prv.revenue)
        if pd.notna(cur.gross_profit) and pd.notna(prv.gross_profit)
        and cur.revenue and prv.revenue else None)
    d["9_asset_turnover_rising"] = bool(cur.revenue / cur.total_assets
                                        > prv.revenue / prv.total_assets)
    w = PP.weigh(d, PURE9)
    if w["pct"] is None or w["possible"] < 6:   # too sparse to be a score
        return None
    return round(w["pct"] / 100 * 9, 2)


def main() -> int:
    con = duckdb.connect()
    f = con.execute(f"""
        SELECT ticker, CAST(fy_end AS DATE) fy_end, CAST(filed AS DATE) filed,
               ebit, net_income, cfo, total_assets, current_assets, current_liabilities,
               long_term_debt, short_term_debt, cash, shares, revenue, gross_profit, equity
        FROM '{FUND}'
        WHERE ebit IS NOT NULL AND net_income IS NOT NULL AND cfo IS NOT NULL
          AND total_assets > 0 AND current_assets IS NOT NULL AND current_liabilities > 0
          AND shares > 0 AND revenue > 0
        ORDER BY ticker, fy_end
    """).df()
    f["ce"] = f.total_assets - f.current_liabilities
    f = f[f.ce > 0].copy()
    f["roce"] = f.ebit / f.ce

    latest_px = con.execute(f"""
        SELECT Symbol, Close, Date FROM (
          SELECT Symbol, Close, Date,
                 row_number() OVER (PARTITION BY Symbol ORDER BY Date DESC) rn
          FROM '{PX}' WHERE Close > 0)
        WHERE rn = 1
    """).df().set_index("Symbol")

    print(f"\n{'='*84}\n  4-STAGE FUNNEL — US, latest available filing per ticker "
          f"(as of price date {latest_px.Date.max().date() if len(latest_px) else '?'})"
          f"\n{'='*84}")
    print("  Educational/research only. NOT investment advice.\n")

    # RECENCY GUARD. g.iloc[-1] is the latest row that SURVIVED the WHERE filters
    # above (ebit/net_income/cfo/total_assets/current_assets/current_liabilities/
    # shares/revenue all required) — not necessarily the ticker's latest FILING.
    # Found live: GCO's revenue tag goes NaN for every fy_end after 2013-02-02
    # despite filings existing through 2026, so iloc[-1] silently returned a
    # 13-YEAR-OLD row as "current." Confirmed systemic, not isolated: EVC, WNC,
    # LFVN, STLD show the identical pattern (revenue extraction stops years before
    # their actual latest filing) — 5 of 12 names in one funnel run. This is a
    # collector-side revenue-tag coverage gap (separate, larger fix), but the
    # acute problem here is presenting stale data as a current recommendation.
    # 550 days ~ 18 months: a genuinely current annual filing can legitimately sit
    # up to ~400 days old (the collector's own filing-lag tolerance) plus a few
    # months before the NEXT fiscal year is filed: outside that window, treat the
    # ticker as having no current, usable data rather than silently downgrading
    # to old data.
    RECENCY_LIMIT_DAYS = 550
    today = pd.Timestamp.today()
    stale_skipped = 0

    rows = []
    for tk, g in f.groupby("ticker"):
        if len(g) < 2:
            continue
        cur, prv = g.iloc[-1], g.iloc[-2]
        if (today - pd.Timestamp(cur.fy_end)).days > RECENCY_LIMIT_DAYS:
            stale_skipped += 1
            continue
        px = latest_px.Close.get(tk)
        if px is None:
            continue
        f9 = _f9(cur, prv)
        market_cap = cur.shares * px
        ev = FV.enterprise_value(market_cap, cur.long_term_debt, cur.short_term_debt, cur.cash)
        ey = FV.earnings_yield(cur.ebit, ev)
        sloan = FV.sloan_ratio(cur.net_income, cur.cfo, cur.total_assets)
        rows.append({
            "Symbol": tk, "fy_end": str(cur.fy_end), "filed": str(cur.filed),
            "roce": cur.roce, "f_score": f9, "earnings_yield": ey, "sloan_ratio": sloan,
            "market_cap": market_cap,
        })
    d = pd.DataFrame(rows)
    n0 = len(d)
    print(f"  STAGE 0  universe (usable fundamentals + a live price)      {n0:>6,}")
    print(f"           ({stale_skipped:,} tickers excluded: latest usable filing "
          f">{RECENCY_LIMIT_DAYS}d old, not current data)")

    s1 = d[d.roce > ROCE_HURDLE].copy()
    print(f"  STAGE 1  ROCE > {ROCE_HURDLE*100:.0f}%                                        "
          f"{len(s1):>6,}   ({len(s1)/n0*100:.1f}% of universe)")

    s2 = s1[s1.f_score.notna() & (s1.f_score >= F_HURDLE)].copy()
    print(f"  STAGE 2  + Piotroski F-Score >= {F_HURDLE:.0f}/9                         "
          f"{len(s2):>6,}   ({len(s2)/max(len(s1),1)*100:.1f}% of stage 1)")

    s2v = s2[s2.earnings_yield.notna()].copy()
    n_cut = max(1, round(len(s2v) * EY_TOP_PCT))
    s3 = s2v.nlargest(n_cut, "earnings_yield") if len(s2v) else s2v
    print(f"  STAGE 3  + Earnings Yield top {EY_TOP_PCT*100:.0f}% (of stage 2, EV-priceable)     "
          f"{len(s3):>6,}   ({len(s3)/max(len(s2),1)*100:.1f}% of stage 2)")

    s4 = s3[s3.sloan_ratio.notna() & (s3.sloan_ratio < 0)].copy()
    print(f"  STAGE 4  + Sloan Ratio < 0 (cash-backed earnings)             "
          f"{len(s4):>6,}   ({len(s4)/max(len(s3),1)*100:.1f}% of stage 3)")

    print(f"\n  {'='*80}\n  FINAL RECOMMENDATION LIST — {len(s4)} names passed all 4 stages\n  {'='*80}")
    if len(s4):
        out = s4.sort_values("earnings_yield", ascending=False)[
            ["Symbol", "roce", "f_score", "earnings_yield", "sloan_ratio", "market_cap", "fy_end", "filed"]
        ]
        with pd.option_context("display.max_rows", None, "display.width", 140):
            disp = out.copy()
            disp["roce"] = (disp.roce * 100).round(1).astype(str) + "%"
            disp["earnings_yield"] = (disp.earnings_yield * 100).round(1).astype(str) + "%"
            disp["sloan_ratio"] = disp.sloan_ratio.round(3)
            disp["market_cap"] = (disp.market_cap / 1e9).round(2).astype(str) + "B"
            print(disp.to_string(index=False))
        out.to_csv("reports/funnel_valuation_quality_us.csv", index=False)
        print("\n  -> reports/funnel_valuation_quality_us.csv")
    else:
        print("  none — funnel is empty at current thresholds")

    print(f"\n  NOTE: India/Europe/Japan/Korea are not run here — their point-in-time "
          f"fundamentals warehouses\n  are not yet reliable enough for this screen "
          f"(India's screener.in collection is ~1% complete;\n  EU/JP/KR have no "
          f"point-in-time collection at all yet). Wiring them is a separate, scoped step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
