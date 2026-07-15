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

# ── weights ───────────────────────────────────────────────────────────────────
# Every test is a 0/1 pass, and the weight decides what a pass is WORTH. Weight
# vectors are how one scoring engine filters for different kinds of company:
# the tests never change, only what you are willing to pay for.
#
# score() returns the raw booleans; weights are applied afterwards by weigh().
# That separation is deliberate and load-bearing for backtesting — statements are
# fetched and tested ONCE, then any number of weight vectors are swept over the
# cached result. Folding weights into score() would mean a network round-trip per
# vector and make a sweep impractical.
#
# TEST_NAMES is the canonical order. Anything reading these dicts should key by
# name, never by position.
TEST_NAMES = (
    "1_roa_positive", "2_cfo_positive", "3_roa_improving", "4_accruals_cfo_gt_roa",
    "5_leverage_falling", "6_current_ratio_rising", "7_no_dilution",
    "8_gross_margin_rising", "9_asset_turnover_rising",
    "10_roce_level", "11_roce_stable", "12_roce_not_deteriorating",
)

PIOTROSKI_TESTS = TEST_NAMES[:9]
ROCE_TESTS = TEST_NAMES[9:]

# Presets are hypotheses about what matters, not settings. Each is justified by
# what it would have picked or rejected on this repo's own India sample.
PRESETS: dict[str, dict[str, float]] = {
    # Canonical: reproduces Piotroski 9 + ROCE 3 exactly. The control.
    "canonical": {n: 1.0 for n in TEST_NAMES},

    # QUALITY — durable compounders. Pays for earning well on capital and, more,
    # for earning it CONSISTENTLY.
    #
    # WHY STABILITY OUTWEIGHS LEVEL (2.0 vs 3.5), which looks backwards:
    # A LINEAR WEIGHTED SUM CANNOT EXPRESS "NEEDS BOTH" — that is a conjunction,
    # and no choice of weights turns a sum into an AND. Measured, not assumed:
    # with level and stability both at 3.0, SUZLON (ROCE 32.1%, CV 0.87) and NTPC
    # (ROCE 9.9%, CV 0.04) TIED at 57.7 — each banked one 3.0 and the vector could
    # not tell "a return you cannot rely on" from "a return capped by regulation".
    # Both scored F=7.0, so Piotroski could not either.
    # Tilting toward stability breaks the tie in the direction that reflects what
    # the level/stability split is FOR: a repeatable 10% is evidence of management
    # skill, an erratic 32% is usually evidence of a cycle. Callers who genuinely
    # need the conjunction should filter on the raw booleans
    # (10_roce_level AND 11_roce_stable), not hunt for magic weights.
    "quality": {**{n: 0.5 for n in PIOTROSKI_TESTS},
                "1_roa_positive": 1.0, "2_cfo_positive": 1.0,
                "10_roce_level": 2.0, "11_roce_stable": 3.5,
                "12_roce_not_deteriorating": 1.5},

    # TURNAROUND — improving off a weak base. Pays for the deltas and for cash
    # quality; explicitly does NOT require a high ROCE level, because demanding
    # one defines the whole category out of existence. Keeps stability at zero:
    # a turnaround is BY DEFINITION unstable, so penalising CV here would be
    # incoherent. This is the vector that would surface TATASTEEL/BHEL — which
    # "quality" correctly rejects. Neither vector is wrong; they hunt different game.
    "turnaround": {**{n: 0.5 for n in TEST_NAMES},
                   "3_roa_improving": 3.0, "4_accruals_cfo_gt_roa": 2.0,
                   "2_cfo_positive": 2.0, "9_asset_turnover_rising": 2.0,
                   "8_gross_margin_rising": 2.0,
                   "10_roce_level": 0.0, "11_roce_stable": 0.0,
                   "12_roce_not_deteriorating": 2.0},

    # SAFETY — balance-sheet defence. Pays for falling leverage, rising current
    # ratio, no dilution, positive cash, and a ROCE that does not swing. Note this
    # is the one preset where a LOW absolute return is acceptable: a regulated
    # utility (NTPC, CV 0.04) is exactly what this vector should find.
    "safety": {**{n: 0.5 for n in TEST_NAMES},
               "5_leverage_falling": 3.0, "6_current_ratio_rising": 2.0,
               "7_no_dilution": 2.0, "2_cfo_positive": 2.0,
               "11_roce_stable": 3.0, "10_roce_level": 0.5},
}


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

    Thin wrapper around score_from_statements() — see that function for the full
    contract. Exists so callers that only have a Ticker object (not pre-fetched
    frames) don't need to know the attribute names.
    """
    try:
        inc, bal, cfs = ticker.income_stmt, ticker.balance_sheet, ticker.cashflow
    except Exception:
        return {}
    return score_from_statements(inc, bal, cfs)


def score_from_statements(inc, bal, cfs) -> dict:
    """Piotroski F (0-9) + ROCE block (0-3) from already-fetched income_stmt /
    balance_sheet / cashflow DataFrames (yfinance's own frame shape: rows are line
    items, columns are period-end dates, newest first).

    Split out from score() so a caller that fetches statements itself — e.g. via a
    fallback chain across yfinance's inconsistent attribute names across versions
    ("income_stmt" vs "financials") — can score from what it already has instead
    of triggering a second, possibly-different fetch through a live Ticker. This
    is the fix for a real bug: full_us_market_scan.py had its OWN inline 9-test
    formula that scored a MISSING field as a FAILED test (0), not a skipped one —
    so any stock with a sparse yfinance balance sheet floored at f_score=1.0
    regardless of its actual fundamentals (proven on COLL: SEC EDGAR shows FY2025
    net income $62.9M, CFO $329.3M, EBIT $179.6M, 5 straight years of revenue
    growth — plainly not a 1/9 company). Routing both pipelines through this one
    function, with its `_ran()` skip-not-fail discipline, fixes it at the source
    instead of patching the symptom in two places that will drift apart again.

    Returns f_score/f_tested and plus_score/plus_tested. Tests whose inputs are
    absent are SKIPPED and counted, never scored 0 — a missing gross-margin line
    is not evidence of a falling gross margin, and silently zeroing it would drag
    every affected company toward "weak". Callers should read f_score against
    f_tested, not against a presumed 9.
    """
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


def _ran(v) -> bool:
    """Did this test actually run?

    NOT simply `v is not None`. A scored result round-tripped through CSV/parquet
    (which is exactly what a backtest sweep does) comes back with skipped tests as
    float NaN, and NaN fails an `is None` check while being TRUTHY. That silently
    counted every skipped test as a PASS — it broke the canonical control on 33 of
    118 stocks before this guard existed. Strings are the same trap from CSV:
    bool("False") is True.
    """
    if v is None:
        return False
    if isinstance(v, float) and v != v:      # NaN
        return False
    if isinstance(v, str):
        return v.strip().lower() in ("true", "false", "1", "0")
    return True


def _passed(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1")
    return bool(v)


def weigh(r: dict, weights: dict[str, float] | str = "canonical") -> dict:
    """Apply a weight vector to an ALREADY-SCORED result. No network, no refetch.

    Pass a preset name or a {test_name: weight} dict. Unlisted tests weigh 0.

    NORMALISATION — the part that is easy to get wrong. Tests whose inputs were
    missing are skipped (None), not failed. If we divided the earned weight by the
    FULL vector's weight, every company missing a gross-margin line would score
    low for a data gap rather than a business fact — and that gap is not random:
    RELIANCE has no Gross Profit line, so a naive denominator would systematically
    mark down exactly the large caps. So the denominator is the weight of the tests
    that ACTUALLY RAN, making `pct` comparable across companies with different
    coverage.

    Returns:
      raw        earned weight
      possible   weight of tests that ran (the honest denominator)
      pct        raw/possible, 0-100 — THE comparable figure
      coverage   possible/total_vector_weight — how much of the vector was testable.
                 Low coverage means a high pct is thin, so it is reported, never
                 folded into pct. Filter on it explicitly.
    """
    if isinstance(weights, str):
        if weights not in PRESETS:
            raise KeyError(f"unknown preset {weights!r}; have {sorted(PRESETS)}")
        weights = PRESETS[weights]
    if not r:
        return {"raw": None, "possible": None, "pct": None, "coverage": None}

    raw = possible = 0.0
    for name, w in weights.items():
        v = r.get(name)
        if not _ran(v):          # test did not run — excluded from BOTH sides
            continue
        possible += w
        if _passed(v):
            raw += w
    total = sum(weights.values()) or 1.0
    if possible <= 0:
        return {"raw": 0.0, "possible": 0.0, "pct": None, "coverage": 0.0}
    return {"raw": raw, "possible": possible,
            "pct": raw / possible * 100, "coverage": possible / total}


def sweep(r: dict, presets=None) -> dict[str, float]:
    """pct under every preset, for one scored company. Cheap: pure arithmetic."""
    return {p: weigh(r, p)["pct"] for p in (presets or PRESETS)}


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
