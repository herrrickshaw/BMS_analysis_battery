#!/usr/bin/env python3
"""
sweep_growth_risk_us.py — backtest the "step 2" factor stack (P/FCF, FCF/EBITDA,
Altman Z-Score, Reinvestment Rate x ROCE, 12-1 Month Momentum) on the same
point-in-time US SEC EDGAR panel and rebalance schedule as
sweep_piotroski_plus_us.py / sweep_valuation_quality_us.py, so results are
directly comparable rather than a new, incomparable sample.

WHAT THIS TESTS, deliberately separated
-----------------------------------------
  1. Each factor ALONE — does it beat the universe on its own?
  2. Altman Z-Score as a GATE, not a rank — the framework's own suggested use
     ("High F-Score with a Safe Altman Z-Score eliminates bankruptcy risk") is
     a screen, not a ranking factor: nobody buys the SAFEST company, they
     avoid the DISTRESSED ones. Tested as: does excluding DISTRESS-zone names
     from the existing Piotroski-Plus canonical top-20 change the outcome?
  3. Momentum needs its own price lookback (252 trading days back for the
     12-month leg), so REBAL is trimmed to dates with enough trailing history
     in the panel — a shorter effective sample than the other sweeps, stated
     explicitly rather than silently producing a name-only-comparable row.

DATA: same FUND parquet as the other sweeps, now also carrying capex, d_and_a,
retained_earnings, total_liabilities (added to sec_history_collector.py's
CONCEPTS — a second backfill re-collection, same self-healing mechanism as the
cash/short_term_debt addition). Coverage on these new fields is expected to be
partial (XBRL tag adoption varies by filer); reported explicitly, not assumed.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import duckdb
import numpy as np
import pandas as pd

import factor_growth_risk as FG
import piotroski_plus as PP

FUND = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet"
PX = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"
HOLD = 252
TOP_N = 20
REBAL = [pd.Timestamp(f"{y}-06-01") for y in range(2017, 2026)]


def _roce_tests(cur, prv, hist):
    """Duplicated from sweep_valuation_quality_us.py deliberately, not
    imported — matches this project's established pattern of keeping each
    standalone analysis script self-contained rather than cross-coupled."""
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
               long_term_debt, short_term_debt, cash, shares, revenue, gross_profit, equity,
               capex, d_and_a, retained_earnings, total_liabilities
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
    print(f"\n{'='*84}\n  GROWTH & RISK FACTORS — P/FCF, FCF/EBITDA, Altman Z, Reinvestment×ROCE, "
          f"Momentum\n{'='*84}")
    print("  Educational/research only. NOT investment advice.")
    print(f"  fundamentals: {len(f):,} ticker-years | {f.ticker.nunique():,} tickers")
    for c in ("capex", "d_and_a", "retained_earnings", "total_liabilities"):
        print(f"  {c} tag coverage: {f[c].notna().mean()*100:.0f}%")
    print()

    # ── price panel: forward returns (as before) PLUS trailing lookback prices
    #    for 12-1 momentum, both computed off the same corporate-action-filtered
    #    fw table so a split doesn't fake a momentum spike the way it once faked
    #    an illiquid-premium return (see reference_deep_10y_market_data in memory).
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
             lag(p.Close,21)  OVER (PARTITION BY p.Symbol ORDER BY p.Date) px_21,
             lag(p.Close,252) OVER (PARTITION BY p.Symbol ORDER BY p.Date) px_252,
             sum(c.is_ca) OVER (PARTITION BY p.Symbol ORDER BY p.Date
               ROWS BETWEEN 1 FOLLOWING AND {HOLD} FOLLOWING) ca_ahead
      FROM px p JOIN ca c ON p.Symbol=c.Symbol AND p.Date=c.Date;
    """)
    ret = con.execute(f"""
      WITH rb AS (SELECT unnest([{ds}]) t),
      anchor AS (SELECT rb.t, min(fw.Date) d FROM rb JOIN fw ON fw.Date >= rb.t GROUP BY rb.t)
      SELECT a.t, f.Symbol, f.Close entry_px,
             coalesce(f.fwd, f.last_px)/f.Close - 1 fwd_ret,
             CASE WHEN f.px_21 IS NOT NULL AND f.px_252 IS NOT NULL AND f.px_252 > 0
                  THEN f.px_21/f.px_252 - 1 END mom_12_1
      FROM anchor a JOIN fw f ON f.Date = a.d
      WHERE coalesce(f.ca_ahead,0)=0 AND f.Close>0
    """).df()
    ret["t"] = pd.to_datetime(ret["t"])
    pmap = {(r.Symbol, r.t): (r.entry_px, r.fwd_ret, r.mom_12_1) for r in ret.itertuples()}
    n_mom = ret.mom_12_1.notna().sum()
    print(f"  forward returns: {len(ret):,} rows over {ret.t.nunique()} rebalances")
    print(f"  momentum computable: {n_mom:,}/{len(ret):,} ({n_mom/len(ret)*100:.0f}%) "
          f"— early rebalances lack 252d of trailing history in the panel\n")

    rows = []
    by_t = {tk: g.reset_index(drop=True) for tk, g in f.groupby("ticker")}
    for t in REBAL:
        for tk, g in by_t.items():
            vis = g[g.filed <= t]
            if len(vis) < 2:
                continue
            cur, prv = vis.iloc[-1], vis.iloc[-2]
            px_ret_mom = pmap.get((tk, t))
            if px_ret_mom is None:
                continue
            entry_px, fr, mom = px_ret_mom
            if fr is None or fr != fr:
                continue

            market_cap = cur.shares * entry_px
            fcf = FG.free_cash_flow(cur.cfo, cur.capex)
            pfcf = FG.price_to_fcf(market_cap, fcf)
            fcf_ebitda = FG.fcf_to_ebitda(fcf, cur.ebit, cur.d_and_a)
            z = FG.altman_z_score(cur.current_assets, cur.current_liabilities, cur.total_assets,
                                   cur.retained_earnings, cur.ebit, market_cap,
                                   cur.total_liabilities, cur.revenue)
            zone = FG.altman_zone(z)
            reinv = FG.reinvestment_rate(cur.capex, cur.d_and_a, cur.ebit)
            growth = FG.intrinsic_growth_rate(reinv, cur.roce)

            r = _roce_tests(cur, prv, vis["roce"].dropna().tolist())
            rows.append({
                "Symbol": tk, "t": t, "fwd_ret": fr,
                "price_to_fcf": pfcf, "fcf_to_ebitda": fcf_ebitda,
                "altman_z": z, "altman_zone": zone,
                "intrinsic_growth": growth, "mom_12_1": mom,
                "canonical": PP.weigh(r, "canonical")["pct"],
            })
    d = pd.DataFrame(rows)
    if d.empty:
        print("  no scored rows"); return 1
    print(f"  scored panel: {len(d):,} stock-years | {d.Symbol.nunique():,} symbols | "
          f"{d.t.nunique()} rebalances")
    for c in ("price_to_fcf", "fcf_to_ebitda", "altman_z", "intrinsic_growth", "mom_12_1"):
        print(f"  {c:18s} computed: {d[c].notna().sum():,}/{len(d):,} "
              f"({d[c].notna().mean()*100:.0f}%)")
    print()

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
            print(f"  {label:26s} insufficient coverage"); return None
        x = pd.DataFrame(pr, columns=["t", "mean", "median", "uni"])
        x["ex_mean"] = x["mean"] - x.uni
        print(f"  {label:26s} mean {x['mean'].mean()*100:>6.1f}%  median {x['median'].mean()*100:>6.1f}%  "
              f"excess(mean) {x.ex_mean.mean()*100:>+6.1f}%  beat-univ {int((x.ex_mean>0).sum())}/{len(x)}")
        return x

    print("  === STANDALONE FACTORS, top-20 equal-weight, 12m hold ===")
    topN_by("price_to_fcf", ascending=True, label="P/FCF (cheapest)")
    topN_by("fcf_to_ebitda", ascending=False, label="FCF/EBITDA (best conversion)")
    topN_by("altman_z", ascending=False, label="Altman Z (safest)")
    topN_by("intrinsic_growth", ascending=False, label="Intrinsic Growth (Reinv×ROCE)")
    topN_by("mom_12_1", ascending=False, label="12-1 Momentum (strongest)")

    # ── Altman Z as a GATE on the existing canonical top tier, not a rank ──────
    print("\n  === ALTMAN Z AS A GATE on Piotroski-Plus canonical top-20 ===")
    print("  (does excluding DISTRESS-zone names from an already-strong pool help?)")
    topN_by("canonical", ascending=False, label="  canonical top-20, ALL zones")
    not_distress = d[d.altman_zone != "DISTRESS"]
    topN_by("canonical", ascending=False, label="  canonical top-20, ex-DISTRESS", frame=not_distress)

    print("\n  === Altman zone distribution ===")
    vc = d.altman_zone.value_counts()
    for zone in ("SAFE", "GREY", "DISTRESS"):
        n = vc.get(zone, 0)
        print(f"    {zone:9s} {n:>6,}  ({n/len(d)*100:.1f}%)")

    d.to_csv("reports/sweep_growth_risk_us.csv", index=False)
    print("\n  -> reports/sweep_growth_risk_us.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
