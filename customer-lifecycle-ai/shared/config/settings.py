"""
Shared Configuration Settings — Global settings used across all services.

Reads from environment variables via pydantic-settings.
All services import from this single source of truth.

TODO:
Add service-specific settings classes that extend these base settings.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Environment ----
    environment: str = "development"
    log_level: str = "INFO"

    # ---- PostgreSQL (Source — raw/validation data) ----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "customer_lifecycle"
    postgres_user: str = "clp_user"
    postgres_password: str = "clp_password"

    @property
    def database_url(self) -> str:
        """Construct the async database URL from components."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Construct the sync database URL (for Alembic migrations)."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---- PostgreSQL Target (ETL clean/transformed data) ----
    postgres_target_host: str = "localhost"
    postgres_target_port: int = 5432
    postgres_target_db: str = "etl_clean"
    postgres_target_user: str = "postgres"
    postgres_target_password: str = ""

    @property
    def database_target_url(self) -> str:
        """Construct the async target database URL (ETL output)."""
        return (
            f"postgresql+asyncpg://{self.postgres_target_user}:{self.postgres_target_password}"
            f"@{self.postgres_target_host}:{self.postgres_target_port}/{self.postgres_target_db}"
        )

    @property
    def database_target_url_sync(self) -> str:
        """Construct the sync target database URL."""
        return (
            f"postgresql://{self.postgres_target_user}:{self.postgres_target_password}"
            f"@{self.postgres_target_host}:{self.postgres_target_port}/{self.postgres_target_db}"
        )

    # ---- Redis ----
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # ---- Pool Configuration ----
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600

    # ---- API Gateway ----
    gateway_port: int = 8080
    gateway_secret_key: str = "change-me-in-production"

    # ---- JWT / Auth ----
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # ---- LDAP / Active Directory ----
    ldap_enabled: bool = False
    ldap_server: str = "ldap://ad.absa.co.zm:389"
    ldap_base_dn: str = "DC=absa,DC=co,DC=zm"
    ldap_user_dn_template: str = "CN={username},OU=Users,DC=absa,DC=co,DC=zm"
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_search_filter: str = "(sAMAccountName={username})"
    ldap_timeout_seconds: int = 10
    ldap_tls_enabled: bool = False  # Enforce StartTLS in production

    # ---- Security Hardening ----
    lockout_max_attempts: int = 5
    lockout_duration_minutes: int = 15
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_digit: bool = True

    # ---- Health Score ----
    health_score_churn_weight: float = 0.40
    health_score_clv_weight: float = 0.30
    health_score_behaviour_weight: float = 0.30

    # ---- Champion/Challenger ----
    champion_challenger_enabled: bool = True
    challenger_traffic_split: float = 0.10

    # ---- Security ----
    encryption_enabled: bool = False
    audit_logging_enabled: bool = True

    # ---- Schema Mapping — change these when Absa provides a different dataset ----
    # Table names: logical → actual. Update the RHS only.
    table_customer_features: str = "customer_features"
    table_customer_states: str = "customer_states"
    table_transactions_clean: str = "customer_transactions_clean"
    table_accounts_clean: str = "accounts_clean"
    table_cards_clean: str = "cards_clean"
    table_loans_clean: str = "loans_clean"
    table_digital_engagement: str = "digital_engagement_clean"

    # Column names: logical → actual. Update the RHS only.
    col_customer_id: str = "customer_id"
    col_as_of_date: str = "as_of_date"
    col_transaction_date: str = "transaction_date"
    col_channel: str = "channel"
    col_transaction_type: str = "transaction_type"
    col_customer_status: str = "rel_customer_status"   # used for churn label
    col_engagement_score: str = "engagement_score"
    col_total_amount_90d: str = "total_amount_90d"
    col_txn_count_90d: str = "txn_count_90d"

    # Churn label definition
    label_churn_column: str = "rel_customer_status"     # column that defines churn
    label_churn_positive_value: str = "Closed"           # value meaning "churned"

    # Training pipeline
    training_dates: str = "2026-07-17,2026-07-22"       # comma-separated
    training_holdout_date: str = "2026-07-27"

    @property
    def training_date_list(self) -> list[str]:
        return [d.strip() for d in self.training_dates.split(",") if d.strip()]

    def validate_schema_mappings(self, conn=None) -> list[str]:
        """Validate schema mappings — config-level always, DB-level if conn provided.

        Args:
            conn: Optional psycopg2 connection. If provided, verifies that
                  configured tables and columns actually exist in the database.

        Returns:
            List of warning strings (empty = all good).
        """
        warnings = []

        # ── Config-level: check critical values are set ──
        required = [
            ("table_customer_features", self.table_customer_features),
            ("table_transactions_clean", self.table_transactions_clean),
            ("col_transaction_date", self.col_transaction_date),
            ("col_customer_status", self.col_customer_status),
            ("label_churn_column", self.label_churn_column),
        ]
        for name, value in required:
            if not value:
                warnings.append(f"shared.config: {name} is empty — schema mapping incomplete")

        # ── DB-level: verify tables and columns exist ──
        if conn is not None:
            warnings.extend(self._validate_db_schema(conn))

        return warnings

    def _validate_db_schema(self, conn) -> list[str]:
        """Verify configured tables and columns exist in the database."""
        import psycopg2
        warnings = []

        # Collect all table→column mappings to verify
        checks: dict[str, list[str]] = {}

        def _add(table_attr: str, *col_attrs: str):
            table = getattr(self, table_attr, "")
            if not table:
                return
            cols = [getattr(self, c, "") for c in col_attrs]
            cols = [c for c in cols if c]  # skip empty
            if table not in checks:
                checks[table] = []
            checks[table].extend(cols)

        _add("table_customer_features", "col_customer_id", "col_as_of_date",
             "col_customer_status", "col_engagement_score", "col_txn_count_90d",
             "col_total_amount_90d")
        _add("table_customer_states", "col_customer_id", "col_as_of_date")
        _add("table_transactions_clean", "col_customer_id", "col_transaction_date",
             "col_channel", "col_transaction_type")

        try:
            cur = conn.cursor()
            for table, columns in checks.items():
                # Check table exists
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = %s AND table_schema = 'public')",
                    (table,),
                )
                if not cur.fetchone()[0]:
                    warnings.append(f"DB: table '{table}' not found in public schema")
                    continue

                # Check columns exist
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s AND table_schema = 'public'",
                    (table,),
                )
                existing = {row[0] for row in cur.fetchall()}
                for col in set(columns):  # deduplicate
                    if col not in existing:
                        warnings.append(
                            f"DB: column '{col}' not found in table '{table}'"
                        )
        except psycopg2.Error as e:
            warnings.append(f"DB: schema validation query failed: {e}")
        finally:
            cur.close()

        return warnings


# Singleton instance — import this everywhere
settings = Settings()
