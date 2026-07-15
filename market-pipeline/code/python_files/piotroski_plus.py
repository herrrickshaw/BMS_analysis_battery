#!/usr/bin/env python3
"""
piotroski_plus.py — the canonical 9-point Piotroski F-score + a 3-point ROCE block.

WHY ADD ROCE TO PIOTROSKI AT ALL
--------------------------------
Because they measure different things, and this repo has the evidence rather than
just the intuition: across 288 Indian companies, spearman corr(ROCE, F-score) was
only **+0.236**. They are complements, not substitutes.

    Piotroski asks:  is this company getting BETTER this year? (a delta measure —
                     8 of its 9 tests are year-on-year changes or sign tests)
    ROCE asks:       does this company earn well on the capital it employs? (a
                     level measure, and over ~5y, a durability measure)

A firm can score 8/9 on Piotroski while earning 4% on capital — a turnaround off a
weak base. Another can earn 30% on capital with F=3 — a great business having a bad
year. Piotroski alone cannot tell you the first company is a poor business; ROCE
alone cannot tell you the second is deteriorating. Hence Plus.

DESIGN: THE 9 STAY INTACT AND SEPARABLE
---------------------------------------
The F-score is a published, validated construct with 30 years of literature behind
it. It is NOT modified, reweighted or reordered here. The ROCE block is a separate
0-3 that is reported alongside, so:
  * f_score stays comparable to every published Piotroski result, and
  * you can measure whether the Plus block ADDS anything, instead of taking it on
    faith. Fold ROCE into the 9 and both properties are lost forever.

THE ROCE BLOCK (0-3) — level, stability, trend
----------------------------------------------
  +1  roce_ex_cash > 15%      LEVEL      — earns well on capital actually employed
  +1  roce_cv      < 0.30     STABILITY  — sustained, not a cyclical peak
  +1  roce_latest >= 5y mean  TREND      — not quietly deteriorating

Level uses the EX-CASH figure deliberately. ROCE = EBIT/(TA - CL) leaves cash in the
denominator, so a cash-rich company posts a depressed ROCE and looks inefficient at
nothing more than a strong balance sheet. Measured on this repo's India sample the
distortion is large AND uneven: large caps hold 20.0% of capital employed in cash vs
9.5% for small caps, so the raw figure penalises exactly the companies that need it
least. Ex-cash measures the operating engine rather than the treasury.

Stability earns a point of its own because a high ROCE from a cyclical peak and a
high ROCE sustained for five years are opposite signals that look identical in a
single year. On this repo's sample the split was sharp: 64% of large caps and 66% of
mid caps held CV < 0.30, against 43% of small caps.

WHAT THIS DOES NOT MEASURE
--------------------------
ROCE is an accounting-earnings measure (EBIT) over an accounting denominator. It
says nothing about cash flow, revenue growth, or the ability to meet short-term
obligations — Piotroski's CFO tests (2 and 4) carry the cash-quality signal, and the
liquidity gate carries tradeability. Piotroski Plus is a QUALITY filter. It is not a
liquidity filter and must not be used as one: run it BEHIND the liquidity gate, never
instead of it.

DATA
----
Everything comes from yfinance `.income_stmt` / `.balance_sheet` / `.cashflow` — the
statements, NOT `.info`. `.info` carries ratios and ebitda but neither EBIT nor
assets, which is why India's existing fundamentals routes (Trendlyne, screener.in,
yfinance .info) never produced an F-score or a ROCE.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import numpy as np

ROCE_LEVEL_HURDLE = 0.15     # 15% on capital employed
ROCE_CV_HURDLE = 0.30        # sd/mean across ~5y
F_MAX = 9
PLUS_MAX = 3


def _series(df, *names):
    """All years for the first matching statement line, newest first."""
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            v = df.loc[n].dropna()
            if len(v):
                return v.astype(float)
    return None


def _at(s, c):
    return float(s[c]) if s is not None and c in s.index else None


def score(ticker) -> dict:
    """Piotroski F (0-9) + ROCE block (0-3) for one yfinance Ticker.

    Returns f_score/f_tested and plus_score/plus_tested. Tests whose inputs are
    absent are SKIPPED and counted, never scored 0 — a missing gross-margin line
    is not evidence of a falling gross margin, and silently zeroing it would drag
    every affected company toward "weak". Callers should read f_score against
    f_tested, not against a presumed 9.
    """
    try:
        inc, bal, cfs = ticker.income_stmt, ticker.balance_sheet, ticker.cashflow
    except Exception:
        return {}

    ebit = _series(inc, "EBIT", "Operating Income", "OperatingIncome")
    ta = _series(bal, "Total Assets")
    cl = _series(bal, "Current Liabilities", "Total Current Liabilities")
    if ebit is None or ta is None or cl is None:
        return {}
    yrs = [c for c in ebit.index if c in ta.index and c in cl.index]
    if len(yrs) < 2:
        return {}
    y0, y1 = yrs[0], yrs[1]

    ni = _series(inc, "Net Income", "NetIncome")
    cfo = _series(cfs, "Operating Cash Flow", "Total Cash From Operating Activities")
    ca = _series(bal, "Current Assets", "Total Current Assets")
    ltd = _series(bal, "Long Term Debt", "LongTermDebt")
    rev = _series(inc, "Total Revenue", "Operating Revenue")
    gp = _series(inc, "Gross Profit", "GrossProfit")
    sh = _series(bal, "Ordinary Shares Number", "Share Issued",
                 "Common Stock Shares Outstanding")
    cash = _series(bal, "Cash Cash Equivalents And Short Term Investments",
                   "Cash And Cash Equivalents", "CashAndCashEquivalents")

    f, ftest, detail = 0, 0, {}

    def T(name, cond):
        nonlocal f, ftest
        if cond is None:
            detail[name] = None
            return
        ftest += 1
        f += 1 if cond else 0
        detail[name] = bool(cond)

    ta0, ta1 = _at(ta, y0), _at(ta, y1)
    ni0, ni1 = _at(ni, y0), _at(ni, y1)
    roa0 = ni0 / ta0 if None not in (ni0, ta0) and ta0 else None
    roa1 = ni1 / ta1 if None not in (ni1, ta1) and ta1 else None
    cfo0 = _at(cfo, y0)

    # ── PROFITABILITY (4) ───────────────────────────────────────────────────
    T("1_roa_positive", roa0 > 0 if roa0 is not None else None)
    T("2_cfo_positive", cfo0 > 0 if cfo0 is not None else None)
    T("3_roa_improving", roa0 > roa1 if None not in (roa0, roa1) else None)
    T("4_accruals_cfo_gt_roa",
      (cfo0 / ta0) > roa0 if None not in (cfo0, ta0, roa0) and ta0 else None)

    # ── LEVERAGE / LIQUIDITY / SOURCE OF FUNDS (3) ──────────────────────────
    l0 = _at(ltd, y0) / ta0 if _at(ltd, y0) is not None and ta0 else None
    l1 = _at(ltd, y1) / ta1 if _at(ltd, y1) is not None and ta1 else None
    T("5_leverage_falling", l0 < l1 if None not in (l0, l1) else None)
    cr0 = _at(ca, y0) / _at(cl, y0) if _at(ca, y0) is not None and _at(cl, y0) else None
    cr1 = _at(ca, y1) / _at(cl, y1) if _at(ca, y1) is not None and _at(cl, y1) else None
    T("6_current_ratio_rising", cr0 > cr1 if None not in (cr0, cr1) else None)
    s0, s1 = _at(sh, y0), _at(sh, y1)
    # tiny share-count drift is rounding/ESOP noise, not an equity raise
    T("7_no_dilution", s0 <= s1 * 1.01 if None not in (s0, s1) and s1 else None)

    # ── OPERATING EFFICIENCY (2) ────────────────────────────────────────────
    gm0 = _at(gp, y0) / _at(rev, y0) if _at(gp, y0) is not None and _at(rev, y0) else None
    gm1 = _at(gp, y1) / _at(rev, y1) if _at(gp, y1) is not None and _at(rev, y1) else None
    T("8_gross_margin_rising", gm0 > gm1 if None not in (gm0, gm1) else None)
    t0 = _at(rev, y0) / ta0 if _at(rev, y0) is not None and ta0 else None
    t1 = _at(rev, y1) / ta1 if _at(rev, y1) is not None and ta1 else None
    T("9_asset_turnover_rising", t0 > t1 if None not in (t0, t1) else None)

    # ── ROCE BLOCK (+3) ─────────────────────────────────────────────────────
    hist = [float(ebit[c]) / (float(ta[c]) - float(cl[c]))
            for c in yrs if (float(ta[c]) - float(cl[c])) > 0]
    ce0 = ta0 - _at(cl, y0) if ta0 is not None and _at(cl, y0) is not None else None
    roce = float(ebit[y0]) / ce0 if ce0 and ce0 > 0 else None
    cash0 = _at(cash, y0) or 0.0
    ce_ex = (ce0 - cash0) if ce0 else None
    roce_ex = float(ebit[y0]) / ce_ex if ce_ex and ce_ex > 0 else None
    cv = (float(np.std(hist)) / abs(float(np.mean(hist)))
          if len(hist) >= 3 and abs(np.mean(hist)) > 0.01 else None)

    p, ptest = 0, 0

    def P(name, cond):
        nonlocal p, ptest
        if cond is None:
            detail[name] = None
            return
        ptest += 1
        p += 1 if cond else 0
        detail[name] = bool(cond)

    P("10_roce_level", roce_ex > ROCE_LEVEL_HURDLE if roce_ex is not None else None)
    P("11_roce_stable", cv < ROCE_CV_HURDLE if cv is not None else None)
    P("12_roce_not_deteriorating",
      roce >= float(np.mean(hist)) if roce is not None and len(hist) >= 3 else None)

    return {"f_score": f if ftest else None, "f_tested": ftest,
            "plus_score": p if ptest else None, "plus_tested": ptest,
            "total": (f + p) if ftest and ptest else None,
            "roce": roce, "roce_ex_cash": roce_ex, "roce_cv": cv,
            "years": len(hist), **detail}


def verdict(r: dict) -> str:
    """Label. Requires BOTH blocks to be well-measured — a company that is strong
    on Piotroski and unmeasured on ROCE is not a Piotroski Plus pass, it is an
    unknown, and saying so is the entire point of the Plus block."""
    if not r or r.get("f_score") is None or r.get("plus_score") is None:
        return "INSUFFICIENT_DATA"
    if r["f_tested"] < 6 or r["plus_tested"] < 2:
        return "INSUFFICIENT_DATA"
    f, p = r["f_score"], r["plus_score"]
    fs = f / r["f_tested"] * F_MAX          # scale to a 9-point frame when tests were skipped
    if fs >= 7 and p == 3:
        return "STRONG"          # improving AND a durable, efficient business
    if fs >= 7 and p >= 2:
        return "GOOD"
    if fs >= 7:
        return "IMPROVING_WEAK_BUSINESS"    # F says better, ROCE says off a poor base
    if p == 3 and fs >= 4:
        return "QUALITY_NOT_IMPROVING"      # great business, flat/deteriorating year
    if fs <= 3 and p <= 1:
        return "AVOID"
    return "MIXED"
