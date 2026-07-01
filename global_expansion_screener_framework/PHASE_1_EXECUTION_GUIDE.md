# Phase 1 Execution Guide: Historical Data Collection (15-Year)

**Status:** APPROVED - Proceeding with implementation  
**Date:** July 2, 2026  
**Duration:** 4-6 weeks (Month 1-2)  
**Target:** 1,950 companies × 15 years of data collected & validated

---

## Phase 1 Overview

### Objective
Collect 15-year historical dataset (2011 Q1 - 2026 Q2) for 1,950 companies across 20 countries to enable geographic regression analysis.

### Success Criteria
- ✓ 1,950 companies × 60 quarters = 117,000 fundamental records collected
- ✓ 1,950 companies × 3,900 trading days = 7.6M price records collected  
- ✓ 7,800+ announcement events extracted from SEC/exchange filings
- ✓ Macro time series (rates, FX, spreads) synchronized
- ✓ Data quality: >95% completeness, outliers handled
- ✓ Currency normalization: All metrics in USD
- ✓ Ready for Phase 2 regression analysis

### Deliverables
- `historical_data_1950_companies.parquet` (fundamentals)
- `price_history_1950_companies.parquet` (daily OHLCV)
- `announcement_events_7800.csv` (capex/FCF/debt announcements)
- `macro_timeseries_2011_2026.csv` (rates, FX, spreads)
- `data_quality_report.txt` (completeness, outliers, gaps)

---

## Data Collection Architecture

### Layer 1: Daily Price Data (OHLCV)

**Source Priority:**
1. **yfinance** (primary) - Free, 15-year history, reliable
2. **Yahoo Finance archive** (fallback) - Historical data
3. **Alpha Vantage** (fallback 2) - Paid tier for gaps
4. **Local exchange archives** - Country-specific (Tokyo Stock Exchange, etc)

**Scope:**
- 1,950 tickers across 20 countries
- Daily data 2011-01-01 to 2026-06-30 (3,900 trading days)
- Metrics: Open, High, Low, Close, Volume, Adjusted Close
- Handling: Splits, dividends, delisting events

**Implementation:**

```python
import yfinance as yf
import pandas as pd
from datetime import datetime
import concurrent.futures

def collect_price_data(tickers, start_date, end_date):
    """Download 15-year daily OHLCV for all tickers"""
    
    price_data = {}
    
    # Parallel download (10 workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(yf.download, ticker, start=start_date, end=end_date,
                          progress=False): ticker
            for ticker in tickers
        }
        
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                data = future.result()
                if data is not None and len(data) > 0:
                    price_data[ticker] = data
                    print(f"✓ {ticker}: {len(data)} records")
            except Exception as e:
                print(f"✗ {ticker}: {e}")
    
    return price_data

# Execute
tickers = get_global_1950_company_list()  # See list below
price_df = collect_price_data(tickers, '2011-01-01', '2026-06-30')

# Save to parquet
price_df_combined = pd.concat(price_data, names=['ticker', 'date'])
price_df_combined.to_parquet('price_history_1950_companies.parquet')
```

**Timeline:** 2-3 days (yfinance is fast)
**Expected success rate:** 95%+ (mature companies, liquid markets)

---

### Layer 2: Quarterly Fundamentals

**Source Priority:**
1. **yfinance quarterly_financials** (primary) - US & some international
2. **SEC EDGAR API** (US only) - 10-Q, 10-K filings
3. **Country exchange APIs:**
   - Japan: TSE (Tokyo Stock Exchange) API
   - Korea: KOSPI data feed
   - China: SZSE/SHSE data
   - India: BSE/NSE APIs
4. **Financial databases:** Bloomberg, Reuters (if budget available)
5. **Company annual reports:** Manual PDFs (last resort)

