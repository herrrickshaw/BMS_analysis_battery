#!/usr/bin/env python3
"""
validate_current_ratio_proxy.py — is the screener.in current-ratio proxy usable?

THE PROBLEM
-----------
Investopedia's definition is exact: current ratio = Current Assets / Current
Liabilities. screener.in's balance sheet CANNOT supply either term. Its Data Sheet
carries Equity Share Capital / Reserves / Borrowings / Other Liabilities / Total on
the liabilities side and Net Block / CWIP / Investments / Other Assets / Total on
the assets side, with Receivables / Inventory / Cash & Bank as a PARTIAL breakout of
Other Assets. There is no current vs non-current split anywhere.

So the proxy is:
    CA_proxy = receivables + inventory + cash      UNDERSTATES (misses loans &
                                                   advances, prepaid expenses)
    CL_proxy = other_liab                          OVERSTATES (includes non-current
                                                   provisions, deferred tax)
Both errors push the LEVEL down. The proxy's current ratio is simply wrong as a
number and must never be reported as one.

WHY IT MIGHT STILL BE FINE — AND WHY THAT NEEDS TESTING, NOT ASSERTING
----------------------------------------------------------------------
Piotroski's test 6 does not use the level. It asks one thing: DID THE CURRENT RATIO
RISE? Only the SIGN OF THE CHANGE matters. A level bias that is roughly stable
year-to-year cancels in the delta — so a badly-scaled proxy can still get the sign
right nearly always.

"Roughly stable" is an assumption, and assuming it is how a plausible-but-wrong test
gets shipped. This measures it instead: yfinance publishes TRUE Current Assets and
Current Liabilities (~5y) for the same companies screener.in covers for 10y. On the
overlap, compute both, and check how often the proxy's delta sign matches the truth's.

DECISION RULE, fixed BEFORE seeing the result so it cannot be rationalised after:
    >= 80% sign agreement  -> proxy is sound for test 6; use it across the 10y series
    65-80%                 -> marginal; usable ONLY if flagged as approximate
    <  65%                 -> DROP test 6. A coin-flip test that looks populated is
                              worse than a skipped one — it adds noise while implying
                              information, exactly like the quarterly Operating Profit
                              trap avoided earlier.

This is the same discipline that validated EBIT (pbt+interest, checked against
yfinance: RELIANCE 8.9% vs 9.0%) and gross profit (COGS sign pinned by reconstructing
reported PBT to the rupee). A derived field earns its place by matching an
independent source, never by sounding reasonable.
"""
from __future__ import annotations

import concurrent.futures as cf
import sys
import warnings

warnings.filterwarnings("ignore")

import duckdb
import pandas as pd

FUND = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/IN.parquet"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
WORKERS = 6


def truth(sym: str):
    """yfinance's REAL current assets / current liabilities, per fiscal year."""
    import yfinance as yf

    try:
        bal = yf.Ticker(f"{sym}.NS").balance_sheet
    except Exception:
        return None
    if bal is None or bal.empty:
        return None

    def row(*names):
        for n in names:
            if n in bal.index:
                v = bal.loc[n].dropna()
                if len(v):
                    return v.astype(float)
        return None

    ca = row("Current Assets", "Total Current Assets")
    cl = row("Current Liabilities", "Total Current Liabilities")
    if ca is None or cl is None:
        return None
    out = {}
    for c in ca.index:
        if c in cl.index and float(cl[c]):
            out[pd.Timestamp(c).date()] = float(ca[c]) / float(cl[c])
    return {"Symbol": sym, "cr": out} if out else None


def main() -> int:
    con = duckdb.connect()
    f = con.execute(f"""
        SELECT ticker, CAST(fy_end AS DATE) fy_end, receivables, inventory, cash, other_liab
        FROM '{FUND}'
        WHERE other_liab > 0 AND receivables IS NOT NULL
    """).df()
    f["cr_proxy"] = ((f.receivables.fillna(0) + f.inventory.fillna(0) + f.cash.fillna(0))
                     / f.other_liab)
    syms = (f.groupby("ticker").size().sort_values(ascending=False).head(N).index.tolist())
    print(f"\n{'='*76}\n  CURRENT-RATIO PROXY VALIDATION — sign of the delta is what matters"
          f"\n{'='*76}")
    print(f"  testing {len(syms)} tickers against yfinance's true Current Assets/Liabilities\n")

    truths = []
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for t in ex.map(truth, syms):
            if t:
                truths.append(t)
    print(f"  yfinance returned true current ratios for {len(truths)}/{len(syms)}\n")

    rows = []
    for t in truths:
        g = f[f.ticker == t["Symbol"]].sort_values("fy_end")
        for i in range(1, len(g)):
            cur, prv = g.iloc[i], g.iloc[i - 1]
            tc, tp = t["cr"].get(cur.fy_end), t["cr"].get(prv.fy_end)
            if tc is None or tp is None:
                continue
            rows.append({
                "Symbol": t["Symbol"], "fy": cur.fy_end,
                "true_cr": tc, "proxy_cr": cur.cr_proxy,
                "true_rising": tc > tp, "proxy_rising": cur.cr_proxy > prv.cr_proxy,
            })
    d = pd.DataFrame(rows)
    if d.empty:
        print("  no overlapping years — cannot validate"); return 1

    agree = (d.true_rising == d.proxy_rising).mean() * 100
    print(f"  === LEVEL (expected to be wrong — reported to prove the point) ===")
    print(f"    median true current ratio : {d.true_cr.median():.2f}")
    print(f"    median proxy current ratio: {d.proxy_cr.median():.2f}")
    print(f"    -> the proxy LEVEL is not a current ratio and must never be shown as one\n")
    print(f"  === SIGN OF THE DELTA (what Piotroski test 6 actually asks) ===")
    print(f"    n = {len(d)} company-years across {d.Symbol.nunique()} tickers")
    print(f"    proxy delta sign matches truth: {agree:.1f}%")
    base = max(d.true_rising.mean(), 1 - d.true_rising.mean()) * 100
    print(f"    always-guess-the-majority baseline: {base:.1f}%  <- proxy must beat this")
    print()
    if agree >= 80:
        v = "SOUND -> use across the 10y series"
    elif agree >= 65:
        v = "MARGINAL -> usable only if flagged approximate"
    else:
        v = "DROP test 6 — a coin-flip that looks populated is worse than a skip"
    print(f"    VERDICT: {agree:.1f}% -> {v}")
    d.to_csv("reports/current_ratio_proxy_validation.csv", index=False)
    print(f"\n  -> reports/current_ratio_proxy_validation.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
