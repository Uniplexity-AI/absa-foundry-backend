-- Migration 002: Add relationship, card, and digital engagement feature columns
-- Run against the etl_clean database where customer_features lives.
--
-- Usage:
--   psql -h <host> -U <user> -d etl_clean -f database/feature_store/002_add_product_engagement_features.sql

-- ===========================================================================
-- Relationship features (accounts + loans) — unblocks 4 deferred features
-- ===========================================================================
ALTER TABLE public.customer_features
    ADD COLUMN IF NOT EXISTS rel_accounts_active INT,
    ADD COLUMN IF NOT EXISTS rel_has_loan BOOLEAN,
    ADD COLUMN IF NOT EXISTS rel_has_savings BOOLEAN,
    ADD COLUMN IF NOT EXISTS rel_products_owned INT;

-- ===========================================================================
-- Card features — unblocks 5 card portfolio features
-- ===========================================================================
ALTER TABLE public.customer_features
    ADD COLUMN IF NOT EXISTS rel_has_card BOOLEAN,
    ADD COLUMN IF NOT EXISTS rel_card_count INT,
    ADD COLUMN IF NOT EXISTS rel_has_unactivated_card BOOLEAN,
    ADD COLUMN IF NOT EXISTS rel_card_expiring_30d INT,
    ADD COLUMN IF NOT EXISTS rel_card_types INT;

-- ===========================================================================
-- Digital engagement features — unblocks 4 engagement features
-- ===========================================================================
ALTER TABLE public.customer_features
    ADD COLUMN IF NOT EXISTS eng_login_count_7d INT,
    ADD COLUMN IF NOT EXISTS eng_login_count_30d INT,
    ADD COLUMN IF NOT EXISTS eng_digital_platform_preference VARCHAR(32),
    ADD COLUMN IF NOT EXISTS eng_avg_session_duration_30d DOUBLE PRECISION;

-- ===========================================================================
-- Profile features (kyc_tier, nationality) — unblocks 2 profile features
-- ===========================================================================
ALTER TABLE public.customer_features
    ADD COLUMN IF NOT EXISTS prof_kyc_tier VARCHAR(16),
    ADD COLUMN IF NOT EXISTS prof_nationality VARCHAR(64),
    ADD COLUMN IF NOT EXISTS prof_employment_status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS prof_education_level VARCHAR(32),
    ADD COLUMN IF NOT EXISTS prof_declared_vs_observed_income_ratio DOUBLE PRECISION;
