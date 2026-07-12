# NSE Index Methodology Implementation Guide

## Overview

This guide explains how to build custom indices using **NSE (National Stock Exchange of India) Indices Limited official methodology** based on the June 2026 Methodology Document.

NSE manages 80+ indices covering:
- **Broad market indices**: Nifty 500, 100, 50, Midcap 150, Smallcap 250
- **Sectoral indices**: 14+ sectors (Bank, IT, FMCG, Auto, Pharma, etc.)
- **Thematic indices**: 20+ themes (Defense, Digital, Infrastructure, etc.)
- **Strategy indices**: Quality, Momentum, Low Volatility, Dividend, etc.

---

## Part 1: Eligibility Screening (Step 1)

### NSE Minimum Eligibility Criteria

Before a stock can be included in any Nifty index:

```python
builder = NSEIndexBuilder()
eligible = builder.screen_eligible_universe(tickers, price_data)
```

**Required criteria:**
1. **Domiciliation**: India domiciled
2. **Exchange**: Listed & traded on NSE (not delisted)
3. **Series**: Not in BZ series, not suspended
4. **Security Type**: Equity only (not bonds, warrants, convertibles)
5. **Trading Frequency**: Traded ≥90% of days in previous 6 months
6. **Free-float**: Investable Weight Factor (IWF) ≥10% OR 6M avg free-float ≥25% of smallest constituent

**Example:**
```
✓ INFY: 250 trading days (100%) out of 252 days, Free-float 94%, IWF 94% → ELIGIBLE
✗ HDFC: 180 trading days (71%) out of 252 days → INELIGIBLE (fails 90% test)
✗ Company under suspension → INELIGIBLE
```

---

## Part 2: Market Cap Ranking (Step 2)

NSE ranks all eligible companies by **full market capitalization** (not free-float).

```python
ranked = builder.rank_by_market_cap(eligible_df, market_caps)
```

**Ranking hierarchy:**
```
Rank 1:    Reliance (~₹22 lakh Cr)
Rank 2:    TCS (~₹14 lakh Cr)
Rank 3:    HDFC Bank (~₹12 lakh Cr)
...
Rank 50:   (Last Nifty 50 constituent)
Rank 51:   (First Nifty Midcap 150)
...
Rank 200:  (Last Nifty Midcap 150)
Rank 201:  (First Nifty Smallcap 250)
...
Rank 500:  (Last company in Nifty 500)
```

**Output:**
- `market_cap_rank`: 1-500 ranking
- `weight`: % of total market cap
- `cumulative_weight`: Running total (should reach 100%)

---

## Part 3: Index Constitution (Step 3)

### A. Nifty 50 (Market-Cap Weighted)

```python
nifty_50 = builder.nifty_50_constitution(ranked_df)
```

**Rules:**
- Top 50 companies by free-float market cap
- Selected from Nifty 100 universe (ranks 1-100)
- Must have derivatives (Futures & Options) on NSE
- Min impact cost 0.50% for ₹10 Crore basket
- Free-float factor: Typically 60-75% for large-cap stocks
- Quarterly rebalancing: Last trading day of Mar, Jun, Sep, Dec

**Example Nifty 50 weights (as of Jul 2026):**
```
Reliance:     6.8%  ← Highest weight
TCS:          4.2%
HDFC Bank:    3.9%
Infosys:      3.1%
ICICI Bank:   2.7%
...
NTPC:         0.8%  ← Lowest weight
```

### B. Nifty Midcap 150 (Mid-market Cap)

```python
midcap_150 = builder.nifty_midcap_150_constitution(ranked_df)
```

**Rules:**
- Ranks 51-200 by full market cap (ranks 101-250 from Nifty 500)
- Free-float factor: 50-60% (lower than Nifty 50)
- Quarterly rebalancing
- Captures mid-size company performance

### C. Nifty Smallcap 250 (Small-market Cap)

```python
smallcap_250 = builder.nifty_smallcap_250_constitution(ranked_df)
```