**Scope:**
- 60 quarters per company (2011 Q1 - 2026 Q2)
- Metrics to extract:
  - **Income Statement:** Revenue, EBIT, Operating Income, Net Income
  - **Cash Flow:** Operating Cash Flow, Capex, Free Cash Flow
  - **Balance Sheet:** Total Debt, Equity, Current Assets, Current Liabilities
  - **Derived:** ROIC, DSC, Debt/Equity, Interest Coverage

**Implementation:**

```python
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def collect_quarterly_fundamentals(ticker):
    """Extract 60 quarters (2011 Q1 - 2026 Q2) for one company"""
    
    try:
        stock = yf.Ticker(ticker)
        
        # Get quarterly financials
        quarterly_financials = stock.quarterly_financials.T  # Transpose for dates
        quarterly_balance = stock.quarterly_balance_sheet.T
        quarterly_cashflow = stock.quarterly_cashflow.T
        
        # Align to quarters (drop NaN, sort by date)
        quarterly_data = pd.DataFrame()
        quarterly_data['date'] = quarterly_financials.index
        quarterly_data['revenue'] = quarterly_financials.get('Total Revenue', np.nan)
        quarterly_data['operating_income'] = quarterly_financials.get('Operating Income', np.nan)
        quarterly_data['net_income'] = quarterly_financials.get('Net Income', np.nan)
        quarterly_data['operating_cash_flow'] = quarterly_cashflow.get('Operating Cash Flow', np.nan)
        quarterly_data['capex'] = quarterly_cashflow.get('Capital Expenditures', np.nan).abs()
        quarterly_data['total_debt'] = quarterly_balance.get('Total Debt', np.nan)
        quarterly_data['total_equity'] = quarterly_balance.get('Total Equity', np.nan)
        
        # Calculate metrics
        quarterly_data['fcf'] = quarterly_data['operating_cash_flow'] - quarterly_data['capex']
        quarterly_data['fcf_margin'] = quarterly_data['fcf'] / quarterly_data['revenue']
        quarterly_data['de_ratio'] = quarterly_data['total_debt'] / quarterly_data['total_equity']
        quarterly_data['roic'] = quarterly_data['operating_income'] * 0.75 / (
            quarterly_data['total_debt'] + quarterly_data['total_equity']
        )
        
        # Sort and filter to 2011-2026
        quarterly_data = quarterly_data.sort_values('date')
        quarterly_data = quarterly_data[
            (quarterly_data['date'] >= '2011-01-01') & 
            (quarterly_data['date'] <= '2026-06-30')
        ]
        
        # Keep only latest 60 quarters
        if len(quarterly_data) > 60:
            quarterly_data = quarterly_data.tail(60)
        
        return quarterly_data
        
    except Exception as e:
        print(f"✗ {ticker}: {e}")
        return pd.DataFrame()

# Execute for all 1,950 companies
fundamentals_all = {}
for ticker in tickers:
    fundamentals_all[ticker] = collect_quarterly_fundamentals(ticker)
    print(f"✓ {ticker}: {len(fundamentals_all[ticker])} quarters")

# Combine and save
fundamentals_df = pd.concat(fundamentals_all, names=['ticker', 'date'])
fundamentals_df.to_parquet('fundamentals_1950_companies.parquet')
```

**Timeline:** 1-2 weeks (API calls + error handling)
**Expected success rate:** 85-90% (some companies lack history)

---

### Layer 3: Announcement Events

**Source Priority:**
1. **SEC EDGAR API** (US companies) - 8-K, 10-Q, 10-K filings
2. **Country exchange filings:**
   - Japan: TDnet (Tokyo Stock Exchange announcement system)
   - Korea: KIND (Korean stock exchange filings)
   - China: SZSE/SHSE announcements
3. **Company press releases** - Corporate websites, PR Newswire
4. **Market data feeds** - Historical earnings call transcripts

**Scope:**
- 7,800 total announcements across 1,950 companies (avg 4 per company over 15 years)
- Announcement types:
  - Capex guidance changes (+/- 20%, new facility, plant closure)
  - FCF/earnings surprises (beat/miss guidance)
  - Debt issuance/reduction events
  - DSC deterioration signals (covenant concerns)
  - Regulatory events (FDA approval, facility warnings)

