# WORKFLOWS & DATA FLOWS
## Global Multi-Market Portfolio Analysis Platform

**Date:** 2026-07-07  
**Status:** Complete Documentation  
**Scope:** All 4 phases integrated

---

## TABLE OF CONTENTS

1. [Daily Portfolio Monitoring Workflow](#daily-portfolio-monitoring-workflow)
2. [Risk Management Workflow](#risk-management-workflow)
3. [Rebalancing Execution Workflow](#rebalancing-execution-workflow)
4. [Alert & Notification Workflow](#alert--notification-workflow)
5. [Reporting & Analytics Workflow](#reporting--analytics-workflow)
6. [ETL Pipeline Workflow](#etl-pipeline-workflow)
7. [System Integration Flows](#system-integration-flows)

---

# DAILY PORTFOLIO MONITORING WORKFLOW

## Workflow Overview

```
Daily Portfolio Monitoring (Every Trading Day at 4:30pm UTC)

┌─────────────────────────────────────────────────────┐
│ 1. MARKET CLOSE TRIGGER (4:30pm UTC)               │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 2. DATA COLLECTION (Parallel - 5 min window)       │
├─────────────────────────────────────────────────────┤
│ ├─ Cassandra: Fetch live quotes (all 8 markets)   │
│ ├─ yfinance: Fetch close prices + volume           │
│ ├─ FX Service: Fetch EOD FX rates                  │
│ └─ Broker API: Fetch current holdings              │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 3. DATA NORMALIZATION (Sequential - 2 min)         │
├─────────────────────────────────────────────────────┤
│ ├─ Strip India ticker suffixes (.NS/.BO)           │
│ ├─ Convert all prices to USD                       │
│ ├─ Handle missing data (forward fill, interpolate) │
│ └─ Validate data quality (outliers, range checks)  │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 4. PORTFOLIO CALCULATION (Sequential - 3 min)      │
├─────────────────────────────────────────────────────┤
│ ├─ Calculate current market values (qty × price)   │
│ ├─ Calculate allocation % (by market)              │
│ ├─ Calculate daily P&L (current - previous close)  │
│ ├─ Calculate returns (daily, YTD, 3Y, 5Y)          │
│ ├─ Calculate CAGR (annualized)                     │
│ └─ Insert into portfolio_daily_snapshot            │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 5. BENCHMARK COMPARISON (Sequential - 1 min)       │
├─────────────────────────────────────────────────────┤
│ ├─ Fetch benchmark prices (S&P, Nifty, etc.)      │
│ ├─ Calculate benchmark returns                     │
│ ├─ Calculate excess returns (portfolio - benchmark)│
│ └─ Calculate information ratio (excess/tracking)   │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 6. RISK METRIC COMPUTATION (Parallel - 2 min)      │
├─────────────────────────────────────────────────────┤
│ ├─ Calculate volatility (annualized, 252 days)     │
│ ├─ Calculate VaR (95%, 99% confidence)             │
│ ├─ Calculate max drawdown (YTD, 3Y)                │
│ ├─ Recalculate correlation matrix (8x8)            │
│ ├─ Calculate beta vs MSCI ACWI                     │
│ └─ Insert into var_and_risk_daily                  │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 7. DRIFT & REBALANCE CHECK (Sequential - 1 min)    │
├─────────────────────────────────────────────────────┤
│ ├─ Calculate drift % (current vs target allocation)│
│ ├─ Check drift against triggers (5%, 10%)          │
│ ├─ Accumulate drift days since last rebalance      │
│ ├─ Estimate next rebalancing date                  │
│ └─ Update drift_accumulation table                 │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 8. KPI AGGREGATION (Sequential - 1 min)            │
├─────────────────────────────────────────────────────┤
│ ├─ Calculate Sharpe ratio (30-day trailing)        │
│ ├─ Calculate Sortino ratio (downside volatility)   │
│ ├─ Calculate win rate (% positive days)            │
│ ├─ Calculate tracking error vs benchmark           │
│ └─ Cache KPIs for dashboard display                │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 9. ALERT GENERATION (Async - Parallel)             │
├─────────────────────────────────────────────────────┤
│ ├─ Check red thresholds (max DD, VaR)              │
│ ├─ Check yellow thresholds (drift, Sharpe)         │
│ ├─ Check info thresholds (rebalancing due)         │
│ ├─ Route alerts to Slack/Email                     │
│ └─ Log to alert_history table                      │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 10. DASHBOARD UPDATE (Real-time)                   │
├─────────────────────────────────────────────────────┤
│ ├─ Push KPI updates via WebSocket                  │
│ ├─ Update performance summary chart                │
│ ├─ Update risk dashboard                           │
│ ├─ Update drift tracker                            │
│ └─ Highlight alerts (red/yellow/info)              │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 11. REPORT GENERATION (Async - Parallel)           │
├─────────────────────────────────────────────────────┤
│ ├─ Compile daily snapshot                          │
│ ├─ Generate PDF/HTML report                        │
│ ├─ Send email to stakeholders                      │
│ └─ Archive report (S3 / archive storage)           │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 12. COMPLETION & MONITORING (1 min)                │
├─────────────────────────────────────────────────────┤
│ ├─ Log ETL completion timestamp                    │
│ ├─ Monitor for errors / alerts                     │
│ ├─ Update system dashboard (Grafana)               │
│ └─ Trigger next daily job (tomorrow 4:30pm)        │
└─────────────────────────────────────────────────────┘

Total Runtime: ~20 minutes (4:30pm → 4:50pm UTC)
Tolerance: Must complete by 5:00pm (30 min buffer for overnight jobs)
```

## Detailed Steps

### Step 1: Market Close Trigger
**Trigger:** Daily at 4:30pm UTC  
**Mechanism:** APScheduler job queue  
**Idempotency:** Check if snapshot already exists for today; skip if present

```python
async def daily_portfolio_snapshot_job():
    portfolio_id = UUID("...")
    today = date.today()
    
    # Check if already run
    existing = db.query(PortfolioDailySnapshot).filter(
        portfolio_id=portfolio_id,
        snapshot_date=today
    ).first()
    
    if existing:
        log.info(f"Snapshot already exists for {today}, skipping")
        return
    
    # Proceed with full ETL
    await run_daily_etl()
```

### Step 2: Data Collection (Parallel)
**Duration:** ~5 minutes  
**Parallelization:** 4 concurrent workers (Cassandra, yfinance, FX, broker)

```python
async def collect_market_data():
    futures = [
        fetch_cassandra_quotes(),      # Live quotes from cache
        fetch_yfinance_closes(),        # Closing prices + volume
        fetch_fx_rates(),               # Currency conversion
        fetch_broker_holdings()         # Current positions
    ]
    
    results = await asyncio.gather(*futures, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            log.error(f"Data collection failed: {result}")
            # Fallback: Use previous day's data + calculated forward prices
            
    return results
```

### Step 3: Data Normalization
**Duration:** ~2 minutes  
**Key Operations:**
- Strip India ticker suffixes
- FX normalization to USD
- Handle missing data
- Outlier detection

```python
def normalize_prices(raw_data):
    df = pd.DataFrame(raw_data)
    
    # Strip India suffix (.NS, .BO)
    df['ticker'] = df['ticker'].str.replace(r'\.NS|\.BO$', '', regex=True)
    
    # FX normalization
    for idx, row in df.iterrows():
        if row['market'] != 'usa':
            fx_rate = fx_cache.get(f"{row['currency']}/USD")
            df.loc[idx, 'close_usd'] = row['close_local'] * fx_rate
    
    # Forward-fill missing data
    df.fillna(method='ffill', limit=1, inplace=True)
    
    # Outlier detection (price change >20% one-day)
    df['price_change'] = df['close_usd'].pct_change()
    outliers = df[df['price_change'].abs() > 0.20]
    if len(outliers) > 0:
        log.warning(f"Outliers detected: {outliers}")
        # Use previous close instead
        
    return df
```

### Step 4: Portfolio Calculation
**Duration:** ~3 minutes  
**Calculation Order:** Atomic, no parallelization (to avoid race conditions)

```python
async def calculate_portfolio_snapshot():
    portfolio = db.query(Portfolio).get(portfolio_id)
    holdings = db.query(Holdings).filter(portfolio_id=portfolio_id).all()
    
    by_market = {}
    total_value_usd = 0
    
    for holding in holdings:
        market = holding.market
        if market not in by_market:
            by_market[market] = {'quantity': 0, 'value_usd': 0}
        
        # Get current price (normalized to USD)
        current_price = await get_price(holding.ticker, market)
        
        # Calculate holding value
        holding_value_usd = holding.quantity * current_price
        by_market[market]['value_usd'] += holding_value_usd
        total_value_usd += holding_value_usd
    
    # Calculate allocations and returns
    for market, data in by_market.items():
        allocation_pct = data['value_usd'] / total_value_usd * 100
        
        # Compare to target allocation
        target = portfolio.target_allocation[market]
        drift_pct = allocation_pct - target
        
        # Insert snapshot
        snapshot = PortfolioDailySnapshot(
            portfolio_id=portfolio_id,
            snapshot_date=date.today(),
            market=market,
            target_allocation_pct=target,
            current_allocation_pct=allocation_pct,
            drift_pct=drift_pct,
            total_value_usd=data['value_usd']
        )
        db.add(snapshot)
    
    db.commit()
```

### Step 5-12: Subsequent Steps
*(Similar implementation pattern - sequential/parallel execution, error handling, logging)*

---

# RISK MANAGEMENT WORKFLOW

## Workflow Overview

```
Risk Monitoring & Calculation (Every trading day + intraday)

┌─────────────────────────────────────────────────────────┐
│ DAILY RISK CALCULATION (4:35pm UTC, after portfolio)   │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 1. HISTORICAL RETURNS FETCH (Parallel - 2 min)         │
├─────────────────────────────────────────────────────────┤
│ ├─ Fetch last 252 trading days (1 year)                │
│ ├─ Calculate daily returns (log returns)               │
│ ├─ Detect & handle gaps (holidays, splits)             │
│ └─ Cache in Redis for performance                      │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 2. PORTFOLIO VOLATILITY CALCULATION (1 min)            │
├─────────────────────────────────────────────────────────┤
│ ├─ Calculate daily portfolio returns                   │
│ ├─ Calculate standard deviation (252 trading days)     │
│ ├─ Annualize (multiply by √252)                        │
│ └─ Store in volatility_tracking table                  │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 3. VALUE AT RISK CALCULATION (1 min)                   │
├─────────────────────────────────────────────────────────┤
│ ├─ Calculate parametric VaR (95%, 99%)                 │
│ │  VaR = portfolio_value × z_score × volatility       │
│ ├─ Calculate historical VaR (percentile of returns)   │
│ ├─ Calculate CVaR (average of tail losses)            │
│ └─ Store in var_and_risk_daily table                  │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 4. CORRELATION MATRIX UPDATE (1 min)                   │
├─────────────────────────────────────────────────────────┤
│ ├─ Fetch 8-market indices (last 252 days)             │
│ ├─ Calculate Pearson correlation (8x8 matrix)          │
│ ├─ Store in volatility_tracking (JSONB format)         │
│ └─ Detect high correlation pairs (>0.8)                │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 5. CURRENCY EXPOSURE ANALYSIS (1 min)                  │
├─────────────────────────────────────────────────────────┤
│ ├─ Calculate gross FX exposure (by currency)           │
│ ├─ Calculate net exposure (after hedges)               │
│ ├─ Calculate FX impact (since last rebalance)          │
│ ├─ Calculate FX volatility (annualized)                │
│ └─ Update currency_exposure table                      │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 6. SECTOR CONCENTRATION CHECK (1 min)                  │
├─────────────────────────────────────────────────────────┤
│ ├─ Classify holdings by sector (by market)             │
│ ├─ Calculate portfolio weight % (by sector)            │
│ ├─ Compare to benchmark weights                        │
│ ├─ Flag concentration risk (>25% any sector)           │
│ └─ Update sector_concentration table                   │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 7. DRAWDOWN TRACKING (1 min)                           │
├─────────────────────────────────────────────────────────┤
│ ├─ Calculate cumulative max (peak portfolio value)     │
│ ├─ Calculate drawdown from peak (current - peak)       │
│ ├─ Update max drawdown (YTD and 3Y)                    │
│ └─ Flag if approaching -22% threshold                 │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ INTRADAY RISK MONITORING (Every 60 seconds during     │
│ trading hours, real-time)                              │
│                                                         │
│ ├─ Fetch current intraday prices (WebSocket)          │
│ ├─ Calculate intraday portfolio value                 │
│ ├─ Calculate intraday return %                        │
│ ├─ Update 1-day VaR (95% confidence)                  │
│ └─ Check if VaR breached (>2% portfolio)              │
└─────────────────────────────────────────────────────────┘
```

## Risk Thresholds & Alerts

```
VOLATILITY TRIGGERS:
├─ Green: 12-15% (target zone)
├─ Yellow: 15-18% (caution, monitor)
└─ Red: >18% (potential de-risk)

VALUE AT RISK TRIGGERS:
├─ Green: <1% portfolio value (1-day loss)
├─ Yellow: 1-2% portfolio value (monitor)
└─ Red: >2% portfolio value (de-risk immediately)

DRAWDOWN TRIGGERS:
├─ Green: -5% to 0% (normal range)
├─ Yellow: -5% to -22% (monitor)
└─ Red: >-22% (likely de-risk)

CORRELATION TRIGGERS:
├─ Alert: Any pair >0.85 (high divergence risk)
└─ Action: Reduce position size in correlated pair

SECTOR CONCENTRATION TRIGGERS:
├─ Alert: Any sector >25% (concentration risk)
└─ Action: Rebalance to <20% target
```

---

# REBALANCING EXECUTION WORKFLOW

## Workflow Overview

```
Rebalancing Cycle (Quarterly or Semi-Annual)

TRIGGER: Scheduled date OR manual trigger
TIME: Between market close (4:30pm) and next market open (9:30am next day)

┌─────────────────────────────────────────────────────┐
│ 1. PRE-REBALANCE ANALYSIS (2 days before)          │
├─────────────────────────────────────────────────────┤
│ ├─ Forecast market prices (to rebalance date)       │
│ ├─ Estimate current drift (given price forecast)   │
│ ├─ Calculate target quantities (by market)          │
│ ├─ Identify tax-loss harvesting opportunities      │
│ ├─ Estimate transaction costs                       │
│ └─ Generate pre-rebalance report                    │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 2. APPROVAL STEP (1 day before)                     │
├─────────────────────────────────────────────────────┤
│ ├─ Portfolio manager reviews forecast               │
│ ├─ Approves or modifies target weights              │
│ ├─ Approves tax-loss harvesting opportunities      │
│ └─ Confirms rebalancing date                        │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 3. EXECUTION DAY (Market close to 5:00pm)          │
├─────────────────────────────────────────────────────┤
│ ├─ Fetch latest prices & current holdings          │
│ ├─ Calculate shares to buy/sell (by market)         │
│ ├─ Break orders by execution priority:             │
│ │  1. Sell overweight positions (highest drift)    │
│ │  2. Buy underweight positions (highest drift)    │
│ │  3. Tax-loss harvesting sales                    │
│ ├─ Estimate slippage (market impact)                │
│ └─ Place orders via broker API                     │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 4. EXECUTION TRACKING (5pm → next market open)    │
├─────────────────────────────────────────────────────┤
│ ├─ Monitor order status (placed → filled)           │
│ ├─ Track execution prices vs forecast               │
│ ├─ Handle partial fills & rejections                │
│ ├─ Log all trades to rebalancing_execution_history  │
│ └─ Notify PM if execution deviates >2% from plan   │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 5. SETTLEMENT & CONFIRMATION (T+1 or T+2)         │
├─────────────────────────────────────────────────────┤
│ ├─ Confirm settlement of all trades                 │
│ ├─ Verify cash flows & positions                    │
│ ├─ Calculate realized gains/losses (for tax)        │
│ ├─ Update holdings in database                      │
│ └─ Reset drift counter (drift_pct = 0)              │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 6. POST-REBALANCE ANALYSIS (1-3 days after)        │
├─────────────────────────────────────────────────────┤
│ ├─ Calculate execution cost (basis points)          │
│ ├─ Compare to estimated cost (variance)             │
│ ├─ Analyze market impact (slippage)                 │
│ ├─ Verify new allocations meet targets              │
│ ├─ Calculate tax impact (realized gains/losses)     │
│ └─ Generate post-rebalance report                   │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ 7. ARCHIVE & REPORTING (End of week)                │
├─────────────────────────────────────────────────────┤
│ ├─ Archive all execution details                    │
│ ├─ Update rebalancing_schedule status               │
│ ├─ Generate quarterly report (if applicable)        │
│ └─ File tax documentation (realized gains/losses)   │
└─────────────────────────────────────────────────────┘
```

---

# ALERT & NOTIFICATION WORKFLOW

## Alert Generation & Routing

```
REAL-TIME ALERT PROCESSING

┌─────────────────────────────────────────────────┐
│ ALERT TRIGGER (From daily/intraday calculations)│
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ RULE EVALUATION (Alert Engine)                  │
├─────────────────────────────────────────────────┤
│                                                 │
│ IF metric_value > red_threshold THEN            │
│   ├─ alert_level = RED                          │
│   ├─ action = IMMEDIATE                         │
│   └─ routing = [email, slack, dashboard]        │
│                                                 │
│ ELSE IF metric_value > yellow_threshold THEN   │
│   ├─ alert_level = YELLOW                       │
│   ├─ action = MONITOR                           │
│   └─ routing = [slack, dashboard]               │
│                                                 │
│ ELSE IF info_condition THEN                    │
│   ├─ alert_level = INFO                         │
│   ├─ action = NOTIFY                            │
│   └─ routing = [slack]                          │
│                                                 │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ DEDUPLICATION CHECK                             │
├─────────────────────────────────────────────────┤
│ ├─ Compare to last 24hrs of alerts              │
│ ├─ If duplicate, increment counter only         │
│ ├─ Don't re-send if already active              │
│ └─ Mark resolved when metric returns to normal  │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ MESSAGE FORMATTING                              │
├─────────────────────────────────────────────────┤
│ ├─ Alert title: "{alert_level} {alert_type}"   │
│ ├─ Current value vs threshold                  │
│ ├─ Recommended action                          │
│ ├─ Link to dashboard (for context)             │
│ └─ Timestamp (UTC)                             │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ ROUTING (Async Workers)                         │
├─────────────────────────────────────────────────┤
│                                                 │
│ RED ALERTS:                                    │
│ ├─ Slack: @channel (urgent notification)       │
│ ├─ Email: PMs + Risk Officer + CTO             │
│ ├─ SMS: Portfolio Manager (phone call)          │
│ └─ Dashboard: Red banner + sound alert          │
│                                                 │
│ YELLOW ALERTS:                                 │
│ ├─ Slack: #portfolio-alerts (regular)           │
│ └─ Dashboard: Yellow highlight + notification   │
│                                                 │
│ INFO ALERTS:                                   │
│ ├─ Slack: Threaded message (no ping)            │
│ └─ Dashboard: Info badge                        │
│                                                 │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ AUDIT LOGGING                                   │
├─────────────────────────────────────────────────┤
│ ├─ Log all alerts to alert_history table        │
│ ├─ Record triggered_at timestamp                │
│ ├─ Record routing channels & delivery status    │
│ ├─ Update resolved_at when alert clears         │
│ └─ Retention: 2 years (compliance)              │
└─────────────────────────────────────────────────┘
```

---

# REPORTING & ANALYTICS WORKFLOW

## Report Generation Schedule

```
DAILY REPORTS (Every trading day, 5:00pm UTC)
├─ Daily Performance Snapshot
│  ├─ Portfolio CAGR, Sharpe, volatility
│  ├─ Daily P&L ($ and %)
│  ├─ Market contribution breakdown
│  ├─ Top/bottom performers
│  └─ Alerts triggered
└─ Distribution: Email to portfolio managers

WEEKLY REPORTS (Every Friday, 5:30pm UTC)
├─ Weekly Performance Review
│  ├─ Weekly returns vs benchmark
│  ├─ Volatility trend
│  ├─ Correlation changes
│  └─ Risk metrics summary
└─ Distribution: Email + Dashboard

MONTHLY REPORTS (1st day of month, 8:00am UTC)
├─ Monthly KPI Scorecard
│  ├─ CAGR (YTD, 1Y, 3Y, 5Y)
│  ├─ Sharpe ratio, Sortino, Information ratio
│  ├─ Max drawdown, win rate, tracking error
│  ├─ Cost tracking vs budget
│  └─ Performance attribution by market
├─ Monthly Performance Report (PDF)
│  ├─ Executive summary
│  ├─ Detailed performance analysis
│  ├─ Risk metrics
│  ├─ Market allocation chart
│  └─ Outlook for next month
└─ Distribution: Email to executives + stakeholders

QUARTERLY REPORTS (10th of quarter month, 9:00am UTC)
├─ Quarterly Strategy Review
│  ├─ Strategic objectives vs actuals
│  ├─ Rebalancing execution review
│  ├─ Tax efficiency analysis
│  ├─ Currency hedge effectiveness
│  ├─ Recommendations for next quarter
│  └─ Risk management summary
├─ Quarterly Performance Report (PDF + presentation)
├─ Board-ready executive summary
└─ Distribution: Email + in-person review

ANNUAL REPORTS (January 2nd, 9:00am UTC)
├─ Annual Strategy Review
│  ├─ Full year CAGR vs target
│  ├─ Risk metrics (Sharpe, volatility, max DD)
│  ├─ Tax efficiency (all markets)
│  ├─ Cost analysis (total rebalancing cost)
│  ├─ Peer benchmarking
│  └─ Strategic recommendations
├─ Annual Performance Report (PDF + charts)
├─ Tax reporting document (by jurisdiction)
├─ 10-K equivalent for investors
└─ Distribution: All stakeholders + regulatory bodies
```

---

# ETL PIPELINE WORKFLOW

## Daily ETL Process

```
DAILY ETL PIPELINE (4:30pm - 5:00pm UTC)

                    ┌─ Cassandra
                    │  (Real-time quotes)
Market Close → ETL ─┤─ yfinance
(4:30pm UTC)        │  (OHLCV history)
                    └─ FX APIs
                       (Spot rates)
                       
        ↓ (Data Collection)
        
    [Validate & Normalize]
    ├─ Check for missing data
    ├─ Strip ticker suffixes
    ├─ Convert to USD
    └─ Detect outliers
    
        ↓ (Data Transformation)
        
    [Calculate Metrics]
    ├─ Portfolio P&L
    ├─ Risk metrics (volatility, VaR)
    ├─ Correlation matrix
    ├─ Currency exposure
    └─ Drift tracking
    
        ↓ (Quality Checks)
        
    [Validate Results]
    ├─ Assert CAGR in expected range
    ├─ Assert Sharpe in expected range
    ├─ Assert allocations sum to 100%
    ├─ Assert no null values in key fields
    └─ Alert if validation fails
    
        ↓ (Data Load)
        
    [Persist to PostgreSQL]
    ├─ portfolio_daily_snapshot
    ├─ portfolio_intraday_quotes
    ├─ volatility_tracking
    ├─ var_and_risk_daily
    ├─ currency_exposure
    ├─ sector_concentration
    ├─ drift_accumulation
    └─ alert_history
    
        ↓ (Publishing)
        
    [Push to Dashboard]
    ├─ WebSocket broadcast to connected clients
    ├─ Update in-memory cache (Redis)
    ├─ Trigger real-time KPI updates
    └─ Highlight alerts (red/yellow/info)
    
        ↓ (Monitoring)
        
    [Log & Alert]
    ├─ Log completion timestamp
    ├─ Log metrics (rows processed, duration)
    ├─ Alert if runtime exceeds 30 minutes
    ├─ Alert if any validation failures
    └─ Update Prometheus metrics

Retry Logic:
├─ Max retries: 3
├─ Backoff: Exponential (1s → 2s → 4s)
├─ On failure: Use previous day's data + forward calculation
└─ Alert: Notify on 2nd failure, escalate on 3rd
```

---

# SYSTEM INTEGRATION FLOWS

## Data Flow Across All Systems

```
┌──────────────────────────────────────────────────────────────┐
│                    EXTERNAL SOURCES                          │
├────────────────┬──────────────┬──────────────────────────────┤
│  yfinance      │  NSE/BSE     │  FX APIs                     │
│  OHLCV history │  Real-time   │  Spot rates                  │
└────────┬───────┴──────┬───────┴──────────────┬───────────────┘
         │              │                      │
┌────────▼──────────────▼──────────────────────▼───────────────┐
│                 DATA FETCHERS                                │
│                (Parallel collection)                         │
└────────┬──────────────┬──────────────────────┬───────────────┘
         │              │                      │
┌────────▼──────────────▼──────────────────────▼───────────────┐
│            NORMALIZATION & VALIDATION                        │
│  ├─ Strip ticker suffixes                                   │
│  ├─ Convert to USD                                          │
│  ├─ Handle missing data                                     │
│  └─ Detect & flag outliers                                  │
└────────┬──────────────────────────────────────────┬──────────┘
         │                                          │
┌────────▼──────────────────┐        ┌─────────────▼──────────┐
│    PORTFOLIO CALCULATOR    │        │  RISK CALCULATOR       │
│  ├─ Current allocation    │        │  ├─ Volatility         │
│  ├─ Daily P&L            │        │  ├─ VaR                │
│  ├─ Returns (YTD, 3Y, 5Y) │        │  ├─ Correlation        │
│  └─ CAGR, Sharpe         │        │  ├─ Beta               │
└────────┬──────────────────┘        │  └─ Max drawdown       │
         │                           └─────────────┬──────────┘
         │                                        │
┌────────▼────────────────────────────────────────▼──────────┐
│         REBALANCING ENGINE                                 │
│  ├─ Drift calculation                                      │
│  ├─ Trigger checking                                       │
│  ├─ Cost estimation                                        │
│  └─ Tax-loss harvesting ID                                │
└────────┬──────────────────────────────────────────────────┘
         │
┌────────▼──────────────────────────────────────────────────┐
│         ALERT ENGINE (Async Workers)                      │
│  ├─ Rule evaluation (red/yellow/info)                     │
│  ├─ Deduplication (24hr check)                            │
│  ├─ Formatting (title, body, action)                      │
│  └─ Routing (Slack/Email/Dashboard)                       │
└────────┬──────────────────────────────────────────────────┘
         │
    ┌────┴────┬────────────┬──────────────┐
    │          │            │              │
    ▼          ▼            ▼              ▼
┌─────────┐ ┌──────┐ ┌───────────┐ ┌───────────┐
│PostgreSQL│ │Slack │ │SendGrid   │ │Dashboard  │
│Database  │ │API   │ │(Email)    │ │WebSocket  │
└──────────┘ └──────┘ └───────────┘ └───────────┘
```

---

## API Flow Diagram

```
CLIENT REQUEST (React Dashboard)
       │
       ▼
┌──────────────────────┐
│  FastAPI Router      │
│  /api/portfolio/*    │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Business Logic      │
│  (portfolio_analyzer)│
└──────────────────────┘
       │
    ┌──┴──────────────────┐
    │                     │
    ▼                     ▼
┌─────────────┐     ┌────────────────┐
│PostgreSQL   │     │  Cassandra     │
│Historical   │     │  Real-time     │
│Data         │     │  Quotes        │
└─────────────┘     └────────────────┘
    │                     │
    └─────────┬───────────┘
              │
              ▼
        ┌──────────────┐
        │  Response    │
        │  JSON        │
        └──────────────┘
              │
              ▼
        ┌──────────────┐
        │  WebSocket   │
        │  Push        │
        └──────────────┘
              │
              ▼
        ┌──────────────┐
        │  Dashboard   │
        │  Update      │
        └──────────────┘
```

---

**WORKFLOWS DOCUMENTATION COMPLETE**  
**Ready for Implementation & Deployment**

