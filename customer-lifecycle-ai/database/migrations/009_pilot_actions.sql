-- Migration: Pilot action log + per-customer mutable state
-- Target DB: etl_clean (Decision Intelligence Service :8005 writes it)
--
-- Backs the frontend write buttons (Assign RM / Enrol Campaign / Launch
-- Campaign / Acknowledge alert / NBA Override / Save Action Plan / Record
-- Action). Every click is persisted server-side so it survives reloads and
-- is visible to other pilot viewers — not just localStorage.
--
-- Two tables:
--   pilot_action_log       — append-only audit of every intervention click
--   pilot_customer_state   — latest per-customer mutable state (rm,
--                            enrolled campaigns, acked alerts, override)
--
-- NOTE: synthetic PoC data only. Safe to TRUNCATE before real onboarding.

CREATE TABLE IF NOT EXISTS pilot_action_log (
    id          BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(64)  NOT NULL,
    action_type VARCHAR(48)  NOT NULL,   -- RM_ASSIGNED, CAMPAIGN_ENROLLED,
                                         -- ALERT_ACKNOWLEDGED, NBA_OVERRIDE,
                                         -- CAMPAIGN_LAUNCHED, ACTION_PLAN_CREATED,
                                         -- ACTION_RECORDED, RM_CONTACTED
    detail      TEXT,
    meta        JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor       VARCHAR(128),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pilot_action_log_customer
    ON pilot_action_log (customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pilot_action_log_type
    ON pilot_action_log (action_type);

CREATE TABLE IF NOT EXISTS pilot_customer_state (
    customer_id VARCHAR(64) PRIMARY KEY,
    state       JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
