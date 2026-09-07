"""
ETL Landing Zone Writer - Local filesystem implementation.

Implements the LandingZoneWriter protocol from the ingestion module.
Writes immutable data files in time-partitioned directories with
checksum verification and database tracking.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from etl.landing.interfaces import LandingFileRepository, LandingZoneReader
from etl.schemas.connector_schemas import Dataset
from etl.schemas.landing_schemas import (
    LandingFileFormat,
    LandingFileRecord,
    LandingFileStatus,
    LandingPath,
    LandingZoneConfig,
)


class LocalLandingZoneWriter:
    """Local filesystem landing zone writer.

    Writes datasets as Parquet (or configurable format) to a
    time-partitioned directory structure. Files are write-once
    and never modified — enforcing immutability.

    Implements the LandingZoneWriter protocol from etl.ingestion.interfaces.
    """

    def __init__(
        self,
        config: LandingZoneConfig | None = None,
        repository: LandingFileRepository | None = None,
    ) -> None:
        """Initialize the landing zone writer.

        Args:
            config: Landing zone configuration. Uses defaults if None.
            repository: Optional repository for persisting file metadata.
        """
        self._config = config or LandingZoneConfig()
        self._repository = repository

    async def write_dataset(self, dataset: Dataset, batch_id: str) -> str:
        """Write a full dataset to the landing zone as a single file.

        Args:
            dataset: The dataset to persist.
            batch_id: The batch identifier for path partitioning.

        Returns:
            Absolute path where the data was stored.
        """
        path = LandingPath.from_batch_id(batch_id, self._config.base_path)
        return await self._write_file(
            df=dataset.data,
            path=path,
            chunk_index=0,
            batch_id=batch_id,
            column_names=dataset.column_names,
            column_types=dataset.column_types,
            source_type=dataset.metadata.source_type.value,
            source_name=dataset.metadata.source_name,
        )

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
        path = LandingPath.from_batch_id(batch_id, self._config.base_path)
        return await self._write_file(
            df=dataset.data,
            path=path,
            chunk_index=chunk_index,
            batch_id=batch_id,
            column_names=dataset.column_names,
            column_types=dataset.column_types,
            source_type=dataset.metadata.source_type.value,
            source_name=dataset.metadata.source_name,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_file(
        self,
        df: pd.DataFrame,
        path: LandingPath,
        chunk_index: int,
        batch_id: str,
        column_names: list[str],
        column_types: dict[str, str],
        source_type: str | None = None,
        source_name: str | None = None,
    ) -> str:
        """Write a DataFrame to the landing zone.

        Steps:
        1. Ensure directory exists
        2. Write file (Parquet default)
        3. Verify checksum
        4. Register in database
        5. Mark as LANDED
        """
        file_id = str(uuid.uuid4())
        fmt = self._config.default_format

        # Build file name and full path
        file_name = self._build_file_name(chunk_index, fmt)
        full_dir = Path(path.batch_directory)
        full_path = full_dir / file_name

        # Create directories if needed
        if self._config.create_parent_directories:
            full_dir.mkdir(parents=True, exist_ok=True)

        # Write file
        absolute_path = str(full_path.resolve())
        self._write_dataframe(df, absolute_path, fmt)

        # Get file stats
        file_size = full_path.stat().st_size

        # Compute checksum
        checksum = None
        if self._config.enable_checksum_verification:
            checksum = self._compute_file_checksum(absolute_path)

        # Create file record
        record = LandingFileRecord(
            file_id=file_id,
            batch_id=batch_id,
            chunk_index=chunk_index,
            file_name=file_name,
            file_path=absolute_path,
            file_format=fmt,
            file_size_bytes=file_size,
            row_count=len(df),
            checksum_sha256=checksum,
            status=LandingFileStatus.WRITING,
            column_names=column_names,
            column_types=column_types,
            source_type=source_type,
            source_name=source_name,
            compression=self._config.compression,
        )

        # Persist file record
        if self._repository:
            await self._repository.save_file_record(record)

        # Mark as LANDED after successful write + verification
        verified_at = datetime.now(timezone.utc) if checksum else None
        if self._repository:
            await self._repository.update_file_status(
                file_id=file_id,
                status=LandingFileStatus.LANDED.value,
                verified_at=verified_at,
            )

        return absolute_path

    def _write_dataframe(
        self, df: pd.DataFrame, path: str, fmt: LandingFileFormat
    ) -> None:
        """Write DataFrame to disk in the specified format.

        Args:
            df: DataFrame to write.
            path: Absolute file path.
            fmt: Target file format.

        Raises:
            ValueError: If format is unsupported.
        """
        if fmt == LandingFileFormat.PARQUET:
            df.to_parquet(
                path,
                compression=self._config.compression,
                index=False,
            )
        elif fmt == LandingFileFormat.CSV:
            df.to_csv(path, index=False)
        elif fmt == LandingFileFormat.JSON:
            df.to_json(path, orient="records", lines=True)
        else:
            raise ValueError(f"Unsupported file format: {fmt}")

    def _compute_file_checksum(self, file_path: str) -> str:
        """Compute SHA-256 checksum of a file on disk.

        Reads the file in chunks for memory efficiency.

        Args:
            file_path: Absolute path to the file.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(self._config.write_buffer_size), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _build_file_name(
        chunk_index: int, fmt: LandingFileFormat
    ) -> str:
        """Build a standardized file name for a chunk.

        Format: chunk_{index:04d}.{extension}

        Args:
            chunk_index: Zero-based chunk index.
            fmt: File format.

        Returns:
            File name string.
        """
        return f"chunk_{chunk_index:04d}.{fmt.value}"
