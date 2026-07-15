#!/usr/bin/env python3
"""
sweep_piotroski_plus.py — weight-vector sweep on REAL 10-year point-in-time data.

Supersedes backtest_piotroski_plus.py, which was starved: yfinance carries ~5 annual
statements, leaving 2 usable rebalances after the reporting lag and the prior-year a
Piotroski delta needs. This reads screener.in's collected history instead —
10 fiscal years (2017-2026) — which is what makes ~8 rebalances possible.

TESTS AVAILABLE FROM THIS SOURCE — 8 of 9, and which 8 matters
--------------------------------------------------------------
  1 ROA > 0                net_income / TA          TA = eq+res+bor+other_liab
  2 CFO > 0                cfo
  3 dROA > 0
  4 accruals CFO/TA > ROA
  5 leverage falling       borrowings / TA
  6 current ratio rising   CA ~ receivables+inventory+cash ; CL ~ other_liab   APPROX
  7 no dilution            shares
  8 gross margin rising    NOT AVAILABLE — screener.in's annual P&L has no COGS line
                           (it itemises Raw Material Cost, Power and Fuel, Employee
                           Cost etc. separately, and which of those are "cost of
                           goods" is a judgement call, not a fact). Skipped rather
                           than guessed.
  9 asset turnover rising  revenue / TA
  10-12 ROCE block         ebit / capital_employed, 10y CV, trend — ALL THREE

Test 6 is an APPROXIMATION and is labelled as one: screener.in's balance sheet does
not split current from non-current, so "Other Liabilities" stands in for current
liabilities and receivables+inventory+cash for current assets. It is directionally
right and wrong in level. It is included because excluding it would drop Piotroski's
only liquidity test entirely; it is flagged here so nobody reads test 6 as exact.

NO-LOOKAHEAD
------------
screener.in exposes the fiscal PERIOD-END but not the filing date. SEBI LODR requires
audited annuals within ~60 days of FY-end; this uses 120 to be conservative. At
rebalance t only fiscal years with fy_end + 120d <= t are visible. Rebalances are
1 August, so a 31-March year-end has cleared.

WHAT SURVIVORSHIP LOOKS LIKE HERE — better, still not clean
-----------------------------------------------------------
The universe comes from ltm/IN.parquet, which retains 964 delisted symbols. But
screener.in only serves pages for LISTED companies, so a firm that delisted in 2019
still has no fundamentals and cannot be scored. The bias is smaller than the yfinance
route (10y of history means a 2019 delisting at least had scoreable years BEFORE it
died, if it was collected) but it is not zero. Results remain an upper bound.
"""
from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")

import duckdb
import numpy as np
import pandas as pd

import piotroski_plus as PP

FUND = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/IN.parquet"
PX = "/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"
LAG_DAYS = 120
HOLD = 252
TOP_N = 20
ROCE_CV_HURDLE = PP.ROCE_CV_HURDLE
ROCE_LEVEL_HURDLE = PP.ROCE_LEVEL_HURDLE


def load():
    con = duckdb.connect()
    f = con.execute(f"""
        SELECT ticker, CAST(fy_end AS DATE) fy_end, net_income, revenue, cfo, shares,
               equity_capital, reserves, borrowings, other_liab,
               receivables, inventory, cash, ebit, capital_employed, roce,
               raw_material_cost, change_in_inventory, power_and_fuel, other_mfr_exp
        FROM '{FUND}' WHERE ebit IS NOT NULL AND capital_employed > 0
    """).df()
    f["ta"] = (f["equity_capital"].fillna(0) + f["reserves"].fillna(0)
               + f["borrowings"].fillna(0) + f["other_liab"].fillna(0))
    f = f[f["ta"] > 0].sort_values(["ticker", "fy_end"])
    return con, f


