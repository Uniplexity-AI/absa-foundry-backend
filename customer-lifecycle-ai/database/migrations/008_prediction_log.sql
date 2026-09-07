-- Migration: prediction_log — real per-prediction telemetry (Phase B)
-- Target DB: etl_clean
--
-- Written best-effort by prediction-service on every per-customer scoring
-- call. Joined later with customer_states transitions to CHURNED (90-day
-- horizon) to realize outcome labels → true confusion matrix, per-segment
-- AUC, precision/recall over time. Replaces the simulated monitoring data.

CREATE TABLE IF NOT EXISTS prediction_log (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    as_of_date DATE NOT NULL,
    model_id VARCHAR(64) NOT NULL,
    model_version VARCHAR(64),
    churn_probability DOUBLE PRECISION NOT NULL,
    predicted_class VARCHAR(16) NOT NULL,
    latency_ms DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_predlog_customer ON prediction_log(customer_id, as_of_date);
CREATE INDEX IF NOT EXISTS idx_predlog_created ON prediction_log(created_at);