**Implementation:**

```python
import requests
import json
from datetime import datetime

def extract_sec_announcements(cik, ticker):
    """Extract 8-K filings from SEC EDGAR API"""
    
    base_url = "https://data.sec.gov/submissions"
    
    try:
        # Get company filing history
        response = requests.get(f"{base_url}/CIK{cik:010d}.json")
        filings = response.json()['filings']['recent']['form']
        dates = response.json()['filings']['recent']['filingDate']
        
        # Filter 8-K filings (current reports) within 2011-2026
        announcements = []
        for i, form in enumerate(filings):
            if form == '8-K':
                filing_date = datetime.strptime(dates[i], '%Y-%m-%d')
                if datetime(2011, 1, 1) <= filing_date <= datetime(2026, 6, 30):
                    announcements.append({
                        'ticker': ticker,
                        'date': filing_date,
                        'form': '8-K',
                        'url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type=8-K"
                    })
        
        return announcements
    
    except Exception as e:
        print(f"✗ {ticker}: {e}")
        return []

def parse_announcement_text(filing_url, form_type):
    """Parse 8-K text for capex/FCF/debt keywords"""
    
    # Keywords for each announcement type
    keywords = {
        'capex_increase': ['capital expenditure', 'capex', 'facility', 'factory', 'plant', 
                          'expansion', 'construction', 'investment in'],
        'capex_decrease': ['capex cut', 'capital reduction', 'facility closure', 'plant shutdown'],
        'fcf_beat': ['cash flow', 'free cash flow', 'exceeded', 'beat', 'outperformed'],
        'fcf_miss': ['cash flow', 'free cash flow', 'missed', 'below', 'weaker than expected'],
        'debt_increase': ['debt issuance', 'credit facility', 'bond offering', 'loan'],
        'debt_reduction': ['debt paydown', 'deleveraging', 'debt reduction', 'paid down'],
        'dsc_issue': ['covenant', 'default', 'breach', 'liquidity concern'],
    }
    
    # Parse and classify (simplified; actual parsing more complex)
    return {
        'filing_url': filing_url,
        'announcement_type': 'capex_increase',  # Simplified
        'sentiment': 'positive',  # Simplified
        'estimated_impact_pct': 3.5
    }

# Execute for all US companies
announcements_all = []
for ticker, cik in us_company_list:  # CIK = company ID from SEC
    company_announcements = extract_sec_announcements(cik, ticker)
    announcements_all.extend(company_announcements)

# Save
announcements_df = pd.DataFrame(announcements_all)
announcements_df.to_csv('announcements_7800_events.csv', index=False)
print(f"Extracted {len(announcements_df)} announcements")
```

**Timeline:** 1 week (SEC API is efficient)
**Expected count:** 7,800 announcements (avg 4 per company)

---

### Layer 4: Macro Data

**Source:**
- Federal Reserve (US rates, yield curve)
- ECB (European rates)
- Bank of Japan (Japan rates)
- World Bank (GDP growth, inflation by country)
- OECD (interest rates by country)
- FX data (monthly average rates: USD/EUR, USD/JPY, etc)
- Credit spreads (if available)

**Scope:**
- Monthly data 2011-2026 (180 months)
- Metrics:
  - Interest rates (Fed Funds, 10Y Treasuries, by country)
  - GDP growth (quarterly, by country)
  - Inflation (monthly, by country)
  - FX rates (USD against major currencies)
  - Credit spreads (HY spread, IG spread)
  - Stock market returns (S&P 500, MSCI World, regional indices)

**Implementation:**

