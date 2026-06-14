# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A multi-market investment research and trading analytics platform covering India, US, Europe, Japan, and Korea. It combines:

- **Full-stack web app** (FastAPI + React) for live screening, portfolio P&L, and daily scan reports
- **Multi-exchange stock coverage**: India (NSE/BSE), US (NYSE/NASDAQ), Europe (17 exchanges, 966 stocks), Japan (TSE), Korea (KRX)
- **Daily scan report**: Darvas/Buffett + Piotroski across all Cassandra-cached markets
- **Portfolio upload & P&L**: Excel/PDF parsing, historical prices, dividends, RSI signals
- **Stock screening & scoring** (NSE/BSE via Pegu Score and Sarvas Scan — R pipeline)
- **Portfolio optimization** using Modern Portfolio Theory
- **Put-call parity arbitrage trading** for BankNifty, Crude Oil, and Silver derivatives
- **IPO/SEBI data scraping** and per-stock fundamental analysis

## Running the App

```bash
./run_app.sh          # starts backend :8000 + frontend :5173
```

`run_app.sh` refreshes instrument lists at startup:
- India: NSE EQUITY_L.csv (curl)
- US: NASDAQ trader files (~7,000 equities)
- Japan: JPX data_j.xls (TSE)
- Korea: FinanceDataReader (KOSPI + KOSDAQ)
- Europe: Wikipedia index scraping (rebuilds `europe_all_list.csv` if >30 days old)
- China: akshare A-shares

Backend runs with `--reload` so code changes apply immediately without restart.

## Full Data Pipeline (Python → R → Reports)

```bash
./run_pegu_sarvas.sh              # NIFTY500 + BSE (default)
./run_pegu_sarvas.sh nifty50      # Quick test with NIFTY50 only
./run_pegu_sarvas.sh all          # All NSE + BSE equities
```

## Individual CLI Modules

```bash
python nse_bse_extractor.py --exchange BOTH --index NIFTY500
python portfolio_analysis.py --symbols RELIANCE TCS INFY [--weights 0.4 0.35 0.25]
python stock_metrics_nse.py RELIANCE [--rsi-period 21 --news 5]
python nse_bse_benchmark.py [--live SYMBOL1 SYMBOL2 | --points 10000]
python -m put_call_parity.main           # live trading
python -m put_call_parity.main --backtest
```

## Architecture

### Full-Stack Web App

```
browser (React :5173)
    ↕ REST
FastAPI backend (:8000)
    ├── routers/cassandra_router.py   DB management + daily scan
    ├── routers/live.py               yfinance fetch + live scan
    ├── routers/portfolio.py          portfolio parse + P&L
    ├── routers/scan.py               screener CSV scan
    ├── routers/upload.py             screener CSV upload
    └── routers/sectors.py            Damodaran sector benchmarks

Cassandra (local)  ←→  db/cassandra_client.py
                        db/seeder.py          (seeds instruments per market)
                        db/bulk_fetcher.py    (OHLCV+RSI Phase 1, fundamentals Phase 2)
                        db/quote_updater.py   (upsert + read quotes)
                        db/scheduler.py       (APScheduler daily prefetch)
```

### Cassandra Keyspace: `herrrickshaw`

| Table | Key | Contents |
|---|---|---|
| `instruments` | `(market, yf_ticker)` | name, symbol, ISIN, exchange, country |
| `instruments_by_symbol` | `(market, symbol)` | search by ticker |
| `instruments_by_name` | `(market, name_lower)` | search by name prefix |
| `stock_quotes` | `(market, yf_ticker)` | cmp, rsi, ema_50, rsi_signal, pe, pb, roe, opm, market_cap, volume, high_52w, low_52w, debt_to_equity |
| `price_history` | `(yf_ticker, price_date)` | historical close prices |
| `seed_status` | `market` | seeded_at, row_count |

### Market Coverage & Ticker Format

