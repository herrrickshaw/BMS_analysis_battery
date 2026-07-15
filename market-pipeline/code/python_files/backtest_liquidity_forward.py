#!/usr/bin/env python3
"""
backtest_liquidity_forward.py — does liquidity PREDICT forward returns?

WHY THIS EXISTS
---------------
The 2026-07-15 cross-sectional finding was that liquid Indian stocks sit above
their 200-DMA far more often than illiquid ones (Q1 49.1% vs Q5 31.8%,
chi2 p=3.7e-12). That is a SNAPSHOT and it cannot support the conclusion people
want to draw from it. In a year when large caps outperformed, "liquid stocks are
currently in uptrends" is close to tautological. It says nothing about what
happens NEXT, which is the only thing a screener needs to know.

This script answers the forward-looking version: rank by liquidity at time t
using ONLY data available at t, then measure what the stock actually did over the
following 63 trading days. Repeat quarterly over 5 years.

The literature makes two OPPOSING predictions, and the point is to see which one
this market obeys:
  * Amihud (2002)          — illiquid stocks earn HIGHER returns (illiquidity
                             premium), strongest among small firms. Predicts Q5 > Q1.
  * Fang, Noe & Tice (2009) — liquid firms are BETTER FIRMS (higher Q, higher ROA).
                             Predicts nothing about returns directly.
Both can be true: better companies need not be better investments.

DATA — and why this dataset specifically
----------------------------------------
cache_seed/ltm/IN.parquet: 4,423,382 rows, 3,476 symbols, 2016-01-01..2026-07-13.

It survives the test that kills most backtests: 964 of 3,476 symbols (27.7%) stop
trading before 2026-06 and were KEPT. Delisted names are present with their final
bars (GMRINFRA, HBLPOWER, IIFLSEC, REVATHIEQU). A universe built by fetching 10y
of history for today's listed stocks would show ~0 deaths and would silently drop
every company that failed — the single most common way a backtest invents alpha.

The local repo's price cache cannot do this job: it holds 1.1 years.

NO-LOOKAHEAD RULES
------------------
1. Liquidity, DMA50 and DMA200 at date t use bars <= t only. Enforced by SQL
   window frames that are explicitly `PRECEDING ... AND CURRENT ROW`.
2. Forward return uses bars > t only.
3. A stock that DELISTS inside the holding window exits at its last real close
   rather than being dropped. Dropping it would re-introduce exactly the
   survivorship bias the dataset was built to avoid — a stock that dies is
   usually a stock that fell.
4. Rebalance dates stop 63 trading days before the data ends, so every signal has
   a full, real holding period. No partial windows.

Rolling turnover uses MEAN, not median: DuckDB has no windowed median, and a
list_median over a 60-bar frame on 4.4M rows is too slow to be worth it. Mean
turnover is more sensitive to block deals, which is why the FLOOR here is a
quintile rank (relative) rather than an absolute rupee bar — ranks are far more
robust to a single outlier day than a threshold is.
"""
from __future__ import annotations

import sys

import duckdb

PARQUET = "/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"
HOLD_BARS = 63          # ~3 trading months
LIQ_WINDOW = 60         # bars of history for the liquidity measure
MIN_BARS_FOR_DMA = 200
REBAL_EVERY = "quarter"


