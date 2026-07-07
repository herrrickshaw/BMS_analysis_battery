# 📊 Portfolio Analyzer - Complete User Guide

A comprehensive portfolio analysis and evaluation tool supporting multi-market analysis (India, US, Europe, Japan, Korea, China). Provides real-time metrics, quality scoring, rebalancing recommendations, and tax efficiency analysis.

---

## ⚡ Quick Start (2 minutes)

### 1. Install & Run

```bash
# Make startup script executable
chmod +x run_portfolio_analyzer.sh

# Start the portfolio analyzer
./run_portfolio_analyzer.sh
```

This will:
- Create a Python virtual environment
- Install all dependencies
- Start the FastAPI backend on http://127.0.0.1:8001
- Display the dashboard URL to open in your browser

### 2. Open Dashboard

Open in your browser:
```
file:///Users/umashankar/stock-screener/portfolio_dashboard.html
```

### 3. Load Portfolio

**Option A: Use Sample Data**
- Click "Load Sample" button to test with 20-stock sample portfolio

**Option B: Upload Your Data**
- Prepare a CSV or Excel file with your portfolio
- Click "Upload Portfolio" and select your file
- Dashboard auto-refreshes with your data

---

## 📋 Portfolio File Format

### Required Columns

| Column | Type | Format | Example |
|--------|------|--------|---------|
| `ticker` | String | Stock ticker | `HDFCBANK`, `AAPL`, `ADS.DE` |
| `quantity` | Number | Shares held | `10`, `5.5` |
| `purchase_price` | Number | Per-share price | `1500`, `180.50` |
| `purchase_date` | Date | Purchase date | `2023-01-15`, `2024-07-07` |
| `market` | String | Market code | `india`, `us`, `europe`, `japan`, `korea`, `china` |

### Optional Columns

| Column | Type | Example |
|--------|------|---------|
| `sector` | String | `banking`, `tech`, `energy`, etc. |
| `current_price` | Number | Current price (fetched if not provided) |

### Example CSV Format

```csv
ticker,quantity,purchase_price,purchase_date,market,sector
HDFCBANK,10,1500,2023-01-15,india,banking
RELIANCE,5,2800,2023-02-20,india,energy
AAPL,5,180,2023-11-10,us,tech
ADS.DE,8,180,2024-04-05,europe,auto
7203.T,25,2400,2023-08-14,japan,auto
005930.KS,30,55000,2023-09-09,korea,tech
```

### Example Excel Format

Same columns as CSV, save as `.xlsx` or `.xls`

---

## 🎯 Dashboard Features

### Overview Tab
- **Summary Cards**: Total invested, current value, gain/loss, holding count
- **Risk Metrics**:
  - Concentration Ratio: Largest single position (target: <10%)
  - Diversification Ratio: Effective number of positions (higher is better)
  - Herfindahl Index: Portfolio concentration score (0-1)
- **Income Metrics**:
  - Dividend Yield: Annual dividend as % of portfolio
  - Estimated Annual Dividend: Total rupees expected
- **Market Exposure**: Geographic breakdown (India, US, Europe, Japan, Korea)

### Holdings Tab
Complete stock-by-stock breakdown:
- Ticker & market classification
- Quantity, cost basis, current value
- Unrealized gain/loss (₹ and %)
- Portfolio allocation %
- Days held (for LTCG eligibility tracking)

### Quality Tab
Position quality evaluation:
- P/E Ratio: Valuation metric
- P/B Ratio: Price-to-book comparison
- ROE: Return on equity %
- Dividend Yield: Annual dividend %
- **Quality Score** (0-100): Composite score based on:
  - P/E ratio in healthy range (8-25)
  - Low P/B ratio (≤3)
  - Strong ROE (>15%)
  - Dividend presence (>1%)
  - Market cap >$1B

### Rebalancing Tab
- **Overweight Positions** (>10%):
  - Identifies concentration risk
  - Shows current value and allocation %
  - Recommends reduction target
  
