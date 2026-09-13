-- ===========================================================================
-- Migration 014: Customer identity fields on the clean layer
-- Target database: etl_clean
--
-- Adds the two identity attributes the RM workspace shows on the customer
-- profile but that no pilot table carries yet:
--
--   account_number — the customer's primary account. Populated explicitly by
--                    the ingest pipeline when a source supplies it; when it is
--                    NULL the profile API falls back to the earliest row in
--                    public.accounts_clean, so the field is useful either way.
--   national_id    — the customer's NRC / national identity number. Kept as
--                    free text because the format varies per country
--                    (Zambia: ######/##/#). No pilot source supplies it yet,
--                    so it stays NULL until a source is mapped through
--                    /api/v1/ingest.
--
-- Both are NULLABLE and additive, so existing rows and readers are untouched.
-- Idempotent: safe to re-run.
-- ===========================================================================

DO $$
BEGIN
    IF to_regclass('public.customers_clean') IS NOT NULL THEN
        ALTER TABLE public.customers_clean
            ADD COLUMN IF NOT EXISTS account_number VARCHAR(64),
            ADD COLUMN IF NOT EXISTS national_id    VARCHAR(32);
    END IF;
END $$;

-- The RM workspace looks customers up by account number as well as by ID.
CREATE INDEX IF NOT EXISTS idx_customers_clean_account_number
    ON public.customers_clean (account_number);

CREATE INDEX IF NOT EXISTS idx_accounts_clean_customer_opened
    ON public.accounts_clean (customer_id, opened_date);
