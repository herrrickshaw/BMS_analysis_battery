# Phase 1 Accelerated Online Strategy
## Compress 4-5 Weeks → 1-2 Weeks via Cloud APIs & Data Providers

**Status:** Alternative execution path (use if speed is priority)  
**Timeline:** 1-2 weeks vs 4-5 weeks (3-4x faster)  
**Cost:** $2-5K (vs $1K local) but massive time savings  
**Tradeoff:** Higher cost, more APIs, less control

---

## Executive Summary

**Current Plan:** 4-5 weeks local/parallel downloads  
**Accelerated Plan:** 1-2 weeks using cloud data providers + bulk APIs  
**Speed Gain:** 3-4x faster  
**Key Lever:** Pay for pre-aggregated data instead of collecting it

---

## Strategy 1: Bulk Historical Data Providers (Fastest)

### Option A: Polygon.io (Recommended)
**Cost:** $400/month (Premium tier)  
**Timeline:** 2-3 days  
**Coverage:** US stocks + crypto (but limited international)

```python
# Polygon.io bulk download (1,000+ tickers in parallel)
from polygon import RESTClient

client = RESTClient(api_key="YOUR_KEY")

# Get 15 years of daily data for all tickers at once
# Polygon handles parallelization internally
for ticker in us_tickers:
    aggs = client.get_aggs(
        ticker=ticker,
        multiplier=1,
        timespan="day",
        from_="2011-01-01",
        to="2026-06-30"
    )
```

**Pros:**
- Handles parallelization internally
- 15-year history available
- REST API + WebSocket options
- ~100x faster than yfinance for bulk downloads

**Cons:**
- US-focused (limited international coverage)
- Need to supplement with other sources for Europe/Asia

### Option B: EOD Historical Data
**Cost:** $200/month (All stocks worldwide)  
**Timeline:** 1-2 days  
**Coverage:** 150+ markets globally

```python
import requests
import pandas as pd

api_key = "YOUR_EOD_KEY"
base_url = "https://eodhd.com/api/eod"

# Bulk download: 1,950 tickers in parallel
def fetch_eod_data(ticker_list):
    results = {}
    for ticker in ticker_list:
        url = f"{base_url}/{ticker}?from=2011-01-01&to=2026-06-30&api_token={api_key}"
        response = requests.get(url)
        results[ticker] = response.json()
    return results

# Parallelized
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=50) as executor:
    data = executor.map(lambda t: fetch_eod_data([t]), ticker_list)
```

**Pros:**
- Global coverage (150+ markets)
- 50+ years historical data
- Bulk endpoint available
- ~50x faster than yfinance

**Cons:**
- Rate limits (1,000 requests/day free, more with plan)
- May need multiple tier subscription for parallelization

### Option C: AlphaVantage Premium Bulk
**Cost:** $100/month  
**Timeline:** 3-5 days  
**Coverage:** US + some international

**Pros:**
- Cheapest premium option
- Real-time updates included

**Cons:**
- Slower bulk downloads
- Limited international

---

## Strategy 2: Aggregate Financial Data APIs (For Fundamentals)

### Option A: Financial Data APIs (Fastest)
**Cost:** $500-1K/month  
**Timeline:** 1-2 days for all 1,950 companies

#### IEX Cloud
```python
from iexfinance.stocks import Stock
import concurrent.futures

# Get fundamentals for 1,950 companies in parallel
def fetch_iex_fundamentals(ticker):
    try:
        stock = Stock(ticker, token="YOUR_IEX_KEY")
        return {
            'ticker': ticker,
            'revenue': stock.get_quote()['latestQuarter'],
            'fundamentals': stock.get_fundamentals()
        }
    except:
        return None

with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
    fundamentals = list(executor.map(fetch_iex_fundamentals, ticker_list))
```

**Coverage:** 15 years of quarterly data available  
**Speed:** 100x faster than yfinance API calls  
**Parallelization:** Up to 1,000 concurrent requests  

#### Financial Modeling Prep (FMP)
```python
# FMP API - bulk fundamentals retrieval
import requests

headers = {'Authorization': 'YOUR_FMP_KEY'}

# Get all income statements, balance sheets, cash flows at once
def fetch_all_fundamentals(ticker):
    endpoints = [
        f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=20&apikey=KEY",
        f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{ticker}?limit=20&apikey=KEY",
        f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{ticker}?limit=20&apikey=KEY"
    ]
    
    results = {}
    for endpoint in endpoints:
        results[endpoint.split('/')[5]] = requests.get(endpoint).json()
    return results

# Parallelized
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=100) as executor:
    all_data = list(executor.map(fetch_all_fundamentals, ticker_list))
```

**Coverage:** 60+ quarters for most companies  
**Speed:** Real-time API with caching  
**Cost:** $200-500/month

