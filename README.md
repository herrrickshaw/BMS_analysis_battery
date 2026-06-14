# Herrrickshaw — Multi-Market Investment Research Platform

A full-stack investment research platform covering **India · US · Europe · Japan · Korea**.  
Combines live market data, institutional scan frameworks, portfolio P&L, and a persistent file analysis workspace — all backed by Apache Cassandra.

---

## Quick Start

```bash
# 1. Start Cassandra
brew services start cassandra        # macOS
# sudo systemctl start cassandra     # Linux

# 2. Start everything (installs all deps automatically)
./run_app.sh
```

| Service | URL |
|---|---|
| Web App | http://localhost:5173 |
| REST API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| DB Health | http://localhost:8000/api/db/status |

On first start the backend automatically seeds **~16,750 instruments** across all markets into Cassandra.

---

## Repository Structure

```
herrrickshaw/
│
├── run_app.sh                    ← ONE COMMAND TO START EVERYTHING
│                                   Installs deps, refreshes instrument lists,
│                                   launches backend (:8000) + frontend (:5173)
│
├── CLAUDE.md                     ← Codebase guide for Claude Code (AI assistant)
├── ASSUMPTIONS.md                ← Design assumptions and data source notes
│
├── backend/                      ← FastAPI Python backend
│   ├── main.py                   App entry point, Cassandra lifespan, router registration
│   ├── requirements.txt          Python dependencies
│   ├── column_map.py             40+ Screener.in column header aliases → canonical names
│   ├── damodaran.py              Aswath Damodaran sector P/E loader (India/US/EM)
│   ├── scheduler.py              APScheduler daily prefetch job (runs at midnight)
│   │
│   ├── db/                       ← Cassandra persistence layer
│   │   ├── cassandra_client.py   Session singleton with graceful CSV-only fallback
│   │   ├── schema.cql            DDL — auto-applied on first startup
│   │   ├── seeder.py             Seeds instrument CSV files into Cassandra tables
│   │   ├── bulk_fetcher.py       Phase 1: OHLCV+RSI bulk fetch via yf.download()
│   │   │                         Phase 2: fundamentals via yf.Ticker().info (throttled)
│   │   └── quote_updater.py      upsert_quotes() / get_quotes() / get_market_quotes_df()
│   │                             Also caches historical prices (price_history table)
│   │
│   ├── parsers/                  ← File and market data parsers
│   │   ├── excel_parser.py       Multi-sheet Excel parser — auto-detects headers,
│   │   │                         extracts ticker/ISIN/name, enriches from Cassandra
│   │   ├── pdf_parser.py         pdfplumber text extraction, ISIN regex, ticker scan
│   │   ├── market_db.py          Per-market symbol DB (Cassandra-first, CSV fallback)
│   │   │                         Loads instrument lists, handles lookup + fuzzy match
│   │   └── symbol_db.py          NSE equity CSV loader — ISIN ↔ symbol bidirectional map
│   │
│   ├── fetchers/                 ← Data fetchers
│   │   ├── live.py               yfinance parallel fetch, RSI-14 (Wilder), EMA-50
│   │   └── history.py            Historical prices (yfinance + Cassandra cache)
│   │                             _bare_ticker(): strips .NS/.BO for Cassandra lookup
│   │                             _market_from_ticker(): routes 19 European suffixes
│   │
│   ├── scanners/                 ← Scan engines
│   │   ├── darvas.py             Full Darvas Box + Buffett overlay (score 0–10)
│   │   │                         Requires Screener.in CSV with fundamentals
│   │   ├── piotroski.py          Full Piotroski F-Score (score 0–9)
│   │   │                         Requires Screener.in CSV with fundamentals
│   │   ├── coffee_can.py         Coffee Can compounding filter + moat score (0–5)
│   │   │                         Requires Screener.in CSV with fundamentals
│   │   └── daily_scanner.py      OHLCV+RSI-only scanner — works without fundamentals
│   │                             Darvas/Buffett (0–7) + Piotroski simplified (0–6)
│   │                             Used by the Daily Report across all Cassandra markets
│   │
│   └── routers/                  ← FastAPI route handlers
│       ├── upload.py             POST /api/upload — Screener.in CSV ingest
│       ├── scan.py               POST /api/scan/{type} — run scan engines on CSV data
│       ├── export.py             GET /api/export — download results as Excel
│       ├── live.py               POST /api/live/fetch — yfinance fetch + Cassandra write
│       │                         POST /api/live/scan — run scanners on live data
│       │                         GET /api/live/compare — Screener vs live delta
│       ├── portfolio.py          POST /api/portfolio/parse — Excel/PDF → holdings + RSI
│       │                         POST /api/portfolio/history — P&L with purchase date
│       ├── sectors.py            GET /api/sectors — Damodaran sector benchmarks
│       ├── cassandra_router.py   GET /api/db/status, seed, search, bulk fetch, scheduler
│       │                         POST /api/db/daily/scan — all-market Darvas+Piotroski
│       └── files.py              File workspace CRUD + analysis
│                                 POST /api/files/upload, GET /api/files,
│                                 DELETE /api/files/{id}, GET /api/files/{id}/preview
│                                 POST /api/files/{id}/analyse
│
├── frontend/                     ← React 18 + Vite + Tailwind web app
│   ├── package.json
│   ├── vite.config.js            Proxy /api → :8000
│   ├── tailwind.config.js
│   └── src/
│       ├── main.jsx              React entry point
│       ├── App.jsx               Root component — view mode routing, state management
│       ├── api.js                All fetch helpers (one function per endpoint)
│       ├── index.css
│       └── components/
│           ├── DailyReport.jsx   ⚡ Daily Report — all-market Darvas+Piotroski
│           │                     from Cassandra, market filter tabs, currency-aware
│           ├── FileWorkspace.jsx 📂 Files — drag-drop upload, persistent workspace,
│           │                     5 analysis types (darvas/piotroski/coffee_can/portfolio/preview)
│           ├── PortfolioUpload.jsx  Portfolio upload with market dropdown selector
│           │                        (India/US/Europe/Japan/Korea/China), P&L panel
│           ├── ResultsTable.jsx  Sortable results table, RSI badge, criteria drill-down
│           ├── LivePanel.jsx     Live fetch controls, index selector, compare button
│           ├── ScanControls.jsx  Scan engine buttons (Darvas / Piotroski / Coffee Can)
│           ├── MarketTabs.jsx    Market tab strip (NSE Large/Mid/Small/BSE/European)
│           ├── UploadPanel.jsx   Screener.in CSV drag-drop upload zone
│           ├── FilterSidebar.jsx Signal, PE, ROE, D/E, completeness filters
│           ├── ComparisonTable.jsx  Screener vs live field-by-field delta view
│           ├── SectorBenchmarks.jsx Damodaran sector P/E chart
│           ├── ScoreBadge.jsx    Coloured score chip (BUY / WATCH / AVOID)
│           ├── Header.jsx        App header with Cassandra status dot
│           └── DisclaimerModal.jsx  Risk disclaimer
│
├── data/                         ← Instrument reference data
│   ├── europe_all_list.csv       966 European stocks across 17 exchanges
│   │                             (LSE, Frankfurt, Euronext, Nordic, Madrid, Swiss,
│   │                              Vienna, Warsaw, Athens) — rebuilt every 30 days
│   ├── frankfurt_list.csv        DAX40 + MDAX50 + SDAX70 — 142 stocks (.F suffix)
│   ├── london_list.csv           FTSE100 + FTSE250 + SmallCap — 436 stocks (.L suffix)
│   ├── europe_extended_list.csv  Intermediate build artifact (11 major indices)
│   ├── europe_list.csv           Legacy STOXX 600 list (superseded by europe_all_list.csv)
│   ├── us_list.csv               ~7,000 US equities from NASDAQ trader files (daily refresh)
│   ├── japan_list.csv            TSE equities from JPX data_j.xls (daily refresh)
│   ├── korea_list.csv            KOSPI + KOSDAQ from FinanceDataReader (daily refresh)
│   ├── nse_equity_list.csv       NSE EQUITY_L.csv (daily refresh via curl)
│   ├── sp500_list.csv            S&P 500 fallback if us_list.csv not generated
│   ├── all_stocks_combined.csv   Output of nse_bse_extractor.py (R pipeline input)
│   ├── damodaran/                Damodaran sector P/E CSVs (India / US / EM)
│   └── samples/                  Sample Screener.in exports for testing
│       ├── nse_largecap_sample.csv
│       ├── nse_midcap_sample.csv
│       └── european_sample.csv
│
├── uploads/                      ← Persistent file workspace
│   ├── _meta.json                File registry (id, name, size, upload date)
│   └── <id>_<filename>           Uploaded files (CSV/Excel/PDF), survive server restart
│
├── put_call_parity/              ← Options arbitrage subsystem
│   ├── main.py                   CLI entry — live trading or --backtest mode
│   ├── config.py                 Broker credentials, instruments (BankNifty/Crude/Silver),
│   │                             lot sizes, deviation thresholds, full cost model
│   ├── broker.py                 BrokerBase ABC + KiteBroker / UpstoxBroker / AngelBroker
│   ├── parity_engine.py          Core math: (C−P) − (F−K)e^(−rT), cost-adjusted signals
│   ├── strategy.py               Scan loop: expiry selection, OI filter, signal generation
│   ├── trade_manager.py          3-leg order execution, positions.json persistence
│   └── requirements.txt          Broker API deps (kiteconnect, etc.)
│
├── reports/                      ← R pipeline outputs
│   ├── top_pegu_picks.csv
│   ├── sarvas_scan_results.csv
│   ├── pegu_sarvas_all_stocks.csv
│   └── *.png                     Score distribution charts
│
├── run_pegu_sarvas.sh            R pipeline runner (NIFTY500 / BSE / all)
├── nse_bse_extractor.py          NSE+BSE data fetch → data/all_stocks_combined.csv
├── pegu_sarvas_analysis.R        Pegu Score (0–100) + Sarvas Scan in R
├── portfolio_analysis.py         Modern Portfolio Theory — efficient frontier, Monte Carlo
├── stock_metrics_nse.py          Per-stock: PEG, PE×PB, RSI-14, corporate announcements
├── nse_bse_benchmark.py          Data-fetch stack benchmarking (stdlib/requests/full)
├── requirements_nse_bse.txt      CLI tool dependencies
├── SEBI_web_scraper.ipynb        Selenium scraper for SEBI DRHP filings → styled Excel
└── Stock_reporting.ipynb         Interactive stock analysis notebook
```

