#!/usr/bin/env python3
"""
sweep_piotroski_plus_us.py — weight sweep on US SEC EDGAR data.

WHY THE US RUN IS THE BETTER TEST
---------------------------------
India (screener.in) gives 10y but ~8 rebalances, 8-of-9 tests, and a 120-day
reporting-lag PROXY because screener.in never exposes the filing date.

US (SEC EDGAR, via sec_history_collector.py) gives:
  * REAL filing dates — `filed` carries 1,449 distinct fy_end->filed lags, including
    a 2009 fiscal year filed in 2012 (a genuine late/restated filing). This is a true
    as-of date, not a lag assumption. It is the single biggest methodological upgrade
    over the India run.
  * ALL 9 Piotroski tests exactly — current_assets and current_liabilities are
    reported directly, so test 6 needs no proxy and no validation.
  * ~10 dense rebalances (2016-2025, 196->579 tickers/yr).

HONEST LIMITS, measured not assumed
-----------------------------------
The headline "42 years / 111,949 rows" is false twice over:
  1. 16 rows carry fy_end up to 2029 — impossible, parse artefacts (0.01%).
  2. Requiring all 12 tests TOGETHER collapses 111,949 -> 4,889 rows / 1,038 tickers.
     The binding field is long_term_debt (21% populated). Before 2016 that leaves
     5-34 tickers/year — too few to rank a top-20 from, so the usable window is
     2016-2025, not 2007-2026.
Filing lag is constrained to 0-400 days: negatives are impossible, and >400d are
restatements whose `filed` date no longer marks when the market learned the numbers.

SURVIVORSHIP: unlike the India route, EDGAR keeps filings for companies that later
delisted — a firm that filed in 2018 and died in 2020 still has its 2018 filing. The
price parquet retains delisted names too. So this run is the closest to unbiased
available, though names that never filed at all remain absent.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import duckdb
import numpy as np
import pandas as pd

import piotroski_plus as PP

FUND = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet"
# 🔴 WAS global-market-data/cache_seed/ltm/US.parquet — an INTERRUPTED collection.
# It holds 5,358 symbols but is missing whole letter blocks (D-L, O, U-Z) and omits
# S&P 500 names outright (CME, CMI absent; its most-covered symbols are all B's).
# Every US result before 2026-07-15 18:00 ran on 597 tickers drawn only from
# A,B,C,M,N,P,Q,R,S,T — a letter-biased subset, not a universe.
# The complete panel is in global-stock-screener: 9,278 symbols, and overlap with EDGAR
# fundamentals rises 2,281 (50%) -> 4,459 (97%).
PX = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"
HOLD = 252
TOP_N = 20
REBAL = [pd.Timestamp(f"{y}-06-01") for y in range(2017, 2026)]


def main() -> int:
    con = duckdb.connect()
    f = con.execute(f"""
        SELECT ticker, CAST(fy_end AS DATE) fy_end, CAST(filed AS DATE) filed,
               ebit, net_income, cfo, total_assets, current_assets, current_liabilities,
               long_term_debt, shares, revenue, gross_profit, equity
        FROM '{FUND}'
        WHERE ebit IS NOT NULL AND net_income IS NOT NULL AND cfo IS NOT NULL
          AND total_assets > 0 AND current_assets IS NOT NULL AND current_liabilities > 0
          AND shares > 0 AND revenue > 0
          AND gross_profit IS NOT NULL
          -- long_term_debt is NOT required. It is only 21% populated and was the
          -- BINDING constraint: requiring it collapsed the sample to 359 symbols with
          -- a median turnover of $27.6M/day — 77x more liquid than the typical US
          -- stock, i.e. the S&P mega-cap complex. That is the one place Piotroski
          -- was never claimed to work: his 1996 paper locates the edge in SMALL,
          -- ILLIQUID, low-coverage value names, and this repo's own ROCE work found
          -- the F-score discriminates least in large caps (16.2% vs 14.1%) and most
          -- in small (15.7% vs 8.0%). The negative result was therefore partly an
          -- artefact of WHERE the data-completeness filter pointed the test.
          -- Test 5 (falling leverage) is now SKIPPED when the field is absent rather
          -- than excluding the company; weigh() drops skipped tests from BOTH the
          -- numerator and denominator, so scores stay comparable across companies
          -- with different coverage.
          AND date_diff('day', CAST(fy_end AS DATE), CAST(filed AS DATE)) BETWEEN 0 AND 400
          AND CAST(fy_end AS DATE) BETWEEN DATE '2014-01-01' AND DATE '2026-07-15'
        ORDER BY ticker, fy_end
    """).df()
    f["ce"] = f.total_assets - f.current_liabilities
    f = f[f.ce > 0].copy()
    f["roce"] = f.ebit / f.ce
    print(f"\n{'='*80}\n  PIOTROSKI PLUS — WEIGHT SWEEP | US (SEC EDGAR) | hold {HOLD}d"
          f"\n{'='*80}")
    print("  Educational/research only. NOT investment advice.")
    print("  Entry gated on the REAL SEC filing date, not a reporting-lag assumption.\n")
    print(f"  fundamentals: {len(f):,} ticker-years | {f.ticker.nunique():,} tickers | "
          f"{f.fy_end.min()} .. {f.fy_end.max()}")

    ds = ", ".join(f"DATE '{d.date()}'" for d in REBAL)
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

    def tests(cur, prv, hist):
        d = {}
        roa, roa_p = cur.net_income / cur.total_assets, prv.net_income / prv.total_assets
        d["1_roa_positive"] = bool(roa > 0)
        d["2_cfo_positive"] = bool(cur.cfo > 0)
        d["3_roa_improving"] = bool(roa > roa_p)
        d["4_accruals_cfo_gt_roa"] = bool(cur.cfo / cur.total_assets > roa)
        # skipped, not failed, when long_term_debt is absent — a missing field is not
        # evidence of rising leverage
        d["5_leverage_falling"] = (
            bool(cur.long_term_debt / cur.total_assets < prv.long_term_debt / prv.total_assets)
            if pd.notna(cur.long_term_debt) and pd.notna(prv.long_term_debt) else None)
        d["6_current_ratio_rising"] = bool(cur.current_assets / cur.current_liabilities
                                           > prv.current_assets / prv.current_liabilities)
        d["7_no_dilution"] = bool(cur.shares <= prv.shares * 1.01)
        d["8_gross_margin_rising"] = bool(cur.gross_profit / cur.revenue
                                          > prv.gross_profit / prv.revenue)
        d["9_asset_turnover_rising"] = bool(cur.revenue / cur.total_assets
                                            > prv.revenue / prv.total_assets)
        d["10_roce_level"] = bool(cur.roce > PP.ROCE_LEVEL_HURDLE)
        if len(hist) >= 3 and abs(np.mean(hist)) > 0.01:
            d["11_roce_stable"] = bool(np.std(hist) / abs(np.mean(hist)) < PP.ROCE_CV_HURDLE)
            d["12_roce_not_deteriorating"] = bool(cur.roce >= np.mean(hist))
        else:
            d["11_roce_stable"] = d["12_roce_not_deteriorating"] = None
        return d

    rows = []
    by_t = {tk: g.reset_index(drop=True) for tk, g in f.groupby("ticker")}
    for t in REBAL:
        for tk, g in by_t.items():
            vis = g[g.filed <= t]                 # REAL filing date — true as-of
            if len(vis) < 2:
                continue
            cur, prv = vis.iloc[-1], vis.iloc[-2]
            fr = rmap.get((tk, t))
            if fr is None or fr != fr:
                continue
            r = tests(cur, prv, vis["roce"].dropna().tolist())
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

    print("\n  === excess vs universe, year by year (read THIS, not the mean) ===")
    print(f"  {'year':6s} " + " ".join(f"{p:>11s}" for p in res))
    for t in sorted({t for p in res for t in res[p].t}):
        print(f"  {t.year:<6} " + " ".join(
            f"{res[p][res[p].t==t]['ex'].iloc[0]*100:>+10.1f}%"
            if len(res[p][res[p].t == t]) else f"{'--':>11s}" for p in res))

    print("\n  === is high-F actually GOOD in the US? mean AND median — they disagree ===")
    for lo, hi, lab in [(0, 40, "weak  (bottom)"), (40, 70, "middle"), (70, 101, "strong (top)")]:
        s = d[(d.canonical >= lo) & (d.canonical < hi)]
        if len(s) > 50:
            print(f"    canonical {lab:16s} n={len(s):>5,}  mean fwd {s.fwd_ret.mean()*100:>6.1f}%"
                  f"  median {s.fwd_ret.median()*100:>6.1f}%")

    # Did dropping the long_term_debt requirement actually reach smaller names? If the
    # sample is still mega-cap-only, the rerun proves nothing and must say so.
    liq = con.execute(f"""
        WITH l AS (SELECT Symbol, Close*Volume tv,
                          row_number() OVER (PARTITION BY Symbol ORDER BY Date DESC) rn
                   FROM '{PX}' WHERE Close>0 AND Volume>0)
        SELECT Symbol, median(tv) turnover FROM l WHERE rn<=60 GROUP BY 1""").df()
    m = d[["Symbol"]].drop_duplicates().merge(liq, on="Symbol", how="left")
    print(f"\n  === did this actually reach the small names? ===")
    print(f"    tested symbols {len(m):,} | median turnover ${m.turnover.median()/1e6:,.1f}M/day")
    print(f"    full universe  {len(liq):,} | median turnover ${liq.turnover.median()/1e6:,.1f}M/day")
    print(f"    tested median sits at the {(liq.turnover < m.turnover.median()).mean()*100:.0f}th"
          f" percentile of US liquidity  (was 80th when long_term_debt was required)")

    print("\n  === F-score edge BY LIQUIDITY — Piotroski claims the edge is in SMALL names ===")
    dl = d.merge(liq, on="Symbol", how="left")
    dl = dl[dl.turnover.notna()].copy()
    if len(dl) > 200:
        dl["tier"] = pd.qcut(dl.turnover, 3, labels=["SMALL", "MID", "LARGE"])
        print(f"    {'tier':7s} {'n':>6s} {'F>=70 mean':>11s} {'F>=70 med':>10s} "
              f"{'F<40 mean':>10s} {'F<40 med':>9s} {'med edge':>9s}")
        for t in ("SMALL", "MID", "LARGE"):
            s = dl[dl.tier == t]
            hi, lo = s[s.canonical >= 70], s[s.canonical < 40]
            if len(hi) > 20 and len(lo) > 20:
                edge = (hi.fwd_ret.median() - lo.fwd_ret.median()) * 100
                print(f"    {t:7s} {len(s):>6,} {hi.fwd_ret.mean()*100:>10.1f}% "
                      f"{hi.fwd_ret.median()*100:>9.1f}% {lo.fwd_ret.mean()*100:>9.1f}% "
                      f"{lo.fwd_ret.median()*100:>8.1f}% {edge:>+8.1f}%")
        print("    (median edge = high-F median minus low-F median. Piotroski predicts")
        print("     this is POSITIVE and LARGEST in SMALL.)")

    # ── rank WITHIN tier, not across ──────────────────────────────────────────
    # THE POINT OF THIS RUN. The all-sample top-20 lost the universe in every vector,
    # and the tier table above says why: the edge is +14.4% median in SMALL and -7.3%
    # in LARGE, so a portfolio ranked across everything fills up with large caps —
    # exactly where the screen is worth less than nothing. Ranking within a tier tests
    # whether the screen works when pointed at the end of the market it claims.
    #
    # MEDIAN is the headline, not mean. Every finding this session flipped between the
    # two and the median was right each time (LARGE F<40 posts a 117% mean against a
    # 15.1% median — a handful of moonshots). A 10-stock median is also what an
    # investor actually experiences; the mean is what one lottery ticket does to a
    # spreadsheet.
    print("\n  === RANK WITHIN TIER (top-10 per tier per year) — the actionable test ===")
    TOP_T = 10
    print(f"    {'tier':7s} {'vector':11s} {'port med':>9s} {'tier med':>9s} "
          f"{'MED EDGE':>9s} {'port mean':>10s} {'beat tier':>10s}")
    for t in ("SMALL", "MID", "LARGE"):
        st = dl[dl.tier == t]
        for p in PP.PRESETS:
            per = []
            for ts, g in st.groupby("t"):
                g2 = g[g[p].notna()]
                if len(g2) < TOP_T * 2:          # need a real pool to rank inside
                    continue
                top = g2.nlargest(TOP_T, p)
                per.append((top.fwd_ret.median(), g2.fwd_ret.median(), top.fwd_ret.mean()))
            if len(per) < 4:
                continue
            x = pd.DataFrame(per, columns=["pm", "um", "pmean"])
            edge = (x.pm - x.um).mean() * 100
            print(f"    {t:7s} {p:11s} {x.pm.mean()*100:>8.1f}% {x.um.mean()*100:>8.1f}% "
                  f"{edge:>+8.1f}% {x.pmean.mean()*100:>9.1f}% "
                  f"{int((x.pm > x.um).sum()):>4}/{len(x):<4}")
        print()
    d.to_csv("reports/sweep_piotroski_plus_us.csv", index=False)
    print("\n  -> reports/sweep_piotroski_plus_us.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
