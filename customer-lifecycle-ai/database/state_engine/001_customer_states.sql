-- ===========================================================================
-- Customer State Engine DDL — Layer 1 (Behaviour Intelligence)
-- ===========================================================================
-- Database: etl_clean (co-located with customer_features from Feature Engine)
-- Purpose:  Stores customer lifecycle states and state transitions.
--           Layer 1 writes state + classification_rules.
--           Layer 2 (Prediction Service) backfills health_score + component_scores.
--
-- Usage:
--   psql -h <host> -U postgres -d etl_clean -f database/state_engine/001_customer_states.sql
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. customer_states — One row per customer per as_of_date
-- ---------------------------------------------------------------------------
-- Idempotent by design: ON CONFLICT (customer_id, as_of_date) DO UPDATE
-- ensures re-running /states/compute on the same date updates in-place.
--
-- Columns owned by Layer 1: state, classification_rules, computed_at
-- Columns owned by Layer 2: health_score, component_scores (backfilled later)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.customer_states (
    -- Identity
    id              BIGSERIAL PRIMARY KEY,
    customer_id     VARCHAR(64) NOT NULL,
    as_of_date      DATE NOT NULL,

    -- === Layer 1: State classification ===
    -- 6-state Absa lifecycle: NEW → ACTIVE → GROWING → AT_RISK → DORMANT → CHURNED
    state           VARCHAR(16) NOT NULL
                    CHECK (state IN ('NEW', 'ACTIVE', 'GROWING', 'AT_RISK', 'DORMANT', 'CHURNED')),

    -- Which rules fired during classification (JSONB — extensible)
    -- Example: {"risk_rules": ["30d_inactivity", "engagement_drop"], "active_rules": []}
    classification_rules JSONB DEFAULT '{}',

    -- === Layer 2: Health Score (Prediction Service) ===
    -- Written as NULL by Layer 1. Layer 2 backfills after computing churn_prob.
    -- NULL means "not yet scored" — consumers must handle this.
    health_score    NUMERIC(5,2) CHECK (health_score IS NULL OR (health_score >= 0 AND health_score <= 100)),

    -- Component sub-scores that feed into health_score
    -- Example: {"churn_risk_sub": 72.5, "clv_percentile_sub": 85.0, "behaviour_sub": 63.0}
    component_scores JSONB DEFAULT '{}',

    -- === Metadata ===
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Idempotency contract
    UNIQUE (customer_id, as_of_date)
);

-- Indexes: query patterns from API routes
CREATE INDEX IF NOT EXISTS idx_customer_states_customer
    ON customer_states(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_states_date
    ON customer_states(as_of_date);
CREATE INDEX IF NOT EXISTS idx_customer_states_state
    ON customer_states(state);
-- Partial index: only rows where Layer 2 (Prediction Service) has backfilled.
-- Avoids wasting index space on NULLs — every row starts NULL until Layer 2 runs.
CREATE INDEX IF NOT EXISTS idx_customer_states_health
    ON customer_states(health_score DESC) WHERE health_score IS NOT NULL;
-- Composite index for "latest state per customer" queries
CREATE INDEX IF NOT EXISTS idx_customer_states_customer_date
    ON customer_states(customer_id, as_of_date DESC);


-- ---------------------------------------------------------------------------
-- Migration guard: tables created before v2.0 carry a 4-state CHECK constraint
-- (missing NEW/GROWING). Drop it and re-add the full 6-state constraint.
-- Idempotent — safe to re-run.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    con_name text;
BEGIN
    SELECT conname INTO con_name
    FROM pg_constraint
    WHERE conrelid = 'public.customer_states'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%state%';
    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.customer_states DROP CONSTRAINT %I', con_name);
    END IF;
    ALTER TABLE public.customer_states
        ADD CONSTRAINT customer_states_state_check
        CHECK (state IN ('NEW', 'ACTIVE', 'GROWING', 'AT_RISK', 'DORMANT', 'CHURNED'));
END $$;


-- ---------------------------------------------------------------------------
-- 2. state_transitions — One row per state change per customer
-- ---------------------------------------------------------------------------
-- Written by TransitionAnalyzer when it detects a state change between
-- two consecutive as_of_date snapshots. Powers the Markov transition matrix
-- and the State Timeline UI component (FR-CUST-03).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.state_transitions (
    id                      BIGSERIAL PRIMARY KEY,
    customer_id             VARCHAR(64) NOT NULL,
    from_state              VARCHAR(16) NOT NULL,
    to_state                VARCHAR(16) NOT NULL,
    transition_date         DATE NOT NULL,

    -- How long the customer stayed in the previous state
    days_in_previous_state  INTEGER,

    -- Human-readable trigger (e.g. "30d inactivity threshold crossed (days_since_last_txn=45)")
    trigger_reason          VARCHAR(256),

    -- Feature snapshot at the moment of transition (for audit / debugging)
    -- Example: {"days_since_last_txn": 45, "engagement_score": 12.5, "risk_dormant_indicator": true}
    feature_snapshot        JSONB DEFAULT '{}',

    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Query: "show all transitions for customer X"
CREATE INDEX IF NOT EXISTS idx_state_transitions_customer
    ON state_transitions(customer_id, transition_date);

-- Query: "aggregate transition counts for Markov matrix"
CREATE INDEX IF NOT EXISTS idx_state_transitions_matrix
    ON state_transitions(from_state, to_state, transition_date);


-- ---------------------------------------------------------------------------
-- 3. Relationships — how these tables connect to the rest of the system
-- ---------------------------------------------------------------------------

-- customer_states.customer_id  ──→  customer_features.customer_id (Feature Engine)
--   Both tables use the same customer_id format (CUST#####) and live in
--   the same database (etl_clean). No cross-DB joins needed.
--
--   The state engine reads customer_features to classify, then writes
--   customer_states. The Timeline UI joins customer_states + state_transitions
--   on customer_id.

-- customer_states.as_of_date  ──→  customer_features.as_of_date (Feature Engine)
--   Same point-in-time contract: both tables have one row per customer per date.
--   State for as_of_date=2026-07-29 uses features for the same date.

-- state_transitions.from_state / to_state  ──→  customer_states.state
--   The Markov engine aggregates state_transitions grouped by (from_state, to_state)
--   to build the 4×4 probability matrix. No FK constraint (avoid cascade issues
--   if a customer_states row is re-computed).


-- ---------------------------------------------------------------------------
-- 4. Sample queries (for developer reference)
-- ---------------------------------------------------------------------------

-- Get state for a single customer:
--   SELECT state, health_score, classification_rules, computed_at
--   FROM customer_states
--   WHERE customer_id = 'CUST00001' AND as_of_date = '2026-07-29';

-- Get timeline (states + transitions) for a customer:
--   SELECT s.as_of_date, s.state, t.from_state, t.to_state, t.trigger_reason
--   FROM customer_states s
--   LEFT JOIN state_transitions t
--     ON s.customer_id = t.customer_id AND s.as_of_date = t.transition_date
--   WHERE s.customer_id = 'CUST00001'
--   ORDER BY s.as_of_date DESC;

-- Build Markov transition matrix (180-day window):
--   SELECT from_state, to_state, COUNT(*) AS transition_count
--   FROM state_transitions
--   WHERE transition_date > (CURRENT_DATE - INTERVAL '180 days')
--   GROUP BY from_state, to_state;

-- Portfolio summary by state:
--   SELECT state, COUNT(*) AS customers, AVG(health_score) AS avg_health
--   FROM customer_states
--   WHERE as_of_date = '2026-07-29'
--   GROUP BY state
--   ORDER BY COUNT(*) DESC;