---

## Web App — View Modes

| Tab | What it does |
|---|---|
| ⚡ **Daily Report** | One-click Darvas/Buffett + Piotroski scan across all 16,750 Cassandra-cached stocks. Market filter tabs (All / India / US / Europe / Japan / Korea), market-aware currency (₹ / $ / € / ¥ / ₩), BUY + WATCH only, sortable by any column. |
| 📂 **Files** | Persistent file workspace. Upload a CSV, Excel, or PDF once — it stays on disk. Select it and run any of five analyses: Darvas, Piotroski, Coffee Can, Portfolio P&L, or Data Preview. Results appear inline. |
| **Screener Scan** | Upload a Screener.in CSV export and run the full scan engines with complete fundamental data (promoter holding, EPS growth, OCF, etc.). |
| **Live Scan** | Fetch real-time data from yfinance for any NSE index or a custom symbol list, then run scan engines on the live snapshot. |
| **Sector Benchmarks** | Damodaran sector P/E benchmarks for India, US, and Emerging Markets — the same values used in the Darvas C9 valuation check. |

**Portfolio sidebar** (on all tabs): Upload a broker statement (Excel/PDF), select market, get matched tickers enriched with CMP, RSI-14, EMA-50, dividends, unrealised P&L, and total return.

---

## Market & Exchange Coverage

