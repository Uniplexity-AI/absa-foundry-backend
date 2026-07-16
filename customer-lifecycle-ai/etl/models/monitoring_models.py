"""
ETL Monitoring Models - SQLAlchemy 2.0 ORM for pipeline metrics.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, TimestampMixin


class PipelineMetricsRecord(Base, TimestampMixin):
    """Persistent pipeline execution metrics."""
    __tablename__ = "etl_pipeline_metrics"
    __table_args__ = {"schema": "etl", "comment": "Pipeline execution metrics"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    total_execution_time_s: Mapped[float] = mapped_column(Float, default=0.0)
    rows_ingested: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_validated: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_rejected: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_transformed: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_loaded: Mapped[int] = mapped_column(BigInteger, default=0)
    validation_error_count: Mapped[int] = mapped_column(BigInteger, default=0)
    validation_warning_count: Mapped[int] = mapped_column(BigInteger, default=0)
    duplicate_count: Mapped[int] = mapped_column(BigInteger, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=100.0)
    throughput_rows_per_sec: Mapped[float] = mapped_column(Float, default=0.0)
    step_durations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )


class JobStatusRecord(Base, TimestampMixin):
    """Current job status snapshot."""
    __tablename__ = "etl_job_status"
    __table_args__ = {"schema": "etl", "comment": "Current pipeline job statuses"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    total_rows: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_processed: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_failed: Mapped[int] = mapped_column(BigInteger, default=0)
    validation_errors: Mapped[int] = mapped_column(BigInteger, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
