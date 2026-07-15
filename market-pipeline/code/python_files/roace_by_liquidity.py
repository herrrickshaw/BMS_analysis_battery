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
WORKERS = 3          # yfinance throttles; 6 workers straight after 4 market scans
                     # (~13,000 calls) returned ZERO statements for every ticker.
# yfinance does NOT raise when throttled — it returns EMPTY frames, so a throttle is
# indistinguishable from "this company has no data" unless you probe a name you KNOW has
# statements. RELIANCE.NS is the canary: if its income_stmt is empty, we are throttled.
BACKOFF_SECS = 180   # 3 minutes between attempts
MAX_ATTEMPTS = 5     # ~15 min of patience before giving up


def _throttled() -> bool:
    """True when yfinance is refusing us. Probes a ticker guaranteed to have data."""
    import yfinance as yf
    try:
        i = yf.Ticker("RELIANCE.NS").income_stmt
        return i is None or i.empty
    except Exception:
        return True


def wait_for_yfinance() -> bool:
    """Back off until yfinance answers again. Returns False if it never does.

    Waiting beats hammering: every failed call while throttled extends the block. This
    is the same lesson screener.in taught three times today — a restart is not a retry.
    """
    import time
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not _throttled():
            if attempt > 1:
                print(f"  yfinance responding again (attempt {attempt})")
            return True
        if attempt == MAX_ATTEMPTS:
            break
        print(f"  throttled — waiting {BACKOFF_SECS}s "
              f"(attempt {attempt}/{MAX_ATTEMPTS}, ~{BACKOFF_SECS*(MAX_ATTEMPTS-attempt)//60} min left)")
        time.sleep(BACKOFF_SECS)
    return False


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


