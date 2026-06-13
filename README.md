# Stock Screener

A full-stack investment research app that applies three scan frameworks — **Darvas Box**, **Piotroski F-Score**, and **Coffee Can Portfolio** — to Screener.in CSV exports across five markets.

---

## Quick Start

```bash
# One-command start (installs deps automatically)
./run_app.sh

# Or manually:
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

| Service  | URL |
|---|---|
| Web app  | http://localhost:5173 |
| API      | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

---

## Demo with Sample Data

Three sample CSVs are included in `data/samples/`:

| File | Market Tab to Use |
|---|---|
| `nse_largecap_sample.csv` | NSE Large Cap |
| `nse_midcap_sample.csv` | NSE Mid Cap |
| `nasdaq_adr_sample.csv` | NASDAQ ADRs |

Steps:
1. Open http://localhost:5173
2. Click the **NSE Large Cap** tab
3. Upload `data/samples/nse_largecap_sample.csv`
4. Click **Run All Scans**
5. Switch between Darvas / Piotroski / Coffee Can views in the scan panel

---

## How to Export from Screener.in

1. Go to https://www.screener.in/screens/
2. Create or open a query (e.g. "NIFTY 500")
3. Add the columns listed below under **Column Mapping**
4. Click **Export** → CSV
5. Upload that CSV to the matching market tab

One CSV per market tab. You can re-upload at any time; the new data replaces the old for that market.

---

## Column Mapping

The app auto-detects Screener.in column headers. Add these to your Screener query for best results:

| Metric | Screener Column Name |
|---|---|
| Company name | `Name` |
| Exchange code | `NSE Code` or `BSE Code` |
| Current price | `CMP Rs.` |
| Market cap | `Market Cap Rs.Cr.` |
| P/E ratio | `P/E` |
| P/B ratio | `P/B` |
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

Missing columns are handled gracefully — the criterion is marked N/A and excluded from the score.

---

## The Three Scan Engines

### 1. Darvas Box (Score 0–10)

Combines Nicholas Darvas's price/momentum boxes with Warren Buffett's quality overlay.

**Criteria (1 point each):**

| # | Criterion | Threshold |
|---|---|---|
| C1 | Price near 52W high | CMP within 3% of 52W High |
| C2 | Volume breakout | Today's volume ≥ 1.5× 30-day average |
| C3 | Above box floor | CMP ≥ 85% of 52W High |
| C4 | Consistent ROE | ROE > 15% |
| C5 | Profit margin | Net/Operating margin > 10% |
| C6 | Low debt | D/E < 0.5 |
| C7 | Promoter conviction | Promoter holding > 50% |
| C8 | EPS growth | 5Y profit growth > 10% |
| C9 | Fair valuation | P/E < 1.5× sector P/E (or P/E < 35 absolute) |
| C10 | Price strength | CMP in upper half of 52W range |

**Colour codes:** Score ≥ 7 → **Green BUY** · 4–6 → **Amber WATCH** · < 4 → **Red AVOID**

---

### 2. Piotroski F-Score (Score 0–9)

Classic 9-point financial strength score. Uses Screener.in's pre-computed score when available.

**Profitability (4 points):**
- F1: ROA > 0
- F2: Operating cash flow > 0
- F3: ROA improving YoY *(requires two-period data; N/A in snapshot mode)*
- F4: OCF/Assets > ROA (cash earnings beat reported earnings)

**Leverage & Liquidity (3 points):**
- F5: D/E < 0.5 *(proxy for decreasing long-term debt)*
- F6: Current ratio > 1.5 *(proxy for improved liquidity)*
- F7: No new share issuance *(requires historical share count; N/A in snapshot mode)*

**Operating Efficiency (2 points):**
- F8: Operating margin > 20% *(proxy for gross margin improvement)*
- F9: Asset turnover > 0.5 *(or ROE > 15% as fallback)*

**Colour codes:** Score 8–9 → **Dark Green BUY ★** · 6–7 → **Amber WATCH** · ≤ 5 → **Red AVOID**

> **Tip:** Include the `Piotroski score` column in your Screener export. When present, it uses Screener's own full calculation (more accurate than snapshot approximation).

---

### 3. Coffee Can Portfolio (Pass / Fail + Moat 0–5)

Saurabh Mukherjea's framework for buy-and-hold forever stocks. All six hard filters must pass.

**Hard Filters (all must pass):**

| Filter | Threshold |
|---|---|
| Revenue CAGR | > 10% (10Y → 5Y → 3Y fallback) |
| Profit CAGR | > 10% (same fallback) |
| ROCE | > 15% |
| Debt/Equity | < 1 throughout |
| Promoter pledge | < 10% |
| Market cap | > ₹100 Cr (or $100M for ADRs) |

**Moat Score (0–5 bonus):**

| Signal | Points |
|---|---|
| OPM > 40% | +2 |
| OPM 25–40% | +1 |
| ROE > 20% | +1 |
| ROCE > 25% | +1 |
| D/E < 0.3 | +1 |

**Colour codes:** All filters pass → **Green ✓ Pass** · Any filter fails → **Red ✗ Fail**

> Note: Banks and NBFCs naturally fail the D/E filter (financial leverage). Coffee Can is designed for non-financial businesses.

---

## Architecture

```
backend/                    FastAPI (Python 3.9+)
├── main.py                 App entry + CORS
├── column_map.py           Screener header normaliser (40+ aliases per field)
├── scanners/
│   ├── darvas.py           Darvas + Buffett overlay
│   ├── piotroski.py        9-point F-Score
│   └── coffee_can.py       Hard filters + moat score
└── routers/
    ├── upload.py           POST /api/upload
    ├── scan.py             POST /api/scan/{darvas|piotroski|coffee_can|all}
    └── export.py           GET  /api/export  (Excel download)

