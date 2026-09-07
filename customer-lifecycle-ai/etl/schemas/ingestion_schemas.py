"""
ETL Ingestion Schemas - Pydantic v2 data models for the Ingestion Framework.

Defines data structures for:
- IngestionRequest: Input to trigger ingestion from a source
- IngestionResult: Output summarizing what was ingested
- IngestionBatch: Full batch metadata for tracking
- IngestionStatus: State machine for batch lifecycle
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from etl.schemas.connector_schemas import BatchMetadata, ConnectorConfig, SourceType


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IngestionStatus(str, Enum):
    """Lifecycle states of an ingestion batch."""
    RECEIVED = "RECEIVED"           # Data received, not yet processed
    CHECKSUMMED = "CHECKSUMMED"     # Checksum computed and verified
    LANDED = "LANDED"               # Raw data written to landing zone
    REGISTERED = "REGISTERED"       # Metadata persisted in database
    VALIDATION_TRIGGERED = "VALIDATION_TRIGGERED"  # Validation event emitted
    FAILED = "FAILED"               # Ingestion failed at some step
    CANCELLED = "CANCELLED"         # Ingestion was manually cancelled


# ---------------------------------------------------------------------------
# Ingestion Request
# ---------------------------------------------------------------------------

class IngestionRequest(BaseModel):
    """Request to trigger data ingestion from a source.

    Sent by the orchestration service or API to initiate an ETL pipeline run.
    """
    model_config = ConfigDict(extra="forbid")

    connector_config: ConnectorConfig = Field(
        description="Configuration for the source connector to use",
    )
    pipeline_name: str = Field(
        default="default",
        description="Name of the pipeline this ingestion belongs to",
    )
    trigger_type: str = Field(
        default="manual",
        description="What triggered this ingestion: manual, scheduled, event, api",
    )
    triggered_by: str = Field(
        default="system",
        description="User or service that triggered this ingestion",
    )
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Priority level (1=highest, 10=lowest)",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for end-to-end tracing across services",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary tags for categorization and filtering",
    )
    max_rows: int | None = Field(
        default=None,
        ge=1,
        description="Maximum rows to ingest (null = unlimited)",
    )
    dry_run: bool = Field(
        default=False,
        description="If True, validate configuration but do not actually ingest data",
    )


# ---------------------------------------------------------------------------
# Ingestion Batch (Full Metadata)
# ---------------------------------------------------------------------------

class IngestionBatch(BaseModel):
    """Complete metadata for a single ingestion batch.

    Extends BatchMetadata with ingestion-specific fields tracked
    throughout the ingestion lifecycle.
    """
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(
        description="Unique batch identifier (UUID v4 + timestamp)",
    )
    pipeline_name: str = Field(
        description="Name of the pipeline this batch belongs to",
    )
    source_type: SourceType = Field(
        description="Type of the source connector used",
    )
    source_name: str = Field(
        description="Name of the source system",
    )
    status: IngestionStatus = Field(
        default=IngestionStatus.RECEIVED,
        description="Current status in the ingestion lifecycle",
    )
    trigger_type: str = Field(
        default="manual",
        description="What triggered this ingestion",
    )
    triggered_by: str = Field(
        default="system",
        description="User or service identifier",
    )
    correlation_id: str | None = Field(
        default=None,
        description="End-to-end correlation ID",
    )
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
    )
    total_rows: int = Field(
        default=0,
        ge=0,
        description="Total rows ingested",
    )
    total_chunks: int = Field(
        default=0,
        ge=0,
        description="Total chunks received from connector",
    )
    total_size_bytes: int = Field(
        default=0,
        ge=0,
        description="Total size of ingested data in bytes",
    )
    checksum_sha256: str | None = Field(
        default=None,
        description="SHA-256 checksum of all ingested data",
    )
    landing_path: str | None = Field(
        default=None,
        description="Path in the landing zone where raw data is stored",
    )
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the first chunk was received (UTC)",
    )
    landed_at: datetime | None = Field(
        default=None,
        description="When data was written to landing zone (UTC)",
    )
    registered_at: datetime | None = Field(
        default=None,
        description="When metadata was persisted to database (UTC)",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When ingestion lifecycle completed (UTC)",
    )
    duration_seconds: float | None = Field(
        default=None,
        description="Total wall-clock duration of ingestion",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if ingestion failed",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary tags for categorization",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional ingestion-specific metadata",
    )

    @property
    def is_complete(self) -> bool:
        """Whether ingestion has completed (success or failure)."""
        return self.status in (
            IngestionStatus.VALIDATION_TRIGGERED,
            IngestionStatus.FAILED,
            IngestionStatus.CANCELLED,
        )

    @property
    def is_successful(self) -> bool:
        """Whether ingestion completed successfully."""
        return self.status == IngestionStatus.VALIDATION_TRIGGERED


# ---------------------------------------------------------------------------
# Ingestion Result
# ---------------------------------------------------------------------------

class IngestionResult(BaseModel):
    """Summary result returned after ingestion completes.

    Provides a high-level overview of what was ingested for
    downstream consumers (orchestration, monitoring, API responses).
    """
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(description="Batch identifier")
    status: IngestionStatus = Field(description="Final ingestion status")
    pipeline_name: str = Field(description="Pipeline name")
    source_type: SourceType = Field(description="Source type")
    source_name: str = Field(description="Source name")
    total_rows: int = Field(default=0, description="Total rows ingested")
    total_chunks: int = Field(default=0, description="Total chunks processed")
    total_size_bytes: int = Field(default=0, description="Total data size")
    checksum_sha256: str | None = Field(default=None, description="Data checksum")
    landing_path: str | None = Field(default=None, description="Landing zone path")
    received_at: datetime = Field(description="When ingestion started")
    completed_at: datetime | None = Field(default=None, description="When ingestion finished")
    duration_seconds: float | None = Field(default=None, description="Total duration")
    error_message: str | None = Field(default=None, description="Error if failed")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings encountered during ingestion",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Downstream steps that should be triggered next",
    )

    @classmethod
    def from_batch(cls, batch: IngestionBatch) -> IngestionResult:
        """Create an IngestionResult from an IngestionBatch."""
        return cls(
            batch_id=batch.batch_id,
            status=batch.status,
            pipeline_name=batch.pipeline_name,
            source_type=batch.source_type,
            source_name=batch.source_name,
            total_rows=batch.total_rows,
            total_chunks=batch.total_chunks,
            total_size_bytes=batch.total_size_bytes,
            checksum_sha256=batch.checksum_sha256,
            landing_path=batch.landing_path,
            received_at=batch.received_at,
            completed_at=batch.completed_at,
            duration_seconds=batch.duration_seconds,
            error_message=batch.error_message,
            next_steps=["validation"] if batch.is_successful else [],
        )


# ---------------------------------------------------------------------------
# Ingestion Event (for event-driven architecture)
# ---------------------------------------------------------------------------

class IngestionEvent(BaseModel):
    """Event emitted after successful ingestion.

    Consumed by the Validation Engine and Monitoring module.
    Follows the normalized event format defined in the database spec.
    """
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(description="Unique event identifier (UUID v4)")
    event_type: str = Field(
        default="ingestion.completed",
        description="Event type: ingestion.completed, ingestion.failed, etc.",
    )
    batch_id: str = Field(description="Batch ID this event relates to")
    pipeline_name: str = Field(description="Pipeline name")
    source_type: SourceType = Field(description="Source type")
    source_name: str = Field(description="Source name")
    status: IngestionStatus = Field(description="Ingestion status")
    total_rows: int = Field(default=0, description="Total rows ingested")
    checksum_sha256: str | None = Field(default=None, description="Data checksum")
    landing_path: str | None = Field(default=None, description="Landing zone path")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the event occurred (UTC)",
    )
    correlation_id: str | None = Field(default=None, description="Correlation ID")
    producer: str = Field(
        default="etl-ingestion-service",
        description="Service that produced this event",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional event payload",
    )
