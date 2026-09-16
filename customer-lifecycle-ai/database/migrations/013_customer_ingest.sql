-- ===========================================================================
-- Migration 013: Customer ingest reject store
-- Target database: etl_clean
--
-- Rows that fail the ingest format contract (etl/ingest/customer_schema.py)
-- are never silently dropped: they land here with the exact rule violations so
-- an operator can fix the source extract and re-upload only what failed.
--
-- This is deliberately separate from public.customers_rejected, which mirrors
-- the legacy raw_customers → customers_clean pipeline shape and cannot carry
-- a generic "which rule failed" payload.
--
-- Idempotent: safe to re-run.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS public.customer_ingest_rejected (
    id                BIGSERIAL PRIMARY KEY,
    batch_id          VARCHAR(64),
    source_name       VARCHAR(256),
    row_number        INTEGER,
    customer_id       VARCHAR(64),
    raw_row           JSONB,
    rejection_reason  TEXT,
    rejected_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_customer_ingest_rejected_batch
    ON public.customer_ingest_rejected (batch_id);

CREATE INDEX IF NOT EXISTS idx_customer_ingest_rejected_rejected_at
    ON public.customer_ingest_rejected (rejected_at DESC);
