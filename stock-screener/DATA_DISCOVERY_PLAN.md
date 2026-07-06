# 📊 DATA DISCOVERY PLAN
## Additional Data Sources for Complete Gap Analysis

**Objective**: Identify and integrate additional data sources to complete the gap analysis framework

**Status**: Planning phase  
**Date**: July 6, 2026

---

## MISSING DATA BY GAP CATEGORY

### 1. HISTORICAL CRISIS PERIOD DATA (For Regime Testing)

**Gap**: No actual backtest results for 2008, 2000, 2022 crisis periods

**Data Needed**:
- [ ] **2008-2009 Financial Crisis**: 
  - Daily OHLCV data for all 15 markets (Sep 2008 - Mar 2009)
  - Source: yfinance, CRSP, Bloomberg
  - Challenge: Need surviving stocks only (survivorship issue)
  
- [ ] **2000-2002 Dot-Com Crash**:
  - Daily OHLCV data for US/Tech focus (Mar 2000 - Oct 2002)
  - Source: CRSP, yfinance
  - Challenge: Many tech delistings
  
- [ ] **2022-2023 Rate Hiking Cycle**:
  - Daily OHLCV data (Jan 2022 - Dec 2023)
  - Fed funds rate by date
  - 10-year Treasury yield by date
  - Source: FRED (Federal Reserve Economic Data), yfinance

**Why This Data Matters**:
- Validates whether 54.5% win rate holds in stress periods
- Tests if Sharpe ratio 0.70-0.80 is sustainable
- Identifies if strategy underperforms in crises (likely)
- Critical for publication: Reviewers will ask "What happens in 2008?"

**Effort to Collect**: 2-3 days

---

### 2. DELISTED STOCK PRICE DATA (For Survivorship Bias)

**Gap**: Know ~1,329 delistings happened but don't have their returns

**Data Needed**:
- [ ] **US Delistings (2021-2026)**:
  - CRSP delisting file (~400 US delistings)
  - Last trading price, delisting date, delisting reason
  - Source: Wharton CRSP, COMPUSTAT
  
- [ ] **India Delistings (2021-2026)**:
  - BSE/NSE regulatory delisting data (~170-180)
  - Source: BSE website, NSE archives, SEBI filings
  
- [ ] **Emerging Market Delistings**:
  - Brazil B3 delistings (~50-55)
  - Japan TSE delistings (~140-150)
  - Source: Exchange websites, regulatory bodies
  
- [ ] **Return at Delisting**:
  - Closing price at delisting date
  - Average return of delisted stocks vs survivors
  - Source: Exchange data, Bloomberg terminals, FactSet

**Why This Data Matters**:
- Quantifies actual survivorship bias (currently estimated 2-5%)
- Could reveal bias is 1% (overblown) or 10% (critical)
- Changes realistic return from 22-25% to 21-26%

**Effort to Collect**: 3-5 days (data scattered across sources)

---

### 3. TRANSACTION COST MICRO-STRUCTURE DATA

**Gap**: Transaction cost model uses theoretical averages; need actual market data

**Data Needed**:
- [ ] **Bid-Ask Spreads by Market/Size/Time**:
  - US: Large-cap 1 bps, mid 3 bps, small 10+ bps (confirmed)
  - India: Large-cap 5 bps, mid 15 bps, small 50+ bps (needs verification)
  - Emerging markets: Actual spread data by market
  - Source: Bloomberg, FactSet, exchange tick data
  
- [ ] **Market Impact Data**:
  - How much does buying 1% of daily volume move the price?
  - Empirical estimates by market/stock
  - Source: Academic papers (Almgren-Chriss), Bloomberg terminals
  
- [ ] **Broker Commissions by Market**:
  - Actual costs for international trading
  - Emerging market premia
  - Source: Interactive Brokers, broker websites
  
- [ ] **Exchange Fees & Taxes**:
  - Current fee schedules
  - Tax treatment by country (withholding taxes, capital gains)
  - Source: Exchange websites, IRS, local authorities

**Why This Data Matters**:
- Current model: 2.6%-33.9% annual costs (broad range)
- Actual data could refine to 4-8% (much more useful)
- Could show quarterly rebalancing is optimal or suboptimal

**Effort to Collect**: 3-4 days (many public sources)

---

### 4. FUNDAMENTAL DATA BY MARKET (For Piotroski Validation)

**Gap**: Claimed 100% data quality but not verified by source

**Data Needed**:
- [ ] **Accounting Data Completeness by Market**:
  - % of stocks with quarterly earnings data
  - % with full income statement/balance sheet
  - US: ~95% (excellent)
  - India: ~70-80% (gaps for small-cap)
  - Emerging Asia: ~60-75% (missing data common)
  - Source: FactSet, Capital IQ, local exchanges
  
- [ ] **Data Quality Issues by Market**:
  - Accounting standard differences (IFRS vs local)
  - Reporting lag (US 30-45 days, India 45-60 days)
  - Restatements and corrections (US vs emerging)
  - Source: Academic papers, data vendor documentation
  
