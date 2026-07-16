"""
ETL Connectors - Base interfaces and abstract classes.

Defines the common contract that all data source connectors must implement.
Every connector outputs a standardized format: Dataset + BatchMetadata.

Architecture:
    Connector (ABC)
    ├── DatabaseConnector (ABC)
    │   ├── PostgresConnector
    │   ├── SqlServerConnector
    │   ├── OracleConnector
    │   └── MySQLConnector
    ├── FileConnector (ABC)
    │   ├── CsvConnector
    │   ├── ExcelConnector
    │   ├── JsonConnector
    │   └── XmlConnector
    ├── ApiConnector (ABC)
    │   ├── RestConnector
    │   └── SoapConnector
    └── StreamingConnector (ABC)  # Future: Kafka, Debezium, CDC
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import pandas as pd

from etl.schemas.connector_schemas import BatchMetadata, ConnectorConfig, Dataset


class Connector(ABC):
    """Abstract base class for all data source connectors.

    All connectors must implement extract() which returns a standardized
    Dataset with associated BatchMetadata. This ensures downstream
    components (ingestion, validation, transformation) operate on a
    consistent format regardless of source type.
    """

    def __init__(self, config: ConnectorConfig) -> None:
        """Initialize the connector with its configuration.

        Args:
            config: Connector configuration including source type,
                    connection parameters, and extraction settings.
        """
        self.config = config
        self._connected: bool = False

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source.

        Must be called before extract(). Implementations should set
        self._connected = True on success.

        Raises:
            ConnectionError: If connection to the source fails.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the data source.

        Should be idempotent — safe to call multiple times.
        Implementations should set self._connected = False.
        """
        ...

    @abstractmethod
    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from the source as standardized Datasets.

        Yields Dataset objects, each containing a pandas DataFrame
        and associated metadata. Supports streaming large datasets
        by yielding in chunks.

        Yields:
            Dataset: Standardized data container with DataFrame and metadata.

        Raises:
            RuntimeError: If called before connect().
            ExtractionError: If data extraction fails.
        """
        ...

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Test whether the connection to the source is valid.

        Returns:
            True if connection is healthy, False otherwise.
        """
        ...

    async def __aenter__(self) -> Connector:
        """Async context manager entry — calls connect()."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit — calls disconnect()."""
        await self.disconnect()


class DatabaseConnector(Connector, ABC):
    """Abstract base for database-backed connectors.

    Provides common database functionality: connection pooling,
    query execution, pagination for large result sets.
    """

    @abstractmethod
    async def get_table_names(self) -> list[str]:
        """List all available tables in the connected database.

        Returns:
            List of table names (schema.table format where applicable).
        """
        ...

    @abstractmethod
    async def get_table_schema(self, table_name: str) -> dict[str, str]:
        """Retrieve column names and their data types for a table.

        Args:
            table_name: Fully qualified table name.

        Returns:
            Dict mapping column_name → data_type.
        """
        ...

    @abstractmethod
    async def get_row_count(self, table_name: str) -> int:
        """Get approximate or exact row count for a table.

        Args:
            table_name: Fully qualified table name.

        Returns:
            Number of rows in the table.
        """
        ...


class FileConnector(Connector, ABC):
    """Abstract base for file-based connectors.

    Provides common file operations: path resolution, glob support,
    encoding detection, file size validation.
    """

    @abstractmethod
    async def list_files(self) -> list[str]:
        """List all files matching the configured path pattern.

        Returns:
            List of absolute file paths.
        """
        ...

    @abstractmethod
    async def get_file_metadata(self, file_path: str) -> dict[str, Any]:
        """Retrieve metadata for a specific file.

        Args:
            file_path: Absolute path to the file.

        Returns:
            Dict with keys: size_bytes, modified_at, encoding, row_count (if known).
        """
        ...


class ApiConnector(Connector, ABC):
    """Abstract base for API-based connectors.

    Provides common API operations: authentication, pagination,
    rate limiting, retry logic.
    """

    @abstractmethod
    async def get_endpoints(self) -> list[str]:
        """List available API endpoints.

        Returns:
            List of endpoint paths.
        """
        ...

    @abstractmethod
    async def get_schema(self, endpoint: str) -> dict[str, Any]:
        """Retrieve the schema/structure for an API endpoint response.

        Args:
            endpoint: API endpoint path.

        Returns:
            Schema definition (OpenAPI-style or similar).
        """
        ...


class StreamingConnector(Connector, ABC):
    """Abstract base for streaming connectors (future).

    Reserved for Kafka, Debezium, CDC, and other event-stream sources.
    Not implemented in Phase 2 — placeholder for future extension.
    """

    @abstractmethod
    async def subscribe(self, topic: str) -> None:
        """Subscribe to a streaming topic.

        Args:
            topic: Topic/stream name to subscribe to.
        """
        ...

    @abstractmethod
    async def consume(self) -> AsyncIterator[Dataset]:
        """Consume messages from the subscribed stream.

        Yields:
            Dataset objects from the stream.
        """
        ...
