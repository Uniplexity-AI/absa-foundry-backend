"""
ETL Service — business logic for the ETL dashboard API.

Transforms raw AuditRecord ORM objects into the Pydantic response
models expected by the frontend (ETLRunHistory.vue).

FR-OPS-01: ETL Run History table
FR-OPS-02: Data Quality Dashboard
FR-OPS-03: System Health

Coding standards: ALL business logic here. No raw SQL. Uses ETLRepository.
"""

from __future__ import annotations

import logging

from etl.repositories.etl_repository import ETLRepository
from gateway.schemas.etl_schemas import (
    DashboardKPIs,
    QualityTrendPoint,
    StatusPanel,
    ETLRunSummary,
    ETLDashboardResponse,
)

logger = logging.getLogger("gateway.services.etl")


class ETLService:
    """ETL dashboard service — transforms DB records into API responses."""

    def __init__(self, repository: ETLRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_dashboard(
        self,
        page: int = 1,
        limit: int = 25,
        status: str | None = None,
    ) -> ETLDashboardResponse:
        """Build the full ETL dashboard response from audit records.

        Args:
            page: 1-based page number.
            limit: Items per page (1–100).
            status: Optional filter: COMPLETED, FAILED.

        Returns:
            ETLDashboardResponse with KPIs, status, quality trend, and paginated runs.
        """
        kpis_raw = await self._repo.get_todays_kpis()
        status_raw = await self._repo.get_status_panel()
        trend_raw = await self._repo.get_quality_trend(limit=10)
        runs_raw, total_runs = await self._repo.get_runs(
            page=page, limit=limit, status=status,
        )

        return ETLDashboardResponse(
            kpis=self._build_kpis(kpis_raw),
            status=self._build_status(status_raw),
            quality_trend=self._build_trend(trend_raw),
            runs=[self._build_run_summary(r, i) for i, r in enumerate(runs_raw)],
            total_runs=total_runs,
            page=page,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Private: Mappers (ORM / dict → Pydantic response)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_kpis(raw: dict) -> DashboardKPIs:
        return DashboardKPIs(
            todays_runs=raw["todays_runs"],
            successful_runs=raw["successful_runs"],
            failed_runs=raw["failed_runs"],
            running_runs=raw["running_runs"],
            avg_quality=raw["avg_quality"],
            avg_duration=_format_duration(raw.get("avg_duration_seconds")),
            success_rate=raw["success_rate"],
        )

    @staticmethod
    def _build_status(raw: dict) -> StatusPanel:
        return StatusPanel(
            current_status=raw["current_status"],
            current_status_since=raw.get("current_status_since"),
            current_pipeline=raw.get("current_pipeline"),
            last_successful_run=raw.get("last_successful_run"),
            last_successful_duration=_format_duration(
                raw.get("last_successful_duration"),
            ),
            last_successful_rows=_format_rows(raw.get("last_successful_rows")),
            last_successful_quality=raw.get("last_successful_quality"),
            latest_quality=raw.get("latest_quality"),
            latest_quality_rows=_format_rows(raw.get("latest_quality_rows")),
            sla_threshold=raw.get("sla_threshold", 95.0),
            last_failure_run=raw.get("last_failure_run"),
            last_failure_detail=raw.get("last_failure_detail"),
        )

    @staticmethod
    def _build_trend(raw: list[dict]) -> list[QualityTrendPoint]:
        return [
            QualityTrendPoint(
                label=p["label"],
                value=p["value"],
                rows=_format_rows(p["rows"]),
                rejected=_format_rows(p["rejected"]),
                failed=p["failed"],
            )
            for p in raw
        ]

    @staticmethod
    def _build_run_summary(row: dict, index: int) -> ETLRunSummary:
        return ETLRunSummary(
            id=row["id"],
            runId=row["audit_id"],
            batchId=row["batch_id"] or "--",
            duration=_format_duration(row.get("duration_seconds")),
            rowsReceived=_format_rows(row.get("rows_received")),
            rowsValid=_format_rows(row.get("rows_valid")),
            rowsLoaded=_format_rows(row.get("rows_loaded")),
            rowsRejected=row.get("rows_rejected") or 0,
            qualityScore=round(float(row.get("quality_score") or 0), 1),
            qualityClass=_quality_class(float(row.get("quality_score") or 0)),
            status=row["status"],
            statusClass=_status_class(row["status"]),
        )


# =========================================================================
# Formatting helpers (shared)
# =========================================================================

def _format_duration(seconds: float | None) -> str:
    """Format duration_seconds into 'XXm YYs' string."""
    if seconds is None:
        return "--"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}m {s:02d}s"


def _format_rows(n: int | None) -> str:
    """Format row counts with K/M suffix."""
    if n is None:
        return "--"
    if n >= 1_000_000:
        val = n / 1_000_000
        s = f"{val:.2f}".rstrip("0").rstrip(".")
        return f"{s}M"
    if n >= 1_000:
        return f"{n // 1_000}K"
    return str(n)


def _quality_class(score: float) -> str:
    if score >= 99.0:
        return "good"
    if score >= 95.0:
        return "warning"
    return "critical"


def _status_class(status: str) -> str:
    s = status.upper()
    if s in ("COMPLETED", "SUCCESS"):
        return "completed"
    if s in ("FAILED", "ERROR"):
        return "failed"
    if s in ("RUNNING", "IN_PROGRESS"):
        return "running"
    return "pending"
