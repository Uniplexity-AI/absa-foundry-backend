"""
Database Connectors - PostgreSQL, SQL Server, Oracle, MySQL.

Each database connector implements the DatabaseConnector interface,
providing connection management, query execution, and data extraction
with chunked/paginated streaming for large datasets.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from etl.connectors.factory import register_connector
from etl.connectors.interfaces import DatabaseConnector
from etl.schemas.connector_schemas import (
    BatchMetadata,
    ConnectorConfig,
    ConnectorInfo,
    Dataset,
    SourceType,
)


# ---------------------------------------------------------------------------
# Connection URL Builders
# ---------------------------------------------------------------------------

def _build_asyncpg_url(config: ConnectorConfig) -> str:
    """Build asyncpg connection URL for PostgreSQL."""
    return (
        f"postgresql+asyncpg://{config.username}:{config.password}"
        f"@{config.host}:{config.port}/{config.database}"
    )


def _build_aioodbc_url(config: ConnectorConfig, driver: str) -> str:
    """Build aioodbc connection URL for SQL Server / MySQL via ODBC."""
    return (
        f"mssql+aioodbc://{config.username}:{config.password}"
        f"@{config.host}:{config.port}/{config.database}"
        f"?driver={driver}"
    )


def _build_asyncmy_url(config: ConnectorConfig) -> str:
    """Build asyncmy connection URL for MySQL."""
    return (
        f"mysql+asyncmy://{config.username}:{config.password}"
        f"@{config.host}:{config.port}/{config.database}"
    )


# ---------------------------------------------------------------------------
# Base Async Database Connector
# ---------------------------------------------------------------------------

class AsyncDatabaseConnector(DatabaseConnector):
    """Base class for async SQLAlchemy-based database connectors.

    Provides common functionality: engine management, query execution
    with pagination, and table metadata inspection.
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._engine: AsyncEngine | None = None

    def _build_connection_url(self) -> str:
        """Build the database connection URL. Must be overridden by subclasses."""
        raise NotImplementedError

    async def connect(self) -> None:
        """Establish async database connection pool."""
        url = self._build_connection_url()
        self._engine = create_async_engine(
            url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            connect_args={"timeout": self.config.timeout_seconds},
        )
        # Verify connectivity
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        self._connected = True

    async def disconnect(self) -> None:
        """Dispose the database connection pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._connected = False

    async def validate_connection(self) -> bool:
        """Test if the database connection is alive."""
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from the database using the configured query.

        Paginates results in chunks of batch_size for memory efficiency.
        """
        if not self._connected or self._engine is None:
            raise RuntimeError("Cannot extract: connector is not connected.")

        batch_id = str(uuid.uuid4())
        query = self.config.query or f"SELECT * FROM {self.config.table_name}"
        offset = 0
        chunk_index = 0
        total_rows = 0

        metadata = BatchMetadata(
            batch_id=batch_id,
            source_type=self.config.source_type,
            source_name=self.config.source_name,
            extracted_at=datetime.now(timezone.utc),
            query_executed=query,
            total_chunks=0,
        )

        async with AsyncSession(self._engine) as session:
            while True:
                paginated_query = text(
                    f"{query} LIMIT {self.config.batch_size} OFFSET {offset}"
                )
                result = await session.execute(paginated_query)
                rows = result.fetchall()

                if not rows:
                    break

                columns = list(result.keys())
                df = pd.DataFrame(rows, columns=columns)
                total_rows += len(df)

                chunk_metadata = metadata.model_copy(update={
                    "total_rows": total_rows,
                    "total_chunks": chunk_index + 1,
                    "extraction_completed_at": None,
                })

                yield Dataset(
                    data=df,
                    metadata=chunk_metadata,
                    chunk_index=chunk_index,
                )

                if len(rows) < self.config.batch_size:
                    break

                offset += self.config.batch_size
                chunk_index += 1

        # Final metadata update
        metadata.total_rows = total_rows
        metadata.total_chunks = chunk_index + 1
        metadata.extraction_completed_at = datetime.now(timezone.utc)

    async def get_table_names(self) -> list[str]:
        """List all tables in the connected database."""
        if self._engine is None:
            raise RuntimeError("Not connected.")
        async with self._engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            return [row[0] for row in result.fetchall()]

    async def get_table_schema(self, table_name: str) -> dict[str, str]:
        """Get column names and types for a table."""
        if self._engine is None:
            raise RuntimeError("Not connected.")
        async with self._engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = :table_name",
            ), {"table_name": table_name})
            return {row[0]: row[1] for row in result.fetchall()}

    async def get_row_count(self, table_name: str) -> int:
        """Get approximate row count."""
        if self._engine is None:
            raise RuntimeError("Not connected.")
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            )
            return result.scalar() or 0


# ---------------------------------------------------------------------------
# PostgreSQL Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.POSTGRESQL,
    ConnectorInfo(
        source_type=SourceType.POSTGRESQL,
        display_name="PostgreSQL",
        description="Connector for PostgreSQL databases using asyncpg",
        supported_operations=["extract", "list_tables", "get_schema", "get_row_count"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class PostgresConnector(AsyncDatabaseConnector):
    """PostgreSQL database connector using asyncpg driver."""

    def _build_connection_url(self) -> str:
        if self.config.connection_string:
            url = self.config.connection_string
            if "postgresql+asyncpg" not in url:
                url = url.replace("postgresql://", "postgresql+asyncpg://")
            return url
        return _build_asyncpg_url(self.config)


# ---------------------------------------------------------------------------
# MySQL Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.MYSQL,
    ConnectorInfo(
        source_type=SourceType.MYSQL,
        display_name="MySQL",
        description="Connector for MySQL databases using asyncmy",
        supported_operations=["extract", "list_tables", "get_schema", "get_row_count"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class MySQLConnector(AsyncDatabaseConnector):
    """MySQL database connector using asyncmy driver."""

    def _build_connection_url(self) -> str:
        if self.config.connection_string:
            url = self.config.connection_string
            if "mysql+asyncmy" not in url:
                url = url.replace("mysql://", "mysql+asyncmy://")
            return url
        return _build_asyncmy_url(self.config)


# ---------------------------------------------------------------------------
# SQL Server Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.SQLSERVER,
    ConnectorInfo(
        source_type=SourceType.SQLSERVER,
        display_name="SQL Server",
        description="Connector for Microsoft SQL Server using aioodbc",
        supported_operations=["extract", "list_tables", "get_schema", "get_row_count"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class SqlServerConnector(AsyncDatabaseConnector):
    """SQL Server database connector using aioodbc + ODBC Driver 18."""

    def _build_connection_url(self) -> str:
        if self.config.connection_string:
            return self.config.connection_string
        return _build_aioodbc_url(self.config, "ODBC Driver 18 for SQL Server")


# ---------------------------------------------------------------------------
# Oracle Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.ORACLE,
    ConnectorInfo(
        source_type=SourceType.ORACLE,
        display_name="Oracle",
        description="Connector for Oracle Database using oracledb (thin mode)",
        supported_operations=["extract", "list_tables", "get_schema", "get_row_count"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class OracleConnector(AsyncDatabaseConnector):
    """Oracle database connector using python-oracledb in thin mode."""

    def _build_connection_url(self) -> str:
        if self.config.connection_string:
            return self.config.connection_string
        return (
            f"oracle+oracledb://{self.config.username}:{self.config.password}"
            f"@{self.config.host}:{self.config.port}/?service_name={self.config.database}"
        )
