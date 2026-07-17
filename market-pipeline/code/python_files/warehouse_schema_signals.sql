-- warehouse_schema_signals.sql
--
-- New fact tables for screener-research data collected outside the existing
-- OHLCV/fundamentals pipeline. Extends the existing market_data warehouse
-- (public.markets, public.stocks, public.ohlcv_history, public.fundamentals)
-- WITHOUT modifying any of those tables.
--
-- Source files (see load_signals_to_warehouse.py):
--   1. factorial_screener_signals_us.parquet               -> fact_screener_signal
--   2. factorial_screener_signals_IN_technical.parquet      -> fact_screener_signal
--   3. factorial_screener_signals_JP_technical.parquet      -> fact_screener_signal
--   4. factorial_screener_signals_KR_technical.parquet      -> fact_screener_signal
--   5. factorial_screener_signals_CN_technical.parquet      -> fact_screener_signal
--   6. short_interest_us.parquet                            -> fact_short_interest
--   7. insider_transactions_us.parquet                      -> fact_insider_transaction
--
-- Apply with:
--   psql -h /tmp -U umashankar -d market_data -f warehouse_schema_signals.sql

-- =====================================================================
-- fact_screener_signal
--   One row per (stock_id, signal_date, screener): the forward returns
--   and liquidity/volatility stats captured when a screener fired on a
--   given stock/date, across horizons 5/21/63/126/252 trading days.
--   market_id is denormalized from stocks.market_id purely for query
--   convenience (avoids a join on every market-filtered query).
--
--   ON CONFLICT strategy: DO UPDATE.
--   Rationale: the source files are periodically regenerated (return
--   windows recomputed as more history/benchmark data becomes
--   available), so a reload should refresh values for an existing
--   (stock_id, signal_date, screener) key rather than silently keep
--   stale numbers. Observed exact-duplicate rows *within* a single
--   load (14,719 in the US file, all-NULL return columns from
--   insufficient trailing history) are harmless either way since
--   DO UPDATE just rewrites the same NULLs.
-- =====================================================================
CREATE TABLE IF NOT EXISTS public.fact_screener_signal (
    signal_id           BIGSERIAL PRIMARY KEY,
    stock_id            INTEGER NOT NULL REFERENCES public.stocks(stock_id) ON DELETE CASCADE,
    market_id           INTEGER NOT NULL REFERENCES public.markets(market_id),
    signal_date          DATE NOT NULL,
    screener             VARCHAR(50) NOT NULL,
    signal_year           SMALLINT,
    ret_t5d              DOUBLE PRECISION,
    bench_ret_t5d         DOUBLE PRECISION,
    xret_t5d              DOUBLE PRECISION,
    ret_t21d              DOUBLE PRECISION,
    bench_ret_t21d        DOUBLE PRECISION,
    xret_t21d             DOUBLE PRECISION,
    ret_t63d              DOUBLE PRECISION,
    bench_ret_t63d        DOUBLE PRECISION,
    xret_t63d              DOUBLE PRECISION,
    ret_t126d              DOUBLE PRECISION,
    bench_ret_t126d        DOUBLE PRECISION,
    xret_t126d             DOUBLE PRECISION,
    ret_t252d               DOUBLE PRECISION,
    bench_ret_t252d         DOUBLE PRECISION,
    xret_t252d               DOUBLE PRECISION,
    dollar_vol_63d            DOUBLE PRECISION,
    log_liquidity              DOUBLE PRECISION,
    volatility_63d               DOUBLE PRECISION,
    loaded_at                     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_fact_screener_signal UNIQUE (stock_id, signal_date, screener)
);
CREATE INDEX IF NOT EXISTS idx_fact_screener_signal_market ON public.fact_screener_signal(market_id);
CREATE INDEX IF NOT EXISTS idx_fact_screener_signal_screener ON public.fact_screener_signal(screener);
CREATE INDEX IF NOT EXISTS idx_fact_screener_signal_date ON public.fact_screener_signal(signal_date);

