# Quantitative Stock Analysis System

> Multi-market equity screening across **NSE/BSE, NASDAQ/NYSE, Europe, Japan, Korea, Singapore** —
> fundamentals, backtesting, ML signals, news sentiment, and mean-variance portfolio construction.

[![Security Scan](https://github.com/herrrickshaw/quant-stock-analysis/actions/workflows/security-scan.yml/badge.svg)](https://github.com/herrrickshaw/quant-stock-analysis/actions/workflows/security-scan.yml)

> **Note:** the fuel-retail / toll / export-trade material that previously lived here has
> been split into dedicated repos (see [Related repositories](#-related-repositories)).
> This repo is now **stock analysis only** — renamed from `Retail-outlet-data` (the old URL redirects).

---

## 📁 Repository layout

| Path | What's in it |
|---|---|
| `Downloads/code/python_files/` | Engine — 60+ Python modules (scanners, backtesting, ML, sentiment, MPT) + `strategies/` |
| `Downloads/code/notebooks/` | Colab/Jupyter notebooks (`Stock_Analysis_Colab.ipynb`, `US_Market_Screener_Colab.ipynb`, daily scans) |
| `Downloads/code/native/` | C-accelerated Darvas Box (`darvas_fast.c` / `.so` + wrapper) |
| `Downloads/code/backtesting/` | Backtesting research papers (PDF) |
| `nse_screener_reference/` | Reference OHLC cache (Nifty parquets), `symbol_master.parquet`, latest scan/backtest results |
| `docs/` | Jekyll GitHub Pages site (repo showcase, DISCOM calculator) |
| root `*.md` | System docs (`STOCK_ANALYSIS_SYSTEM.md`, `SCREENER_BASIS.md`, glossary, profile) |
| `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `entrypoint.sh` | Containerised execution |

---

## 🚀 Quick start
```bash
git clone https://github.com/herrrickshaw/quant-stock-analysis.git
cd quant-stock-analysis
pip install -r requirements.txt
cd Downloads/code/python_files
```

### Scanners
```bash
python full_indian_market_scan.py     # India (NSE + BSE)
python full_us_market_scan.py        # USA (NYSE + NASDAQ)
python full_european_market_scan.py  # Europe
python full_japan_market_scan.py     # Japan
python full_korea_market_scan.py     # South Korea
python run_global_analysis.py        # multi-market runner
```

### Reports, backtest, portfolio
```bash
python stock_daily_report_improved.py   # India daily report
python us_stock_daily_report.py         # US daily report
python daily_combined_report.py         # combined multi-market report
python backtest_screeners.py            # screener backtests
python walk_forward_backtest.py         # walk-forward validation
python portfolio_builder.py             # MPT / max-Sharpe portfolio
python ml_signal_engine.py              # ML-enhanced signals
python sentiment_pipeline.py            # news sentiment
python build_mailer.py && python send_mailer.py   # email digest
```

---

## 🎯 Screening strategies (`strategies/`)

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

## 🔗 Related repositories

| Repo | Domain |
|---|---|
| [`global-market-scanners`](https://github.com/herrrickshaw/global-market-scanners) | Focused 5-market scanner + industry/peer parquet dataset |
| [`fuel-retail-outlets`](https://github.com/herrrickshaw/fuel-retail-outlets) | India fuel/petrol retail outlet data, maps & gap analysis |
| [`toll-plaza-highways`](https://github.com/herrrickshaw/toll-plaza-highways) | Toll-plaza visualisation + toll↔outlet distance analysis |
| [`india-trade-export-analysis`](https://github.com/herrrickshaw/india-trade-export-analysis) | India import/export trade analysis 2020–2026 |

## 📄 Notes
Not investment advice. Screener output is for research only.