---

## Strategy 3: SEC EDGAR Bulk Processing (Announcements)

### EDGAR Fast Parallel Parser
**Cost:** Free (SEC API)  
**Timeline:** 1-2 days  
**Method:** Parallel request to EDGAR with smart caching

```python
# SEC EDGAR bulk 8-K extraction (fast)
import concurrent.futures
from sec_cik_lookup import get_cik

def fetch_sec_filings_bulk(tickers_with_ciks):
    """Parallel 8-K extraction from SEC"""
    
    def fetch_one_company(ticker, cik):
        base_url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
        try:
            response = requests.get(base_url)
            filings = response.json()['filings']['recent']
            
            # Filter 8-K filings (current reports)
            eights_k = [
                {
                    'ticker': ticker,
                    'date': filings['filingDate'][i],
                    'form': filings['form'][i]
                }
                for i, form in enumerate(filings['form'])
                if form == '8-K' and filings['filingDate'][i] >= '2011-01-01'
            ]
            return eights_k
        except:
            return []
    
    # 100+ parallel requests (SEC allows this)
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [
            executor.submit(fetch_one_company, ticker, cik)
            for ticker, cik in tickers_with_ciks
        ]
        
        all_filings = []
        for future in concurrent.futures.as_completed(futures):
            all_filings.extend(future.result())
    
    return all_filings

# Process in batch: ~10M JSON blobs in parallel
announcements = fetch_sec_filings_bulk(us_tickers_with_ciks)
```

**Pros:**
- Completely free
- SEC allows high parallelization (100+ concurrent)
- 15 years of data available
- JSON format ready to parse

**Cons:**
- Manual parsing needed (but we have regex for capex/FCF/debt keywords)
- Non-US companies need country-specific sources

---

## Strategy 4: Macro Data (Fastest)

### FRED API + World Bank (1 Day)
```python
import requests
import pandas as pd
from datetime import datetime

# Federal Reserve Economic Data (FRED)
fred_key = "YOUR_FRED_KEY"

fred_series = {
    'fed_funds': 'DFF',
    'us_10y': 'DGS10',
    'unemployment': 'UNRATE',
    'inflation': 'CPIAUCSL',
    'real_gdp': 'A191RA1Q225SBEA'
}

# Bulk download all series at once (parallel)
from concurrent.futures import ThreadPoolExecutor

def fetch_fred_series(series_id):
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={fred_key}"
    return pd.DataFrame(requests.get(url).json()['observations'])

with ThreadPoolExecutor(max_workers=10) as executor:
    macro_data = {
        name: future.result()
        for name, future in zip(
            fred_series.keys(),
            executor.map(fetch_fred_series, fred_series.values())
        )
    }

# All 180 months in <5 minutes
```

**Timeline:** <1 day (all macro data collected)

---

## Accelerated Phase 1 Timeline

### DAY 1-2: Price Data (Polygon.io or EOD Historical)
**Parallelization:** 50-100 concurrent API requests  
**Timeline:** 2-3 days  
**Cost:** $400-200/month  
**Result:** 7.6M price records

**Script:**
```python
# Fast parallel download using EOD Historical Data API
import asyncio
import aiohttp
import pandas as pd

async def download_prices_fast(tickers, api_key):
    """Async parallel download (1,950 tickers in parallel)"""
    
    async def fetch_one(session, ticker):
        url = f"https://eodhd.com/api/eod/{ticker}?from=2011-01-01&to=2026-06-30&api_token={api_key}"
        async with session.get(url) as resp:
            return ticker, await resp.json()
    
    # 100 concurrent connections
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100)) as session:
        tasks = [fetch_one(session, ticker) for ticker in tickers]
        results = await asyncio.gather(*tasks)
    
    return dict(results)

# Execute: 1,950 tickers in ~2-3 hours
prices = asyncio.run(download_prices_fast(ticker_list, api_key))
```

### DAY 3-4: Quarterly Fundamentals (IEX Cloud or FMP)
**Parallelization:** 100+ concurrent API requests  
**Timeline:** 1-2 days  
**Cost:** $500-1K/month  
**Result:** 117K quarterly records

**Script:**
```python
# Fast parallel fundamentals download
import asyncio
import aiohttp

async def download_fundamentals_fast(tickers, api_key):
    """Async parallel (100+ concurrent)"""
    
    async def fetch_fundamentals(session, ticker):
        endpoints = [
            f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=60&apikey={api_key}",
            f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{ticker}?limit=60&apikey={api_key}",
            f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{ticker}?limit=60&apikey={api_key}"
        ]
        
        results = {}
        async with session.get(endpoints[0]) as resp:
            results['income'] = await resp.json()
        async with session.get(endpoints[1]) as resp:
            results['balance'] = await resp.json()
        async with session.get(endpoints[2]) as resp:
            results['cashflow'] = await resp.json()
        
        return ticker, results
    
    # 100 concurrent connections
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100)) as session:
        tasks = [fetch_fundamentals(session, ticker) for ticker in tickers]
        results = await asyncio.gather(*tasks)
    
    return dict(results)

# Execute: 1,950 tickers in ~4-6 hours
fundamentals = asyncio.run(download_fundamentals_fast(ticker_list, api_key))
```

