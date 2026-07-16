"""
ETL Monitoring Schemas - Pydantic v2 models for pipeline observability.

Tracks pipeline execution metrics, job statuses, throughput,
and system resource usage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MetricType(str, Enum):
    COUNTER = "COUNTER"
    GAUGE = "GAUGE"
    HISTOGRAM = "HISTOGRAM"
    SUMMARY = "SUMMARY"


# ---------------------------------------------------------------------------
# Job Snapshot
# ---------------------------------------------------------------------------

class JobSnapshot(BaseModel):
    """Current state of a running or recently completed pipeline job."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Pipeline run identifier")
    pipeline_name: str
    batch_id: str | None = None
    status: JobStatus
    current_step: str | None = None
    progress_pct: float = Field(default=0.0, ge=0, le=100)
    total_rows: int = 0
    rows_processed: int = 0
    rows_failed: int = 0
    validation_errors: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Pipeline Metrics
# ---------------------------------------------------------------------------

class PipelineMetrics(BaseModel):
    """Aggregated metrics for a pipeline run."""
    model_config = ConfigDict(extra="forbid")

    run_id: str
    pipeline_name: str
    batch_id: str | None = None
    total_execution_time_s: float = 0.0
    rows_ingested: int = 0
    rows_validated: int = 0
    rows_rejected: int = 0
    rows_transformed: int = 0
    rows_loaded: int = 0
    validation_error_count: int = 0
    validation_warning_count: int = 0
    duplicate_count: int = 0
    quality_score: float = Field(default=100.0, ge=0, le=100)
    throughput_rows_per_sec: float = 0.0
    step_durations: dict[str, float] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# System Metrics
# ---------------------------------------------------------------------------

class SystemMetrics(BaseModel):
    """System-level resource usage metrics."""
    model_config = ConfigDict(extra="forbid")

    cpu_percent: float = Field(default=0.0, ge=0, le=100)
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_used_gb: float = 0.0
    active_connections: int = 0
    open_files: int = 0
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def memory_pct(self) -> float:
        if self.memory_total_mb == 0:
            return 0.0
        return min(self.memory_used_mb / self.memory_total_mb * 100, 100.0)


# ---------------------------------------------------------------------------
# Monitoring Config
# ---------------------------------------------------------------------------

class MonitoringConfig(BaseModel):
    """Monitoring engine configuration."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    collection_interval_seconds: float = Field(default=10.0, ge=1.0)
    metrics_retention_days: int = Field(default=90, ge=1)
    track_system_metrics: bool = True
    alert_on_failure: bool = True
    alert_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "quality_score_min": 80.0,
            "error_rate_max": 10.0,
            "execution_time_max_s": 7200,
            "throughput_min": 100,
            "memory_pct_max": 85.0,
        },
    )
