# 🚀 Portfolio Analyzer - Setup & Getting Started

## Quick Setup (5 minutes)

### Step 1: Start the Service

```bash
cd /Users/umashankar/stock-screener

# Make script executable (first time only)
chmod +x run_portfolio_analyzer.sh

# Start service
./run_portfolio_analyzer.sh
```

**Expected output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Portfolio Analyzer - Startup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Creating virtual environment...
Activating virtual environment...
Installing/updating dependencies...
✓ Starting FastAPI backend on http://127.0.0.1:8001
✓ Opening web dashboard at http://127.0.0.1:8001 in browser...

Dashboard URL: file:///Users/umashankar/stock-screener/portfolio_dashboard.html

API Endpoints:
  POST   /portfolio/upload                - Upload portfolio file
  POST   /portfolio/load-sample          - Load sample portfolio
  GET    /portfolio/metrics              - Portfolio metrics
...

Stop backend: Press Ctrl+C
```

### Step 2: Open Dashboard in Browser

Copy and paste this URL into your browser:
```
file:///Users/umashankar/stock-screener/portfolio_dashboard.html
```

You should see:
- Header with "Portfolio Analyzer" title
- Buttons: Upload Portfolio, Load Sample, Update Prices
- Tab navigation: Overview, Holdings, Quality, Rebalancing, Sectors, Alerts

### Step 3: Load Sample Data

Click the **"Load Sample"** button to populate the dashboard with 20 sample stocks.

You should see:
- Overview cards with portfolio metrics
- Summary of total invested, current value, gains
- Risk metrics (concentration ratio, diversification)
- Market exposure breakdown

**That's it! You're ready to use the analyzer.**

---

## Upload Your Own Portfolio

### Format 1: CSV File (Simplest)

1. Create a file named `my_portfolio.csv` with your holdings

2. Required columns:
   ```
   ticker,quantity,purchase_price,purchase_date,market
   HDFCBANK,10,1500,2023-01-15,india
   AAPL,5,180,2023-11-10,us
   ADS.DE,8,180,2024-04-05,europe
   ```

3. Optional column:
   ```
   sector
   banking
   tech
   auto
   ```

4. Upload via dashboard:
   - Click "Upload Portfolio"
   - Select your CSV file
   - Dashboard auto-loads

### Format 2: Excel File

1. Create `my_portfolio.xlsx` with same columns as CSV

2. Put data in first sheet

3. Upload via dashboard

### Market Codes

Use these exact codes in the `market` column:
- `india` - NSE/BSE stocks
- `us` - US stocks (NYSE/NASDAQ)
- `europe` - European exchanges
- `japan` - TSE stocks
- `korea` - KRX stocks
- `china` - A-shares

### Ticker Formats

| Market | Format | Example |
|--------|--------|---------|
| India | Bare NSE symbol | `HDFCBANK`, `RELIANCE`, `INFY` |
| USA | Bare ticker | `AAPL`, `MSFT`, `TSLA` |
| Europe | With exchange suffix | `ADS.DE`, `SAP.DE`, `RIO.L` |
| Japan | With exchange suffix | `7203.T`, `8306.T` |
| Korea | With exchange suffix | `005930.KS`, `000660.KS` |

---

## Dashboard Tabs Explained

### 📊 Overview Tab (Default)

**Summary Cards:**
- Total Invested: How much you've put in
- Current Value: What it's worth now
- Total Gain: Rupees gained (or lost)
- Holdings: Number of stocks

**Metrics:**
- Concentration Ratio: % of largest position
  - Green if <10%
  - Red if >15%
- Diversification Ratio: How spread out
- Dividend Yield: Annual dividend %

**Market Exposure:**
- Pie chart style breakdown
- India, USA, Europe, Japan, Korea percentages

### 📋 Holdings Tab

Complete stock-by-stock table showing:
- Ticker and market
- Quantity owned
- Cost basis (invested amount)
- Current value
- Unrealized gain/loss (₹ and %)
- Portfolio allocation %
- Days held (for tax tracking)

**Sort options:** Click column headers to sort

### ⭐ Quality Tab

Position evaluation showing:
- P/E Ratio: Valuation (lower = cheaper)
- P/B Ratio: Book value comparison
- ROE: Profitability %
- Dividend Yield: Annual dividend %
- Quality Score: 0-100 rating
  - 60-79: Good
  - 80+: Excellent

### ⚖️ Rebalancing Tab

**Overweight Positions:**
- Stocks >10% of portfolio
- Recommended max: 10%
- Shows how much to trim

**Tax Implications:**
- Unrealized gains
- Holding period (days)
- Tax status (STCG vs LTCG)
- Estimated tax if sold now

### 📈 Sectors Tab

Breakdown by sector:
- Banking, Tech, Energy, Auto, etc.
- Allocation % per sector
- Average gain/loss per sector
- Stock count per sector

### 🚨 Alerts Tab

Actionable alerts by severity:

**🔴 HIGH (Critical)**
- Concentration risk >15%
- Immediate action needed

**🟡 MEDIUM (Important)**
- Overweight positions
- High tax consequences
- Sector concentration

**🔵 LOW (Consideration)**
- Dividend yield below target
- Diversification opportunities

---

## File Locations

Once running, all files are in:
```
/Users/umashankar/stock-screener/
├── portfolio_analyzer.py           # CLI tool
├── portfolio_api.py                # Backend API
├── portfolio_dashboard.html        # Web interface
├── portfolio_requirements.txt       # Dependencies
├── run_portfolio_analyzer.sh        # Startup script
├── sample_portfolio.csv            # Sample data
├── PORTFOLIO_ANALYZER_README.md    # Full documentation
└── PORTFOLIO_SETUP.md              # This file
```

---

## Common Tasks

### Update Prices

Click **"Update Prices"** button to refresh current stock prices from yfinance.

Takes 1-2 minutes depending on number of stocks.

### Get Current P/E Ratio

Go to **Quality tab** → P/E Ratio column

Or use API:
```bash
curl http://127.0.0.1:8001/portfolio/quality
```

### Check Tax Impact Before Selling

Go to **Rebalancing tab** → Tax Implications section

Shows STCG vs LTCG, estimated tax, and breakeven hold date

### Export as JSON

Use API endpoint:
```bash
curl http://127.0.0.1:8001/portfolio/report > portfolio_report.json
```

### Identify Overweight Positions

Go to **Rebalancing tab** → Overweight Positions

Shows all positions >10% with recommended trim amounts

### Get Rebalancing Recommendations

Go to **Alerts tab**

Shows what to sell, what to buy, and why

---

## Troubleshooting

### Dashboard won't load

**Problem:** Page stays blank or shows error
**Solution:**
1. Check terminal where you ran `./run_portfolio_analyzer.sh`
2. Look for errors in output
3. Restart:
   - Press Ctrl+C in terminal
   - Run `./run_portfolio_analyzer.sh` again
4. Wait 5 seconds for backend to start
5. Refresh browser (Cmd+R)

### "Upload failed"

**Problem:** Can't upload CSV/Excel file
**Solution:**
1. Verify file format (CSV or XLSX)
2. Check column names match exactly:
   - `ticker`, `quantity`, `purchase_price`, `purchase_date`, `market`
3. Ensure no empty rows at top
4. Try saving CSV in UTF-8 encoding

### "Failed to fetch prices"

**Problem:** Update Prices button fails
**Solution:**
1. Check internet connection
2. Verify ticker format (especially Europe/Japan)
3. Try again - sometimes yfinance has timeouts
4. If persistent, manually enter current prices in Excel and re-upload

### No portfolio data shows

**Problem:** Dashboard loads but no data
**Solution:**
1. Click "Load Sample" button
2. Or upload your own portfolio CSV
3. Wait for "Portfolio loaded" message
4. Data should appear in tabs

---

## API for Integration

The analyzer exposes REST API endpoints you can use programmatically:

### Quick Example: Get Portfolio Metrics

```bash
# Get metrics for current portfolio
curl http://127.0.0.1:8001/portfolio/metrics

