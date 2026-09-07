"""
ETL Configuration - Centralized, environment-based configuration.

Loads all ETL settings from environment variables and YAML files.
Nothing hardcoded — all rules, thresholds, and settings configurable.

Categories:
- Validation rules, accepted channels/currencies
- Duplicate detection thresholds and strategies
- Retry policies, scheduling, checkpoint settings
- Monitoring alerts, logging levels, audit retention
"""

from etl.config.service import ETLConfig, generate_sample_config

__all__ = [
    "ETLConfig",
    "generate_sample_config",
]
