# Stock Analysis System — Domain-Driven Architecture (v3.1.0)

A refactoring of the v1.0–v3.0 stock analysis system into a clean,
layered **Domain-Driven Design (DDD)** architecture.

> ⚠️ Educational/research use only. NOT financial advice.

---

## Why DDD?

The v1.0–v3.0 system worked but had business logic scattered across monolithic
scripts (`full_indian_market_scan.py` was 880 lines mixing data fetch, screening
rules, and Excel output). v3.1 separates these concerns into distinct domains
with strict dependency rules.

**The dependency rule (inward only):**

```
┌─────────────────────────────────────────────────────────┐
│              INFRASTRUCTURE LAYER                         │
│   yfinance · Parquet cache · nsepython · openpyxl · SMTP  │
│   (Implements the contracts defined by inner layers)     │
└────────────────────┬────────────────────────────────────┘
                     │ implements interfaces ▼
┌─────────────────────────────────────────────────────────┐
│              APPLICATION LAYER                            │
│   Commands · Queries · Handlers · Orchestrators · Ports  │
│   (Coordinates the domain; contains NO business rules)   │
└────────────────────┬────────────────────────────────────┘
                     │ calls domain behaviour ▼
┌─────────────────────────────────────────────────────────┐
│                 DOMAIN LAYER                              │
│   Entities · Value Objects · Aggregates · Specifications │
│   Repository Interfaces · Domain Events                  │
│   (Pure business logic — NO imports from outer layers)   │
└─────────────────────────────────────────────────────────┘
```

**Key rule:** Domain imports nothing from Application or Infrastructure.
Infrastructure depends on Domain (implements its interfaces), never the reverse.
This makes the business rules testable without yfinance, network, or files.

---

## Bounded Contexts (Domains)

| Domain | Aggregate Root | Responsibility |
|--------|----------------|----------------|
| **market_data** | `Stock` | Prices, indices, OHLCV, regime classification |
| **screening** | `ScreeningCandidate` | 6 screeners as composable Specifications |
| **backtest** | `BacktestRun` | Walk-forward, train/test/val, return horizons |
| **ipo** | `NewListing` | IPO discovery, graduated screener gates |
| **intraday** | `TradingSession` | 15/30-min pattern detection |
| **reporting** | `Report` | Excel, HTML email, exchange-split tables |

---

## Layer Walkthrough

### Domain Layer (`domain/`)

Pure Python — no `yfinance`, no `pandas` I/O, no network. Just business rules.

**Value Objects** (`domain/shared/value_objects.py`) — immutable, equality by value:
- `Ticker(symbol, exchange)` — knows its `.yfinance_symbol` (`RELIANCE.NS`)
- `Price(amount, currency)` — prevents mixing INR/USD
- `VIXLevel(value)` — encapsulates regime + position-size rules
- `Percentage`, `DateRange`, `ReturnHorizon` — domain primitives

**Entities & Aggregate Root** (`domain/market_data/entities.py`):
- `Stock` — aggregate root; enforces price-bar ordering, exposes `pe_zone`,
  `is_darvas_eligible()`, `is_golden_cross_eligible()`
- `MarketIndex` — `classify_regime()` is pure domain logic (200 DMA + slope)
- `Sector` — sector-aware PE-zone thresholds (banking 12/18/22, FMCG 40/60/80…)

**Specifications** (`domain/screening/specifications.py`) — the Specification pattern
replaces scattered `if roic > 15 and ey > 8` conditions:
```python
spec = MagicFormulaSpec()
if spec.is_satisfied_by(candidate):
    ...
spec.explain()  # "Magic Formula: ROIC>15%, Earnings Yield>8%, ..."

# Composable:
quality_breakout = DarvasBoxSpec().and_(PiotroskiSpec(min_score=7))
```
The 6 screeners + `TripleHitSpec` + `MultiScreenSpec` all live here as testable objects.

**Repository Interfaces** (`domain/market_data/repositories.py`) — the Domain
declares WHAT it needs; Infrastructure decides HOW:
- `IStockRepository`, `IMarketIndexRepository`
- `ILiveMarketDataService`, `IFundamentalsRepository`

**Domain Events** (`domain/shared/events.py`) — decouple aggregates:
`BreakoutDetected`, `MultiScreenHitDetected`, `NewListingDiscovered`,
`IntradayPatternDetected` published through a simple `DomainEventBus`.

### Application Layer (`application/`)

Orchestrates the domain. Contains NO business rules — only coordination.

- `commands/run_daily_scan.py` — `RunDailyScanCommand` + `RunDailyScanHandler`
  (CQRS). The handler injects 4 repository interfaces and runs all
  specifications, publishing events. It speaks only in domain terms.
- `ports/report_writer.py` — `IReportWriter`, `INotificationService` output ports.

### Infrastructure Layer (`infrastructure/`)

The ONLY place that knows about yfinance, Parquet, nsepython, openpyxl, SMTP.

- `market_data/composite_repository.py`:
  - `CompositeStockRepository` — 3-tier cache (memory → Parquet → yfinance)
  - `ParquetIndexRepository` — baked-in index data + incremental update
  - `NSEPythonLiveService` — VIX, FII/DII, bulk deals, events
  - `YFinanceFundamentalsRepository` — annual/quarterly financials
  - `create_stock_analysis_container()` — dependency-injection factory

---

## Usage

```python
from infrastructure.market_data.composite_repository import (
    create_stock_analysis_container
)
from application.commands.run_daily_scan import (
    RunDailyScanCommand, RunDailyScanHandler
)

# Wire up Infrastructure → Application
container = create_stock_analysis_container(workers=8)
handler   = RunDailyScanHandler(**container)

# Execute the use case
result = handler.handle(RunDailyScanCommand(markets=["IN"], top=100))
print(f"Triple hits: {result.triple_hits}")
print(f"Regime: {result.regime} | VIX: {result.vix}")
```

To swap data sources (e.g. NSE direct API instead of yfinance), write a new
`IStockRepository` implementation — no Domain or Application code changes.

---

## What this refactoring buys us

| Before (v1.0–v3.0) | After (v3.1 DDD) |
|--------------------|------------------|
| `if roic>15 and ey>8` repeated in 4 files | One `MagicFormulaSpec`, used everywhere |
| yfinance calls mixed into screening loops | Isolated in `CompositeStockRepository` |
| Cannot test screeners without network | Specs tested with in-memory `Stock` |
| Adding a data source = editing every script | Add one repository implementation |
| Excel writing tangled with scan logic | `IReportWriter` port, swappable adapter |
| Regime logic duplicated 3× | `MarketIndex.classify_regime()` — one place |

---

## Migration path

v3.1 wraps the existing v1.0 infrastructure (`market_data_cache.py`,
`nse_data_fetcher.py`) inside the new repository adapters — so the proven
caching and data-fetch code is reused, not rewritten. The DDD layer sits on
top, providing clean structure for v3.2+ feature work.
