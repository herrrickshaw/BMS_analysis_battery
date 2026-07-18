-- warehouse_versioning.sql
--
-- Adds data-snapshot versioning to the market_data warehouse. Until now,
-- every loader (load_signals_to_warehouse.py, load_ohlcv_to_warehouse.py)
-- used ON CONFLICT DO UPDATE keyed on a natural key (stock_id, date,
-- screener, ...), which overwrites in place -- a reload leaves no record
-- of what the value was before the reload. This migration changes that:
-- reloads now ACCUMULATE as new batches instead of overwriting, so you can
-- ask "what did fact_screener_signal look like as of 2026-07-01" and get a
-- real answer.
--
-- Design (data snapshot versioning, not a schema-migration/DDL tracker):
--   1. load_batches: one row per loader run. Every fact table load is
--      tagged with a batch_id referencing this table (source file, git
--      commit, row count, start/finish time, status).
--   2. Each versioned fact table gets a `batch_id` column. The old natural
--      key (e.g. UNIQUE(stock_id, signal_date, screener)) is extended to
--      include batch_id, so a NEW load never collides with a prior load's
--      rows -- both are kept. ON CONFLICT now only fires if the *same*
--      batch_id is re-run (e.g. a crashed loader resumed), where DO UPDATE
--      keeps that resume idempotent without creating duplicate history.
--   3. A `<table>_current` view (DISTINCT ON natural key, latest batch
--      first) reproduces the pre-migration "just give me the latest value"
--      behavior, so existing downstream queries can switch to querying the
--      view and see no change in row count/shape.
--   4. "As of date X" queries: join to load_batches on finished_at <= X,
--      take DISTINCT ON natural key ordered by batch finished_at DESC.
--      See the worked example at the bottom of this file.
--
-- Scope: fact_screener_signal, fact_short_interest, fact_insider_transaction
-- (built this session) + ohlcv_history (pre-existing, but reloaded by
-- load_ohlcv_to_warehouse.py built this session). `fundamentals` is
-- excluded -- it has no date dimension at all (UNIQUE(stock_id) only, 1 row
-- total in the live DB) and is not written by any loader in this repo, so
-- there is nothing to version yet; revisit if/when a real fundamentals
-- loader is built.
--
-- Apply with:
--   psql -h /tmp -U umashankar -d market_data -f warehouse_versioning.sql

-- =====================================================================
-- load_batches: registry of every load run, across all versioned tables.
-- =====================================================================
CREATE TABLE IF NOT EXISTS public.load_batches (
    batch_id      BIGSERIAL PRIMARY KEY,
    table_name    VARCHAR(50) NOT NULL,
    job_name      VARCHAR(100),
    source_file   TEXT,
    git_commit    VARCHAR(40),
    row_count     BIGINT,
    started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at   TIMESTAMP,
    status        VARCHAR(10) NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'success', 'failed')),
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_load_batches_table ON public.load_batches(table_name, finished_at);

-- =====================================================================
-- fact_screener_signal: add batch_id, extend natural key
-- =====================================================================
ALTER TABLE public.fact_screener_signal
    ADD COLUMN IF NOT EXISTS batch_id BIGINT REFERENCES public.load_batches(batch_id);

ALTER TABLE public.fact_screener_signal
    DROP CONSTRAINT IF EXISTS uq_fact_screener_signal;
ALTER TABLE public.fact_screener_signal
    ADD CONSTRAINT uq_fact_screener_signal_batch
    UNIQUE (stock_id, signal_date, screener, batch_id);

CREATE OR REPLACE VIEW public.fact_screener_signal_current AS
SELECT DISTINCT ON (stock_id, signal_date, screener) *
FROM public.fact_screener_signal
ORDER BY stock_id, signal_date, screener, batch_id DESC;

-- =====================================================================
-- fact_short_interest: add batch_id, extend natural key
-- =====================================================================
ALTER TABLE public.fact_short_interest
    ADD COLUMN IF NOT EXISTS batch_id BIGINT REFERENCES public.load_batches(batch_id);

ALTER TABLE public.fact_short_interest
    DROP CONSTRAINT IF EXISTS uq_fact_short_interest;
ALTER TABLE public.fact_short_interest
    ADD CONSTRAINT uq_fact_short_interest_batch
    UNIQUE (stock_id, settlement_date, batch_id);

CREATE OR REPLACE VIEW public.fact_short_interest_current AS
SELECT DISTINCT ON (stock_id, settlement_date) *
FROM public.fact_short_interest
ORDER BY stock_id, settlement_date, batch_id DESC;

