-- ===========================================================================
-- Migration 017: Add complete feature store catalogue to customer_features
-- Target database: etl_clean
-- ===========================================================================

DO $$
BEGIN
    IF to_regclass('public.customer_features') IS NOT NULL THEN
        -- Transaction counts & cadence
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS txn_count_365d INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS credit_sum_30d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS debit_sum_30d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS credit_to_debit_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS balance_trend_90d VARCHAR(64);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS monthly_income_estimate DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS has_salary_credit BOOLEAN;

        -- Behavioural features
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS behav_txn_count_7d INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS behav_active_days_90d INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS behav_inactive_days_90d INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS behav_recency_score DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS behav_frequency_score DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS behav_diversity_score DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS behav_activity_consistency DOUBLE PRECISION;

        -- Financial features
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS fin_total_credit_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS fin_total_debit_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS fin_median_txn_amount_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS fin_salary_consistency DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS fin_income_growth DOUBLE PRECISION;

        -- Channel mix
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS chan_mobile_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS chan_atm_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS chan_branch_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS chan_digital_adoption_score DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS chan_channel_entropy DOUBLE PRECISION;

        -- Tenure & lifecycle
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS customer_tenure_days INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS customer_segment VARCHAR(64);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS age_years INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS onboarding_channel VARCHAR(32);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS target_lifecycle_stage VARCHAR(64);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS engagement_score DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS txn_frequency_trend DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS inactivity_streak_days INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS balance_growth_pct DOUBLE PRECISION;

        -- Temporal patterns
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS temp_weekend_txn_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS temp_weekday_txn_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS temp_morning_activity_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS temp_afternoon_activity_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS temp_evening_activity_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS temp_payday_activity_ratio_90d DOUBLE PRECISION;

        -- Risk & anomalies
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS risk_high_value_txn_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS risk_txn_volatility_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS risk_reversal_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS risk_cash_heavy_ratio_90d DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS risk_unusual_channel_flag BOOLEAN;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS risk_dormant_indicator BOOLEAN;

        -- Relationship & products
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_customer_status VARCHAR(64);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_accounts_active INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_has_loan BOOLEAN;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_has_savings BOOLEAN;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_products_owned INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_has_card BOOLEAN;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_card_count INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_has_unactivated_card BOOLEAN;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_card_expiring_30d INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS rel_card_types INT;

        -- Digital engagement
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS eng_login_count_7d INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS eng_login_count_30d INT;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS eng_digital_platform_preference VARCHAR(32);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS eng_avg_session_duration_30d DOUBLE PRECISION;

        -- Demographics & profile
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS prof_age_band VARCHAR(16);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS prof_primary_branch VARCHAR(16);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS prof_kyc_tier VARCHAR(16);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS prof_nationality VARCHAR(64);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS prof_employment_status VARCHAR(32);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS prof_education_level VARCHAR(32);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS prof_declared_vs_observed_income_ratio DOUBLE PRECISION;
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS market_segment_code VARCHAR(16);
        ALTER TABLE public.customer_features ADD COLUMN IF NOT EXISTS market_segment VARCHAR(32);
    END IF;
END $$;
