"""
application/commands/run_daily_scan.py
========================================
Application Layer — CQRS Command + Handler.

CQRS (Command Query Responsibility Segregation):
  Commands change state, return nothing (or a result ID).
  Queries read state, change nothing.

RunDailyScanCommand orchestrates the full daily scan:
  1. Fetch live market context (regime, VIX, FII/DII)
  2. Get all NSE/BSE symbols
  3. Load OHLC from cache (incremental update — only new bars)
  4. Run all 6 screener specifications against each candidate
  5. Publish domain events for each signal
  6. Persist results via repositories
  7. Trigger report generation

The handler does NOT contain business logic — it orchestrates.
Business logic lives in Domain Specifications and Entities.
Infrastructure concerns live in Repository implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from domain.market_data.repositories import (
    IFundamentalsRepository,
    ILiveMarketDataService,
    IMarketIndexRepository,
    IStockRepository,
)
from domain.screening.specifications import (
    BullCartelSpec,
    CoffeeCanSpec,
    DarvasBoxSpec,
    GoldenCrossSpec,
    MagicFormulaSpec,
    MultiScreenSpec,
    PiotroskiSpec,
    ScreeningCandidate,
    TripleHitSpec,
)
from domain.shared.events import (
    BreakoutDetected,
    MarketRegimeChanged,
    MultiScreenHitDetected,
    ScreenerRunCompleted,
    get_event_bus,
)
from domain.shared.value_objects import Exchange, Ticker


# ── Command ───────────────────────────────────────────────────────────────────

@dataclass
class RunDailyScanCommand:
    """
    Command to run the full daily scan.
    Immutable intent — describes WHAT to do, not HOW.
    """
    markets:    List[str]  = field(default_factory=lambda: ["IN", "US"])
    top:        int        = 0          # 0 = full universe
    workers:    int        = 8
    run_scans:  bool       = True       # False = OHLC only, no fundamentals
    requested_at: datetime = field(default_factory=datetime.utcnow)


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class DailyScanResult:
    """Result returned by the command handler."""
    total_scanned:       int = 0
    darvas_breakouts:    int = 0
    golden_crosses:      int = 0
    piotroski_strong:    int = 0
    coffee_can_pass:     int = 0
    magic_formula_pass:  int = 0
    bull_cartel_pass:    int = 0
    triple_hits:         int = 0
    multi_screen_hits:   int = 0
    regime:              str = "UNKNOWN"
    vix:                 float = 0.0
    duration_sec:        float = 0.0
    output_path:         str = ""
    errors:              List[str] = field(default_factory=list)


# ── Command Handler ───────────────────────────────────────────────────────────

class RunDailyScanHandler:
    """
    Handles RunDailyScanCommand by orchestrating the domain and infrastructure.

    Dependencies injected via constructor (Dependency Inversion Principle):
      - IStockRepository        — abstracts yfinance/Parquet data access
      - IMarketIndexRepository  — abstracts index data
      - ILiveMarketDataService  — abstracts nsepython live data
      - IFundamentalsRepository — abstracts yfinance financial statements
      - IReportWriter           — abstracts Excel / email output (injected separately)

    The handler knows NOTHING about yfinance, Parquet, or pandas.
    It only speaks in domain terms (Stock, Ticker, Specification).
    """

    def __init__(
        self,
        stock_repo:       IStockRepository,
        index_repo:       IMarketIndexRepository,
        live_service:     ILiveMarketDataService,
        fund_repo:        IFundamentalsRepository,
        report_writer     = None,   # IReportWriter
    ):
        self._stock_repo   = stock_repo
        self._index_repo   = index_repo
        self._live_service = live_service
        self._fund_repo    = fund_repo
        self._report_writer = report_writer
        self._bus          = get_event_bus()

        # Pre-build specifications (stateless, reusable)
        self._specs = {
            "darvas":       DarvasBoxSpec(confirm=3, vol_threshold=1.2),
            "golden_cross": GoldenCrossSpec(),
            "piotroski":    PiotroskiSpec(min_score=7),
            "coffee_can":   CoffeeCanSpec(),
            "magic_formula": MagicFormulaSpec(),
            "bull_cartel":  BullCartelSpec(),
        }
        self._triple_spec = TripleHitSpec()
        self._multi_spec  = MultiScreenSpec(min_screens=3)

    def handle(self, command: RunDailyScanCommand) -> DailyScanResult:
        """Execute the daily scan command."""
        t0     = datetime.utcnow()
        result = DailyScanResult()

        # ── Step 1: Live market context ────────────────────────────────────────
        print("  [DailyScan] Step 1 — Live market context …")
        try:
            vix     = self._live_service.get_vix() or 15.0
            result.vix = vix
            nifty   = self._index_repo.get_index("^NSEI")
            if nifty:
                result.regime = nifty.classify_regime().value
        except Exception as e:
            result.errors.append(f"Market context: {e}")
            print(f"  [DailyScan] Context error: {e}")

        # ── Step 2: Symbol universe ────────────────────────────────────────────
        print("  [DailyScan] Step 2 — Symbol universe …")
        all_tickers: List[Ticker] = []
        if "IN" in command.markets:
            try:
                nse_syms  = self._live_service.get_all_nse_symbols()
                bse_syms  = []  # TODO: add BSE via ILiveMarketDataService
                all_tickers += [Ticker(s, Exchange.NSE) for s in nse_syms]
                all_tickers += [Ticker(s, Exchange.BSE) for s in bse_syms]
            except Exception as e:
                result.errors.append(f"NSE symbols: {e}")

        if command.top:
            all_tickers = all_tickers[:command.top]
        print(f"  [DailyScan] Universe: {len(all_tickers)} tickers")

        # ── Step 3: Bulk OHLC load (uses cache) ───────────────────────────────
        print("  [DailyScan] Step 3 — Bulk OHLC load (cache-first) …")
        stocks = self._stock_repo.get_bulk(all_tickers, period="1y")
        result.total_scanned = len(stocks)
        print(f"  [DailyScan] Loaded: {len(stocks)} stocks")

        # ── Step 4: Screen each stock ──────────────────────────────────────────
        print("  [DailyScan] Step 4 — Running specifications …")
        screener_counts = {k: 0 for k in self._specs}
        triple_hits = []
        multi_hits  = []

        for sym, stock in stocks.items():
            # Build candidate (aggregate all data for this stock)
            candidate = self._build_candidate(stock, command.run_scans)

            # Run each specification
            passed = []
            for name, spec in self._specs.items():
                try:
                    if spec.is_satisfied_by(candidate):
                        screener_counts[name] += 1
                        passed.append(name)
                        # Publish domain event for Darvas breakout
                        if name == "darvas":
                            self._bus.publish(BreakoutDetected(
                                ticker=sym,
                                exchange=stock.ticker.exchange.value,
                                price=candidate.current_price,
                                screener="DarvasBox",
                            ))
                except Exception as e:
                    result.errors.append(f"{sym}/{name}: {e}")

            # Check composite specs
            if self._triple_spec.is_satisfied_by(candidate):
                triple_hits.append(sym)

            if self._multi_spec.is_satisfied_by(candidate):
                multi_hits.append(sym)
                self._bus.publish(MultiScreenHitDetected(
                    ticker=sym,
                    exchange=stock.ticker.exchange.value,
                    screens_passed=len(passed),
                    screeners=passed,
                    price=candidate.current_price,
                ))

        # ── Step 5: Collect results ────────────────────────────────────────────
        result.darvas_breakouts   = screener_counts["darvas"]
        result.golden_crosses     = screener_counts["golden_cross"]
        result.piotroski_strong   = screener_counts["piotroski"]
        result.coffee_can_pass    = screener_counts["coffee_can"]
        result.magic_formula_pass = screener_counts["magic_formula"]
        result.bull_cartel_pass   = screener_counts["bull_cartel"]
        result.triple_hits        = len(triple_hits)
        result.multi_screen_hits  = len(multi_hits)

        # Publish summary event
        self._bus.publish(ScreenerRunCompleted(
            screener_name="DailyFullScan",
            universe_size=result.total_scanned,
            signals_found=result.multi_screen_hits,
            duration_sec=(datetime.utcnow() - t0).total_seconds(),
        ))

        # ── Step 6: Generate report ────────────────────────────────────────────
        if self._report_writer:
            try:
                result.output_path = self._report_writer.write(
                    stocks=stocks,
                    screener_results=screener_counts,
                    triple_hits=triple_hits,
                    multi_hits=multi_hits,
                    regime=result.regime,
                    vix=result.vix,
                )
            except Exception as e:
                result.errors.append(f"Report: {e}")

        result.duration_sec = (datetime.utcnow() - t0).total_seconds()
        print(f"  [DailyScan] Complete in {result.duration_sec:.1f}s")
        self._print_summary(result)
        return result

    def _build_candidate(self, stock, run_scans: bool) -> ScreeningCandidate:
        """
        Build a ScreeningCandidate from a Stock aggregate.
        If run_scans=True, fetches fundamentals (slower).
        If run_scans=False, only OHLC-based screeners will pass.
        """
        candidate = ScreeningCandidate(
            symbol=stock.ticker.symbol,
            suffix=".NS" if stock.ticker.exchange == Exchange.NSE else
                   ".BO" if stock.ticker.exchange == Exchange.BSE else "",
            ohlc_df=self._stock_to_dataframe(stock),
            bar_count=stock.bar_count,
            current_price=stock.current_price.amount if stock.current_price else 0.0,
        )

        if run_scans:
            try:
                fund = self._fund_repo.get_annual_financials(stock.ticker)
                candidate.income_stmt   = fund.get("income_stmt")
                candidate.balance_sheet = fund.get("balance_sheet")
                candidate.cash_flow     = fund.get("cash_flow")
                q_fund = self._fund_repo.get_quarterly_financials(stock.ticker)
                candidate.quarterly_inc = q_fund.get("quarterly_income")
                info = self._fund_repo.get_stock_info(stock.ticker)
                candidate.market_cap     = info.get("marketCap", 0) or 0
                candidate.trailing_pe    = info.get("trailingPE")
                candidate.forward_pe     = info.get("forwardPE")
                candidate.debt_to_equity = info.get("debtToEquity")
                candidate.total_debt     = info.get("totalDebt", 0) or 0
                candidate.total_cash     = info.get("totalCash", 0) or 0
                candidate.book_value     = info.get("bookValue")
                candidate.sector         = info.get("sector", "")
            except Exception:
                pass   # Fundamental data unavailable — OHLC specs still run

        return candidate

    def _stock_to_dataframe(self, stock):
        """Convert Stock price series to DataFrame for specifications."""
        import pandas as pd
        bars = stock.price_series
        if not bars:
            return None
        return pd.DataFrame(
            [{"Open": b.open, "High": b.high, "Low": b.low,
              "Close": b.close, "Volume": b.volume}
             for b in bars],
            index=pd.DatetimeIndex([b.date for b in bars])
        )

    def _print_summary(self, r: DailyScanResult):
        print(f"\n  ── SCAN SUMMARY ──────────────────────────────────")
        print(f"  Universe:        {r.total_scanned:>6,}")
        print(f"  Darvas Breakouts:{r.darvas_breakouts:>6,}")
        print(f"  Golden Cross:    {r.golden_crosses:>6,}")
        print(f"  Piotroski ≥7:   {r.piotroski_strong:>6,}")
        print(f"  Coffee Can:      {r.coffee_can_pass:>6,}")
        print(f"  Magic Formula:   {r.magic_formula_pass:>6,}")
        print(f"  Bull Cartel:     {r.bull_cartel_pass:>6,}")
        print(f"  Triple Hits:     {r.triple_hits:>6,}")
        print(f"  Multi-Screen 3+: {r.multi_screen_hits:>6,}")
        print(f"  Regime: {r.regime} | VIX: {r.vix:.1f} | Time: {r.duration_sec:.1f}s")
        if r.errors:
            print(f"  Errors: {len(r.errors)} — first: {r.errors[0][:60]}")
