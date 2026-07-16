"""
ETL Staging Service - Orchestrates writes to staging tables.

Loads validated and transformed data into staging tables,
ready for the production loader to pick up. Never loads
directly into production.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from etl.schemas.staging_schemas import (
    StagingConfig,
    StagingLoadResult,
    StagingLoadStatus,
    StagingTable,
)
from etl.staging.repository import StagingRepository


class StagingService:
    """Service for loading data into staging tables.

    Maps transformed DataFrames to staging table columns and
    performs bulk inserts with batch tracking.
    """

    def __init__(
        self,
        repository: StagingRepository,
        config: StagingConfig | None = None,
    ) -> None:
        self._repo = repository
        self.config = config or StagingConfig()

    async def load_customers(
        self, df: pd.DataFrame, batch_id: str
    ) -> StagingLoadResult:
        """Load customer data into stg_customer.

        Args:
            df: DataFrame with customer data.
            batch_id: Batch identifier.

        Returns:
            StagingLoadResult with load statistics.
        """
        return await self._load_table(df, batch_id, StagingTable.CUSTOMER)

    async def load_accounts(
        self, df: pd.DataFrame, batch_id: str
    ) -> StagingLoadResult:
        """Load account data into stg_account."""
        return await self._load_table(df, batch_id, StagingTable.ACCOUNT)

    async def load_transactions(
        self, df: pd.DataFrame, batch_id: str
    ) -> StagingLoadResult:
        """Load transaction data into stg_transaction."""
        return await self._load_table(df, batch_id, StagingTable.TRANSACTION)

    async def load_branches(
        self, df: pd.DataFrame, batch_id: str
    ) -> StagingLoadResult:
        """Load branch data into stg_branch."""
        return await self._load_table(df, batch_id, StagingTable.BRANCH)

    async def truncate_all(self, batch_id: str | None = None) -> dict[str, int]:
        """Truncate all staging tables, optionally scoped to batch.

        Args:
            batch_id: Optional batch scope.

        Returns:
            Dict of table_name → rows_deleted.
        """
        results: dict[str, int] = {}
        for table in StagingTable:
            count = await self._repo.truncate_table(table, batch_id)
            results[table.value] = count
        return results

    async def get_load_status(
        self, batch_id: str
    ) -> dict[str, int]:
        """Get row counts for all staging tables for a batch.

        Args:
            batch_id: Batch identifier.

        Returns:
            Dict of table_name → row_count.
        """
        status: dict[str, int] = {}
        for table in StagingTable:
            count = await self._repo.get_row_count(table, batch_id)
            status[table.value] = count
        return status

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _load_table(
        self,
        df: pd.DataFrame,
        batch_id: str,
        table: StagingTable,
    ) -> StagingLoadResult:
        """Generic load operation for any staging table.

        Args:
            df: DataFrame to load.
            batch_id: Batch identifier.
            table: Target staging table.

        Returns:
            StagingLoadResult.
        """
        start = time.monotonic()
        result = StagingLoadResult(
            batch_id=batch_id,
            table=table,
            status=StagingLoadStatus.LOADING,
            started_at=datetime.now(timezone.utc),
        )

        try:
            if df.empty:
                result.status = StagingLoadStatus.LOADED
                result.completed_at = datetime.now(timezone.utc)
                return result

            # Normalize column names to match ORM attributes
            df = self._normalize_columns(df, table)

            rows = await self._repo.bulk_insert_df(table, df, batch_id)
            await self._repo.flush()

            result.rows_loaded = rows
            result.status = StagingLoadStatus.LOADED
            result.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            result.status = StagingLoadStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(timezone.utc)

        return result

    @staticmethod
    def _normalize_columns(df: pd.DataFrame, table: StagingTable) -> pd.DataFrame:
        """Normalize DataFrame columns to match staging ORM attributes.

        Strips the table prefix and lowercases. E.g., 'StgCustomer.customer_id' → 'customer_id'

        Args:
            df: Source DataFrame.
            table: Target table.

        Returns:
            DataFrame with normalized column names.
        """
        # Simple lowercase normalization
        df = df.copy()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        return df
