"""
ETL Landing Zone Repository - Database persistence for landing file records.

Implements the LandingFileRepository protocol for tracking
every file written to the immutable landing zone.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from etl.landing.interfaces import LandingFileRepository
from etl.models.landing_models import LandingFileRecord as LandingFileORM
from etl.schemas.landing_schemas import LandingFileRecord, LandingFileStatus


class LandingFileSqlRepository:
    """SQLAlchemy-based repository for landing file metadata.

    Implements the LandingFileRepository protocol.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with an async SQLAlchemy session.

        Args:
            session: Active async database session.
        """
        self._session = session

    async def save_file_record(self, record: LandingFileRecord) -> None:
        """Persist a landing file metadata record.

        Args:
            record: The file record to save.
        """
        orm = LandingFileORM(
            file_id=record.file_id,
            batch_id=record.batch_id,
            chunk_index=record.chunk_index,
            file_name=record.file_name,
            file_path=record.file_path,
            file_format=record.file_format.value,
            file_size_bytes=record.file_size_bytes,
            row_count=record.row_count,
            checksum_sha256=record.checksum_sha256,
            status=record.status.value,
            column_names=record.column_names,
            column_types=record.column_types,
            verified_at=record.verified_at,
            source_type=record.source_type,
            source_name=record.source_name,
            compression=record.compression,
            tags=record.tags,
        )
        self._session.add(orm)
        await self._session.flush()

    async def update_file_status(
        self, file_id: str, status: str, verified_at: object | None = None
    ) -> None:
        """Update a file's status.

        Args:
            file_id: The file identifier.
            status: New status value.
            verified_at: Optional verification timestamp.
        """
        values: dict[str, object] = {"status": status}
        if verified_at is not None:
            values["verified_at"] = verified_at

        stmt = (
            update(LandingFileORM)
            .where(LandingFileORM.file_id == file_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_file_record(
        self, file_id: str
    ) -> LandingFileRecord | None:
        """Retrieve a file record by ID.

        Args:
            file_id: The file identifier.

        Returns:
            LandingFileRecord if found, None otherwise.
        """
        stmt = select(LandingFileORM).where(LandingFileORM.file_id == file_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()

        if orm is None:
            return None

        return self._orm_to_schema(orm)

    async def list_files_by_batch(
        self, batch_id: str
    ) -> list[LandingFileRecord]:
        """List all files belonging to a batch.

        Args:
            batch_id: The batch identifier.

        Returns:
            List of landing file records ordered by chunk_index.
        """
        stmt = (
            select(LandingFileORM)
            .where(LandingFileORM.batch_id == batch_id)
            .order_by(LandingFileORM.chunk_index)
        )
        result = await self._session.execute(stmt)
        orms = result.scalars().all()
        return [self._orm_to_schema(o) for o in orms]

    @staticmethod
    def _orm_to_schema(orm: LandingFileORM) -> LandingFileRecord:
        """Convert ORM model to Pydantic schema.

        Args:
            orm: SQLAlchemy ORM instance.

        Returns:
            LandingFileRecord schema.
        """
        return LandingFileRecord(
            file_id=orm.file_id,
            batch_id=orm.batch_id,
            chunk_index=orm.chunk_index,
            file_name=orm.file_name,
            file_path=orm.file_path,
            file_format=LandingFileFormat(orm.file_format),
            file_size_bytes=orm.file_size_bytes,
            row_count=orm.row_count,
            checksum_sha256=orm.checksum_sha256,
            status=LandingFileStatus(orm.status),
            column_names=orm.column_names or [],
            column_types=orm.column_types or {},
            created_at=orm.created_at,
            verified_at=orm.verified_at,
            source_type=orm.source_type,
            source_name=orm.source_name,
            compression=orm.compression,
            tags=orm.tags or {},
        )