- **Tax Implications**:
  - Unrealized gains per position
  - Holding period (days)
  - Tax status (STCG vs LTCG)
  - Estimated tax if sold now
  - India: LTCG @ 20%, STCG @ slab rate

### Sectors Tab
- Sector-wise allocation breakdown
- Value and % of portfolio per sector
- Average gain/loss per sector
- Stock count per sector

### Alerts Tab
Actionable alerts ranked by severity:

**🔴 HIGH**: 
- Concentration >15% (CRITICAL)
- Immediate action recommended

**🟡 MEDIUM**:
- Overweight positions requiring trim
- High STCG tax implications
- Sector concentration >30%

**🔵 LOW**:
- Dividend yield below target
- Diversification opportunities

---

## 🛠️ CLI Tool Usage

### Basic Analysis

```bash
# Analyze portfolio and generate report
python portfolio_analyzer.py --file portfolio.csv --output report.json

# Fetch current prices and fundamentals
python portfolio_analyzer.py --file portfolio.csv \
  --fetch-prices --fetch-fundamentals

# Export results to CSV
python portfolio_analyzer.py --file portfolio.csv \
  --export-csv analysis.csv
```

### Command Options

```
--file              Portfolio file (CSV or Excel) [REQUIRED]
--output            Output JSON file [default: portfolio_report.json]
--fetch-prices      Fetch current prices from yfinance
--fetch-fundamentals Fetch PE, PB, ROE, dividend data
--export-csv        Export portfolio to CSV file
```

---

## 📊 API Endpoints (For Integration)

All endpoints return JSON. Base URL: `http://127.0.0.1:8001`

### Portfolio Management

**POST /portfolio/upload**
Upload portfolio file (CSV/Excel)
```bash
curl -F "file=@portfolio.csv" http://127.0.0.1:8001/portfolio/upload
```

**POST /portfolio/load-sample**
Load 20-stock sample portfolio for testing
```bash
curl -X POST http://127.0.0.1:8001/portfolio/load-sample
```

**GET /portfolio/status**
Quick portfolio status
```bash
curl http://127.0.0.1:8001/portfolio/status
```

### Analysis Endpoints

**GET /portfolio/metrics**
Complete portfolio metrics
```bash
curl http://127.0.0.1:8001/portfolio/metrics
```

**GET /portfolio/holdings**
Detailed holdings with sort options
```bash
# Sort by allocation %
curl http://127.0.0.1:8001/portfolio/holdings?sort_by=allocation_pct

# Sort by gain/loss %
curl http://127.0.0.1:8001/portfolio/holdings?sort_by=gain_loss_pct
```

**GET /portfolio/quality**
Position quality scores
```bash
curl http://127.0.0.1:8001/portfolio/quality
```

**GET /portfolio/rebalancing**
Rebalancing opportunities and tax implications
```bash
# Default max position 10%
curl http://127.0.0.1:8001/portfolio/rebalancing

# Custom threshold (15%)
curl http://127.0.0.1:8001/portfolio/rebalancing?max_position_pct=15
```

**GET /portfolio/sectors**
Sector-wise allocation
```bash
curl http://127.0.0.1:8001/portfolio/sectors
```

**GET /portfolio/alerts**
Portfolio alerts and recommendations
```bash
curl http://127.0.0.1:8001/portfolio/alerts
```

**GET /portfolio/report**
Complete analysis report (JSON)
```bash
curl http://127.0.0.1:8001/portfolio/report
```

### Data Fetching

**POST /portfolio/fetch-prices**
Update current prices from yfinance
```bash
curl -X POST http://127.0.0.1:8001/portfolio/fetch-prices
```

**POST /portfolio/fetch-fundamentals**
Fetch fundamental data (PE, PB, ROE, etc.)
```bash
curl -X POST http://127.0.0.1:8001/portfolio/fetch-fundamentals
```

### Analysis

**POST /portfolio/analyze-stock**
Analyze single stock
```bash
curl "http://127.0.0.1:8001/portfolio/analyze-stock?ticker=HDFCBANK&market=india"
```

