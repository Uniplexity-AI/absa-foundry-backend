-- =============================================================================
-- Migration 021: ABSA ML Feature Store Tables
-- Target database: etl_clean (or absa_dw)
--
-- Creates the four model-specific feature store tables that the updated ETL
-- pipeline will populate from the real ABSA banking tables.
-- Grain: customer_number × snapshot_month (monthly batch)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Shared Feature Foundation
-- Populated by: etl/config/extraction_specs/shared_features.yaml
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_store_shared (
    -- Identity
    customer_id             VARCHAR(64)     NOT NULL,
    snapshot_month          DATE            NOT NULL,
    snapshot_date           DATE,
    loaded_at               TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    batch_id                VARCHAR(64)     NOT NULL,

    -- Demographics / profile
    tenure_months           INTEGER,
    sex                     VARCHAR(16),
    geo_region              VARCHAR(64),
    town_or_city            VARCHAR(64),
    country                 VARCHAR(64),
    gross_income            NUMERIC(14,2),
    other_income            NUMERIC(14,2),
    income_proxy            NUMERIC(14,2),
    job_title               VARCHAR(128),
    employment_type         VARCHAR(64),
    employment_status       VARCHAR(64),
    market_segment          VARCHAR(64),
    risk_level              VARCHAR(32),
    risk_score              NUMERIC(10,2),
    credit_rating           VARCHAR(16),
    barclaycard_grade       VARCHAR(16),
    solicitation_channel    VARCHAR(64),
    acquisition_campaign    VARCHAR(32),

    -- Product depth
    num_active_products     INTEGER,
    has_investment          SMALLINT,
    current_count           INTEGER,
    savings_count           INTEGER,
    investment_count        INTEGER,
    secured_count           INTEGER,
    unsecured_count         INTEGER,
    has_mortgage            SMALLINT,

    -- RFM
    recency_days            INTEGER,
    frequency_30d           INTEGER,
    frequency_90d           INTEGER,
    frequency_12m           INTEGER,
    monetary_30d            NUMERIC(18,2),
    monetary_90d            NUMERIC(18,2),
    monetary_12m            NUMERIC(18,2),
    max_transaction_value_12m NUMERIC(18,2),
    active_days_30d         INTEGER,
    active_days_90d         INTEGER,
    avg_transaction_value_12m NUMERIC(18,2),

    -- Cash flow
    credits_30d             NUMERIC(18,2),
    credits_90d             NUMERIC(18,2),
    debits_30d              NUMERIC(18,2),
    debits_90d              NUMERIC(18,2),
    net_cashflow_30d        NUMERIC(18,2),
    net_cashflow_90d        NUMERIC(18,2),
    inbound_vs_outbound_ratio_90d NUMERIC(10,4),

    -- Loan / other bank
    interest_rate           NUMERIC(8,4),
    other_bank_name         VARCHAR(64),
    other_bank_cde          VARCHAR(32),

    PRIMARY KEY (customer_id, snapshot_month)
);

CREATE INDEX IF NOT EXISTS idx_fss_snapshot  ON public.feature_store_shared (snapshot_month);
CREATE INDEX IF NOT EXISTS idx_fss_customer  ON public.feature_store_shared (customer_id);

-- ---------------------------------------------------------------------------
-- CLV Feature Store
-- Populated by: etl/config/extraction_specs/clv_features.yaml
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_store_clv (
    customer_id                 VARCHAR(64)     NOT NULL,
    snapshot_month              DATE            NOT NULL,
    loaded_at                   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    batch_id                    VARCHAR(64)     NOT NULL,

    -- Features
    fee_income_m1               NUMERIC(14,2),
    fee_income_12m              NUMERIC(14,2),
    avg_monthly_fee_12m         NUMERIC(14,2),
    card_spend_12m              NUMERIC(14,2),
    num_products_opened_12m     INTEGER,
    num_products_closed_12m     INTEGER,
    product_net_12m             INTEGER,
    nii_m1                      NUMERIC(14,2),
    avg_monthly_nii_12m         NUMERIC(14,2),

    -- Training labels (NULL in scoring mode)
    target_fee_income_12m       NUMERIC(14,2),
    target_clv_12m              NUMERIC(14,2),
    target_margin_12m           NUMERIC(14,2),

    PRIMARY KEY (customer_id, snapshot_month)
);

