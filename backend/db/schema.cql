-- Bootstrap script for the herrrickshaw keyspace.
-- Run manually via:  cqlsh -f backend/db/schema.cql
-- The FastAPI app also runs all of this automatically on startup via cassandra_client.connect().

CREATE KEYSPACE IF NOT EXISTS herrrickshaw
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE herrrickshaw;

-- ── instruments tables (seeded from CSV files) ────────────────────────────────

CREATE TABLE IF NOT EXISTS instruments (
    market      text,
    yf_ticker   text,
    symbol      text,
    name        text,
    name_lower  text,
    isin        text,
    exchange    text,
    country     text,
    PRIMARY KEY (market, yf_ticker)
) WITH CLUSTERING ORDER BY (yf_ticker ASC);

-- Lookup by raw exchange code / NSE symbol / US ticker
CREATE TABLE IF NOT EXISTS instruments_by_symbol (
    market    text,
    symbol    text,
    yf_ticker text,
    name      text,
    PRIMARY KEY (market, symbol)
) WITH CLUSTERING ORDER BY (symbol ASC);

-- Lookup by lowercase company name (supports prefix-range queries)
CREATE TABLE IF NOT EXISTS instruments_by_name (
    market     text,
    name_lower text,
    yf_ticker  text,
    name       text,
    PRIMARY KEY (market, name_lower)
) WITH CLUSTERING ORDER BY (name_lower ASC);

-- Lookup by ISIN (India: INE…, US: US…, etc.)
CREATE TABLE IF NOT EXISTS instruments_by_isin (
    isin      text PRIMARY KEY,
    market    text,
    yf_ticker text,
    symbol    text,
    name      text
);

-- ── live quote cache ──────────────────────────────────────────────────────────
-- Updated fire-and-forget after every /api/live/fetch call.
-- Signal values: BUY | SELL | HOLD
--   BUY  = RSI < 30  AND Close > EMA_50
--   SELL = RSI > 70  AND Close < EMA_50
--   HOLD = otherwise

CREATE TABLE IF NOT EXISTS stock_quotes (
    market         text,
    yf_ticker      text,
    fetched_at     timestamp,
    cmp            double,
    rsi            double,
    ema_50         double,
    rsi_signal     text,
    pe             double,
    pb             double,
    roe            double,
    opm            double,
    market_cap     double,
    volume         bigint,
    high_52w       double,
    low_52w        double,
    debt_to_equity double,
    PRIMARY KEY (market, yf_ticker)
) WITH CLUSTERING ORDER BY (yf_ticker ASC);

-- ── seeding book-keeping ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS seed_status (
    market    text PRIMARY KEY,
    seeded_at timestamp,
    row_count int
);
