"""
ETL Staging Repository - Data access for staging tables.

Provides bulk insert, upsert, truncate, and query operations
for each staging table. Uses SQLAlchemy async sessions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from etl.models.staging_models import StgAccount, StgBranch, StgCustomer, StgTransaction
from etl.schemas.staging_schemas import StagingTable


class StagingRepository:
    """Unified repository for all staging table operations.

    Provides type-safe bulk operations for each staging table
    with batch_id tracking for selective truncation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Generic Operations
    # ------------------------------------------------------------------

    async def bulk_insert(
        self,
        table: StagingTable,
        records: list[dict[str, Any]],
        batch_id: str,
    ) -> int:
        """Insert records into a staging table in bulk.

        Args:
            table: Target staging table.
            records: List of record dicts to insert.
            batch_id: Batch identifier for tracking.

        Returns:
            Number of rows inserted.
        """
        if not records:
            return 0

        model = self._get_model(table)
        enriched = [
            {**r, "batch_id": batch_id}
            for r in records
        ]
        stmt = insert(model).values(enriched)
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def bulk_insert_df(
        self,
        table: StagingTable,
        df: pd.DataFrame,
        batch_id: str,
    ) -> int:
        """Insert a DataFrame into a staging table.

        Args:
            table: Target staging table.
            df: DataFrame with matching column names.
            batch_id: Batch identifier.

        Returns:
            Number of rows inserted.
        """
        if df.empty:
            return 0
        records = df.where(pd.notna(df), None).to_dict(orient="records")
        return await self.bulk_insert(table, records, batch_id)

    async def truncate_table(
        self, table: StagingTable, batch_id: str | None = None
    ) -> int:
        """Truncate a staging table, optionally scoped to a batch.

        Args:
            table: Staging table to truncate.
            batch_id: If provided, only delete rows for this batch.

        Returns:
            Number of rows deleted.
        """
        model = self._get_model(table)
        if batch_id:
            stmt = delete(model).where(model.batch_id == batch_id)
        else:
            stmt = delete(model)
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def get_row_count(
        self, table: StagingTable, batch_id: str | None = None
    ) -> int:
        """Count rows in a staging table.

        Args:
            table: Staging table.
            batch_id: Optional batch filter.

        Returns:
            Row count.
        """
        model = self._get_model(table)
        stmt = select(func.count()).select_from(model)
        if batch_id:
            stmt = stmt.where(model.batch_id == batch_id)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def flush(self) -> None:
        """Flush pending changes to the database."""
        await self._session.flush()

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self._session.commit()

    # ------------------------------------------------------------------
    # Table-Specific Queries
    # ------------------------------------------------------------------

    async def get_staging_customers(
        self, batch_id: str | None = None, limit: int = 10000
    ) -> list[StgCustomer]:
        """Retrieve customer records from staging."""
        stmt = select(StgCustomer)
        if batch_id:
            stmt = stmt.where(StgCustomer.batch_id == batch_id)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_staging_transactions(
        self, batch_id: str | None = None, limit: int = 10000
    ) -> list[StgTransaction]:
        """Retrieve transaction records from staging."""
        stmt = select(StgTransaction)
        if batch_id:
            stmt = stmt.where(StgTransaction.batch_id == batch_id)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_staging_accounts(
        self, batch_id: str | None = None, limit: int = 10000
    ) -> list[StgAccount]:
        """Retrieve account records from staging."""
        stmt = select(StgAccount)
        if batch_id:
            stmt = stmt.where(StgAccount.batch_id == batch_id)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_staging_branches(
        self, batch_id: str | None = None, limit: int = 10000
    ) -> list[StgBranch]:
        """Retrieve branch records from staging."""
        stmt = select(StgBranch)
        if batch_id:
            stmt = stmt.where(StgBranch.batch_id == batch_id)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_model(table: StagingTable) -> type:
        """Map StagingTable enum to SQLAlchemy model class."""
        model_map = {
            StagingTable.CUSTOMER: StgCustomer,
            StagingTable.ACCOUNT: StgAccount,
            StagingTable.TRANSACTION: StgTransaction,
            StagingTable.BRANCH: StgBranch,
        }
        return model_map[table]