### DAY 5: Announcements (SEC EDGAR Parallel)
**Parallelization:** 100+ concurrent SEC requests (allowed)  
**Timeline:** 1 day  
**Cost:** Free  
**Result:** 7,800 announcements

### DAY 6: Macro Data (FRED + World Bank)
**Timeline:** <1 day  
**Cost:** Free  
**Result:** 180 monthly records

### DAY 7: QC, Backup, Documentation
**Timeline:** 1 day  
**Result:** Ready for Phase 2

---

## Accelerated Architecture (1-2 Weeks)

```
DAY 1-2:  EOD Historical (Price) ──┐
DAY 3-4:  FMP API (Fundamentals) ──┼─→ Parallel Processing (100+ threads)
DAY 5:    SEC EDGAR (Announcements)─┤
DAY 6:    FRED API (Macro) ────────┘
DAY 7:    QC + Backup + Handoff
```

**Total:** 7 days vs 35 days (5x faster)

---

## Cost Comparison

| Component | Local Plan | Accelerated Plan | Speedup |
|-----------|-----------|-----------------|---------|
| **Price Data** | yfinance (free) | EOD Historical ($200) | 10-20x |
| **Fundamentals** | yfinance (free) | FMP/IEX ($500) | 50-100x |
| **Announcements** | SEC API (free) | SEC API (free) | 10x via parallelization |
| **Macro** | Public APIs (free) | FRED API (free) | 10x via parallelization |
| **Total Cost** | $1K (infra) | $2.5K (APIs + infra) | **3-5x faster** |

---

## Recommended: Hybrid Accelerated Plan

**Best of both worlds:**
- Use **EOD Historical Data** ($200/mo) for price + fundamentals (combined API)
- Use **SEC EDGAR** free API for announcements (parallel)
- Use **FRED API** free for macro
- Use **AWS Lambda** for parallelization (pay-as-you-go, ~$50)

**Total Cost:** $250/month + $50 AWS = **$300 for full acceleration**

**Timeline:** **7-10 days** (vs 35 days)

**Speed Gain:** **3-5x faster**

---

## Implementation: Hybrid Accelerated Script