-- =====================================================================
-- fact_insider_transaction: add batch_id.
-- NOT extending the natural key here -- a filed Form 4 transaction is
-- immutable (see warehouse_schema_signals.sql's DO NOTHING rationale), so
-- there is never a "new version" of the same transaction to accumulate;
-- batch_id is kept purely for load-lineage (which run first inserted this
-- row), not for versioning its values.
-- =====================================================================
ALTER TABLE public.fact_insider_transaction
    ADD COLUMN IF NOT EXISTS batch_id BIGINT REFERENCES public.load_batches(batch_id);

-- =====================================================================
-- ohlcv_history: add batch_id, extend natural key
-- =====================================================================
ALTER TABLE public.ohlcv_history
    ADD COLUMN IF NOT EXISTS batch_id BIGINT REFERENCES public.load_batches(batch_id);

ALTER TABLE public.ohlcv_history
    DROP CONSTRAINT IF EXISTS ohlcv_history_stock_id_date_key;
ALTER TABLE public.ohlcv_history
    ADD CONSTRAINT uq_ohlcv_history_batch
    UNIQUE (stock_id, date, batch_id);

CREATE OR REPLACE VIEW public.ohlcv_history_current AS
SELECT DISTINCT ON (stock_id, date) *
FROM public.ohlcv_history
ORDER BY stock_id, date, batch_id DESC;

-- =====================================================================
-- Backfill: every row loaded before this migration has batch_id IS NULL.
-- Give them one shared "legacy" batch per table so the _current views and
-- future as-of-date queries have something to anchor to, instead of a
-- permanent NULL. finished_at is backdated to the earliest loaded_at seen
-- in that table, which is the closest honest estimate of when that data
-- actually landed (this migration itself doesn't know the true original
-- load times, since they weren't tracked).
-- =====================================================================
DO $$
DECLARE
    v_batch_id BIGINT;
    v_earliest TIMESTAMP;
BEGIN
    IF EXISTS (SELECT 1 FROM public.fact_screener_signal WHERE batch_id IS NULL) THEN
        SELECT MIN(loaded_at) INTO v_earliest FROM public.fact_screener_signal WHERE batch_id IS NULL;
        INSERT INTO public.load_batches (table_name, job_name, source_file, row_count, started_at, finished_at, status, notes)
        VALUES ('fact_screener_signal', 'legacy_backfill', NULL,
                (SELECT count(*) FROM public.fact_screener_signal WHERE batch_id IS NULL),
                v_earliest, v_earliest, 'success', 'Rows loaded before batch versioning existed')
        RETURNING batch_id INTO v_batch_id;
        UPDATE public.fact_screener_signal SET batch_id = v_batch_id WHERE batch_id IS NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM public.fact_short_interest WHERE batch_id IS NULL) THEN
        SELECT MIN(loaded_at) INTO v_earliest FROM public.fact_short_interest WHERE batch_id IS NULL;
        INSERT INTO public.load_batches (table_name, job_name, source_file, row_count, started_at, finished_at, status, notes)
        VALUES ('fact_short_interest', 'legacy_backfill', NULL,
                (SELECT count(*) FROM public.fact_short_interest WHERE batch_id IS NULL),
                v_earliest, v_earliest, 'success', 'Rows loaded before batch versioning existed')
        RETURNING batch_id INTO v_batch_id;
        UPDATE public.fact_short_interest SET batch_id = v_batch_id WHERE batch_id IS NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM public.fact_insider_transaction WHERE batch_id IS NULL) THEN
        SELECT MIN(loaded_at) INTO v_earliest FROM public.fact_insider_transaction WHERE batch_id IS NULL;
        INSERT INTO public.load_batches (table_name, job_name, source_file, row_count, started_at, finished_at, status, notes)
        VALUES ('fact_insider_transaction', 'legacy_backfill', NULL,
                (SELECT count(*) FROM public.fact_insider_transaction WHERE batch_id IS NULL),
                v_earliest, v_earliest, 'success', 'Rows loaded before batch versioning existed')
        RETURNING batch_id INTO v_batch_id;
        UPDATE public.fact_insider_transaction SET batch_id = v_batch_id WHERE batch_id IS NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM public.ohlcv_history WHERE batch_id IS NULL) THEN
        SELECT MIN(created_at) INTO v_earliest FROM public.ohlcv_history WHERE batch_id IS NULL;
        INSERT INTO public.load_batches (table_name, job_name, source_file, row_count, started_at, finished_at, status, notes)
        VALUES ('ohlcv_history', 'legacy_backfill', NULL,
                (SELECT count(*) FROM public.ohlcv_history WHERE batch_id IS NULL),
                v_earliest, v_earliest, 'success', 'Rows loaded before batch versioning existed')
        RETURNING batch_id INTO v_batch_id;
        UPDATE public.ohlcv_history SET batch_id = v_batch_id WHERE batch_id IS NULL;
    END IF;
END $$;

-- =====================================================================
-- Worked example -- "what did fact_screener_signal look like as of
-- 2026-07-01" for a given stock/screener (not run by this migration,
-- shown for reference):
--
-- SELECT DISTINCT ON (stock_id, signal_date, screener) fss.*
-- FROM fact_screener_signal fss
-- JOIN load_batches lb ON lb.batch_id = fss.batch_id
-- WHERE lb.finished_at <= '2026-07-01' AND lb.status = 'success'
-- ORDER BY stock_id, signal_date, screener, lb.finished_at DESC;
-- =====================================================================