| Market | Cassandra key format | yfinance suffix | Instruments |
|---|---|---|---|
| india | bare NSE symbol (`HDFCBANK`) | `.NS` appended for yf | ~2,368 |
| us | bare symbol (`AAPL`) | none | ~7,442 |
| europe | pre-suffixed (`ADS.DE`, `RIO.L`) | none (suffix embedded) | ~1,214 |
| japan | pre-suffixed (`7203.T`) | none | ~3,709 |
| korea | pre-suffixed (`005930.KS`) | none | ~2,768 |
| china | pre-suffixed (`600519.SS`) | none | ~0 seeded |

**Critical**: India tickers are stored bare (no `.NS`). `fetchers/history.py:_bare_ticker()` strips `.NS`/`.BO` before Cassandra lookup. `_market_from_ticker()` maps all 19 European exchange suffixes (`.DE`, `.F`, `.L`, `.PA`, `.MI`, `.MC`, `.ST`, `.HE`, `.CO`, `.OL`, `.AS`, `.BR`, `.LS`, `.IR`, `.SW`, `.WA`, `.AT`, `.VI`) to `'europe'`.

### European Exchange Coverage (`data/europe_all_list.csv`)

966 stocks across 17 exchanges built from Wikipedia index pages + hardcoded constituents:

| Exchange group | Stocks | Suffixes |
|---|---|---|
| London Stock Exchange | 436 | `.L` |
| Deutsche Boerse Frankfurt | 142 | `.F` / `.DE` |
| Euronext (Paris/Amsterdam/Brussels/Lisbon/Oslo/Milan/Dublin) | 208 | `.PA .AS .BR .LS .OL .MI .IR` |
| Nasdaq Nordic (Stockholm/Helsinki/Copenhagen) | 80 | `.ST .HE .CO` |
| BME Madrid | 35 | `.MC` |
| SIX Swiss | 20 | `.SW` |
| Vienna ATX | 20 | `.VI` |
| Warsaw GPW | 20 | `.WA` |
| Athens | 25 | `.AT` |

### Data Files

| File | Contents |
|---|---|
| `data/europe_all_list.csv` | 966 European stocks (yf_ticker, name, index, exchange) |
| `data/frankfurt_list.csv` | DAX40 + MDAX50 + SDAX70 (142 stocks, `.F` suffix) |
| `data/london_list.csv` | FTSE100 + FTSE250 + SmallCap (436 stocks, `.L` suffix) |
| `data/europe_extended_list.csv` | 11-index intermediate build artifact |
| `data/us_list.csv` | ~7,000 US equities (NASDAQ trader, refreshed daily) |
| `data/japan_list.csv` | TSE equities from JPX (refreshed daily) |
| `data/korea_list.csv` | KOSPI + KOSDAQ from FinanceDataReader (refreshed daily) |
| `data/nse_equity_list.csv` | NSE EQUITY_L.csv (refreshed daily) |

### Bulk Fetch Strategy

`db/bulk_fetcher.py` — two phases, rate-limit friendly:
- **Phase 1** (`yf.download()` batches of 50): OHLCV + RSI-14 + EMA-50 for all instruments. ~20–40 min for full universe.
- **Phase 2** (individual `.info` calls, throttled): PE, PB, ROE, OPM, market cap, D/E. Optional; adds 1–3h.

Trigger via: `POST /api/db/fetch_quotes?market=<market>&with_fundamentals=false`
Poll via: `GET /api/db/fetch_progress`

### Scanners

**`scanners/daily_scanner.py`** — OHLCV+RSI-compatible, works without fundamentals:
- **Darvas/Buffett** (0–7): near-52W-high (+2), above-EMA50 (+2), range-strength (+1), RSI-healthy (+1), optional Buffett overlay ROE/PE/DE (+1 each)
  - BUY ≥ 5 · WATCH ≥ 3
- **Piotroski simplified** (0–6): momentum proxies (above-EMA50, RSI-range, near-high) + fundamentals when present; dynamic thresholds scale with available field count
  - BUY ≥ ceil(max×0.65) · WATCH ≥ ceil(max×0.40)

