"""
ETL Ingestion Repository - Data access for ingestion metadata.

Implements the IngestionRepository protocol using SQLAlchemy async sessions.
Manages persistence of batch and chunk records.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from etl.models.ingestion_models import IngestionBatchRecord, IngestionChunkRecord
from etl.schemas.ingestion_schemas import IngestionBatch, IngestionStatus


class IngestionRepository:
    """SQLAlchemy-based repository for ingestion metadata.

    Implements the IngestionRepository protocol for persisting
    and retrieving ingestion batch and chunk records.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with an async SQLAlchemy session.

        Args:
            session: Active async database session.
        """
        self._session = session

    async def save_batch(self, batch: IngestionBatch) -> None:
        """Persist an ingestion batch record.

        Creates a new IngestionBatchRecord from the IngestionBatch schema
        and inserts it into the database.

        Args:
            batch: The batch metadata to persist.
        """
        record = IngestionBatchRecord(
            batch_id=batch.batch_id,
            pipeline_name=batch.pipeline_name,
            source_type=batch.source_type.value,
            source_name=batch.source_name,
            status=batch.status.value,
            trigger_type=batch.trigger_type,
            triggered_by=batch.triggered_by,
            correlation_id=batch.correlation_id,
            priority=batch.priority,
            total_rows=batch.total_rows,
            total_chunks=batch.total_chunks,
            total_size_bytes=batch.total_size_bytes,
            checksum_sha256=batch.checksum_sha256,
            landing_path=batch.landing_path,
            received_at=batch.received_at,
            landed_at=batch.landed_at,
            registered_at=datetime.now(timezone.utc),
            completed_at=batch.completed_at,
            duration_seconds=batch.duration_seconds,
            error_message=batch.error_message,
            tags=batch.tags,
            extra_metadata=batch.extra,
        )
        self._session.add(record)
        await self._session.flush()

    async def update_batch_status(
        self, batch_id: str, status: str, **kwargs: object
    ) -> None:
        """Update batch status and optional additional fields.

        Args:
            batch_id: The batch to update.
            status: New status value (use IngestionStatus enum values).
            **kwargs: Additional columns to update (use ORM attribute names).
        """
        values = {"status": status, **kwargs}
        stmt = (
            update(IngestionBatchRecord)
            .where(IngestionBatchRecord.batch_id == batch_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_batch(self, batch_id: str) -> IngestionBatch | None:
        """Retrieve a batch by its ID.

        Args:
            batch_id: The batch ID to look up.

        Returns:
            IngestionBatch if found, None otherwise.
        """
        stmt = select(IngestionBatchRecord).where(
            IngestionBatchRecord.batch_id == batch_id
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            return None

        return IngestionBatch(
            batch_id=record.batch_id,
            pipeline_name=record.pipeline_name,
            source_type=record.source_type,  # type: ignore[arg-type]
            source_name=record.source_name,
            status=IngestionStatus(record.status),
            trigger_type=record.trigger_type,
            triggered_by=record.triggered_by,
            correlation_id=record.correlation_id,
            priority=record.priority,
            total_rows=record.total_rows,
            total_chunks=record.total_chunks,
            total_size_bytes=record.total_size_bytes,
            checksum_sha256=record.checksum_sha256,
            landing_path=record.landing_path,
            received_at=record.received_at,
            landed_at=record.landed_at,
            registered_at=record.registered_at,
            completed_at=record.completed_at,
            duration_seconds=record.duration_seconds,
            error_message=record.error_message,
            tags=record.tags or {},
            extra=record.extra_metadata or {},
        )

    async def save_chunk(
        self,
        batch_id: str,
        chunk_index: int,
        row_count: int,
        size_bytes: int,
        checksum: str | None,
        chunk_path: str | None,
        column_names: list[str] | None,
        column_types: dict[str, str] | None,
    ) -> None:
        """Persist a chunk record for granular tracking.

        Args:
            batch_id: Parent batch ID.
            chunk_index: Zero-based chunk index.
            row_count: Number of rows in this chunk.
            size_bytes: Size of this chunk in bytes.
            checksum: SHA-256 checksum of this chunk.
            chunk_path: Path to chunk file in landing zone.
            column_names: Ordered list of column names.
            column_types: Mapping of column_name → dtype.
        """
        record = IngestionChunkRecord(
            batch_id=batch_id,
            chunk_index=chunk_index,
            row_count=row_count,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
            chunk_path=chunk_path,
            column_names=column_names,
            column_types=column_types,
            received_at=datetime.now(timezone.utc),
        )
        self._session.add(record)
        await self._session.flush()

    async def list_batches_by_pipeline(
        self, pipeline_name: str, limit: int = 100
    ) -> list[IngestionBatch]:
        """List recent batches for a pipeline.

        Args:
            pipeline_name: Pipeline name filter.
            limit: Maximum number of batches to return.

        Returns:
            List of IngestionBatch ordered by received_at descending.
        """
        stmt = (
            select(IngestionBatchRecord)
            .where(IngestionBatchRecord.pipeline_name == pipeline_name)
            .order_by(IngestionBatchRecord.received_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        records = result.scalars().all()

        batches: list[IngestionBatch] = []
        for record in records:
            batches.append(IngestionBatch(
                batch_id=record.batch_id,
                pipeline_name=record.pipeline_name,
                source_type=record.source_type,  # type: ignore[arg-type]
                source_name=record.source_name,
                status=IngestionStatus(record.status),
                trigger_type=record.trigger_type,
                triggered_by=record.triggered_by,
                correlation_id=record.correlation_id,
                priority=record.priority,
                total_rows=record.total_rows,
                total_chunks=record.total_chunks,
                total_size_bytes=record.total_size_bytes,
                checksum_sha256=record.checksum_sha256,
                landing_path=record.landing_path,
                received_at=record.received_at,
                landed_at=record.landed_at,
                registered_at=record.registered_at,
                completed_at=record.completed_at,
                duration_seconds=record.duration_seconds,
                error_message=record.error_message,
                tags=record.tags or {},
                extra=record.extra_metadata or {},
            ))
        return batches