```python
import yfinance as yf
import pandas as pd

def collect_macro_data():
    """Collect macro time series 2011-2026"""
    
    macro_data = pd.DataFrame()
    macro_data['date'] = pd.date_range('2011-01-01', '2026-06-30', freq='MS')
    
    # US rates (Fed Funds, 10Y)
    # Note: Would use FRED API in production
    fedfunds = yf.download('^FEDFUNDS', start='2011-01-01', end='2026-06-30')
    macro_data['fed_funds'] = fedfunds['Close'].resample('MS').last()
    
    # Stock market returns
    sp500 = yf.download('^GSPC', start='2011-01-01', end='2026-06-30')
    macro_data['sp500_return'] = sp500['Close'].pct_change().resample('MS').sum()
    
    # VIX (volatility)
    vix = yf.download('^VIX', start='2011-01-01', end='2026-06-30')
    macro_data['vix'] = vix['Close'].resample('MS').mean()
    
    # HY credit spread (proxy from bonds)
    # In production: Use Bloomberg or FRED
    macro_data['hy_spread'] = np.random.normal(400, 100, len(macro_data))  # Placeholder
    
    return macro_data

macro_df = collect_macro_data()
macro_df.to_csv('macro_timeseries_2011_2026.csv', index=False)
```

**Timeline:** 1-2 days (publicly available APIs)
**Data sources:** Fed FRED API, World Bank API, OECD, Yahoo Finance

---

## Global Company Universe (1,950 Companies)

### North America (750 companies)
- **USA (600):** NYSE, NASDAQ large-cap + mid-cap
  - Tech: NVDA, MSFT, AAPL, TSLA, AMD (semiconductors)
  - Finance: JPM, BAC, GS, WFC
  - Healthcare: JNJ, PFE, MRNA, ABBV
  - Industrials: GE, BA, CAT, MMM
  - Energy: XOM, CVX, COP
  - Consumer: WMT, COST, MCD, NKE
  - Real Estate/Utilities: DLR, NEE
  
- **Canada (100):** Toronto Stock Exchange
  - Finance: TD, RY, BNS
  - Energy: ENB, CNQ, SU
  - Materials: BHP, RIO
  
- **Mexico (50):** Bolsa Mexicana
  - GFINBURO, WALMEX, BIMBOA

### Europe (400 companies)
- **Germany (100):** Xetra
  - Autos: VOW3, BMW, DAI (VW, BMW, Daimler)
  - Tech/Software: SAP, SIE (Siemens)
  - Industrial: SIEGY (Siemens), BASF
  
- **UK (100):** LSE
  - Finance: LLOY, BARC, HSBA
  - Pharma: GSK, AZN (AstraZeneca)
  - Oil: BP, SHEL
  
- **France (80):** Euronext Paris
  - Pharma: SANOFI
  - Luxury: LVMH, OREP
  - Auto: RNO (Renault)
  
- **Other Europe (120):** Switzerland, Netherlands, Spain, Italy, Sweden
  - Novartis, Nestle (Switzerland)
  - ASML, ING (Netherlands)

### Asia-Pacific (650 companies)
- **China (250):** Shanghai, Shenzhen
  - Tech: BABA (Alibaba), TCEHY (Tencent), BIDU (Baidu)
  - Tech manufacturing: BLDP, XPEV
  - Finance: PAAS
  - Materials: Vale China ops
  
- **Japan (150):** Tokyo Stock Exchange
  - Tech: TYO:6752 (Panasonic), TYO:6901 (Toyota)
  - Auto: TYO:7203 (Toyota), TYO:7267 (Honda)
  - Finance: TYO:8306 (SMFG)
  
- **South Korea (80):** KOSPI
  - Tech: SAMSUNG (005930), SK Hynix (000660)
  - Autos: HYUNDAI
  
- **India (100):** NSE/BSE
  - Pharma: CIPLA, LT (Lupin)
  - Auto: MARUTI, TATAMOTORS
  - IT: INFY, TCS
  - Finance: ICICIBANK, SBIN
  
- **Other Asia-Pacific (70):** Singapore, Australia, Hong Kong
  - Singapore: DBS, UOB
  - Australia: BHP, RIO, NAB

### Emerging Markets (150 companies)
- **Brazil (80):** B3
  - Energy: VALE (mining), PETR (Petrobras)
  - Finance: ITUB
  - Agribusiness: WEGE (JBS)
  
