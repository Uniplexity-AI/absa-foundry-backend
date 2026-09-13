-- ===========================================================================
-- Migration 015: Make public.customer_features a first-class ingest target
-- Target database: etl_clean
--
-- The RM workspace can now load a data extract straight from a CSV or from the
-- core system, choosing which table it lands in (see /api/v1/ingest/schema).
-- ``public.customers_clean`` has been a load target since migration 013;
-- ``public.customer_features`` needed two things first:
--
--   1. Two columns that the feature-store export carries but the DDL never
--      declared. Without them those columns had nowhere to land, which is why
--      the mapping table reported them as "not loaded":
--
--        target_lifecycle_stage — the supervised label used for lifecycle
--                                 staging; NULLABLE because the historical
--                                 snapshots genuinely have no label.
--        balance_growth_pct     — forward-looking balance growth in percent.
--                                 DOUBLE PRECISION to match the other
--                                 derived percentage features on this table
--                                 (amount_growth_ratio, *_pct columns).
--
--   2. A NOT NULL DEFAULT on computed_at is already present, so the ingest
--      loader can stamp ``computed_at`` for rows that arrive without it, while
--      still honouring a value supplied by the extract. No change needed.
--
-- Everything here is additive and NULLABLE, so existing rows, readers
-- (feature engineering, prediction, state engine) and the UNIQUE
-- ``(customer_id, as_of_date)`` upsert key are all unaffected.
-- Idempotent: safe to re-run.
-- ===========================================================================

DO $$
BEGIN
    IF to_regclass('public.customer_features') IS NOT NULL THEN
        ALTER TABLE public.customer_features
            ADD COLUMN IF NOT EXISTS target_lifecycle_stage VARCHAR(16),
            ADD COLUMN IF NOT EXISTS balance_growth_pct     DOUBLE PRECISION;
    END IF;
END $$;

-- The profile / state lookups read the newest snapshot per customer, and the
-- ingest upsert probes (customer_id, as_of_date) on every row. Both are served
-- by the existing indexes; this one backs "latest snapshot for a cohort".
CREATE INDEX IF NOT EXISTS idx_customer_features_customer_date_desc
    ON public.customer_features (customer_id, as_of_date DESC);

-- Cheap way for operators to see how much of a snapshot is actually labelled.
CREATE INDEX IF NOT EXISTS idx_customer_features_lifecycle_stage
    ON public.customer_features (target_lifecycle_stage);
