-- ===========================================================================
-- ETL Schema Migration — 021_feature_stores.sql
-- Target database: etl_clean
--
-- Creates the model-specific feature stores as requested in the ETL Update Plan.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS public.feature_store_shared (
    customer_id VARCHAR(64) PRIMARY KEY,
    snapshot_month DATE,
    snapshot_date DATE,
    tenure_months INTEGER,
    sex VARCHAR(16),
    geo_region VARCHAR(64),
    town_or_city VARCHAR(64),
    country VARCHAR(64),
    gross_income NUMERIC(14,2),
    other_income NUMERIC(14,2),
    income_proxy NUMERIC(14,2),
    job_title VARCHAR(128),
    employment_type VARCHAR(64),
    employment_status VARCHAR(64),
    market_segment VARCHAR(64),
    risk_level VARCHAR(32),
    risk_score VARCHAR(32),
    credit_rating VARCHAR(32),
    barclaycard_grade VARCHAR(32),
    solicitation_channel VARCHAR(64),
    acquisition_campaign VARCHAR(64),
    num_active_products INTEGER,
    has_investment INTEGER,
    current_count INTEGER,
    savings_count INTEGER,
    investment_count INTEGER,
    secured_count INTEGER,
    unsecured_count INTEGER,
    has_mortgage INTEGER,
    recency_days INTEGER,
    frequency_30d INTEGER,
    frequency_90d INTEGER,
    frequency_12m INTEGER,
    monetary_30d NUMERIC(14,2),
    monetary_90d NUMERIC(14,2),
    monetary_12m NUMERIC(14,2),
    max_transaction_value_12m NUMERIC(14,2),
    active_days_30d INTEGER,
    active_days_90d INTEGER,
    avg_transaction_value_12m NUMERIC(14,2),
    credits_30d NUMERIC(14,2),
    credits_90d NUMERIC(14,2),
    debits_30d NUMERIC(14,2),
    debits_90d NUMERIC(14,2),
    net_cashflow_30d NUMERIC(14,2),
    net_cashflow_90d NUMERIC(14,2),
    inbound_vs_outbound_ratio_90d NUMERIC(14,4),
    interest_rate NUMERIC(14,4),
    other_bank_name VARCHAR(128),
    other_bank_cde VARCHAR(64),
    loaded_at TIMESTAMPTZ DEFAULT NOW(),
    batch_id VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS public.feature_store_clv (
    customer_id VARCHAR(64) PRIMARY KEY REFERENCES public.feature_store_shared(customer_id),
    snapshot_month DATE,
    fee_income_m1 NUMERIC(14,2),
    fee_income_12m NUMERIC(14,2),
    avg_monthly_fee_12m NUMERIC(14,2),
    card_spend_12m NUMERIC(14,2),
    num_products_opened_12m INTEGER,
    num_products_closed_12m INTEGER,
    product_net_12m INTEGER,
    nii_m1 NUMERIC(14,2),
    avg_monthly_nii_12m NUMERIC(14,2),
    target_fee_income_12m NUMERIC(14,2),
    target_clv_12m NUMERIC(14,2),
    target_margin_12m NUMERIC(14,2),
    loaded_at TIMESTAMPTZ DEFAULT NOW(),
    batch_id VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS public.feature_store_churn (
    customer_id VARCHAR(64) PRIMARY KEY REFERENCES public.feature_store_shared(customer_id),
    snapshot_month DATE,
    -- basic churn fields, inferred from instructions "volume ratios, large outflows, dormancy status"
    dormancy_status VARCHAR(32),
    tx_vol_ratio_30d_90d NUMERIC(14,4),
    large_outflow_flag INTEGER,
    target_churn_30d INTEGER,
    target_churn_90d INTEGER,
    loaded_at TIMESTAMPTZ DEFAULT NOW(),
    batch_id VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS public.feature_store_lifecycle (
    customer_id VARCHAR(64) PRIMARY KEY REFERENCES public.feature_store_shared(customer_id),
    snapshot_month DATE,
    -- basic lifecycle fields, inferred from instructions "salary consistency, activity change metrics"
    salary_consistency_score NUMERIC(14,4),
    activity_change_metric NUMERIC(14,4),
    loaded_at TIMESTAMPTZ DEFAULT NOW(),
    batch_id VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS public.feature_store_balance (
    customer_id VARCHAR(64) PRIMARY KEY REFERENCES public.feature_store_shared(customer_id),
    snapshot_month DATE,
    -- basic balance fields, inferred from instructions "cash-flow metrics and calendar features"
    cash_flow_metric NUMERIC(14,4),
    calendar_features VARCHAR(64),
    loaded_at TIMESTAMPTZ DEFAULT NOW(),
    batch_id VARCHAR(64)
);
