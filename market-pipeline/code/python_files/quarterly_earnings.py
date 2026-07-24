#!/usr/bin/env python3
"""
quarterly_earnings.py — a listed-brokerage-style quarterly P&L for the
proprietary trading operation (à la Motilal Oswal Financial Services results).

The live paper-track ledger is only ~6 weeks, so a real multi-quarter earnings
history is reconstructed from the 10y backtest: each geography is a business
SEGMENT ("desk") running the regime-conditional strategy (zone_regime.json —
momentum/trend in bull, mean-revert in bear), liquidity-gated to HIGH+MEDIUM
turnover names. Each desk is capitalised with fixed AUM; every ~2 weeks it
deploys AUM equally into its BUY names, holds, and books the P&L. Quarters are
aggregated into a consolidated P&L with segment reporting, QoQ/YoY, and EPS.

Output: reports/quarterly_earnings.md + reports/quarterly_earnings.csv
        + reports/segment_revenue_by_quarter.csv

⚠️ Gross of slippage/market-impact; AUM, opex, tax, treasury and share count are
STATED assumptions (top of file). Descriptive accounting on a simulated book —
not a forecast, not investment advice.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import strategy_regime_survival as S

HERE = Path(__file__).resolve().parent
SEG = {"IN": "India Equities", "US": "US Equities", "EU": "Europe Equities",
       "JP": "Japan Equities", "KR": "Korea Equities"}

# ---- ASSUMPTIONS (tunable) -------------------------------------------------
AUM_PER_DESK = 1_000_000.0           # USD capital per geography desk (firm = $5M)
OPEX_ANNUAL_PCT = 0.020              # staff+data+infra, % of AUM p.a. (0.5%/qtr)
IDLE_FRACTION = 0.40                 # avg share of AUM in cash earning treasury
SHARES_OUT = 10_000_000             # for EPS (assumed)
TAX_ST = {"IN":0.200,"US":0.240,"EU":0.26375,"JP":0.20315,"KR":0.000}  # short-term
COST_BPS = {"IN":35,"US":10,"EU":25,"JP":15,"KR":30}                    # round-trip/hold
RF = {"IN":0.068,"US":0.043,"EU":0.025,"JP":0.010,"KR":0.032}          # treasury yield
# ---------------------------------------------------------------------------


def weekly_book_returns(mkt: str, bull_rule: str, bear_rule: str) -> pd.Series:
    """Per-week forward-2wk return of the regime-conditional, liquidity-gated
    long-only BUY book for one desk."""
    close, turn = S.load_panel(mkt)
    reg = S.regime_series(close, turn)
    sig = S.signals(close)
    fwd = (close.shift(-S.FWD // 5) / close - 1).clip(-0.40, 0.40)
    out = {}
    for t in close.index[close.index >= S.START]:
        g = reg.get(t)
        if g not in ("bull", "bear"):
            continue
        rule = bull_rule if g == "bull" else bear_rule
        liq = S.liquidity_mask(turn.loc[t], close.loc[t])
        f = fwd.loc[t].where(liq).dropna()
        if len(f) < S.MIN_NAMES:
            continue
        buys = f[sig[rule].loc[t].reindex(f.index) == 1]
        if len(buys) >= 5:
            out[t] = float(buys.mean())
    return pd.Series(out).sort_index()


def desk_quarterly(mkt: str, br: str, er: str) -> pd.DataFrame:
    """Quarterly P&L for one desk from bi-weekly (non-overlapping) holds."""
    wk = weekly_book_returns(mkt, br, er)
    if wk.empty:
        return pd.DataFrame()
    holds = wk.iloc[::2]                        # non-overlapping 2-week holds
    q = holds.groupby(holds.index.to_period("Q"))
    rows = []
    tax_r, cbps, rf = TAX_ST[mkt], COST_BPS[mkt], RF[mkt]
    for period, g in q:
        n = len(g)
        gross = AUM_PER_DESK * g.sum()                       # trading revenue
        treasury = AUM_PER_DESK * IDLE_FRACTION * rf * 0.25  # float income
        txn = AUM_PER_DESK * n * cbps / 1e4                  # fees & commission
        opex = AUM_PER_DESK * OPEX_ANNUAL_PCT / 4            # operating expense
        pbt = gross + treasury - txn - opex
        tax = max(0.0, pbt) * tax_r
        rows.append({"quarter": str(period), "segment": SEG[mkt], "market": mkt,
                     "holds": n, "trading_revenue": gross, "other_income": treasury,
                     "total_income": gross + treasury, "fees_commission": txn,
                     "operating_expense": opex, "total_expense": txn + opex,
                     "pbt": pbt, "tax": tax, "pat": pbt - tax})
    return pd.DataFrame(rows)


def main() -> int:
    zr = json.loads((HERE / "cache_seed" / "zone_regime.json").read_text())
    frames = []
    for mkt in S.MARKETS:
        z = zr.get(mkt, {})
        br, er = z.get("bull_rule", "trend"), z.get("bear_rule", "revert")
        d = desk_quarterly(mkt, br, er)
        if not d.empty:
            frames.append(d)
        print(f"  {mkt}: {SEG[mkt]:<16} bull={br} bear={er} -> {len(d)} quarters")
    seg = pd.concat(frames, ignore_index=True)
    seg.to_csv(HERE / "reports" / "segment_revenue_by_quarter.csv", index=False)

    # ---- consolidated firm P&L per quarter ----------------------------------
    num = ["holds","trading_revenue","other_income","total_income","fees_commission",
           "operating_expense","total_expense","pbt","tax","pat"]
    con = seg.groupby("quarter")[num].sum().sort_index()
    # margin only meaningful on positive income; a negative/near-zero denominator
    # produces spurious %s (a real firm reports "n/m" then)
    con["pat_margin_%"] = np.where(con["total_income"] > 0.05e6,
                                   (con["pat"] / con["total_income"] * 100).round(1), np.nan)
    con["eps"] = (con["pat"] / SHARES_OUT).round(3)
    con["qoq_pat_%"] = (con["pat"].pct_change() * 100).round(1)
    con["yoy_pat_%"] = (con["pat"].pct_change(4) * 100).round(1)
    con.to_csv(HERE / "reports" / "quarterly_earnings.csv")

    # ---- markdown (last 8 quarters, brokerage layout) -----------------------
    def m(v): return f"{v/1e6:,.2f}"      # $ millions
    qs = list(con.index)[-8:]
    L = ["# Proprietary Trading — Quarterly Earnings (brokerage-style)", "",
         f"Consolidated results, USD millions. Firm AUM ${AUM_PER_DESK*5/1e6:,.0f}M "
         f"across 5 desks; regime-conditional strategy, liquidity-gated (HIGH+MEDIUM "
         f"turnover). Segments = geography desks. Simulated from the 10y backtest — "
         f"gross of slippage; opex {OPEX_ANNUAL_PCT*100:.1f}% AUM p.a., tax = short-term "
         f"cap-gains by jurisdiction, EPS on {SHARES_OUT/1e6:.0f}M shares. Not a forecast.",
         "",
         "## Consolidated P&L ($M)", "",
         "| Line | " + " | ".join(qs) + " |", "|---|" + "---|"*len(qs)]
    def row(lbl, key, fn=m):
        return f"| {lbl} | " + " | ".join(fn(con.loc[q, key]) for q in qs) + " |"
    L += [row("Revenue from operations (trading)", "trading_revenue"),
          row("Other income (treasury on float)", "other_income"),
          row("**Total income**", "total_income"),
          row("Fees & commission expense", "fees_commission"),
          row("Operating expenses", "operating_expense"),
          row("**Total expenses**", "total_expense"),
          row("**Profit before tax (PBT)**", "pbt"),
          row("Tax expense", "tax"),
          row("**Profit after tax (PAT)**", "pat"),
          "| PAT margin % | " + " | ".join(f"{con.loc[q,'pat_margin_%']:.0f}%" if pd.notna(con.loc[q,'pat_margin_%']) else "n/m" for q in qs) + " |",
          "| EPS ($) | " + " | ".join(f"{con.loc[q,'eps']:.3f}" for q in qs) + " |",
          "| QoQ PAT % | " + " | ".join(f"{con.loc[q,'qoq_pat_%']:+.0f}%" if pd.notna(con.loc[q,'qoq_pat_%']) else "—" for q in qs) + " |",
          "| YoY PAT % | " + " | ".join(f"{con.loc[q,'yoy_pat_%']:+.0f}%" if pd.notna(con.loc[q,'yoy_pat_%']) else "—" for q in qs) + " |"]

    # segment revenue + PBT (last 8 quarters)
    for metric, title in [("trading_revenue","Segment revenue ($M)"), ("pat","Segment PAT ($M)")]:
        piv = seg.pivot_table(index="segment", columns="quarter", values=metric, aggfunc="sum")
        piv = piv[[q for q in qs if q in piv.columns]]
        L += ["", f"## {title}", "", "| Segment | " + " | ".join(piv.columns) + " |",
              "|---|" + "---|"*len(piv.columns)]
        for s in piv.index:
            L.append(f"| {s} | " + " | ".join(m(piv.loc[s,q]) for q in piv.columns) + " |")

    # annual roll-up
    con2 = con.copy(); con2["year"] = [q[:4] for q in con2.index]
    ann = con2.groupby("year")[["total_income","pbt","tax","pat"]].sum()
    ann["pat_margin_%"] = np.where(ann["total_income"] > 0.05e6,
                                   (ann["pat"]/ann["total_income"]*100).round(1), np.nan)
    L += ["", "## Annual roll-up ($M)", "", "| Year | Total income | PBT | Tax | PAT | Margin |",
          "|---|--:|--:|--:|--:|--:|"]
    for y in ann.index:
        r = ann.loc[y]
        mar = f"{r['pat_margin_%']:.0f}%" if pd.notna(r['pat_margin_%']) else "n/m"
        L.append(f"| {y} | {m(r.total_income)} | {m(r.pbt)} | {m(r.tax)} | {m(r.pat)} | {mar} |")
    L += ["", "> ⚠️ Simulated prop-desk results from the 10y backtest, gross of "
          "slippage/impact; AUM, opex, treasury, tax and share count are stated "
          "assumptions. Descriptive accounting, not a forecast or investment advice."]
    (HERE / "reports" / "quarterly_earnings.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote reports/quarterly_earnings.{{md,csv}}, segment_revenue_by_quarter.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
