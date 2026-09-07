"""
ETL Validation Models - SQLAlchemy 2.0 ORM models for validation results.

Tracks per-batch and per-record validation outcomes for audit
and quality monitoring.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, TimestampMixin


class ValidationRun(Base, TimestampMixin):
    """Record of a validation execution for a batch.

    One row per batch validation run. Summarizes aggregate results.
    """
    __tablename__ = "etl_validation_run"
    __table_args__ = {
        "schema": "etl",
        "comment": "Validation execution records — one per batch",
    }

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        comment="Surrogate primary key",
    )
    run_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="Unique validation run identifier (UUID v4)",
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="FK reference to the batch being validated",
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING",
        comment="Overall status: PENDING, RUNNING, PASSED, FAILED, PARTIAL",
    )
    total_records: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Total records validated",
    )
    valid_records: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Records passing all validations",
    )
    invalid_records: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Records with at least one error",
    )
    duplicate_records: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Duplicate records detected",
    )
    total_errors: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Total error count",
    )
    total_warnings: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
        comment="Total warning count",
    )
    quality_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=100.0,
        comment="Computed quality score (0-100)",
    )
    error_by_category: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Error count per validation category",
    )
    error_by_rule: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Error count per rule ID",
    )
    started_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=func.now(),
        comment="When validation started",
    )
    completed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When validation completed",
    )
    duration_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Total validation duration",
    )
    config_snapshot: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Snapshot of validation config used (for audit)",
    )


class ValidationErrorRecord(Base, TimestampMixin):
    """Individual validation error for a specific record.

    Stored for audit and data quality trend analysis.
    """
    __tablename__ = "etl_validation_error"
    __table_args__ = {
        "schema": "etl",
        "comment": "Individual validation errors — one per failed rule per record",
    }

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="FK reference to etl_validation_run.run_id",
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
    )
    rule_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="Rule that detected the error",
    )
    category: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="Validation category",
    )
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ERROR",
        comment="ERROR, WARNING, INFO",
    )
    field_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="Field that failed validation",
    )
    message: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Human-readable error message",
    )
    record_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Row index in the dataset",
    )
    actual_value: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Actual value that failed (string representation)",
    )
    expected_value: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Expected value or pattern (string representation)",
    )
