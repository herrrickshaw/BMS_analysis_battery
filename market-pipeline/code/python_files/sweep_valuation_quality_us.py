#!/usr/bin/env python3
"""
sweep_valuation_quality_us.py — backtest Earnings Yield + Sloan Ratio on the same
point-in-time US SEC EDGAR panel and rebalance schedule as sweep_piotroski_plus_us.py,
so results are directly comparable to the existing Piotroski Plus numbers rather than
a new, incomparable sample.

WHAT THIS TESTS, deliberately in this order
--------------------------------------------
  1. Earnings Yield ALONE       — does "cheap on EBIT/EV" beat the universe?
  2. Sloan Ratio ALONE          — does "cash-backed income" beat the universe?
  3. Earnings Yield WITHIN the existing Piotroski-Plus "canonical" top tier — the
     framework's actual claim ("High ROCE + High Earnings Yield ensures you buy
     quality cheaply") is a CONJUNCTION, not two independent screens. Testing (1)
     and (3) separately is the only way to tell whether combining adds anything,
     the same discipline piotroski_plus.py already applies to F-score + ROCE.

DATA: same FUND parquet as sweep_piotroski_plus_us.py, now carrying `cash` and
`short_term_debt` (added to sec_history_collector.py's CONCEPTS — a backfill
re-collection was required since collect_ticker() re-derives every concept from a
fresh fetch and cannot patch a single new column into already-collected tickers).
market_cap = shares (as of the filing) x Close (at the rebalance date) — the same
approximation Piotroski test 7 already implicitly relies on (share count as of the
last filing), not a look-ahead: shares are known at `filed`, price is observed at
the rebalance date itself.
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
HOLD = 252
TOP_N = 20
REBAL = [pd.Timestamp(f"{y}-06-01") for y in range(2017, 2026)]


def _roce_tests(cur, prv, hist):
    """Same 12-test dict sweep_piotroski_plus_us.py builds, duplicated (not
    imported) because that module's `tests()` is defined inside main() and is not
    meant as a library surface. Kept in lockstep by construction: both read the
    same FUND columns and the same PP.ROCE_LEVEL_HURDLE / ROCE_CV_HURDLE constants."""
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
    d["10_roce_level"] = bool(cur.roce > PP.ROCE_LEVEL_HURDLE)
    if len(hist) >= 3 and abs(np.mean(hist)) > 0.01:
        d["11_roce_stable"] = bool(np.std(hist) / abs(np.mean(hist)) < PP.ROCE_CV_HURDLE)
        d["12_roce_not_deteriorating"] = bool(cur.roce >= np.mean(hist))
    else:
        d["11_roce_stable"] = d["12_roce_not_deteriorating"] = None
    return d


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
          AND date_diff('day', CAST(fy_end AS DATE), CAST(filed AS DATE)) BETWEEN 0 AND 400
          AND CAST(fy_end AS DATE) BETWEEN DATE '2014-01-01' AND DATE '2026-07-15'
        ORDER BY ticker, fy_end
    """).df()
    f["ce"] = f.total_assets - f.current_liabilities
    f = f[f.ce > 0].copy()
    f["roce"] = f.ebit / f.ce
    cash_cov = f.cash.notna().mean() * 100
    debt_cov = f.short_term_debt.notna().mean() * 100
    print(f"\n{'='*80}\n  VALUATION + QUALITY FACTORS — Earnings Yield & Sloan Ratio | US SEC EDGAR"
          f"\n{'='*80}")
    print("  Educational/research only. NOT investment advice.")
    print(f"  fundamentals: {len(f):,} ticker-years | {f.ticker.nunique():,} tickers")
    print(f"  cash tag coverage: {cash_cov:.0f}%  |  short_term_debt tag coverage: {debt_cov:.0f}%"
          f"  (absent treated as 0, see factor_valuation_quality.py)\n")

    # ── price panel: same corporate-action-filtered forward-return machinery as
    #    sweep_piotroski_plus_us.py, PLUS the raw Close at each rebalance for EV ──
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
      SELECT a.t, f.Symbol, f.Close entry_px, coalesce(f.fwd, f.last_px)/f.Close - 1 fwd_ret
      FROM anchor a JOIN fw f ON f.Date = a.d
      WHERE coalesce(f.ca_ahead,0)=0 AND f.Close>0
    """).df()
    ret["t"] = pd.to_datetime(ret["t"])
    pmap = {(r.Symbol, r.t): (r.entry_px, r.fwd_ret) for r in ret.itertuples()}
    print(f"  forward returns: {len(ret):,} rows over {ret.t.nunique()} rebalances\n")

    rows = []
    by_t = {tk: g.reset_index(drop=True) for tk, g in f.groupby("ticker")}
    for t in REBAL:
        for tk, g in by_t.items():
            vis = g[g.filed <= t]
            if len(vis) < 2:
                continue
            cur, prv = vis.iloc[-1], vis.iloc[-2]
            px_ret = pmap.get((tk, t))
            if px_ret is None:
                continue
            entry_px, fr = px_ret
            if fr is None or fr != fr:
                continue

            market_cap = cur.shares * entry_px
            ev = FV.enterprise_value(market_cap, cur.long_term_debt, cur.short_term_debt, cur.cash)
            ey = FV.earnings_yield(cur.ebit, ev)
            sloan = FV.sloan_ratio(cur.net_income, cur.cfo, cur.total_assets)

            r = _roce_tests(cur, prv, vis["roce"].dropna().tolist())
            rec = {
                "Symbol": tk, "t": t, "fwd_ret": fr,
                "earnings_yield": ey, "sloan_ratio": sloan,
                "canonical": PP.weigh(r, "canonical")["pct"],
            }
            rows.append(rec)
    d = pd.DataFrame(rows)
    if d.empty:
        print("  no scored rows"); return 1
    print(f"  scored panel: {len(d):,} stock-years | {d.Symbol.nunique():,} symbols | "
          f"{d.t.nunique()} rebalances")
    print(f"  earnings_yield computed: {d.earnings_yield.notna().sum():,}/{len(d):,}  "
          f"({d.earnings_yield.notna().mean()*100:.0f}%)")
    print(f"  sloan_ratio computed:    {d.sloan_ratio.notna().sum():,}/{len(d):,}  "
          f"({d.sloan_ratio.notna().mean()*100:.0f}%)\n")

    uni = d.groupby("t")["fwd_ret"].mean()
    print(f"  {'universe':22s} mean {uni.mean()*100:>6.1f}%  median {uni.median()*100:>6.1f}%\n")

    def topN_by(col, ascending, label, n=TOP_N, frame=None):
        base = d if frame is None else frame
        pr = []
        for t, g in base.groupby("t"):
            g2 = g[g[col].notna()]
            if len(g2) < n:
                continue
            top = g2.nsmallest(n, col) if ascending else g2.nlargest(n, col)
            pr.append((t, top.fwd_ret.mean(), top.fwd_ret.median(), g2.fwd_ret.mean()))
        if not pr:
            print(f"  {label:22s} insufficient coverage"); return None
        x = pd.DataFrame(pr, columns=["t", "mean", "median", "uni"])
        x["ex_mean"] = x["mean"] - x.uni
        print(f"  {label:22s} mean {x['mean'].mean()*100:>6.1f}%  median {x['median'].mean()*100:>6.1f}%  "
              f"excess(mean) {x.ex_mean.mean()*100:>+6.1f}%  beat-univ {int((x.ex_mean>0).sum())}/{len(x)}")
        return x

    print("  === STANDALONE FACTORS, top-20 equal-weight, 12m hold ===")
    ey_x = topN_by("earnings_yield", ascending=False, label="Earnings Yield (top)")
    sl_x = topN_by("sloan_ratio", ascending=True, label="Sloan Ratio (lowest = best)")

    # ── the actual claim under test: EY WITHIN the existing quality/health pass ──
    print("\n  === EARNINGS YIELD WITHIN Piotroski-Plus canonical top tier ===")
    print("  (does adding valuation to an already-quality-filtered pool help?)")
    for lo, lab in [(0, "ALL (no quality filter)"), (70, "canonical >= 70 (quality-passed)")]:
        sub = d[d.canonical >= lo] if lo else d
        topN_by("earnings_yield", ascending=False, label=f"  EY top-20, {lab}", frame=sub)

    # ── liquidity context — every prior finding in this project was tier-dependent
    liq = con.execute(f"""
        WITH l AS (SELECT Symbol, Close*Volume tv,
                          row_number() OVER (PARTITION BY Symbol ORDER BY Date DESC) rn
                   FROM '{PX}' WHERE Close>0 AND Volume>0)
        SELECT Symbol, median(tv) turnover FROM l WHERE rn<=60 GROUP BY 1""").df()
    dl = d.merge(liq, on="Symbol", how="left")
    dl = dl[dl.turnover.notna()].copy()
    if len(dl) > 200:
        dl["tier"] = pd.qcut(dl.turnover, 3, labels=["SMALL", "MID", "LARGE"])
        print("\n  === Earnings Yield edge BY LIQUIDITY TIER (median, top-10 vs tier) ===")
        print(f"    {'tier':7s} {'n':>6s} {'EY-top med':>11s} {'tier med':>9s} {'edge':>8s}")
        for t in ("SMALL", "MID", "LARGE"):
            s = dl[dl.tier == t]
            per = []
            for ts, g in s.groupby("t"):
                g2 = g[g.earnings_yield.notna()]
                if len(g2) < 20:
                    continue
                top = g2.nlargest(10, "earnings_yield")
                per.append((top.fwd_ret.median(), g2.fwd_ret.median()))
            if len(per) < 4:
                continue
            x = pd.DataFrame(per, columns=["pm", "um"])
            print(f"    {t:7s} {len(s):>6,} {x.pm.mean()*100:>10.1f}% {x.um.mean()*100:>8.1f}% "
                  f"{(x.pm-x.um).mean()*100:>+7.1f}%")

    d.to_csv("reports/sweep_valuation_quality_us.csv", index=False)
    print("\n  -> reports/sweep_valuation_quality_us.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
