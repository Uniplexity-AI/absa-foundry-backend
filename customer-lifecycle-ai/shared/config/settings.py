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

    # ---- PostgreSQL ----
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
    jwt_access_token_expire_minutes: int = 30

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
