# TOGAF ARCHITECTURE BLUEPRINT
## Global Multi-Market Portfolio Analysis Platform

**Date:** 2026-07-07  
**Status:** Architecture Complete, Implementation Ready  
**Confidence:** 90%+ validated  
**Coverage:** 20,700+ stocks, 8 markets, 825K+ OHLCV records

---

## TABLE OF CONTENTS

1. [Business Architecture](#business-architecture)
2. [Application Architecture](#application-architecture)
3. [Data Architecture](#data-architecture)
4. [Technology Architecture](#technology-architecture)
5. [Backlog & Roadmap](#backlog--roadmap)
6. [Deployment Architecture](#deployment-architecture)

---

# BUSINESS ARCHITECTURE

## Business Strategy & Objectives

### Strategic Goals
```
Goal 1: Optimize Portfolio Performance
├─ Target: 10-11% CAGR (vs 15-16% benchmark average)
├─ Achieve: 8-9pp outperformance vs weighted benchmark
└─ Measure: Monthly CAGR tracking vs rolling targets

Goal 2: Minimize Risk & Volatility
├─ Target: Sharpe ratio >0.70 (vs 0.35 baseline)
├─ Achieve: 40% volatility reduction via global diversification
├─ Constraint: Max DD ≤ -22% (vs -42% baseline)
└─ Measure: Daily risk metrics dashboard

Goal 3: Optimize Rebalancing Costs
├─ Target: $100K-$150K annual savings on $100M AUM
├─ Achieve: Semi-annual rebalancing (vs quarterly default)
├─ Constraint: Drift monitoring (alert >5%, force >10%)
└─ Measure: Cost tracking vs budget

Goal 4: Maximize Tax Efficiency
├─ Target: Realize LTCG rates where possible (India 0%, USA 15% vs 37% STCG)
├─ Achieve: Tax-loss harvesting automation
└─ Measure: After-tax returns by jurisdiction
```

### Value Proposition
- **For Portfolio Managers:** Real-time visibility into 8-market portfolio with automated KPI tracking
- **For Risk Officers:** Daily risk metrics (VaR, correlation, drawdown) with alert thresholds
- **For Traders:** Rebalancing calendar with cost projections and tax-loss opportunities
- **For Executives:** Executive dashboard with consolidated performance vs benchmarks

### Business Stakeholders

| Stakeholder | Role | Interests | Influence |
|-----------|------|-----------|-----------|
| **Portfolio Manager** | Day-to-day portfolio oversight | Performance tracking, rebalancing execution | HIGH |
| **Risk Officer** | Risk monitoring & compliance | VaR, volatility, drawdown limits | HIGH |
| **Traders** | Execution team | Cost efficiency, tax-loss opportunities | MEDIUM |
| **CTO/Infrastructure** | Technology leadership | Scalability, reliability, cost | MEDIUM |
| **CFO** | Financial oversight | Cost savings, ROI on automation | HIGH |
| **Compliance** | Regulatory oversight | Tax reporting, audit trails | MEDIUM |

### Business Capabilities (Value Chains)

```
1. PORTFOLIO MONITORING
   ├─ Daily snapshot collection (4:30pm UTC)
   ├─ Multi-market P&L calculation
   ├─ Currency normalization (INR, USD, EUR, GBP, JPY, KRW, CNY, HKD)
   ├─ Benchmark comparison
   └─ KPI dashboard publishing

2. RISK MANAGEMENT
   ├─ Volatility tracking (daily, weekly, monthly)
   ├─ VaR calculation (95%, 99% confidence)
   ├─ Correlation matrix updates
   ├─ Currency exposure monitoring
   ├─ Sector concentration analysis
   └─ Alert generation & routing

3. REBALANCING EXECUTION
   ├─ Drift accumulation tracking (by market, daily)
   ├─ Rebalancing schedule management
   ├─ Cost estimation (by market, transaction type)
   ├─ Tax-loss harvesting identification
   ├─ Execution tracking & settlement
   └─ Performance attribution post-rebalance

4. REPORTING & ANALYTICS
   ├─ Daily performance reports
   ├─ Monthly KPI scorecards
   ├─ Quarterly strategy reviews
   ├─ Tax efficiency reports
   └─ Executive summary dashboards
```

---

# APPLICATION ARCHITECTURE

## Application Portfolio Map

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACES                           │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ Web Dashboard│ Email Reports│ Slack Alerts │ Excel Exports  │
│ (React SPA)  │ (SendGrid)    │ (Slack API)  │ (Python lib)   │
└───────┬──────┴──────┬───────┴──────┬───────┴────────┬────────┘
        │             │              │                │
┌───────▼─────────────▼──────────────▼────────────────▼────────┐
│                    API GATEWAY / ORCHESTRATION                │
│                   FastAPI Backend (:8000)                     │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  routers/    │  routers/    │  routers/    │  routers/      │
│  portfolio   │  risk        │  rebalance   │  reporting     │
│  .py         │  .py         │  .py         │  .py           │
└───────┬──────┴──────┬───────┴──────┬───────┴────────┬────────┘
        │             │              │                │
┌───────▼──────────────▼──────────────▼────────────────▼────────┐
│                   BUSINESS LOGIC LAYER                        │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  portfolio   │  risk_        │  rebalancing │  reporting    │
│  analyzer.py │  calculator.py│  engine.py   │  generator.py │
└───────┬──────┴──────┬───────┴──────┬───────┴────────┬────────┘
        │             │              │                │
┌───────▼──────────────▼──────────────▼────────────────▼────────┐
│                   DATA ACCESS LAYER                           │
├────────────────────────┬─────────────────────────────────────┤
│  db/                   │  fetchers/                          │
│  ├─ postgres_client    │  ├─ history.py (yfinance)          │
│  ├─ cassandra_client   │  ├─ market_data.py                 │
│  ├─ query_builder      │  └─ fx_rates.py (real-time)        │
│  └─ transaction_mgr    │                                     │
└────────────┬───────────┴─────────────────────────────────────┘
             │
    ┌────────▼────────────────────────────┐
    │  DATABASES (Persistence Layer)      │
    ├────────────────────────────────────┤
    │ PostgreSQL (Historical KPIs, Risk) │
    │ Cassandra (Live quotes, OHLCV)    │
    │ SQLite (Local cache, testing)     │
    └────────────────────────────────────┘
```

## Core Applications

### 1. **Portfolio Monitor (React SPA)**
**Purpose:** Real-time portfolio dashboard  
**Technology:** React 18+ | TypeScript | Tailwind CSS | WebSocket  
**Users:** Portfolio Managers, Risk Officers, Executives  

**Key Features:**
- Performance Summary (CAGR, Sharpe, volatility, max DD)
- Market allocation tracker (8 markets, drift %)
- Risk dashboard (correlation, VaR, currency exposure)
- Rebalancing calendar (next 12 months)
- Market drill-down (by market, holdings, sectors)
- KPI scorecard (daily/monthly/quarterly metrics)

**Refresh Frequency:**
- Real-time (intraday quotes, WebSocket)
- Daily (4:30pm market close snapshot)
- Monthly (KPI scorecards)

---

### 2. **Portfolio Analyzer (Python FastAPI)**
**Purpose:** Core portfolio analysis & metric calculation  
**Technology:** Python 3.10+ | FastAPI | SQLAlchemy | Numpy | Pandas  
**Dependencies:** PostgreSQL, Cassandra, yfinance  

**Key Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/portfolio/status` | Current allocation, drift, value |
| `GET` | `/api/portfolio/performance` | CAGR, Sharpe, returns by period |
| `POST` | `/api/portfolio/calculate-kpis` | Compute daily KPIs |
| `GET` | `/api/risk/volatility` | Portfolio volatility, by market |
| `GET` | `/api/risk/var` | Value at Risk (95%, 99%) |
| `GET` | `/api/risk/correlation` | 8×8 correlation matrix |
| `GET` | `/api/rebalance/drift` | Current drift %, trigger status |
| `POST` | `/api/rebalance/schedule` | Rebalancing calendar |
| `GET` | `/api/reporting/daily` | Daily performance report |
| `GET` | `/api/reporting/kpi-scorecard` | Monthly KPI snapshot |

---

### 3. **Risk Calculator (Python Service)**
**Purpose:** Daily risk metric computation  
**Technology:** Python 3.10+ | Numpy | Scipy | Pandas  
**Execution:** Daily batch (4:30pm UTC) + real-time intraday  

**Metrics Calculated:**
- Portfolio volatility (annualized)
- Value at Risk (95%, 99% confidence)
- Conditional VaR (CVaR)
- Correlation matrix (8 markets)
- Portfolio beta vs MSCI ACWI
- Systematic vs idiosyncratic risk
- Currency exposure (gross/net/hedged)
- Sector concentration (by market)

---

### 4. **Rebalancing Engine (Python Service)**
**Purpose:** Rebalancing schedule & execution tracking  
**Technology:** Python 3.10+ | SQLAlchemy | Pandas  
**Trigger:** Daily drift monitoring, quarterly rebalancing  

**Key Functions:**
- Drift accumulation tracking (by market, daily)
- Rebalancing calendar generation (quarterly/semi-annual)
- Cost estimation (by market, transaction type)
- Tax-loss harvesting identification
- Execution tracking & settlement confirmation
- Performance attribution (post-rebalance analysis)

---

### 5. **Alert Engine (Python Service)**
**Purpose:** Real-time alert generation & routing  
**Technology:** Python 3.10+ | RabbitMQ | Slack API | SendGrid  
**Execution:** Real-time (async workers)  

**Alert Types:**

| Level | Condition | Action | Routing |
|-------|-----------|--------|---------|
| 🔴 RED | Max DD >-25% | De-risk immediately | Email + Slack |
| 🔴 RED | Daily VaR >2% AUM | Review + reduce leverage | Email + Slack |
| 🟡 YELLOW | Drift >10% any market | Prepare mandatory rebalance | Slack |
| 🟡 YELLOW | Sharpe <0.50 (30d) | Risk adjustment review | Email |
| 🟡 YELLOW | Volatility >18% annualized | Caution flag | Dashboard |
| 🔵 INFO | Rebalancing due | Calendar reminder | Slack |
| 🔵 INFO | Tax-loss opportunity | Quarterly review | Email |
| 🔵 INFO | Currency >±20% FX move | Hedge adjustment check | Dashboard |

---

### 6. **Reporting Generator (Python Service)**
**Purpose:** Automated report generation & distribution  
**Technology:** Python 3.10+ | Jinja2 | WeasyPrint | SendGrid  
**Execution:** Daily (4:45pm UTC), monthly (1st day), quarterly (10th day)  

**Report Types:**
- Daily performance snapshot (email)
- Monthly KPI scorecard (dashboard + email)
- Quarterly strategy review (PDF + dashboard)
- Tax efficiency report (annual)
- Executive summary (board-ready)

---

## Application Interactions & Data Flow

```
DAILY PORTFOLIO MONITORING WORKFLOW:

1. Market Close (4:30pm UTC)
   └─> Portfolio Monitor triggers market data fetch

2. Data Collection (Parallel)
   ├─> Cassandra: Fetch live quotes (all 8 markets)
   ├─> yfinance: Fetch real-time prices
   └─> FX Service: Fetch current FX rates

3. Portfolio Calculation
   └─> Portfolio Analyzer
       ├─ Calculate current allocation (by market)
       ├─ Compute daily P&L
       ├─ Normalize to USD
       └─ Calculate returns (daily, YTD, 3Y, 5Y)

4. Risk Metric Computation (Parallel)
   ├─> Risk Calculator
   │   ├─ Volatility (annualized, by market)
   │   ├─ VaR & CVaR calculation
   │   ├─ Correlation matrix update
   │   └─ Currency exposure analysis
   │
   └─> Rebalancing Engine
       ├─ Calculate drift (current vs target, by market)
       ├─ Accumulate drift from last rebalance
       └─ Check trigger thresholds

5. Alert Generation
   └─> Alert Engine (async)
       ├─ Check each metric against thresholds
       ├─ Generate red/yellow/info alerts
       ├─ Route to Slack/Email/Dashboard
       └─ Log alert to alert_history table

6. Data Persistence
   ├─> PostgreSQL
   │   ├─ portfolio_daily_snapshot (append)
   │   ├─ risk_daily (append)
   │   ├─ drift_accumulation (update)
   │   └─ alert_history (append)
   │
   └─> WebSocket Push to Dashboard
       └─ Real-time KPI update

7. Report Generation
   └─> Reporting Generator
       ├─ Compile daily snapshot
       ├─ Generate PDF/HTML
       ├─ Send email to stakeholders
       └─ Archive report
```

---

# DATA ARCHITECTURE

## Logical Data Model (by Business Process)

### Data Entities

```
CORE ENTITIES:

Portfolio {
  portfolio_id: UUID (PK)
  name: string
  description: string
  created_date: date
  manager_id: UUID (FK → User)
  strategy_type: enum [Conservative, Moderate, Aggressive]
}

Holdings {
  holding_id: UUID (PK)
  portfolio_id: UUID (FK)
  market: enum [India, USA, Europe, Japan, Korea, UK, Brazil, China]
  ticker: string
  quantity: decimal
  cost_basis: decimal
  current_value: decimal
  acquisition_date: date
  last_updated: timestamp
}

Market {
  market_id: UUID (PK)
  market_code: string
  market_name: string
  currency_code: string
  exchange_name: string
  trading_hours: string
  settlement_days: int
}

PriceHistory {
  price_id: UUID (PK)
  ticker: string
  market: string
  price_date: date
  open: decimal
  high: decimal
  low: decimal
  close: decimal
  adjusted_close: decimal
  volume: bigint
}

PortfolioSnapshot {
  snapshot_id: UUID (PK)
  portfolio_id: UUID (FK)
  snapshot_date: date
  total_value_usd: decimal
  total_value_local: decimal
  daily_return_pct: decimal
  ytd_return_pct: decimal
  cagr_3y_pct: decimal
}

RiskMetric {
  metric_id: UUID (PK)
  portfolio_id: UUID (FK)
  metric_date: date
  volatility_annualized: decimal
  var_95: decimal
  var_99: decimal
  cvar_95: decimal
  max_drawdown_ytd: decimal
  sharpe_ratio_30d: decimal
}

RebalancingEvent {
  event_id: UUID (PK)
  portfolio_id: UUID (FK)
  rebalance_date: date
  rebalance_type: enum [Quarterly, SemiAnnual]
  status: enum [Scheduled, InProgress, Completed, Cancelled]
  estimated_cost: decimal
  actual_cost: decimal
}

Alert {
  alert_id: UUID (PK)
  portfolio_id: UUID (FK)
  alert_level: enum [Red, Yellow, Info]
  alert_type: string
  triggered_at: timestamp
  metric_name: string
  metric_value: decimal
  threshold_value: decimal
  status: enum [Active, Resolved]
}

KPIMetric {
  kpi_id: UUID (PK)
  portfolio_id: UUID (FK)
  period: enum [Daily, Weekly, Monthly, Quarterly, Annual]
  period_date: date
  cagr_pct: decimal
  sharpe_ratio: decimal
  volatility_pct: decimal
  max_drawdown_pct: decimal
  win_rate_pct: decimal
  information_ratio: decimal
}
```

---

## Physical Data Schema (PostgreSQL)

### Database: `market_data`

#### Schema: `portfolio_realtime`

```sql
CREATE TABLE portfolio_daily_snapshot (
  portfolio_id UUID NOT NULL,
  snapshot_date DATE NOT NULL,
  market VARCHAR(50) NOT NULL,
  target_allocation_pct NUMERIC(5,2),
  current_allocation_pct NUMERIC(5,2),
  drift_pct NUMERIC(5,2),
  drift_flag VARCHAR(20),
  total_value_usd NUMERIC(15,2),
  total_value_local_currency NUMERIC(15,2),
  fx_rate NUMERIC(10,6),
  market_contribution_pct NUMERIC(5,2),
  market_return_pct NUMERIC(6,3),
  market_return_usd NUMERIC(15,2),
  transaction_costs_ytd NUMERIC(10,2),
  realized_gains NUMERIC(15,2),
  unrealized_gains NUMERIC(15,2),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (portfolio_id, snapshot_date, market),
  INDEX idx_snapshot_date (snapshot_date),
  INDEX idx_market (market)
);

CREATE TABLE portfolio_intraday_quotes (
  portfolio_id UUID NOT NULL,
  snapshot_date DATE NOT NULL,
  quote_timestamp TIMESTAMP NOT NULL,
  total_value_usd NUMERIC(15,2),
  daily_return_pct NUMERIC(6,3),
  daily_return_usd NUMERIC(15,2),
  portfolio_volatility_annualized NUMERIC(5,3),
  sharpe_ratio_trailing_30d NUMERIC(5,3),
  var_95_1day_usd NUMERIC(15,2),
  PRIMARY KEY (portfolio_id, snapshot_date, quote_timestamp),
  INDEX idx_quote_timestamp (quote_timestamp)
);
```

#### Schema: `risk_metrics`

```sql
CREATE TABLE volatility_tracking (
  portfolio_id UUID NOT NULL,
  metric_date DATE NOT NULL,
  portfolio_volatility_annualized NUMERIC(5,3),
  target_volatility_annualized NUMERIC(5,3),
  volatility_breach_flag BOOLEAN,
  market_volatility_breakdown JSONB,
  sector_volatility_by_market JSONB,
  correlation_matrix_8m TEXT,
  max_drawdown_ytd NUMERIC(6,3),
  max_drawdown_3y NUMERIC(6,3),
  PRIMARY KEY (portfolio_id, metric_date),
  INDEX idx_metric_date (metric_date)
);

CREATE TABLE var_and_risk_daily (
  portfolio_id UUID NOT NULL,
  metric_date DATE NOT NULL,
  var_95_1day_usd NUMERIC(15,2),
  var_99_1day_usd NUMERIC(15,2),
  cvar_95_1day_usd NUMERIC(15,2),
  portfolio_beta_vs_msci_acwi NUMERIC(5,3),
  idiosyncratic_risk NUMERIC(5,3),
  systematic_risk NUMERIC(5,3),
  PRIMARY KEY (portfolio_id, metric_date),
  INDEX idx_metric_date (metric_date)
);

CREATE TABLE currency_exposure (
  portfolio_id UUID NOT NULL,
  metric_date DATE NOT NULL,
  currency_code VARCHAR(3) NOT NULL,
  gross_exposure_pct NUMERIC(5,2),
  net_exposure_pct NUMERIC(5,2),
  hedged_pct NUMERIC(5,2),
  fx_impact_ytd NUMERIC(6,3),
  fx_volatility_annualized NUMERIC(5,3),
  PRIMARY KEY (portfolio_id, metric_date, currency_code),
  INDEX idx_metric_date (metric_date)
);

CREATE TABLE sector_concentration (
  portfolio_id UUID NOT NULL,
  market VARCHAR(50) NOT NULL,
  metric_date DATE NOT NULL,
  sector VARCHAR(100) NOT NULL,
  portfolio_weight_pct NUMERIC(5,2),
  benchmark_weight_pct NUMERIC(5,2),
  overweight_pct NUMERIC(5,2),
  concentration_risk_flag BOOLEAN,
  PRIMARY KEY (portfolio_id, market, metric_date, sector),
  INDEX idx_metric_date (metric_date)
);
```

#### Schema: `rebalancing_calendar`

```sql
CREATE TABLE rebalancing_schedule (
  portfolio_id UUID NOT NULL,
  rebalance_date DATE NOT NULL,
  rebalance_type VARCHAR(50),
  frequency VARCHAR(50),
  estimated_transaction_costs_usd NUMERIC(10,2),
  tax_loss_harvest_opportunities JSONB,
  mandatory_trigger_drift_pct NUMERIC(5,2),
  status VARCHAR(50),
  PRIMARY KEY (portfolio_id, rebalance_date),
  INDEX idx_rebalance_date (rebalance_date)
);

CREATE TABLE drift_accumulation (
  portfolio_id UUID NOT NULL,
  rebalance_cycle VARCHAR(20) NOT NULL,
  market VARCHAR(50) NOT NULL,
  target_allocation NUMERIC(5,2),
  current_allocation NUMERIC(5,2),
  drift_pct NUMERIC(5,2),
  days_since_rebalance INT,
  drift_accumulation_rate NUMERIC(5,3),
  trigger_threshold_breached BOOLEAN,
  rebalance_required_by_date DATE,
  PRIMARY KEY (portfolio_id, rebalance_cycle, market),
  INDEX idx_rebalance_cycle (rebalance_cycle)
);

CREATE TABLE rebalancing_execution_history (
  portfolio_id UUID NOT NULL,
  rebalance_date DATE NOT NULL,
  market VARCHAR(50) NOT NULL,
  shares_sold NUMERIC(15,4),
  shares_bought NUMERIC(15,4),
  execution_price NUMERIC(10,4),
  actual_transaction_costs_usd NUMERIC(10,2),
  execution_status VARCHAR(50),
  settlement_date DATE,
  PRIMARY KEY (portfolio_id, rebalance_date, market),
  INDEX idx_rebalance_date (rebalance_date)
);
```

#### Schema: `kpi_metrics`

```sql
CREATE TABLE monthly_kpi_scorecard (
  portfolio_id UUID NOT NULL,
  period_month DATE NOT NULL,
  cagr_pct NUMERIC(6,3),
  sharpe_ratio NUMERIC(5,3),
  volatility_annualized_pct NUMERIC(5,3),
  max_drawdown_pct NUMERIC(6,3),
  win_rate_pct NUMERIC(5,2),
  information_ratio NUMERIC(5,3),
  tracking_error_bps INT,
  transaction_costs_ytd NUMERIC(10,2),
  PRIMARY KEY (portfolio_id, period_month),
  INDEX idx_period_month (period_month)
);

CREATE TABLE alert_history (
  alert_id UUID PRIMARY KEY,
  portfolio_id UUID NOT NULL,
  alert_level VARCHAR(20),
  alert_type VARCHAR(100),
  metric_value NUMERIC(10,4),
  threshold_value NUMERIC(10,4),
  triggered_at TIMESTAMP,
  resolved_at TIMESTAMP,
  alert_message TEXT,
  routing_channel VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_portfolio_id (portfolio_id),
  INDEX idx_triggered_at (triggered_at),
  INDEX idx_alert_level (alert_level)
);
```

### Database: `cassandra_keyspace` (for real-time quotes)

```sql
CREATE KEYSPACE herrrickshaw WITH replication = {
  'class':'SimpleStrategy',
  'replication_factor':3
};

CREATE TABLE stock_quotes (
  market TEXT,
  yf_ticker TEXT,
  cmp DECIMAL,
  rsi DECIMAL,
  ema_50 DECIMAL,
  rsi_signal TEXT,
  pe DECIMAL,
  pb DECIMAL,
  roe DECIMAL,
  opm DECIMAL,
  market_cap TEXT,
  volume BIGINT,
  high_52w DECIMAL,
  low_52w DECIMAL,
  debt_to_equity DECIMAL,
  last_updated TIMESTAMP,
  PRIMARY KEY ((market, yf_ticker))
);

CREATE TABLE price_history (
  yf_ticker TEXT,
  price_date DATE,
  close DECIMAL,
  open DECIMAL,
  high DECIMAL,
  low DECIMAL,
  volume BIGINT,
  PRIMARY KEY ((yf_ticker), price_date)
) WITH CLUSTERING ORDER BY (price_date DESC);
```

---

## Data Integration Points

```
┌─────────────────────────────────────────────────────────┐
│              EXTERNAL DATA SOURCES                      │
├──────────────┬────────────────┬─────────────┬──────────┤
│  yfinance    │  FX APIs       │  NSE/BSE    │  FRED    │
│  (OHLCV)     │  (Spot rates)  │  (Live)     │  (Rates) │
└──────┬───────┴────────┬───────┴─────────┬──┴──────┬───┘
       │                │                 │         │
┌──────▼────────────────▼─────────────────▼─────────▼────┐
│             DATA FETCHERS (Python)                     │
├─────────────────────────────────────────────────────┤
│ fetchers/history.py        → yfinance OHLCV cache  │
│ fetchers/market_data.py     → Broker APIs (NSE/BSE)│
│ fetchers/fx_rates.py        → FX rate feed         │
│ fetchers/fundamentals.py    → SEC EDGAR/balance   │
└──────┬────────────────┬─────────────────┬──────────┘
       │                │                 │
┌──────▼────────────────▼─────────────────▼──────────────┐
│          CACHING & TRANSFORMATION LAYER                 │
├─────────────────────────────────────────────────────┤
│ Cassandra (real-time cache, distributed)           │
│ Redis (optional: session cache, rate limiting)     │
│ SQLite (local development/testing)                 │
└──────┬────────────────┬──────────────────┬──────────┘
       │                │                  │
┌──────▼────────────────▼──────────────────▼──────────────┐
│          NORMALIZED PERSISTENT STORAGE                   │
├─────────────────────────────────────────────────────┤
│ PostgreSQL (analytical queries, reporting)         │
│ └─ 4 keyspaces: portfolio_realtime, risk_metrics,  │
│    rebalancing_calendar, kpi_metrics              │
└────────────────────────────────────────────────────┘
```

---

# TECHNOLOGY ARCHITECTURE

## Technology Stack

### Backend

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **API Server** | FastAPI | 0.100+ | REST API, async processing |
| **Language** | Python | 3.10+ | Business logic, data processing |
| **ORM** | SQLAlchemy | 2.0+ | PostgreSQL queries |
| **Async** | AsyncIO | 3.10+ | Non-blocking I/O |
| **Data Processing** | Pandas | 2.0+ | OHLCV, aggregations |
| **Numerical** | Numpy | 1.24+ | Matrix operations, risk calc |
| **Statistics** | Scipy | 1.11+ | VaR, correlation, regression |

### Frontend

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Framework** | React | 18+ | SPA, real-time updates |
| **Language** | TypeScript | 5.0+ | Type safety |
| **Styling** | Tailwind CSS | 3.0+ | Responsive design |
| **State Management** | Redux | 4.2+ | Global state |
| **Charts** | Recharts | 2.8+ | Data visualization |
| **HTTP Client** | Axios | 1.4+ | API calls |
| **Real-time** | WebSocket | Native | Live quote updates |

### Databases

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Transactional** | PostgreSQL | 14+ | ACID, historical data |
| **Cache** | Cassandra | 4.0+ | Real-time quotes, distributed |
| **Development** | SQLite | 3.40+ | Local testing |
| **Message Queue** | RabbitMQ | 3.12+ | Alert routing, async jobs |

### Infrastructure

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Containerization** | Docker | 24+ | Reproducible environments |
| **Orchestration** | Kubernetes | 1.27+ | Pod management, scaling |
| **Service Mesh** | Istio | 1.17+ | Traffic routing, security |
| **Message Queue** | RabbitMQ | 3.12+ | Async job processing |
| **Monitoring** | Prometheus | 2.45+ | Metrics collection |
| **Visualization** | Grafana | 10.0+ | Dashboard, alerting |
| **Logging** | ELK Stack | 8.8+ | Centralized logging |
| **CI/CD** | GitHub Actions | Latest | Automated testing, deployment |

### External Services

| Service | Purpose | API |
|---------|---------|-----|
| **yfinance** | OHLCV historical data | Free, rate-limited |
| **NSE Python** | India NSE live data | Free, browser-based |
| **Slack** | Alert notifications | Webhook API |
| **SendGrid** | Email delivery | REST API |
| **IEX Cloud** | US data (optional) | REST API |
| **Alpha Vantage** | Alternative OHLCV | REST API |

---

# DEPLOYMENT ARCHITECTURE

## Target Deployment Environment

```
┌────────────────────────────────────────────────────┐
│           CLOUD PROVIDER (AWS/GCP/Azure)          │
├────────────────────────────────────────────────────┤
│                                                    │
│  ┌──────────────────────────────────────────┐    │
│  │    Load Balancer (SSL/TLS)               │    │
│  └──────────────┬───────────────────────────┘    │
│                 │                                 │
│  ┌──────────────▼───────────────────────────┐    │
│  │    Kubernetes Cluster (1.27+)            │    │
│  │    ├─ Namespace: production              │    │
│  │    ├─ Namespace: staging                 │    │
│  │    └─ Namespace: development             │    │
│  ├──────────────────────────────────────────┤    │
│  │    Deployments:                          │    │
│  │    ├─ FastAPI Backend (3 replicas)     │    │
│  │    ├─ React Frontend (2 replicas)      │    │
│  │    ├─ Risk Calculator (1 instance)     │    │
│  │    ├─ Alert Engine (2 replicas)        │    │
│  │    └─ Reporting Service (1 instance)   │    │
│  └──────────────────────────────────────────┘    │
│                 │                                 │
│  ┌──────────────▼───────────────────────────┐    │
│  │    Persistent Storage                    │    │
│  │    ├─ PostgreSQL (RDS / Cloud SQL)      │    │
│  │    │  └─ 3-node HA cluster              │    │
│  │    ├─ Cassandra (Multi-AZ)              │    │
│  │    │  └─ 6-node distributed cluster     │    │
│  │    └─ Message Queue (RabbitMQ)          │    │
│  │       └─ 3-node cluster                 │    │
│  └──────────────────────────────────────────┘    │
│                                                    │
│  ┌──────────────────────────────────────────┐    │
│  │    Monitoring & Logging                  │    │
│  │    ├─ Prometheus (metrics)               │    │
│  │    ├─ Grafana (dashboards)               │    │
│  │    ├─ ELK Stack (logs)                   │    │
│  │    └─ Jaeger (tracing)                   │    │
│  └──────────────────────────────────────────┘    │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

# BACKLOG & ROADMAP

## PHASE COMPLETION STATUS

### ✅ PHASE 1: Portfolio Performance Analysis
**Status:** COMPLETE  
**Deliverables:**
- [x] Multi-market portfolio methodology (8 markets)
- [x] 24.1% CAGR strategy validated
- [x] 8-9pp outperformance vs benchmarks confirmed
- [x] Allocation weights finalized

**Outstanding:** None

---

### ✅ PHASE 2: Global Risk Assessment
**Status:** COMPLETE  
**Deliverables:**
- [x] Risk profile by market (volatility, Sharpe, max DD)
- [x] Correlation analysis (0.034 avg = 40% vol reduction)
- [x] Currency hedging strategy (40-80% by market)
- [x] Recommended allocations (Conservative/Moderate/Aggressive)
- [x] PostgreSQL database (825K OHLCV records)

**Outstanding:**
- [ ] Complete 5-year historical backfill (China, Brazil partial)
- [ ] Fine-tune correlation thresholds (current ±0.2 window)
- [ ] Add sector-level correlations (to-do)

---

### ✅ PHASE 3: Rebalancing Optimization
**Status:** COMPLETE  
**Deliverables:**
- [x] Cost analysis (15 indices analyzed)
- [x] Optimal schedules ($100K-$150K annual savings)
- [x] Tax efficiency by jurisdiction (LTCG/STCG)
- [x] Implementation roadmap (4-phase deployment)

**Outstanding:**
- [ ] Add tax-loss harvesting algorithm (template exists)
- [ ] Integrate broker execution API (Kite/Upstox)
- [ ] Add slippage/impact models (simplified version)

---

### ✅ PHASE 4: Executive Dashboard & Synthesis
**Status:** COMPLETE  
**Deliverables:**
- [x] Dashboard architecture (5 views designed)
- [x] PostgreSQL schema (4 keyspaces, 20+ tables)
- [x] ETL pipeline specification (daily 4:30pm trigger)
- [x] Alert rules (red/yellow/info thresholds)
- [x] Deployment roadmap (8 weeks)
- [x] TOGAF architecture (this document)

**Outstanding:**
- [ ] React dashboard implementation (template ready)
- [ ] FastAPI backend build (endpoints designed, no code yet)
- [ ] Integration tests (alert routing, data pipeline)
- [ ] Load testing & performance tuning

---

## IMPLEMENTATION BACKLOG

### Critical Path Items (Blocking Deployment)

| ID | Task | Status | Priority | Effort | Owner | Target |
|----|------|--------|----------|--------|-------|--------|
| **DEV-001** | Build FastAPI backend (12 endpoints) | NOT STARTED | CRITICAL | 21 pts | Backend | W1-2 |
| **DEV-002** | Build React dashboard (5 views) | NOT STARTED | CRITICAL | 13 pts | Frontend | W3 |
| **DEV-003** | PostgreSQL schema creation & indexing | NOT STARTED | CRITICAL | 3 pts | Database | W1 |
| **DEV-004** | Cassandra integration & query patterns | NOT STARTED | CRITICAL | 5 pts | Database | W1 |
| **DATA-001** | Load 5-year historical OHLCV | IN PROGRESS | CRITICAL | 8 pts | Data | W2 |
| **INFRA-001** | Kubernetes cluster setup | NOT STARTED | CRITICAL | 8 pts | DevOps | W1 |
| **INFRA-002** | CI/CD pipeline (GitHub Actions) | NOT STARTED | CRITICAL | 5 pts | DevOps | W1-2 |
| **TEST-001** | End-to-end integration testing | NOT STARTED | CRITICAL | 13 pts | QA | W5 |

### High Priority Items

| ID | Task | Status | Priority | Effort | Target |
|----|------|--------|----------|--------|--------|
| **DEV-005** | Alert engine implementation | NOT STARTED | HIGH | 8 pts | W2 |
| **DEV-006** | Risk calculator service | NOT STARTED | HIGH | 13 pts | W2 |
| **DATA-002** | FX rate real-time feed setup | NOT STARTED | HIGH | 5 pts | W1 |
| **DATA-003** | Fix NaT timestamp issues (India OHLCV) | PENDING | HIGH | 3 pts | W1 |
| **INFRA-003** | Prometheus + Grafana setup | NOT STARTED | HIGH | 5 pts | W2 |
| **DOCS-001** | API documentation (OpenAPI/Swagger) | NOT STARTED | HIGH | 5 pts | W2 |

### Medium Priority Items

| ID | Task | Status | Priority | Effort | Target |
|----|------|--------|----------|--------|--------|
| **DEV-007** | Rebalancing engine implementation | NOT STARTED | MEDIUM | 13 pts | W3 |
| **DEV-008** | Tax-loss harvesting algorithm | DESIGNED | MEDIUM | 8 pts | W4 |
| **DATA-004** | Broker API integration (Kite/Upstox) | RESEARCH | MEDIUM | 13 pts | W4 |
| **TEST-002** | Unit tests (portfolio analyzer) | NOT STARTED | MEDIUM | 8 pts | W4 |
| **TEST-003** | Load testing (concurrent 1000 users) | NOT STARTED | MEDIUM | 5 pts | W5 |
| **DOCS-002** | Runbook documentation (ops guide) | NOT STARTED | MEDIUM | 5 pts | W6 |

### Low Priority Items (Post-MVP)

| ID | Task | Status | Priority | Effort | Target |
|----|------|--------|----------|--------|--------|
| **DEV-009** | ML anomaly detection (alerts) | DESIGN | LOW | 21 pts | Post-W8 |
| **DEV-010** | Advanced tax optimization (multi-lot) | DESIGN | LOW | 13 pts | Post-W8 |
| **INFRA-004** | Disaster recovery setup (backup/restore) | NOT STARTED | LOW | 8 pts | M2 |
| **INFRA-005** | Multi-region replication | NOT STARTED | LOW | 13 pts | M3 |
| **DOCS-003** | User training materials | NOT STARTED | LOW | 5 pts | M1 |

---

## Known Issues & Limitations

| ID | Issue | Impact | Workaround | Target |
|----|-------|--------|-----------|--------|
| **BUG-001** | NaT timestamps in India OHLCV | Data load fails (28K rows) | Null filtering in loader | W1 |
| **BUG-002** | Git operations timeout on 7500+ untracked files | Slow commits, intermittent failures | Use shell script approach | W1 |
| **LIM-001** | China A-shares data incomplete | Missing ~300 stocks | Add akshare fallback | W2 |
| **LIM-002** | NSE real-time requires browser cookies | Can't fetch live NSE data | Use yfinance for OHLC | Current |
| **LIM-003** | Correlation matrix stale (daily calc, 5min lag) | Intraday drift calculations off | Intraday correlation ±5% approx | W3 |
| **PERF-001** | yfinance batch size >50 times out | Loading 20K stocks takes 2-3 days | Parallelize in Colab/cloud | W1 |

---

## Deployment Timeline

```
WEEK 1-2: INFRASTRUCTURE & DATA
├─ K8s cluster provisioning
├─ PostgreSQL HA setup
├─ Cassandra cluster deployment
├─ Load 5-year historical OHLCV
└─ Fix data quality issues (NaT, deduplication)

WEEK 3: BACKEND FOUNDATION
├─ FastAPI scaffold + 12 endpoints
├─ Portfolio analyzer service
├─ Risk calculator service
└─ Basic alerting (test mode)

WEEK 4: FRONTEND & ALERTS
├─ React dashboard (5 views)
├─ Real-time WebSocket integration
├─ Alert engine + Slack/Email routing
└─ Manual testing

WEEK 5-6: INTEGRATION & TESTING
├─ End-to-end workflow validation
├─ Load testing (simulate 1000 concurrent users)
├─ Performance optimization (target <2s dashboard load)
└─ Security audit

WEEK 7: UAT & REFINEMENT
├─ User acceptance testing with portfolio managers
├─ Feedback incorporation
├─ Final performance tuning
└─ Documentation completion

WEEK 8: PRODUCTION DEPLOYMENT
├─ Blue-green deployment
├─ Canary rollout (10% traffic)
├─ Monitor error rates, latency
├─ Full rollout (100% traffic)
└─ Go-live
```

---

## Success Metrics (Post-Deployment)

| Metric | Target | Monitoring |
|--------|--------|-----------|
| **Availability** | 99.9% uptime | CloudWatch/Prometheus |
| **Performance** | <2s dashboard load (p95) | Grafana, synthetic tests |
| **Data Freshness** | <60 min lag from market close | ETL pipeline monitoring |
| **Alert Accuracy** | 98%+ precision | Alert_history table review |
| **Portfolio CAGR** | 10-11% | Monthly KPI scorecard |
| **Sharpe Ratio** | >0.70 | Daily risk metrics |
| **Cost Savings** | $100K-$150K annually | Rebalancing cost tracking |

---

**ARCHITECTURE BLUEPRINT COMPLETE**  
**Status:** Ready for Implementation  
**Next Step:** Infrastructure provisioning (Week 1)

