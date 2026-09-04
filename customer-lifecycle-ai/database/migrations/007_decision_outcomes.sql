-- Migration: decision_outcomes table for the Business Outcomes & ROI Tracker
-- Target DB: etl_clean (Decision Intelligence Service :8005 reads it)
--
-- Tracks every retention intervention: what was offered, what it cost,
-- whether the customer accepted, and how much revenue was protected.
-- The business-outcomes endpoint aggregates ROI from these rows.
--
-- NOTE: this table's SCHEMA is the production design (per the frontend
-- contract). The rows currently in it are SYNTHETIC seed data used only
-- to validate the design in the pilot sandbox. Before real pilot
-- onboarding: TRUNCATE decision_outcomes; and do not run the seed script
-- against any environment holding actual customer data.

CREATE TABLE IF NOT EXISTS decision_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id VARCHAR(64) NOT NULL,
    intervention_type VARCHAR(64) NOT NULL,          -- e.g. FEE_WAIVER, RM_CALL, RATE_TOPUP
    channel VARCHAR(32) NOT NULL DEFAULT 'RM_CALL',  -- DIGITAL, RM_CALL, RM_DIRECT, MARKETING
    branch_id VARCHAR(64),                           -- from customer_features.prof_primary_branch
    is_pilot_branch BOOLEAN NOT NULL DEFAULT FALSE,  -- pilot vs control group flag
    cost_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    accepted_flag BOOLEAN NOT NULL DEFAULT FALSE,
    retained_90d BOOLEAN,                            -- still active 90 days post-intervention (nullable = pending)
    clv_score DECIMAL(12, 2),                        -- CLV estimate at intervention time
    revenue_protected_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outcomes_customer ON decision_outcomes(customer_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_created ON decision_outcomes(created_at);
CREATE INDEX IF NOT EXISTS idx_outcomes_branch ON decision_outcomes(branch_id);
