"""
ETL Ingestion Models - SQLAlchemy 2.0 ORM models for ingestion tracking.

Models for tracking ingestion batches throughout their lifecycle
from reception through landing zone storage.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, TimestampMixin


class IngestionBatchRecord(Base, TimestampMixin):
    """Immutable record of every ingestion batch.

    One row per batch, tracking the complete lifecycle from
    data reception through landing zone storage and validation trigger.
    """
    __tablename__ = "etl_ingestion_batch"
    __table_args__ = {
        "schema": "etl",
        "comment": "Ingestion batch lifecycle records — one row per ingested batch",
    }

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        comment="Surrogate primary key",
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="Unique batch identifier (UUID v4 + timestamp prefix)",
    )
    pipeline_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="Name of the pipeline that triggered this ingestion",
    )
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="Source connector type: postgresql, csv, rest, etc.",
    )
    source_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Human-readable source system name",
    )
    connector_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
        comment="FK reference to etl_connector_registry.connector_id",
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="RECEIVED",
        server_default="'RECEIVED'",
        comment="Current status: RECEIVED, CHECKSUMMED, LANDED, REGISTERED, VALIDATION_TRIGGERED, FAILED, CANCELLED",
    )
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual",
        comment="Trigger type: manual, scheduled, event, api",
    )
    triggered_by: Mapped[str] = mapped_column(
        String(255), nullable=False, default="system",
        comment="User or service that triggered the ingestion",
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
        comment="End-to-end correlation ID for tracing",
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5,
        comment="Priority level: 1 (highest) to 10 (lowest)",
    )
    total_rows: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Total rows ingested across all chunks",
    )
    total_chunks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Total chunks received from connector",
    )
    total_size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Total size of ingested data in bytes",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 checksum of all ingested data",
    )
    landing_path: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Absolute path in the landing zone where raw data is stored",
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Timestamp when first data chunk was received (UTC)",
    )
    landed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp when data was written to landing zone (UTC)",
    )
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp when metadata was persisted (UTC)",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp when ingestion lifecycle completed (UTC)",
    )
    duration_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Wall-clock duration of entire ingestion process",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Error details if ingestion failed",
    )
    tags: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Arbitrary key-value tags for categorization",
    )
    extra_metadata: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Additional ingestion-specific metadata (JSON)",
    )


class IngestionChunkRecord(Base, TimestampMixin):
    """Record of each individual chunk within an ingestion batch.

    Tracks per-chunk metadata for granular progress monitoring
    and checkpoint-based resumption.
    """
    __tablename__ = "etl_ingestion_chunk"
    __table_args__ = {
        "schema": "etl",
        "comment": "Per-chunk ingestion records for granular progress tracking",
    }

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        comment="Surrogate primary key",
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="FK reference to etl_ingestion_batch.batch_id",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="Zero-based chunk index within the batch",
    )
    row_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Number of rows in this chunk",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Size of this chunk in bytes",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 checksum of this chunk's data",
    )
    chunk_path: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Path to the chunk file in the landing zone",
    )
    column_names: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="Ordered list of column names in this chunk",
    )
    column_types: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Mapping of column_name → dtype for this chunk",
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this chunk was received (UTC)",
    )
