"""
ETL Models - SQLAlchemy 2.0 ORM models for ETL metadata.

Models for tracking connector configurations, batch execution history,
and data source registry. Extends shared.database.base.Base following
the project's database model conventions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Connector Registry
# ---------------------------------------------------------------------------

class ConnectorRegistration(Base, TimestampMixin):
    """Registry of configured data source connectors.

    Each row represents one configured connection to a data source.
    Sensitive fields are NOT stored — they're fetched from a secrets
    manager at runtime.
    """
    __tablename__ = "etl_connector_registry"
    __table_args__ = {"schema": "etl", "comment": "Registered data source connectors"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        comment="Surrogate primary key",
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="Unique connector identifier (e.g., 'pg-core-banking')",
    )
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="Source type: postgresql, sqlserver, oracle, mysql, csv, etc.",
    )
    source_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Human-readable source name (e.g., 'Core Banking DB - Prod')",
    )
    is_active: Mapped[bool] = mapped_column(
        default=True, server_default=func.true(), nullable=False,
        comment="Whether this connector is active and available for use",
    )
    host: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Hostname or IP address (null for file connectors)",
    )
    port: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Port number (null for file connectors)",
    )
    database_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Database or file path reference",
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Non-sensitive connector configuration (JSON)",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Human-readable description of this connector",
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp of last successful connection",
    )
    connection_status: Mapped[str] = mapped_column(
        String(32), default="disconnected", server_default="'disconnected'",
        comment="Current connection status: disconnected, connected, failed",
    )


# ---------------------------------------------------------------------------
# Batch Execution Log
# ---------------------------------------------------------------------------

class BatchExecutionLog(Base, TimestampMixin):
    """Log of every batch extraction executed by the ETL engine.

    Provides full traceability for audit and debugging purposes.
    Each row represents one batch extraction from a source.
    """
    __tablename__ = "etl_batch_execution_log"
    __table_args__ = {"schema": "etl", "comment": "Batch extraction execution history"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        comment="Surrogate primary key",
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="Unique batch identifier (UUID v4)",
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="FK reference to etl_connector_registry.connector_id",
    )
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="Source type at time of extraction",
    )
    source_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Source name at time of extraction",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="When extraction started (UTC)",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When extraction completed (UTC)",
    )
    status: Mapped[str] = mapped_column(
        String(32), default="RUNNING", server_default="'RUNNING'",
        comment="Extraction status: RUNNING, COMPLETED, FAILED, CANCELLED",
    )
    total_rows: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0",
        comment="Total rows extracted",
    )
    total_chunks: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
        comment="Total chunks yielded",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 checksum of extracted data",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Error message if extraction failed",
    )
    duration_seconds: Mapped[float | None] = mapped_column(
        nullable=True,
        comment="Total extraction duration in seconds",
    )
    query_or_path: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="SQL query, file path, or API endpoint used",
    )
    extra_metadata: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Additional extraction metadata",
    )
