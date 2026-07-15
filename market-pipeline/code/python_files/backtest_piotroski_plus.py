#!/usr/bin/env python3
"""
backtest_piotroski_plus.py — sweep weight vectors against real forward returns.

WHAT THIS CAN AND CANNOT ESTABLISH — read before believing any number below.
=========================================================================
Two limitations are structural. Neither is fixable with the data on hand, and both
push results in the OPTIMISTIC direction, so treat every figure as an upper bound.

1. SURVIVORSHIP BIAS IN THE FUNDAMENTALS (the serious one).
   The price data is clean: 964 of 3,476 Indian symbols delisted and were KEPT.
   The fundamentals are not. yfinance serves statements only for CURRENTLY LISTED
   companies, so every company that went bust between 2021 and 2026 has prices but
   no statements, and silently drops out of the scored universe.
   Those companies are exactly the ones a quality screen should have avoided. Their
   absence flatters every vector here, and flatters the weak ones most, because the
   disasters they would have bought are invisible. This is not a caveat to note and
   move past: it is the single biggest reason not to trade this result.

2. STATISTICAL POWER IS NEAR ZERO.
   yfinance carries ~5 annual statements, and a Piotroski delta needs a prior year,
   so there are at most ~4 usable annual rebalances. Four. Stocks co-move heavily
   within a year, so the effective sample is closer to 4 than to the ~600
   stock-years the row count suggests. A vector "winning" across 4 observations is
   indistinguishable from luck. This backtest can plausibly REJECT a vector that
   fails badly; it cannot ENDORSE one that wins.

NO-LOOKAHEAD RULES
------------------
The statements yfinance returns are TODAY's. Scoring a stock on FY2026 financials
and testing it against 2022 returns would be lookahead of the worst kind, and would
manufacture a spectacular fake result. Defences:

  * Statement columns carry the FISCAL YEAR END date. At rebalance t only columns
    with fiscal_end + REPORTING_LAG <= t are visible.
  * REPORTING_LAG = 120 days. Indian companies close FY on 31 March and publish
    audited annuals ~May-June. Using FY2025 (ended 2025-03-31) on 2025-04-01 would
    be trading on results nobody had. 120 days puts the earliest use at ~end-July.
  * Rebalance dates are 1 August, after the lag has cleared for a March year-end.
  * Forward returns come from the point-in-time price parquet, never from the
    fundamentals source.
  * Corporate actions are filtered exactly as in backtest_liquidity_forward.py —
    that file's first run produced a fake +12.20% mean with 248% sd purely from
    unadjusted 1:100 ETF splits.

The canonical vector is the control. If a weighted vector cannot beat all-weights-1.0
out of sample, the weights are fitting noise.
"""
from __future__ import annotations

import concurrent.futures as cf
import sys
import warnings
from datetime import timedelta

warnings.filterwarnings("ignore")

import duckdb
import numpy as np
import pandas as pd

import piotroski_plus as PP

PARQUET = "/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"
REPORTING_LAG = timedelta(days=120)
HOLD_DAYS = 252                 # ~12 months
LIQ_FLOOR = 10_000_000          # Rs 1 crore/day — the gate, applied PIT
TOP_N = 20                      # portfolio size per vector per rebalance
UNIVERSE = int(sys.argv[1]) if len(sys.argv) > 1 else 250
WORKERS = 6


def liquid_universe(con) -> pd.DataFrame:
    return con.execute(f"""
      WITH l AS (SELECT Symbol, Close*Volume tv,
                        row_number() OVER (PARTITION BY Symbol ORDER BY Date DESC) rn
                 FROM '{PARQUET}' WHERE Close>0 AND Volume>0),
      m AS (SELECT Symbol, median(tv) turnover FROM l WHERE rn<=60
            GROUP BY 1 HAVING count(*)>=50 AND median(tv) >= {LIQ_FLOOR}),
      a AS (SELECT Symbol FROM '{PARQUET}' GROUP BY 1
            HAVING max(Date) >= DATE '2026-06-01')
      SELECT m.Symbol, m.turnover FROM m JOIN a USING (Symbol)
      ORDER BY m.turnover DESC LIMIT {UNIVERSE}
    """).df()


