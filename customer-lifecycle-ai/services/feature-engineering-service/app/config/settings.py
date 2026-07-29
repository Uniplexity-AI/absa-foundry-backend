"""Feature Engineering Service — Configuration (Environment Variables)."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureConfig(BaseSettings):
    """Configurable feature engineering parameters with sensible banking defaults.

    Override via environment variables: FE_ENGAGEMENT_RECENCY_WEIGHT=50, etc.
    """
    model_config = SettingsConfigDict(env_prefix="FE_", extra="ignore")

    # Engagement score weights (must sum sensibly but aren't enforced)
    engagement_recency_weight: float = 40.0
    engagement_frequency_weight: float = 35.0
    engagement_diversity_weight: float = 25.0
    engagement_max_recency_days: int = 90
    engagement_max_frequency_txn: int = 30
    engagement_max_diversity_channels: int = 5
    engagement_max_diversity_types: int = 5

    # Activity windows
    activity_consistency_window_days: int = 90
    inactive_days_window: int = 90

    # Channel names (configurable per bank's channel taxonomy)
    channel_mobile: str = "MOBILE"
    channel_atm: str = "ATM"
    channel_branch: str = "BRANCH"
    channel_online: str = "ONLINE"
    channel_internet: str = "INTERNET"

    # Risk thresholds
    risk_high_value_threshold: float = 10000.0
    risk_dormant_days: int = 90

    # Financial thresholds
    financial_salary_min_amount: float = 500.0
    financial_income_window_days: int = 90


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    environment: str = "development"
    log_level: str = "INFO"
    service_port: int = 8002
    features: FeatureConfig = FeatureConfig()
