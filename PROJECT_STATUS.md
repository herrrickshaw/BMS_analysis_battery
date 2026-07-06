# Project Status Dashboard

**Last Updated:** June 29, 2026  
**Repository:** [herrrickshaw/Retail-outlet-data](https://github.com/herrrickshaw/Retail-outlet-data)

---

## 🎯 Current Focus

### Active Development: Global Multi-Market Stock Analysis System
**Status:** ✅ Production-Ready  
**Last Commit:** `feat: Bloomberg-equivalent public sources; SEC EDGAR fundamentals for US`

---

## 📊 System Metrics

| Metric | Value | Status |
|--------|-------|--------|
| **Supported Exchanges** | 20 major (NSE, BSE, NASDAQ, NYSE, EU, JP, SG, HK, etc.) | ✅ Complete |
| **Indian Stocks** | 2,681 (NSE: 2,364 + BSE-only: 317) | ✅ Live |
| **US Stocks** | 50+ (Dow30 + NASDAQ) | ✅ Live |
| **EU/Global** | 878+ (Euronext + regional) | ✅ Live |
| **Screening Strategies** | 10+ modular strategies | ✅ Implemented |
| **Data Sources** | Bloomberg-equivalent + official feeds | ✅ Mapped |
| **Backtesting** | Walk-forward validation | ✅ Active |
| **Security Scans** | Weekly automated | ✅ Enabled |

---

## 🚀 Core Features

### ✅ Implemented
- [x] NSE/BSE batch screener (305 stocks, 2,681 all)
- [x] US stock analysis (NASDAQ/NYSE)
- [x] Global multi-market runner (20 exchanges)
- [x] Fundamental analysis (SEC EDGAR, Damodaran)
- [x] Technical indicators (RSI, MACD, Bollinger Bands, Darvas Box)
- [x] Coffee Can strategy (ROE + $1B cap + FCF)
- [x] Magic Formula (EBIT/EV + ROC)
- [x] Piotroski F-Score
- [x] GARP screening
- [x] Debt Reduction strategy
- [x] Backtesting engine
- [x] MPT portfolio construction
- [x] Sentiment analysis (news RSS feeds)
- [x] LMDB + Parquet caching
- [x] yfinance + nsepython integration

### 🔄 In Progress
- [ ] ML ensemble classifiers (Piotroski + fundamentals)
- [ ] Real-time data streaming (WebSocket feeds)
- [ ] Live notification alerts
- [ ] Web dashboard (interactive charts)

### 📋 Planned
- [ ] Options analytics (Black-Scholes, Greeks)
- [ ] Corporate action handling (splits, dividends)
- [ ] Earnings seasonality analysis
- [ ] Cross-market arbitrage detection

---

## 📁 Key Files

### Analysis Engines
| File | Purpose | Status |
|------|---------|--------|
| `batch_analysis.py` | NSE/BSE 305 + 2,681 stock screener | ✅ Production |
| `stock_daily_report_improved.py` | Nifty 50 daily batch | ✅ Production |
| `us_stock_daily_report.py` | NASDAQ/NYSE daily | ✅ Production |
| `global_analysis_runner.py` | 20-exchange multi-market | ✅ Production |
| `sec_fundamentals.py` | SEC EDGAR XBRL extraction | ✅ Production |

### Data Caches
| Path | Content | Size | Update |
|------|---------|------|--------|
| `Downloads/data/cache/` | OHLCV reference data | 530 MB | Daily |
| `Downloads/data/stock_scan/` | NSE/BSE scan results | Variable | Per run |
| `Downloads/data/us_stocks/` | NASDAQ results | Variable | Per run |

### Reference Data (Git LFS)
- `data/seeds/NSE_2364.csv` — Live NSE symbols
- `data/seeds/BSE_317.csv` — BSE-only symbols
- `data/seeds/NASDAQ_50.csv` — US sample
- `data/seeds/Damodaran_48156.xls` — Global companies
- `data/seeds/Euronext_878.csv` — EU stocks

---

## 🔒 Security Status

### ✅ Implemented Protections
- [x] Branch protection on `main` (PR required, 1 review minimum)
- [x] No force pushes allowed
- [x] No branch deletions allowed
- [x] Admin bypass disabled
- [x] Secrets removed from git history (password wordlist eliminated)
- [x] Strict .gitignore (credentials, configs, personal data excluded)
- [x] Weekly automated security scans (detect-secrets, truffleHog, safety, bandit)

### 🛡️ Scan Results (Latest Run)
- **Secrets detected:** 0
- **Vulnerable dependencies:** Green
- **Code security issues:** None critical

### 📅 Security Scan Schedule
- **Frequency:** Weekly (Sundays, 2:00 AM UTC / 9:30 AM IST)
- **Manual trigger:** `gh workflow run security-scan.yml`
- **Reports:** GitHub Actions Artifacts (30-day retention)

---

## 📈 Performance

### Analysis Speed
| Operation | Time | Notes |
|-----------|------|-------|
| NSE 305 screener | ~8 min | Batch mode, all 10 strategies |
| NSE/BSE all (2,681) | ~45 min | Full universal run |
| US 50-stock scan | ~3 min | NASDAQ/Dow30 |
| Global 20-exchange | ~25 min | Multi-market aggregation |

### Data Freshness
- **NSE/BSE:** Updated daily (market close)
- **NASDAQ/NYSE:** Updated daily (market close)
- **EU/Global:** Updated on exchange-specific schedules
- **Fundamental:** Updated quarterly (SEC filings, annual updates)

---

## 🐛 Known Limitations

### Data Sources
- **nsepython:** Fails on Mac (requires browser cookies); use yfinance instead
- **yfinance:** Rate limiting (~2000 req/day); batching required
- **debtToEquity:** Sometimes >10; normalize by /100

### Strategies
- **Darvas Box:** Always exclude current bar from formation (else breakdown detection fails)
- **Options:** SEC filing delays (1-2 days after close)
- **Sentiment:** RSS feed-dependent; no consensus/estimates (proprietary)

### Geographic
- **Chinese exchanges:** Limited free data (use Yahoo's .SS/.SZ mappings)
- **Indian mid/small caps:** Lower yfinance coverage vs. NSE API

---

## 🔗 Documentation Map

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](./README.md) | System overview & quick start | All users |
| [PROJECT_STATUS.md](./PROJECT_STATUS.md) | This — current metrics & status | Developers |
| [ARCHIVED_PROJECTS.md](./ARCHIVED_PROJECTS.md) | Inactive branches & old projects | Reference |
| [DATA_AND_MODULES.md](./Downloads/code/python_files/DATA_AND_MODULES.md) | Module reference | Developers |
| [BLOOMBERG_SOURCES.md](./Downloads/code/python_files/BLOOMBERG_SOURCES.md) | Free data source mapping | Data engineers |
| [CHANGELOG.md](./CHANGELOG.md) | Release history | All |

---

## 🤝 Contribution Guidelines

### Before Committing
1. ✅ Type hints on all functions
2. ✅ Docstrings (one-line for simple, multi-line for complex)
3. ✅ No secrets/credentials in code
4. ✅ Run `mypy Downloads/code/python_files/` locally
5. ✅ Test with sample data

### PR Requirements
- Requires 1 code review (anyone can approve)
- Must pass security scans
- No force pushes
- Commit message format:
  ```
  category: brief description
  
  Longer explanation if needed.
  ```

---

## 📞 Support & Contact

**Questions?**
- 📧 Email: umashankartd1991@gmail.com
- 🐙 GitHub Issues: [Create Issue](https://github.com/herrrickshaw/Retail-outlet-data/issues)
- 🔒 Security: Use GitHub Security tab for sensitive reports

---

## 📋 Quick Reference

### Run Commands
```bash
# Indian (NSE/BSE)
python Downloads/code/python_files/batch_analysis.py --excel       # 305 stocks
python Downloads/code/python_files/batch_analysis.py --all-nse-bse # 2,681 stocks

# US (NASDAQ/Dow30)
python Downloads/code/python_files/us_stock_daily_report.py

# Global (20 exchanges)
python Downloads/code/python_files/global_analysis_runner.py

# Security scan (manual)
gh workflow run security-scan.yml
```

### View Latest Results
```bash
# Last NSE scan
ls -lt Downloads/data/stock_scan/*_results.xlsx | head -1

# Last NASDAQ scan
ls -lt Downloads/data/us_stocks/ | head -5
```

---

**Status:** ✅ All systems operational | 🔒 Security: Green | 📊 Data: Fresh
