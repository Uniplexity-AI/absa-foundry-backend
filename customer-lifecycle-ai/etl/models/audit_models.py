"""
ETL Audit Models - SQLAlchemy 2.0 ORM for compliance audit trail.

Uses ImmutableModel — records are write-once, never modified.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, ImmutableModel


class AuditRecord(Base, ImmutableModel):
    """Immutable audit trail — one record per batch.

    Uses ImmutableModel: no soft-delete, no updated_by.
    Records are append-only for regulatory compliance.
    """
    __tablename__ = "etl_audit"
    __table_args__ = {"schema": "etl", "comment": "Immutable audit trail — one record per batch"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    rows_received: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_valid: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_rejected: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_loaded: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_skipped: Mapped[int] = mapped_column(BigInteger, default=0)

    duplicates_detected: Mapped[int] = mapped_column(BigInteger, default=0)
    warnings_count: Mapped[int] = mapped_column(BigInteger, default=0)
    errors_count: Mapped[int] = mapped_column(BigInteger, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=100.0)

    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    triggered_by: Mapped[str] = mapped_column(String(255), default="system")
    operator_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
