"""
ETL Orchestration Models - SQLAlchemy 2.0 ORM models for pipeline runs.

Tracks pipeline execution history, step results, and scheduling.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, TimestampMixin


class PipelineRunRecord(Base, TimestampMixin):
    """Record of a pipeline execution run."""
    __tablename__ = "etl_pipeline_run"
    __table_args__ = {"schema": "etl", "comment": "Pipeline execution history"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="Unique run identifier (UUID v4)",
    )
    pipeline_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual",
    )
    triggered_by: Mapped[str] = mapped_column(
        String(255), nullable=False, default="system",
    )
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING",
    )
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0)
    step_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
