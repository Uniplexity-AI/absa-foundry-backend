"""
ETL Staging Schemas - Pydantic v2 schemas for staging layer operations.

Defines data structures for writing to and reading from staging tables.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StagingLoadStatus(str, Enum):
    """Status of a staging load operation."""
    PENDING = "PENDING"
    LOADING = "LOADING"
    LOADED = "LOADED"
    FAILED = "FAILED"
    TRUNCATED = "TRUNCATED"


class StagingTable(str, Enum):
    """Available staging tables."""
    CUSTOMER = "stg_customer"
    ACCOUNT = "stg_account"
    TRANSACTION = "stg_transaction"
    BRANCH = "stg_branch"


class StagingLoadRequest(BaseModel):
    """Request to load data into a staging table."""
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(description="Batch identifier")
    table: StagingTable = Field(description="Target staging table")
    truncate_before_load: bool = Field(
        default=False,
        description="Truncate staging table before loading (for full reloads)",
    )


class StagingLoadResult(BaseModel):
    """Result of a staging load operation."""
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    table: StagingTable
    status: StagingLoadStatus
    rows_loaded: int = 0
    rows_skipped: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error_message: str | None = None


class StagingConfig(BaseModel):
    """Staging layer configuration."""
    model_config = ConfigDict(extra="forbid")

    batch_size: int = Field(default=5000, ge=1, description="Rows per insert batch")
    truncate_after_load: bool = Field(
        default=False,
        description="Auto-truncate staging after successful production load",
    )
    schema_name: str = Field(default="staging", description="Database schema name")