frontend/                   React 18 + Vite + Tailwind CSS
└── src/
    ├── App.jsx             State, filters, API wiring
    └── components/
        ├── MarketTabs      5-tab market selector
        ├── UploadPanel     Drag-drop CSV upload
        ├── ScanControls    Per-scan run buttons
        ├── FilterSidebar   Signal + numeric sliders
        ├── ResultsTable    Sortable + expandable criteria breakdown
        └── ScoreBadge      Scan-type-aware colour coding
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload?market=nse_largecap` | Upload CSV/Excel for a market |
| `GET` | `/api/markets` | List uploaded markets and row counts |
| `POST` | `/api/scan/{scan_type}?market=nse_largecap` | Run scan (`darvas`, `piotroski`, `coffee_can`, or `all`) |
| `GET` | `/api/results?market=nse_largecap&scan_type=all` | Fetch results with optional filters |
| `GET` | `/api/export?market=nse_largecap&scan_type=all` | Download Excel with all scan sheets |

---

## Filter Sliders

| Slider | What it filters |
|---|---|
| Signal | Toggle BUY / WATCH / AVOID rows |
| Min Market Cap | Hide stocks below a market cap threshold |
| Max P/E | Exclude expensive stocks |
| Min ROE % | Minimum return on equity |
| Max D/E | Maximum leverage |
| Min Data Completeness | Exclude stocks with too many N/A criteria |

Filters are applied client-side on already-scanned results — no need to re-run scans after adjusting.

---

## Project Structure

```
herrrickshaw/
├── backend/                FastAPI backend
├── frontend/               React frontend
├── data/
│   └── samples/            Demo CSVs (NSE Large Cap, Mid Cap, NASDAQ ADRs)
├── run_app.sh              Start both servers
├── ASSUMPTIONS.md          Design decisions and approximations
└── CLAUDE.md               Codebase guide for Claude Code
```

The original scripts (`nse_bse_extractor.py`, `portfolio_analysis.py`, `pegu_sarvas_analysis.R`, `put_call_parity/`) remain in the repo alongside the web app.
