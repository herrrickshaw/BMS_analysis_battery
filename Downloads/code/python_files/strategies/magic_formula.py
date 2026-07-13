#!/usr/bin/env python3
# Magic Formula — Joel Greenblatt: rank by Earnings Yield (EBIT/EV) + Return on
# Capital (EBIT/(Net WC + Net Fixed Assets)). High of both = cheap & good.
from __future__ import annotations
from .base import StockData, Result, safe

META = {"name": "Magic Formula", "slug": "magic_formula", "category": "fundamental",
        "description": "Greenblatt: high earnings yield (EBIT/EV) AND high return on "
                       "capital. Ranked composite of the two.",
        "needs": "fundamentals"}
# Thresholds reconciled with full_us_market_scan.py / full_indian_market_scan.py
# (sourced from screener.in's own Magic Formula screen) rather than this module's
# previous ad hoc, uncited EY>=8%/ROC>=15% — those let a stock pass here that
# every production scan's Magic Formula would reject, or vice versa.
EY_MIN = 15.0    # % earnings yield floor for a standalone pass
ROC_MIN = 25.0   # % return on capital floor


def screen(s: StockData) -> Result | None:
    g = s.f
    ebit = safe(g("ebit"))
    ev = safe(g("enterprise_value"))
    roc = safe(g("roc")) or safe(g("roce"))
    ey = safe(g("earnings_yield"))
    book_value = safe(g("book_value"))
    if ey is None and ebit is not None and ev and ev != 0:
        ey = ebit / ev * 100
    if ey is None or roc is None:
        return None
    # book value > 0 gate matches the production scans (excludes negative/zero
    # book-value names where ROC/EY can be numerically meaningless)
    passed = ey >= EY_MIN and roc >= ROC_MIN and (book_value is None or book_value > 0)
    # composite score: higher EY + higher ROC rank better (sum, higher=better)
    return Result(s.symbol, META["slug"], passed=passed,
                  score=round(ey + roc, 2),
                  metrics={"EarningsYield%": round(ey, 2), "ROC%": round(roc, 2),
                           "BookValue": book_value},
                  note="cheap+quality" if passed else "")
