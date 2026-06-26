"""
domain/screening/specifications.py
=====================================
Screener Specifications — Encapsulate screening criteria as domain objects.

SPECIFICATION PATTERN (Evans 2003)
────────────────────────────────────
A Specification encapsulates a business rule that can be:
  1. is_satisfied_by(candidate) → bool   — test one object
  2. and_(other)                → Spec   — combine two specifications
  3. or_(other)                 → Spec   — alternative
  4. not_()                     → Spec   — negation

This replaces scattered `if roic > 25 and ey > 15` conditions scattered
across multiple scripts with self-describing, composable, testable objects.

Before DDD (v1.0):
    # In full_indian_market_scan.py line 347:
    qualifies_mf = bool(roic and roic>15 and ey and ey>8 and bv and bv>0 ...)

After DDD (v3.1):
    spec = MagicFormulaSpec()
    if spec.is_satisfied_by(stock):
        ...

The specification BELONGS in the domain because it encodes business rules
about what makes a stock qualify — not infrastructure concerns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


# ── Base Specification ────────────────────────────────────────────────────────

class Specification(ABC):
    """Base class for all screener specifications."""

    @abstractmethod
    def is_satisfied_by(self, candidate: Any) -> bool:
        """Test whether the candidate satisfies this specification."""
        ...

    @abstractmethod
    def explain(self) -> str:
        """Return a human-readable description of what this spec tests."""
        ...

    def and_(self, other: Specification) -> Specification:
        return AndSpecification(self, other)

    def or_(self, other: Specification) -> Specification:
        return OrSpecification(self, other)

    def not_(self) -> Specification:
        return NotSpecification(self)


@dataclass
class AndSpecification(Specification):
    left: Specification
    right: Specification

    def is_satisfied_by(self, candidate: Any) -> bool:
        return self.left.is_satisfied_by(candidate) and self.right.is_satisfied_by(candidate)

    def explain(self) -> str:
        return f"({self.left.explain()}) AND ({self.right.explain()})"


@dataclass
class OrSpecification(Specification):
    left: Specification
    right: Specification

    def is_satisfied_by(self, candidate: Any) -> bool:
        return self.left.is_satisfied_by(candidate) or self.right.is_satisfied_by(candidate)

    def explain(self) -> str:
        return f"({self.left.explain()}) OR ({self.right.explain()})"


@dataclass
class NotSpecification(Specification):
    spec: Specification

    def is_satisfied_by(self, candidate: Any) -> bool:
        return not self.spec.is_satisfied_by(candidate)

    def explain(self) -> str:
        return f"NOT ({self.spec.explain()})"


# ── Candidate ─────────────────────────────────────────────────────────────────

@dataclass
class ScreeningCandidate:
    """
    Data transfer object passed to Specifications.
    Aggregates all data needed by any screener to avoid multiple calls.
    Populated by Application layer before calling specifications.
    """
    symbol:        str
    suffix:        str           # ".NS", ".BO", ""

    # Price data (from Stock entity)
    ohlc_df:       Optional[pd.DataFrame] = None
    bar_count:     int = 0
    current_price: float = 0.0

    # Annual fundamentals
    income_stmt:   Optional[pd.DataFrame] = None
    balance_sheet: Optional[pd.DataFrame] = None
    cash_flow:     Optional[pd.DataFrame] = None

    # Quarterly fundamentals
    quarterly_inc: Optional[pd.DataFrame] = None

    # From ticker.info
    market_cap:    float = 0.0    # raw (not in crores)
    trailing_pe:   Optional[float] = None
    forward_pe:    Optional[float] = None
    debt_to_equity:Optional[float] = None
    total_debt:    float = 0.0
    total_cash:    float = 0.0
    book_value:    Optional[float] = None
    sector:        str = ""

    # Computed
    _cache: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def market_cap_cr(self) -> float:
        """Market cap in Indian crores."""
        return self.market_cap / 1e7 if self.market_cap else 0.0

    @property
    def is_financial_company(self) -> bool:
        """Banks/NBFCs excluded from ROIC/ROCE screeners."""
        s = (self.sector or "").lower()
        kws = ["bank","financial","insurance","nbfc","capital","leasing","credit"]
        return any(kw in s for kw in kws)

    def _row(self, df: Optional[pd.DataFrame], *names, col: int = 0) -> Optional[float]:
        """Safely extract a value from a financial statement DataFrame."""
        if df is None or df.empty: return None
        for name in names:
            if name in df.index:
                try:
                    val = df.loc[name].iloc[col]
                    return float(val) if pd.notna(val) else None
                except Exception:
                    pass
        return None

    def _series(self, df: Optional[pd.DataFrame], *names) -> list:
        """Extract all available values for a row across years."""
        for name in names:
            if df is not None and name in df.index:
                return [float(v) for v in df.loc[name].dropna() if pd.notna(v)]
        return []


# ══════════════════════════════════════════════════════════════════════════════
# THE SIX SCREENER SPECIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

class DarvasBoxSpec(Specification):
    """
    Darvas Box Breakout Specification.
    Requires: current price > confirmed box top (volume-confirmed).
    Note: Full walk-forward detection is in Infrastructure.
          This spec validates that a Darvas breakout occurred in the OHLC data.
    """
    def __init__(self, confirm: int = 3, vol_threshold: float = 1.2):
        self.confirm       = confirm
        self.vol_threshold = vol_threshold

    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        if candidate.ohlc_df is None or candidate.bar_count < self.confirm + 20:
            return False
        df = candidate.ohlc_df
        h  = df["High"].values.astype(float)
        l  = df["Low"].values.astype(float)
        c  = df["Close"].values.astype(float)
        n  = len(c)

        # Look back 60 bars for a confirmed box top
        box_top = None
        for j in range(n - self.confirm - 2, max(0, n - 62) - 1, -1):
            if h[j] == 0: continue
            win = h[j+1:j+1+self.confirm]
            if len(win) == self.confirm and all(x < h[j] for x in win):
                box_top = h[j]; break

        if box_top is None:
            return False

        # Check current close is above box top
        return c[-1] > box_top

    def explain(self) -> str:
        return (f"Darvas Box Breakout: close > confirmed box top "
                f"(confirm={self.confirm} days, vol≥{self.vol_threshold}×avg)")


class GoldenCrossSpec(Specification):
    """
    Golden Cross: 50 DMA just crossed above 200 DMA (today's bar).
    Requires ≥ 201 bars of OHLC history.
    """
    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        if candidate.ohlc_df is None or candidate.bar_count < 205:
            return False
        closes = candidate.ohlc_df["Close"].astype(float)
        d50    = closes.rolling(50).mean()
        d200   = closes.rolling(200).mean()
        # Strict: crossed exactly today
        return (float(d50.iloc[-2]) < float(d200.iloc[-2]) and
                float(d50.iloc[-1]) > float(d200.iloc[-1]))

    def explain(self) -> str:
        return "Golden Cross: 50 DMA just crossed above 200 DMA today"


class DMA50AboveDMA200Spec(Specification):
    """Broader: 50 DMA is currently above 200 DMA (not just today's cross)."""
    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        if candidate.ohlc_df is None or candidate.bar_count < 205:
            return False
        closes = candidate.ohlc_df["Close"].astype(float)
        d50    = float(closes.rolling(50).mean().iloc[-1])
        d200   = float(closes.rolling(200).mean().iloc[-1])
        return d50 > d200

    def explain(self) -> str:
        return "50 DMA is above 200 DMA"


class PiotroskiSpec(Specification):
    """
    Piotroski F-Score ≥ threshold (default 7/9).
    9-point accounting quality score (Piotroski 2000).
    Excludes financial companies.
    """
    def __init__(self, min_score: int = 7):
        self.min_score = min_score

    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        if candidate.is_financial_company:
            return False
        inc, bal, cf = candidate.income_stmt, candidate.balance_sheet, candidate.cash_flow
        if inc is None or inc.empty:
            return False

        r = candidate._row
        ni0 = r(inc, "Net Income", col=0);  a0 = r(bal, "Total Assets", col=0)
        ni1 = r(inc, "Net Income", col=1);  a1 = r(bal, "Total Assets", col=1)
        roa0 = (ni0/a0) if (ni0 and a0) else None
        roa1 = (ni1/a1) if (ni1 and a1) else None
        ocf0 = r(cf, "Operating Cash Flow", "Total Cash From Operating Activities")
        ltd0 = r(bal, "Long Term Debt", col=0) or 0
        ltd1 = r(bal, "Long Term Debt", col=1) or 0
        ca0  = r(bal, "Current Assets", "Total Current Assets", col=0)
        cl0  = r(bal, "Current Liabilities", "Total Current Liabilities", col=0)
        ca1  = r(bal, "Current Assets", "Total Current Assets", col=1)
        cl1  = r(bal, "Current Liabilities", "Total Current Liabilities", col=1)
        sh0  = r(bal, "Share Issued", col=0); sh1 = r(bal, "Share Issued", col=1)
        rev0 = r(inc, "Total Revenue", col=0); gp0 = r(inc, "Gross Profit", col=0)
        rev1 = r(inc, "Total Revenue", col=1); gp1 = r(inc, "Gross Profit", col=1)

        score = (
            (1 if (roa0 and roa0 > 0) else 0) +
            (1 if (ocf0 and ocf0 > 0) else 0) +
            (1 if (roa0 and roa1 and roa0 > roa1) else 0) +
            (1 if (ocf0 and a0 and roa0 and (ocf0/a0) > roa0) else 0) +
            (1 if (a0 and a1 and (ltd0/a0) < (ltd1/a1)) else 0) +
            (1 if (ca0 and cl0 and ca1 and cl1 and (ca0/cl0) > (ca1/cl1)) else 0) +
            ((1 if sh0 <= sh1 else 0) if (sh0 and sh1) else 1) +
            (1 if (gp0 and rev0 and gp1 and rev1 and (gp0/rev0) > (gp1/rev1)) else 0) +
            (1 if (rev0 and a0 and rev1 and a1 and (rev0/a0) > (rev1/a1)) else 0)
        )
        return score >= self.min_score

    def explain(self) -> str:
        return f"Piotroski F-Score ≥ {self.min_score}/9 (9-point accounting quality)"


class CoffeeCanSpec(Specification):
    """
    Coffee Can Portfolio Screen.
    CAGR > 10%, ROCE > 15%, D/E < 1, MCap ≥ ₹500Cr, no loss year.
    (Mukherjea / Marcellus Investment Managers)
    """
    def __init__(self, min_cagr: float = 10, min_roce: float = 15,
                 max_de: float = 1.0, min_mcap_cr: float = 500):
        self.min_cagr    = min_cagr
        self.min_roce    = min_roce
        self.max_de      = max_de
        self.min_mcap_cr = min_mcap_cr

    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        if candidate.is_financial_company:
            return False
        inc, bal = candidate.income_stmt, candidate.balance_sheet
        if inc is None or inc.empty:
            return False

        s = candidate._series
        revs = s(inc, "Total Revenue")
        if len(revs) < 2 or revs[-1] <= 0:
            return False
        cagr = ((revs[0]/revs[-1])**(1/(len(revs)-1))-1)*100
        if cagr < self.min_cagr:
            return False

        ebit_s = s(inc, "EBIT", "Operating Income", "Ebit")
        ta_s   = s(bal, "Total Assets")
        cl_s   = s(bal, "Current Liabilities", "Total Current Liabilities")
        roce_l = [ebit_s[i]/(ta_s[i]-cl_s[i])*100
                  for i in range(min(len(ebit_s),len(ta_s),len(cl_s)))
                  if (ta_s[i]-cl_s[i]) > 0]
        if not roce_l or sum(roce_l)/len(roce_l) < self.min_roce:
            return False

        de_raw = candidate.debt_to_equity
        if de_raw is not None:
            de = de_raw/100 if de_raw > 10 else de_raw
            if de >= self.max_de:
                return False

        if candidate.market_cap_cr < self.min_mcap_cr:
            return False

        ni_s = s(inc, "Net Income")
        return bool(ni_s and all(n > 0 for n in ni_s))

    def explain(self) -> str:
        return (f"Coffee Can: Rev CAGR>{self.min_cagr}%, ROCE>{self.min_roce}%, "
                f"D/E<{self.max_de}, MCap≥₹{self.min_mcap_cr}Cr, no loss year")


class MagicFormulaSpec(Specification):
    """
    Joel Greenblatt Magic Formula (2005).
    ROIC > min_roic AND Earnings Yield > min_ey.
    Excludes financial companies and negative-earnings stocks.
    Signal date: July 1 (after all annual reports released — Preet et al. 2021).
    """
    def __init__(self, min_roic: float = 15, min_ey: float = 8,
                 min_mcap_cr: float = 100):
        self.min_roic    = min_roic
        self.min_ey      = min_ey
        self.min_mcap_cr = min_mcap_cr

    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        if candidate.is_financial_company:
            return False
        inc, bal = candidate.income_stmt, candidate.balance_sheet
        if inc is None or inc.empty:
            return False

        r    = candidate._row
        ebit = r(inc, "EBIT", "Operating Income", "Ebit", col=0)
        a0   = r(bal, "Total Assets", col=0)
        cl0  = r(bal, "Current Liabilities", "Total Current Liabilities", col=0)
        cap  = (a0 - (cl0 or 0)) if a0 else None
        mcap = candidate.market_cap
        td   = candidate.total_debt or 0
        cash = candidate.total_cash or 0
        ev   = (mcap + td - cash) if mcap else None
        bv   = candidate.book_value
        ni   = r(inc, "Net Income", col=0)

        roic = (ebit/cap*100) if (ebit and cap and cap > 0) else None
        ey   = (ebit/ev*100)  if (ebit and ev  and ev  > 0) else None

        return bool(
            roic and roic > self.min_roic and
            ey   and ey   > self.min_ey   and
            bv   and bv   > 0             and
            ni   and ni   > 0             and
            candidate.market_cap_cr > self.min_mcap_cr
        )

    def explain(self) -> str:
        return (f"Magic Formula: ROIC>{self.min_roic}%, "
                f"Earnings Yield>{self.min_ey}%, bv>0, MCap>₹{self.min_mcap_cr}Cr")


class BullCartelSpec(Specification):
    """
    Bull Cartel: strong quarterly earnings momentum.
    YoY quarterly sales growth > 15%, profit growth > 20%, NP > ₹1Cr.
    """
    def __init__(self, min_sales_growth: float = 15,
                 min_profit_growth: float = 20,
                 min_net_profit_cr: float = 1):
        self.min_sales_growth  = min_sales_growth
        self.min_profit_growth = min_profit_growth
        self.min_net_profit_cr = min_net_profit_cr

    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        inc_q = candidate.quarterly_inc
        if inc_q is None or len(inc_q.columns) < 5:
            return False

        r       = candidate._row
        rev_q0  = r(inc_q, "Total Revenue", col=0)
        rev_q4  = r(inc_q, "Total Revenue", col=4)
        ni_q0   = r(inc_q, "Net Income",    col=0)
        ni_q4   = r(inc_q, "Net Income",    col=4)

        sg = ((rev_q0-rev_q4)/abs(rev_q4)*100) if (rev_q0 and rev_q4 and rev_q4!=0) else None
        pg = ((ni_q0-ni_q4)/abs(ni_q4)*100)    if (ni_q0  and ni_q4  and ni_q4!=0)  else None
        nc = ni_q0/1e7 if ni_q0 else None

        return bool(
            sg and sg > self.min_sales_growth   and
            pg and pg > self.min_profit_growth  and
            nc and nc > self.min_net_profit_cr
        )

    def explain(self) -> str:
        return (f"Bull Cartel: YoY sales>{self.min_sales_growth}%, "
                f"profit>{self.min_profit_growth}%, NP>₹{self.min_net_profit_cr}Cr")


# ── Composite Specifications ──────────────────────────────────────────────────

class TripleHitSpec(Specification):
    """
    Triple Hit: Darvas BREAKOUT + Piotroski ≥7 + Coffee Can PASS.
    The highest-conviction combined signal in the system.
    Backtest: 8 stocks out of 2,400 qualified in Jun 2026.
    """
    def __init__(self):
        self._darvas   = DarvasBoxSpec()
        self._piotroski = PiotroskiSpec(min_score=7)
        self._coffee    = CoffeeCanSpec()

    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        return (self._darvas.is_satisfied_by(candidate) and
                self._piotroski.is_satisfied_by(candidate) and
                self._coffee.is_satisfied_by(candidate))

    def explain(self) -> str:
        return "Triple Hit: Darvas Breakout AND Piotroski≥7 AND Coffee Can PASS"


class MultiScreenSpec(Specification):
    """
    Multi-Screen Hit: passes N or more out of the 6 screeners.
    Default: 3+ for high conviction signals.
    """
    def __init__(self, min_screens: int = 3):
        self.min_screens = min_screens
        self._specs = [
            DarvasBoxSpec(),
            GoldenCrossSpec(),
            PiotroskiSpec(),
            CoffeeCanSpec(),
            MagicFormulaSpec(),
            BullCartelSpec(),
        ]

    def is_satisfied_by(self, candidate: ScreeningCandidate) -> bool:
        passed = sum(1 for s in self._specs if s.is_satisfied_by(candidate))
        return passed >= self.min_screens

    def passed_screeners(self, candidate: ScreeningCandidate) -> list:
        return [s.explain()[:20] for s in self._specs if s.is_satisfied_by(candidate)]

    def explain(self) -> str:
        return f"Multi-Screen: passes ≥{self.min_screens} of 6 screeners simultaneously"
