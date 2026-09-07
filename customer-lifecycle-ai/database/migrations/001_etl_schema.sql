-- ===========================================================================
-- ETL Schema Migration — 001_etl_schema.sql
-- Target database: etl_clean (the clean/transformed database)
--
-- Creates the `etl` schema and the audit/validation tables that the ETL
-- pipeline (run_etl.py) and the API gateway read/write.
--
-- Run against etl_clean only. The raw data tables live in etl_validation.
-- ===========================================================================

-- pgcrypto provides gen_random_uuid() used by the iam schema.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS etl;

-- ===========================================================================
-- etl_audit — immutable audit trail, one record per pipeline batch.
-- Mirrors etl/models/audit_models.py (AuditRecord) plus the columns that
-- run_etl.py writes via its INSERT statement.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS etl.etl_audit (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    audit_id             VARCHAR(64)  UNIQUE NOT NULL,
    batch_id             VARCHAR(64)  NOT NULL,
    source_type          VARCHAR(64)  NOT NULL,
    source_name          VARCHAR(255) NOT NULL,
    pipeline_name        VARCHAR(255) NOT NULL,
    started_at           TIMESTAMPTZ  NOT NULL,
    completed_at         TIMESTAMPTZ,
    duration_seconds     FLOAT,
    rows_received        BIGINT       NOT NULL DEFAULT 0,
    rows_valid           BIGINT       NOT NULL DEFAULT 0,
    rows_rejected        BIGINT       NOT NULL DEFAULT 0,
    rows_loaded          BIGINT       NOT NULL DEFAULT 0,
    rows_skipped         BIGINT       NOT NULL DEFAULT 0,
    duplicates_detected  BIGINT       NOT NULL DEFAULT 0,
    warnings_count       BIGINT       NOT NULL DEFAULT 0,
    errors_count         BIGINT       NOT NULL DEFAULT 0,
    quality_score        FLOAT        NOT NULL DEFAULT 100.0,
    status               VARCHAR(32)  NOT NULL DEFAULT 'COMPLETED',
    error_message        TEXT,
    triggered_by         VARCHAR(255) NOT NULL DEFAULT 'system',
    operator_id          VARCHAR(128),
    tags                 JSONB,
    extra                JSONB,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_etl_audit_batch      ON etl.etl_audit (batch_id);
CREATE INDEX IF NOT EXISTS idx_etl_audit_completed  ON etl.etl_audit (completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_etl_audit_status     ON etl.etl_audit (status);

-- ===========================================================================
-- etl_validation_run — aggregate validation result per batch.
-- Mirrors etl/models/validation_models.py (ValidationRun).
-- ===========================================================================
CREATE TABLE IF NOT EXISTS etl.etl_validation_run (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id            VARCHAR(64) UNIQUE NOT NULL,
    batch_id          VARCHAR(64) NOT NULL,
    status            VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    total_records     BIGINT NOT NULL DEFAULT 0,
    valid_records     BIGINT NOT NULL DEFAULT 0,
    invalid_records   BIGINT NOT NULL DEFAULT 0,
    duplicate_records BIGINT NOT NULL DEFAULT 0,
    total_errors      BIGINT NOT NULL DEFAULT 0,
    total_warnings    BIGINT NOT NULL DEFAULT 0,
    quality_score     FLOAT  NOT NULL DEFAULT 100.0,
    error_by_category JSONB,
    error_by_rule     JSONB,
    config_snapshot   JSONB,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at      TIMESTAMPTZ,
    duration_seconds  FLOAT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_etl_validation_run_batch ON etl.etl_validation_run (batch_id);
CREATE INDEX IF NOT EXISTS idx_etl_validation_run_run   ON etl.etl_validation_run (run_id);

-- ===========================================================================
-- etl_validation_error — per-record validation error detail.
-- Mirrors etl/models/validation_models.py (ValidationErrorRecord).
-- ===========================================================================
CREATE TABLE IF NOT EXISTS etl.etl_validation_error (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id         VARCHAR(64) NOT NULL,
    batch_id       VARCHAR(64) NOT NULL,
    rule_id        VARCHAR(64) NOT NULL,
    category       VARCHAR(32) NOT NULL,
    severity       VARCHAR(16) NOT NULL DEFAULT 'ERROR',
    field_name     VARCHAR(128),
    message        TEXT NOT NULL,
    record_index   INTEGER NOT NULL DEFAULT 0,
    actual_value   TEXT,
    expected_value TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_etl_validation_error_batch ON etl.etl_validation_error (batch_id);
CREATE INDEX IF NOT EXISTS idx_etl_validation_error_rule  ON etl.etl_validation_error (rule_id);
CREATE INDEX IF NOT EXISTS idx_etl_validation_error_run   ON etl.etl_validation_error (run_id);
