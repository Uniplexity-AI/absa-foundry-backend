"""
ETL Configuration - Centralized, environment-based configuration service.

Loads all ETL settings from environment variables and YAML config files.
Nothing is hardcoded — all rules, thresholds, and settings are configurable.

Categories:
- Validation rules (mandatory fields, accepted values)
- Channel definitions, currency codes
- Thresholds (duplicate similarity, quality score)
- Retry policies
- Pipeline scheduling
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from etl.schemas.audit_schemas import AuditConfig
from etl.schemas.checkpoint_schemas import CheckpointConfig
from etl.schemas.landing_schemas import LandingZoneConfig
from etl.schemas.loading_schemas import LoadPipelineConfig
from etl.schemas.logging_schemas import LoggingConfig
from etl.schemas.monitoring_schemas import MonitoringConfig
from etl.schemas.orchestration_schemas import PipelineDefinition, default_etl_pipeline
from etl.schemas.staging_schemas import StagingConfig
from etl.schemas.transformation_schemas import TransformationConfig
from etl.schemas.validation_schemas import ValidationConfig


class ETLConfig:
    """Centralized ETL configuration loaded from env vars and YAML.

    Usage:
        config = ETLConfig.load()
        validation_cfg = config.validation
        transformation_cfg = config.transformation

    Environment variables override YAML values. All configs have
    sensible defaults for banking use cases.
    """

    def __init__(self) -> None:
        # Infrastructure
        self.landing = LandingZoneConfig(
            base_path=os.getenv("ETL_LANDING_BASE_PATH", "/data/landing"),
        )
        self.staging = StagingConfig()
        self.checkpoint = CheckpointConfig()
        self.logging = LoggingConfig()

        # Pipeline
        self.audit = AuditConfig()
        self.monitoring = MonitoringConfig()
        self.loading = LoadPipelineConfig()
        self.orchestration_pipeline: PipelineDefinition = default_etl_pipeline()

        # Domain-specific
        self.validation = ValidationConfig()
        self.transformation = TransformationConfig()

        # Schema drift detection
        self.schema_mode: str = "strict"
        self.expected_columns: list[str] = [
            "customer_id", "account_id", "branch_code",
            "transaction_date", "transaction_type", "channel",
            "currency", "amount", "data_issue",
        ]

        # Override from env
        self._load_from_env()

    @classmethod
    def load(cls, config_path: str | None = None) -> ETLConfig:
        """Load configuration from YAML file and environment.

        Args:
            config_path: Optional path to YAML config file.

        Returns:
            Fully configured ETLConfig.
        """
        config = cls()

        if config_path:
            with open(config_path) as f:
                data = yaml.safe_load(f)
            config._load_from_dict(data)

        return config

    @classmethod
    def load_from_env(cls) -> ETLConfig:
        """Load configuration from environment variables only.

        Returns:
            ETLConfig with env-based overrides.
        """
        return cls()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load_from_env(self) -> None:
        """Override config values from environment variables."""
        env_map = {
            "ETL_LANDING_BASE_PATH": ("landing", "base_path"),
            "ETL_STAGING_BATCH_SIZE": ("staging", "batch_size"),
            "ETL_VALIDATION_ENABLED": ("validation", "enabled"),
            "ETL_MONITORING_ENABLED": ("monitoring", "enabled"),
            "ETL_LOGGING_LEVEL": ("logging", "default_level"),
            "ETL_AUDIT_RETENTION_YEARS": ("audit", "retention_years"),
        }
        for env_var, (obj_name, attr) in env_map.items():
            value = os.getenv(env_var)
            if value is not None:
                obj = getattr(self, obj_name)
                # Convert types
                if isinstance(getattr(obj, attr), bool):
                    value = value.lower() in ("true", "1", "yes")  # type: ignore[assignment]
                elif isinstance(getattr(obj, attr), int):
                    value = int(value)  # type: ignore[assignment]
                elif isinstance(getattr(obj, attr), float):
                    value = float(value)  # type: ignore[assignment]
                setattr(obj, attr, value)  # type: ignore[arg-type]

    def _load_from_dict(self, data: dict[str, Any]) -> None:
        """Override config values from a YAML dict.

        Args:
            data: Parsed YAML configuration dictionary.
        """
        if "landing" in data:
            for k, v in data["landing"].items():
                if hasattr(self.landing, k):
                    setattr(self.landing, k, v)
        if "validation" in data:
            for k, v in data["validation"].items():
                if hasattr(self.validation, k):
                    setattr(self.validation, k, v)
        if "transformation" in data:
            for k, v in data["transformation"].items():
                if hasattr(self.transformation, k):
                    setattr(self.transformation, k, v)
        if "monitoring" in data:
            for k, v in data["monitoring"].items():
                if hasattr(self.monitoring, k):
                    setattr(self.monitoring, k, v)
        if "logging" in data:
            for k, v in data["logging"].items():
                if hasattr(self.logging, k):
                    setattr(self.logging, k, v)
        if "schema" in data:
            schema_cfg = data["schema"]
            if "mode" in schema_cfg:
                self.schema_mode = schema_cfg["mode"]
            if "expected_columns" in schema_cfg:
                self.expected_columns = schema_cfg["expected_columns"]


# ---------------------------------------------------------------------------
# Sample YAML Config Generator
# ---------------------------------------------------------------------------

def generate_sample_config() -> str:
    """Generate a sample YAML configuration file.

    Returns:
        YAML string with all configurable options.
    """
    return """# ETL Configuration - Customer Lifecycle Prediction System
# All values can be overridden by environment variables.

landing:
  base_path: /data/landing
  default_format: parquet
  compression: snappy

staging:
  batch_size: 5000
  truncate_after_load: true

validation:
  enabled: true
  mandatory_fields:
    - customer_id
    - account_id
    - branch_code
    - transaction_date
    - transaction_type
    - transaction_channel
    - transaction_amount
    - currency
  accepted_currencies:
    - ZAR
    - USD
    - EUR
    - GBP
  accepted_transaction_types:
    - CREDIT
    - DEBIT
    - TRANSFER
    - PAYMENT
  accepted_channels:
    - BRANCH
    - ATM
    - POS
    - ONLINE
    - MOBILE
  duplicate_detection_enabled: true
  duplicate_keys:
    - customer_id
    - account_id
    - branch_code
    - transaction_date
    - transaction_amount
    - transaction_type
    - transaction_channel
  exact_duplicate_strategy: reject
  near_duplicate_strategy: flag

transformation:
  date_fields:
    - transaction_date
  date_output_format: "%Y-%m-%d"
  null_fill_values:
    branch_name: UNKNOWN
    currency: ZAR

monitoring:
  enabled: true
  collection_interval_seconds: 10
  alert_thresholds:
    quality_score_min: 80
    error_rate_max: 10
    throughput_min: 100

logging:
  enabled: true
  default_level: INFO
  json_format: true

audit:
  enabled: true
  retention_years: 7

checkpoint:
  enabled: true
  save_interval_records: 1000
  save_interval_seconds: 30
  max_retries_per_checkpoint: 3
"""
