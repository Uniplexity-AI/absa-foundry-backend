"""
ETL Logging Service - Structured JSON logging for all ETL subsystems.

Provides 7 separate log streams:
- System: Infrastructure, service health
- ETL: Pipeline operations, batch processing
- Validation: Rule results, data quality
- Transformation: Mapping decisions, enrichments
- Performance: Timing, throughput
- Audit: Compliance trail
- Security: Access events

All logs use structured JSON format for ELK/Splunk integration.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

from etl.schemas.logging_schemas import LogCategory, LogEntry, LogLevel, LoggingConfig


class ETLLogger:
    """Structured JSON logger for ETL pipeline operations.

    Each log category writes to a separate logical stream.
    All output is JSON-formatted for machine consumption.

    Usage:
        logger = ETLLogger("etl.validation")
        logger.info("Validation started", batch_id="b-001", record_count=10000)
        logger.error("Validation failed", error_type="ValueError", error_details="...")
    """

    _instances: dict[str, ETLLogger] = {}
    _config: LoggingConfig = LoggingConfig()

    def __init__(self, logger_name: str, config: LoggingConfig | None = None) -> None:
        self._name = logger_name
        self._config = config or ETLLogger._config
        self._python_logger = logging.getLogger(logger_name)
        self._python_logger.setLevel(self._config.default_level.value)

        if not self._python_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(message)s")  # Raw JSON, no extra formatting
            )
            self._python_logger.addHandler(handler)

    @classmethod
    def configure(cls, config: LoggingConfig) -> None:
        """Set global logging configuration.

        Args:
            config: Logging configuration.
        """
        cls._config = config

    @classmethod
    def get_logger(cls, name: str) -> ETLLogger:
        """Get or create a logger by name.

        Args:
            name: Logger name (e.g., 'etl.validation', 'etl.ingestion').

        Returns:
            ETLLogger instance.
        """
        if name not in cls._instances:
            cls._instances[name] = ETLLogger(name)
        return cls._instances[name]

    # ------------------------------------------------------------------
    # Logging methods
    # ------------------------------------------------------------------

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._log(LogLevel.CRITICAL, message, **kwargs)

    # ------------------------------------------------------------------
    # Performance logging
    # ------------------------------------------------------------------

    def performance(
        self,
        operation: str,
        duration_ms: float,
        **kwargs: Any,
    ) -> None:
        """Log a performance metric.

        Args:
            operation: Operation name.
            duration_ms: Duration in milliseconds.
            **kwargs: Additional context.
        """
        self._log(
            LogLevel.INFO,
            f"Performance: {operation} completed in {duration_ms:.2f}ms",
            category=LogCategory.PERFORMANCE,
            duration_ms=duration_ms,
            extra={"operation": operation, **kwargs},
        )

    # ------------------------------------------------------------------
    # Validation logging
    # ------------------------------------------------------------------

    def validation(
        self,
        rule_id: str,
        passed: bool,
        record_count: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Log a validation rule result.

        Args:
            rule_id: Rule identifier.
            passed: Whether the rule passed.
            record_count: Records affected.
            **kwargs: Additional context.
        """
        level = LogLevel.INFO if passed else LogLevel.WARNING
        status = "PASSED" if passed else "FAILED"
        self._log(
            level,
            f"Validation rule {rule_id}: {status}",
            category=LogCategory.VALIDATION,
            record_count=record_count,
            extra={"rule_id": rule_id, "passed": passed, **kwargs},
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _log(self, level: LogLevel, message: str, **kwargs: Any) -> None:
        """Internal log method — builds and emits a LogEntry.

        Args:
            level: Log level.
            message: Human-readable message.
            **kwargs: Additional LogEntry fields.
        """
        if not self._config.enabled:
            return

        # Resolve category from logger name or kwargs
        category = kwargs.pop("category", self._infer_category(self._name))
        category_level = self._config.category_levels.get(
            category.value if hasattr(category, "value") else str(category),
            self._config.default_level,
        )

        # Skip if below category threshold
        level_rank = {
            LogLevel.DEBUG: 10, LogLevel.INFO: 20,
            LogLevel.WARNING: 30, LogLevel.ERROR: 40, LogLevel.CRITICAL: 50,
        }
        cat_rank = level_rank.get(category_level, 20)
        if level_rank[level] < cat_rank:
            return

        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            level=level,
            category=category,
            message=message,
            logger_name=self._name,
            **kwargs,
        )

        log_method = {
            LogLevel.DEBUG: self._python_logger.debug,
            LogLevel.INFO: self._python_logger.info,
            LogLevel.WARNING: self._python_logger.warning,
            LogLevel.ERROR: self._python_logger.error,
            LogLevel.CRITICAL: self._python_logger.critical,
        }[level]

        if self._config.json_format:
            log_method(entry.to_json())
        else:
            log_method(f"[{category.value}] {message}")

    @staticmethod
    def _infer_category(logger_name: str) -> LogCategory:
        """Infer log category from logger name.

        Args:
            logger_name: Logger name like 'etl.validation'.

        Returns:
            Appropriate LogCategory.
        """
        name_lower = logger_name.lower()
        if "validation" in name_lower:
            return LogCategory.VALIDATION
        elif "transform" in name_lower:
            return LogCategory.TRANSFORMATION
        elif "perf" in name_lower:
            return LogCategory.PERFORMANCE
        elif "audit" in name_lower:
            return LogCategory.AUDIT
        elif "security" in name_lower:
            return LogCategory.SECURITY
        elif "etl" in name_lower:
            return LogCategory.ETL
        return LogCategory.SYSTEM
