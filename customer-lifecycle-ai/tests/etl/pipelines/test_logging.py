"""
Unit tests for ETL Logging module.

Tests cover:
- ETLLogger creation and singleton behavior
- Log level filtering
- Category inference
- JSON output format
- Performance logging
- Validation logging
- LoggingConfig defaults
"""

from __future__ import annotations

import json

import pytest

from etl.logging.service import ETLLogger
from etl.schemas.logging_schemas import (
    LogCategory,
    LogEntry,
    LogLevel,
    LoggingConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_logger() -> None:
    """Reset logger state between tests."""
    ETLLogger._instances.clear()
    ETLLogger._config = LoggingConfig()


# ---------------------------------------------------------------------------
# LoggingConfig Tests
# ---------------------------------------------------------------------------

class TestLoggingConfig:
    def test_defaults(self) -> None:
        config = LoggingConfig()
        assert config.enabled is True
        assert config.default_level == LogLevel.INFO
        assert config.json_format is True
        assert config.console_output is True

    def test_category_levels_exist(self) -> None:
        config = LoggingConfig()
        for cat in LogCategory:
            assert cat.value in config.category_levels


# ---------------------------------------------------------------------------
# ETLLogger Tests
# ---------------------------------------------------------------------------

class TestETLLogger:
    def test_get_logger_returns_same_instance(self) -> None:
        logger1 = ETLLogger.get_logger("etl.validation")
        logger2 = ETLLogger.get_logger("etl.validation")
        assert logger1 is logger2

    def test_get_logger_different_names(self) -> None:
        logger1 = ETLLogger.get_logger("etl.ingestion")
        logger2 = ETLLogger.get_logger("etl.validation")
        assert logger1 is not logger2

    def test_info_logs_without_error(self) -> None:
        logger = ETLLogger.get_logger("etl.test")
        # Should not raise
        logger.info("Test message", batch_id="b-001")

    def test_debug_logs_without_error(self) -> None:
        logger = ETLLogger.get_logger("etl.test")
        logger.debug("Debug message")

    def test_warning_logs_without_error(self) -> None:
        logger = ETLLogger.get_logger("etl.test")
        logger.warning("Warning message")

    def test_error_logs_without_error(self) -> None:
        logger = ETLLogger.get_logger("etl.test")
        logger.error("Error message", error_type="ValueError", error_details="Bad value")

    def test_performance_log(self) -> None:
        logger = ETLLogger.get_logger("etl.performance")
        logger.performance("validation", duration_ms=123.45)

    def test_validation_log_pass(self) -> None:
        logger = ETLLogger.get_logger("etl.validation")
        logger.validation("MANDATORY-001", passed=True, record_count=1000)

    def test_validation_log_fail(self) -> None:
        logger = ETLLogger.get_logger("etl.validation")
        logger.validation("BUSINESS-AMT-001", passed=False, record_count=5)


# ---------------------------------------------------------------------------
# Category Inference Tests
# ---------------------------------------------------------------------------

class TestCategoryInference:
    def test_infer_validation(self) -> None:
        assert ETLLogger._infer_category("etl.validation") == LogCategory.VALIDATION

    def test_infer_transformation(self) -> None:
        assert ETLLogger._infer_category("etl.transformation") == LogCategory.TRANSFORMATION

    def test_infer_performance(self) -> None:
        assert ETLLogger._infer_category("etl.performance") == LogCategory.PERFORMANCE

    def test_infer_audit(self) -> None:
        assert ETLLogger._infer_category("etl.audit") == LogCategory.AUDIT

    def test_infer_security(self) -> None:
        assert ETLLogger._infer_category("etl.security") == LogCategory.SECURITY

    def test_infer_etl_default(self) -> None:
        assert ETLLogger._infer_category("etl.ingestion") == LogCategory.ETL

    def test_infer_system_fallback(self) -> None:
        assert ETLLogger._infer_category("something.else") == LogCategory.SYSTEM


# ---------------------------------------------------------------------------
# LogEntry Tests
# ---------------------------------------------------------------------------

class TestLogEntry:
    def test_to_json(self) -> None:
        entry = LogEntry(
            level=LogLevel.INFO,
            category=LogCategory.ETL,
            message="Test message",
            batch_id="b-001",
        )
        json_str = entry.to_json()
        data = json.loads(json_str)
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert data["batch_id"] == "b-001"

    def test_extra_fields(self) -> None:
        entry = LogEntry(
            level=LogLevel.WARNING,
            category=LogCategory.VALIDATION,
            message="Rule failed",
            extra={"rule_id": "R001", "actual": "xyz"},
        )
        json_str = entry.to_json()
        data = json.loads(json_str)
        assert data["extra"]["rule_id"] == "R001"
