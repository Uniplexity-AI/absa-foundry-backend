"""
ETL Connector Schemas - Pydantic v2 data models for connector I/O.

Defines the standardized data structures used by all connectors:
- ConnectorConfig: Source connection parameters
- BatchMetadata: Batch-level identifying information
- Dataset: The core data container (DataFrame + metadata)
- Various result/wrapper types for connector operations
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    """Supported data source categories."""
    POSTGRESQL = "postgresql"
    SQLSERVER = "sqlserver"
    ORACLE = "oracle"
    MYSQL = "mysql"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    XML = "xml"
    REST = "rest"
    SOAP = "soap"
    KAFKA = "kafka"          # Future
    DEBEZIUM = "debezium"    # Future
    CDC = "cdc"              # Future
    CORE_BANKING = "core_banking"


class ConnectionStatus(str, Enum):
    """Status of a connector's connection to its source."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class DatasetFormat(str, Enum):
    """Format of the data within a Dataset."""
    DATAFRAME = "dataframe"
    JSONL = "jsonl"
    ARROW = "arrow"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ConnectorConfig(BaseModel):
    """Configuration for a data source connector.

    Contains all parameters needed to connect to and extract from a source.
    Sensitive fields (passwords, tokens) should be loaded from environment
    variables or secrets manager, not hardcoded.
    """
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType = Field(
        description="Type of data source this connector targets",
    )
    source_name: str = Field(
        description="Human-readable name for this source (e.g., 'Core Banking DB')",
    )
    host: str | None = Field(
        default=None,
        description="Hostname or IP address of the source",
    )
    port: int | None = Field(
        default=None,
        description="Port number for the connection",
    )
    database: str | None = Field(
        default=None,
        description="Database name (for database connectors)",
    )
    username: str | None = Field(
        default=None,
        description="Username for authentication",
    )
    password: str | None = Field(
        default=None,
        description="Password for authentication (use secrets in production)",
    )
    connection_string: str | None = Field(
        default=None,
        description="Full connection string (alternative to individual params)",
    )
    query: str | None = Field(
        default=None,
        description="SQL query or API endpoint to execute",
    )
    table_name: str | None = Field(
        default=None,
        description="Table name to extract (database connectors)",
    )
    file_path: str | None = Field(
        default=None,
        description="File path or glob pattern (file connectors)",
    )
    file_pattern: str | None = Field(
        default=None,
        description="Glob pattern for matching multiple files",
    )
    api_base_url: str | None = Field(
        default=None,
        description="Base URL for API connectors",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for authentication (use secrets in production)",
    )
    batch_size: int = Field(
        default=10000,
        ge=1,
        le=1000000,
        description="Number of records per batch/chunk",
    )
    timeout_seconds: int = Field(
        default=300,
        ge=1,
        description="Connection and query timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for transient failures",
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional connector-specific parameters",
    )
    encoding: str = Field(
        default="utf-8",
        description="Character encoding for file-based sources",
    )
    has_header: bool = Field(
        default=True,
        description="Whether file-based sources include a header row",
    )
    delimiter: str = Field(
        default=",",
        description="Field delimiter for CSV sources",
    )

    @field_validator("source_name")
    @classmethod
    def source_name_must_not_be_empty(cls, v: str) -> str:
        """Validate source_name is non-empty and meaningful."""
        if not v or not v.strip():
            raise ValueError("source_name must not be empty")
        return v.strip()


# ---------------------------------------------------------------------------
# Batch Metadata
# ---------------------------------------------------------------------------