def tests(cur, prv, hist) -> dict:
    """The 8 available Piotroski tests + the 3 ROCE tests, as raw booleans."""
    d = {}
    roa = cur.net_income / cur.ta if cur.ta else None
    roa_p = prv.net_income / prv.ta if prv.ta else None
    d["1_roa_positive"] = bool(roa > 0) if roa is not None else None
    d["2_cfo_positive"] = bool(cur.cfo > 0) if pd.notna(cur.cfo) else None
    d["3_roa_improving"] = bool(roa > roa_p) if None not in (roa, roa_p) else None
    d["4_accruals_cfo_gt_roa"] = (bool(cur.cfo / cur.ta > roa)
                                  if pd.notna(cur.cfo) and cur.ta and roa is not None else None)
    lv = cur.borrowings / cur.ta if pd.notna(cur.borrowings) and cur.ta else None
    lv_p = prv.borrowings / prv.ta if pd.notna(prv.borrowings) and prv.ta else None
    d["5_leverage_falling"] = bool(lv < lv_p) if None not in (lv, lv_p) else None
    # TEST 6 IS DROPPED — the proxy FAILED validation and was never trustworthy.
    #
    # The proxy was (receivables+inventory+cash) / other_liab, because screener.in's
    # balance sheet has no current/non-current split. It was justified on the argument
    # that Piotroski test 6 only needs the SIGN of the change, so a stable level bias
    # would cancel in the delta. That argument was never tested — it was asserted.
    #
    # Measured (validate_current_ratio_proxy.py, reconstructed from yfinance since
    # screener.in blocked us; other_liab := total_assets - equity - debt, screener's
    # own definition), 237 company-years / 60 liquid Indian tickers:
    #     LEVEL: true median 1.37 vs proxy median 0.68  — off by ~2x
    #     SIGN : 62.1% agreement vs a 57.6% majority-guess baseline
    # A 4.5pp edge over guessing, on n=177. The bias is NOT stable, so it does NOT
    # cancel in the delta. The decision rule (>=80 sound / 65-80 marginal / <65 drop)
    # was fixed BEFORE the measurement precisely so this could not be rationalised
    # afterwards. 62.1% -> DROP.
    #
    # Skipped, not zeroed: weigh() removes it from both numerator and denominator, so
    # India scores on 8 tests and stays comparable to US scores on 9. Scoring it 0
    # would silently penalise every Indian company for a data gap.
    d["6_current_ratio_rising"] = None
    d["7_no_dilution"] = (bool(cur.shares <= prv.shares * 1.01)
                          if pd.notna(cur.shares) and pd.notna(prv.shares) and prv.shares else None)
    # Test 8: gross margin, computed HERE from the raw cost lines rather than read from
    # the collector's gross_margin column. Two reasons:
    #  1. The running collection loaded the collector module BEFORE the manufacturer
    #     gate was added, so its gross_margin column is the UNGATED version — wrong for
    #     services firms (it would put TCS at ~98% against a true ~42%).
    #  2. Deriving it here keeps the gate next to the test that depends on it.
    # MANUFACTURERS ONLY (rm/sales >= 0.30), where the formula is validated against
    # yfinance's true Gross Profit at -0.1pp error (n=50). Below that it is skipped, not
    # guessed: screener.in never splits Employee Cost into direct vs SG&A, so a services
    # COGS cannot be built from this source.
    def _gm(r):
        if not (pd.notna(r.raw_material_cost) and r.revenue and r.revenue > 0):
            return None
        if r.raw_material_cost / r.revenue < 0.30:      # not a manufacturer
            return None
        cogs = (r.raw_material_cost - (r.change_in_inventory or 0)
                + (r.power_and_fuel or 0) + (r.other_mfr_exp or 0))
        return (r.revenue - cogs) / r.revenue
    gm, gm_p = _gm(cur), _gm(prv)
    d["8_gross_margin_rising"] = bool(gm > gm_p) if None not in (gm, gm_p) else None
    at = cur.revenue / cur.ta if pd.notna(cur.revenue) and cur.ta else None
    at_p = prv.revenue / prv.ta if pd.notna(prv.revenue) and prv.ta else None
    d["9_asset_turnover_rising"] = bool(at > at_p) if None not in (at, at_p) else None

    d["10_roce_level"] = bool(cur.roce > ROCE_LEVEL_HURDLE) if pd.notna(cur.roce) else None
    if len(hist) >= 3 and abs(np.mean(hist)) > 0.01:
        cv = float(np.std(hist) / abs(np.mean(hist)))
        d["11_roce_stable"] = bool(cv < ROCE_CV_HURDLE)
        d["12_roce_not_deteriorating"] = bool(cur.roce >= np.mean(hist))
    else:
        d["11_roce_stable"] = d["12_roce_not_deteriorating"] = None
    return d


