#!/usr/bin/env python3
"""
build_india_factor_panel.py — turn screener.in line items into a testable panel.

Produces one row per (ticker, rebalance year) carrying:
  f_score      Piotroski 0-9, computed from filed statements
  roce, roce_avg3, roce_cv, roce_level/stable/improving
  debt_ratio_falling      the debt-cycle condition
  xret_T+252d, xret_T+126d   benchmark-adjusted forward returns

NO-LOOKAHEAD RULES — the whole result is worthless without these
---------------------------------------------------------------
* Indian FY ends 31 March; audited annuals publish ~May-July. The collector's
  `filed` field is a FLAT fy_end+90d PROXY, not a real filing date, so it cannot
  be trusted on its own — 90 days lands 29 June, before many annuals exist.
* REBALANCE is therefore 1 AUGUST, and a fiscal year is only visible if
  fy_end + REPORTING_LAG(120d) <= rebalance. FY2025 (ended 2025-03-31) becomes
  usable 2025-07-29, so it is first traded on 2025-08-01. FY2026 is NOT visible
  on 2025-08-01 even though it sits in the same file.
* Forward returns are measured FROM the rebalance date, never from fiscal-year
  end. Using fy_end would hand the strategy four months it never had.

SURVIVORSHIP — unfixable here, and it flatters everything
---------------------------------------------------------
screener.in serves pages for companies that still exist. Firms that were delisted
or went bust between 2017 and 2026 have prices in the panel but no statements,
so they silently leave the scored universe. Those are precisely the names a
quality screen exists to avoid. Every number this produces is an upper bound.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FUND = Path("/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/IN.parquet")
PRICE = Path("/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet")
BENCH = "NIFTYBEES"
OUT = HERE / "cache_seed" / "india_factor_panel.parquet"

REPORTING_LAG = pd.Timedelta(days=120)
MIN_YEARS, MIN_CFO = 5, 3
# Years of total_assets a ticker needs before it can be scored at all.
MIN_BALANCE_SHEET = 3
# Tickers that must survive the filter before a panel is worth building.
MIN_TICKERS = 100

# Fields Piotroski cannot be computed without, and the tests that die with them.
# Coverage below REQUIRED_COVERAGE means the panel cannot answer the question and
# says so, instead of returning an all-zero column that reads as a result.
PIOTROSKI_INPUTS = {
    "total_assets":        "F1, F3, F4, F9 (denominator)",
    "cfo":                 "F2, F4",
    "long_term_debt":      "F5",
    "current_assets":      "F6",
    "current_liabilities": "F6",
    "shares":              "F7",
    "gross_profit":        "F8",
    "net_income":          "F1, F3",
    "revenue":             "F8, F9",
}
REQUIRED_COVERAGE = 0.30


def _assert_input_coverage(f: pd.DataFrame) -> None:
    """Refuse to build a panel whose inputs cannot support the score."""
    n = len(f)
    cov = {c: (f[c].notna().mean() if c in f.columns else 0.0)
           for c in PIOTROSKI_INPUTS}
    bad = {c: v for c, v in cov.items() if v < REQUIRED_COVERAGE}
    print(f"  input coverage over {n:,} rows:")
    for c, v in sorted(cov.items(), key=lambda x: x[1]):
        flag = "❌" if v < REQUIRED_COVERAGE else "  "
        print(f"    {flag} {c:<22} {v*100:>5.1f}%   {PIOTROSKI_INPUTS[c]}")
    if bad:
        raise SystemExit(
            "\n  ABORT: "
            + ", ".join(f"{c} at {v*100:.0f}%" for c, v in bad.items())
            + f" (need >={REQUIRED_COVERAGE*100:.0f}%).\n"
            "  Piotroski is not computable on this data. Building anyway would\n"
            "  emit piotroski=0 for every row, which reads as 'the factor never\n"
            "  fires' rather than 'the inputs are absent'. Collect balance-sheet\n"
            "  data before re-running.")
ROCE_LEVEL_HURDLE = 0.15
ROCE_CV_HURDLE = 0.30


def _safe(a, b):
    """a/b, or NaN — never an exception and never an inf that poisons a mean."""
    try:
        if b in (0, None) or b != b or a is None or a != a:
            return np.nan
        v = a / b
        return v if abs(v) < 1e6 else np.nan
    except Exception:
        return np.nan


def piotroski(cur: pd.Series, prv: pd.Series) -> dict:
    """9 tests from two consecutive filed years.

    Tests whose inputs are missing are SKIPPED and counted, never scored 0 — a
    missing gross-margin line is not evidence of a falling gross margin. Callers
    must read f_score against f_tested, not against a presumed 9.
    """
    t, got = {}, 0
    a0, a1 = cur.get("total_assets"), prv.get("total_assets")
    roa0, roa1 = _safe(cur.get("net_income"), a0), _safe(prv.get("net_income"), a1)
    cfo0 = cur.get("cfo")

    def add(k, cond, ok):
        nonlocal got
        if ok:
            t[k] = int(bool(cond)); got += 1
        else:
            t[k] = np.nan

    add("f1_roa_pos", roa0 and roa0 > 0, roa0 == roa0)
    add("f2_cfo_pos", cfo0 is not None and cfo0 == cfo0 and cfo0 > 0, cfo0 == cfo0)
    add("f3_roa_up", roa0 > roa1 if (roa0 == roa0 and roa1 == roa1) else False,
        roa0 == roa0 and roa1 == roa1)
    acc = _safe(cfo0, a0)
    add("f4_accruals", acc > roa0 if (acc == acc and roa0 == roa0) else False,
        acc == acc and roa0 == roa0)
    l0, l1 = _safe(_debt(cur), a0), _safe(_debt(prv), a1)
    add("f5_leverage_down", l0 < l1 if (l0 == l0 and l1 == l1) else False,
        l0 == l0 and l1 == l1)
    c0 = _safe(cur.get("current_assets"), cur.get("current_liabilities"))
    c1 = _safe(prv.get("current_assets"), prv.get("current_liabilities"))
    add("f6_curratio_up", c0 > c1 if (c0 == c0 and c1 == c1) else False,
        c0 == c0 and c1 == c1)
    s0, s1 = cur.get("shares"), prv.get("shares")
    add("f7_no_dilution", s0 <= s1 if (s0 and s1) else False, bool(s0) and bool(s1))
    g0 = _safe(cur.get("gross_profit"), cur.get("revenue"))
    g1 = _safe(prv.get("gross_profit"), prv.get("revenue"))
    add("f8_margin_up", g0 > g1 if (g0 == g0 and g1 == g1) else False,
        g0 == g0 and g1 == g1)
    at0, at1 = _safe(cur.get("revenue"), a0), _safe(prv.get("revenue"), a1)
    add("f9_turnover_up", at0 > at1 if (at0 == at0 and at1 == at1) else False,
        at0 == at0 and at1 == at1)

    score = int(np.nansum([v for v in t.values() if v == v]))
    return {"f_score": score, "f_tested": got, **t}


def _debt(r: pd.Series):
    """Total borrowings, whichever vocabulary the row uses.

    🔴 The two sources name the same concept differently, and the gate happens to
    select the one this builder was NOT reading. On the 99 gate-passing tickers:
    borrowings 81% populated, long_term_debt 8%. So `debt_reduction` computed
    from long_term_debt fired ZERO times across 707 firm-years — impossible for a
    test that should catch roughly half of them, and a missing field reading as
    "no company reduced debt".

        screener.in  ->  borrowings           (one combined line)
        yfinance     ->  long_term_debt + short_term_debt

    screener.in does not split long vs short, so the sum is the honest
    equivalent — not a coincidence of naming.
    """
    b = r.get("borrowings")
    if b is not None and b == b:
        return float(b)
    parts = [r.get("long_term_debt"), r.get("short_term_debt")]
    vals = [float(x) for x in parts if x is not None and x == x]
    return sum(vals) if vals else np.nan


def _equity(r: pd.Series):
    """Shareholders' funds, whichever vocabulary the row uses.

    screener.in itemises Equity Share Capital + Reserves; yfinance gives a single
    `equity`. Same quantity, and the gate-passing rows carry the former (89%)
    not the latter (8%).
    """
    e = r.get("equity")
    if e is not None and e == e:
        return float(e)
    ec, res = r.get("equity_capital"), r.get("reserves")
    if ec is not None and ec == ec and res is not None and res == res:
        return float(ec) + float(res)
    return np.nan


def roce_of(r: pd.Series) -> float:
    """EBIT / capital employed. CE = shareholders' funds + total borrowings."""
    eq, dbt = _equity(r), _debt(r)
    if eq != eq:
        return np.nan
    ce = eq + (dbt if dbt == dbt else 0.0)
    # Require positive shareholder funds: a negative-net-worth shell rescued into
    # positive CE by borrowings prints a flattering ROCE off a restructuring.
    return _safe(r.get("ebit"), ce) if eq > 0 and ce > 0 else np.nan


