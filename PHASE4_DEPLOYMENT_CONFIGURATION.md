# PHASE 4 DEPLOYMENT CONFIGURATION

**Status:** Ready for Implementation  
**Target:** 8-week deployment cycle  
**Environment:** PostgreSQL + React + FastAPI  

---

## DATABASE SCHEMA (PostgreSQL)

### Keyspace 1: Portfolio Realtime

#### Table: portfolio_daily_snapshot
```sql
CREATE TABLE portfolio_daily_snapshot (
  portfolio_id UUID,
  date DATE,
  market VARCHAR(50),
  target_allocation_pct DECIMAL(5,2),
  current_allocation_pct DECIMAL(5,2),
  drift_pct DECIMAL(5,2),
  drift_flag VARCHAR(20),
  total_value_usd DECIMAL(15,2),
  total_value_local_currency DECIMAL(15,2),
  fx_rate DECIMAL(10,6),
  market_contribution_pct DECIMAL(5,2),
  market_return_pct DECIMAL(6,3),
  market_return_usd DECIMAL(15,2),
  transaction_costs_ytd DECIMAL(10,2),
  realized_gains DECIMAL(15,2),
  unrealized_gains DECIMAL(15,2),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (portfolio_id, date, market)
);

CREATE INDEX idx_portfolio_daily_date ON portfolio_daily_snapshot(date);
CREATE INDEX idx_portfolio_daily_market ON portfolio_daily_snapshot(market);
```

#### Table: portfolio_intraday_quotes
```sql
CREATE TABLE portfolio_intraday_quotes (
  portfolio_id UUID,
  date DATE,
  timestamp TIMESTAMP,
  total_value_usd DECIMAL(15,2),
  daily_return_pct DECIMAL(6,3),
  daily_return_usd DECIMAL(15,2),
  portfolio_volatility_annualized DECIMAL(5,3),
  sharpe_ratio_trailing_30d DECIMAL(5,3),
  var_95_1day_usd DECIMAL(15,2),
  PRIMARY KEY (portfolio_id, date, timestamp)
);

CREATE INDEX idx_portfolio_intraday_timestamp ON portfolio_intraday_quotes(timestamp);
```

### Keyspace 2: Risk Metrics

#### Table: volatility_tracking
```sql
CREATE TABLE volatility_tracking (
  portfolio_id UUID,
  date DATE,
  portfolio_volatility_annualized DECIMAL(5,3),
  target_volatility_annualized DECIMAL(5,3),
  volatility_breach_flag BOOLEAN,
  market_volatility_breakdown JSONB,
  sector_volatility_by_market JSONB,
  correlation_matrix_8m TEXT,
  max_drawdown_ytd DECIMAL(6,3),
  max_drawdown_3y DECIMAL(6,3),
  PRIMARY KEY (portfolio_id, date)
);
```

#### Table: var_and_risk_daily
```sql
CREATE TABLE var_and_risk_daily (
  portfolio_id UUID,
  date DATE,
  var_95_1day_usd DECIMAL(15,2),
  var_99_1day_usd DECIMAL(15,2),
  cvar_95_1day_usd DECIMAL(15,2),
  portfolio_beta_vs_msci_acwi DECIMAL(5,3),
  idiosyncratic_risk DECIMAL(5,3),
  systematic_risk DECIMAL(5,3),
  PRIMARY KEY (portfolio_id, date)
);
```

#### Table: currency_exposure
```sql
CREATE TABLE currency_exposure (
  portfolio_id UUID,
  date DATE,
  currency_code VARCHAR(3),
  gross_exposure_pct DECIMAL(5,2),
  net_exposure_pct DECIMAL(5,2),
  hedged_pct DECIMAL(5,2),
  fx_impact_ytd DECIMAL(6,3),
  fx_volatility_annualized DECIMAL(5,3),
  PRIMARY KEY (portfolio_id, date, currency_code)
);
```

#### Table: sector_concentration
```sql
CREATE TABLE sector_concentration (
  portfolio_id UUID,
  market VARCHAR(50),
  date DATE,
  sector VARCHAR(100),
  portfolio_weight_pct DECIMAL(5,2),
  benchmark_weight_pct DECIMAL(5,2),
  overweight_pct DECIMAL(5,2),
  concentration_risk_flag BOOLEAN,
  PRIMARY KEY (portfolio_id, market, date, sector)
);
```

### Keyspace 3: Rebalancing Calendar

#### Table: rebalancing_schedule
```sql
CREATE TABLE rebalancing_schedule (
  portfolio_id UUID,
  rebalance_date DATE,
  rebalance_type VARCHAR(50),
  frequency VARCHAR(50),
  estimated_transaction_costs_usd DECIMAL(10,2),
  tax_loss_harvest_opportunities JSONB,
  mandatory_trigger_drift_pct DECIMAL(5,2),
  status VARCHAR(50),
  PRIMARY KEY (portfolio_id, rebalance_date)
);
```

