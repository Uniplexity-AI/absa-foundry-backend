-- ===========================================================================
-- ETL Schema Migration — 002_clean_data_tables.sql
-- Target database: etl_clean
--
-- Creates the core cleaned data tables that the synthetic data generator
-- (generate_synthetic_feature_store_data.py) populates, and that the
-- Feature Engineering service reads from.
--
-- This ensures all DDL is managed by Alembic/migrations, not by data generators.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS public.customers_clean (
    customer_id VARCHAR(64) PRIMARY KEY,
    full_name VARCHAR(128),
    date_of_birth DATE,
    gender VARCHAR(16),
    branch_code VARCHAR(16),
    customer_since_date DATE,
    kyc_tier VARCHAR(16),
    nationality VARCHAR(64),
    status VARCHAR(16),
    loaded_at TIMESTAMPTZ NOT NULL,
    batch_id VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.customer_transactions_clean (
    transaction_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) REFERENCES public.customers_clean(customer_id),
    transaction_date TIMESTAMP,
    amount NUMERIC(14,2),
    transaction_type VARCHAR(16),
    channel VARCHAR(16),
    merchant_category VARCHAR(32),
    currency VARCHAR(8),
    loaded_at TIMESTAMPTZ NOT NULL,
    batch_id VARCHAR(64) NOT NULL
);

-- Ensure transaction_date is TIMESTAMP (it might have been DATE)
DO $$
BEGIN
  IF (SELECT data_type FROM information_schema.columns
      WHERE table_name = 'customer_transactions_clean'
        AND column_name = 'transaction_date') = 'date' THEN
    ALTER TABLE public.customer_transactions_clean ALTER COLUMN transaction_date
      TYPE TIMESTAMP USING transaction_date::timestamp;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.accounts_clean (
    account_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) REFERENCES public.customers_clean(customer_id),
    account_type VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    opened_date DATE,
    loaded_at TIMESTAMPTZ NOT NULL,
    batch_id VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.loans_clean (
    loan_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) REFERENCES public.customers_clean(customer_id),
    loan_type VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    origination_date DATE,
    loaded_at TIMESTAMPTZ NOT NULL,
    batch_id VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.cards_clean (
    card_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) REFERENCES public.customers_clean(customer_id),
    card_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    issued_date DATE,
    expiry_date DATE,
    activated_date DATE,
    loaded_at TIMESTAMPTZ NOT NULL,
    batch_id VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.digital_engagement_clean (
    engagement_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) REFERENCES public.customers_clean(customer_id),
    login_date DATE NOT NULL,
    platform VARCHAR(32) NOT NULL,
    session_duration_seconds INTEGER,
    actions_count INTEGER,
    loaded_at TIMESTAMPTZ NOT NULL,
    batch_id VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.demographics_clean (
    customer_id VARCHAR(64) PRIMARY KEY REFERENCES public.customers_clean(customer_id),
    employment_status VARCHAR(32),
    employer_name VARCHAR(128),
    monthly_income_declared NUMERIC(14,2),
    education_level VARCHAR(32),
    marital_status VARCHAR(16),
    loaded_at TIMESTAMPTZ NOT NULL,
    batch_id VARCHAR(64) NOT NULL
);