| Market | Exchanges | Instruments | yfinance Suffix | Cassandra key format |
|---|---|---|---|---|
| India | NSE / BSE | ~2,368 | `.NS` appended by fetcher | Bare symbol (`HDFCBANK`) |
| US | NYSE / NASDAQ | ~7,442 | none | Bare symbol (`AAPL`) |
| Europe | 17 exchanges (see below) | ~1,214 | already embedded | Pre-suffixed (`ADS.DE`, `RIO.L`) |
| Japan | TSE (Tokyo) | ~3,709 | `.T` embedded | Pre-suffixed (`7203.T`) |
| Korea | KOSPI / KOSDAQ | ~2,768 | `.KS` / `.KQ` embedded | Pre-suffixed (`005930.KS`) |

**European exchanges:** London `.L` · Frankfurt `.F` · Xetra `.DE` · Paris `.PA` · Amsterdam `.AS` · Milan `.MI` · Madrid `.MC` · Stockholm `.ST` · Helsinki `.HE` · Copenhagen `.CO` · Oslo `.OL` · Brussels `.BR` · Lisbon `.LS` · Dublin `.IR` · Zurich `.SW` · Vienna `.VI` · Warsaw `.WA` · Athens `.AT`

---

## Scan Engines

### Darvas / Buffett (Score 0–10)
Price momentum (Nicholas Darvas's box system) layered with Warren Buffett quality criteria.

| Criteria | Threshold |
|---|---|
| C1 Price near 52W high | CMP within 3% of 52W high |
| C2 Volume breakout | Volume ≥ 1.5× 30-day average |
| C3 Above box floor | CMP ≥ 85% of 52W high |
| C4 Consistent ROE | ROE > 15% |
| C5 Profit margin | Net/operating margin > 10% |
| C6 Low debt | D/E < 0.5 |
| C7 Promoter conviction | Promoter holding > 50% |
| C8 EPS growth | 5Y profit growth > 10% |
| C9 Fair valuation | P/E < 1.5× Damodaran sector P/E (fallback: P/E < 35) |
| C10 Price strength | CMP in upper half of 52W range |

BUY ≥ 7 · WATCH ≥ 4 · AVOID < 4

### Piotroski F-Score (Score 0–9)
Nine-point financial health score from professor Joseph Piotroski.

- **Profitability (4 pts):** ROA > 0 · OCF > 0 · improving ROA · OCF/Assets > ROA
- **Leverage & Liquidity (3 pts):** D/E decreased · current ratio improved · no dilution
- **Efficiency (2 pts):** OPM > 20% · asset turnover > 0.5

BUY ≥ 8 · WATCH ≥ 6 · AVOID ≤ 5

### Coffee Can (Pass/Fail + Moat 0–5)
Saurabh Mukherjea's long-term compounding framework. All six hard filters must pass:
Revenue CAGR > 10% · Profit CAGR > 10% · ROCE > 15% · D/E < 1 · Promoter pledge < 10% · Market cap > ₹100 Cr

### Daily Scanner (works without fundamentals)
Tuned for Cassandra Phase-1 OHLCV+RSI data. Used by the ⚡ Daily Report.
- **Darvas simplified (0–7):** Near 52W high (+2), above EMA-50 (+2), range strength (+1), RSI health (+1), optional ROE/PE/D&E overlay (+1 each when available)
- **Piotroski simplified (0–6):** Three momentum proxies + fundamentals when present; BUY/WATCH thresholds scale proportionally with available field count

---

## Put-Call Parity Arbitrage

Trades mispricings where `(C − P) − (F − K)e^(−rT)` exceeds total transaction costs.  
Instruments: **BankNifty (NSE) · Crude Oil (MCX) · Silver (MCX)**

```bash
python -m put_call_parity.main              # live trading
python -m put_call_parity.main --backtest   # replay option_chain_snapshot.json
```

Credentials → `put_call_parity/config.py` (not committed to git).

---

## R Pipeline (Pegu Score + Sarvas Scan)

```bash
./run_pegu_sarvas.sh              # NIFTY500 + BSE (default)
./run_pegu_sarvas.sh nifty50      # quick test
./run_pegu_sarvas.sh all          # full NSE + BSE universe
```

**Pegu Score (0–100):** Valuation 30 + Quality 30 + Growth 25 + Safety 15  
**Sarvas Scan:** Multi-criteria BUY/SELL signals + visualisation charts  
Outputs to `reports/`.

---

## Key API Endpoints

```
# Daily scan across all markets
POST /api/db/daily/scan?markets=india,us,europe,japan,korea&scans=darvas,piotroski

# File workspace
GET    /api/files
POST   /api/files/upload
DELETE /api/files/{id}
GET    /api/files/{id}/preview?rows=20
POST   /api/files/{id}/analyse?analysis=darvas&market=india

# Portfolio
POST /api/portfolio/parse?market=india      parse Excel/PDF → holdings + RSI
POST /api/portfolio/history                 P&L + dividends from purchase date

# Cassandra management
GET  /api/db/status                         health + instrument/quote counts
POST /api/db/seed?market=europe&force=true  (re)seed a market
POST /api/db/fetch_quotes?market=us         start OHLCV bulk fetch
GET  /api/db/fetch_progress                 poll bulk fetch status
GET  /api/db/search?market=india&q=hdfc     search by name or ticker
POST /api/db/scheduler/trigger              fire immediate full-market prefetch

# Screener CSV flow
POST /api/upload?market=nse_largecap
POST /api/scan/darvas?market=nse_largecap
GET  /api/export?market=nse_largecap&scan_type=all
```

---

## Dependencies

```bash
pip install -r backend/requirements.txt          # web app backend
pip install -r requirements_nse_bse.txt          # CLI tools (extractor, portfolio, benchmark)
pip install -r put_call_parity/requirements.txt  # broker APIs (kiteconnect, etc.)
```

R packages: `dplyr`, `ggplot2`, `tidyr`, `readr`, `scales`

Apache Cassandra 4.x or 5.x required. Schema is auto-applied on first backend start.
