"""
ETL Checkpoint Schemas - Pydantic v2 models for resumable processing.

Tracks pipeline execution progress so processing can resume
from the last checkpoint after failure — never restart completed work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckpointStatus(str, Enum):
    """Status of a checkpoint."""
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Checkpoint(BaseModel):
    """A single checkpoint capturing the exact state of pipeline execution.

    Stored after each step or batch of records, enabling precise
    resumption from the point of failure.
    """
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(description="Unique checkpoint identifier")
    batch_id: str = Field(description="Batch being processed")
    pipeline_name: str = Field(description="Pipeline name")
    current_step: str = Field(description="Current pipeline step ID")
    current_record_index: int = Field(
        default=0, ge=0,
        description="Row index within the current step's data",
    )
    total_records: int = Field(default=0, ge=0, description="Total records for current step")
    status: CheckpointStatus = Field(default=CheckpointStatus.IN_PROGRESS)
    retry_count: int = Field(default=0, ge=0, description="Number of retries at this checkpoint")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Step-specific state (e.g., last_processed_id)",
    )
    error_message: str | None = Field(default=None)

    @property
    def progress_pct(self) -> float:
        """Percentage of current step completed."""
        if self.total_records == 0:
            return 100.0
        return min(self.current_record_index / self.total_records * 100, 100.0)

    @property
    def is_resumable(self) -> bool:
        """Whether this checkpoint can be resumed from."""
        return self.status in (CheckpointStatus.IN_PROGRESS, CheckpointStatus.FAILED)


class CheckpointConfig(BaseModel):
    """Configuration for checkpoint behavior."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True)
    save_interval_records: int = Field(
        default=1000, ge=1,
        description="Save checkpoint every N records",
    )
    save_interval_seconds: float = Field(
        default=30.0, ge=1.0,
        description="Save checkpoint at least every N seconds",
    )
    max_retries_per_checkpoint: int = Field(
        default=3, ge=0,
        description="Max retries at a single checkpoint",
    )
    retention_days: int = Field(
        default=30, ge=1,
        description="Days to retain completed checkpoints",
    )
    backend: str = Field(
        default="database",
        description="Checkpoint backend: database, redis, file",
    )