#### Table: drift_accumulation
```sql
CREATE TABLE drift_accumulation (
  portfolio_id UUID,
  rebalance_cycle VARCHAR(20),
  market VARCHAR(50),
  target_allocation DECIMAL(5,2),
  current_allocation DECIMAL(5,2),
  drift_pct DECIMAL(5,2),
  days_since_rebalance INT,
  drift_accumulation_rate DECIMAL(5,3),
  trigger_threshold_breached BOOLEAN,
  rebalance_required_by_date DATE,
  PRIMARY KEY (portfolio_id, rebalance_cycle, market)
);
```

#### Table: rebalancing_execution_history
```sql
CREATE TABLE rebalancing_execution_history (
  portfolio_id UUID,
  rebalance_date DATE,
  market VARCHAR(50),
  shares_sold DECIMAL(15,4),
  shares_bought DECIMAL(15,4),
  execution_price DECIMAL(10,4),
  actual_transaction_costs_usd DECIMAL(10,2),
  execution_status VARCHAR(50),
  settlement_date DATE,
  PRIMARY KEY (portfolio_id, rebalance_date, market)
);
```

### Keyspace 4: KPI Metrics

#### Table: monthly_kpi_scorecard
```sql
CREATE TABLE monthly_kpi_scorecard (
  portfolio_id UUID,
  month DATE,
  cagr_pct DECIMAL(6,3),
  sharpe_ratio DECIMAL(5,3),
  volatility_annualized_pct DECIMAL(5,3),
  max_drawdown_pct DECIMAL(6,3),
  win_rate_pct DECIMAL(5,2),
  information_ratio DECIMAL(5,3),
  tracking_error_bps INT,
  transaction_costs_ytd DECIMAL(10,2),
  PRIMARY KEY (portfolio_id, month)
);
```

#### Table: alert_history
```sql
CREATE TABLE alert_history (
  alert_id UUID PRIMARY KEY,
  portfolio_id UUID,
  alert_level VARCHAR(20),
  alert_type VARCHAR(100),
  metric_value DECIMAL(10,4),
  threshold_value DECIMAL(10,4),
  triggered_at TIMESTAMP,
  resolved_at TIMESTAMP,
  alert_message TEXT,
  routing_channel VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_portfolio ON alert_history(portfolio_id);
CREATE INDEX idx_alert_triggered ON alert_history(triggered_at);
CREATE INDEX idx_alert_level ON alert_history(alert_level);
```

---

## ETL PIPELINE SPECIFICATION

### Daily Batch Job (4:30pm UTC)

```python
# Schedule: Daily at 16:30 UTC (market close)
# Duration: ~30 seconds
# Frequency: Every trading day

class DailyPortfolioSnapshotETL:
    def run(self):
        # 1. Fetch current portfolio state from broker API
        portfolio_state = self.fetch_portfolio_state()
        
        # 2. Fetch current market quotes (Cassandra)
        market_quotes = self.fetch_market_quotes()
        
        # 3. Calculate portfolio metrics
        daily_metrics = self.calculate_metrics(portfolio_state, market_quotes)
        
        # 4. Insert into portfolio_daily_snapshot
        self.insert_daily_snapshot(daily_metrics)
        
        # 5. Calculate KPIs (daily, YTD, 30-day, 3-year)
        kpis = self.calculate_kpis()
        
        # 6. Check alert thresholds
        alerts = self.check_alerts(daily_metrics, kpis)
        
        # 7. Route alerts (Slack/Email)
        self.route_alerts(alerts)
        
        # 8. Generate daily report
        self.generate_daily_report(daily_metrics, kpis, alerts)
        
        return {'status': 'success', 'timestamp': NOW()}
```

### Real-Time Quote Updates (Trading Hours)

```python
# WebSocket connection to market data feed
# Updates intraday portfolio value every minute

class IntraDayQuoteUpdater:
    def on_market_update(self, market, ticker, new_price):
        # 1. Update position value for (market, ticker)
        # 2. Recalculate portfolio total value
        # 3. Calculate daily return %
        # 4. Update portfolio_intraday_quotes table
        # 5. Broadcast to dashboard via WebSocket
        
        self.update_intraday_value()
```

---

## ALERT RULES CONFIGURATION

### Alert Thresholds (YAML)