def build(con: duckdb.DuckDBPyConnection, years: int = 5) -> None:
    con.execute(f"""
    CREATE OR REPLACE TABLE px AS
    SELECT Date, Symbol, Close, Volume, Close * Volume AS turnover
    FROM '{PARQUET}'
    WHERE Close > 0 AND Volume >= 0
      AND Date >= (SELECT max(Date) FROM '{PARQUET}') - INTERVAL '{years + 1} years'
    """)

    # Everything below is a PRECEDING-only frame => strictly point-in-time.
    con.execute(f"""
    CREATE OR REPLACE TABLE feat AS
    SELECT *,
      row_number() OVER w                                            AS bar_i,
      avg(turnover) OVER (PARTITION BY Symbol ORDER BY Date
                          ROWS BETWEEN {LIQ_WINDOW - 1} PRECEDING AND CURRENT ROW) AS liq,
      count(*)      OVER (PARTITION BY Symbol ORDER BY Date
                          ROWS BETWEEN {LIQ_WINDOW - 1} PRECEDING AND CURRENT ROW) AS liq_n,
      avg(Close)    OVER (PARTITION BY Symbol ORDER BY Date
                          ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)  AS dma50,
      avg(Close)    OVER (PARTITION BY Symbol ORDER BY Date
                          ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS dma200,
      count(*)      OVER (PARTITION BY Symbol ORDER BY Date
                          ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS dma_n,
      max(Close)    OVER (PARTITION BY Symbol ORDER BY Date
                          ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING)  AS box_top_prev
    FROM px
    WINDOW w AS (PARTITION BY Symbol ORDER BY Date)
    """)

    # ── corporate-action defence ──────────────────────────────────────────────
    # THIS DATASET STORES RAW Close, NOT ADJUSTED CLOSE. Splits, bonuses and
    # consolidations are therefore indistinguishable from returns, and they are
    # not rare:
    #   GOLDBEES  3359.60 -> 33.55  (-99%)   1:100 ETF unit split
    #   SETFGOLD  4259.95 -> 42.35  (-99%)   1:100
    #   KAUSHALYA    4.15 -> 935.55 (+22,443% over 63 bars)  reverse split
    # 1,047 single-day drops steeper than -45% exist, 249 of them landing on
    # clean 2/3/4/5/10 ratios. Left alone these dominate the mean: the first run
    # of this script reported a +12.20% mean forward return for the most illiquid
    # quintile with a 248% standard deviation. That was not an illiquidity
    # premium, it was arithmetic on unadjusted splits.
    #
    # Fix: flag any bar whose 1-day move falls outside [-50%, +100%]. Real equities
    # essentially never do this; corporate actions always do. Any holding window
    # containing a flagged bar is dropped.
    #
    # This is a HEURISTIC, and it cuts BOTH ways: it also removes genuine crashes
    # and genuine multi-baggers, which biases the surviving sample toward the
    # calm middle. The correct fix is Adjusted Close, which this dataset lacks.
    # Treat what follows as directional, not as a precise return estimate.
    con.execute("""
    CREATE OR REPLACE TABLE ca AS
    SELECT Symbol, Date,
           CASE WHEN prev > 0 AND (Close/prev - 1 < -0.50 OR Close/prev - 1 > 1.00)
                THEN 1 ELSE 0 END AS is_ca
    FROM (SELECT Symbol, Date, Close,
                 lag(Close) OVER (PARTITION BY Symbol ORDER BY Date) AS prev
          FROM px)
    """)

    # Forward return. lead() over the FOLLOWING bars only.
    # last_close is the stock's final bar ever: the delisting exit price.
    # ca_ahead counts flagged bars inside the holding window (t, t+HOLD_BARS].
    con.execute(f"""
    CREATE OR REPLACE TABLE fwd AS
    SELECT f.*,
      lead(f.Close, {HOLD_BARS}) OVER (PARTITION BY f.Symbol ORDER BY f.Date) AS close_fwd,
      last_value(f.Close) OVER (PARTITION BY f.Symbol ORDER BY f.Date
                              ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
                                                                        AS close_last,
      max(f.Date) OVER (PARTITION BY f.Symbol)                          AS sym_last_date,
      sum(c.is_ca) OVER (PARTITION BY f.Symbol ORDER BY f.Date
                         ROWS BETWEEN 1 FOLLOWING AND {HOLD_BARS} FOLLOWING) AS ca_ahead,
      sum(c.is_ca) OVER (PARTITION BY f.Symbol ORDER BY f.Date
                         ROWS BETWEEN {LIQ_WINDOW} PRECEDING AND CURRENT ROW) AS ca_behind
    FROM feat f
    JOIN ca c ON f.Symbol = c.Symbol AND f.Date = c.Date
    """)