# Response includes:
{
  "summary": {
    "total_invested": 500000,
    "current_value": 575000,
    "total_gain": 75000,
    "total_gain_pct": 15.0,
    "number_of_stocks": 20
  },
  "risk": {
    "concentration_ratio": 28.4,
    "diversification_ratio": 3.5
  },
  "income": {
    "dividend_yield": 1.49,
    "estimated_annual_dividend": 8563
  }
}
```

### See All Endpoints

Full API documentation available at:
```
http://127.0.0.1:8001/docs
```

Opens interactive Swagger UI where you can test all endpoints

---

## Next Steps

1. **Load Sample Data** (1 min)
   - Click "Load Sample" to see example portfolio
   - Explore all tabs to understand metrics

2. **Prepare Your Data** (5-10 min)
   - Use `sample_portfolio.csv` as template
   - Export your holdings to CSV
   - Or manually create CSV file

3. **Upload Portfolio** (1 min)
   - Click "Upload Portfolio"
   - Select your CSV file
   - Dashboard auto-refreshes

4. **Review Recommendations** (5 min)
   - Check Overview for health check
   - Go to Alerts for action items
   - Review Rebalancing tab for specifics

5. **Plan Execution** (10-20 min)
   - Document recommended actions
   - Plan tax-efficient sequence
   - Use PORTFOLIO_REBALANCING_TRACKER.md for detailed plan

6. **Execute & Monitor** (Ongoing)
   - Execute sells/buys based on plan
   - Update prices weekly
   - Review monthly for new alerts

---

## Support

**Full Documentation:**
See [PORTFOLIO_ANALYZER_README.md](PORTFOLIO_ANALYZER_README.md) for:
- Detailed metric explanations
- All API endpoints
- Advanced features
- Troubleshooting guide

**Questions:**
1. Check the README first
2. Review sample data in dashboard
3. Look at API docs at http://127.0.0.1:8001/docs
4. Check terminal output for error messages

---

**Status:** ✅ Ready to use  
**Last Updated:** 07-Jul-2026
