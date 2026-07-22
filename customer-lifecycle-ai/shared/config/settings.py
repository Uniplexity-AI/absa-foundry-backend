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


# Singleton instance — import this everywhere
settings = Settings()
