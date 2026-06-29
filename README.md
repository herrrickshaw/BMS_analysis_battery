# Global Multi-Market Stock Analysis System

> **Quantitative screeners for NSE/BSE/NASDAQ/NYSE/EU/JP** with fundamental analysis, backtesting, and MPT portfolio optimization.

[![Security Scan](https://github.com/herrrickshaw/Retail-outlet-data/actions/workflows/security-scan.yml/badge.svg)](https://github.com/herrrickshaw/Retail-outlet-data/actions/workflows/security-scan.yml)

## 📊 System Overview

Comprehensive quantitative stock analysis framework supporting:
- **20 major exchanges** (NSE, BSE, NASDAQ, NYSE, Euronext, Tokyo Stock Exchange, Singapore Exchange, etc.)
- **10+ screening strategies** (Piotroski, Coffee Can, Magic Formula, GARP, Debt Reduction, Darvas Box)
- **Fundamental & technical analysis** via SEC EDGAR, Bloomberg-equivalent sources, and exchange feeds
- **Backtesting engine** with walk-forward validation
- **ML-enhanced signals** and sentiment analysis
- **Mean-variance portfolio construction** (MPT)

## 🚀 Quick Start

### Installation
```bash
git clone https://github.com/herrrickshaw/Retail-outlet-data.git
cd Retail-outlet-data
pip install -r requirements.txt
```

### Run Screener
```bash
# NSE/BSE batch analysis (305 stocks)
python Downloads/code/python_files/batch_analysis.py --excel

# All NSE+BSE (2,681 stocks)
python Downloads/code/python_files/batch_analysis.py --all-nse-bse

# US stocks (Dow30 + NASDAQ50)
python Downloads/code/python_files/us_stock_daily_report.py

# Global analysis
python Downloads/code/python_files/global_analysis_runner.py
```

### Daily Reports
- **Indian:** `Downloads/code/python_files/stock_daily_report_improved.py`
- **US:** `Downloads/code/python_files/us_stock_daily_report.py`
- **Global:** Multi-market runner with exchange-specific optimizations

---

## 📁 Architecture

```
Downloads/
├── code/python_files/
│   ├── batch_analysis.py              # 305-stock NSE/BSE screener
│   ├── stock_daily_report_improved.py # Nifty 50 batch reporter
│   ├── us_stock_daily_report.py       # NASDAQ/NYSE analysis
│   ├── global_analysis_runner.py      # 20-exchange multi-market
│   ├── sec_fundamentals.py            # SEC EDGAR data fetch
│   └── [screening_strategies]/        # Modular strategy implementations
├── data/
│   ├── stock_scan/                    # NSE/BSE scan results
│   ├── us_stocks/                     # NASDAQ/NYSE reports
│   ├── backtest/                      # Walk-forward analysis
│   ├── portfolio/                     # MPT optimization
│   └── cache/                         # OHLCV reference data
└── notebooks/
    └── analysis_templates/            # Jupyter notebooks (Colab-ready)
```

---

## 🎯 Screening Strategies

| Strategy | Criteria | Best For |
|----------|----------|----------|
| **Piotroski F-Score** | Profitability + quality | Quality growth |
| **Coffee Can** | ROE + $1B cap + FCF | Low-risk compounding |
| **Magic Formula** | EBIT/EV + ROC | Value + quality blend |
| **GARP** | Growth + reasonable P/E | Growth at reasonable price |
| **Debt Reduction** | Falling leverage + profit | Turnarounds |
| **Darvas Box** | Breakout + pullback | Momentum plays |
| **Technical Momentum** | RSI + MACD + trend | Short-term trends |
| **ML Signals** | Ensemble learners | Pattern recognition |

---

## 📚 Data Sources

### Indian Markets (NSE/BSE)
- **Exchange:** Official NSE/BSE equity universe feeds
- **OHLC:** yfinance, nsepython
- **Fundamentals:** BSE API, company websites
- **Cache:** LMDB + parquet for 2,681 stocks

### US Markets (NASDAQ/NYSE)
- **Universe:** 500 Dow30 + NASDAQ50 stocks
- **OHLC:** yfinance
- **Fundamentals:** SEC EDGAR XBRL (official regulatory filings)
- **Macro:** FRED (Federal Reserve Economic Data)

### Global Markets
- **EU:** Euronext (STOXX 600 seed)
- **Japan:** Tokyo Stock Exchange
- **Singapore/HK:** Regional exchanges
- **FX Rates:** ECB/Bank of England/FRED

### Reference Datasets
- **Damodaran Master List:** 48,156+ global companies
- **Ken French Factors:** 6 Fama-French factors
- **Industry Comps:** Sector-level benchmarks

---

## 🔒 Security & Quality

✅ **Weekly automated security scans** (secrets, vulnerabilities, credentials)  
✅ **Branch protection** on main (PR required, 1 review min)  
✅ **Force pushes disabled** on production branches  
✅ **Sensitive data excluded** via strict .gitignore  
✅ **Type hints & docstrings** (production-ready code)

---

## 📊 Sample Output

### Coffee Can (NSE 2024)
```
SCHNEIDER    PRICE: ₹172.50  ROE: 28.2%  FCF: 2.4B  CONFIDENCE: ★★★★★
VBL          PRICE: ₹1,280   ROE: 34.1%  FCF: 890M  CONFIDENCE: ★★★★★
MASTEK       PRICE: ₹3,420   ROE: 26.8%  FCF: 412M  CONFIDENCE: ★★★★★
```

### Magic Formula (NASDAQ Q3)
```
AAPL         EBIT/EV: 0.18   ROC: 0.42   RANK: #1
MSFT         EBIT/EV: 0.19   ROC: 0.38   RANK: #2
```

---

## 🛠️ Development

### Local Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest Downloads/code/python_files/tests/

# Type checking
mypy Downloads/code/python_files/
```

### Notebooks (Colab-Ready)
```python
# In Google Colab
!git clone https://github.com/herrrickshaw/Retail-outlet-data.git
%cd Retail-outlet-data
exec(open('Downloads/code/notebooks/setup.py').read())
```

---

## 📖 Documentation

- **[Data & Modules](./Downloads/code/python_files/DATA_AND_MODULES.md)** — Detailed module reference
- **[Bloomberg Equivalents](./Downloads/code/python_files/BLOOMBERG_SOURCES.md)** — Free data source mapping
- **[Exchange Universe](./EXCHANGE_UNIVERSE.md)** — Live NSE/BSE/global symbols
- **[nsepython API](./MEMORY.md#nsepython)** — Indian market data API reference

---

## 🤝 Contributing

Issues and PRs welcome! Security reports: → GitHub Security tab

---

## 📄 License

MIT License — See LICENSE file

---

## 📞 Contact

**Author:** Umashankar  
**Email:** umashankartd1991@gmail.com  
**GitHub:** [@herrrickshaw](https://github.com/herrrickshaw)

---

## 📋 Changelog

See [CHANGELOG.md](./CHANGELOG.md) for release history.

**Latest:** Global multi-market analysis (20 exchanges) + SEC EDGAR fundamentals for US + Bloomberg-equivalent sources map