def _series(df, *names):
    """All available years for the first matching statement line, newest first."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            v = df.loc[n].dropna()
            if len(v):
                return v.astype(float)
    return None


def roace_one(sym: str) -> dict | None:
    """ROCE for one symbol: latest, cash-adjusted, and its 5-year stability.

    THREE MEASURES, because ROCE alone answers less than it appears to:

    1. roace — EBIT / (Total Assets - Current Liabilities). The textbook figure.

    2. roace_ex_cash — the same with cash and short-term investments removed from
       capital employed. ROCE is DISTORTED BY LARGE CASH RESERVES: cash sits in
       Total Assets and inflates the denominator, so a cash-rich company posts an
       artificially depressed ROCE while looking capital-inefficient at nothing
       more than a strong balance sheet. Indian IT and pharma carry exactly this
       profile. Excess cash is not capital *employed* in the operating business,
       so removing it measures the operating engine rather than the treasury.

    3. roace_cv — coefficient of variation (sd/mean) of ROCE across every year of
       statements available (~5). A HIGH AND STABLE ROCE is the signal that
       management allocates capital well; a high but erratic ROCE is usually a
       cyclical peak being mistaken for skill. One year cannot distinguish them.
       LOWER cv = steadier. Reported alongside the level, never instead of it.

    Averaging note: this uses year-END capital employed, not the AVERAGE of
    opening and closing (the "A" in ROACE). yfinance gives ~5 annual snapshots, so
    a true average is available only for the overlapping years; year-end is the
    conventional simplification and is applied identically to every tier, so tier
    COMPARISONS stay valid even where a single company's level is slightly off.
    """
    import numpy as np
    import yfinance as yf

    try:
        t = yf.Ticker(f"{sym}.NS")
        inc, bal = t.income_stmt, t.balance_sheet
    except Exception:
        return None

    ebit_s = _series(inc, "EBIT", "Operating Income", "OperatingIncome")
    ta_s = _series(bal, "Total Assets")
    cl_s = _series(bal, "Current Liabilities", "Total Current Liabilities")
    if ebit_s is None or ta_s is None or cl_s is None:
        return None

    cash_s = _series(bal, "Cash Cash Equivalents And Short Term Investments",
                     "Cash And Cash Equivalents", "CashAndCashEquivalents")

    # align on the years present in all three statements
    yrs = [c for c in ebit_s.index if c in ta_s.index and c in cl_s.index]
    if not yrs:
        return None
    hist = []
    for c in yrs:
        ce = float(ta_s[c]) - float(cl_s[c])
        if ce > 0:
            hist.append(float(ebit_s[c]) / ce)
    if not hist:
        return None

    latest = yrs[0]
    ce = float(ta_s[latest]) - float(cl_s[latest])
    if ce <= 0:
        return None
    cash = float(cash_s[latest]) if cash_s is not None and latest in cash_s.index else 0.0
    ce_ex = ce - cash
    roace = float(ebit_s[latest]) / ce

    out = {"Symbol": sym, "ebit": float(ebit_s[latest]), "capital_employed": ce,
           "cash": cash, "roace": roace, "years": len(hist),
           "roace_ex_cash": (float(ebit_s[latest]) / ce_ex) if ce_ex > 0 else None,
           "cash_pct_of_ce": cash / ce * 100 if ce else None}
    # stability needs >=3 years to mean anything; mean must be non-trivial or cv explodes
    if len(hist) >= 3 and abs(np.mean(hist)) > 0.01:
        out["roace_cv"] = float(np.std(hist) / abs(np.mean(hist)))
    else:
        out["roace_cv"] = None
    out.update(_piotroski(t, inc, bal, ta_s, cl_s, yrs))
    return out


def _piotroski(t, inc, bal, ta_s, cl_s, yrs) -> dict:
    """Piotroski F-score from the SAME statements — 7 of the 9 tests.

    Computed here rather than reused because India's fundamentals routes
    (Trendlyne / screener.in / yfinance .info) never carried an F-score: this repo
    has had zero Indian fundamentals for its last 6 workbooks. The statements
    needed for ROCE already contain most of Piotroski's inputs, so the marginal
    cost is one extra call (cashflow).

    SEVEN of nine, and the score is scaled to that — the two share-issuance and
    gross-margin tests need data yfinance does not reliably return for Indian
    names. A 7-point scale is stated as such rather than a 9-point scale silently
    missing two points, which would drag every company toward "weak".
    """
    z = {"f_score": None, "f_max": 7}
    if len(yrs) < 2:
        return z
    y0, y1 = yrs[0], yrs[1]           # newest, prior
    try:
        cfs = t.cashflow
    except Exception:
        cfs = None
    ni = _series(inc, "Net Income", "NetIncome")
    cfo = _series(cfs, "Operating Cash Flow", "Total Cash From Operating Activities")
    ca = _series(bal, "Current Assets", "Total Current Assets")
    ltd = _series(bal, "Long Term Debt", "LongTermDebt")
    rev = _series(inc, "Total Revenue", "Operating Revenue")

    def at(s, c):
        return float(s[c]) if s is not None and c in s.index else None

    f, tested = 0, 0

    def test(cond):
        nonlocal f, tested
        if cond is None:
            return
        tested += 1
        f += 1 if cond else 0

    ni0, ni1 = at(ni, y0), at(ni, y1)
    ta0, ta1 = at(ta_s, y0), at(ta_s, y1)
    cfo0 = at(cfo, y0)
    roa0 = (ni0 / ta0) if ni0 is not None and ta0 else None
    roa1 = (ni1 / ta1) if ni1 is not None and ta1 else None

    test(roa0 > 0 if roa0 is not None else None)                       # 1 profitable
    test(cfo0 > 0 if cfo0 is not None else None)                       # 2 cash generative
    test(roa0 > roa1 if None not in (roa0, roa1) else None)            # 3 improving ROA
    test((cfo0 / ta0) > roa0 if None not in (cfo0, ta0, roa0) and ta0 else None)  # 4 accruals
    # 5 falling leverage
    l0 = (at(ltd, y0) / ta0) if at(ltd, y0) is not None and ta0 else None
    l1 = (at(ltd, y1) / ta1) if at(ltd, y1) is not None and ta1 else None
    test(l0 < l1 if None not in (l0, l1) else None)
    # 6 improving current ratio
    cr0 = (at(ca, y0) / at(cl_s, y0)) if at(ca, y0) is not None and at(cl_s, y0) else None
    cr1 = (at(ca, y1) / at(cl_s, y1)) if at(ca, y1) is not None and at(cl_s, y1) else None
    test(cr0 > cr1 if None not in (cr0, cr1) else None)
    # 7 improving asset turnover
    t0 = (at(rev, y0) / ta0) if at(rev, y0) is not None and ta0 else None
    t1 = (at(rev, y1) / ta1) if at(rev, y1) is not None and ta1 else None
    test(t0 > t1 if None not in (t0, t1) else None)

    if tested >= 5:                    # too sparse to be a score below this
        z["f_score"] = f * 7 / tested  # scale to the 7-point frame
        z["f_tested"] = tested
    return z


def main() -> int:
    print(f"\n{'='*72}\n  ROACE by LIQUIDITY tier — India | sample {PER_TIER}/tier\n{'='*72}")
    print("  Educational/research only. NOT investment advice.\n")
    if not wait_for_yfinance():
        print("  yfinance still throttled after "
              f"{MAX_ATTEMPTS} attempts / {MAX_ATTEMPTS*BACKOFF_SECS//60} min. Try later.")
        return 1
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
    # An empty `rows` used to crash with KeyError: 'Symbol' — pd.DataFrame([]) has no
    # columns, so the merge key does not exist. That made a HOST THROTTLE look like a
    # code bug. yfinance returns empty frames rather than raising when it throttles, so
    # this is the only signal there is: say what happened.
    if not rows:
        print("  ZERO tickers returned statements. yfinance is almost certainly")
        print("  throttling — it returns EMPTY frames rather than raising. Verify with:")
        print("      yf.Ticker('RELIANCE.NS').income_stmt   # empty => throttled")
        print("  Back off and retry later; do not run this straight after a full scan")
        print("  (four market scans make ~13,000 yfinance calls).")
        return 1
    got = pd.DataFrame(rows).merge(samp, on="Symbol", how="left")
    print(f"  statements retrieved for {len(got)}/{len(samp)} "
          f"({len(got)/len(samp)*100:.0f}%)\n")
    if got.empty:
        print("  no data"); return 1

    got["roace_pct"] = got["roace"] * 100
    got["roace_ex_cash_pct"] = got["roace_ex_cash"] * 100
    # winsorise: banks/NBFCs and shells produce |ROACE| in the hundreds, which the
    # mean cannot survive. Median is the honest headline; trimmed mean supports it.
    keep = got[got["roace_pct"].between(-50, 150)]

    print("  === 1. ROCE LEVEL — is capital better employed in liquid firms? ===")
    print(f"  {'TIER':7s} {'n':>4s} {'turnover Rs cr':>15s} {'ROCE':>7s} {'ex-cash':>8s} "
          f"{'cash%CE':>8s} {'p25':>7s} {'p75':>7s}")
    for tier in ("LARGE", "MID", "SMALL"):
        s = keep[keep["tier"] == tier]
        if not len(s):
            continue
        print(f"  {tier:7s} {len(s):>4} {s['turnover'].median()/1e7:>15,.1f} "
              f"{s['roace_pct'].median():>6.1f}% {s['roace_ex_cash_pct'].median():>7.1f}% "
              f"{s['cash_pct_of_ce'].median():>7.1f}% "
              f"{s['roace_pct'].quantile(.25):>6.1f}% {s['roace_pct'].quantile(.75):>6.1f}%")

    print("\n  === 2. ROCE STABILITY — high AND stable is the signal, not high alone ===")
    print(f"  {'TIER':7s} {'n':>4s} {'median CV':>10s} {'% with CV<0.3 (steady)':>23s} "
          f"{'% high AND steady':>18s}")
    for tier in ("LARGE", "MID", "SMALL"):
        s = keep[(keep["tier"] == tier) & keep["roace_cv"].notna()]
        if len(s) < 3:
            continue
        steady = (s["roace_cv"] < 0.30).mean() * 100
        both = ((s["roace_cv"] < 0.30) & (s["roace_pct"] > 15)).mean() * 100
        print(f"  {tier:7s} {len(s):>4} {s['roace_cv'].median():>10.2f} {steady:>22.0f}% "
              f"{both:>17.0f}%")
    print("    (CV = sd/mean of ROCE across ~5y of statements; LOWER = steadier.")
    print("     'high AND steady' = ROCE > 15% and CV < 0.30 in the same company)")

    if "f_score" in keep.columns and keep["f_score"].notna().any():
        print("\n  === 3. ROCE x PIOTROSKI — do they agree, or find different firms? ===")
        f = keep[keep["f_score"].notna()]
        print(f"  {'TIER':7s} {'n':>4s} {'median F':>9s} {'% F>=7':>8s} "
              f"{'ROCE if F>=7':>13s} {'ROCE if F<=3':>13s}")
        for tier in ("LARGE", "MID", "SMALL"):
            s = f[f["tier"] == tier]
            if len(s) < 3:
                continue
            hi = s[s["f_score"] >= 7]["roace_pct"].median()
            lo = s[s["f_score"] <= 3]["roace_pct"].median()
            print(f"  {tier:7s} {len(s):>4} {s['f_score'].median():>9.1f} "
                  f"{(s['f_score']>=7).mean()*100:>7.0f}% "
                  f"{hi if pd.notna(hi) else float('nan'):>12.1f}% "
                  f"{lo if pd.notna(lo) else float('nan'):>12.1f}%")
        cor = f[["roace_pct", "f_score"]].corr(method="spearman").iloc[0, 1]
        print(f"    spearman corr(ROCE, F-score) = {cor:+.3f}")
        print("    ROCE measures long-run capital efficiency; Piotroski measures")
        print("    year-on-year fundamental IMPROVEMENT. A low correlation means they")
        print("    are complements, not substitutes — a firm can earn 30% on capital")
        print("    while deteriorating (high ROCE, low F), or be a turnaround off a")
        print("    weak base (low ROCE, high F).")

    print(f"\n  dropped as out-of-range (banks/NBFCs/shells): {len(got)-len(keep)}")
    print("  NOTE: ROCE says nothing about cash flow, revenue growth, or the ability to")
    print("  meet short-term obligations. It is a long-run efficiency measure and is")
    print("  read here alongside, not instead of, the liquidity gate.")
    out = "reports/roace_by_liquidity_india.csv"
    got.to_csv(out, index=False)
    print(f"  full sample -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
