"""
ETL Checkpoint Service - Resumable pipeline execution.

Saves and restores pipeline execution state so processing
can resume from the exact point of failure — never restart
completed work.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from etl.models.checkpoint_models import CheckpointRecord
from etl.schemas.checkpoint_schemas import Checkpoint, CheckpointConfig, CheckpointStatus


class CheckpointService:
    """Manages pipeline checkpoints for resumable processing.

    Saves progress after each batch of records and each step
    completion. On resume, loads the latest checkpoint and
    skips already-processed records.
    """

    def __init__(
        self,
        session: AsyncSession,
        config: CheckpointConfig | None = None,
    ) -> None:
        self._session = session
        self.config = config or CheckpointConfig()
        self._last_save_time: float = 0.0

    async def save(
        self,
        batch_id: str,
        pipeline_name: str,
        current_step: str,
        current_record_index: int,
        total_records: int,
        metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> Checkpoint:
        """Save a checkpoint of current pipeline progress.

        Args:
            batch_id: Batch identifier.
            pipeline_name: Pipeline name.
            current_step: Current step ID.
            current_record_index: Records processed so far.
            total_records: Total records for this step.
            metadata: Step-specific state.
            error_message: Error if checkpointing after failure.

        Returns:
            The saved Checkpoint.
        """
        if not self.config.enabled:
            return self._dummy_checkpoint(batch_id, pipeline_name, current_step)

        existing = await self._find_existing(batch_id, current_step)

        checkpoint_id = existing.checkpoint_id if existing else str(uuid.uuid4())
        status = CheckpointStatus.FAILED if error_message else CheckpointStatus.IN_PROGRESS

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            batch_id=batch_id,
            pipeline_name=pipeline_name,
            current_step=current_step,
            current_record_index=current_record_index,
            total_records=total_records,
            status=status,
            retry_count=(existing.retry_count + 1) if existing and error_message else 0,
            metadata=metadata or {},
            error_message=error_message,
            updated_at=datetime.now(timezone.utc),
        )

        if existing:
            await self._update_record(checkpoint)
        else:
            await self._insert_record(checkpoint)

        await self._session.flush()
        self._last_save_time = time.monotonic()
        return checkpoint

    async def load(
        self, batch_id: str, step_id: str
    ) -> Checkpoint | None:
        """Load the latest checkpoint for a batch and step.

        Args:
            batch_id: Batch identifier.
            step_id: Step to resume.

        Returns:
            Checkpoint if found and resumable, None otherwise.
        """
        if not self.config.enabled:
            return None

        stmt = (
            select(CheckpointRecord)
            .where(
                CheckpointRecord.batch_id == batch_id,
                CheckpointRecord.current_step == step_id,
            )
            .order_by(CheckpointRecord.last_updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            return None

        checkpoint = self._record_to_checkpoint(record)
        if not checkpoint.is_resumable:
            return None
        if checkpoint.retry_count >= self.config.max_retries_per_checkpoint:
            return None

        return checkpoint

    async def mark_completed(
        self, batch_id: str, step_id: str
    ) -> None:
        """Mark a checkpoint as completed — work is done.

        Args:
            batch_id: Batch identifier.
            step_id: Completed step.
        """
        if not self.config.enabled:
            return

        stmt = (
            update(CheckpointRecord)
            .where(
                CheckpointRecord.batch_id == batch_id,
                CheckpointRecord.current_step == step_id,
            )
            .values(
                status=CheckpointStatus.COMPLETED.value,
                last_updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_resume_offset(
        self, batch_id: str, step_id: str, total: int
    ) -> int:
        """Get the record index from which to resume.

        Args:
            batch_id: Batch identifier.
            step_id: Step ID to resume.
            total: Total records (used if no checkpoint exists).

        Returns:
            Record index to resume from (0 if starting fresh).
        """
        checkpoint = await self.load(batch_id, step_id)
        if checkpoint is None:
            return 0
        return min(checkpoint.current_record_index, total)

    async def should_save_checkpoint(
        self, records_since_save: int
    ) -> bool:
        """Check if it's time to save a checkpoint.

        Saves based on record count OR time interval.

        Args:
            records_since_save: Records processed since last save.

        Returns:
            True if a checkpoint should be saved now.
        """
        if not self.config.enabled:
            return False
        if records_since_save >= self.config.save_interval_records:
            return True
        elapsed = time.monotonic() - self._last_save_time
        return elapsed >= self.config.save_interval_seconds

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _find_existing(
        self, batch_id: str, step_id: str
    ) -> Checkpoint | None:
        """Find an existing checkpoint for upsert."""
        stmt = (
            select(CheckpointRecord)
            .where(
                CheckpointRecord.batch_id == batch_id,
                CheckpointRecord.current_step == step_id,
            )
            .order_by(CheckpointRecord.last_updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return self._record_to_checkpoint(record) if record else None

    async def _insert_record(self, checkpoint: Checkpoint) -> None:
        """Insert a new checkpoint record."""
        record = CheckpointRecord(
            checkpoint_id=checkpoint.checkpoint_id,
            batch_id=checkpoint.batch_id,
            pipeline_name=checkpoint.pipeline_name,
            current_step=checkpoint.current_step,
            current_record_index=checkpoint.current_record_index,
            total_records=checkpoint.total_records,
            status=checkpoint.status.value,
            retry_count=checkpoint.retry_count,
            last_updated_at=checkpoint.updated_at,
            metadata_json=checkpoint.metadata,
            error_message=checkpoint.error_message,
        )
        self._session.add(record)

    async def _update_record(self, checkpoint: Checkpoint) -> None:
        """Update an existing checkpoint record."""
        stmt = (
            update(CheckpointRecord)
            .where(CheckpointRecord.checkpoint_id == checkpoint.checkpoint_id)
            .values(
                current_record_index=checkpoint.current_record_index,
                total_records=checkpoint.total_records,
                status=checkpoint.status.value,
                retry_count=checkpoint.retry_count,
                last_updated_at=checkpoint.updated_at,
                metadata_json=checkpoint.metadata,
                error_message=checkpoint.error_message,
            )
        )
        await self._session.execute(stmt)

    @staticmethod
    def _record_to_checkpoint(record: CheckpointRecord) -> Checkpoint:
        """Convert ORM record to Pydantic schema."""
        return Checkpoint(
            checkpoint_id=record.checkpoint_id,
            batch_id=record.batch_id,
            pipeline_name=record.pipeline_name,
            current_step=record.current_step,
            current_record_index=record.current_record_index,
            total_records=record.total_records,
            status=CheckpointStatus(record.status),
            retry_count=record.retry_count,
            created_at=record.created_at,
            updated_at=record.last_updated_at,
            metadata=record.metadata_json or {},
            error_message=record.error_message,
        )

    @staticmethod
    def _dummy_checkpoint(
        batch_id: str, pipeline_name: str, step: str
    ) -> Checkpoint:
        """Return a no-op checkpoint when checkpoints are disabled."""
        return Checkpoint(
            checkpoint_id="disabled",
            batch_id=batch_id,
            pipeline_name=pipeline_name,
            current_step=step,
            status=CheckpointStatus.IN_PROGRESS,
        )