**Rules:**
- Ranks 201-500 by full market cap (ranks 251-500 from Nifty 500)
- Free-float factor: 40-50% (smallest free-float)
- Quarterly rebalancing
- More volatile, higher growth potential

### D. Nifty 500 (Full Market)

- Top 500 companies combined (Nifty 50 + Midcap 150 + Smallcap 250 + extra constituents)
- Covers ~98% of Indian market capitalization
- Quarterly rebalancing

---

## Part 4: Factor/Quality Indices (Step 4)

### A. Nifty Quality 50

```python
quality_50 = builder.nifty_quality_50(nifty_50_df, fundamental_data)
```

**Selection criteria (from Nifty 50):**
- Return on Equity (ROE) ≥ 15%
- Debt-to-Equity ≤ 0.50
- 3-year revenue CAGR > 10%
- Equal weight (not market-cap weighted)
- Quarterly rebalancing

**Example:**
```
✓ TCS: ROE 18%, D/E 0.15, CAGR 12% → ELIGIBLE
✓ MSFT (India): ROE 20%, D/E 0.05, CAGR 25% → ELIGIBLE
✗ Banks: High D/E (>1.0 for leverage) → INELIGIBLE
```

### B. Nifty Low Volatility 50

```python
low_vol = builder.nifty_low_volatility_50(nifty_100_df)
```

**Rules:**
- Select 50 stocks from Nifty 100 with lowest volatility
- Capped equal weight: Max 3% per stock
- Quarterly rebalancing
- Defensive portfolio strategy

