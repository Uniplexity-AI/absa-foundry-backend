"""
ETL Landing Zone Reader - Data retrieval from immutable storage.

Provides read-only access to the landing zone for downstream
modules (validation, transformation). Never modifies files.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from etl.landing.interfaces import LandingZoneReader
from etl.schemas.landing_schemas import LandingFileFormat, LandingPath, LandingZoneConfig


class LocalLandingZoneReader(LandingZoneReader):
    """Local filesystem landing zone reader.

    Provides read-only access to landing zone data. Used by
    validation and transformation modules to access raw data
    without direct filesystem manipulation.
    """

    def __init__(self, config: LandingZoneConfig | None = None) -> None:
        """Initialize the landing zone reader.

        Args:
            config: Landing zone configuration. Uses defaults if None.
        """
        self._config = config or LandingZoneConfig()

    async def read_dataset(self, path: LandingPath) -> pd.DataFrame:
        """Read a full dataset from the landing zone.

        Reads all chunk files in the batch directory and concatenates
        them into a single DataFrame.

        Args:
            path: Structured path to the dataset.

        Returns:
            DataFrame containing all data for the batch.

        Raises:
            FileNotFoundError: If the batch directory does not exist.
        """
        batch_dir = Path(path.batch_directory)
        if not batch_dir.exists():
            raise FileNotFoundError(
                f"Landing zone batch directory not found: {batch_dir}"
            )

        dataframes: list[pd.DataFrame] = []
        # Read all chunk files in the batch directory
        chunk_files = sorted(batch_dir.glob("chunk_*.parquet"))
        if not chunk_files:
            chunk_files = sorted(batch_dir.glob("chunk_*.csv"))
        if not chunk_files:
            chunk_files = sorted(batch_dir.glob("chunk_*.json"))

        for chunk_file in chunk_files:
            df = self._read_file(str(chunk_file))
            dataframes.append(df)

        if not dataframes:
            return pd.DataFrame()

        return pd.concat(dataframes, ignore_index=True)

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
            FileNotFoundError: If the chunk file does not exist.
        """
        batch_dir = Path(path.batch_directory)

        # Try different formats in order of preference
        for fmt in (LandingFileFormat.PARQUET, LandingFileFormat.CSV, LandingFileFormat.JSON):
            file_name = f"chunk_{chunk_index:04d}.{fmt.value}"
            chunk_path = batch_dir / file_name
            if chunk_path.exists():
                return self._read_file(str(chunk_path))

        raise FileNotFoundError(
            f"Chunk {chunk_index} not found in {batch_dir}"
        )

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
        date_dir = (
            Path(self._config.base_path)
            / f"{year:04d}"
            / f"{month:02d}"
            / f"{day:02d}"
        )
        if not date_dir.exists():
            return []
        return sorted(
            d.name for d in date_dir.iterdir() if d.is_dir()
        )

    async def list_chunks(self, batch_id: str) -> list[str]:
        """List all chunk file names for a batch.

        Args:
            batch_id: The batch identifier (must also provide date context).

        Returns:
            List of chunk file names.
        """
        # Search across date partitions for this batch
        base = Path(self._config.base_path)
        chunk_files: list[str] = []
        for date_dir in base.rglob(batch_id):
            if date_dir.is_dir():
                chunk_files = sorted(
                    f.name for f in date_dir.iterdir()
                    if f.is_file() and f.name.startswith("chunk_")
                )
                break
        return chunk_files

    async def file_exists(self, path: LandingPath) -> bool:
        """Check if a file or batch directory exists.

        Args:
            path: Structured path to check.

        Returns:
            True if the path exists.
        """
        return Path(path.full_path).exists() if path.file_name else Path(path.batch_directory).exists()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_file(self, file_path: str) -> pd.DataFrame:
        """Read a file into a DataFrame based on its extension.

        Args:
            file_path: Absolute path to the file.

        Returns:
            DataFrame containing the file data.

        Raises:
            ValueError: If file format is unsupported.
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".parquet":
            return pd.read_parquet(file_path)
        elif ext == ".csv":
            return pd.read_csv(file_path)
        elif ext == ".json":
            return pd.read_json(file_path, lines=True)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
