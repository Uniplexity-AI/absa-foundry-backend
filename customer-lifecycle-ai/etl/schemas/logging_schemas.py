"""
ETL Logging Schemas - Pydantic v2 models for structured logging.

Defines log categories, levels, and the structured log entry format
for ELK/Splunk integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogCategory(str, Enum):
    """Separate log streams for different ETL subsystems."""
    SYSTEM = "system"           # Infrastructure, service health
    ETL = "etl"                 # Pipeline operations
    VALIDATION = "validation"   # Rule results
    TRANSFORMATION = "transformation"  # Mapping decisions
    PERFORMANCE = "performance"  # Timing data
    AUDIT = "audit"             # Compliance trail
    SECURITY = "security"       # Access events


# ---------------------------------------------------------------------------
# Log Entry
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    """Structured JSON log entry for ELK/Splunk integration.

    Every log entry includes standard metadata for filtering,
    searching, and correlation across services.
    """
    model_config = ConfigDict(extra="allow")

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the event occurred (UTC, ISO 8601)",
    )
    level: LogLevel = Field(default=LogLevel.INFO)
    category: LogCategory = Field(default=LogCategory.SYSTEM)
    message: str = Field(description="Human-readable log message")
    logger_name: str = Field(default="etl", description="Logger name for filtering")

    # Context
    service: str = Field(default="etl-engine", description="Service/module name")
    batch_id: str | None = Field(default=None, description="Batch identifier")
    pipeline_name: str | None = Field(default=None, description="Pipeline name")
    run_id: str | None = Field(default=None, description="Pipeline run identifier")
    step_id: str | None = Field(default=None, description="Current pipeline step")
    correlation_id: str | None = Field(default=None, description="End-to-end correlation ID")

    # Additional
    duration_ms: float | None = Field(default=None, description="Operation duration in ms")
    record_count: int | None = Field(default=None, description="Records affected")
    error_type: str | None = Field(default=None, description="Exception type if error")
    error_details: str | None = Field(default=None, description="Exception traceback/details")
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured data",
    )

    def to_json(self) -> str:
        """Serialize to JSON string for file/stream output."""
        return self.model_dump_json(exclude_none=True)


class LoggingConfig(BaseModel):
    """Centralized logging configuration."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    default_level: LogLevel = LogLevel.INFO
    json_format: bool = Field(default=True, description="Output as JSON (vs plain text)")
    include_timestamps: bool = True
    include_caller_info: bool = False

    # Per-category level overrides
    category_levels: dict[str, LogLevel] = Field(
        default_factory=lambda: {
            "system": LogLevel.INFO,
            "etl": LogLevel.INFO,
            "validation": LogLevel.WARNING,
            "transformation": LogLevel.INFO,
            "performance": LogLevel.INFO,
            "audit": LogLevel.INFO,
            "security": LogLevel.WARNING,
        },
    )

    # Output destinations
    console_output: bool = True
    file_output: bool = False
    file_path: str = Field(default="/var/log/etl/etl.log")
    max_file_size_mb: int = Field(default=100, ge=1)
    backup_count: int = Field(default=10, ge=1)