-- =====================================================================
-- fact_short_interest
--   FINRA-style bi-monthly short interest settlement data, US only.
--   UNIQUE(stock_id, settlement_date) — confirmed 0 duplicate rows on
--   this key in the 97,555-row source file, so this is a real natural
--   key (one settlement report per stock per settlement date).
--
--   ON CONFLICT strategy: DO UPDATE.
--   Rationale: FINRA occasionally issues revisions (source file has a
--   revisionFlag column) to a previously reported settlement date, so
--   a reload should overwrite with the latest reported values.
-- =====================================================================
CREATE TABLE IF NOT EXISTS public.fact_short_interest (
    short_interest_id             BIGSERIAL PRIMARY KEY,
    stock_id                      INTEGER NOT NULL REFERENCES public.stocks(stock_id) ON DELETE CASCADE,
    settlement_date                DATE NOT NULL,
    accounting_year_month_number    INTEGER,
    issue_name                       VARCHAR(255),
    issuer_services_group_exchange_code VARCHAR(10),
    market_class_code                 VARCHAR(20),
    current_short_position_quantity    BIGINT,
    previous_short_position_quantity    BIGINT,
    stock_split_flag                     VARCHAR(5),
    average_daily_volume_quantity         BIGINT,
    days_to_cover_quantity                 NUMERIC,
    revision_flag                           VARCHAR(5),
    change_percent                           NUMERIC,
    change_previous_number                    BIGINT,
    loaded_at                                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_fact_short_interest UNIQUE (stock_id, settlement_date)
);
CREATE INDEX IF NOT EXISTS idx_fact_short_interest_date ON public.fact_short_interest(settlement_date);

-- =====================================================================
-- fact_insider_transaction
--   SEC Form 4 insider transactions, US only.
--
--   Natural key: NOT just (accession_number, stock_id) — a single
--   accession_number (one SEC filing) commonly reports MULTIPLE
--   distinct transactions for the same insider/symbol (e.g. several
--   lots sold on the same day at different prices, or several trans
--   codes). Verified: 29,639 of 82,408 distinct accession numbers in
--   the source file have >1 row. Using accession_number+stock_id alone
--   would silently collapse those into one row via ON CONFLICT.
--   The composite key below (accession_number, stock_id, trans_date,
--   trans_code, trans_shares, trans_price_per_share) was verified to
--   have exactly 3,958 duplicate rows in the 208,930-row source file,
--   which is EXACTLY the count of byte-identical full-row duplicates
--   (confirmed via df.duplicated() on the whole frame) — i.e. this key
--   is a true natural key and the only conflicts it will ever produce
--   are genuine re-loads of the same filing data.
--
--   ON CONFLICT strategy: DO NOTHING.
--   Rationale: a filed Form 4 transaction is immutable historical
--   fact; if the same natural key reappears on reload it is the same
--   record, not a revision, so there's nothing to update.
--
--   Note: TRANS_DATE has 1 null and TRANS_PRICEPERSHARE has 56 nulls
--   in the source; Postgres UNIQUE constraints treat NULL as distinct
--   from NULL, so a handful of rows sharing all non-null key columns
--   but a null trans_date/price could theoretically both land in the
--   table (not deduped). This affects at most ~57 of 208,930 rows.
-- =====================================================================
CREATE TABLE IF NOT EXISTS public.fact_insider_transaction (
    insider_txn_id            BIGSERIAL PRIMARY KEY,
    stock_id                   INTEGER NOT NULL REFERENCES public.stocks(stock_id) ON DELETE CASCADE,
    accession_number            VARCHAR(30) NOT NULL,
    trans_date                   DATE,
    filing_date                   DATE,
    trans_code                     VARCHAR(5),
    trans_shares                    NUMERIC,
    trans_price_per_share             NUMERIC,
    quarter                             VARCHAR(10),
    loaded_at                            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_fact_insider_transaction
        UNIQUE (accession_number, stock_id, trans_date, trans_code, trans_shares, trans_price_per_share)
);
CREATE INDEX IF NOT EXISTS idx_fact_insider_transaction_stock ON public.fact_insider_transaction(stock_id);
CREATE INDEX IF NOT EXISTS idx_fact_insider_transaction_filing_date ON public.fact_insider_transaction(filing_date);