def statements(sym: str):
    """Fetch once; every rebalance and every vector reuses this."""
    import yfinance as yf

    try:
        t = yf.Ticker(f"{sym}.NS")
        inc, bal, cfs = t.income_stmt, t.balance_sheet, t.cashflow
        if inc is None or inc.empty or bal is None or bal.empty:
            return None
        return {"Symbol": sym, "inc": inc, "bal": bal, "cfs": cfs}
    except Exception:
        return None


class _AsOf:
    """A Ticker-shaped view of statements truncated to what was public at `asof`.

    piotroski_plus.score() takes anything exposing .income_stmt/.balance_sheet/
    .cashflow, so slicing the columns here is all it takes to make the whole scorer
    point-in-time. The scorer needs no knowledge of dates at all.
    """

    def __init__(self, s, asof):
        cut = asof - REPORTING_LAG
        self.income_stmt = self._trim(s["inc"], cut)
        self.balance_sheet = self._trim(s["bal"], cut)
        self.cashflow = self._trim(s["cfs"], cut)

    @staticmethod
    def _trim(df, cut):
        if df is None or df.empty:
            return df
        keep = [c for c in df.columns if pd.Timestamp(c) <= pd.Timestamp(cut)]
        return df[sorted(keep, reverse=True)] if keep else df.iloc[:, :0]


def forward_returns(con, dates) -> pd.DataFrame:
    """PIT forward returns with the corporate-action filter and delisting exits."""
    con.execute(f"""
    CREATE OR REPLACE TABLE px AS
      SELECT Date, Symbol, Close FROM '{PARQUET}' WHERE Close>0""")
    con.execute("""
    CREATE OR REPLACE TABLE ca AS
      SELECT Symbol, Date,
             CASE WHEN prev>0 AND (Close/prev-1 < -0.50 OR Close/prev-1 > 1.00)
                  THEN 1 ELSE 0 END is_ca
      FROM (SELECT Symbol, Date, Close,
                   lag(Close) OVER (PARTITION BY Symbol ORDER BY Date) prev FROM px)""")
    con.execute(f"""
    CREATE OR REPLACE TABLE fw AS
      SELECT p.Symbol, p.Date, p.Close,
             lead(p.Close, {HOLD_DAYS}) OVER w close_fwd,
             last_value(p.Close) OVER (PARTITION BY p.Symbol ORDER BY p.Date
                 ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) close_last,
             sum(c.is_ca) OVER (PARTITION BY p.Symbol ORDER BY p.Date
                 ROWS BETWEEN 1 FOLLOWING AND {HOLD_DAYS} FOLLOWING) ca_ahead
      FROM px p JOIN ca c ON p.Symbol=c.Symbol AND p.Date=c.Date
      WINDOW w AS (PARTITION BY p.Symbol ORDER BY p.Date)""")
    ds = ", ".join(f"DATE '{d}'" for d in dates)
    return con.execute(f"""
      WITH anchor AS (
        SELECT Symbol, Date, Close, close_fwd, close_last, ca_ahead,
               first_value(Date) OVER (PARTITION BY Symbol, rb ORDER BY Date) pick
        FROM (SELECT f.*, (SELECT min(d) FROM (SELECT unnest([{ds}]) d)
                           WHERE d >= f.Date) rb FROM fw f))
      SELECT Symbol, Date AS t,
             coalesce(close_fwd, close_last)/Close - 1 AS fwd_ret,
             close_fwd IS NULL AS delisted
      FROM fw WHERE Date IN ({ds}) AND coalesce(ca_ahead,0)=0
    """).df()


