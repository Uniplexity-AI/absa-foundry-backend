-- ===========================================================================
-- Migration 016: Soft delete for customers
-- Target database: etl_clean
--
-- Deleting a customer is a data-management action, not a row removal. The clean
-- layer is the historical record that the feature store, state engine, audit
-- trail and model metrics are all derived from, so physically removing a
-- customer would:
--
--   * be blocked by six foreign keys onto public.customers_clean (all NO ACTION)
--     — accounts_clean, cards_clean, customer_transactions_clean,
--     demographics_clean, digital_engagement_clean, loans_clean;
--   * silently orphan ten more tables that carry customer_id but have no FK
--     (customer_features, customer_states, decision_outcomes, prediction_log,
--     state_transitions, pilot_customer_state, pilot_action_log, and the three
--     *_rejected tables);
--   * destroy ROI/label history — e.g. the 500 rows in decision_outcomes that
--     exist precisely to measure whether past decisions worked;
--   * remove ~348k transaction rows and 15k feature snapshots that other
--     customers' aggregates were computed against.
--
-- So deletion is modelled as a reversible flag, following the convention this
-- codebase already uses for model_registry / feature_registry /
-- calibration_proposals (is_deleted BOOLEAN DEFAULT false + deleted_at).
--
-- Read paths exclude deleted customers; the rows themselves are retained.
-- Idempotent: safe to re-run.
-- ===========================================================================

DO $$
BEGIN
    IF to_regclass('public.customers_clean') IS NOT NULL THEN
        ALTER TABLE public.customers_clean
            ADD COLUMN IF NOT EXISTS is_deleted      BOOLEAN     NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS deleted_at      TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS deleted_by      VARCHAR(64),
            ADD COLUMN IF NOT EXISTS deleted_reason  VARCHAR(255);
    END IF;
END $$;

-- Every customer-facing read filters deleted customers out with
-- `NOT EXISTS (SELECT 1 FROM customers_clean WHERE customer_id = ... AND is_deleted)`.
-- Deletions should be rare, so index the small side of that lookup.
CREATE INDEX IF NOT EXISTS idx_customers_clean_deleted
    ON public.customers_clean (customer_id)
    WHERE is_deleted;

-- Keeps the "who removed this and when" audit query cheap.
CREATE INDEX IF NOT EXISTS idx_customers_clean_deleted_at
    ON public.customers_clean (deleted_at DESC)
    WHERE is_deleted;

-- Existing rows are all live.
UPDATE public.customers_clean SET is_deleted = false WHERE is_deleted IS NULL;
