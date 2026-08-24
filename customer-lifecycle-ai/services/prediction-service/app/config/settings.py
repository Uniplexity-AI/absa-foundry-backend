"""Prediction Service — Configuration (Environment Variables).

Mirrors FeatureConfig + StateConfig patterns.
All thresholds env-prefixed with PRED_.
"""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class PredictionConfig(BaseSettings):
    """Prediction thresholds and model paths. Env-prefixed PRED_.

    Mirrors FeatureConfig (FE_) and StateConfig (CS_).
    """

    model_config = SettingsConfigDict(env_prefix="PRED_", extra="ignore")

    # ---- Model ----
    model_type: str = "xgboost"          # xgboost | lightgbm
    churn_model_path: str = "models/champion/churn/xgboost_churn_v1.json"
    clv_model_path: str = ""              # POST-POC: switch to trained regressor file
                                          # Empty string = use percentile-rank (PoC default).
                                          # Service boot skips CLV model loading if path is empty.
    churn_threshold: float = 0.5         # default classification cutoff

    # ---- Health Score weights — read from shared config (single source of truth) ----
    # Shared config defaults: health_score_churn_weight=0.40,
    # health_score_clv_weight=0.30, health_score_behaviour_weight=0.30
    # These PRED_* overrides allow per-service tuning without changing shared defaults.
    health_churn_weight: float = 0.40
    health_clv_weight: float = 0.30
    health_behaviour_weight: float = 0.30

    # ---- Champion/Challenger (post-PoC) ----
    champion_challenger_enabled: bool = False
    challenger_traffic_split: float = 0.10

    # ---- Batch processing ----
    batch_chunk_size: int = 1000  # customers per chunk — bounds memory usage

    # ---- Feature snapshot cache ----
    feature_cache_ttl_seconds: int = 300  # cache features + CLV percentiles per as_of_date


class Settings(BaseSettings):
    """Service settings. Mirrors Feature Engineering Settings pattern."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    environment: str = "development"
    log_level: str = "INFO"
    service_port: int = 8004
    prediction: PredictionConfig = PredictionConfig()
