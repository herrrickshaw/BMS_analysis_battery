# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A multi-module investment research and trading analytics system for Indian markets, combining:
- **Stock screening & scoring** (NSE/BSE equities via Pegu Score and Sarvas Scan)
- **Portfolio optimization** using Modern Portfolio Theory
- **Put-call parity arbitrage trading** for BankNifty, Crude Oil, and Silver derivatives
- **IPO/SEBI data scraping** and per-stock fundamental analysis

## Commands

### Full Data Pipeline (Python → R → Reports)
```bash
./run_pegu_sarvas.sh              # NIFTY500 + BSE (default)
./run_pegu_sarvas.sh nifty50      # Quick test with NIFTY50 only
./run_pegu_sarvas.sh all          # All NSE + BSE equities
```

### Individual Modules
```bash
# Data extraction
python nse_bse_extractor.py --exchange BOTH --index NIFTY500

# Portfolio optimization (MPT, efficient frontier)
python portfolio_analysis.py --symbols RELIANCE TCS INFY [--weights 0.4 0.35 0.25]

# Per-stock metrics (PEG, PE×PB, RSI, news)
python stock_metrics_nse.py RELIANCE [--rsi-period 21 --news 5]

# Benchmarking (pure Python vs requests vs full-stack)
python nse_bse_benchmark.py [--live SYMBOL1 SYMBOL2 | --points 10000]

# Put-call parity live trading
python -m put_call_parity.main

# Put-call parity backtest
python -m put_call_parity.main --backtest
```

### Dependencies
```bash
pip install -r requirements_nse_bse.txt          # Core (extraction, analysis, portfolio)
pip install -r put_call_parity/requirements.txt  # Broker APIs (kiteconnect, etc.)
```

R packages required for scoring: `dplyr`, `ggplot2`, `tidyr`, `readr`, `scales`

## Architecture

### Data Flow

```
NSE CSV Archives + Yahoo Finance + BSE API
        ↓
nse_bse_extractor.py  →  data/all_stocks_combined.csv
        ↓
pegu_sarvas_analysis.R  (invoked by run_pegu_sarvas.sh)
        ↓
reports/  (top_pegu_picks.csv, sarvas_scan_results.csv, *.png)
```

### Key Modules

**`nse_bse_extractor.py`** — Orchestrates NSE + BSE equity data fetch. Outputs unified CSV with OHLCV, PE, PB, PEG, ROE, margins, growth rates, beta. Supports `--exchange` and `--index` filters.

**`pegu_sarvas_analysis.R`** — Fundamental scoring in R:
- **Pegu Score** (0–100): Valuation 30pts + Quality 30pts + Growth 25pts + Safety 15pts
- **Sarvas Scan**: Multi-criteria filter generating BUY/SELL signals

**`portfolio_analysis.py`** — Modern Portfolio Theory: 8,000 Monte Carlo samples, efficient frontier, min-variance and max-Sharpe portfolios, beta vs NIFTY50, Graham Number fair value.

**`stock_metrics_nse.py`** — NSE corporate announcements, PEG ratio (Trailing P/E ÷ EPS growth%), PE×PB composite, RSI-14 (Wilder's method).

**`nse_bse_benchmark.py`** — Compares 3 data-fetching stacks (stdlib / requests / full) with memory profiling via `tracemalloc`. Has offline mock mode.

### Put-Call Parity Subsystem (`put_call_parity/`)

Trades mispricings where `(C - P) - (F - K)e^(-rT)` deviates beyond total transaction costs.

- **`config.py`** — Credentials, instruments (BankNifty NSE, Crude Oil MCX, Silver MCX), lot sizes, deviation thresholds, cost model (brokerage, STT, exchange charges, GST, SEBI fees)
- **`broker.py`** — BrokerBase ABC with concrete adapters: KiteBroker, UpstoxBroker, AngelBroker
- **`parity_engine.py`** — Core parity math, deviation detection, cost-adjusted signal filtering
- **`strategy.py`** — Main scan loop: expiry selection (2–30 DTE), option chain fetch, OI filtering (min 500), signal generation
- **`trade_manager.py`** — 3-leg order execution, position book persisted to `positions.json`
- **`main.py`** — CLI entry (live vs `--backtest` mode using `option_chain_snapshot.json`)

Broker credentials go in `put_call_parity/config.py` (not committed).

### Notebooks

- **`SEBI_web_scraper.ipynb`** — Selenium scraper for DRHP filings from SEBI website; outputs styled Excel
- **`Stock_reporting.ipynb`** — Interactive stock analysis

### Output Locations

| Output | Location |
|---|---|
| Unified equity data | `data/all_stocks_combined.csv` |
| Pegu-scored universe | `reports/pegu_sarvas_all_stocks.csv` |
| Top picks | `reports/top_pegu_picks.csv` |
| Sarvas BUY signals | `reports/sarvas_scan_results.csv` |
| Benchmark results | `reports/benchmark_results.csv` |
| Charts | `reports/*.png` |
| Active positions | `put_call_parity/positions.json` |

## Key Design Decisions

- **Cost-adjusted signals**: Put-call parity deviations are only acted on after accounting for STT, exchange charges, brokerage, GST, and SEBI fees — raw deviation alone is not sufficient.
- **Position persistence**: `positions.json` is written after every order so the strategy survives restarts without losing track of open legs.
- **Optional heavy deps**: `nse_bse_benchmark.py` falls back gracefully if `nsepython`/`yfinance` are unavailable (offline mock mode).
- **R for scoring**: The Pegu/Sarvas pipeline deliberately uses R (not Python) for the statistical scoring and visualization step.
