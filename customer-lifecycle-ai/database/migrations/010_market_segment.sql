-- ===========================================================================
-- Migration 010: Bank Market-Segment Integration (additive / nullable)
-- Target DB: etl_clean
--
-- Carries the bank's authoritative market-segment field into the clean layer
-- and the feature store WITHOUT modifying any existing synthetic rows.
--
--   customers_clean.market_segment_code  — original bank value (raw, preserved)
--   customers_clean.market_segment       — deterministic label (shared mapping)
--   customer_features.market_segment_code — same raw code on the feature row
--   customer_features.market_segment      — same deterministic label (feature)
--
-- Both columns are NULLABLE and ADD COLUMN IF NOT EXISTS, so:
--   * existing synthetic customers_clean / customer_features rows are untouched,
--   * a fresh pilot DB gets the columns with NULLs until real bank data lands,
--   * re-running the migration is safe.
--
-- Single authoritative mapping lives in shared/constants/market_segments.py
-- (BANK-PROVIDED BUSINESS LOGIC — see docs/ml/market-segment-integration.md).
-- No SQL CASE here by design; labels are resolved via that module.
--
-- Each block is guarded with to_regclass() so the migration succeeds even on
-- partially-migrated / older databases where a table does not yet exist.
-- ===========================================================================

-- ---- customers_clean: raw bank code + deterministic label ----
DO $$
BEGIN
    IF to_regclass('public.customers_clean') IS NOT NULL THEN
        ALTER TABLE public.customers_clean
            ADD COLUMN IF NOT EXISTS market_segment_code VARCHAR(16),
            ADD COLUMN IF NOT EXISTS market_segment      VARCHAR(32);
    END IF;
END $$;

-- ---- customer_features: carry the same two values onto feature rows ----
DO $$
BEGIN
    IF to_regclass('public.customer_features') IS NOT NULL THEN
        ALTER TABLE public.customer_features
            ADD COLUMN IF NOT EXISTS market_segment_code VARCHAR(16),
            ADD COLUMN IF NOT EXISTS market_segment      VARCHAR(32);
    END IF;
END $$;

-- ---- demographics_clean: keep the code available for demographics lineage ----
DO $$
BEGIN
    IF to_regclass('public.demographics_clean') IS NOT NULL THEN
        ALTER TABLE public.demographics_clean
            ADD COLUMN IF NOT EXISTS market_segment_code VARCHAR(16);
    END IF;
END $$;
