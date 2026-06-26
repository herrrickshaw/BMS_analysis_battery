# Changelog

All notable changes follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: breaking change or major new capability
- **MINOR**: new feature, backward-compatible
- **PATCH**: bug fix, performance improvement

---

## [3.5.0] — 2026-06-26 — Two Separate Pipelines (Historical vs News)

Splits all analysis into two clean, independent orchestrators with distinct
entry points, data sources, and online/offline characteristics.

### Added
- **`pipeline_historical.py`** — PIPELINE 1: historical data analysis (OFFLINE).
  Orchestrates price/fundamental stages over the 5-year Parquet cache:
  scan → backtest → walk-forward → pattern discovery → sector clustering →
  DL strategy → implied sentiment↔price proxy. `--stages` selects a subset;
  `full` / `analytics` presets. No live network beyond cache warming.
- **`pipeline_news.py`** — PIPELINE 2: news-based analysis (ONLINE/live text).
  4 stages: market mood (regime gauge) → per-ticker sentiment → forward
  monitor (logs at 1d/1wk/1mo/3mo cadence) → sentiment↔price join (builds the
  true news-vs-price correlation dataset as the log matures).
  Sources: RSS (Moneycontrol/ET/BusinessLine/LiveMint, no key) + 4 APIs.

### Separation of concerns
  Historical = offline, price/fundamentals, backtested patterns, 5-yr cache.
  News       = online, live headlines, VADER/provider sentiment, forward-looking.
  They share only stock_utils helpers; otherwise fully decoupled.

---

## [3.4.0] — 2026-06-26 — Indian News Sources (Moneycontrol/ET/BusinessLine)

### Added
- `IndianRSSProvider` in sentiment_pipeline.py — free RSS, no API key:
  Moneycontrol, Economic Times, BusinessLine, LiveMint. Per-ticker matching +
  market-mood regime gauge. Verified live (ADANIENT +0.64, market mood +0.43).

---

## [3.3.0] — 2026-06-26 — News Sentiment Ingestion Pipeline

Adds the textual-sentiment stream that turns the price-only screeners/ML into
hybrid market+sentiment models — the configuration Sharma et al. (IJIRTM 2025)
and the DL survey found consistently outperforms single-source models.

### Added
- **`sentiment_pipeline.py`** — multi-source news sentiment ingestion:
  - 4 provider adapters (free tiers): **Marketaux** (100/day, global),
    **Alpha Vantage** (25/day, native sentiment), **Finnhub** (60/min),
    **NewsData.io** (1,000/month, multi-language)
  - Provider abstraction with per-source rate-limit throttling
  - Sentiment scoring: provider-native score when available, else VADER with a
    finance-tuned lexicon (beat/upgrade/surge positive; plunge/fraud/downgrade negative)
  - Quota-weighted aggregation → per-ticker score [-1,+1] + POSITIVE/NEUTRAL/NEGATIVE
  - 6-hour result cache to conserve API quota; graceful degradation if a key is missing
  - Demo mode (VADER on sample headlines) when no API keys are set
- `vaderSentiment` added to requirements.txt

### Setup
  export MARKETAUX_KEY / ALPHAVANTAGE_KEY / FINNHUB_KEY / NEWSDATA_KEY
- `warm_india_cache.py` — warms 5-yr Parquet cache for full NSE+BSE
  (2,372 NSE + 2,133 BSE-only = 4,505 tickers)

### Research papers added (1)
- Sharma et al. (IJIRTM 2025) — hybrid market+sentiment beats price-only. (16 total)

---

## [3.2.0] — 2026-06-26 — AI Pattern Discovery & Sector Analytics

Adds an analytics suite that mines the 5-year Parquet cache (6,280 stocks across
NSE + NASDAQ + NYSE) for structure, plus a literature-grounded strategy evaluator
and a full glossary. Reuses the shared `stock_utils` helpers throughout.

### Added
- **`stock_utils.py`** — shared helpers eliminating duplication across 14 scripts
  (`first_df`, `row`, `series`, `extract_ticker_df`, `bulk_download`,
  `parallel_map`, `cagr`, `pct_change`, `normalise_debt_to_equity`).
- **`pattern_discovery.py`** — 4-step unsupervised + supervised discovery:
  cleansing → 24-feature extraction → KMeans/DBSCAN/PCA + GradientBoosting →
  insight extraction (behavioural archetypes, anomalies, co-moving pairs).
  Honest finding: out-of-sample forward-return R² ≈ 0 (semi-efficient markets);
  value is structural (clusters, pairs), not predictive.