- [ ] **Piotroski F-Score Component Analysis**:
  - Which components available in each market?
  - Cash flow vs accrual quality (emerging markets weak)
  - ROA calculations (impact of accounting standards)
  - Source: FactSet data dictionaries, COMPUSTAT

**Why This Data Matters**:
- Claimed "100% data quality" may be optimistic
- Emerging markets may have 20-30% missing data
- Could explain why quality screen works better in developed markets
- Would show Piotroski threshold differences are driven by data quality

**Effort to Collect**: 2-3 days

---

### 5. SECTOR & FACTOR COMPOSITION DATA

**Gap**: Unknown portfolio sector weights; don't know if alpha is from sectors or stocks

**Data Needed**:
- [ ] **Portfolio Sector Weights by Market**:
  - Which sectors overweight? (likely Financials, Healthcare, Industrials)
  - Compare to market-cap weighted benchmark
  - Source: Run GICS classification on your backtested stocks
  
- [ ] **Market Cap Distribution**:
  - Large-cap (>$10B) concentration
  - Mid-cap ($1B-$10B) vs small-cap (<$1B)
  - Liquidity-filtered vs unfiltered universe
  - Source: yfinance market cap data
  
- [ ] **Factor Exposures**:
  - Size (SMB): Are you overweight small-cap?
  - Value (HML): P/B and P/E ratios vs benchmark
  - Momentum (WML): Recent 12-month returns vs market
  - Quality (QMJ): Already covered by Piotroski
  - Source: Calculate from your backtested data
  
- [ ] **Sector Performance (2021-2026)**:
  - Which sectors outperformed (Financials? Tech? Healthcare?)
  - Is your 27.3% from sector tilts or stock selection?
  - Source: MSCI sector index returns, S&P sector returns

**Why This Data Matters**:
- Could show 5-10% of return is sector tilt, not skill
- Example: If overweight Financials, and Financials +30%, that's luck not skill
- Would reduce "true alpha" from 27.3% or even 20% to something lower

**Effort to Collect**: 2-3 days (mostly calculation from existing data)

---

### 6. EARNINGS CALENDAR DATA (For Seasonality Validation)

**Gap**: Post-earnings drift +0.82% is aggregate; need granular data

**Data Needed**:
- [ ] **Earnings Announcement Dates (2021-2026)**:
  - All companies in your 20,000-stock universe
  - Actual announcement dates (not estimate dates)
  - Source: SEC EDGAR (US), exchange filings (international)
  
- [ ] **Earnings Surprises**:
  - Actual earnings vs analyst consensus
  - Positive vs negative surprise magnitude
  - By quarter (Q1, Q2, Q3, Q4)
  - Source: FactSet, Capital IQ, company filings
  
- [ ] **Drift Analysis by Surprise Size**:
  - 5% positive surprise: +X% drift
  - 20% positive surprise: +Y% drift
  - 10% negative surprise: -Z% drift
  - Source: Calculate from returns + earnings data
  
- [ ] **Seasonality by Region**:
  - US earnings season (Jan-May report Q4, Apr-Aug report Q1, etc.)
  - India earnings season (different timing)
  - Japan (different timing)
  - Source: Exchange calendars, earnings distribution data

**Why This Data Matters**:
- Claimed +0.82% drift is aggregate; could be +0.2% for small, +1.5% for large
- Could show drift only works on surprise magnitude >10%
- Could show drift is market-specific (works in US, not in India)
- Would refine alpha estimate from "0.8% from earnings" to something more accurate

**Effort to Collect**: 2-3 days

---

### 7. CORRELATION STABILITY DATA (For Diversification Testing)

**Gap**: Claimed Japan-India correlation 0.32; but how stable is it?

**Data Needed**:
- [ ] **Rolling Correlations by Period**:
  - 12-month rolling correlations (2021-2026)
  - 3-month rolling correlations (for crisis detection)
  - Pre-crisis (2020) vs crisis (2020 March) vs post (2020-2021)
  - Source: Calculate from index returns data
  
- [ ] **Correlation Stress Tests**:
  - What happens if all correlations become 0.80?
  - Portfolio volatility in "worst case" correlation regime
  - Return reduction from diversification loss
  - Source: Simulation based on your allocation
  
- [ ] **Crisis Correlation Data**:
  - 2008 crisis: Average correlation reached?
  - 2020 COVID: Average correlation reached?
  - How many days correlation > 0.70?
  - Source: Historical index data

**Why This Data Matters**:
- Diversification benefit from low correlations disappears in crises
- Your -10.5% volatility benefit could become 0% in crisis
- Would show real benefit is -5% to -8%, not -10.5%

**Effort to Collect**: 1-2 days

---

## DATA COLLECTION PRIORITY

### **TIER 1: CRITICAL (Must have for publication)**
1. **2008 Crisis Data** (2-3 days)
   - Affects: Sharpe ratio validation, drawdown estimation
   - Output: "Strategy returned -40% in 2008 vs market -40%"

