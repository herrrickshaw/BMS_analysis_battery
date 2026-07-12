# PostgreSQL Market Data Setup

## Prerequisites

### 1. Install PostgreSQL
```bash
# macOS (via Homebrew)
brew install postgresql@15

# Start PostgreSQL
brew services start postgresql@15

# Verify installation
psql --version
```

### 2. Install Python Dependencies
```bash
pip install psycopg2-binary pandas
```

## Quick Start

### Load All Data
```bash
python /Users/umashankar/load_market_data_to_postgres.py
```

This will:
✅ Create `market_data` database (if not exists)
✅ Create normalized schema (markets, stocks, ohlcv_history, fundamentals)
✅ Discover all CSV files in `/Users/umashankar/data/`
✅ Load data by market (India, USA, UK, Germany, Europe, Japan, Korea, China)
✅ Create performance indexes
✅ Show summary statistics

## Database Schema

```
markets (8 records)
├── market_id (PK)
├── market_name (unique)
├── exchange, country, currency, timezone
└── trading_hours

stocks (20,700+ records)
├── stock_id (PK)
├── ticker, name, market_id (FK)
├── sector, industry, market_cap_usd
└── UNIQUE(ticker, market_id)

ohlcv_history (millions of records)
├── ohlcv_id (PK)
├── stock_id (FK), date
├── open_price, high_price, low_price, close_price
├── volume, adj_close
└── UNIQUE(stock_id, date)

fundamentals (stock snapshots)
├── fundamental_id (PK)
├── stock_id (FK, unique)
├── pe_ratio, pb_ratio, roe, roa, debt_to_equity
├── dividend_yield, eps, revenue, net_income
└── operating_margin, profit_margin
```

## Useful Queries

### Connect to Database
```bash
psql -d market_data
```

### View Markets
```sql
SELECT * FROM markets ORDER BY market_name;
```

### Stocks by Market
```sql
SELECT m.market_name, COUNT(*) as stock_count
FROM stocks s
JOIN markets m ON s.market_id = m.market_id
GROUP BY m.market_name
ORDER BY stock_count DESC;
```

### Top Stocks by Market Cap
```sql
SELECT ticker, name, sector, market_cap_usd
FROM stocks
WHERE market_cap_usd IS NOT NULL
ORDER BY market_cap_usd DESC
LIMIT 20;
```

### OHLCV Data (Latest Close for a Stock)
```sql
SELECT s.ticker, s.name, h.date, h.close_price, h.volume
FROM ohlcv_history h
JOIN stocks s ON h.stock_id = s.stock_id
WHERE s.ticker = 'RELIANCE'
ORDER BY h.date DESC
LIMIT 30;
```

### Best Quality Stocks (by Fundamentals)
```sql
SELECT s.ticker, s.name, s.sector, 
       f.pe_ratio, f.roe, f.dividend_yield, f.debt_to_equity
FROM stocks s
JOIN fundamentals f ON s.stock_id = f.stock_id
WHERE f.roe > 0.15 AND f.debt_to_equity < 0.5
ORDER BY f.roe DESC
LIMIT 50;
```

### Stocks by Sector (India)
```sql
SELECT sector, COUNT(*) as stock_count, 
       AVG(CAST(f.pe_ratio AS FLOAT)) as avg_pe,
       AVG(CAST(f.roe AS FLOAT)) as avg_roe
FROM stocks s
LEFT JOIN fundamentals f ON s.stock_id = f.stock_id
WHERE s.market_id = (SELECT market_id FROM markets WHERE market_name = 'india')
GROUP BY sector
ORDER BY stock_count DESC;
```

### OHLCV Statistics (52-Week High/Low)
```sql
SELECT s.ticker, s.name, s.sector,
       MAX(h.high_price) as high_52w,
       MIN(h.low_price) as low_52w,
       (SELECT close_price FROM ohlcv_history WHERE stock_id = s.stock_id ORDER BY date DESC LIMIT 1) as latest_close
FROM stocks s
JOIN ohlcv_history h ON s.stock_id = h.stock_id
WHERE h.date > CURRENT_DATE - INTERVAL '1 year'
GROUP BY s.stock_id, s.ticker, s.name, s.sector
ORDER BY (high_52w - low_52w) DESC
LIMIT 50;
```

### Cross-Market Comparison
```sql
SELECT m.market_name, COUNT(DISTINCT s.stock_id) as total_stocks,
       COUNT(DISTINCT f.fundamental_id) as with_fundamentals,
       ROUND(100.0 * COUNT(DISTINCT f.fundamental_id) / COUNT(DISTINCT s.stock_id), 1) as coverage_pct
FROM markets m
LEFT JOIN stocks s ON m.market_id = s.market_id
LEFT JOIN fundamentals f ON s.stock_id = f.stock_id
GROUP BY m.market_id, m.market_name
ORDER BY total_stocks DESC;
```

## Performance Tips

### Index Already Created For:
- `ticker` lookup (fast symbol search)
- `market_id` (fast market filtering)
- `sector` (fast sector analysis)
- `date` on OHLCV (fast time-series queries)
- `(stock_id, date)` composite (fast historical lookups)

### Query Optimization
```sql
-- Use EXPLAIN to analyze query plans
EXPLAIN ANALYZE
SELECT s.ticker, AVG(h.close_price) as avg_price
FROM stocks s
JOIN ohlcv_history h ON s.stock_id = h.stock_id
WHERE s.market_id = 1
  AND h.date > CURRENT_DATE - INTERVAL '30 days'
GROUP BY s.ticker;
```

## Maintenance

### Export Data to CSV
```sql
COPY (SELECT * FROM stocks WHERE market_id = 1) 
TO '/tmp/india_stocks.csv' WITH CSV HEADER;
```

### Backup Database
```bash
pg_dump -d market_data -Fc > market_data_backup.dump
```

### Restore Database
```bash
pg_restore -d market_data market_data_backup.dump
```

### Check Database Size
```sql
SELECT pg_size_pretty(pg_database_size('market_data'));
```

## Troubleshooting

### Connection Issues
```bash
# Check PostgreSQL status
brew services list | grep postgresql

# Restart PostgreSQL
brew services restart postgresql@15
```

### Permission Errors
```bash
# Switch to postgres user
sudo -u postgres psql
CREATE USER postgres SUPERUSER;
ALTER USER postgres WITH PASSWORD 'postgres';
```

### Import Errors
Check CSV format:
- Ensure headers match expected columns
- Check for encoding issues (should be UTF-8)
- Verify date formats (YYYY-MM-DD)

---

**Next Steps:**
1. Run `python /Users/umashankar/load_market_data_to_postgres.py`
2. Connect via `psql -d market_data`
3. Run queries from above
4. Use for Phase 1 analysis queries
