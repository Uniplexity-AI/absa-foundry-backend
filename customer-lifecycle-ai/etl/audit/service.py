"""
ETL Audit Service - Compliance audit trail management.

Records complete batch lifecycle for every ETL run:
source, timing, row counts, quality, duplicates, operator.

All audit records are immutable — write-once, never modified.
Required for banking compliance and regulatory reporting.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from etl.models.audit_models import AuditRecord as AuditRecordORM
from etl.schemas.audit_schemas import AuditConfig, AuditRecord


class AuditService:
    """Immutable audit trail for ETL batch processing.

    Every batch processed by the ETL engine generates an
    audit record that is never modified — append-only for
    regulatory compliance.
    """

    def __init__(
        self,
        session: AsyncSession,
        config: AuditConfig | None = None,
    ) -> None:
        self._session = session
        self.config = config or AuditConfig()

    async def create_audit_record(self, record: AuditRecord) -> AuditRecord:
        """Create an immutable audit record.

        Args:
            record: Complete audit record for a batch.

        Returns:
            The persisted AuditRecord.

        Raises:
            ValueError: If audit is disabled.
        """
        if not self.config.enabled:
            raise ValueError("Audit trail is disabled")

        record.audit_id = record.audit_id or str(uuid.uuid4())

        orm = AuditRecordORM(
            audit_id=record.audit_id,
            batch_id=record.batch_id,
            source_type=record.source_type,
            source_name=record.source_name,
            pipeline_name=record.pipeline_name,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_seconds=record.duration_seconds,
            rows_received=record.rows_received,
            rows_valid=record.rows_valid,
            rows_rejected=record.rows_rejected,
            rows_loaded=record.rows_loaded,
            rows_skipped=record.rows_skipped,
            duplicates_detected=record.duplicates_detected,
            warnings_count=record.warnings_count,
            errors_count=record.errors_count,
            quality_score=record.quality_score,
            status=record.status,
            error_message=record.error_message,
            triggered_by=record.triggered_by,
            operator_id=record.operator_id,
            tags=record.tags,
            extra=record.extra,
        )
        self._session.add(orm)
        await self._session.flush()

        return record

    async def get_audit_record(
        self, batch_id: str
    ) -> AuditRecord | None:
        """Retrieve audit record by batch ID.

        Args:
            batch_id: Batch identifier.

        Returns:
            AuditRecord if found, None otherwise.
        """
        stmt = select(AuditRecordORM).where(
            AuditRecordORM.batch_id == batch_id
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._orm_to_schema(orm) if orm else None

    async def list_recent_batches(
        self, limit: int = 100
    ) -> list[AuditRecord]:
        """List most recent batch audit records.

        Args:
            limit: Maximum records to return.

        Returns:
            List of AuditRecords ordered by creation time descending.
        """
        stmt = (
            select(AuditRecordORM)
            .order_by(AuditRecordORM.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._orm_to_schema(r) for r in result.scalars().all()]

    @staticmethod
    def _orm_to_schema(orm: AuditRecordORM) -> AuditRecord:
        """Convert ORM model to Pydantic schema."""
        return AuditRecord(
            audit_id=orm.audit_id,
            batch_id=orm.batch_id,
            source_type=orm.source_type,
            source_name=orm.source_name,
            pipeline_name=orm.pipeline_name,
            started_at=orm.started_at,
            completed_at=orm.completed_at,
            duration_seconds=orm.duration_seconds,
            rows_received=orm.rows_received,
            rows_valid=orm.rows_valid,
            rows_rejected=orm.rows_rejected,
            rows_loaded=orm.rows_loaded,
            rows_skipped=orm.rows_skipped,
            duplicates_detected=orm.duplicates_detected,
            warnings_count=orm.warnings_count,
            errors_count=orm.errors_count,
            quality_score=orm.quality_score,
            status=orm.status,
            error_message=orm.error_message,
            triggered_by=orm.triggered_by,
            operator_id=orm.operator_id,
            tags=orm.tags or {},
            extra=orm.extra or {},
        )