def build() -> pd.DataFrame:
    f = pd.read_parquet(FUND)
    f["ticker"] = f["ticker"].astype(str).str.upper()
    f["fy_end"] = pd.to_datetime(f["fy_end"], errors="coerce")
    f = f[f["fy_end"].notna()]

    # ── input-coverage gate ───────────────────────────────────────────────────
    # 🔴 The filter used to be `yrs>=5 AND cfo>=3` — it gated on CASH FLOW and
    # never checked the BALANCE SHEET. That selected 436 tickers with income and
    # cash-flow lines but no total_assets (present on 94 of 4,355 rows, 2%), then
    # computed a score that structurally needs one. Five of nine tests use
    # total_assets as a denominator (F1/F3/F4/F9) or the balance sheet (F5/F6),
    # so f_tested capped at 3, the `f_tested>=7` gate excluded everything, and
    # the panel reported piotroski=0 and debt_reduction=0 across 3,405 rows.
    #
    # Zero looked like a finding. It was a selection artefact — guaranteed by the
    # filter, not discovered by it. So coverage is now asserted UP FRONT, per
    # field, and a panel that cannot support the score refuses to build rather
    # than emitting confident zeros.
    _assert_input_coverage(f)

    g = f.groupby("ticker").agg(
        yrs=("fy_end", "nunique"),
        cfo=("cfo", lambda s: s.notna().sum()),
        # The denominator five of nine tests depend on. Selecting without it is
        # what caused the silent zero-fire.
        ta=("total_assets", lambda s: s.notna().sum()),
    )
    keep = g[(g["yrs"] >= MIN_YEARS) & (g["cfo"] >= MIN_CFO)
             & (g["ta"] >= MIN_BALANCE_SHEET)].index

    # Row-level coverage passing is not sufficient. A field can be 47% present
    # overall while almost no single ticker has the 3+ consecutive years the
    # score needs — coverage spread thinly across many tickers looks healthy in
    # aggregate and supports nothing. Observed 2026-07-21: total_assets 46.6% of
    # rows, but only 10 tickers cleared the per-ticker bar, and 2 survived the
    # return join. Abort on the count that actually determines testability.
    if len(keep) < MIN_TICKERS:
        raise SystemExit(
            f"\n  ABORT: only {len(keep)} tickers have >={MIN_YEARS}y history, "
            f">={MIN_CFO}y cfo and >={MIN_BALANCE_SHEET}y total_assets "
            f"(need >={MIN_TICKERS}).\n"
            "  Row-level coverage looked adequate; per-ticker depth does not.\n"
            "  A panel this thin cannot support factor combinations — collect\n"
            "  more balance-sheet history before re-running.")
    f = f[f["ticker"].isin(keep)].sort_values(["ticker", "fy_end"])
    print(f"  usable tickers: {len(keep)}  rows: {len(f):,}")

    # Annual only — a half-year fy_end mixed into a Piotroski delta compares
    # 12 months against 6 and manufactures a fake improvement.
    f["month"] = f["fy_end"].dt.month
    f = f[f["month"] == 3]
    print(f"  after keeping only March year-ends: {len(f):,} rows")

    f["roce"] = f.apply(roce_of, axis=1)
    rows = []
    for tk, grp in f.groupby("ticker"):
        grp = grp.sort_values("fy_end").reset_index(drop=True)
        for i in range(1, len(grp)):
            cur, prv = grp.loc[i], grp.loc[i - 1]
            hist = grp.loc[max(0, i - 4):i, "roce"].dropna()
            rec = {"ticker": tk, "fy_end": cur["fy_end"],
                   "visible_from": cur["fy_end"] + REPORTING_LAG,
                   "roce": cur["roce"],
                   "roce_avg3": grp.loc[max(0, i - 2):i, "roce"].dropna().mean(),
                   "roce_cv": (hist.std() / abs(hist.mean())
                               if len(hist) >= 3 and hist.mean() else np.nan)}
            rec.update(piotroski(cur, prv))
            d0 = _safe(_debt(cur), cur.get("total_assets"))
            d1 = _safe(_debt(prv), prv.get("total_assets"))
            rec["debt_ratio_falling"] = bool(d0 < d1) if (d0 == d0 and d1 == d1) else False
            rows.append(rec)
    p = pd.DataFrame(rows)

    p["roce_level"] = p["roce"] >= ROCE_LEVEL_HURDLE
    p["roce_stable"] = p["roce_cv"] <= ROCE_CV_HURDLE
    p["roce_improving"] = p["roce"] > p["roce_avg3"]
    p["roce_plus"] = p[["roce_level", "roce_stable", "roce_improving"]].sum(axis=1) >= 3
    p["piotroski"] = (p["f_score"] >= 7) & (p["f_tested"] >= 7)
    p["debt_reduction"] = p["debt_ratio_falling"]
    print(f"  scored firm-years: {len(p):,}")

    # ---- forward returns from the rebalance date -----------------------------
    # BSE-code bridge. screener.in keys 270 of 428 usable tickers by NUMERIC BSE
    # code (500003); the price panel keys by NSE alphabetic symbol. Without this
    # map, 63% of the scored universe silently drops out of the return join and
    # the panel looks four times thinner than it is — the sample-size problem
    # would then be blamed on collection rather than on a join.
    bse2nse = {}
    try:
        xl = pd.read_excel("/Users/umashankar/Library/Mobile Documents/"
                           "com~apple~CloudDocs/Desktop/xlsx/Stock_List_NSE_BSE_1.xlsx",
                           sheet_name="Stock List")
        xl.columns = [str(c).strip() for c in xl.columns]
        for _, r in xl.iterrows():
            bc, ns = r.get("BSE Code"), r.get("NSE Symbol")
            if pd.notna(bc) and pd.notna(ns):
                bse2nse[str(int(bc))] = str(ns).strip().upper()
        print(f"  BSE->NSE bridge: {len(bse2nse)} pairs")
    except Exception as e:
        print(f"  ⚠️  BSE bridge unavailable ({type(e).__name__}) — numeric codes will not join")

    px = pd.read_parquet(PRICE, columns=["Date", "Symbol", "Close"])
    px["Symbol"] = px["Symbol"].astype(str).str.upper()
    px["Date"] = pd.to_datetime(px["Date"])
    bench = (px[px["Symbol"] == BENCH].set_index("Date")["Close"].sort_index())
    if bench.empty:
        print(f"  ⚠️  benchmark {BENCH} absent — falling back to equal-weight universe mean")
        bench = px.groupby("Date")["Close"].mean().sort_index()
    wide = px.pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last").sort_index()

    out = []
    for year in range(2017, 2027):
        reb = pd.Timestamp(f"{year}-08-01")
        # ONLY fiscal years already public at the rebalance. This is the line
        # that makes the whole thing point-in-time.
        elig = p[(p["visible_from"] <= reb)].copy()
        if elig.empty:
            continue
        elig = elig.sort_values("fy_end").groupby("ticker").tail(1)   # most recent visible

        idx = wide.index
        i0 = idx.searchsorted(reb)
        if i0 >= len(idx):
            continue
        for hz, label in ((252, "xret_T+252d"), (126, "xret_T+126d")):
            i1 = min(i0 + hz, len(idx) - 1)
            if i1 <= i0:
                elig[label] = np.nan
                continue
            d0, d1 = idx[i0], idx[i1]
            r = (wide.loc[d1] / wide.loc[d0] - 1) * 100
            b = (bench.asof(d1) / bench.asof(d0) - 1) * 100
            key = elig["ticker"].map(lambda t: bse2nse.get(t, t))
            elig[label] = key.map(r) - b
        elig["year"] = year
        out.append(elig)

    panel = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    return panel


def main() -> int:
    p = build()
    if p.empty:
        print("  empty panel", file=sys.stderr)
        return 1
    OUT.parent.mkdir(exist_ok=True)
    p.to_parquet(OUT, index=False)
    print(f"\n  panel: {len(p):,} rows, {p['ticker'].nunique()} tickers, "
          f"{p['year'].nunique()} rebalances")
    print("  firms per rebalance:")
    for y, n in p.groupby("year").size().items():
        fr = p[p["year"] == y]["xret_T+252d"].notna().sum()
        print(f"     {y}: {n:4d} scored, {fr:4d} with 252d forward return")
    print(f"\n  → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
