-- ===========================================================================
-- Local Password Authentication for iam.users
-- Applies to: SOURCE database (POSTGRES_DB, e.g. etl_validation)
--
-- Adds local username/password columns so the gateway can verify logins
-- without LDAP. The password is stored as a salted pbkdf2_sha256 hash
-- (see shared/auth/password.py). failed_attempts / locked_until provide a
-- persistent lockout that survives gateway restarts.
--
-- Idempotent — safe to re-run.
-- ===========================================================================

DO $$
BEGIN
    IF to_regclass('iam.users') IS NOT NULL THEN
        ALTER TABLE iam.users
            ADD COLUMN IF NOT EXISTS password_hash    VARCHAR(255),
            ADD COLUMN IF NOT EXISTS must_change_pwd  BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS failed_attempts  INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS locked_until     TIMESTAMPTZ;
    END IF;
END $$;
