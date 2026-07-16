"""
ETL Checkpoint Models - SQLAlchemy 2.0 ORM model for checkpoint persistence.

Stores pipeline execution checkpoints for resumable processing.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, TimestampMixin


class CheckpointRecord(Base, TimestampMixin):
    """Persistent checkpoint for resumable pipeline execution."""
    __tablename__ = "etl_checkpoint"
    __table_args__ = {"schema": "etl", "comment": "Pipeline checkpoints for resumable processing"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    checkpoint_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    current_step: Mapped[str] = mapped_column(String(128), nullable=False)
    current_record_index: Mapped[int] = mapped_column(BigInteger, default=0)
    total_records: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(32), default="IN_PROGRESS")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