**GET /portfolio/comparison**
Compare with benchmark
```bash
curl http://127.0.0.1:8001/portfolio/comparison?benchmark=nifty50
```

---

## 💡 Key Metrics Explained

### Concentration Ratio
Percentage of portfolio in largest position
- **Safe**: <10%
- **Caution**: 10-15%
- **Risk**: >15%

### Diversification Ratio
Effective number of equal-weight positions
- **Formula**: 1 / Herfindahl Index
- **Example**: Ratio of 5 = portfolio as diversified as 5 equal positions

### Herfindahl Index
Portfolio concentration (0-1 scale)
- **0**: Perfectly diversified
- **1**: Single stock
- **0.25**: Moderate concentration
- **Target**: <0.15

### Quality Score
Composite measure (0-100)
- PE ratio reasonable (8-25)
- PB ratio low (≤3)
- ROE strong (>15%)
- Dividend present (>1%)
- Market cap large (>$1B)
- **Score ≥60**: Good quality
- **Score ≥80**: Excellent quality

### Dividend Yield
Annual dividend as % of current portfolio value
```
Dividend Yield = (Annual Dividend Income / Portfolio Value) × 100
```
- **Target**: 2-3%
- **Above-average**: >3%

### Holding Period (LTCG Eligibility)
Days since purchase, determines tax treatment
- **<365 days**: STCG (short-term capital gain) @ slab rate
- **≥365 days**: LTCG (long-term capital gain) @ 20%
- **India equity**: Flat 20% tax on LTCG

---

## 🔄 Typical Workflow

### Week 1: Upload & Analyze
1. Prepare portfolio CSV with current holdings
2. Upload via dashboard
3. Review Overview tab for summary health
4. Check Alerts tab for critical issues
5. Identify concentration risks

### Week 2: Deep Dive
1. Review Holdings tab for individual positions
2. Check Quality tab for valuation metrics
3. Examine Rebalancing tab for overweight positions
4. Review tax implications before selling

### Week 3: Action Plan
1. Note overweight positions requiring trim
2. Identify underweight sectors to build
3. Plan rebalancing sequence (minimize tax)
4. Set target allocation per sector
5. Plan trades over coming month

### Ongoing: Monitor
1. Update prices weekly (button: "Update Prices")
2. Review alerts for new issues
3. Track dividend dates
4. Monitor for LTCG eligibility milestones
5. Rebalance quarterly

---

## 🎯 Sample Analysis Scenarios

### Scenario 1: Concentration Risk
**Problem**: Maruti at 28.4% of portfolio (>10% threshold)
**Dashboard Alert**: HIGH severity - concentration risk
**Recommended Action**:
1. Go to Rebalancing tab
2. Note Maruti position
3. Plan staged sales (sell 20% per week)
4. Check Tax Implications for unrealized gains
5. Deploy proceeds to underweight sectors

### Scenario 2: Dividend Optimization
**Problem**: 1.49% dividend yield vs 2.5% target
**Dashboard Alert**: LOW severity - income opportunity
**Recommended Action**:
1. Go to Alerts tab → "Add dividend-paying stocks"
2. Review Sectors tab → identify low-yield sectors
3. Check Quality tab → identify high-dividend stocks
4. Plan positions: REC, GAIL, Coal India, Power Grid
5. Add ₹1-2L in high-yield stocks

### Scenario 3: Tax Efficiency
**Problem**: High STCG on recent gains (20-30% unrealized)
**Dashboard Alert**: MEDIUM severity - tax implications
**Recommended Action**:
1. Go to Rebalancing tab → Tax Implications
2. Filter positions with STCG status
3. Hold until 365 days for LTCG (20% vs ~30% tax)
4. Or harvest losses to offset gains
5. Use dry powder for new investments

