"""
ETL Landing Zone Schemas - Pydantic v2 schemas for landed file tracking.

Defines data structures for:
- LandingFileRecord: Metadata about a file in the landing zone
- LandingPath: Structured landing zone path
- LandingZoneConfig: Configuration for landing zone storage
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LandingFileFormat(str, Enum):
    """Supported file formats in the landing zone."""
    PARQUET = "parquet"
    CSV = "csv"
    JSON = "json"
    AVRO = "avro"


class LandingFileStatus(str, Enum):
    """Lifecycle status of a landed file."""
    WRITING = "WRITING"       # Currently being written
    LANDED = "LANDED"         # Successfully written and verified
    CORRUPT = "CORRUPT"       # Failed integrity check
    ARCHIVED = "ARCHIVED"     # Moved to long-term storage


# ---------------------------------------------------------------------------
# Landing Path
# ---------------------------------------------------------------------------

class LandingPath(BaseModel):
    """Structured representation of a landing zone path.

    Decomposes the time-partitioned path into its constituent parts
    for querying and filtering.
    """
    model_config = ConfigDict(extra="forbid")

    base_path: str = Field(
        default="/data/landing",
        description="Root directory of the landing zone",
    )
    year: int = Field(description="Partition year")
    month: int = Field(ge=1, le=12, description="Partition month")
    day: int = Field(ge=1, le=31, description="Partition day")
    batch_id: str = Field(description="Batch identifier")
    file_name: str | None = Field(
        default=None,
        description="Specific file name within the batch directory",
    )

    @property
    def batch_directory(self) -> str:
        """Full path to the batch directory."""
        return str(
            PurePosixPath(self.base_path)
            / f"{self.year:04d}"
            / f"{self.month:02d}"
            / f"{self.day:02d}"
            / self.batch_id
        )

    @property
    def full_path(self) -> str:
        """Full path including file name if specified."""
        if self.file_name:
            return str(PurePosixPath(self.batch_directory) / self.file_name)
        return self.batch_directory

    @classmethod
    def from_batch_id(cls, batch_id: str, base_path: str = "/data/landing") -> LandingPath:
        """Create a LandingPath from a batch ID using current date.

        Args:
            batch_id: The batch identifier.
            base_path: Root landing zone directory.

        Returns:
            LandingPath with current date partitioning.
        """
        now = datetime.now(timezone.utc)
        return cls(
            base_path=base_path,
            year=now.year,
            month=now.month,
            day=now.day,
            batch_id=batch_id,
        )


# ---------------------------------------------------------------------------
# Landing File Record (Schema)
# ---------------------------------------------------------------------------

class LandingFileRecord(BaseModel):
    """Metadata about a single file in the landing zone.

    Maps 1:1 to etl_landing_file table. Used for tracking
    and retrieval of immutable raw data files.
    """
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(
        description="Unique file identifier (UUID v4)",
    )
    batch_id: str = Field(
        description="Parent batch identifier",
    )
    chunk_index: int = Field(
        default=0,
        ge=0,
        description="Chunk index within the batch",
    )
    file_name: str = Field(
        description="Name of the file in the landing zone",
    )
    file_path: str = Field(
        description="Absolute path to the file",
    )
    file_format: LandingFileFormat = Field(
        description="Format of the landed file",
    )
    file_size_bytes: int = Field(
        default=0,
        ge=0,
        description="Size of the file in bytes",
    )
    row_count: int = Field(
        default=0,
        ge=0,
        description="Number of rows in the file",
    )
    checksum_sha256: str | None = Field(
        default=None,
        description="SHA-256 checksum of the file contents",
    )
    status: LandingFileStatus = Field(
        default=LandingFileStatus.WRITING,
        description="Current status of the file",
    )
    column_names: list[str] = Field(
        default_factory=list,
        description="Ordered list of column names",
    )
    column_types: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of column_name → dtype",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the file was created (UTC)",
    )
    verified_at: datetime | None = Field(
        default=None,
        description="When the file integrity was verified (UTC)",
    )
    source_type: str | None = Field(
        default=None,
        description="Source type that produced this data",
    )
    source_name: str | None = Field(
        default=None,
        description="Source system name",
    )
    compression: str | None = Field(
        default=None,
        description="Compression algorithm used (snappy, gzip, none)",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary tags",
    )

    @field_validator("file_path")
    @classmethod
    def file_path_must_match_format(cls, v: str) -> str:
        """Validate that file_path references the landing zone."""
        if "landing" not in v:
            raise ValueError("file_path must be within the landing zone")
        return v


# ---------------------------------------------------------------------------
# Landing Zone Configuration
# ---------------------------------------------------------------------------

class LandingZoneConfig(BaseModel):
    """Configuration for the landing zone storage.

    All values can be overridden via environment variables.
    """
    model_config = ConfigDict(extra="forbid")

    base_path: str = Field(
        default="/data/landing",
        description="Root directory for the landing zone",
    )
    default_format: LandingFileFormat = Field(
        default=LandingFileFormat.PARQUET,
        description="Default file format for landed data",
    )
    compression: str = Field(
        default="snappy",
        description="Compression codec: snappy, gzip, lz4, zstd, none",
    )
    max_file_size_mb: int = Field(
        default=256,
        ge=1,
        le=10240,
        description="Maximum file size in MB before splitting",
    )
    enable_checksum_verification: bool = Field(
        default=True,
        description="Verify checksums after writing",
    )
    retention_days: int = Field(
        default=2555,  # ~7 years
        ge=1,
        description="Number of days to retain files before archival",
    )
    write_buffer_size: int = Field(
        default=65536,
        ge=4096,
        description="Write buffer size in bytes",
    )
    create_parent_directories: bool = Field(
        default=True,
        description="Auto-create parent directories if they don't exist",
    )
