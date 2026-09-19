-- ===========================================================================
-- Migration 020: public.customers_clean.mobile_number (idempotent)
-- Target database: etl_clean
--
-- WHY THIS EXISTS
--   gateway/services/customer_profile_service.py._PROFILE_SQL selects
--   c.mobile_number. On any database where that column is absent:
--
--     * GET /api/v1/customers/{id}/profile raises UndefinedColumn -> HTTP 500,
--       so the profile page silently falls back to snapshot-only data and no
--       saved edit is ever visible; and
--     * etl/ingest/loader.py.upsert writes only the columns it can reflect, so
--       a mobile-number edit was dropped while the load still reported success.
--
--   Migration 014 also declares this column, but 014 is "already applied" on
--   existing databases, so a runner that tracks applied migrations would never
--   execute its new statement. This file is the forward fix for those
--   databases; scripts/pilot_migrate.py registers it after 018 and 019.
--
-- Idempotent: guarded with to_regclass + ADD COLUMN IF NOT EXISTS, so it is a
-- safe no-op on a database that already has the column. Nullable, so existing
-- rows and readers are untouched.
-- ===========================================================================

DO $$
BEGIN
    IF to_regclass('public.customers_clean') IS NOT NULL THEN
        ALTER TABLE public.customers_clean
            ADD COLUMN IF NOT EXISTS mobile_number VARCHAR(32);
    END IF;
END $$;
