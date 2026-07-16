"""
ETL Loading Schemas - Pydantic v2 schemas for production load operations.

Defines the loading pipeline configuration, load steps with dependency
ordering, and per-step load results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LoadStepStatus(str, Enum):
    """Status of a single loading step."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class LoadStrategy(str, Enum):
    """How data is loaded into production tables."""
    UPSERT = "upsert"       # INSERT ... ON CONFLICT UPDATE
    APPEND = "append"       # INSERT only (for append-only tables)
    REPLACE = "replace"     # TRUNCATE then INSERT
    MERGE = "merge"         # Complex merge with business logic


# ---------------------------------------------------------------------------
# Load Step Definition
# ---------------------------------------------------------------------------

class LoadStep(BaseModel):
    """Definition of a single loading step in the pipeline.

    Each step loads one staging table into one production table
    with a specific strategy and ordering constraint.
    """
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(description="Unique step identifier")
    step_name: str = Field(description="Human-readable step name")
    staging_table: str = Field(description="Source staging table name")
    target_table: str = Field(description="Target production table name")
    target_schema: str = Field(description="Target production schema")
    load_strategy: LoadStrategy = Field(default=LoadStrategy.UPSERT)
    conflict_columns: list[str] = Field(
        default_factory=list,
        description="Columns for ON CONFLICT clause (upsert key)",
    )
    update_columns: list[str] = Field(
        default_factory=list,
        description="Columns to update on conflict (empty = all)",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Step IDs that must complete before this one",
    )
    post_load_action: str | None = Field(
        default=None,
        description="Action to trigger after load: feature_engineering, prediction, etc.",
    )
    is_enabled: bool = Field(default=True)
    description: str = Field(default="")


class LoadStepResult(BaseModel):
    """Result of executing a single loading step."""
    step_id: str
    step_name: str
    status: LoadStepStatus
    rows_loaded: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Load Pipeline Config & Result
# ---------------------------------------------------------------------------

class LoadPipelineConfig(BaseModel):
    """Configuration for the full loading pipeline.

    Defines all load steps and their execution order.
    """
    model_config = ConfigDict(extra="forbid")

    pipeline_name: str = Field(default="production_load")
    steps: list[LoadStep] = Field(
        default_factory=lambda: _default_steps(),
        description="Ordered load steps (dependency-resolved at runtime)",
    )
    batch_size: int = Field(default=5000, ge=1)
    truncate_staging_on_success: bool = Field(default=True)
    stop_on_failure: bool = Field(default=True)
    emit_events: bool = Field(default=True)


class LoadPipelineResult(BaseModel):
    """Aggregate result of a complete loading pipeline execution."""
    batch_id: str
    pipeline_name: str
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    total_rows_loaded: int = 0
    status: LoadStepStatus = LoadStepStatus.PENDING
    step_results: list[LoadStepResult] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    staging_truncated: bool = False

    @property
    def is_successful(self) -> bool:
        return self.status == LoadStepStatus.COMPLETED


# ---------------------------------------------------------------------------
# Default Loading Order
# ---------------------------------------------------------------------------

def _default_steps() -> list[LoadStep]:
    """Default loading steps per the database design specification v2.

    Order: Customers → Accounts → Branches → Transactions
    This ensures referential integrity (FK constraints satisfied).
    """
    return [
        LoadStep(
            step_id="load_customers",
            step_name="Load Customers",
            staging_table="stg_customer",
            target_table="customer",
            target_schema="clean",
            load_strategy=LoadStrategy.UPSERT,
            conflict_columns=["customer_id"],
            description="Load customer master data into clean.customer",
        ),
        LoadStep(
            step_id="load_accounts",
            step_name="Load Accounts",
            staging_table="stg_account",
            target_table="account",
            target_schema="clean",
            load_strategy=LoadStrategy.UPSERT,
            conflict_columns=["account_id"],
            depends_on=["load_customers"],
            description="Load account data — depends on customers",
        ),
        LoadStep(
            step_id="load_branches",
            step_name="Load Branches",
            staging_table="stg_branch",
            target_table="branch",
            target_schema="clean",
            load_strategy=LoadStrategy.UPSERT,
            conflict_columns=["branch_code"],
            description="Load branch/channel reference data",
        ),
        LoadStep(
            step_id="load_transactions",
            step_name="Load Transactions",
            staging_table="stg_transaction",
            target_table="customer_transactions_clean",
            target_schema="clean",
            load_strategy=LoadStrategy.APPEND,
            depends_on=["load_customers", "load_accounts", "load_branches"],
            post_load_action="feature_engineering",
            description="Load transactions into clean.customer_transactions_clean — depends on customers, accounts, branches",
        ),
    ]
