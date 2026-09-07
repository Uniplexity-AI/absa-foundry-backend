"""
ETL API Schemas — Pydantic v2 response models for ETL endpoints.

Shared between gateway/routes/etl_routes.py and gateway/services/etl_service.py
to avoid circular imports.

FR-OPS-01: ETL Run History
FR-OPS-02: Data Quality Dashboard
FR-OPS-03: System Health
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ETLRunSummary(BaseModel):
    """Single run row for the execution history table (FR-OPS-01)."""
    id: int
    run_id: str = Field(alias="runId")
    batch_id: str = Field(alias="batchId")
    duration: str
    rows_received: str = Field(alias="rowsReceived")
    rows_valid: str = Field(alias="rowsValid")
    rows_loaded: str = Field(alias="rowsLoaded")
    rows_rejected: int = Field(alias="rowsRejected")
    quality_score: float = Field(alias="qualityScore")
    quality_class: str = Field(alias="qualityClass")
    status: str
    status_class: str = Field(alias="statusClass")

    model_config = {"populate_by_name": True}


class QualityTrendPoint(BaseModel):
    """Single point on the quality trend chart (FR-OPS-02)."""
    label: str
    value: float
    rows: str
    rejected: str
    failed: bool


class StatusPanel(BaseModel):
    """Current operational status panel data."""
    current_status: str
    current_status_since: str | None = None
    current_pipeline: str | None = None
    last_successful_run: str | None = None
    last_successful_duration: str | None = None
    last_successful_rows: str | None = None
    last_successful_quality: float | None = None
    latest_quality: float | None = None
    latest_quality_rows: str | None = None
    sla_threshold: float = 95.0
    last_failure_run: str | None = None
    last_failure_detail: str | None = None


class DashboardKPIs(BaseModel):
    """Aggregated KPI cards for the dashboard header."""
    todays_runs: int
    successful_runs: int
    failed_runs: int
    running_runs: int
    avg_quality: float
    avg_duration: str
    success_rate: float


class ETLDashboardResponse(BaseModel):
    """Full dashboard response: KPIs + status panel + quality trend + runs."""
    kpis: DashboardKPIs
    status: StatusPanel
    quality_trend: list[QualityTrendPoint]
    runs: list[ETLRunSummary]
    total_runs: int
    page: int
    limit: int


# ═══════════════════════════════════════════════════════════════════
# Batch Detail Schemas (GET /api/etl/runs/{runId})
# ═══════════════════════════════════════════════════════════════════

class RunDetail(BaseModel):
    """Full audit record for a single run."""
    id: int
    run_id: str = Field(alias="runId")
    batch_id: str | None = Field(default=None, alias="batchId")
    status: str
    pipeline_name: str | None = Field(default=None, alias="pipelineName")
    triggered_by: str | None = Field(default=None, alias="triggeredBy")
    started_at: str | None = Field(default=None, alias="startedAt")
    completed_at: str | None = Field(default=None, alias="completedAt")
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")
    duration: str
    rows_received: int = Field(alias="rowsReceived")
    rows_valid: int = Field(alias="rowsValid")
    rows_loaded: int = Field(alias="rowsLoaded")
    rows_rejected: int = Field(alias="rowsRejected")
    rows_skipped: int = Field(default=0, alias="rowsSkipped")
    duplicates_detected: int = Field(default=0, alias="duplicatesDetected")
    warnings_count: int = Field(default=0, alias="warningsCount")
    errors_count: int = Field(default=0, alias="errorsCount")
    quality_score: float | None = Field(default=None, alias="qualityScore")
    error_message: str | None = Field(default=None, alias="errorMessage")
    source_type: str | None = Field(default=None, alias="sourceType")
    source_name: str | None = Field(default=None, alias="sourceName")
    sla_threshold: float = 95.0

    model_config = {"populate_by_name": True}


class ValidationDetail(BaseModel):
    """Validation run summary for a batch."""
    run_id: str | None = Field(default=None, alias="validationRunId")
    status: str | None = None
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    duplicate_records: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    quality_score: float | None = None
    error_by_category: dict | None = Field(default=None, alias="errorByCategory")
    error_by_rule: dict | None = Field(default=None, alias="errorByRule")

    model_config = {"populate_by_name": True}


class ETLRunDetailResponse(BaseModel):
    """Full batch detail: run + validation data."""
    run: RunDetail
    validation: ValidationDetail | None = None
