# Herrrickshaw — Investment Research Platform

A full-stack investment research platform for Indian and global markets.  
Combines portfolio ingestion, live market data, NoSQL storage, and three institutional-grade scan frameworks.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Data Ingestion Pipeline](#data-ingestion-pipeline)
   - [Excel Input](#excel-input)
   - [PDF Input](#pdf-input)
   - [Ticker Resolution Logic](#ticker-resolution-logic)
3. [Data Validation Pipeline](#data-validation-pipeline)
4. [Historical Price Retrieval — Date of Purchase](#historical-price-retrieval--date-of-purchase)
5. [Cassandra NoSQL Database](#cassandra-nosql-database)
6. [Live Data & RSI Signal](#live-data--rsi-signal)
7. [Insights & Recommendations](#insights--recommendations)
8. [Scan Engines](#scan-engines)
9. [API Reference](#api-reference)
10. [Architecture](#architecture)
11. [Column Mapping (Screener.in)](#column-mapping-screenerin)
12. [Project Structure](#project-structure)

---

## Quick Start

```bash
# Start Cassandra first
brew services start cassandra      # macOS
# sudo systemctl start cassandra   # Linux

# One-command start (installs all deps automatically)
./run_app.sh
```

| Service     | URL                          |
|-------------|------------------------------|
| Web App     | http://localhost:5173        |
| API         | http://localhost:8000        |
| API Docs    | http://localhost:8000/docs   |
| DB Status   | http://localhost:8000/api/db/status |

On first start the backend seeds **~16,750 instruments** across all supported markets into Cassandra automatically.

---

## Data Ingestion Pipeline

Upload a portfolio or watchlist from any broker, fund house, or spreadsheet.  
Supported formats: **Excel (.xlsx / .xls)** and **PDF**.  
Supported markets: **India (NSE/BSE) · US · Europe · Japan · Korea · China**.

```
Excel / PDF Upload
      │
      ▼
┌─────────────────────────────────────┐
│         Sheet / Page Scanner        │
│  • Detect header rows (ticker,      │
│    name, ISIN, symbol columns)      │
│  • Fall back to free-text scan      │
│    if no header recognised          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│        Ticker Resolution            │  ← multi-strategy, in priority order
│  1. Exact symbol match (DB)         │
│  2. ISIN lookup (DB)                │
│  3. Fuzzy name match (difflib 0.6)  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      Cassandra Quote Enrichment     │
│  • CMP, RSI-14, EMA-50, RSI Signal  │
│  • Served from cache if available   │
└──────────────┬──────────────────────┘
               │
               ▼
         Matched Stock List
     {yf_ticker, name, matched_via,
      cmp, rsi, rsi_signal, ema_50}
```

### Excel Input

The parser scans every sheet and auto-detects column roles from header names:

| Role | Recognised Header Names |
|------|--------------------------|
| Ticker / Symbol | `symbol`, `ticker`, `nse code`, `bse code`, `scrip`, `trading symbol`, `stock code`, `security code` … |
| Company Name | `name`, `company`, `company name`, `scrip name`, `issuer`, `description` … |
| ISIN | `isin`, `isin number`, `isin code`, `isin no` |

When no structured header is found (e.g. a plain holdings statement), the full cell text of each sheet is scanned with a market-specific regex pattern and every matching ticker/ISIN is resolved.

**Endpoint:** `POST /api/portfolio/parse?market=india`  
**Body:** multipart file upload (`.xlsx` or `.xls`)

```json
{
  "stocks": [
    {
      "yf_ticker": "RELIANCE.NS",
      "symbol":    "RELIANCE.NS",
      "name":      "Reliance Industries Limited",
      "isin":      "INE002A01018",
      "matched_via": "ISIN",
      "sheet":     "Holdings",
      "quote": {
        "cmp":        2945.60,
        "rsi":        58.3,
        "ema_50":     2810.40,
        "rsi_signal": "HOLD",
        "pe":         28.4,
        "roe":        14.2,
        "fetched_at": "2026-06-14T10:30:00+00:00"
      }
    }
  ],
  "warnings": [],
  "meta": {
    "total_found":    42,
    "quotes_enriched": 38,
    "cassandra":      "online"
  }
}
```

### PDF Input

Parses broker account statements, demat holdings PDFs, and fund factsheets.

1. Text is extracted page-by-page using `pdfplumber`
2. ISIN patterns (`INE…` for India, `US…`, `JP…`, `KR…`) are extracted first — most reliable
3. Market-specific ticker regex is applied to remaining text
4. All candidates are resolved through the same Cassandra-backed lookup as Excel

**Endpoint:** `POST /api/portfolio/parse?market=india`  
**Body:** multipart file upload (`.pdf`)

### Ticker Resolution Logic

Each market uses its own pattern and lookup chain:

| Market | Native Pattern | ISIN Prefix | yfinance Suffix |
|--------|---------------|-------------|-----------------|
| India  | `[A-Z][A-Z0-9&]{1,14}` | `IN` | `.NS` |
| US     | `[A-Z]{1,5}` | `US` | *(none)* |
| Europe | `[A-Z0-9]{2,8}\.[A-Z]{2}` | country-specific | embedded |
| Japan  | `\d{4,5}` | `JP` | `.T` |
| Korea  | `\d{6}` | `KR` | `.KS / .KQ` |
| China  | `\d{6}` | `CN` | `.SS / .SZ` |

Resolution priority per row:
1. **Symbol exact match** → `instruments_by_symbol` (Cassandra)
2. **ISIN exact match** → `instruments_by_isin` (Cassandra)
3. **Name fuzzy match** → `instruments_by_name` (Cassandra prefix-range) + difflib fallback
4. **CSV in-memory dict** fallback if Cassandra offline

---

## Data Validation Pipeline

Every row that enters the system passes through a validation and normalisation layer before it is scored or stored.

```
Raw Row (from CSV / Excel / Live Fetch)
         │
         ▼
┌────────────────────────────────────┐
│  1. Column Normalisation           │
│     40+ Screener.in header aliases │
│     mapped to canonical field names│
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  2. Type Coercion                  │
│     • Strip ₹/,/% suffixes         │
│     • Numeric strings → float      │
│     • NaN / "N/A" / "-" → None    │
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  3. Unit Normalisation             │
│     • yfinance ROE/OPM × 100       │
│       (returned as decimals)       │
│     • Market cap INR → ₹ Crore     │
│       (÷ 1e7)                      │
│     • Market cap USD → USD M       │
│       (÷ 1e6)                      │
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  4. Completeness Score             │
│     Required fields checked per    │
│     scan type; % present shown in  │
│     "Data" column of results table │
└──────────────┬─────────────────────┘
               │
               ▼
┌────────────────────────────────────┐
│  5. Sector Benchmark Lookup        │
│     Damodaran sector P/E fetched   │
│     for C9 (Darvas valuation check)│
│     Falls back to absolute P/E<35  │
└──────────────┬─────────────────────┘
               │
               ▼
        Validated Row → Scanner / Cassandra
```

**Validation outcomes per row:**
- `completeness` field (0–100%) tells you how many required criteria could be evaluated
- Criteria with missing inputs are marked `null` (shown as grey dot) rather than forced to pass/fail
- Rows with completeness below a user-configurable threshold are filtered out in the UI

---

## Historical Price Retrieval — Date of Purchase

When a portfolio Excel includes a **date of purchase** column, the system retrieves historical closing prices from yfinance to calculate cost basis and unrealised P&L.

### How to include purchase date in your upload file

Add a column named `date`, `purchase date`, `buy date`, or `transaction date` (case-insensitive) with values in any standard date format (`DD-MM-YYYY`, `YYYY-MM-DD`, `DD/MM/YYYY`):

| Symbol | Name | Quantity | Purchase Date | Purchase Price |
|--------|------|----------|---------------|----------------|
| RELIANCE | Reliance Industries | 10 | 15-Jan-2023 | 2410.50 |
| TCS | Tata Consultancy Services | 5 | 03-Mar-2022 | 3678.00 |
| INFY | Infosys | 8 | 22-Aug-2021 | 1685.75 |

### Historical price fetch endpoint

```http
POST /api/portfolio/history
Content-Type: application/json

{
  "market": "india",
  "holdings": [
    {
      "yf_ticker":      "RELIANCE.NS",
      "purchase_date":  "2023-01-15",
      "purchase_price": 2410.50,
      "quantity":       10
    }
  ]
}
```

**Response — per holding:**

```json
{
  "holdings": [
    {
      "yf_ticker":       "RELIANCE.NS",
      "name":            "Reliance Industries Limited",
      "purchase_date":   "2023-01-15",
      "purchase_price":  2410.50,
      "quantity":        10,
      "price_on_date":   2389.85,
      "current_price":   2945.60,
      "cost_basis":      24105.00,
      "current_value":   29456.00,
      "unrealised_pnl":  5351.00,
      "pnl_pct":         22.19,
      "rsi":             58.3,
      "rsi_signal":      "HOLD"
    }
  ],
  "summary": {
    "total_invested":    241050.00,
    "current_value":     294560.00,
    "total_pnl":         53510.00,
    "total_pnl_pct":     22.19
  }
}
```

### How historical prices are fetched

```
yf.Ticker("RELIANCE.NS").history(start="2023-01-15", end="2023-01-16")
                  │
                  ▼
     Closing price on the nearest trading day
     (automatically skips weekends and market holidays)
```

Prices are cached in Cassandra's `stock_quotes` table after the first fetch. Subsequent requests for the same ticker + date are served from cache without hitting yfinance.

### Supported date range

yfinance provides daily OHLCV data going back to **IPO date** for most stocks. Practical reliable history:
- NSE/BSE equities: 1994–present
- US equities: 1962–present
- Japan/Korea/Europe: typically 2000–present

---

## Cassandra NoSQL Database

The platform uses Apache Cassandra as its persistence layer for instrument metadata and live quote caching.

### Keyspace: `herrrickshaw`

| Table | Primary Key | Contents |
|-------|-------------|----------|
| `instruments` | `(market, yf_ticker)` | Static metadata: symbol, name, ISIN, exchange, country |
| `instruments_by_symbol` | `(market, symbol)` | Fast O(1) lookup by exchange code |
| `instruments_by_name` | `(market, name_lower)` | Name prefix-range search without ALLOW FILTERING |
| `instruments_by_isin` | `isin` | Cross-market ISIN → yf_ticker mapping |
| `stock_quotes` | `(market, yf_ticker)` | Latest price, RSI-14, EMA-50, RSI signal, P/E, ROE, volume |
| `seed_status` | `market` | Tracks which markets have been seeded |

### Instrument counts (on first start)

| Market | Instruments |
|--------|-------------|
| India (NSE) | ~2,368 |
| US (NASDAQ/NYSE) | ~7,442 |
| Europe | ~463 |
| Japan (TSE) | ~3,709 |
| Korea (KRX) | ~2,768 |

### Setup

```bash
brew install cassandra          # macOS
brew services start cassandra

# Schema is created automatically on first backend start.
# To bootstrap manually:
cqlsh -f backend/db/schema.cql
```

### DB Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/db/status` | Connection health + row counts per market |
| `POST` | `/api/db/seed?market=india` | Seed one market from CSV |
| `POST` | `/api/db/seed/all` | Seed all markets (idempotent) |
| `GET` | `/api/db/search?market=india&q=reliance` | Prefix search by name or symbol |

### Graceful fallback

If Cassandra is not running, the app operates in **CSV-only mode**: all existing scan and upload features work unchanged using in-memory dicts. The Cassandra status dot in the header turns grey.

---

## Live Data & RSI Signal

After matching tickers from an upload, click **Fetch Live Data** to pull current fundamentals and technicals from yfinance. Results are written to Cassandra and displayed immediately.

### RSI / EMA-50 Signal

Computed from 6 months of daily closing prices per stock:

| Signal | Condition |
|--------|-----------|
| **BUY** | RSI-14 < 30 (oversold) **and** Close > EMA-50 (uptrend) |
| **SELL** | RSI-14 > 70 (overbought) **and** Close < EMA-50 (downtrend) |
| **HOLD** | All other conditions |

**RSI calculation** uses Wilder's smoothing (`EWM alpha = 1/14`).  
**EMA-50** uses standard exponential weighted mean (`span = 50`).

The signal is shown:
- As a coloured badge in the scan results table (all three scan types)
- As a signal column in the portfolio upload ticker list (from Cassandra cache)
- As summary chips in the results toolbar (e.g. "3 RSI BUY · 1 RSI SELL")

---

## Insights & Recommendations

The platform surfaces actionable signals at three levels:

### 1. Stock-level (per scan)

Each scan engine produces a `signal`, `score`, and `criteria` breakdown per stock:

| Engine | Signal Scale | Primary Insight |
|--------|-------------|-----------------|
| Darvas Box | 0–10, BUY ≥ 7 | Momentum + quality: stock is breaking out with fundamentals backing it |
| Piotroski F-Score | 0–9, BUY ≥ 8 | Financial strength: company is improving on 9 balance-sheet metrics |
| Coffee Can | Pass/Fail + Moat 0–5 | Long-term compounder: consistent double-digit growth, durable moat |

### 2. Technical signal (RSI × EMA-50)

Layered on top of every fundamental scan — the RSI Signal column tells you whether the entry/exit timing is supported by momentum:

- A Darvas BUY with RSI BUY = high-conviction entry (breakout + oversold)
- A Coffee Can PASS with RSI SELL = fundamentally strong but technically stretched; wait for pullback
- An F-Score ≥ 8 with RSI HOLD = financially improving, timing neutral

### 3. Portfolio-level (after upload + fetch)

When you upload a portfolio and fetch live data:

- **Unrealised P&L** vs purchase price (requires date-of-purchase column)
- **Concentration risk**: signal distribution (how many BUY vs SELL vs HOLD across the portfolio)
- **Screener vs Live divergence**: field-by-field delta between your uploaded Screener.in data and live yfinance prices — stocks with > 20% divergence flagged red

### Sector benchmarks (Damodaran)

P/E comparison for Darvas C9 uses Aswath Damodaran's annually-updated sector medians for India, US, and Emerging Markets — not the sector average from the uploaded dataset. This prevents the "everyone looks cheap in a cheap sector" distortion.

---

## Scan Engines

### 1. Darvas Box + Buffett Overlay (Score 0–10)

Combines Nicholas Darvas's price/momentum box system with Warren Buffett's quality criteria.

| # | Criterion | Threshold |
|---|-----------|-----------|
| C1 | Price near 52W high | CMP within 3% of 52W High |
| C2 | Volume breakout | Volume ≥ 1.5× 30-day average |
| C3 | Above box floor | CMP ≥ 85% of 52W High |
| C4 | Consistent ROE | ROE > 15% |
| C5 | Profit margin | Net/Operating margin > 10% |
| C6 | Low debt | D/E < 0.5 |
| C7 | Promoter conviction | Promoter holding > 50% |
| C8 | EPS growth | 5Y profit growth > 10% |
| C9 | Fair valuation | P/E < 1.5× Damodaran sector P/E (fallback P/E < 35) |
| C10 | Price strength | CMP in upper half of 52W range |

Score ≥ 7 → **BUY** · 4–6 → **WATCH** · < 4 → **AVOID**

---

### 2. Piotroski F-Score (Score 0–9)

Classic 9-point financial health score.

**Profitability (4 pts):** ROA > 0 · OCF > 0 · ROA improving · OCF/Assets > ROA  
**Leverage & Liquidity (3 pts):** D/E < 0.5 · Current ratio > 1.5 · No dilution  
**Operating Efficiency (2 pts):** OPM > 20% · Asset turnover > 0.5

Score 8–9 → **BUY ★** · 6–7 → **WATCH** · ≤ 5 → **AVOID**

> When `Piotroski score` is present in your Screener export, the app uses it directly (more accurate than the snapshot approximation).

---

### 3. Coffee Can Portfolio (Pass / Fail + Moat 0–5)

Saurabh Mukherjea's compounding framework — all six hard filters must pass.

| Filter | Threshold |
|--------|-----------|
| Revenue CAGR | > 10% (10Y → 5Y → 3Y fallback) |
| Profit CAGR | > 10% |
| ROCE | > 15% |
| Debt/Equity | < 1 |
| Promoter pledge | < 10% |
| Market cap | > ₹100 Cr (or $100 M for US/ADRs) |

Moat bonus (+1 each): OPM > 40% (+2) · ROE > 20% · ROCE > 25% · D/E < 0.3

---

## API Reference

### Portfolio & Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/portfolio/parse?market=india` | Upload Excel/PDF → matched tickers + cached quotes |
| `POST` | `/api/portfolio/history` | Fetch historical prices from purchase date |
| `GET` | `/api/portfolio/markets` | List supported markets |

### Screener CSV Upload & Scan

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload?market=nse_largecap` | Upload Screener.in CSV |
| `POST` | `/api/scan/{scan_type}?market=` | Run scan (`darvas` · `piotroski` · `coffee_can` · `all`) |
| `GET` | `/api/export?market=&scan_type=` | Download Excel with all scan result sheets |

### Live Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/live/fetch?market=` | Fetch live data from yfinance (+ RSI/EMA-50) |
| `GET` | `/api/live/status?market=` | Fetch progress polling |
| `POST` | `/api/live/scan?market=&scan_type=` | Run scanners on live-fetched data |
| `GET` | `/api/live/compare?market=` | Field-by-field delta: Screener vs live |
| `GET` | `/api/live/indices` | Available NSE index symbol lists |

### Cassandra Database

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/db/status` | Connection health + instrument/quote counts |
| `POST` | `/api/db/seed?market=india` | Seed one market (idempotent) |
| `POST` | `/api/db/seed/all` | Seed all markets |
| `GET` | `/api/db/search?market=india&q=tata` | Prefix search by name or symbol |

---

## Architecture

```
browser (React 18 + Vite + Tailwind)
    │  REST / JSON
    ▼
FastAPI (Python 3.9+, uvicorn)
    │
    ├── routers/
    │   ├── upload.py           Screener.in CSV ingest
    │   ├── scan.py             Run scan engines
    │   ├── export.py           Excel download
    │   ├── live.py             yfinance fetch + Cassandra write
    │   ├── portfolio.py        Excel/PDF parse + quote enrichment
    │   ├── sectors.py          Damodaran sector P/E
    │   └── cassandra_router.py DB status / seed / search
    │
    ├── db/
    │   ├── cassandra_client.py Session singleton (graceful fallback)
    │   ├── seeder.py           Bulk load CSV → Cassandra instruments tables
    │   ├── quote_updater.py    upsert_quotes / get_quotes
    │   └── schema.cql          DDL (also auto-applied on startup)
    │
    ├── parsers/
    │   ├── excel_parser.py     Multi-sheet header detection + row resolution
    │   ├── pdf_parser.py       pdfplumber text extraction + ISIN/ticker scan
    │   ├── market_db.py        Per-market lookup (Cassandra-first, CSV fallback)
    │   └── symbol_db.py        NSE equity CSV loader (ISIN ↔ symbol)
    │
    ├── fetchers/
    │   └── live.py             yfinance parallel fetch · RSI-14 · EMA-50
    │
    └── scanners/
        ├── darvas.py           10-point Darvas + Buffett overlay
        ├── piotroski.py        9-point F-Score
        └── coffee_can.py       Hard filters + moat score

Apache Cassandra 5.x
    ├── instruments             16,750+ tickers, 6 markets
    ├── instruments_by_symbol
    ├── instruments_by_name     Prefix-range search
    ├── instruments_by_isin
    ├── stock_quotes            RSI · EMA-50 · CMP · P/E · ROE (live cache)
    └── seed_status
```

---

## Column Mapping (Screener.in)

The backend auto-detects Screener.in column headers. Add these columns to your Screener query for best results:

| Metric | Screener Column Name |
|--------|----------------------|
| Company name | `Name` |
| Exchange code | `NSE Code` or `BSE Code` |
| Current price | `CMP Rs.` |
| Market cap | `Market Cap Rs.Cr.` |
| P/E | `P/E` |
| P/B | `P/B` |
| ROE | `ROE %` |
| ROCE | `ROCE %` |
| Debt/Equity | `Debt to equity` |
| Current ratio | `Current ratio` |
| Operating margin | `OPM %` |
| Net margin | `Net profit margin %` |
| Revenue growth 5Y | `Sales growth 5Years %` |
| Profit growth 5Y | `Profit growth 5Years %` |
| Revenue growth 10Y | `Sales growth 10Years %` |
| Profit growth 10Y | `Profit growth 10Years %` |
| Operating cash flow | `Cash from Operations Rs.Cr.` |
| Net profit (TTM) | `Net profit Rs.Cr.` |
| Total assets | `Total assets Rs.Cr.` |
| Promoter holding | `Promoter holding %` |
| Promoter pledge | `Promoter pledge %` |
| 52-week high | `52 Week High Rs.` |
| 52-week low | `52 Week Low Rs.` |
| Volume | `Volume` |
| 30-day avg volume | `30D Avg Volume` |
| F-Score (optional) | `Piotroski score` |

Missing columns are marked N/A per criterion and excluded from the score — they do not count against the stock.

---

## Project Structure

```
herrrickshaw/
├── backend/
│   ├── main.py                 FastAPI app + Cassandra lifespan
│   ├── requirements.txt
│   ├── db/
│   │   ├── cassandra_client.py
│   │   ├── seeder.py
│   │   ├── quote_updater.py
│   │   └── schema.cql
│   ├── parsers/
│   │   ├── excel_parser.py
│   │   ├── pdf_parser.py
│   │   ├── market_db.py
│   │   └── symbol_db.py
│   ├── fetchers/
│   │   └── live.py             RSI-14 · EMA-50 · yfinance
│   ├── scanners/
│   │   ├── darvas.py
│   │   ├── piotroski.py
│   │   └── coffee_can.py
│   └── routers/
│       ├── upload.py
│       ├── scan.py
│       ├── export.py
│       ├── live.py
│       ├── portfolio.py
│       ├── sectors.py
│       └── cassandra_router.py
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/
│           ├── Header.jsx          Cassandra status dot
│           ├── MarketTabs.jsx
│           ├── UploadPanel.jsx
│           ├── PortfolioUpload.jsx CMP + RSI Signal columns
│           ├── LivePanel.jsx
│           ├── ScanControls.jsx
│           ├── FilterSidebar.jsx
│           ├── ResultsTable.jsx    RSI Signal badge column
│           └── ScoreBadge.jsx
├── data/
│   ├── nse_equity_list.csv
│   ├── us_list.csv
│   ├── europe_list.csv
│   ├── japan_list.csv
│   ├── korea_list.csv
│   └── samples/
│       ├── nse_largecap_sample.csv
│       ├── nse_midcap_sample.csv
│       └── nasdaq_adr_sample.csv
├── put_call_parity/            Options arbitrage subsystem (BankNifty/Crude/Silver)
├── run_app.sh                  One-command start
└── CLAUDE.md                   Codebase guide
```