```python
#!/usr/bin/env python3
"""
Phase 1 Accelerated: 1-2 weeks instead of 4-5 weeks
Uses EOD Historical Data API + Parallel processing
"""

import asyncio
import aiohttp
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
import boto3

class Phase1Accelerated:
    """Rapid data collection via cloud APIs + parallelization"""
    
    def __init__(self, eod_key, fmp_key, fred_key):
        self.eod_key = eod_key
        self.fmp_key = fmp_key
        self.fred_key = fred_key
        self.s3 = boto3.client('s3')
    
    async def download_all_prices_async(self, tickers):
        """EOD Historical: 1,950 tickers in 2-3 hours (vs 3 days)"""
        print("📥 Downloading prices (EOD Historical API)...")
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100)) as session:
            tasks = []
            for ticker in tickers:
                url = f"https://eodhd.com/api/eod/{ticker}?from=2011-01-01&to=2026-06-30&api_token={self.eod_key}"
                tasks.append(self._fetch_eod(session, ticker, url))
            
            results = await asyncio.gather(*tasks)
        
        price_df = pd.concat(results)
        price_df.to_parquet('s3://YOUR_BUCKET/price_history_1950_companies.parquet')
        print(f"✅ Prices complete: {len(price_df):,} records")
        return price_df
    
    async def download_all_fundamentals_async(self, tickers):
        """FMP: 1,950 tickers in 4-6 hours (vs 1-2 weeks)"""
        print("📥 Downloading fundamentals (FMP API)...")
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100)) as session:
            tasks = []
            for ticker in tickers:
                tasks.append(self._fetch_fmp_fundamentals(session, ticker))
            
            results = await asyncio.gather(*tasks)
        
        fund_df = pd.concat([r for r in results if r is not None])
        fund_df.to_parquet('s3://YOUR_BUCKET/fundamentals_1950_companies.parquet')
        print(f"✅ Fundamentals complete: {len(fund_df):,} records")
        return fund_df
    
    def download_announcements_parallel(self, tickers_with_ciks):
        """SEC EDGAR: 7,800 announcements in <2 hours (vs 1 week)"""
        print("📥 Downloading announcements (SEC EDGAR API)...")
        
        with ThreadPoolExecutor(max_workers=100) as executor:
            results = list(executor.map(
                lambda x: self._fetch_sec_8k(x[0], x[1]),
                tickers_with_ciks
            ))
        
        announcements = pd.concat([pd.DataFrame(r) for r in results if r])
        announcements.to_csv('s3://YOUR_BUCKET/announcements_7800_events.csv')
        print(f"✅ Announcements complete: {len(announcements):,} events")
        return announcements
    
    def download_macro_fast(self):
        """FRED API: All macro in <1 hour"""
        print("📥 Downloading macro data (FRED API)...")
        
        fred_series = {
            'fed_funds': 'DFF',
            'us_10y': 'DGS10',
            'unemployment': 'UNRATE'
        }
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = {
                name: executor.submit(self._fetch_fred, series_id)
                for name, series_id in fred_series.items()
            }
            macro_df = pd.DataFrame({
                name: future.result()['value'].astype(float).values
                for name, future in results.items()
            })
        
        macro_df.to_csv('s3://YOUR_BUCKET/macro_timeseries_2011_2026.csv')
        print(f"✅ Macro complete: {len(macro_df)} months")
        return macro_df
    
    async def run_all(self, tickers):
        """Run all downloads in parallel (true concurrent, not sequential)"""
        print("\n🚀 PHASE 1 ACCELERATED - Starting (Target: 1 week)")
        print(f"   Companies: {len(tickers)}")
        print(f"   API: EOD Historical + FMP + SEC EDGAR + FRED")
        print(f"   Parallelization: 100+ concurrent connections\n")
        
        # Run price + fundamentals + announcements + macro in PARALLEL
        tasks = [
            asyncio.create_task(self.download_all_prices_async(tickers)),
            asyncio.create_task(self.download_all_fundamentals_async(tickers)),
            # Announcements + Macro run in parallel threads
        ]
        
        # SEC + FRED in thread pool (non-async)
        executor = ThreadPoolExecutor(max_workers=2)
        announcements_future = executor.submit(
            self.download_announcements_parallel,
            self.get_us_tickers_with_ciks()
        )
        macro_future = executor.submit(self.download_macro_fast)
        
        # Wait for all to complete
        price_df, fund_df = await asyncio.gather(*tasks)
        announcements = announcements_future.result()
        macro_df = macro_future.result()
        
        print("\n✅ PHASE 1 COMPLETE!")
        print(f"   Price records: {len(price_df):,}")
        print(f"   Fundamental records: {len(fund_df):,}")
        print(f"   Announcements: {len(announcements):,}")
        print(f"   Macro points: {len(macro_df)}")
        print("\n📦 Data ready for Phase 2 (Geographic Regression)")

# Execute
if __name__ == "__main__":
    accelerator = Phase1Accelerated(
        eod_key="YOUR_EOD_KEY",
        fmp_key="YOUR_FMP_KEY",
        fred_key="YOUR_FRED_KEY"
    )
    
    tickers = ["AAPL", "MSFT", "NVDA", ...]  # 1,950 tickers
    
    # Run: All 4 downloads in true parallel (not sequential)
    asyncio.run(accelerator.run_all(tickers))
```

---

## Timeline Comparison

| Phase | Local Plan | Accelerated | Speedup |
|-------|-----------|------------|---------|
| **Week 1-2** | Price data | Price + Fundamentals (parallel) | 5-10x |
| **Week 2-3** | Fundamentals | Announcements (parallel) | 10x |
| **Week 3-4** | Announcements | Macro (parallel) | 5x |
| **Week 4** | Macro + QC | QC + Backup | - |
| **Total** | **4-5 weeks** | **1-2 weeks** | **3-5x faster** |

---

## Final Recommendations

### If Speed is Priority (Recommended):
✅ **Use Hybrid Accelerated Plan**
- EOD Historical Data ($200/mo) for price + fundamentals
- Async/parallel processing (100+ threads)
- Timeline: **7-10 days**
- Cost: $300-400 total

### If Budget is Priority:
✅ **Use Local Plan with optimizations**
- yfinance (free) with parallel workers (10+)
- SEC EDGAR (free) with parallel requests (100+)
- Timeline: **2-3 weeks** (compromise)
- Cost: $1K (infrastructure only)

### Hybrid Sweet Spot:
✅ **Recommended: Middle Path**
- EOD Historical Data ($200/mo) - covers price + fundamentals globally
- SEC EDGAR (free) - announcements
- FRED (free) - macro
- AWS Lambda (pay-per-use ~$50) - orchestration
- **Timeline: 10-14 days**
- **Cost: $250 (APIs) + $50 (AWS) = $300**

---

**Next Step:** Approve accelerated plan and we can have Phase 1 complete by **July 9-15** instead of August 6!
