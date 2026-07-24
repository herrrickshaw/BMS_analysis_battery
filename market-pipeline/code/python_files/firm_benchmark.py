#!/usr/bin/env python3
"""
firm_benchmark.py — quantify the profitability lift from the reward-optimised
factor map (income + balance-sheet stability), then benchmark the firm's returns
against REAL listed trading/brokerage firms per geography (live yfinance).

One panel pass per market computes the firm's annual P&L under BOTH the current
and the optimised regime maps; reports mean PAT, ROE, annual Sharpe, worst year
and loss-year count for each. Then pulls actual ROE / net margin / revenue growth
for Motilal Oswal, Interactive Brokers, Nomura, Mirae Asset, Flow Traders, etc.

Output: reports/firm_benchmark.md + reports/firm_benchmark.csv
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import strategy_regime_survival as S
import quarterly_earnings as Q
from profitability_optimizer import factor_library

HERE = Path(__file__).resolve().parent

COMPARABLES = {           # geography : {ticker: name}
 "India":  {"MOTILALOFS.NS": "Motilal Oswal", "ANGELONE.NS": "Angel One",
            "ISEC.NS": "ICICI Securities", "360ONE.NS": "360 ONE"},
 "US":     {"IBKR": "Interactive Brokers", "SCHW": "Charles Schwab",
            "HOOD": "Robinhood", "LPLA": "LPL Financial"},
 "Japan":  {"8604.T": "Nomura", "8601.T": "Daiwa Securities", "8628.T": "Matsui"},
 "Korea":  {"006800.KS": "Mirae Asset Sec", "016360.KS": "Samsung Securities"},
 "Europe": {"FLOW.AS": "Flow Traders", "IGG.L": "IG Group", "PLUS.L": "Plus500"},
}


def annual_firm_pnl(maps: dict) -> pd.DataFrame:
    """Annual per-desk + firm PAT under a given {mkt:{bull_rule,bear_rule}} map."""
    per_year = {}
    for mkt in S.MARKETS:
        close, turn = S.load_panel(mkt)
        reg = S.regime_series(close, turn)
        lib = factor_library(close)
        fwd = (close.shift(-S.FWD // 5) / close - 1).clip(-0.40, 0.40)
        br = maps[mkt]["bull_rule"]; er = maps[mkt]["bear_rule"]
        book = {}
        for t in close.index[close.index >= S.START]:
            g = reg.get(t)
            if g not in ("bull", "bear"):
                continue
            liq = S.liquidity_mask(turn.loc[t], close.loc[t])
            f = fwd.loc[t].where(liq).dropna()
            if len(f) < S.MIN_NAMES:
                continue
            buys = f[lib[br if g == "bull" else er].loc[t].reindex(f.index) == 1]
            if len(buys) >= 5:
                book[t] = float(buys.mean())
        bs = pd.Series(book).sort_index()
        holds = bs.iloc[::2]                         # non-overlapping 2wk holds
        tax_r, cbps, rf = Q.TAX_ST[mkt], Q.COST_BPS[mkt], Q.RF[mkt]
        for yr, g in holds.groupby(holds.index.year):
            gross = Q.AUM_PER_DESK * g.sum()
            treas = Q.AUM_PER_DESK * Q.IDLE_FRACTION * rf
            txn = Q.AUM_PER_DESK * len(g) * cbps / 1e4
            opex = Q.AUM_PER_DESK * Q.OPEX_ANNUAL_PCT
            pbt = gross + treas - txn - opex
            pat = pbt - max(0.0, pbt) * tax_r
            per_year.setdefault(yr, 0.0)
            per_year[yr] += pat
    return pd.Series(per_year).sort_index()


def stats(pat: pd.Series, equity: float) -> dict:
    return {"mean_pat_$M": pat.mean()/1e6, "roe_%": pat.mean()/equity*100,
            "sharpe": pat.mean()/pat.std() if pat.std() else float("nan"),
            "worst_yr_$M": pat.min()/1e6, "loss_years": int((pat < 0).sum()),
            "n_years": len(pat)}


def fetch_comparables() -> pd.DataFrame:
    import yfinance as yf
    rows = []
    for geo, d in COMPARABLES.items():
        for tk, nm in d.items():
            roe = mar = rg = mcap = np.nan
            try:
                info = yf.Ticker(tk).info
                roe = info.get("returnOnEquity"); mar = info.get("profitMargins")
                rg = info.get("revenueGrowth"); mcap = info.get("marketCap")
            except Exception:
                pass
            rows.append({"geography": geo, "ticker": tk, "firm": nm,
                         "roe_%": roe*100 if roe is not None and roe==roe else np.nan,
                         "net_margin_%": mar*100 if mar is not None and mar==mar else np.nan,
                         "rev_growth_%": rg*100 if rg is not None and rg==rg else np.nan,
                         "mktcap_$B": mcap/1e9 if mcap else np.nan})
    return pd.DataFrame(rows)


def main() -> int:
    equity = Q.AUM_PER_DESK * len(S.MARKETS)
    cur = json.loads((HERE / "cache_seed" / "zone_regime.json").read_text())
    opt = json.loads((HERE / "cache_seed" / "zone_regime_optimized.json").read_text())
    print("computing annual firm P&L (current map)…")
    pat_cur = annual_firm_pnl(cur)
    print("computing annual firm P&L (optimised map)…")
    pat_opt = annual_firm_pnl(opt)
    sc, so = stats(pat_cur, equity), stats(pat_opt, equity)

    L = ["# Firm profitability: current vs reward-optimised, benchmarked to real firms", "",
         f"Firm equity ${equity/1e6:.0f}M (5 desks × ${Q.AUM_PER_DESK/1e6:.0f}M), 10y backtest, "
         "liquidity-gated, regime-conditional. Reward-optimised map = "
         "`zone_regime_optimized.json` (max information ratio).", "",
         "## Profitability & balance-sheet lift", "",
         "| metric | current | **optimised** |", "|---|--:|--:|",
         f"| mean annual PAT ($M) | {sc['mean_pat_$M']:.2f} | **{so['mean_pat_$M']:.2f}** |",
         f"| return on equity (ROE) | {sc['roe_%']:.1f}% | **{so['roe_%']:.1f}%** |",
         f"| annual Sharpe (PAT) | {sc['sharpe']:.2f} | **{so['sharpe']:.2f}** |",
         f"| worst year ($M) | {sc['worst_yr_$M']:.2f} | **{so['worst_yr_$M']:.2f}** |",
         f"| loss years (of {sc['n_years']}) | {sc['loss_years']} | **{so['loss_years']}** |", ""]

    # annual series side by side
    L += ["## Annual PAT ($M) — current vs optimised", "",
          "| year | " + " | ".join(str(y) for y in pat_cur.index) + " |",
          "|---|" + "---|"*len(pat_cur.index)]
    L.append("| current | " + " | ".join(f"{pat_cur[y]/1e6:+.2f}" for y in pat_cur.index) + " |")
    L.append("| optimised | " + " | ".join(f"{pat_opt.get(y, float('nan'))/1e6:+.2f}" for y in pat_cur.index) + " |")

    # real-firm benchmark
    print("fetching comparable firms (yfinance)…")
    bench = fetch_comparables()
    bench.to_csv(HERE / "reports" / "firm_benchmark_comparables.csv", index=False)
    L += ["", "## Benchmark — real listed trading/brokerage firms (live yfinance)", "",
          "ROE / net margin / rev growth are currency-neutral ratios (comparable); "
          "mkt cap is in each firm's LOCAL currency billions (not USD).", "",
          "| geography | firm | ROE | net margin | rev growth | mkt cap (local bn) |",
          "|---|---|--:|--:|--:|--:|"]
    for _, r in bench.iterrows():
        def g(v, s=""): return f"{v:.1f}{s}" if v == v else "—"
        L.append(f"| {r.geography} | {r.firm} | {g(r['roe_%'],'%')} | {g(r['net_margin_%'],'%')} | "
                 f"{g(r['rev_growth_%'],'%')} | {g(r['mktcap_$B'])} |")
    L.append(f"| **—** | **Our firm (optimised)** | **{so['roe_%']:.1f}%** | — | — | 0.005 |")
    L += ["", "> Our ROE is on a $5M paper-AUM prop book, gross of slippage; real firms "
          "carry fee/interest/AMC income, leverage and franchise value a pure prop desk "
          "lacks — read the comparison as a return-quality sanity check, not a valuation. "
          "Not investment advice."]
    (HERE / "reports" / "firm_benchmark.md").write_text("\n".join(L))
    pd.DataFrame({"year": pat_cur.index, "pat_current": pat_cur.values,
                  "pat_optimised": [pat_opt.get(y, np.nan) for y in pat_cur.index]}
                 ).to_csv(HERE / "reports" / "firm_benchmark.csv", index=False)
    print("\n".join(L))
    print("\nwrote reports/firm_benchmark.{md,csv} + firm_benchmark_comparables.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
