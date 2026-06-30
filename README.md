# Retail-outlet-data

> A combined research monorepo with two halves:
> **(1)** a multi-market **quantitative stock-analysis system**, and
> **(2)** **India petroleum / fuel retail-outlet + toll-plaza geospatial data** and trade-export analysis.

[![Security Scan](https://github.com/herrrickshaw/Retail-outlet-data/actions/workflows/security-scan.yml/badge.svg)](https://github.com/herrrickshaw/Retail-outlet-data/actions/workflows/security-scan.yml)

---

## 📁 Repository layout

| Path | What's in it |
|---|---|
| `Downloads/code/python_files/` | The stock-analysis engine — 60+ Python modules (screeners, backtesting, ML, sentiment, MPT) + `strategies/` |
| `Downloads/code/notebooks/` | Colab/Jupyter notebooks (`Stock_Analysis_Colab.ipynb`, `US_Market_Screener_Colab.ipynb`, daily scan reports) |
| `Downloads/code/native/` | C-accelerated Darvas Box (`darvas_fast.c` / `.so` + Python wrapper) |
| `Downloads/code/backtesting/` | Backtesting research papers (PDF) |
| `nse_screener_reference/` | Reference OHLC cache (Nifty parquets), `symbol_master.parquet`, latest scan/backtest results |
| `api-data-integration/` | **Fuel retail outlet feeds** — BPCL dealerships, CashAtPOS fuel stations, SSRI pumps (geojson/json/csv, state-wise) |
| `outlet_data_bpcl_complete/` | Complete BPCL dealership dumps (geojson + summaries) |
| `fuel-pump-locations-map/` | Interactive web map of fuel pump / retail outlet locations |
| `fuel-station-gap-analysis/` | Fuel-station coverage **gap-analysis heatmap** dashboard |
| `toll-plaza-visualization/` | Toll-plaza dashboards + toll↔retail-outlet distance analysis (highways) |
| `export-analysis/` | India import/export trade analysis 2020–2026 (RBI reserves, fiscal, opportunities) |
| `data-sources/` | Retail-outlet & market data-source references |
| `docs/` | Jekyll GitHub Pages site (repo showcase, DISCOM calculator) |
| root `*.md` | System docs (`STOCK_ANALYSIS_SYSTEM.md`, `SCREENER_BASIS.md`, `TOLL_RETAIL_*`, `SSRI_*`, glossary, profile) |
| `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `entrypoint.sh` | Containerised execution |

---

## 📊 Part 1 — Quantitative stock analysis

Multi-market equity screening across **NSE/BSE, NASDAQ/NYSE, Europe, Japan, Korea, Singapore**, with fundamentals, backtesting, ML signals, news sentiment, and mean-variance portfolio construction.

### Install
```bash
git clone https://github.com/herrrickshaw/Retail-outlet-data.git
cd Retail-outlet-data
pip install -r requirements.txt
```

### Run the scanners
```bash
cd Downloads/code/python_files

python full_indian_market_scan.py        # India (NSE + BSE)
python full_us_market_scan.py            # USA (NYSE + NASDAQ)
python full_european_market_scan.py      # Europe
python full_japan_market_scan.py         # Japan
python full_korea_market_scan.py         # South Korea
python run_global_analysis.py            # multi-market runner
```

### Reports, backtest, portfolio
```bash
python stock_daily_report_improved.py    # India daily report
python us_stock_daily_report.py          # US daily report
python daily_combined_report.py          # combined multi-market report
python backtest_screeners.py             # screener backtests
python walk_forward_backtest.py          # walk-forward validation
python portfolio_builder.py              # MPT / max-Sharpe portfolio
python ml_signal_engine.py               # ML-enhanced signals
python sentiment_pipeline.py             # news sentiment
python build_mailer.py && python send_mailer.py   # email digest
```

### Screening strategies (`strategies/`)

| Strategy | Module |
|---|---|
| Piotroski F-Score | `piotroski.py` |
| Coffee Can | `coffee_can.py` |
| Magic Formula | `magic_formula.py` |
| GARP | `garp.py` |
| Debt Reduction | `debt_reduction.py` |
| Darvas Box | `darvas.py` |
| Golden Crossover | `golden_crossover.py` |
| Dividend Yield | `dividend_yield.py` |
| Cash Conversion Cycle | `cash_conversion_cycle.py` |
| Loss-to-Profit | `loss_to_profit.py` |
| Bluest Blue Chips | `bluest_blue_chips.py` |

---

## ⛽ Part 2 — Retail outlet, toll & trade data

India petroleum retail-network and highway infrastructure data, plus trade-export analysis.

- **Fuel retail outlets** (`api-data-integration/`, `outlet_data_bpcl_complete/`) — BPCL dealerships, CashAtPOS fuel stations, and SSRI pump data pulled and normalised to geojson/json/csv with state-wise summaries. Source notes in `data-sources/RETAIL_OUTLETS_DATA_SOURCES.md`.
- **Maps & gap analysis** (`fuel-pump-locations-map/`, `fuel-station-gap-analysis/`) — self-contained static web apps. Run with `python3 -m http.server` from each folder.
- **Toll plazas / highways** (`toll-plaza-visualization/`) — `toll_plaza_dashboard.py` and visualisation scripts; toll↔retail-outlet distance work documented in `TOLL_RETAIL_DISTANCE_ANALYSIS_SUMMARY.md`.
- **Export analysis** (`export-analysis/`) — India import/export 2020–2026, RBI reserves vs trade deficit, high-opportunity export projections (`export_analysis.py`, `export_extended_analysis.py`, CSV/MD outputs).

---

## 🔗 Related repositories

- [`global-market-scanners`](https://github.com/herrrickshaw/global-market-scanners) — the focused 5-market scanner + industry/peer parquet dataset
- [`retail-outlet-monitoring`](https://github.com/herrrickshaw/retail-outlet-monitoring) — standalone fuel-station gap-analysis + locations map

## 📄 Notes
- Outlet/toll datasets are sourced from public OMC / petroleum-retail listings; treat as indicative for planning and visualisation, not an official registry.
- Not investment advice. Screener output is for research only.