CREATE INDEX IF NOT EXISTS idx_fsc_snapshot ON public.feature_store_clv (snapshot_month);

-- ---------------------------------------------------------------------------
-- Churn Feature Store
-- Populated by: etl/config/extraction_specs/churn_features.yaml
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_store_churn (
    customer_id                     VARCHAR(64)     NOT NULL,
    snapshot_month                  DATE            NOT NULL,
    loaded_at                       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    batch_id                        VARCHAR(64)     NOT NULL,

    -- Volume features
    txn_count_30d                   INTEGER,
    txn_count_90d                   INTEGER,
    txn_count_180d                  INTEGER,
    vol_30d                         NUMERIC(18,2),
    vol_90d                         NUMERIC(18,2),
    vol_180d                        NUMERIC(18,2),
    vol_ratio_30_180                NUMERIC(10,4),
    vol_ratio_30_90                 NUMERIC(10,4),
    txn_count_change_pct_90d        NUMERIC(10,4),

    -- Large outflows
    large_outflow_count_30d         INTEGER,
    large_outflow_amount_30d        NUMERIC(18,2),

    -- Dormancy proximity
    days_to_dormancy                INTEGER,
    lifecycle_status_at_snapshot    VARCHAR(32),
    future_txn_count_90d            INTEGER,

    -- Training labels (NULL in scoring mode)
    churn_30d                       SMALLINT,
    churn_90d                       SMALLINT,

    PRIMARY KEY (customer_id, snapshot_month)
);

CREATE INDEX IF NOT EXISTS idx_fsch_snapshot ON public.feature_store_churn (snapshot_month);

-- ---------------------------------------------------------------------------
-- Lifecycle Feature Store
-- Populated by: etl/config/extraction_specs/lifecycle_features.yaml
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_store_lifecycle (
    customer_id                     VARCHAR(64)     NOT NULL,
    snapshot_month                  DATE            NOT NULL,
    loaded_at                       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    batch_id                        VARCHAR(64)     NOT NULL,

    -- Activity pattern features
    salary_flag                     SMALLINT,
    salary_consistency_3m           SMALLINT,
    activity_change_flag            SMALLINT,
    avg_salary_amount               NUMERIC(14,2),
    txn_count_12m                   INTEGER,
    distinct_channels_90d           INTEGER,

    -- No supervised target (unsupervised / heuristic stage)
    lifecycle_stage_label           VARCHAR(32),

    PRIMARY KEY (customer_id, snapshot_month)
);

CREATE INDEX IF NOT EXISTS idx_fsl_snapshot ON public.feature_store_lifecycle (snapshot_month);

-- ---------------------------------------------------------------------------
-- Balance Feature Store
-- Populated by: etl/config/extraction_specs/balance_features.yaml
-- Grain: customer × day (daily as-of)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_store_balance (
    customer_id                     VARCHAR(64)     NOT NULL,
    as_of_date                      DATE            NOT NULL,
    loaded_at                       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    batch_id                        VARCHAR(64)     NOT NULL,

    -- Cash-flow / balance features
    credits_7d                      NUMERIC(18,2),
    debits_7d                       NUMERIC(18,2),
    net_cashflow_7d                 NUMERIC(18,2),
    credits_30d                     NUMERIC(18,2),
    debits_30d                      NUMERIC(18,2),
    net_cashflow_30d                NUMERIC(18,2),
    day_of_month                    INTEGER,
    day_of_week                     INTEGER,
    is_month_end                    SMALLINT,
    is_month_start                  SMALLINT,

    -- Training labels (NULL in scoring mode)
    target_dab_30d                  NUMERIC(18,2),
    target_dab_60d                  NUMERIC(18,2),
    target_dab_90d                  NUMERIC(18,2),

    PRIMARY KEY (customer_id, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_fsb_as_of ON public.feature_store_balance (as_of_date);
