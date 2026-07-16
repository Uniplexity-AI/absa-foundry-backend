"""
ETL Audit Schemas - Pydantic v2 models for compliance audit trail.

Records complete batch lifecycle: source, timing, row counts,
quality metrics, and operator attribution — required for banking
compliance and regulatory reporting.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditRecord(BaseModel):
    """Complete audit trail for a single batch.

    Every batch must record all fields for regulatory compliance.
    Stored immutably — never modified after creation.
    """
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(description="Unique audit record identifier")
    batch_id: str = Field(description="Batch identifier")

    # Source
    source_type: str = Field(description="Source system type")
    source_name: str = Field(description="Human-readable source name")
    pipeline_name: str = Field(description="Pipeline that processed this batch")

    # Timing
    started_at: datetime = Field(description="When batch processing started (UTC)")
    completed_at: datetime | None = Field(default=None, description="When processing completed")
    duration_seconds: float | None = Field(default=None, description="Total processing duration")

    # Row counts
    rows_received: int = Field(default=0, ge=0, description="Rows received from source")
    rows_valid: int = Field(default=0, ge=0, description="Rows passing all validations")
    rows_rejected: int = Field(default=0, ge=0, description="Rows failing validation")
    rows_loaded: int = Field(default=0, ge=0, description="Rows loaded into production")
    rows_skipped: int = Field(default=0, ge=0, description="Rows skipped (duplicates, etc.)")

    # Quality
    duplicates_detected: int = Field(default=0, ge=0, description="Duplicate records found")
    warnings_count: int = Field(default=0, ge=0, description="Non-fatal warnings")
    errors_count: int = Field(default=0, ge=0, description="Fatal validation errors")
    quality_score: float = Field(default=100.0, ge=0, le=100, description="Computed quality score")

    # Status
    status: str = Field(default="COMPLETED", description="Final status: COMPLETED, FAILED, PARTIAL")
    error_message: str | None = Field(default=None, description="Error if failed")

    # Attribution
    triggered_by: str = Field(default="system", description="User or service that triggered")
    operator_id: str | None = Field(default=None, description="Operator identifier")

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When audit record was created",
    )
    tags: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def rejection_rate_pct(self) -> float:
        if self.rows_received == 0:
            return 0.0
        return round(self.rows_rejected / self.rows_received * 100, 2)

    @property
    def duplicate_rate_pct(self) -> float:
        if self.rows_received == 0:
            return 0.0
        return round(self.duplicates_detected / self.rows_received * 100, 2)


class AuditConfig(BaseModel):
    """Audit trail configuration."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    retention_years: int = Field(default=7, ge=1, description="Regulatory retention period")
    immutable: bool = Field(default=True, description="Audit records are never modified")