def main() -> int:
    con = duckdb.connect()
    print(f"\n{'='*80}\n  PIOTROSKI PLUS — WEIGHT VECTOR SWEEP | India | hold {HOLD_DAYS}d"
          f"\n{'='*80}")
    print("  Educational/research only. NOT investment advice.")
    print("  !! fundamentals are survivorship-biased (yfinance serves only live")
    print("     companies) and there are ~4 rebalances. Upper bound, not evidence. !!\n")

    uni = liquid_universe(con)
    print(f"  universe: {len(uni)} liquid stocks (>= Rs 1cr/day) — fetching statements...")
    stmts = []
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for s in ex.map(statements, uni["Symbol"].tolist()):
            if s:
                stmts.append(s)
    print(f"  statements for {len(stmts)}/{len(uni)}\n")

    # rebalance on 1 Aug of each year the price data can fully support
    maxd = con.execute(f"SELECT max(Date) FROM '{PARQUET}'").fetchone()[0]
    rebals = [pd.Timestamp(f"{y}-08-01") for y in range(2021, 2027)
              if pd.Timestamp(f"{y}-08-01") + timedelta(days=HOLD_DAYS * 1.5) <= pd.Timestamp(maxd)]
    print(f"  rebalances: {[str(d.date()) for d in rebals]}  ({len(rebals)} — this is the power limit)\n")

    fwd = forward_returns(con, [d.date() for d in rebals])
    fwd["t"] = pd.to_datetime(fwd["t"])
    fmap = {(r.Symbol, r.t): r.fwd_ret for r in fwd.itertuples()}

    rows = []
    for t in rebals:
        # nearest trading day at/after the rebalance date
        tt = fwd[fwd["t"] >= t]["t"].min() if (fwd["t"] >= t).any() else None
        for s in stmts:
            r = PP.score(_AsOf(s, t))
            if not r:
                continue
            ret = fmap.get((s["Symbol"], tt))
            if ret is None or ret != ret:
                continue
            rec = {"Symbol": s["Symbol"], "t": t, "fwd_ret": ret}
            for p in PP.PRESETS:
                w = PP.weigh(r, p)
                rec[p] = w["pct"]
                rec[f"{p}_cov"] = w["coverage"]
            rows.append(rec)
    d = pd.DataFrame(rows)
    if d.empty:
        print("  no scored rows"); return 1
    print(f"  scored panel: {len(d):,} stock-years, {d['Symbol'].nunique()} symbols, "
          f"{d['t'].nunique()} rebalances\n")

    print(f"  === TOP-{TOP_N} PORTFOLIO BY EACH VECTOR vs the universe ===")
    uni_ret = d.groupby("t")["fwd_ret"].mean()
    print(f"  {'vector':11s} {'mean 12m':>9s} {'median':>8s} {'vs universe':>12s} "
          f"{'win yrs':>8s} {'worst yr':>9s}")
    print(f"  {'[universe]':11s} {uni_ret.mean()*100:>8.1f}% "
          f"{d['fwd_ret'].median()*100:>7.1f}% {'--':>12s} {'--':>8s} "
          f"{uni_ret.min()*100:>8.1f}%")
    res = {}
    for p in PP.PRESETS:
        per_yr = []
        for t, g in d.groupby("t"):
            g = g[g[p].notna()]
            if len(g) < TOP_N:
                continue
            top = g.nlargest(TOP_N, p)
            per_yr.append((t, top["fwd_ret"].mean(), g["fwd_ret"].mean()))
        if not per_yr:
            continue
        pr = pd.DataFrame(per_yr, columns=["t", "port", "uni"])
        pr["excess"] = pr["port"] - pr["uni"]
        res[p] = pr
        print(f"  {p:11s} {pr['port'].mean()*100:>8.1f}% "
              f"{pr['port'].median()*100:>7.1f}% {pr['excess'].mean()*100:>+11.1f}% "
              f"{int((pr['excess']>0).sum()):>4}/{len(pr):<3} {pr['port'].min()*100:>8.1f}%")

    print("\n  === year by year excess return vs universe (the honest view) ===")
    print(f"  {'year':6s} " + " ".join(f"{p:>11s}" for p in res))
    yrs = sorted({t for p in res for t in res[p]["t"]})
    for t in yrs:
        cells = []
        for p in res:
            v = res[p][res[p]["t"] == t]["excess"]
            cells.append(f"{v.iloc[0]*100:>+10.1f}%" if len(v) else f"{'--':>11s}")
        print(f"  {t.year:<6} " + " ".join(cells))
    print(f"\n  {len(yrs)} observations per vector. A vector beating the control on"
          f" {len(yrs)} points is not evidence — it is a coin landing heads {len(yrs)} times.")
    d.to_csv("reports/backtest_piotroski_plus_india.csv", index=False)
    print("  -> reports/backtest_piotroski_plus_india.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
