-- ===========================================================================
-- Migration 018: CRM Models
-- Target database: etl_clean
-- ===========================================================================

CREATE TABLE IF NOT EXISTS public.next_of_kin (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    relationship VARCHAR(100),
    phone_number VARCHAR(50),
    email VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_next_of_kin_customer_id ON public.next_of_kin(customer_id);

CREATE TABLE IF NOT EXISTS public.engagement_cases (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    case_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    assigned_agent_id VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engagement_cases_customer_id ON public.engagement_cases(customer_id);

CREATE TABLE IF NOT EXISTS public.engagement_interactions (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES public.engagement_cases(id) ON DELETE CASCADE,
    interaction_channel VARCHAR(50) NOT NULL,
    notes TEXT,
    outcome VARCHAR(100),
    cross_sell_details TEXT,
    dormancy_reason VARCHAR(100),
    recommendation TEXT,
    customer_experience VARCHAR(100),
    branch_to_visit VARCHAR(100),
    customer_feedback TEXT,
    interaction_date TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engagement_interactions_case_id ON public.engagement_interactions(case_id);

CREATE TABLE IF NOT EXISTS public.promises (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES public.engagement_cases(id) ON DELETE CASCADE,
    promise_type VARCHAR(50) NOT NULL,
    promise_date TIMESTAMPTZ NOT NULL,
    amount NUMERIC(10, 2),
    is_fulfilled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_promises_case_id ON public.promises(case_id);
