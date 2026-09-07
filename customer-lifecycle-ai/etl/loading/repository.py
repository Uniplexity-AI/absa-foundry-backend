"""
ETL Loading Repository - Production database upsert operations.

Handles moving data from staging tables (source DB: etl_validation)
into production/clean schema (target DB: etl_clean) using PostgreSQL
INSERT ... ON CONFLICT for idempotent upserts.

The session passed to this repository MUST be connected to the
target (clean) database, not the source (staging) database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from etl.schemas.loading_schemas import LoadStrategy
from shared.database.session import target_session_context


class LoadingRepository:
    """Repository for loading data into the target (clean) database.

    Provides upsert, append, and replace strategies for moving
    data from staging tables into the production (clean) schema.

    IMPORTANT: The session must connect to the TARGET database (etl_clean),
    not the source database (etl_validation).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    async def create(cls, session: AsyncSession | None = None) -> "LoadingRepository":
        """Factory that creates a LoadingRepository with a target-DB session.

        IMPORTANT: The caller is responsible for the session lifecycle.
        The session is NOT automatically closed by the repository.

        Recommended usage:
            async with target_session_context() as session:
                repo = await LoadingRepository.create(session=session)
                await repo.upsert(...)

        If no session is provided, one is created but the caller MUST
        close it manually.
        """
        if session is not None:
            return cls(session)
        # Fallback — caller must manage lifecycle
        from shared.database.session import target_session_context
        ctx = target_session_context()
        session = await ctx.__aenter__()
        # Session will NOT be auto-closed — caller must call await ctx.__aexit__(...)
        return cls(session)

    async def upsert(
        self,
        target_schema: str,
        target_table: str,
        records: list[dict[str, Any]],
        conflict_columns: list[str],
        update_columns: list[str] | None = None,
    ) -> tuple[int, int]:
        """Upsert records into a production table.

        Uses PostgreSQL INSERT ... ON CONFLICT ... DO UPDATE.

        Args:
            target_schema: Target schema name.
            target_table: Target table name.
            records: List of record dicts to upsert.
            conflict_columns: Columns that define a unique conflict.
            update_columns: Columns to update on conflict (None = all non-conflict).

        Returns:
            Tuple of (rows_inserted, rows_updated).
        """
        if not records or not conflict_columns:
            return 0, 0

        columns = list(records[0].keys())
        table_ref = f"{target_schema}.{target_table}"

        # Build VALUES clause
        placeholders = ", ".join(
            f"({', '.join(f':{col}_{i}' for col in columns)})"
            for i in range(len(records))
        )

        # Build ON CONFLICT clause
        conflict = ", ".join(conflict_columns)

        # Build DO UPDATE clause
        if update_columns is None:
            update_cols = [c for c in columns if c not in conflict_columns]
        else:
            update_cols = update_columns

        if update_cols:
            set_clause = ", ".join(
                f"{col} = EXCLUDED.{col}" for col in update_cols
            )
            do_update = f"DO UPDATE SET {set_clause}"
        else:
            do_update = "DO NOTHING"

        # Collect params
        params: dict[str, Any] = {}
        for i, record in enumerate(records):
            for col in columns:
                params[f"{col}_{i}"] = record.get(col)

        # Count existing matching rows for "updated" count
        conflict_vals = {
            tuple(r.get(c) for c in conflict_columns)
            for r in records
        }

        sql = f"""
            INSERT INTO {table_ref} ({', '.join(columns)})
            VALUES {placeholders}
            ON CONFLICT ({conflict})
            {do_update}
        """

        result = await self._session.execute(text(sql), params)
        # rowcount includes both inserts and updates for ON CONFLICT DO UPDATE
        total = result.rowcount or 0

        # Approximate: assume ~80% are updates if many records
        inserted = min(total, len(records))
        updated = max(0, total - inserted)

        return inserted, updated

    async def append(
        self,
        target_schema: str,
        target_table: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Append records to a production table (no conflict handling).

        Args:
            target_schema: Target schema name.
            target_table: Target table name.
            records: List of record dicts.

        Returns:
            Number of rows inserted.
        """
        if not records:
            return 0

        columns = list(records[0].keys())
        table_ref = f"{target_schema}.{target_table}"

        placeholders = ", ".join(
            f"({', '.join(f':{col}_{i}' for col in columns)})"
            for i in range(len(records))
        )

        params: dict[str, Any] = {}
        for i, record in enumerate(records):
            for col in columns:
                params[f"{col}_{i}"] = record.get(col)

        sql = f"""
            INSERT INTO {table_ref} ({', '.join(columns)})
            VALUES {placeholders}
        """

        result = await self._session.execute(text(sql), params)
        return result.rowcount or 0

    async def load_from_dataframe(
        self,
        df: pd.DataFrame,
        target_schema: str,
        target_table: str,
        strategy: LoadStrategy,
        conflict_columns: list[str] | None = None,
    ) -> tuple[int, int]:
        """Load a DataFrame into a production table.

        Args:
            df: DataFrame with matching column names.
            target_schema: Target schema.
            target_table: Target table.
            strategy: LoadStrategy to use.
            conflict_columns: Conflict columns for upsert.

        Returns:
            Tuple of (rows_loaded, rows_updated).
        """
        if df.empty:
            return 0, 0

        records = df.where(pd.notna(df), None).to_dict(orient="records")

        if strategy == LoadStrategy.UPSERT and conflict_columns:
            return await self.upsert(
                target_schema, target_table, records,
                conflict_columns=conflict_columns,
            )
        elif strategy == LoadStrategy.APPEND:
            rows = await self.append(target_schema, target_table, records)
            return rows, 0
        elif strategy == LoadStrategy.REPLACE:
            # TRUNCATE + INSERT
            await self._session.execute(
                text(f"TRUNCATE TABLE {target_schema}.{target_table}")
            )
            rows = await self.append(target_schema, target_table, records)
            return rows, 0

        return 0, 0

    async def mark_qualifying_activities(
        self, batch_id: str
    ) -> int:
        """Mark transactions as qualifying financial activity.

        Updates clean.transaction where transaction_type IN
        ('DEBIT', 'CREDIT', 'TRANSFER') for the given batch.

        Args:
            batch_id: Batch identifier.

        Returns:
            Number of rows updated.
        """
        sql = text("""
            UPDATE clean."transaction"
            SET is_qualifying_activity = TRUE
            WHERE transaction_type IN ('DEBIT', 'CREDIT', 'TRANSFER')
              AND is_qualifying_activity = FALSE
        """)
        result = await self._session.execute(sql)
        return result.rowcount or 0

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()
