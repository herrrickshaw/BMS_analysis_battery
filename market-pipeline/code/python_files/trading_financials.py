#!/usr/bin/env python3
"""
Firm-wise Income Statement + Balance Sheet from the paper-trade signal ledger.

Source: reports/signal_outcomes.parquet  (the daily-brief paper-track book)
A "trade" = one signal (market, symbol, signal_date, filter, source), equal-weight.
Realized P&L uses the LONGEST scored horizon per signal (held-to-latest-close spirit).
Open positions (all-pending signals) are carried at cost on the balance sheet.

ALL non-ledger numbers below are STATED MODELING ASSUMPTIONS, tunable at the top.
This is descriptive accounting on a paper book — NOT investment advice.
"""
import pandas as pd, numpy as np, json, sys

LEDGER = "reports/signal_outcomes.parquet"

# ---- ASSUMPTIONS (tunable) -------------------------------------------------
NOTIONAL = 10_000.0            # USD deployed per position, equal-weight
GEO = {"IN":"India","US":"United States","EU":"Europe","JP":"Japan","KR":"Korea"}

# effective capital-gains tax (short-term / long-term). LT applies to h==252 (~1yr).
TAX = {  # (short, long)
 "IN":(0.200,0.125),   # India: STCG 20%, LTCG 12.5% (post-Jul'24 Budget)
 "US":(0.240,0.150),   # US: ST=ordinary(~24% marginal), LT 15%
 "EU":(0.26375,0.26375), # DE Abgeltungsteuer 26.375%, flat (EU blended proxy)
 "JP":(0.20315,0.20315), # Japan flat 20.315%
 "KR":(0.000,0.000),   # Korea: retail listed-share gains exempt (<KRW5bn holding)
}
# round-trip transaction cost, bps of notional (brokerage+tax+exch+spread proxy)
COST_BPS = {"IN":35,"US":10,"EU":25,"JP":15,"KR":30}
# cost of equity (=cost of capital; all-equity book), Jan-2026 approx = Rf + ERP
KE = {"IN":0.138,"US":0.089,"EU":0.080,"JP":0.065,"KR":0.092}
LT_HORIZON = 252               # trading days treated as long-term
# ---------------------------------------------------------------------------

df = pd.read_parquet(LEDGER)
KEY = ["market","symbol","signal_date","filter","source"]

# ---- realized trades: longest scored horizon per signal --------------------
scored = df[(df.status=="scored") & df.fwd_ret.notna()].copy()
scored = scored.sort_values("h").groupby(KEY, dropna=False, as_index=False).last()
scored["long_term"] = scored["h"] >= LT_HORIZON
scored["notional"] = NOTIONAL
scored["gross_pnl"] = scored["notional"] * scored["fwd_ret"]
scored["txn_cost"]  = scored["notional"] * scored["market"].map(COST_BPS)/1e4
scored["net_pnl_pretax"] = scored["gross_pnl"] - scored["txn_cost"]

# Tax with within-(geography, term) loss offset: losses net against gains inside
# each bucket, tax the positive residual, then allocate that tax across winners.
scored["tax"] = 0.0
for (mkt, lt), b in scored.groupby(["market","long_term"]):
    rate = TAX[mkt][1] if lt else TAX[mkt][0]
    base = max(0.0, b["net_pnl_pretax"].sum())          # net gains after offset
    tax_bucket = base * rate
    pos = b.loc[b["net_pnl_pretax"]>0, "net_pnl_pretax"]
    if pos.sum() > 0:
        scored.loc[pos.index, "tax"] = pos/pos.sum() * tax_bucket   # allocate to winners
scored["net_income"] = scored["net_pnl_pretax"] - scored["tax"]

# ---- open positions (all-pending signals) ----------------------------------
kstat = (df.assign(_pending=df.status.eq("pending"))
           .groupby(KEY, dropna=False)
           .agg(all_pending=("_pending","all"))
           .reset_index())          # market is in KEY -> already a column
open_by_mkt = kstat[kstat.all_pending].groupby("market").size()

# ---- per-geography income statement ----------------------------------------
def seg_income(g):
    gains  = g.loc[g.gross_pnl>0,"gross_pnl"].sum()
    losses = g.loc[g.gross_pnl<=0,"gross_pnl"].sum()
    txn    = g["txn_cost"].sum()
    ebit   = gains + losses - txn
    tax    = g["tax"].sum()
    ni     = ebit - tax
    return pd.Series({
        "trades":len(g), "winners":(g.gross_pnl>0).sum(), "hit_rate":(g.gross_pnl>0).mean(),
        "capital_deployed":len(g)*NOTIONAL,
        "revenue_gross_gains":gains, "trading_losses":losses,
        "gross_trading_profit":gains+losses, "txn_costs":-txn,
        "operating_income_ebit":ebit, "income_tax":-tax, "net_income":ni,
    })
inc = scored.groupby("market").apply(seg_income, include_groups=False)
inc = inc.reindex([m for m in GEO if m in inc.index])

# cost-of-capital / economic profit
inc["equity_capital"] = (inc["trades"] + inc.index.map(lambda m: open_by_mkt.get(m,0)))*NOTIONAL
inc["cost_of_capital_%"] = inc.index.map(KE)
inc["capital_charge"] = inc["equity_capital"]*inc["cost_of_capital_%"]
inc["economic_profit_eva"] = inc["net_income"] - inc["capital_charge"]
inc["ROIC_%"] = inc["net_income"]/inc["equity_capital"]

