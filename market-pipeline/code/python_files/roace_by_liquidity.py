#!/usr/bin/env python3
"""
roace_by_liquidity.py — ROACE across large/mid/small cap, split by liquidity.

WHY THIS NEEDED A NEW COLLECTOR
-------------------------------
ROACE = EBIT / Capital Employed, where Capital Employed = Total Assets - Current
Liabilities. None of the existing fundamentals sources carry those inputs for India:

  market  route                      has EBIT?  why
  US      sec_fundamentals (EDGAR)   YES        real financial statements
  IN      Trendlyne -> screener.in   NO         header RATIOS only (pe/roe/d-e)
          -> yfinance .info          NO         .info has ebitda, not ebit+assets

So `cache_seed/fundamentals/IN.parquet` holds 525 rows of pe/roe/debt_to_equity and
ROACE was called impossible. It isn't: yfinance exposes `.income_stmt` and
`.balance_sheet` (NOT `.info`), which carry EBIT, Total Assets and Current
Liabilities directly, with ~5 years of history. Verified before building this:
    RELIANCE.NS  EBIT 1,472,180,000,000 / CE 16,368,860,000,000 = 9.0%
    TCS.NS       EBIT   667,140,000,000 / CE  1,214,580,000,000 = 54.9%
Both match their real-world ROCE (Reliance ~9-10%, TCS ~55% — asset-light IT).

An earlier attempt reconstructed capital employed from ratios
(equity = net_income/roe, assets = net_income/roa) and FAILED: cascading division
by small noisy denominators produced ROACE of 95-137% on a sample that collapsed
to 31 stocks. Read the statements; do not invert the ratios.

WHY LIQUIDITY-TIERED
--------------------
Fang, Noe & Tice (2009 JFE) find liquid firms have genuinely higher operating
returns on assets — liquidity tracks firm QUALITY. That is a separate claim from
returns, where Amihud (2002) finds illiquid stocks earn more. This script tests the
Fang/Noe/Tice half on Indian data: if they are right, ROACE should FALL as
liquidity falls.

Tiers are cut on median daily turnover from the 10.5y point-in-time OHLCV, so
"large/mid/small cap" here means liquidity-ranked, consistent with every other
gate in this repo, rather than a separate market-cap field that would disagree.

SAMPLING
--------
Each symbol costs 2 network calls, so the full 3,476-name universe is impractical
and pointless: a stratified sample answers "what is the ROACE profile per tier"
with a fraction of the calls. Sample size is per-tier and equal, so tiers are
directly comparable. Financial companies are NOT excluded here (see caveat in
main) — for banks/NBFCs capital employed is not meaningful, and they will show up
as outliers. Median is reported alongside mean for that reason.
"""
from __future__ import annotations

import concurrent.futures as cf
import sys
import warnings

warnings.filterwarnings("ignore")

import duckdb
import pandas as pd

PARQUET = "/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"
PER_TIER = int(sys.argv[1]) if len(sys.argv) > 1 else 45
WORKERS = 6          # modest: yfinance rate-limits, and this is a sample not a sweep


def tiers() -> pd.DataFrame:
    con = duckdb.connect()
    return con.execute(f"""
      WITH last60 AS (
        SELECT Symbol, Close*Volume AS tv,
               row_number() OVER (PARTITION BY Symbol ORDER BY Date DESC) rn
        FROM '{PARQUET}' WHERE Close>0 AND Volume>0),
      liq AS (SELECT Symbol, median(tv) AS turnover FROM last60 WHERE rn<=60
              GROUP BY 1 HAVING count(*)>=50),
      -- only names still trading, else we sample delisted shells with no statements
      alive AS (SELECT Symbol FROM '{PARQUET}' GROUP BY 1
                HAVING max(Date) >= DATE '2026-06-01')
      SELECT l.Symbol, l.turnover,
             CASE ntile(3) OVER (ORDER BY l.turnover DESC)
                  WHEN 1 THEN 'LARGE' WHEN 2 THEN 'MID' ELSE 'SMALL' END AS tier
      FROM liq l JOIN alive a USING (Symbol)
    """).df()


def roace_one(sym: str) -> dict | None:
    import yfinance as yf

    def pick(df, *names):
        if df is None or df.empty:
            return None
        for n in names:
            if n in df.index:
                v = df.loc[n].dropna()
                if len(v):
                    return float(v.iloc[0])
        return None

    try:
        t = yf.Ticker(f"{sym}.NS")
        inc, bal = t.income_stmt, t.balance_sheet
    except Exception:
        return None
    ebit = pick(inc, "EBIT", "Operating Income", "OperatingIncome")
    ta = pick(bal, "Total Assets")
    cl = pick(bal, "Current Liabilities", "Total Current Liabilities")
    if not ebit or not ta or not cl:
        return None
    ce = ta - cl
    if ce <= 0:
        return None
    return {"Symbol": sym, "ebit": ebit, "capital_employed": ce, "roace": ebit / ce}


def main() -> int:
    print(f"\n{'='*72}\n  ROACE by LIQUIDITY tier — India | sample {PER_TIER}/tier\n{'='*72}")
    print("  Educational/research only. NOT investment advice.\n")
    t = tiers()
    samp = (t.sort_values("turnover", ascending=False)
             .groupby("tier", group_keys=False)
             .apply(lambda g: g.head(PER_TIER * 3).sample(min(PER_TIER, len(g)), random_state=7)))
    print(f"  universe {len(t):,} live symbols -> sampling {len(samp)} "
          f"({PER_TIER}/tier), {WORKERS} workers\n")

    rows = []
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for r in ex.map(roace_one, samp["Symbol"].tolist()):
            if r:
                rows.append(r)
    got = pd.DataFrame(rows).merge(samp, on="Symbol", how="left")
    print(f"  statements retrieved for {len(got)}/{len(samp)} "
          f"({len(got)/len(samp)*100:.0f}%)\n")
    if got.empty:
        print("  no data"); return 1

    got["roace_pct"] = got["roace"] * 100
    # winsorise: banks/NBFCs and shells produce |ROACE| in the hundreds, which the
    # mean cannot survive. Median is the honest headline; trimmed mean supports it.
    keep = got[got["roace_pct"].between(-50, 150)]
    print(f"  {'TIER':7s} {'n':>4s} {'med turnover Rs cr':>19s} {'MEDIAN ROACE':>13s} "
          f"{'mean':>7s} {'p25':>7s} {'p75':>7s}")
    for tier in ("LARGE", "MID", "SMALL"):
        s = keep[keep["tier"] == tier]
        if not len(s):
            continue
        print(f"  {tier:7s} {len(s):>4} {s['turnover'].median()/1e7:>19,.1f} "
              f"{s['roace_pct'].median():>12.1f}% {s['roace_pct'].mean():>6.1f}% "
              f"{s['roace_pct'].quantile(.25):>6.1f}% {s['roace_pct'].quantile(.75):>6.1f}%")
    print(f"\n  dropped as out-of-range (banks/NBFCs/shells): {len(got)-len(keep)}")
    out = "reports/roace_by_liquidity_india.csv"
    got.to_csv(out, index=False)
    print(f"  full sample -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
