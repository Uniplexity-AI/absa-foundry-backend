"""
ETL Landing Zone Models - SQLAlchemy 2.0 ORM models for landed file tracking.

Tracks every file written to the immutable landing zone for
audit trail and retrieval purposes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, ImmutableModel


class LandingFileRecord(Base, ImmutableModel):
    """Immutable record of a file in the landing zone.

    Uses ImmutableModel (no soft-delete, no updated_by) since
    landing zone files are write-once and never modified.
    """
    __tablename__ = "etl_landing_file"
    __table_args__ = {
        "schema": "etl",
        "comment": "Immutable records of files in the landing zone — write-once, never modified",
    }

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        comment="Surrogate primary key",
    )
    file_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="Unique file identifier (UUID v4)",
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="FK reference to etl_ingestion_batch.batch_id",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Chunk index within the batch (0-based)",
    )
    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Name of the file (e.g., chunk_0001.parquet)",
    )
    file_path: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Absolute path to the file in the landing zone",
    )
    file_format: Mapped[str] = mapped_column(
        String(32), nullable=False, default="parquet",
        comment="File format: parquet, csv, json, avro",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Size of the file in bytes",
    )
    row_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Number of data rows in the file",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 checksum of the file contents",
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="WRITING",
        server_default="'WRITING'",
        comment="File status: WRITING, LANDED, CORRUPT, ARCHIVED",
    )
    column_names: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="Ordered list of column names in the file",
    )
    column_types: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Mapping of column_name → data type",
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When file integrity was verified (UTC)",
    )
    source_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="Source connector type that produced this data",
    )
    source_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Human-readable source system name",
    )
    compression: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="snappy",
        comment="Compression algorithm: snappy, gzip, lz4, zstd, none",
    )
    tags: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Arbitrary key-value tags",
    )
