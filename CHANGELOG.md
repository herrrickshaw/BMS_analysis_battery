# Changelog

All notable changes follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: breaking change or major new capability
- **MINOR**: new feature, backward-compatible
- **PATCH**: bug fix, performance improvement

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
