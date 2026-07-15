#!/usr/bin/env python3
"""
daily_breakout_combo_us.py — darvas x piotroski7, scanned DAILY, cut by liquidity tier.

WHY THIS EXISTS
---------------
combo_by_tier_us.py tried to test the prior work's best result (darvas x piotroski7,
+9.9pp median, 62% win) and FAILED by design: a Darvas breakout is a rare DAILY event,
and sampling it on 9 annual rebalance dates caught ~3% of signals (117 total, giving
n=1 / n=7 / n=17 per tier). n=1 is not a result. This scans every trading day instead.

WHAT IT TESTS
-------------
Two screens with OPPOSITE liquidity gradients, measured on the annual panel:
    tier     darvas alone   F>=7 alone
    SMALL       -7.5%         +8.0%
    LARGE      +12.2%         -2.2%
If Darvas supplies the edge in large caps and Piotroski in small, then the prior work's
aggregate +9.9pp combo is averaging two mechanisms in different segments — and the
combo should behave very differently by tier. That is the hypothesis under test.

NO-LOOKAHEAD
------------
  * Darvas box uses bars STRICTLY BEFORE the signal bar (ROWS 60 PRECEDING AND 1
    PRECEDING). Including the current bar makes a breakdown undetectable and leaks the
    signal into its own box — the repo's standing rule.
  * Breakout fires on the FIRST cross only: close > box_top AND prev close <= box_top.
    Without this, one breakout re-counts every day it stays elevated, inflating n with
    duplicates of a single event.
  * A 10-bar cooldown per symbol suppresses re-entry churn on the same move.
  * F-score comes from the fundamentals PUBLIC at the signal date, gated on EDGAR's
    real `filed` date — not fiscal-year-end plus an assumed lag.
  * Forward return is the 252 bars AFTER the signal; delisting exits at the last real
    close (dropping them would re-introduce survivorship — a stock that dies is usually
    a stock that fell).
  * Corporate actions filtered: any |1-day move| outside [-50%, +100%] in the holding
    window voids the observation. Unadjusted splits previously manufactured a fake
    +12.20% mean with 248% sd.

STATS
-----
Winsorized 1/99 per calendar year (the prior work calls winsorization essential; raw
means are set by a few lottery movers). Median is the headline: every finding this
session flipped between mean and median and the median was right each time.

Signals CLUSTER IN TIME — breakouts fire together in rallies — so observations are not
independent and the effective n is far below the row count. Per-year breakdown is
printed for that reason; read it, not the pooled number.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import duckdb
import pandas as pd

FUND = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet"
PX = "/Users/umashankar/repos/global-market-data/cache_seed/ltm/US.parquet"
HOLD = 252
BOX = 60
COOLDOWN = 10


def main() -> int:
    con = duckdb.connect()
    print(f"\n{'='*78}\n  DARVAS x PIOTROSKI7 — DAILY SCAN, BY LIQUIDITY TIER | US"
          f"\n{'='*78}")
    print("  Educational/research only. NOT investment advice.\n")

    con.execute(f"""
    CREATE OR REPLACE TABLE px AS
      SELECT Date, Symbol, Close, High, Volume FROM '{PX}'
      WHERE Close>0 AND High>0 AND Volume>0 AND Date >= DATE '2016-06-01';
    CREATE OR REPLACE TABLE ca AS
      SELECT Symbol, Date,
             CASE WHEN prev>0 AND (Close/prev-1 < -0.50 OR Close/prev-1 > 1.00)
                  THEN 1 ELSE 0 END is_ca
      FROM (SELECT Symbol, Date, Close,
                   lag(Close) OVER (PARTITION BY Symbol ORDER BY Date) prev FROM px);
    -- box_top from bars STRICTLY BEFORE the signal bar
    CREATE OR REPLACE TABLE sig AS
      SELECT p.Symbol, p.Date, p.Close,
             max(p.High) OVER (PARTITION BY p.Symbol ORDER BY p.Date
                               ROWS BETWEEN {BOX} PRECEDING AND 1 PRECEDING) box_top,
             lag(p.Close) OVER (PARTITION BY p.Symbol ORDER BY p.Date) prev_close,
             median(p.Close*p.Volume) OVER (PARTITION BY p.Symbol ORDER BY p.Date
                               ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) turnover,
             lead(p.Close,{HOLD}) OVER (PARTITION BY p.Symbol ORDER BY p.Date) fwd,
             last_value(p.Close) OVER (PARTITION BY p.Symbol ORDER BY p.Date
                 ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) lastpx,
             sum(c.is_ca) OVER (PARTITION BY p.Symbol ORDER BY p.Date
                 ROWS BETWEEN 1 FOLLOWING AND {HOLD} FOLLOWING) ca_ahead
      FROM px p JOIN ca c ON p.Symbol=c.Symbol AND p.Date=c.Date;
    -- FIRST cross only, else one breakout re-counts every elevated day
    CREATE OR REPLACE TABLE brk AS
      SELECT Symbol, Date, Close, turnover,
             coalesce(fwd, lastpx)/Close - 1 AS fwd_ret
      FROM sig
      WHERE box_top IS NOT NULL AND prev_close IS NOT NULL
        AND Close > box_top AND prev_close <= box_top
        AND coalesce(ca_ahead,0)=0 AND turnover>0
        AND Date <= (SELECT max(Date) FROM px) - INTERVAL '{HOLD+30} days';
    """)
    b = con.execute("SELECT * FROM brk ORDER BY Symbol, Date").df()
    print(f"  raw first-cross breakouts: {len(b):,}")

    # cooldown: drop re-entries within COOLDOWN bars of the prior signal on that symbol
    b["Date"] = pd.to_datetime(b.Date)
    keep, last = [], {}
    for r in b.itertuples():
        p = last.get(r.Symbol)
        if p is None or (r.Date - p).days >= COOLDOWN * 1.4:
            keep.append(r.Index); last[r.Symbol] = r.Date
    b = b.loc[keep]
    print(f"  after {COOLDOWN}-bar cooldown: {len(b):,} signals, {b.Symbol.nunique():,} symbols")

    # F-score public at the signal date (EDGAR real filing date)
    f = con.execute(f"""
      SELECT ticker Symbol, CAST(filed AS DATE) filed, CAST(fy_end AS DATE) fy_end,
             net_income, cfo, total_assets, current_assets, current_liabilities,
             long_term_debt, shares, revenue, gross_profit
      FROM '{FUND}'
      WHERE net_income IS NOT NULL AND cfo IS NOT NULL AND total_assets>0
        AND current_assets IS NOT NULL AND current_liabilities>0 AND shares>0
        AND revenue>0 AND gross_profit IS NOT NULL
        AND date_diff('day',CAST(fy_end AS DATE),CAST(filed AS DATE)) BETWEEN 0 AND 400
      ORDER BY ticker, fy_end""").df()
    f["filed"] = pd.to_datetime(f.filed)

    import piotroski_plus as PP
    PURE = {n: 1.0 for n in PP.PIOTROSKI_TESTS}

    def tests(c_, p_):
        d = {}
        roa, roap = c_.net_income/c_.total_assets, p_.net_income/p_.total_assets
        d["1_roa_positive"] = bool(roa > 0)
        d["2_cfo_positive"] = bool(c_.cfo > 0)
        d["3_roa_improving"] = bool(roa > roap)
        d["4_accruals_cfo_gt_roa"] = bool(c_.cfo/c_.total_assets > roa)
        d["5_leverage_falling"] = (bool(c_.long_term_debt/c_.total_assets
                                        < p_.long_term_debt/p_.total_assets)
                                   if pd.notna(c_.long_term_debt) and pd.notna(p_.long_term_debt) else None)
        d["6_current_ratio_rising"] = bool(c_.current_assets/c_.current_liabilities
                                           > p_.current_assets/p_.current_liabilities)
        d["7_no_dilution"] = bool(c_.shares <= p_.shares*1.01)
        d["8_gross_margin_rising"] = bool(c_.gross_profit/c_.revenue > p_.gross_profit/p_.revenue)
        d["9_asset_turnover_rising"] = bool(c_.revenue/c_.total_assets > p_.revenue/p_.total_assets)
        return d

    by_sym = {s: g.reset_index(drop=True) for s, g in f.groupby("Symbol")}
    rows = []
    for r in b.itertuples():
        g = by_sym.get(r.Symbol)
        if g is None:
            continue
        vis = g[g.filed <= r.Date]          # only what was FILED before the signal
        if len(vis) < 2:
            continue
        w = PP.weigh(tests(vis.iloc[-1], vis.iloc[-2]), PURE)
        if w["pct"] is None or w["possible"] < 7:
            continue
        rows.append({"Symbol": r.Symbol, "Date": r.Date, "fwd_ret": r.fwd_ret,
                     "turnover": r.turnover, "F9": w["pct"]/100*9})
    d = pd.DataFrame(rows)
    if len(d) < 50:
        print(f"  only {len(d)} signals with fundamentals — too few"); return 1
    d["yr"] = d.Date.dt.year
    d["wret"] = d.groupby("yr").fwd_ret.transform(lambda s: s.clip(s.quantile(.01), s.quantile(.99)))
    d["tier"] = pd.qcut(d.turnover, 3, labels=["SMALL", "MID", "LARGE"])
    print(f"  signals WITH point-in-time fundamentals: {len(d):,} "
          f"({d.Symbol.nunique():,} symbols, {d.yr.nunique()} years)\n")

    # baseline: every stock-day in the same tier/year, not just breakouts
    base = con.execute(f"""
      SELECT Symbol, Date, turnover, coalesce(fwd,lastpx)/Close-1 fwd_ret
      FROM sig WHERE coalesce(ca_ahead,0)=0 AND turnover>0 AND fwd IS NOT NULL
        AND Date <= (SELECT max(Date) FROM px) - INTERVAL '{HOLD+30} days'
        AND Date IN (SELECT DISTINCT Date FROM brk)""").df()
    base["Date"] = pd.to_datetime(base.Date); base["yr"] = base.Date.dt.year
    base["wret"] = base.groupby("yr").fwd_ret.transform(lambda s: s.clip(s.quantile(.01), s.quantile(.99)))
    base["tier"] = pd.qcut(base.turnover, 3, labels=["SMALL", "MID", "LARGE"])

    print("  === DAILY-SCANNED BREAKOUTS BY TIER (winsorized median, vs same-tier baseline) ===")
    print(f"  {'tier':7s} {'base med':>9s} {'darvas':>9s} {'n':>6s} "
          f"{'darvas×F7':>11s} {'n':>5s} {'darvas×F<=3':>12s} {'n':>5s}")
    for t in ("SMALL", "MID", "LARGE"):
        bm = base[base.tier == t].wret.median()*100
        g = d[d.tier == t]
        dv = g.wret.median()*100
        hi = g[g.F9 >= 7]; lo = g[g.F9 <= 3]
        hv = hi.wret.median()*100 if len(hi) > 15 else float("nan")
        lv = lo.wret.median()*100 if len(lo) > 15 else float("nan")
        print(f"  {t:7s} {bm:>8.1f}% {dv-bm:>+8.1f}% {len(g):>6,} "
              f"{hv-bm:>+10.1f}% {len(hi):>5} {lv-bm:>+11.1f}% {len(lo):>5}")

    print("\n  === per-year, darvas×F7 minus darvas-alone (does the overlay ADD?) ===")
    print(f"  {'year':6s} " + " ".join(f"{t:>10s}" for t in ("SMALL", "MID", "LARGE")))
    for y in sorted(d.yr.unique()):
        cells = []
        for t in ("SMALL", "MID", "LARGE"):
            g = d[(d.yr == y) & (d.tier == t)]
            hi = g[g.F9 >= 7]
            cells.append(f"{(hi.wret.median()-g.wret.median())*100:>+9.1f}%"
                         if len(hi) >= 5 and len(g) >= 10 else f"{'--':>10s}")
        print(f"  {y:<6} " + " ".join(cells))
    print("\n  Signals CLUSTER in rallies, so effective n << row count. Read the per-year")
    print("  table. PRIOR (no liquidity cut): darvas×F7 = +9.9pp median, 62% win.")
    d.to_csv("reports/daily_breakout_combo_us.csv", index=False)
    print("  -> reports/daily_breakout_combo_us.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
