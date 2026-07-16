"""
ETL Ingestion Interfaces - Abstract contracts for the ingestion layer.

Defines the interfaces that the ingestion service and its dependencies
must implement. Enables testability through dependency injection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from etl.connectors.interfaces import Connector
from etl.schemas.connector_schemas import Dataset
from etl.schemas.ingestion_schemas import IngestionBatch, IngestionRequest, IngestionResult


class LandingZoneWriter(Protocol):
    """Protocol for writing raw data to the landing zone.

    Any implementation that writes Dataset contents to immutable
    storage conforms to this protocol. Enables swapping between
    local filesystem, S3, HDFS, etc.
    """

    async def write_dataset(self, dataset: Dataset, batch_id: str) -> str:
        """Write a dataset to the landing zone.

        Args:
            dataset: The dataset to persist.
            batch_id: The batch ID for path partitioning.

        Returns:
            Absolute path where the data was stored.
        """
        ...

    async def write_chunk(
        self, dataset: Dataset, batch_id: str, chunk_index: int
    ) -> str:
        """Write a single chunk within a batch.

        Args:
            dataset: The chunk dataset.
            batch_id: Parent batch ID.
            chunk_index: Zero-based chunk index.

        Returns:
            Absolute path where the chunk was stored.
        """
        ...


class IngestionRepository(Protocol):
    """Protocol for persisting ingestion metadata.

    Abstracts database operations for ingestion batch and chunk records.
    """

    async def save_batch(self, batch: IngestionBatch) -> None:
        """Persist an ingestion batch record.

        Args:
            batch: The batch metadata to save.
        """
        ...

    async def update_batch_status(
        self, batch_id: str, status: str, **kwargs: object
    ) -> None:
        """Update the status and optional fields of a batch.

        Args:
            batch_id: The batch to update.
            status: New status value.
            **kwargs: Additional fields to update.
        """
        ...

    async def get_batch(self, batch_id: str) -> IngestionBatch | None:
        """Retrieve a batch by its ID.

        Args:
            batch_id: The batch ID to look up.

        Returns:
            IngestionBatch if found, None otherwise.
        """
        ...

    async def save_chunk(
        self, batch_id: str, chunk_index: int, row_count: int,
        size_bytes: int, checksum: str | None, chunk_path: str | None,
        column_names: list[str] | None, column_types: dict[str, str] | None,
    ) -> None:
        """Persist a chunk record.

        Args:
            batch_id: Parent batch ID.
            chunk_index: Zero-based chunk index.
            row_count: Rows in this chunk.
            size_bytes: Size in bytes.
            checksum: SHA-256 checksum.
            chunk_path: Path in landing zone.
            column_names: Column name list.
            column_types: Column type mapping.
        """
        ...


class IngestionEventEmitter(Protocol):
    """Protocol for emitting events after ingestion.

    Enables decoupled communication with downstream services
    (validation engine, monitoring, audit).
    """

    async def emit_ingestion_completed(self, batch: IngestionBatch) -> None:
        """Emit an event when ingestion completes successfully.

        Args:
            batch: The completed ingestion batch.
        """
        ...

    async def emit_ingestion_failed(
        self, batch_id: str, error: str
    ) -> None:
        """Emit an event when ingestion fails.

        Args:
            batch_id: The failed batch ID.
            error: Error message.
        """
        ...


class IngestionServiceInterface(ABC):
    """Abstract interface for the ingestion service.

    The ingestion service orchestrates the end-to-end flow:
    connect → extract → checksum → land → register → emit event.
    """

    @abstractmethod
    async def ingest(self, request: IngestionRequest) -> IngestionResult:
        """Execute the full ingestion pipeline for a source.

        Args:
            request: Ingestion configuration and metadata.

        Returns:
            IngestionResult summarizing what was ingested.

        Raises:
            IngestionError: If any step in the ingestion pipeline fails.
        """
        ...