### Scenario 4: Sector Rebalancing
**Problem**: Banking 35%, Consumer 1.5% (imbalanced)
**Dashboard Alert**: LOW severity - sector concentration
**Recommended Action**:
1. Go to Sectors tab
2. Identify overweight banking (trim weak performers)
3. Identify underweight consumer (build ITC/HUL)
4. Use rebalancing proceeds for new sectors
5. Target: Banking 20%, Consumer 8-10%

---

## ⚙️ Configuration

### Market Ticker Formats

| Market | Format | Example |
|--------|--------|---------|
| India | Bare NSE symbol | `HDFCBANK`, `RELIANCE` |
| USA | Bare ticker | `AAPL`, `MSFT` |
| Europe | Pre-suffixed | `ADS.DE`, `SAP.DE`, `RIO.L` |
| Japan | Pre-suffixed | `7203.T`, `8306.T` |
| Korea | Pre-suffixed | `005930.KS`, `000660.KS` |
| China | Pre-suffixed | `600519.SS`, `601966.SS` |

### Tax Rates (India)
- **LTCG (Equity)**: Flat 20%
- **STCG (Equity)**: As per income slab (10%, 20%, 30%)
- **Dividend**: TDS @ 10% (if no PAN), else no tax
- **Holding period**: 365 days for LTCG eligibility

---

## 🐛 Troubleshooting

### "Failed to fetch prices"
- **Cause**: yfinance API issue or network timeout
- **Solution**: 
  - Retry after 5 minutes
  - Check internet connection
  - Verify ticker format (especially Europe/Japan)
  - Use manually entered prices if API fails

### "Upload failed: Unsupported file format"
- **Cause**: File is not CSV or Excel
- **Solution**: 
  - Save as .csv or .xlsx
  - Verify column headers match required format
  - Check for special characters in filenames

### "No data available in fundamentals"
- **Cause**: yfinance can't find fundamentals for ticker
- **Solution**: 
  - Data still loads without fundamentals
  - Quality scores will be partial
  - Manually enter fundamentals if known
  - Some tickers may not have full data

### Dashboard won't load
- **Cause**: FastAPI backend not running
- **Solution**:
  - Check terminal: `ps aux | grep portfolio_api`
  - Restart: `./run_portfolio_analyzer.sh`
  - Verify port 8001 is free: `lsof -i :8001`

### API endpoint returns 400 error
- **Cause**: No portfolio loaded yet
- **Solution**:
  - Click "Load Sample" or upload portfolio first
  - Then retry API call
  - All endpoints require portfolio context

---

## 📈 Integration with Your Screener

The portfolio analyzer integrates with your existing stock screener:

1. **Sector definitions** match your screener's categories
2. **Quality scores** compatible with Piotroski-style evaluations
3. **Market coverage** aligns with 6-market analysis (India, US, Europe, Japan, Korea, China)
4. **Tax handling** matches India LTCG/STCG rules
5. **Cassandra compatibility**: Can load portfolios from your DB

---

## 📚 Additional Resources

- **API Docs**: Full OpenAPI/Swagger at `http://127.0.0.1:8001/docs`
- **Sample Data**: Pre-loaded when you click "Load Sample"
- **Portfolio Report**: Export as JSON via `/portfolio/report`
- **Rebalancing Tracker**: Use with `PORTFOLIO_REBALANCING_TRACKER.md`

---

## 🚀 Next Steps

1. **Upload Your Portfolio**
   - Prepare CSV with your current holdings
   - Use "Upload Portfolio" to analyze

2. **Review Health**
   - Check Overview tab for overall status
   - Review Alerts tab for action items
   - Identify concentration risks

3. **Plan Rebalancing**
   - Use Rebalancing tab insights
   - Cross-reference with `PORTFOLIO_REBALANCING_TRACKER.md`
   - Plan tax-efficient execution

4. **Monitor Regularly**
   - Update prices weekly
   - Track LTCG milestones
   - Review sector allocation monthly

---

**Version**: 1.0.0  
**Last Updated**: 07-Jul-2026  
**Status**: 🟢 Production Ready