```yaml
alerts:
  - id: max_drawdown_breach
    level: RED
    metric: max_drawdown_ytd
    condition: value < -25
    message: "Portfolio drawdown exceeded -25%"
    action: de_risk_immediately
    routing: [email, slack]
    
  - id: var_breach
    level: RED
    metric: var_95_1day_usd
    condition: value > portfolio_aum * 0.02
    message: "Daily VaR exceeds 2% of portfolio"
    action: reduce_leverage
    routing: [email, slack]
    
  - id: drift_alert
    level: YELLOW
    metric: drift_pct
    condition: value > 10
    message: "Market drift exceeds 10% - mandatory rebalance"
    action: trigger_rebalancing
    routing: [slack]
    
  - id: sharpe_decline
    level: YELLOW
    metric: sharpe_ratio_trailing_30d
    condition: value < 0.50
    message: "Sharpe ratio below target (<0.50)"
    action: risk_review
    routing: [email]
    
  - id: volatility_caution
    level: YELLOW
    metric: portfolio_volatility_annualized
    condition: value > 18
    message: "Volatility exceeding 18% annualized"
    action: monitor
    routing: [dashboard]
    
  - id: rebalancing_due
    level: INFO
    metric: rebalancing_schedule
    condition: days_until <= 7
    message: "Rebalancing scheduled for {date}"
    action: calendar_reminder
    routing: [slack]
    
  - id: tax_loss_opportunity
    level: INFO
    metric: unrealized_gains
    condition: value < -10000
    message: "Tax-loss harvesting opportunity identified"
    action: quarterly_review
    routing: [email]
```

---

## FRONTEND DASHBOARD SPECIFICATION

### View 1: Performance Summary
**Components:**
- Portfolio value (current, daily change, YTD CAGR)
- Allocation pie chart (8 markets)
- Performance line chart (1Y, 3Y, 5Y)
- Top/bottom market contributors (bar chart)

**Refresh Frequency:** Real-time (WebSocket updates)

### View 2: Risk Dashboard
**Components:**
- Volatility gauge (current vs 15% target)
- VaR display (95% confidence, 1-day loss)
- Correlation matrix heatmap (8×8 markets)
- Currency exposure breakdown
- Sector concentration alert

**Refresh Frequency:** Daily (4:30pm UTC)

### View 3: Rebalancing Calendar
**Components:**
- Quarterly/semi-annual schedule (next 12 months)
- Drift accumulation by market (current %)
- Estimated transaction costs
- Tax-loss harvest opportunities
- Historical rebalancing execution

**Refresh Frequency:** Daily (drift), quarterly (schedule updates)

### View 4: Market Drill-Down
**Components:**
- Market selector (dropdown)
- Holdings list (symbol, weight, return %, 52-week performance)
- Sector breakdown
- Performance vs benchmark
- Currency impact

**Refresh Frequency:** Daily (market close)

### View 5: KPI Scorecard
**Components:**
- CAGR % vs target (gauge)
- Sharpe ratio vs target
- Volatility vs 15% target
- Max DD vs -22% target
- Win rate % (positive days)
- Information ratio
- Tracking error (bps)

**Refresh Frequency:** Monthly (official calculation)

---

## DEPLOYMENT INFRASTRUCTURE

### Technology Stack
- **Backend:** Python 3.10+, FastAPI, SQLAlchemy
- **Database:** PostgreSQL 14+, Cassandra 4.0+
- **Frontend:** React 18+, TypeScript, Tailwind CSS
- **Real-time:** WebSocket, Server-Sent Events
- **Message Queue:** RabbitMQ (for async alerts)
- **Notifications:** Slack API, SendGrid (email)
- **Hosting:** Docker, Kubernetes (k8s)
- **Monitoring:** Prometheus, Grafana

### Infrastructure Architecture
```
                    ┌─────────────────┐
                    │   React SPA     │
                    │ (Dashboard 5x)  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  WebSocket API  │
                    │  (Real-time)    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼────┐      ┌───────▼───────┐     ┌──────▼──────┐
   │PostgreSQL│     │  Cassandra    │     │ RabbitMQ    │
   │(Daily    │     │  (Live quotes)│     │ (Alerts)    │
   │KPIs)     │     │               │     │             │
   └──────────┘     └───────────────┘     └──────┬──────┘
                                                  │
                                    ┌─────────────┴──────────┐
                                    │                        │
                              ┌─────▼──────┐         ┌──────▼────┐
                              │ Slack API  │         │SendGrid    │
                              │(Alerts)    │         │(Email)     │
                              └────────────┘         └────────────┘

ETL Pipeline: Daily 4:30pm UTC trigger
  → Fetch portfolio state
  → Calculate metrics
  → Insert into PostgreSQL
  → Check alerts
  → Route notifications
  → Update dashboard (WebSocket push)
```

---

## DEPLOYMENT CHECKLIST (8 Weeks)

### Week 1-2: Infrastructure
- [ ] PostgreSQL cluster setup (HA, backup)
- [ ] Database schema creation (4 keyspaces)
- [ ] Cassandra integration testing
- [ ] Docker images for backend & frontend
- [ ] GitHub Actions CI/CD pipeline
- [ ] Staging environment ready