- **`dl_strategy_eval.py`** — directional classification → mechanical long/flat
  strategy → economic backtest vs buy-and-hold, grounded in 5 DL papers
  (Fister 2019, Olorunnimbe 2022, Toichatturat 2024, Sharma 2025, Miao CS230).
  Finding: ML earns no return alpha in efficient US, modest edge in India, but
  consistently cuts drawdown 12–15pp in both — Fister's risk-adjusted thesis.
- **`sector_analysis.py`** — sector classification (cached) → equal-weighted
  sector return indices → KMeans on 10-feature fingerprints → rankings,
  co-movement (diversification pairs), rotation. Rediscovered defensive vs
  cyclical split; Utilities as best diversifier (US); Tech defensive in India.
- **`GLOSSARY.md`** — ~180 terms across 12 sections (screeners, indicators,
  fundamentals, regime, backtesting, ML, intraday, IPO, architecture, papers).

### Fixed
- Look-ahead leakage in `pattern_discovery` supervised model (as-of feature
  cutoff): spurious R²=0.926 → honest R²=−0.063.

### Research papers added (5)
- Fister et al. (NNW 2019), Olorunnimbe & Viktor (AI Review 2022),
  Toichatturat (SET 2024), Sharma et al. (IJIRTM 2025), Miao (Stanford CS230).
  Total papers incorporated: 15.

---

## [3.1.0] — 2026-06-26 — Domain-Driven Architecture

Refactored the monolithic scan scripts into a clean 3-layer DDD architecture
under `Downloads/stock_ddd/`. Existing v1.0 infrastructure (Parquet cache,
nsepython fetcher) is wrapped as repository adapters — proven code reused, not
rewritten.

### Added
- **Domain Layer** (`domain/`) — pure business logic, zero outer-layer imports
  - `shared/value_objects.py` — `Ticker`, `Price`, `Percentage`, `DateRange`,
    `ReturnHorizon`, `VIXLevel`, `Exchange`/`MarketRegime`/`PEZone` enums
  - `shared/events.py` — domain events + `DomainEventBus` (pub/sub)
  - `market_data/entities.py` — `Stock` aggregate root, `MarketIndex`,
    `PriceBar`, `Sector`; `classify_regime()` as pure domain logic
  - `market_data/repositories.py` — `IStockRepository`, `IMarketIndexRepository`,
    `ILiveMarketDataService`, `IFundamentalsRepository` interfaces
  - `screening/specifications.py` — Specification pattern: 6 screeners +
    `TripleHitSpec` + `MultiScreenSpec`, composable via `.and_()`/`.or_()`/`.not_()`
- **Application Layer** (`application/`) — orchestration, no business rules
  - `commands/run_daily_scan.py` — `RunDailyScanCommand` + handler (CQRS)
  - `ports/report_writer.py` — `IReportWriter`, `INotificationService` output ports
- **Infrastructure Layer** (`infrastructure/`) — the only layer touching yfinance/Parquet/nsepython
  - `market_data/composite_repository.py` — `CompositeStockRepository` (3-tier cache),
    `ParquetIndexRepository`, `NSEPythonLiveService`, `YFinanceFundamentalsRepository`,
    `create_stock_analysis_container()` DI factory
- `stock_ddd/README.md` — architecture guide with layer diagram

### Changed
- Business rules (screener thresholds, regime classification, PE zones) moved
  out of scripts into testable Domain objects
- Dependency rule enforced: Domain ← Application ← Infrastructure (inward only)

### Benefits
- Screeners testable without network (in-memory `Stock` + `Specification`)
- New data source = one new `IStockRepository` impl, zero Domain/App changes
- Single source of truth for each rule (was duplicated across 3–4 scripts)

---

## [2.0.0] — Planned

### Added
- `intraday_monitor.py` — real-time 15-min / 30-min OHLC monitoring daemon
  - Opening Range Breakout (ORB) detection
  - VWAP deviation alerts
  - Volume surge detection (> 3× 15-min average)
  - Momentum burst pattern (3+ consecutive candles in same direction)
  - Darvas Box applied to intraday (15-min bars)
  - Bollinger Band squeeze breakout
  - Runs only during NSE market hours (09:15–15:30 IST, Mon–Fri)
- Intraday strategy section in daily email
- New fundamental strategies based on company regulatory filings

### Changed
- Docker image: added monitoring daemon as background service
- Cron schedule: added 09:15, 09:30, 10:00 IST monitoring triggers

---

## [1.1.0] — Planned

### Changed
- Async data fetching using `asyncio` + `aiohttp` (target: 50% runtime reduction)
- Shared base module extracted from Indian/US scan scripts (remove redundancy)
- Incremental backtest: only re-compute signals for new bars since last run
- Memory optimisation: process stocks in streaming chunks (not all at once)
- Parquet columnar filtering: read only required columns per screener

