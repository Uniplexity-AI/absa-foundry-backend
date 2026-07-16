"""
ETL Landing Zone Interfaces - Abstract contracts for landing zone storage.

Defines the interfaces for writing to and reading from the
immutable landing zone. Implements the LandingZoneWriter protocol
from the ingestion module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

import pandas as pd

from etl.schemas.connector_schemas import Dataset
from etl.schemas.landing_schemas import LandingFileRecord, LandingPath


class LandingZoneReader(ABC):
    """Abstract interface for reading data from the landing zone.

    Downstream modules (validation, transformation) use this
    to access raw immutable data without direct filesystem access.
    """

    @abstractmethod
    async def read_dataset(self, path: LandingPath) -> pd.DataFrame:
        """Read a full dataset from the landing zone.

        Args:
            path: Structured path to the dataset.

        Returns:
            DataFrame containing the raw data.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        ...

    @abstractmethod
    async def read_chunk(
        self, path: LandingPath, chunk_index: int
    ) -> pd.DataFrame:
        """Read a specific chunk from a batch.

        Args:
            path: Structured path to the batch directory.
            chunk_index: Zero-based chunk index.

        Returns:
            DataFrame containing the chunk data.

        Raises:
            FileNotFoundError: If the chunk does not exist.
        """
        ...

    @abstractmethod
    async def list_batches(
        self, year: int, month: int, day: int
    ) -> list[str]:
        """List all batch IDs for a given date partition.

        Args:
            year: Partition year.
            month: Partition month.
            day: Partition day.

        Returns:
            List of batch IDs.
        """
        ...

    @abstractmethod
    async def list_chunks(self, batch_id: str) -> list[str]:
        """List all chunk file names for a batch.

        Args:
            batch_id: The batch identifier.

        Returns:
            List of chunk file names.
        """
        ...

    @abstractmethod
    async def file_exists(self, path: LandingPath) -> bool:
        """Check if a file exists in the landing zone.

        Args:
            path: Structured path to check.

        Returns:
            True if the file exists.
        """
        ...


class LandingFileRepository(Protocol):
    """Protocol for persisting landing file metadata.

    Tracks every file written to the landing zone in the database.
    """

    async def save_file_record(self, record: LandingFileRecord) -> None:
        """Persist a landing file metadata record.

        Args:
            record: The file record to save.
        """
        ...

    async def update_file_status(
        self, file_id: str, status: str, verified_at: object | None = None
    ) -> None:
        """Update a file's status after verification.

        Args:
            file_id: The file identifier.
            status: New status value.
            verified_at: Optional verification timestamp.
        """
        ...

    async def get_file_record(
        self, file_id: str
    ) -> LandingFileRecord | None:
        """Retrieve a file record by ID.

        Args:
            file_id: The file identifier.

        Returns:
            LandingFileRecord if found, None otherwise.
        """
        ...

    async def list_files_by_batch(
        self, batch_id: str
    ) -> list[LandingFileRecord]:
        """List all files belonging to a batch.

        Args:
            batch_id: The batch identifier.

        Returns:
            List of landing file records.
        """
        ...