**Typical constituents:**
- FMCG (Britannia, Nestlé, Colgate)
- Utilities (NTPC, Power Finance)
- Telecom (Jio, Airtel)
- Healthcare (Cipla, Dr Reddy's)

### C. Nifty Dividend Opportunities 50

```python
div_opps = builder.nifty_dividend_opportunities_50(nifty_50_df, dividend_yields)
```

**Rules:**
- Min dividend yield ≥ 2.5% (usually paid annually)
- Selected from Nifty 50
- Market-cap weighted with 3% cap per stock
- Quarterly rebalancing
- Income generation strategy

**Example dividends (high yielders):**
- NTPC: 8.2% yield
- Power Finance: 6.5% yield
- HDFC Bank: 2.8% yield
- Reliance: 2.2% yield

---

## Part 5: Index Calculation (Step 5)

### Formula A: Market-Cap Weighted Index

```python
index_values = builder.calculate_market_cap_index(constituents, price_data)
```

**NSE Formula:**
```
Index Value = (Index Market Cap / Base Market Cap) × Base Index Value

Index Market Cap = Σ(Price × Shares × IWF × Capping Factor)
Base Index Value = 1000 (or 100 depending on index)
```

**Calculation example (2-stock index):**
```
Stock A: Price ₹100, MC ₹500Cr, Free-float 60%
Stock B: Price ₹200, MC ₹300Cr, Free-float 70%

Total Index MC = (100×60% + 200×70%) = 60 + 140 = 200
Weight A = 60/200 = 30%
Weight B = 140/200 = 70%

If Index goes from ₹100 → ₹105:
Stock A contributes: 30% × 5% = 1.5%
Stock B contributes: 70% × 5% = 3.5%
Total = 5% return
```

### Formula B: Equal-Weight Index

```python
ew_index = builder.calculate_equal_weight_index(constituents, price_data)
```

**Rule:** Each stock has equal contribution (1/N weight), regardless of market cap

**Example (50-stock equal-weight):**
```
Each stock weight = 100% / 50 = 2%
If 1 stock gains 10%, contribution = 2% × 10% = 0.2%
If all 50 stocks gain 5%, total return = 5%
```

### Formula C: Total Return Index (with Dividends)

```python
tri = builder.calculate_total_return_index(constituents, price_data, dividends)
```

**NSE Formula:**
```
TRI = Previous_TR × [1 + (Price_Return + Indexed_Dividend) / Previous_Price]

Indexed_Dividend = Dividend_Payout / Base_Market_Cap
```

**Assumption:** All dividends are reinvested back into the index (no cash flow)

**Example (quarterly comparison):**
```
Price Return (PR Index):     +3.5%
Dividend Contribution:       +0.8%  (from 10+ dividend-paying stocks)
Total Return Index (TRI):    +4.3%  (includes reinvested dividends)

Over 5 years:
PR Index: 18.3% CAGR
TRI Index: 20.1% CAGR (additional 1.8pp from dividends)
```

---

## Part 6: Quarterly Rebalancing (Step 6)

```python
schedule = builder.quarterly_rebalancing_schedule(year=2026)
# Output: [('Q1 Rebalancing', Mar 31), ('Q2 Rebalancing', Jun 30), ...]
```

**NSE Rebalancing Schedule:**

| Quarter | Rebalancing Date | Announcement | Effective Date |
|---------|-----------------|--------------|----------------|
| Q1 | Last trading day of March | 3 working days before | T+1 |
| Q2 | Last trading day of June | 3 working days before | T+1 |
| Q3 | Last trading day of September | 3 working days before | T+1 |
| Q4 | Last trading day of December | 3 working days before | T+1 |

**Actions per rebalancing:**
1. **Recalculate IWF**: 6-month average free-float market cap
2. **Update weights**: Based on latest market cap and free-float
3. **Add/Remove constituents**: Based on eligibility
4. **Adjust caps**: Apply weighting limits (e.g., 3% max in dividend indices)
5. **Announce**: Press release 3 working days before effective date

**Example Q1 2026 changes:**
```
Removed (fell out of top 50):
- Bharti Airtel: Rank dropped from 48 → 52

Added (entered top 50):
- SBI: Rank improved from 52 → 49

Changed weights:
- Reliance: 6.8% → 6.5% (market cap increased, % decreased)
- INFY: 2.9% → 3.2% (market cap increased faster than index)
```

---

## Part 7: Index Governance & Maintenance

### NSE Index Committees

1. **Index Advisory Committee**: Macro policy & methodology review
2. **Index Maintenance Sub-Committee**: Operational management, constituent changes
3. **Index Oversight Committee**: Challenge & oversight of methodology

### Data Quality Checks

NSE requires:
- **Prices**: Regulated prices from NSE
- **Shares outstanding**: From NSE/company filings
- **Free-float data**: 6-month rolling average
- **Dividend data**: Ex-dividend dates & amounts
- **Corporate actions**: Splits, mergers, demergers, bonus issues

### Handling Corporate Actions

**Merger/Amalgamation Example (Raytheon + UTC → RTX):**
- Transferor (UTC) excluded on ex-date
- Replacement made for indices with fixed constituents
- No replacement for indices with variable constituents
- Equity shares & IWF updated based on merger terms

**Demerger/Spin-off Example (Parent → Child):**
- Demerged company retained in index
- Spin-off entity added as dummy stock (price = 0)
- After price discovery in SPOS, dummy stock replaced with actual stock
- Weightage calculated based on both securities

---

## Part 8: Practical Implementation

### Example 1: Build Nifty 50-like Index

```python
# Step 1: Get data
tickers = ['RELIANCE.NS', 'TCS.NS', 'HDFC.NS', ...]
price_data = fetch_5_year_data(tickers)
market_caps = fetch_market_caps(tickers)

# Step 2: Screen eligible
builder = NSEIndexBuilder()
eligible = builder.screen_eligible_universe(tickers, price_data)

# Step 3: Rank by market cap
ranked = builder.rank_by_market_cap(eligible, market_caps)

# Step 4: Constitute Nifty 50
nifty_50 = builder.nifty_50_constitution(ranked)

# Step 5: Calculate index
index_series = builder.calculate_market_cap_index(nifty_50, price_data)

# Step 6: Generate report
report = builder.generate_index_report('Nifty 50', nifty_50, index_series)
```

### Example 2: Custom Quality-Dividend Index

```python
# Start with Nifty 50
nifty_50 = builder.nifty_50_constitution(ranked)

# Filter for quality
quality = builder.nifty_quality_50(nifty_50, fundamental_data)

# Subset for dividends
dividend_stocks = quality[quality['dividend_yield'] >= 2.5]

# Equal weight allocation
dividend_stocks['weight'] = 100 / len(dividend_stocks)

# Calculate index with dividends
tri_index = builder.calculate_total_return_index(
    dividend_stocks, price_data, dividends
)
```

### Example 3: Quarterly Rebalancing Workflow

```python
# Get rebalancing dates
schedule = builder.quarterly_rebalancing_schedule(2026)

for quarter_name, rebal_date in schedule:
    print(f"\n{quarter_name} - {rebal_date.date()}")
    
    # Get data as of rebalancing date
    historical_data = get_data_as_of(rebal_date)
    
    # Recalculate eligibility & weights
    eligible = builder.screen_eligible_universe(tickers, historical_data)
    ranked = builder.rank_by_market_cap(eligible, market_caps)
    constituents = builder.nifty_50_constitution(ranked)
    
    # Identify changes
    old_constituents = previous_nifty_50
    additions = set(constituents['ticker']) - set(old_constituents['ticker'])
    deletions = set(old_constituents['ticker']) - set(constituents['ticker'])
    
    print(f"  Added: {additions}")
    print(f"  Removed: {deletions}")
    print(f"  New weights: {constituents[['ticker', 'nifty50_weight']].to_dict()}")
```

---

## Key Insights from NSE Methodology

### 1. Free-Float Adjustment
- **Why**: Prevents family-held companies from dominating
- **Large-cap**: 60-75% free-float (actively traded)
- **Mid-cap**: 50-60% free-float (less liquidity)
- **Small-cap**: 40-50% free-float (controlled ownership)

### 2. Liquidity Requirements
- **Impact cost**: <0.50% for ₹10 Cr basket (Nifty 50)
- **Trading frequency**: ≥90% of days (prevents illiquid stocks)
- **Min IWF**: 10% (ensures tradability)

### 3. Quarterly Rebalancing
- **Why**: Reflects changes in company size, liquidity, quality
- **Timing**: Last trading day of each quarter
- **Announcement**: 3 working days advance notice
- **Market impact**: Automatic rebalancing creates predictable flows

### 4. Capping Mechanisms
- **Nifty 50**: Uncapped (only IWF applied), but naturally concentrated
- **Dividend Opportunities**: 3% cap per stock (diversification)
- **Equal-weight indices**: 2% cap (prevents concentration)

### 5. Total Return vs Price Return
- **Price Index (PR)**: Only capital appreciation/depreciation
- **Total Return Index (TRI)**: Includes dividend reinvestment
- **Difference**: ~1-2pp annually (from dividend yield)

---

## Common Pitfalls to Avoid

### ❌ Mistake 1: Including illiquid stocks
**Problem**: Low free-float, fails 90% trading test
**Solution**: Apply NSE's 90% trading frequency + IWF ≥10% filters

### ❌ Mistake 2: Not rebalancing quarterly
**Problem**: Index drifts from methodology, old constituents remain
**Solution**: Implement quarterly rebalancing on fixed schedule (Mar/Jun/Sep/Dec)

### ❌ Mistake 3: Wrong free-float factors
**Problem**: Overstates large-cap weight, understates liquidity
**Solution**: Use NSE's published IWF (6-month rolling average)

### ❌ Mistake 4: Ignoring corporate actions
**Problem**: Split/bonus distorts price levels, merger creates gaps
**Solution**: Track NSE's corporate action adjustments (IWF updates)

### ❌ Mistake 5: Missing dividend impact
**Problem**: 2% gap between Price and Total Return Index
**Solution**: Use TRI for true performance, PR for price movements only

---

## References

- **NSE Indices Methodology Document**: June 2026
- **NSE Website**: www.niftyindices.com
- **Index Constituents**: Updated real-time on NSE website
- **Quarterly Announcements**: Index Maintenance Sub-Committee press releases

---

**Last Updated**: July 2026  
**Version**: 1.0  
**Compliance**: IOSCO Principles for Financial Benchmarks
