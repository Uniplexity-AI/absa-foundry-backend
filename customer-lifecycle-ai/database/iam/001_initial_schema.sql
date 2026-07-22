-- ===========================================================================
-- IAM Schema — Identity & Access Management
-- Users, roles, service accounts, API keys, refresh tokens, audit trail
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS iam;

-- ===========================================================================
-- Users
-- ===========================================================================

CREATE TABLE iam.users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(100) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    dn              VARCHAR(500) UNIQUE NOT NULL,
    department      VARCHAR(100),
    branch_code     VARCHAR(20),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by      UUID REFERENCES iam.users(user_id)
);

CREATE INDEX idx_users_username ON iam.users(username);
CREATE INDEX idx_users_branch ON iam.users(branch_code);

-- ===========================================================================
-- Roles
-- ===========================================================================

CREATE TABLE iam.roles (
    role_id         SERIAL PRIMARY KEY,
    role_name       VARCHAR(50) UNIQUE NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed default roles
INSERT INTO iam.roles (role_name, description) VALUES
    ('ADMIN',                'Full system access — user management, configuration, model deployment'),
    ('RELATIONSHIP_MANAGER', 'Dashboard with NBA for assigned customers'),
    ('BRANCH_MANAGER',       'Portfolio-level analytics across branch'),
    ('DATA_SCIENTIST',       'Model training, evaluation, champion/challenger testing'),
    ('OPERATIONS',           'System monitoring, pipeline orchestration, read-only dashboards'),
    ('SERVICE_ACCOUNT',      'Machine-to-machine — ETL engine, prediction service, internal APIs');

-- ===========================================================================
-- User ↔ Role mapping
-- ===========================================================================

CREATE TABLE iam.user_roles (
    user_id         UUID REFERENCES iam.users(user_id) ON DELETE CASCADE,
    role_id         INT REFERENCES iam.roles(role_id) ON DELETE CASCADE,
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    granted_by      UUID REFERENCES iam.users(user_id),
    PRIMARY KEY (user_id, role_id)
);

-- ===========================================================================
-- Service Accounts
-- ===========================================================================

CREATE TABLE iam.service_accounts (
    service_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    VARCHAR(100) UNIQUE NOT NULL,
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by      UUID REFERENCES iam.users(user_id)
);

-- ===========================================================================
-- API Keys
-- ===========================================================================

CREATE TABLE iam.api_keys (
    key_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id      UUID REFERENCES iam.service_accounts(service_id) ON DELETE CASCADE,
    api_key_hash    VARCHAR(128) NOT NULL,
    key_prefix      VARCHAR(50) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    scopes          TEXT[] NOT NULL DEFAULT '{}',
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by      UUID REFERENCES iam.users(user_id)
);

CREATE INDEX idx_api_keys_service ON iam.api_keys(service_id);
CREATE INDEX idx_api_keys_hash ON iam.api_keys(api_key_hash);

-- ===========================================================================
-- Refresh Tokens
-- ===========================================================================

CREATE TABLE iam.refresh_tokens (
    token_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES iam.users(user_id) ON DELETE CASCADE,
    token_hash      VARCHAR(128) UNIQUE NOT NULL,
    device_info     VARCHAR(500),
    ip_address      INET,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_refresh_tokens_user ON iam.refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_hash ON iam.refresh_tokens(token_hash);

-- ===========================================================================
-- Auth Audit Trail
-- ===========================================================================

CREATE TABLE iam.auth_audit (
    audit_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES iam.users(user_id),
    service_id      UUID REFERENCES iam.service_accounts(service_id),
    event_type      VARCHAR(50) NOT NULL,
    ip_address      INET,
    user_agent      VARCHAR(500),
    details         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_auth_audit_user ON iam.auth_audit(user_id);
CREATE INDEX idx_auth_audit_event ON iam.auth_audit(event_type, created_at);