def main() -> int:
    con, f = load()
    print(f"\n{'='*80}\n  PIOTROSKI PLUS — WEIGHT SWEEP | India | 10y PIT | hold {HOLD}d"
          f"\n{'='*80}")
    print("  Educational/research only. NOT investment advice.")
    print("  Survivorship: screener.in serves LISTED companies only — upper bound.\n")
    print(f"  fundamentals: {len(f):,} ticker-years | {f.ticker.nunique():,} tickers | "
          f"{f.fy_end.min()} .. {f.fy_end.max()}")

    rebals = [pd.Timestamp(f"{y}-08-01") for y in range(2018, 2026)]
    # forward returns anchored to the first trading day >= t (2021-08-01 was a SUNDAY;
    # an exact-date join silently drops such rebalances)
    ds = ", ".join(f"DATE '{d.date()}'" for d in rebals)
    con.execute(f"""
    CREATE OR REPLACE TABLE px AS SELECT Date, Symbol, Close FROM '{PX}' WHERE Close>0;
    CREATE OR REPLACE TABLE ca AS
      SELECT Symbol, Date, CASE WHEN prev>0 AND (Close/prev-1 < -0.50 OR Close/prev-1 > 1.00)
                                THEN 1 ELSE 0 END is_ca
      FROM (SELECT Symbol, Date, Close, lag(Close) OVER (PARTITION BY Symbol ORDER BY Date) prev FROM px);
    CREATE OR REPLACE TABLE fw AS
      SELECT p.Symbol, p.Date, p.Close,
             lead(p.Close,{HOLD}) OVER (PARTITION BY p.Symbol ORDER BY p.Date) fwd,
             last_value(p.Close) OVER (PARTITION BY p.Symbol ORDER BY p.Date
               ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) last_px,
             sum(c.is_ca) OVER (PARTITION BY p.Symbol ORDER BY p.Date
               ROWS BETWEEN 1 FOLLOWING AND {HOLD} FOLLOWING) ca_ahead
      FROM px p JOIN ca c ON p.Symbol=c.Symbol AND p.Date=c.Date;
    """)
    ret = con.execute(f"""
      WITH rb AS (SELECT unnest([{ds}]) t),
      anchor AS (SELECT rb.t, min(fw.Date) d FROM rb JOIN fw ON fw.Date >= rb.t GROUP BY rb.t)
      SELECT a.t, f.Symbol, coalesce(f.fwd, f.last_px)/f.Close - 1 fwd_ret
      FROM anchor a JOIN fw f ON f.Date = a.d
      WHERE coalesce(f.ca_ahead,0)=0 AND f.Close>0
    """).df()
    ret["t"] = pd.to_datetime(ret["t"])
    rmap = {(r.Symbol, r.t): r.fwd_ret for r in ret.itertuples()}
    print(f"  forward returns: {len(ret):,} rows over {ret.t.nunique()} rebalances\n")

    rows = []
    by_t = {tk: g.reset_index(drop=True) for tk, g in f.groupby("ticker")}
    for t in rebals:
        cut = t - pd.Timedelta(days=LAG_DAYS)
        for tk, g in by_t.items():
            vis = g[g.fy_end <= cut]   # cut is a Timestamp; .date() raises on datetime64
            if len(vis) < 2:
                continue
            cur, prv = vis.iloc[-1], vis.iloc[-2]
            hist = vis["roce"].dropna().tolist()
            r = tests(cur, prv, hist)
            fr = rmap.get((tk, t))
            if fr is None or fr != fr:
                continue
            rec = {"Symbol": tk, "t": t, "fwd_ret": fr}
            for p in PP.PRESETS:
                rec[p] = PP.weigh(r, p)["pct"]
            rows.append(rec)
    d = pd.DataFrame(rows)
    if d.empty:
        print("  no scored rows"); return 1
    print(f"  scored panel: {len(d):,} stock-years | {d.Symbol.nunique():,} symbols | "
          f"{d.t.nunique()} rebalances\n")

    print(f"  === TOP-{TOP_N} PORTFOLIO PER VECTOR (12m hold, equal weight) ===")
    print(f"  {'vector':11s} {'mean':>7s} {'median':>7s} {'vs univ':>8s} {'beat univ':>10s} {'worst':>7s}")
    uni = d.groupby("t")["fwd_ret"].mean()
    print(f"  {'[universe]':11s} {uni.mean()*100:>6.1f}% {uni.median()*100:>6.1f}% "
          f"{'--':>8s} {'--':>10s} {uni.min()*100:>6.1f}%")
    res = {}
    for p in PP.PRESETS:
        pr = []
        for t, g in d.groupby("t"):
            g2 = g[g[p].notna()]
            if len(g2) < TOP_N:
                continue
            pr.append((t, g2.nlargest(TOP_N, p)["fwd_ret"].mean(), g2["fwd_ret"].mean()))
        if not pr:
            continue
        x = pd.DataFrame(pr, columns=["t", "port", "uni"])
        x["ex"] = x.port - x.uni
        res[p] = x
        print(f"  {p:11s} {x.port.mean()*100:>6.1f}% {x.port.median()*100:>6.1f}% "
              f"{x.ex.mean()*100:>+7.1f}% {int((x.ex>0).sum()):>4}/{len(x):<5} {x.port.min()*100:>6.1f}%")

    print("\n  === excess vs universe, year by year — where a 'winner' is made or broken ===")
    print(f"  {'year':6s} " + " ".join(f"{p:>11s}" for p in res))
    for t in sorted({t for p in res for t in res[p].t}):
        cells = []
        for p in res:
            v = res[p][res[p].t == t]["ex"]
            cells.append(f"{v.iloc[0]*100:>+10.1f}%" if len(v) else f"{'--':>11s}")
        print(f"  {t.year:<6} " + " ".join(cells))

    n = max(len(x) for x in res.values()) if res else 0
    print(f"\n  {n} rebalances. canonical is the CONTROL: a weighted vector that cannot")
    print("  beat all-weights-1.0 is fitting noise. With single-digit observations and")
    print("  stocks co-moving within a year, effective n is nearer the rebalance count")
    print("  than the row count — read the year-by-year, not the mean.")
    d.to_csv("reports/sweep_piotroski_plus_india.csv", index=False)
    print("  -> reports/sweep_piotroski_plus_india.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