- **Mexico (40):** Bolsa Mexicana
  - Finance: GFINBURO, BIMBOA
  - Telecom: AMXL
  
- **Other EM (30):** Poland, Russia*, Turkey, Thailand
  *Note: Russia excluded if sanctions block data access

---

## Data Collection Checklist & Timeline

### Week 1-2: Setup & Layer 1 (Price Data)

- [ ] Set up cloud infrastructure (AWS S3 for storage, EC2 for compute)
- [ ] Install Python dependencies (yfinance, pandas, numpy, requests)
- [ ] Create 1,950-company master list with tickers, CIKs, exchange codes
- [ ] Test yfinance download (sample 10 companies)
- [ ] Begin parallel download of daily price data (yfinance)
- [ ] Monitor download success rate (target >95%)
- [ ] Save to `price_history_1950_companies.parquet`
- **Deliverable:** 7.6M price records × 1,950 companies

### Week 2-3: Layer 2 (Quarterly Fundamentals)

- [ ] Verify yfinance quarterly API functionality
- [ ] Build quarterly_financials extraction (revenue, capex, debt, FCF)
- [ ] Handle missing data: interpolate, forward-fill, mark as NaN
- [ ] Validate ROIC, DSC calculations (spot-check 50 companies)
- [ ] Test currency handling (convert non-USD to USD)
- [ ] Save to `fundamentals_1950_companies.parquet`
- **Deliverable:** 117,000 quarterly records × 60 quarters

### Week 3-4: Layer 3 (Announcements)

- [ ] Access SEC EDGAR API (register for free account)
- [ ] Build 8-K filing parser for US 600 companies
- [ ] Test announcement extraction (50 companies × 15 years)
- [ ] For international companies: Research alternative data sources
  - Japan: TDnet API or manual web scraping
  - Korea: KIND filings
  - India: NSE/BSE stock exchange announcements
- [ ] Parse announcement text for capex/FCF/debt keywords
- [ ] Save to `announcements_7800_events.csv`
- **Deliverable:** 7,800 announcement events with classifications

### Week 4: Layer 4 (Macro) & Quality Check

- [ ] Download Fed rates, GDP, inflation via public APIs (FRED, World Bank)
- [ ] Align macro dates with quarterly fundamentals
- [ ] Calculate aggregate statistics (monthly market returns, credit spreads)
- [ ] Save to `macro_timeseries_2011_2026.csv`
- **Data Quality Checks:**
  - [ ] Completeness: >95% of records populated (vs expected)
  - [ ] Outlier handling: Winsorize extreme returns (>5 sigma)
  - [ ] Missing data: Document gaps, decide interpolation strategy
  - [ ] Validation: Spot-check 50 companies for data accuracy
  - [ ] Currency: All metrics confirmed in USD
- [ ] Generate `data_quality_report.txt`

### Week 4-5: Backup & Handoff

- [ ] Compress parquet files, backup to S3 + local
- [ ] Create data dictionary (field descriptions, units, currencies)
- [ ] Document any data gaps or limitations
- [ ] Create Phase 2 input validation checklist
- [ ] Handoff datasets to Phase 2 regression team

---

## Expected Data Quality

### Price Data
- Completeness: 97% (mature, liquid companies)
- Gaps: Typically 0-2 missing days per company (market closures)
- Outliers: Delisting events, 2:1 stock splits, spinoffs handled

### Quarterly Fundamentals
- Completeness: 92% (some companies missing historical data)
- Gaps: Typically Q1-2 for companies with <15 years history
- Outliers: Acquisition/merger quarters (high capex, debt spikes)

### Announcements
- Coverage: 85% of expected announcements (SEC completeness varies)
- Classification: 90% accuracy (automated keyword matching)
- Delays: Some announcements lag earnings by 1-2 weeks

### Macro Data
- Completeness: 100% (public sources reliable)
- Frequency: Monthly (aligned to quarters via resampling)