# ---- per-geography balance sheet -------------------------------------------
def seg_bs(m):
    g = scored[scored.market==m]
    n_op = int(open_by_mkt.get(m,0))
    contributed = (len(g)+n_op)*NOTIONAL
    ebit = inc.loc[m,"operating_income_ebit"]; tax = -inc.loc[m,"income_tax"]
    re   = ebit - tax                      # retained earnings (net income)
    investments = n_op*NOTIONAL            # open positions at cost
    tax_payable = tax
    total_assets = contributed + ebit      # = equity + liabilities
    cash = total_assets - investments
    return pd.Series({
        "cash":cash, "investments_at_cost":investments, "total_assets":total_assets,
        "income_tax_payable":tax_payable, "total_liabilities":tax_payable,
        "contributed_capital":contributed, "retained_earnings":re,
        "total_equity":contributed+re,
        "open_positions":n_op,
        "check_A=L+E": total_assets-(tax_payable+contributed+re),
    })
bs = pd.DataFrame({m:seg_bs(m) for m in inc.index}).T

# ---- firm-wise (per symbol) detail -----------------------------------------
firm = (scored.groupby(["market","symbol"])
        .agg(trades=("net_income","size"), hit=("gross_pnl",lambda s:(s>0).mean()),
             revenue_gross_gains=("gross_pnl",lambda s:s[s>0].sum()),
             gross_trading_profit=("gross_pnl","sum"),
             txn_costs=("txn_cost","sum"), income_tax=("tax","sum"),
             net_income=("net_income","sum"))
        .reset_index())
firm["capital_deployed"]=firm["trades"]*NOTIONAL
firm["operating_income_ebit"]=firm["gross_trading_profit"]-firm["txn_costs"]
firm["geography"]=firm["market"].map(GEO)
firm = firm.sort_values("net_income", ascending=False)

# ---- output ----------------------------------------------------------------
pd.set_option("display.float_format", lambda x:f"{x:,.0f}")
tot = inc[["trades","capital_deployed","revenue_gross_gains","trading_losses",
           "gross_trading_profit","txn_costs","operating_income_ebit","income_tax",
           "net_income","equity_capital","capital_charge","economic_profit_eva"]].sum()

print("="*78); print("INCOME STATEMENT — by geography (USD, $%s/position, realized closed trades)"%f"{NOTIONAL:,.0f}")
print("="*78)
show=inc.copy(); show.index=show.index.map(GEO)
show["hit_rate"]=(show["hit_rate"]*100).round(1)
show["cost_of_capital_%"]=(show["cost_of_capital_%"]*100).round(1)
show["ROIC_%"]=(show["ROIC_%"]*100).round(1)
print(show[["trades","hit_rate","revenue_gross_gains","trading_losses","gross_trading_profit",
            "txn_costs","operating_income_ebit","income_tax","net_income",
            "cost_of_capital_%","capital_charge","economic_profit_eva","ROIC_%"]].to_string())
print("\nCONSOLIDATED net income: {:,.0f} | EVA (after capital charge): {:,.0f}".format(
      tot.net_income, tot.economic_profit_eva))

print("\n"+"="*78); print("BALANCE SHEET — by geography (USD, period-end mark at cost)")
print("="*78)
bshow=bs.copy(); bshow.index=bshow.index.map(GEO)
print(bshow[["cash","investments_at_cost","total_assets","income_tax_payable",
             "contributed_capital","retained_earnings","total_equity","open_positions","check_A=L+E"]].to_string())

print("\n"+"="*78); print("TOP 15 FIRMS by net income"); print("="*78)
print(firm.head(15)[["geography","symbol","trades","hit","revenue_gross_gains",
      "operating_income_ebit","income_tax","net_income"]].to_string(index=False))
print("\nBOTTOM 8 FIRMS by net income")
print(firm.tail(8)[["geography","symbol","trades","gross_trading_profit","net_income"]].to_string(index=False))

# ---- STRATEGY vs BENCHMARK (step 10: which strategy beats the index) --------
strat = (scored.groupby(["market","filter"])
         .agg(trades=("net_income","size"), hit=("gross_pnl",lambda s:(s>0).mean()),
              mean_ret=("fwd_ret","mean"), bench_ret=("mkt_median","mean"),
              excess=("excess_ret","mean"), net_income=("net_income","sum"),
              ebit=("net_pnl_pretax","sum"))
         .reset_index())
strat["capital"]=strat["trades"]*NOTIONAL
strat["ROIC_%"]=(strat["net_income"]/strat["capital"]*100)
strat["alpha_bps"]=(strat["excess"]*1e4)
strat=strat[strat.trades>=20].sort_values("excess", ascending=False)
print("\n"+"="*78); print("STRATEGY vs BENCHMARK  (filter × market, >=20 trades) — ranked by excess return")
print("="*78)
sv=strat.copy()
for c in ["mean_ret","bench_ret","excess"]: sv[c]=(sv[c]*100).round(2)
sv["hit"]=(sv["hit"]*100).round(0); sv["ROIC_%"]=sv["ROIC_%"].round(1); sv["alpha_bps"]=sv["alpha_bps"].round(0)
print(sv[["market","filter","trades","hit","mean_ret","bench_ret","excess","ROIC_%","net_income"]].to_string(index=False))
strat.to_csv("reports/strategy_vs_benchmark.csv", index=False)

# save artifacts
firm.to_csv("reports/firm_financials.csv", index=False)
inc.assign(geography=inc.index.map(GEO)).to_csv("reports/income_statement_by_geo.csv")
bs.assign(geography=bs.index.map(GEO)).to_csv("reports/balance_sheet_by_geo.csv")
print("\nwrote reports/firm_financials.csv (%d firms), income_statement_by_geo.csv, balance_sheet_by_geo.csv"%len(firm))