class BatchMetadata(BaseModel):
    """Metadata associated with a batch of extracted data.

    Provides full traceability: when, where, and how the data was extracted.
    Used by ingestion, audit, and checkpointing.
    """
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(
        description="Unique batch identifier (UUID v4)",
    )
    source_type: SourceType = Field(
        description="Type of the source system",
    )
    source_name: str = Field(
        description="Name of the source system",
    )
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when extraction began (UTC)",
    )
    extraction_completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when extraction completed (UTC)",
    )
    total_rows: int = Field(
        default=0,
        ge=0,
        description="Total number of rows extracted",
    )
    total_chunks: int = Field(
        default=0,
        ge=0,
        description="Total number of chunks/batches",
    )
    checksum_sha256: str | None = Field(
        default=None,
        description="SHA-256 checksum of the entire extracted dataset",
    )
    file_path: str | None = Field(
        default=None,
        description="Original file path (file connectors only)",
    )
    query_executed: str | None = Field(
        default=None,
        description="SQL query that was executed (database connectors only)",
    )
    api_endpoint: str | None = Field(
        default=None,
        description="API endpoint that was called (API connectors only)",
    )
    schema_version: str = Field(
        default="1.0.0",
        description="Schema version for this metadata structure",
    )
    connector_version: str = Field(
        default="1.0.0",
        description="Version of the connector that performed the extraction",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional connector-specific metadata",
    )


# ---------------------------------------------------------------------------
# Dataset — The Core Data Container
# ---------------------------------------------------------------------------

class Dataset(BaseModel):
    """Standardized data container output by all connectors.

    Wraps a pandas DataFrame with associated metadata. This is the
    universal format that all downstream ETL components consume.

    Note: The DataFrame is stored as a model field with arbitrary_types_allowed
    since pandas DataFrames are not natively supported by Pydantic.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    data: pd.DataFrame = Field(
        description="The extracted data as a pandas DataFrame",
    )
    metadata: BatchMetadata = Field(
        description="Metadata about this dataset batch",
    )
    chunk_index: int = Field(
        default=0,
        ge=0,
        description="Index of this chunk within the batch (0-based)",
    )
    format: DatasetFormat = Field(
        default=DatasetFormat.DATAFRAME,
        description="Format of the data in this dataset",
    )
    column_names: list[str] = Field(
        default_factory=list,
        description="Ordered list of column names in the DataFrame",
    )
    column_types: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of column_name → pandas dtype",
    )

    def model_post_init(self, __context: Any) -> None:
        """Auto-populate column_names and column_types from the DataFrame."""
        if self.data is not None and not self.data.empty:
            if not self.column_names:
                object.__setattr__(self, "column_names", list(self.data.columns))
            if not self.column_types:
                object.__setattr__(
                    self,
                    "column_types",
                    {col: str(dtype) for col, dtype in self.data.dtypes.items()},
                )

    @property
    def row_count(self) -> int:
        """Number of rows in this dataset chunk."""
        return len(self.data) if self.data is not None else 0

    @property
    def is_empty(self) -> bool:
        """Whether this dataset contains no data."""
        return self.row_count == 0


# ---------------------------------------------------------------------------
# Connection Test Result
# ---------------------------------------------------------------------------

class ConnectionTestResult(BaseModel):
    """Result of a connector connection validation test."""
    success: bool = Field(description="Whether the connection test passed")
    source_type: SourceType = Field(description="Type of source tested")
    source_name: str = Field(description="Name of source tested")
    latency_ms: float = Field(
        default=0.0,
        description="Connection latency in milliseconds",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if the test failed",
    )
    tested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the connection test was performed",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional diagnostic details",
    )


# ---------------------------------------------------------------------------
# Connector Factory Input
# ---------------------------------------------------------------------------

class ConnectorCreateRequest(BaseModel):
    """Request to create/instantiate a connector via the factory."""
    source_type: SourceType = Field(description="Type of connector to create")
    config: ConnectorConfig = Field(description="Connector configuration")


class ConnectorInfo(BaseModel):
    """Information about an available/registered connector."""
    source_type: SourceType
    display_name: str
    description: str
    supported_operations: list[str]
    version: str
    is_implemented: bool = Field(
        default=True,
        description="Whether this connector is fully implemented",
    )
