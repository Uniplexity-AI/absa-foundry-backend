"""
File Connectors - CSV, Excel, JSON, XML.

Each file connector implements the FileConnector interface, supporting
single files and glob patterns for batch processing.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pandas as pd

from etl.connectors.factory import register_connector
from etl.connectors.interfaces import FileConnector
from etl.schemas.connector_schemas import (
    BatchMetadata,
    ConnectorConfig,
    ConnectorInfo,
    Dataset,
    SourceType,
)


# ---------------------------------------------------------------------------
# Base File Connector
# ---------------------------------------------------------------------------

class BaseFileConnector(FileConnector):
    """Base class for file-based connectors with common file operations."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._files: list[str] = []

    async def connect(self) -> None:
        """Validate that the configured file path(s) exist."""
        files = await self.list_files()
        if not files:
            raise FileNotFoundError(
                f"No files found matching pattern: {self.config.file_path or self.config.file_pattern}"
            )
        self._files = files
        self._connected = True

    async def disconnect(self) -> None:
        """Release any file handles (no-op for most file operations)."""
        self._files = []
        self._connected = False

    async def validate_connection(self) -> bool:
        """Check that at least one matching file exists."""
        try:
            files = await self.list_files()
            return len(files) > 0
        except Exception:
            return False

    async def list_files(self) -> list[str]:
        """List files matching the configured pattern."""
        if self.config.file_path:
            # Direct file path
            if os.path.isfile(self.config.file_path):
                return [os.path.abspath(self.config.file_path)]
        if self.config.file_pattern:
            return sorted(glob.glob(self.config.file_pattern, recursive=True))
        return []

    async def get_file_metadata(self, file_path: str) -> dict[str, Any]:
        """Get metadata for a specific file."""
        stat = os.stat(file_path)
        return {
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            "file_name": os.path.basename(file_path),
            "absolute_path": os.path.abspath(file_path),
        }

    def _compute_file_checksum(self, file_path: str) -> str:
        """Compute SHA-256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _read_file(self, file_path: str) -> pd.DataFrame:
        """Read a file into a DataFrame. Must be overridden by subclasses."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# CSV Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.CSV,
    ConnectorInfo(
        source_type=SourceType.CSV,
        display_name="CSV",
        description="Connector for CSV (comma-separated values) files",
        supported_operations=["extract", "list_files", "get_file_metadata"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class CsvConnector(BaseFileConnector):
    """CSV file connector with configurable delimiter and encoding."""

    def _read_file(self, file_path: str) -> pd.DataFrame:
        """Read CSV file into DataFrame."""
        return pd.read_csv(
            file_path,
            delimiter=self.config.delimiter,
            encoding=self.config.encoding,
            header=0 if self.config.has_header else None,
            low_memory=False,
        )

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from CSV files matching the configured pattern."""
        if not self._connected:
            raise RuntimeError("Cannot extract: connector is not connected.")

        batch_id = str(uuid.uuid4())
        total_rows = 0
        chunk_index = 0

        metadata = BatchMetadata(
            batch_id=batch_id,
            source_type=SourceType.CSV,
            source_name=self.config.source_name,
            extracted_at=datetime.now(timezone.utc),
        )

        for file_path in self._files:
            try:
                df = self._read_file(file_path)
            except Exception as e:
                raise RuntimeError(f"Failed to read CSV file {file_path}: {e}") from e

            total_rows += len(df)
            checksum = self._compute_file_checksum(file_path)

            chunk_metadata = metadata.model_copy(update={
                "total_rows": total_rows,
                "total_chunks": chunk_index + 1,
                "file_path": file_path,
                "checksum_sha256": checksum,
            })

            yield Dataset(
                data=df,
                metadata=chunk_metadata,
                chunk_index=chunk_index,
            )
            chunk_index += 1

        metadata.total_rows = total_rows
        metadata.total_chunks = chunk_index
        metadata.extraction_completed_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Excel Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.EXCEL,
    ConnectorInfo(
        source_type=SourceType.EXCEL,
        display_name="Excel",
        description="Connector for Excel (.xlsx, .xls) files",
        supported_operations=["extract", "list_files", "get_file_metadata"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class ExcelConnector(BaseFileConnector):
    """Excel file connector supporting .xlsx and .xls formats."""

    def _read_file(self, file_path: str) -> pd.DataFrame:
        """Read Excel file into DataFrame."""
        sheet_name = self.config.extra_params.get("sheet_name", 0)
        return pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            header=0 if self.config.has_header else None,
        )

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from Excel files."""
        if not self._connected:
            raise RuntimeError("Cannot extract: connector is not connected.")

        batch_id = str(uuid.uuid4())
        total_rows = 0
        chunk_index = 0

        metadata = BatchMetadata(
            batch_id=batch_id,
            source_type=SourceType.EXCEL,
            source_name=self.config.source_name,
            extracted_at=datetime.now(timezone.utc),
        )

        for file_path in self._files:
            try:
                df = self._read_file(file_path)
            except Exception as e:
                raise RuntimeError(f"Failed to read Excel file {file_path}: {e}") from e

            total_rows += len(df)
            checksum = self._compute_file_checksum(file_path)

            chunk_metadata = metadata.model_copy(update={
                "total_rows": total_rows,
                "total_chunks": chunk_index + 1,
                "file_path": file_path,
                "checksum_sha256": checksum,
            })

            yield Dataset(
                data=df,
                metadata=chunk_metadata,
                chunk_index=chunk_index,
            )
            chunk_index += 1

        metadata.total_rows = total_rows
        metadata.total_chunks = chunk_index
        metadata.extraction_completed_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# JSON Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.JSON,
    ConnectorInfo(
        source_type=SourceType.JSON,
        display_name="JSON",
        description="Connector for JSON files (array of objects or line-delimited JSON)",
        supported_operations=["extract", "list_files", "get_file_metadata"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class JsonConnector(BaseFileConnector):
    """JSON file connector supporting array-of-objects and JSONL formats."""

    def _read_file(self, file_path: str) -> pd.DataFrame:
        """Read JSON file into DataFrame."""
        lines = self.config.extra_params.get("lines", False)
        orient = self.config.extra_params.get("orient", "records")
        return pd.read_json(
            file_path,
            lines=lines,
            orient=orient,
            encoding=self.config.encoding,
        )

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from JSON files."""
        if not self._connected:
            raise RuntimeError("Cannot extract: connector is not connected.")

        batch_id = str(uuid.uuid4())
        total_rows = 0
        chunk_index = 0

        metadata = BatchMetadata(
            batch_id=batch_id,
            source_type=SourceType.JSON,
            source_name=self.config.source_name,
            extracted_at=datetime.now(timezone.utc),
        )

        for file_path in self._files:
            try:
                df = self._read_file(file_path)
            except Exception as e:
                raise RuntimeError(f"Failed to read JSON file {file_path}: {e}") from e

            # Normalize nested JSON if needed
            if self.config.extra_params.get("normalize", False):
                df = pd.json_normalize(df.to_dict(orient="records"))

            total_rows += len(df)
            checksum = self._compute_file_checksum(file_path)

            chunk_metadata = metadata.model_copy(update={
                "total_rows": total_rows,
                "total_chunks": chunk_index + 1,
                "file_path": file_path,
                "checksum_sha256": checksum,
            })

            yield Dataset(
                data=df,
                metadata=chunk_metadata,
                chunk_index=chunk_index,
            )
            chunk_index += 1

        metadata.total_rows = total_rows
        metadata.total_chunks = chunk_index
        metadata.extraction_completed_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# XML Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.XML,
    ConnectorInfo(
        source_type=SourceType.XML,
        display_name="XML",
        description="Connector for XML files",
        supported_operations=["extract", "list_files", "get_file_metadata"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class XmlConnector(BaseFileConnector):
    """XML file connector using pandas read_xml."""

    def _read_file(self, file_path: str) -> pd.DataFrame:
        """Read XML file into DataFrame."""
        xpath = self.config.extra_params.get("xpath", ".//*")
        return pd.read_xml(
            file_path,
            xpath=xpath,
            encoding=self.config.encoding,
        )

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from XML files."""
        if not self._connected:
            raise RuntimeError("Cannot extract: connector is not connected.")

        batch_id = str(uuid.uuid4())
        total_rows = 0
        chunk_index = 0

        metadata = BatchMetadata(
            batch_id=batch_id,
            source_type=SourceType.XML,
            source_name=self.config.source_name,
            extracted_at=datetime.now(timezone.utc),
        )

        for file_path in self._files:
            try:
                df = self._read_file(file_path)
            except Exception as e:
                raise RuntimeError(f"Failed to read XML file {file_path}: {e}") from e

            total_rows += len(df)
            checksum = self._compute_file_checksum(file_path)

            chunk_metadata = metadata.model_copy(update={
                "total_rows": total_rows,
                "total_chunks": chunk_index + 1,
                "file_path": file_path,
                "checksum_sha256": checksum,
            })

            yield Dataset(
                data=df,
                metadata=chunk_metadata,
                chunk_index=chunk_index,
            )
            chunk_index += 1

        metadata.total_rows = total_rows
        metadata.total_chunks = chunk_index
        metadata.extraction_completed_at = datetime.now(timezone.utc)