2. **Delisting Returns Data** (3-5 days)
   - Affects: Survivorship bias quantification
   - Output: "Bias was 2.5%, reduces 27.3% → 24.8%"

3. **Transaction Costs Validation** (2-3 days)
   - Affects: Return realism
   - Output: "Quarterly rebalancing costs 4%, not 2.6%"

4. **Sector Attribution** (2-3 days)
   - Affects: Alpha vs sector tilt analysis
   - Output: "20% of return from Financials overweight"

**Subtotal**: 9-14 days

### **TIER 2: HIGH VALUE (Recommended for robustness)**
5. **2000 & 2022 Crisis Data** (3-4 days)
   - Extends validation to 3 crises
   
6. **Earnings Seasonality Granular** (2-3 days)
   - Refines 0.82% estimate to market/surprise specific
   
7. **Correlation Stability Data** (1-2 days)
   - Validates diversification benefit

**Subtotal**: 6-9 days

### **TIER 3: NICE TO HAVE (For completeness)**
8. **Fundamental Data Quality Analysis** (2-3 days)
   - Validates data completeness claims
   
9. **Market Impact Empirical Validation** (2-3 days)
   - Refines transaction cost model

**Subtotal**: 4-6 days

---

## DATA SOURCE RECOMMENDATIONS

### **Public Sources (Free)**
| Source | Data Available | Coverage | Lag |
|--------|---|---|---|
| yfinance | OHLCV, dividends | 15 markets | Real-time |
| SEC EDGAR | Financials, earnings dates | US only | 30-45 days |
| FRED | Macro rates, economic data | US | Varies |
| Exchange websites | Sector data, trading volume | By exchange | Daily |
| Wikipedia | Index constituents | By index | Manual |

### **Academic/Institutional Sources (Medium cost)**
| Source | Data Available | Coverage | Cost |
|--------|---|---|---|
| CRSP (Wharton) | Delisting data, returns | US | $1-10K/year |
| COMPUSTAT | Fundamentals | Global | $1-10K/year |
| FactSet | Everything | Global | $50K+/year |
| Capital IQ | Fundamentals, earnings | Global | $50K+/year |
| Bloomberg Terminal | Everything | Real-time | $2K+/month |

### **Recommended Minimal Cost Approach**
1. Use yfinance for OHLCV (already have)
2. Use SEC EDGAR for US earnings dates (free)
3. Use CRSP delisting file (1-time $500-1000)
4. Calculate everything else from these sources
5. **Total cost**: ~$1,000-2,000 (vs $50K+)

---

## IMPLEMENTATION TIMELINE

**Week 1-2: TIER 1 (Critical Data)**
- [ ] Download 2008 crisis data (OHLCV, prices, indices)
- [ ] Get US delistings from CRSP
- [ ] Validate transaction cost assumptions
- [ ] Calculate portfolio sector weights
- **Output**: Better cost model, delisting bias, sector attribution

**Week 3: TIER 2 (High-Value Data)**
- [ ] 2000 & 2022 crisis data
- [ ] Earnings surprise and drift granularity
- [ ] Correlation analysis
- **Output**: Extended crisis validation, refined seasonality

**Week 4+: TIER 3 (Polish)**
- [ ] Data quality analysis
- [ ] Market impact validation
- **Output**: Completeness documentation

---

## QUICK REFERENCE: WHERE TO FIND DATA

### By Data Type:
- **Historical prices**: yfinance, CRSP, exchanges
- **Delistings**: CRSP, SEC delisting notifications, exchange archives
- **Earnings dates**: SEC EDGAR, FactSet, Capital IQ
- **Fundamentals**: COMPUSTAT, FactSet, company filings
- **Sector data**: GICS master file, Morningstar, exchanges
- **Macro data**: FRED, central banks, economic surveys

### By Market:
- **US**: CRSP (best), SEC EDGAR, yfinance
- **India**: BSE/NSE archives, FactSet, yfinance
- **Japan**: JPX archives, FactSet, yfinance
- **EU**: Exchange websites, STOXX archives, yfinance
- **EM**: FactSet, Bloomberg, local exchanges

---

## SUCCESS CRITERIA

Data collection is complete when:

✅ 2008 crisis period fully backtestable (daily OHLCV all 15 markets)  
✅ Delisting data available for major markets (US, India, Japan, Brazil)  
✅ Actual transaction costs validated ±20% (not just model)  
✅ Sector composition and returns analyzed  
✅ Earnings surprises segmented by market and size  
✅ Correlation rolling windows calculated  

---

## NEXT STEPS

1. **Today**: Review this plan
2. **Tomorrow**: Start TIER 1 data collection (high ROI)
3. **Week 1**: Complete TIER 1 (critical for gap closure)
4. **Week 2-3**: Integrate data into gap analysis scripts
5. **Week 4**: Finalize paper with complete data

---

*Data Discovery Plan - July 6, 2026*  
*9-19 days estimated to complete comprehensive gap analysis with real data*
