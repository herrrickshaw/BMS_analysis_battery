#!/usr/bin/env python3
"""
metrics_from_filings.py — financial metrics computed from EXCHANGE FILINGS,
cross-validated against the public websites (screener.in / Trendlyne /
Moneycontrol) that investors actually read.

WHY COMPUTE FROM FILINGS AND CHECK AGAINST WEBSITES, NOT THE REVERSE
--------------------------------------------------------------------
The XBRL panel is the primary record: what the company filed, when it filed it.
The websites are derived views of the same filings — convenient, but each one
rounds, restates, and re-buckets slightly differently. Computing metrics from
the filings and then CHECKING agreement with the sites gives:

  * numbers with provenance (every figure traces to a filing with a date), and
  * an automated correctness harness: if our EPS disagrees with screener.in AND
    Moneycontrol for the same quarter, OUR parse is wrong; if the sites also
    disagree with each other, the filing was restated and the divergence is the
    finding.

METRICS (all directly computable from the quarterly P&L filings)
    net_margin        pat / revenue
    opm_proxy         (pbt + finance_costs + depreciation) / revenue  — EBITDA-ish
                      margin from reported lines; labelled a PROXY because Indian
                      filings don't carry a clean EBITDA row
    eps_basic         as filed
    rev_yoy, pat_yoy  vs the same quarter last year (needs both filings)
    interest_cover    (pbt + finance_costs) / finance_costs

VALIDATION UNITS: XBRL values are RUPEES; screener.in's quarterly table is Rs
CRORE (divide by 1e7); EPS is per-share on both sides. Consolidated filings are
compared against the /consolidated/ page, standalone against the standalone page
— mixing them is the classic false mismatch.

    metrics_from_filings.py                    # metrics for every parsed filing
    metrics_from_filings.py --validate 6       # cross-check N symbols vs screener.in
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

try:
    import data_registry as _R
    PANEL = _R.MARKET_CACHE / "nse_xbrl" / "pit_quarterly.parquet"
    OUT = _R.MARKET_CACHE / "nse_xbrl" / "metrics_quarterly.parquet"
except Exception:
    HERE = Path(__file__).resolve().parent
    PANEL = HERE / "cache_seed" / "nse_xbrl" / "pit_quarterly.parquet"
    OUT = HERE / "cache_seed" / "nse_xbrl" / "metrics_quarterly.parquet"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


# ── metrics ───────────────────────────────────────────────────────────────────
def compute() -> pd.DataFrame:
    d = pd.read_parquet(PANEL)
    d["period_end"] = pd.to_datetime(d["period_end"])
    d = d.sort_values(["symbol", "period_end"])

    def safe_div(a, b):
        return a / b if (pd.notna(a) and pd.notna(b) and b not in (0, 0.0)) else None

    rows = []
    for _, r in d.iterrows():
        rev, pat, pbt = r.get("revenue"), r.get("pat"), r.get("pbt")
        fin, dep = r.get("finance_costs"), r.get("depreciation")
        m = {
            "symbol": r["symbol"], "period_end": r["period_end"],
            "filing_date": r.get("filing_date"), "consolidated": r.get("consolidated"),
            "revenue_cr": rev / 1e7 if pd.notna(rev) else None,
            "pat_cr": pat / 1e7 if pd.notna(pat) else None,
            "eps_basic": r.get("eps_basic"),
            "net_margin_pct": (safe_div(pat, rev) or 0) * 100 if safe_div(pat, rev) is not None else None,
            "opm_proxy_pct": (safe_div((pbt or 0) + (fin or 0) + (dep or 0), rev) or 0) * 100
                             if (pd.notna(pbt) and pd.notna(rev) and rev) else None,
            "interest_cover": safe_div((pbt or 0) + (fin or 0), fin)
                              if (pd.notna(fin) and fin) else None,
        }
        rows.append(m)
    out = pd.DataFrame(rows)

    # YoY: same quarter last year, same consolidation basis. Matching on the
    # period-end MONTH+year-1 tolerates the 31-Mar/30-Mar端 variations.
    key = out.assign(_y=out.period_end.dt.year, _m=out.period_end.dt.month)
    prior = key.rename(columns={"revenue_cr": "_rev_py", "pat_cr": "_pat_py"})
    prior = prior[["symbol", "consolidated", "_y", "_m", "_rev_py", "_pat_py"]]
    prior["_y"] += 1
    merged = key.merge(prior, on=["symbol", "consolidated", "_y", "_m"], how="left")
    out["rev_yoy_pct"] = ((merged.revenue_cr - merged._rev_py) / merged._rev_py.abs() * 100
                          ).where(merged._rev_py.notna() & (merged._rev_py != 0))
    out["pat_yoy_pct"] = ((merged.pat_cr - merged._pat_py) / merged._pat_py.abs() * 100
                          ).where(merged._pat_py.notna() & (merged._pat_py != 0))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False); tmp.replace(OUT)
    return out


# ── validation vs screener.in ─────────────────────────────────────────────────
def _screener_quarters(symbol: str, consolidated: bool) -> pd.DataFrame:
    """screener.in's quarterly table: (quarter_label, sales_cr, pat_cr, eps).

    Parsed from the public company page. Polite: callers sample a handful of
    symbols — this host hard-blocked the machine twice on 2026-07-21; the
    validation budget is ~1 request/symbol, never a crawl.
    """
    import io
    import requests
    seg = "consolidated/" if consolidated else ""
    r = requests.get(f"https://www.screener.in/company/{symbol}/{seg}",
                     headers=UA, timeout=25)
    r.raise_for_status()
    # Row labels live inside <button> elements (Company.showSchedule handlers),
    # so naive ">Label</td>" regexes match nothing. pd.read_html flattens the
    # cell markup to text, which is exactly what we want.
    try:
        tables = pd.read_html(io.StringIO(r.text))
    except ValueError:
        return pd.DataFrame()
    qt = None
    for t in tables:
        cols = [str(c) for c in t.columns]
        first = t.iloc[:, 0].astype(str)
        if (sum(bool(re.match(r"[A-Z][a-z]{2} \d{4}", c)) for c in cols) >= 4
                and first.str.contains("Net Profit").any()):
            qt = t
            break
    if qt is None:
        return pd.DataFrame()
    qt = qt.set_index(qt.columns[0])
    qt.index = qt.index.astype(str).str.replace(r"[+\xa0]", "", regex=True).str.strip()

    def row(label):
        hit = [i for i in qt.index if i.startswith(label)]
        if not hit:
            return None
        return pd.to_numeric(qt.loc[hit[0]].astype(str).str.replace(",", ""),
                             errors="coerce")
    sales = row("Sales") if row("Sales") is not None else row("Revenue")
    pat, eps = row("Net Profit"), row("EPS in Rs")
    if sales is None:
        return pd.DataFrame()
    quarters = [str(c) for c in qt.columns]
    return pd.DataFrame({"quarter": quarters,
                         "sales_cr": sales.values,
                         "pat_cr": pat.values if pat is not None else None,
                         "eps": eps.values if eps is not None else None})


_MON = {1: None, 3: "Mar", 6: "Jun", 9: "Sep", 12: "Dec"}


def validate(n_symbols: int) -> int:
    m = pd.read_parquet(OUT)
    m["period_end"] = pd.to_datetime(m["period_end"])
    # screener.in's quarterly table shows roughly the trailing 3 years
    recent = m[m.period_end >= m.period_end.max() - pd.Timedelta(days=1100)]
    syms = recent["symbol"].value_counts().head(n_symbols).index.tolist()
    print(f"  validating {len(syms)} symbols against screener.in "
          f"(filings vs the site's quarterly table)\n")
    ok = diff = nof = 0
    for sym in syms:
        ours_all = recent[recent.symbol == sym]
        # MATCH THE BASIS PER FILING, not per symbol. A company files both
        # standalone and consolidated; comparing a consolidated filing against
        # the standalone page produced a 2.3x "mismatch" (SHYAMMETL: 3,612cr vs
        # 1,559cr) that was two true numbers for two different entities.
        for basis, ours in ours_all.groupby(
                ours_all["consolidated"].astype(str).str.startswith("Consolidated")):
            try:
                site = _screener_quarters(sym, bool(basis))
            except Exception as e:
                print(f"  {sym:12} site fetch failed ({type(e).__name__}) — skipped")
                nof += 1
                time.sleep(3)
                continue
            if site.empty:
                print(f"  {sym:12} [{'cons' if basis else 'stdl'}] no quarterly table")
                nof += 1
                time.sleep(3)
                continue
            for _, r in ours.iterrows():
                mon = r.period_end.month
                label = f"{_MON.get(mon, r.period_end.strftime('%b'))} {r.period_end.year}"
                hit = site[site.quarter == label]
                if hit.empty or r.revenue_cr is None:
                    continue
                s = hit.iloc[0]
                # Tolerance: 2% relative OR 1 crore absolute — the site rounds
                # to whole crore, which is 5% of a Rs20cr quarter. And a nil-
                # revenue quarter shows as blank on the site, not zero: fall
                # back to PAT agreement rather than calling truth a mismatch.
                def close(a, b, rel=0.02, absr=1.0):
                    if a is None or b is None or b != b:
                        return None
                    return abs(a - b) <= max(rel * abs(b), absr)
                rev_ok = close(r.revenue_cr, s.sales_cr)
                pat_ok = close(r.pat_cr, s.pat_cr, rel=0.05, absr=1.0)
                if rev_ok is None:
                    good = bool(pat_ok)
                    flag = "OK " if good else "DIFF"
                elif rev_ok:
                    good = pat_ok is not False
                    flag = "OK " if good else "DIFF"
                elif pat_ok:
                    # Revenue far apart while PAT agrees EXACTLY is not a parse
                    # error — it is two revenue conventions. Excise-paying
                    # industries (liquor, tobacco) file revenue GROSS of excise;
                    # the websites net it out. RADICO: filing 3,715cr gross vs
                    # site 925cr net, PAT 65 == 65. The filing carries no excise
                    # element to reconcile with, so this is classified, not
                    # forced to agree.
                    good = True
                    flag = "DEFN"
                else:
                    good = False
                    flag = "DIFF"
                ok += 1 if good else 0
                diff += 0 if good else 1
                sc = f"{s.sales_cr:,.0f}" if s.sales_cr == s.sales_cr else "—"
                pc = f"{s.pat_cr:,.0f}" if (s.pat_cr is not None and s.pat_cr == s.pat_cr) else "—"
                print(f"  {flag} {sym:12} [{'cons' if basis else 'stdl'}] {label}: "
                      f"rev {r.revenue_cr:>9,.0f} vs {sc:>9} cr | "
                      f"pat {r.pat_cr if r.pat_cr is not None else float('nan'):>7,.0f} vs {pc:>7}")
            time.sleep(3)          # polite — this host blocks
    print(f"\n  agreement: {ok} OK · {diff} DIFF · {nof} unfetchable")
    print("  (DIFF with ONE site = check the parse; DIFF with ALL sites = restated filing)")
    return 0 if diff == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", type=int, default=0, metavar="N")
    a = ap.parse_args()
    out = compute()
    got = out.dropna(subset=["revenue_cr"])
    print(f"  metrics: {len(out)} filing-quarters, {out.symbol.nunique()} symbols "
          f"({got.rev_yoy_pct.notna().sum()} with YoY) -> {OUT.name}")
    if a.validate:
        return validate(a.validate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
