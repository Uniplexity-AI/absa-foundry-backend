-- Feature Store DDL — customer_features table
-- Stores point-in-time feature snapshots for each customer.

CREATE TABLE IF NOT EXISTS public.customer_features (
    id                      BIGSERIAL PRIMARY KEY,
    customer_id             VARCHAR(50) NOT NULL,
    as_of_date              DATE NOT NULL,

    -- Recency / Tenure
    days_since_last_txn     INT,
    days_since_first_txn    INT,

    -- Transaction counts by window
    txn_count_30d           INT,
    txn_count_90d           INT,
    txn_count_180d          INT,

    -- Frequency
    avg_days_between_txn    DOUBLE PRECISION,

    -- Monetary
    total_amount_90d        DOUBLE PRECISION,
    avg_amount_90d          DOUBLE PRECISION,
    total_amount_180d       DOUBLE PRECISION,

    -- Derived
    amount_growth_ratio     DOUBLE PRECISION,

    -- Diversity
    distinct_channels_90d   INT,
    distinct_txn_types_90d  INT,
    dominant_channel        VARCHAR(50),

    -- Volatility
    amount_stddev_90d       DOUBLE PRECISION,

    -- Metadata
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (customer_id, as_of_date)
);

CREATE INDEX idx_customer_features_customer ON customer_features(customer_id);
CREATE INDEX idx_customer_features_date ON customer_features(as_of_date);
CREATE INDEX idx_customer_features_customer_date ON customer_features(customer_id, as_of_date);