---

## Risk Mitigation

### Data Download Failures
- **Risk:** yfinance API throttling, network timeout
- **Mitigation:** Parallel downloads with retry logic (3 attempts), backoff strategy
- **Fallback:** Alpha Vantage API (paid tier), Yahoo Finance archive

### Missing Historical Data
- **Risk:** Small-cap companies, recent IPOs lack 15-year history
- **Mitigation:** Document gap, use available data (5-10 years), don't drop company
- **Filter:** Keep companies with minimum 20 quarters (5 years)

### Currency Inconsistencies
- **Risk:** Balance sheet reported in local currency, exchange rate variation
- **Mitigation:** Use historical quarterly average FX rates, store exchange rates
- **Validation:** Spot-check converted metrics vs original currency

### Announcement Parsing Errors
- **Risk:** Keyword matching misses context (e.g., "capex reduction" vs "capex increase reduction")
- **Mitigation:** Manual review of 100 random announcements, adjust keywords
- **Fallback:** Mark ambiguous announcements for manual review

---

## Deliverables Checklist

- [ ] `price_history_1950_companies.parquet` (7.6M records)
- [ ] `fundamentals_1950_companies.parquet` (117K records)
- [ ] `announcements_7800_events.csv` (7,800 events)
- [ ] `macro_timeseries_2011_2026.csv` (180 months)
- [ ] `data_quality_report.txt` (completeness analysis)
- [ ] `data_dictionary.md` (field definitions, units, currencies)
- [ ] `phase_1_completion_summary.txt` (success metrics)

---

## Success Metrics

**Phase 1 Complete When:**
1. ✅ 1,850+ companies have price data (>95% of 1,950)
2. ✅ 1,500+ companies have 50+ quarters of fundamentals
3. ✅ 7,500+ announcements extracted (>95% of 7,800 target)
4. ✅ Macro data 100% complete (180 monthly records)
5. ✅ Data quality report shows <5% missing values (acceptable)
6. ✅ Spot-check validation passes (50 companies reviewed)
7. ✅ All datasets saved & backed up

**Proceed to Phase 2 when:** All 7 success metrics achieved

---

## Timeline Summary

| Week | Task | Deliverable |
|------|------|-------------|
| **1-2** | Price data collection (yfinance) | 7.6M price records |
| **2-3** | Quarterly fundamentals extraction | 117K fundamental records |
| **3-4** | Announcement events parsing | 7,800 event records |
| **4** | Macro data + quality validation | Macro data + QC report |
| **4-5** | Backup, documentation, handoff | Complete Phase 1 package |

**Total Duration:** 4-5 weeks (aggressive schedule with parallel execution)

**Start Date:** July 2, 2026  
**Target Completion:** August 6, 2026  
**Phase 2 Start:** August 9, 2026

---

## Success Story Indicators

✅ **Price data:** 1,900+ companies download successfully in <3 days
✅ **Fundamentals:** 1,500 companies have 60 quarters of clean data
✅ **Announcements:** 7,500+ 8-K/announcements extracted in <1 week
✅ **Macro:** Federal Reserve, World Bank APIs respond smoothly
✅ **Quality:** Outlier handling, currency conversion working correctly
✅ **Backup:** Triple-redundant storage (S3, local, external drive)

---

## Next Phase (Phase 2 Readiness)

Once Phase 1 complete:
1. Phase 2 team receives datasets
2. Regression calibration begins (2011-2015 data)
3. Geographic factor weights extracted
4. Validation on 2016-2026 out-of-sample period
5. Results feed into Phase 3 (announcement analysis)

**Phase 2 depends on:** Phase 1 datasets quality & completeness

---

**Status:** Ready to begin Phase 1  
**Approval:** Received (July 2, 2026)  
**First commit:** Phase 1 scripts to repo  
**Team needed:** 1 data engineer + 1 QA analyst  
**Infrastructure:** Cloud compute + storage (AWS recommended)

Let's go! 🚀
