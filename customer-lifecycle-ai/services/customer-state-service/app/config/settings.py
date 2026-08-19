"""Customer State Service — Configuration (Environment Variables).

Mirrors FeatureConfig pattern from feature-engineering-service.
All thresholds env-prefixed with CS_.
"""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class StateConfig(BaseSettings):
    """State classification thresholds. Env-prefixed CS_. Mirrors FeatureConfig pattern."""

    model_config = SettingsConfigDict(env_prefix="CS_", extra="ignore")

    # ---- State classification thresholds ----
    churned_days_threshold: int = 365
    dormant_days_threshold: int = 90
    atrisk_days_min: int = 30
    atrisk_days_max: int = 90
    dormant_txn_count_threshold: int = 0
    engagement_dormant_threshold: float = 10.0
    engagement_atrisk_max: float = 20.0

    # ---- NEW / GROWING / hysteresis thresholds ----
    new_tenure_days: int = 90            # tenure <= this -> NEW state
    growing_balance_growth_pct: float = 15.0  # balance growth > this -> GROWING
    dormant_zero_txn_min_days: int = 30  # zero-txn DORMANT requires days > this
    hysteresis_min_txn_30d: int = 2      # DORMANT->ACTIVE requires >= this many txns

    # ---- Markov Chain ----
    markov_window_days: int = 180
    markov_min_transitions: int = 50

    # ---- Journey Analysis ----
    journey_top_paths: int = 5


class Settings(BaseSettings):
    """Service settings. Mirrors Feature Engineering Settings pattern."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    environment: str = "development"
    log_level: str = "INFO"
    service_port: int = 8003
    state: StateConfig = StateConfig()