**`scanners/darvas.py`** — Full Darvas+Buffett (requires Screener.in CSV with fundamentals)
**`scanners/piotroski.py`** — Full 9-point Piotroski (requires Screener.in CSV)
**`scanners/coffee_can.py`** — Coffee Can buy-and-hold (requires Screener.in CSV)

### Key API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/db/daily/scan` | Run Darvas+Piotroski across all Cassandra markets |
| `POST` | `/api/db/fetch_quotes` | Start bulk OHLCV fetch for a market |
| `GET` | `/api/db/fetch_progress` | Poll bulk fetch progress |
| `POST` | `/api/db/seed` | Seed instruments from CSV into Cassandra |
| `GET` | `/api/db/status` | Instrument + quote counts per market |
| `GET` | `/api/db/search` | Search instruments by name or ticker |
| `POST` | `/api/live/fetch` | Fetch live data from yfinance into memory |
| `POST` | `/api/live/scan` | Run scanners on in-memory live data |
| `POST` | `/api/portfolio/parse` | Parse Excel/PDF portfolio file |
| `POST` | `/api/portfolio/history` | Enrich holdings with P&L, dividends, RSI |
| `POST` | `/api/db/scheduler/trigger` | Fire immediate full-market prefetch |

### Frontend (`frontend/src/`)

React + Vite + Tailwind. View modes (toggled top-bar):

| View | Component | Description |
|---|---|---|
| ⚡ Daily Report | `DailyReport.jsx` | All-market Darvas/Piotroski scan from Cassandra |
| Screener Scan | `ResultsTable.jsx` | Results from uploaded Screener.in CSV |
| Live Scan | `ResultsTable.jsx` | Results from yfinance live fetch |
| Compare | `ComparisonTable.jsx` | Side-by-side screener vs live comparison |
| Sector Benchmarks | `SectorBenchmarks.jsx` | Damodaran PE/PB sector data |

**`DailyReport.jsx`**: Market filter tabs (All/India/US/Europe/Japan/Korea), scan type tabs (Darvas/Buffett · Piotroski), market-aware currency (₹/$/ €/¥/₩), coloured market badges, expandable criteria rows, sortable columns.

**`PortfolioUpload.jsx`**: Market dropdown selector (India/US/Europe/Japan/Korea/China), file upload (Excel/PDF), P&L panel with dividends, RSI signals, and total return.

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

- **Cassandra ticker format**: India stores bare NSE symbols; all other markets store pre-suffixed yfinance tickers. `_bare_ticker()` handles the India lookup discrepancy.
- **European suffix routing**: `_market_from_ticker()` maps all 19 European exchange suffixes to the `'europe'` Cassandra partition. Without this, `.DE`/`.L`/`.PA` etc. would fall through to the `'us'` partition.
- **Daily scanner vs full scanners**: `daily_scanner.py` is tuned for Phase-1 OHLCV+RSI data (no fundamentals needed). The full `darvas.py`/`piotroski.py` scanners require Screener.in CSV exports with fundamentals.
- **Piotroski dynamic thresholds**: When fundamentals are absent, max_score shrinks; BUY/WATCH thresholds scale proportionally so sparse data still produces signals.
- **Phase-1-only bulk fetch**: Running `with_fundamentals=false` covers the full instrument universe in 20–40 min. Adding Phase 2 takes 1–3h and fills PE/ROE/D&E — run occasionally, not daily.
- **Cost-adjusted signals**: Put-call parity deviations are only acted on after accounting for STT, exchange charges, brokerage, GST, and SEBI fees.
- **Position persistence**: `positions.json` is written after every order so the strategy survives restarts.
- **R for scoring**: The Pegu/Sarvas pipeline deliberately uses R (not Python) for statistical scoring and visualization.
- **Europe list cache**: `europe_all_list.csv` is rebuilt at startup only if missing or >30 days old (Wikipedia scraping takes ~60s).
