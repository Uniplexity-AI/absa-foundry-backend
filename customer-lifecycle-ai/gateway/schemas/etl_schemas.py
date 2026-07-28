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
