-- Model Management Schema for MLOps Control Plane
-- Applied to the target database

CREATE TABLE IF NOT EXISTS model_registry (
    id UUID PRIMARY KEY,
    model_family VARCHAR(255) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    algorithm VARCHAR(100) NOT NULL,
    training_dataset_version VARCHAR(100) NOT NULL,
    feature_set_version VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    optimal_threshold FLOAT,
    hyperparameters JSONB,
    evaluation_metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by VARCHAR(255),
    updated_by VARCHAR(255),
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS feature_registry (
    id UUID PRIMARY KEY,
    feature_name VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL,
    missing_rate FLOAT DEFAULT 0.0 NOT NULL,
    importance_score FLOAT DEFAULT 0.0 NOT NULL,
    allowed_for_training BOOLEAN DEFAULT TRUE NOT NULL,
    allowed_for_simulation BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by VARCHAR(255),
    updated_by VARCHAR(255),
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS calibration_proposals (
    id UUID PRIMARY KEY,
    model_id UUID NOT NULL REFERENCES model_registry(id),
    proposed_threshold FLOAT NOT NULL,
    metrics_snapshot JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by VARCHAR(255),
    updated_by VARCHAR(255),
    approved_by VARCHAR(255),
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    action VARCHAR(255) NOT NULL,
    model_id UUID REFERENCES model_registry(id),
    previous_state JSONB,
    new_state JSONB,
    reason TEXT
);

-- Seed basic features to the feature_registry for testing
INSERT INTO feature_registry (id, feature_name, display_name, data_type, category)
VALUES 
    (gen_random_uuid(), 'savings_balance', 'Savings Balance', 'numeric', 'financial'),
    (gen_random_uuid(), 'days_since_last_txn', 'Days Since Last Transaction', 'numeric', 'engagement'),
    (gen_random_uuid(), 'mobile_app_logins', 'Mobile App Logins', 'numeric', 'engagement')
ON CONFLICT (feature_name) DO NOTHING;