### Fixed
- US backtest: SEC EDGAR fallback when NASDAQ FTP times out (v1.0.1 backport)
- yfinance crumb expiry: auto-refresh session every 30 minutes in long runs

---

## [1.0.0] — 2026-06-26

### Initial Release — First Docker image

#### Data
- NSE EQ universe: 2,406 stocks (via bhavcopy)
- BSE: 317 BSE-only stocks
- NASDAQ: 4,320 stocks (SEC EDGAR)
- NYSE: 2,831 stocks (SEC EDGAR)
- 5-year OHLC Parquet cache: 340 MB (Nifty 500 baked into image)
- Nifty 50 + S&P 500 index data: 10-year window

#### Screeners (6 total)
- Darvas Box Breakout (walk-forward, volume-confirmed)
- Golden Crossover (50 DMA × 200 DMA)
- Magic Formula (Greenblatt 2005)
- Piotroski F-Score ≥7 (2000)
- Coffee Can Portfolio (Mukherjea / Marcellus)
- Bull Cartel (quarterly earnings momentum)

#### Analysis
- Backtest: 1-year walk-forward (5 horizons: T+1d → T+3mo)
- Walk-forward: 3y/5y/10y train/test/val framework (8 horizons: T+1d → T+252d)
- ML signal: Ridge regression (AlQahtani et al. IJACSA 2025)
- IPO tracker: bhavcopy diff discovery of new listings
- PE zone classification: sector-aware (8 sectors)
- Market regime: Nifty 50 vs 200 DMA + India VIX

#### Infrastructure
- `market_data_cache.py`: 3-tier Parquet cache (memory → disk → network)
  - Cold start: ~12 min for full NSE; warm reads: 0.7 s from memory
  - 334× speedup vs re-downloading every run
- `nse_data_fetcher.py`: live nsepython integration (VIX, FII/DII, bulk deals)
- `stock_enricher.py`: company names, PE zones, exchange grouping
- `ipo_tracker.py`: new listing discovery and graduated screener gates
- `ml_signal_engine.py`: Ridge/LR signal with compare_models() evaluation

#### Daily Automation
- Cron: 8:30 AM weekdays (morning-stock-analysis-report)
- Email: HTML report with exchange-split tables, PE zones, IPO section
- Sequence: IPO tracker → screener_analysis → full Indian scan → full US scan

#### Research Papers Incorporated (10 total)
1. Greenblatt (2005) — Magic Formula
2. Piotroski (2000) — F-Score
3. Darvas (1960) — Box method
4. Mukherjea (2018) — Coffee Can
5. Bailey et al. (2014) — Backtest overfitting
6. Preet et al. (2021) — Magic Formula India
7. Bhute et al. (2024) — Backtesting Brilliance
8. Liu & Zhu (2024) — Kalman Filter market efficiency
9. Dhanus & Amutha (2025) — Super Trend NSE
10. AlQahtani et al. (2025) — ML/DL models

---

## [3.0.0] — Planned (C + R + Async)

### Added
- `c_extensions/darvas_fast.c` — C implementation of Darvas Box (313× faster)
  - `darvas_classify()` — single-bar classification (O(n × lookback))
  - `darvas_walk_forward()` — full walk-forward signal detection
  - `zscore_normalize_window()` — ML feature normalisation (vectorised SIMD)
  - Compiled: `gcc -O3 -march=native -shared -fPIC -o darvas_fast.so`
- `c_extensions/darvas_wrapper.py` — ctypes Python bridge
  - Falls back to pure Python if .so not available
  - `benchmark()` function for A/B timing comparison
- `r_analysis.py` — R statistical analysis via subprocess
  - `compute_r_stats()` — PerformanceAnalytics: Sharpe, Sortino, Calmar, VaR, CVaR
  - `detect_regimes_r()` — HMM regime detection using depmixS4 (3 states)
  - `sharpe_significance_test()` — Lo (2002) bootstrap significance test
  - `compute_technical_indicators_r()` — TTR: RSI, MACD, ATR, Bollinger Bands

### Performance (profiling results)
- Bottleneck identified: **network I/O = 84%** of total time (not processing)
- Darvas Python: 7.8ms/call → C: 0.025ms/call (**313× speedup**)
- Full NSE 2,400 stocks: Python ~138s → C ~1.4s for Darvas
- R PerformanceAnalytics: 0.4s for Sharpe/Sortino/Calmar/VaR
- Conclusion: Parquet cache solves the real bottleneck; C is a bonus for scale