### Week 3: Frontend
- [ ] React project scaffold
- [ ] 5 main views implemented
- [ ] WebSocket connection established
- [ ] Responsive design (mobile/tablet/desktop)
- [ ] Dark/light theme toggle

### Week 4: Alerts
- [ ] Alert engine implementation
- [ ] Slack integration with OAuth
- [ ] Email templates (SendGrid)
- [ ] Alert history persistence
- [ ] Alert rule configuration

### Week 5-6: Historical Data
- [ ] 5-year OHLCV data loaded
- [ ] Historical KPI calculation
- [ ] Backtest portfolio strategy
- [ ] Accuracy validation (manual spot checks)
- [ ] Performance optimization

### Week 7: UAT
- [ ] User acceptance testing
- [ ] Dashboard accuracy verified
- [ ] Query performance <2s (p95)
- [ ] Stress testing (high-volume)
- [ ] Feedback incorporation

### Week 8: Production
- [ ] Blue-green deployment
- [ ] Canary rollout (10% traffic)
- [ ] Monitor error rates & latency
- [ ] Full rollout (100% traffic)
- [ ] Runbook documentation

---

## MONITORING & OBSERVABILITY

### Metrics (Prometheus)
- `dashboard_page_load_time_ms` (p50, p95, p99)
- `database_query_duration_ms` (by query)
- `alert_processing_latency_ms`
- `websocket_connection_count`
- `portfolio_daily_snapshot_insert_rate`
- `etl_pipeline_duration_seconds`

### Logs (ELK Stack)
- Application logs: DEBUG, INFO, WARN, ERROR
- Database logs: Slow queries, connection issues
- Alert logs: All fired alerts with context
- User action logs: Dashboard navigation, exports

### Dashboards (Grafana)
- **System Health:** CPU, memory, disk, network
- **Database Performance:** Query latency, connection pool
- **Application Metrics:** Request rates, error rates, latencies
- **Portfolio KPIs:** CAGR, Sharpe, volatility, max DD (live)
- **Alert Metrics:** Alert rate, routing success, response time

---

## OPERATIONAL RUNBOOKS

### Runbook 1: Daily ETL Failure
```
1. Check if market data feed is available
   → curl https://api.data-provider.com/health
2. Check database connection
   → SELECT 1 FROM portfolio_daily_snapshot LIMIT 1
3. Check alert queue (RabbitMQ)
   → rabbitmqctl list_queues
4. Review logs for specific error
   → tail -100 /var/log/etl_pipeline.log
5. If data source issue: Manual retry after source recovery
6. If database issue: Failover to replica
7. If persistent: Page on-call engineer
```

### Runbook 2: Red Alert Triggered
```
1. Receive alert (Slack/Email)
2. Log into dashboard & verify reading
3. Check market conditions (news, volatility)
4. Contact portfolio manager
5. Execute de-risk action if confirmed
6. Document in alert_history with resolution
7. Investigate root cause post-market
```

### Runbook 3: Dashboard Slowness
```
1. Check database query times
   → SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC
2. Check WebSocket connection count
   → wc -l /proc/*/net/tcp | tail -1
3. Check application logs for memory/CPU issues
4. Scale up database connection pool if needed
5. Clear any stuck queries (manually or via timeout)
6. Monitor until performance recovers
```

---

## SUCCESS CRITERIA

✅ Database operational with 5-year historical data loaded  
✅ Dashboard loads in <2s (p95)  
✅ All 15 KPIs calculating correctly  
✅ Red/yellow alerts fire accurately (98%+ precision)  
✅ Portfolio managers sign off on accuracy  
✅ Rebalancing cost tracking matches actual  
✅ Drift monitoring alerts at correct thresholds  
✅ Monthly KPI scorecard generates automatically  

---

## RISK MITIGATION

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Data quality issues | High | Comprehensive validation tests, manual spot checks |
| Dashboard performance | High | Query optimization, caching strategy, load testing |
| Alert false positives | Medium | Conservative thresholds, multi-condition rules |
| Integration failures | High | API redundancy, fallback mechanisms, circuit breakers |
| Security vulnerabilities | Critical | Pen testing, code review, HTTPS/TLS only |

---

## BUDGET ESTIMATE

- **Development:** $45K (3 engineers × 8 weeks × $150/hr)
- **Infrastructure:** $8K (PostgreSQL, Cassandra, k8s hosting)
- **Tools & Services:** $2K (Slack API, SendGrid, monitoring)
- **Testing & QA:** $4K (UAT, load testing tools)
- **Contingency (10%):** $5.9K

**Total:** $64.9K

---

**Ready for Greenlight** ✅