def sample(con: duckdb.DuckDBPyConnection, years: int) -> None:
    """Quarterly rebalance dates, stopping HOLD_BARS before data end."""
    con.execute(f"""
    CREATE OR REPLACE TABLE rebal AS
    WITH cal AS (SELECT DISTINCT Date FROM px ORDER BY Date),
         numbered AS (SELECT Date, row_number() OVER (ORDER BY Date) AS i,
                             count(*) OVER () AS n FROM cal),
         -- last usable signal date: needs HOLD_BARS of market days after it
         cutoff AS (SELECT Date AS d FROM numbered WHERE i = n - {HOLD_BARS})
    SELECT DISTINCT first_value(Date) OVER (PARTITION BY date_trunc('{REBAL_EVERY}', Date)
                                            ORDER BY Date) AS t
    FROM cal
    WHERE Date <= (SELECT d FROM cutoff)
      AND Date >= (SELECT d FROM cutoff) - INTERVAL '{years} years'
    ORDER BY t
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE panel AS
    SELECT f.Symbol, f.Date AS t, f.liq, f.Close, f.dma50, f.dma200,
           f.Close > f.box_top_prev                       AS breakout,
           f.dma50 > f.dma200                             AS above200,
           -- delisting-aware exit: if no bar exists at t+63, the stock stopped
           -- trading. Exit at its final close instead of dropping the row.
           coalesce(f.close_fwd, f.close_last)            AS exit_px,
           f.close_fwd IS NULL                            AS delisted_in_window,
           coalesce(f.close_fwd, f.close_last) / f.Close - 1 AS fwd_ret
    FROM fwd f
    JOIN rebal r ON f.Date = r.t
    WHERE f.liq_n >= {LIQ_WINDOW}
      AND f.dma_n >= {MIN_BARS_FOR_DMA}
      AND f.liq > 0
      AND f.Close > 0
      AND coalesce(f.ca_ahead, 0) = 0      -- no corporate action in the holding window
      AND coalesce(f.ca_behind, 0) = 0     -- nor in the window the signal was built on
    """)


def report(con: duckdb.DuckDBPyConnection) -> None:
    n, syms, d0, d1, nreb = con.execute("""
        SELECT count(*), count(DISTINCT Symbol), min(t), max(t),
               (SELECT count(*) FROM rebal) FROM panel""").fetchone()
    deli = con.execute("SELECT sum(delisted_in_window) FROM panel").fetchone()[0]
    print(f"  panel: {n:,} stock-quarters | {syms:,} symbols | {nreb} rebalances "
          f"| {d0.date()}..{d1.date()}")
    print(f"  delisted inside a holding window: {deli:,} "
          f"({deli / n * 100:.2f}%) — exited at last close, not dropped\n")

    print("  === forward 63-day return by LIQUIDITY quintile (Q1 = most liquid) ===")
    print(con.execute("""
      WITH q AS (SELECT *, ntile(5) OVER (PARTITION BY t ORDER BY liq DESC) AS Q
                 FROM panel)
      SELECT 'Q' || Q AS quintile, count(*) AS n,
             round(median(liq)/1e7, 2)           AS med_turnover_cr,
             round(avg(fwd_ret)*100, 2)          AS mean_fwd_ret_pct,
             round(median(fwd_ret)*100, 2)       AS median_fwd_ret_pct,
             round(stddev(fwd_ret)*100, 1)       AS sd_pct,
             round(avg(fwd_ret)/stddev(fwd_ret), 3) AS ret_per_unit_risk
      FROM q GROUP BY Q ORDER BY Q
    """).df().to_string(index=False))

    print("\n  === does the SCAN work better in liquid names? fwd return by tier x signal ===")
    print(con.execute("""
      WITH q AS (SELECT *, ntile(5) OVER (PARTITION BY t ORDER BY liq DESC) AS Q
                 FROM panel)
      SELECT 'Q' || Q AS quintile,
             round(avg(CASE WHEN above200 THEN fwd_ret END)*100, 2)      AS above200_ret,
             round(avg(CASE WHEN NOT above200 THEN fwd_ret END)*100, 2)  AS below200_ret,
             round((avg(CASE WHEN above200 THEN fwd_ret END)
                  - avg(CASE WHEN NOT above200 THEN fwd_ret END))*100, 2) AS dma_edge,
             round(avg(CASE WHEN breakout THEN fwd_ret END)*100, 2)      AS breakout_ret,
             round((avg(CASE WHEN breakout THEN fwd_ret END)
                  - avg(fwd_ret))*100, 2)                                AS breakout_edge
      FROM q GROUP BY Q ORDER BY Q
    """).df().to_string(index=False))


def main() -> int:
    years = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    con = duckdb.connect()
    print(f"\n{'='*78}\n  LIQUIDITY -> FORWARD RETURN | India | {years}y | "
          f"hold {HOLD_BARS} bars\n{'='*78}")
    print("  Educational/research only. NOT investment advice.\n")
    build(con, years)
    sample(con, years)
    report(con)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
