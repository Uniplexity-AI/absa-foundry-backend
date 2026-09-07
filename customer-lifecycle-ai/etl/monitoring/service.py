"""
ETL Monitoring Service - Real-time pipeline observability.

Tracks running/completed/failed jobs, rows processed,
validation failures, execution time, and throughput.
Provides alerting when thresholds are breached.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from etl.models.monitoring_models import JobStatusRecord, PipelineMetricsRecord
from etl.schemas.monitoring_schemas import (
    JobSnapshot,
    JobStatus,
    MonitoringConfig,
    PipelineMetrics,
    SystemMetrics,
)


class MonitoringService:
    """Real-time pipeline observability and alerting.

    Tracks:
    - Running / completed / failed jobs
    - Rows processed per step
    - Validation failures
    - Execution time and throughput
    - System resource usage (CPU, RAM)

    Alerts when configured thresholds are breached.
    """

    def __init__(
        self,
        session: AsyncSession,
        config: MonitoringConfig | None = None,
    ) -> None:
        self._session = session
        self.config = config or MonitoringConfig()
        self._job_cache: dict[str, JobSnapshot] = {}

    # ------------------------------------------------------------------
    # Job Tracking
    # ------------------------------------------------------------------

    async def register_job(
        self,
        run_id: str,
        pipeline_name: str,
        batch_id: str | None = None,
        total_rows: int = 0,
    ) -> None:
        """Register a new pipeline job for monitoring.

        Args:
            run_id: Pipeline run identifier.
            pipeline_name: Pipeline name.
            batch_id: Optional batch identifier.
            total_rows: Expected total rows.
        """
        if not self.config.enabled:
            return

        job = JobSnapshot(
            run_id=run_id,
            pipeline_name=pipeline_name,
            batch_id=batch_id,
            status=JobStatus.RUNNING,
            total_rows=total_rows,
        )
        self._job_cache[run_id] = job

        record = JobStatusRecord(
            run_id=run_id,
            pipeline_name=pipeline_name,
            batch_id=batch_id,
            status=JobStatus.RUNNING.value,
            total_rows=total_rows,
        )
        self._session.add(record)
        await self._session.flush()

    async def update_progress(
        self,
        run_id: str,
        current_step: str,
        rows_processed: int = 0,
        rows_failed: int = 0,
        validation_errors: int = 0,
    ) -> None:
        """Update job progress during execution.

        Args:
            run_id: Pipeline run identifier.
            current_step: Current step name.
            rows_processed: Rows processed so far.
            rows_failed: Rows that failed validation.
            validation_errors: Validation error count.
        """
        if not self.config.enabled:
            return

        job = self._job_cache.get(run_id)
        if job is None:
            return

        job.current_step = current_step
        job.rows_processed = rows_processed
        job.rows_failed = rows_failed
        job.validation_errors = validation_errors
        job.updated_at = datetime.now(timezone.utc)

        if job.total_rows > 0:
            job.progress_pct = min(rows_processed / job.total_rows * 100, 100.0)

        stmt = (
            update(JobStatusRecord)
            .where(JobStatusRecord.run_id == run_id)
            .values(
                current_step=current_step,
                rows_processed=rows_processed,
                rows_failed=rows_failed,
                validation_errors=validation_errors,
                progress_pct=job.progress_pct,
            )
        )
        await self._session.execute(stmt)

    async def mark_completed(
        self, run_id: str, metrics: PipelineMetrics | None = None
    ) -> None:
        """Mark a job as completed and record final metrics.

        Args:
            run_id: Pipeline run identifier.
            metrics: Optional final pipeline metrics.
        """
        if not self.config.enabled:
            return

        now = datetime.now(timezone.utc)
        job = self._job_cache.pop(run_id, None)

        stmt = (
            update(JobStatusRecord)
            .where(JobStatusRecord.run_id == run_id)
            .values(
                status=JobStatus.COMPLETED.value,
                progress_pct=100.0,
                duration_seconds=(
                    (now - job.started_at).total_seconds() if job else None
                ),
            )
        )
        await self._session.execute(stmt)

        if metrics:
            await self._save_metrics(metrics)

    async def mark_failed(
        self, run_id: str, error_message: str
    ) -> None:
        """Mark a job as failed.

        Args:
            run_id: Pipeline run identifier.
            error_message: Failure reason.
        """
        if not self.config.enabled:
            return

        job = self._job_cache.pop(run_id, None)
        now = datetime.now(timezone.utc)

        stmt = (
            update(JobStatusRecord)
            .where(JobStatusRecord.run_id == run_id)
            .values(
                status=JobStatus.FAILED.value,
                error_message=error_message,
                duration_seconds=(
                    (now - job.started_at).total_seconds() if job else None
                ),
            )
        )
        await self._session.execute(stmt)

        if self.config.alert_on_failure:
            await self._raise_alert(run_id, error_message)

    # ------------------------------------------------------------------
    # Metrics & Queries
    # ------------------------------------------------------------------

    async def collect_metrics(
        self, run_id: str
    ) -> PipelineMetrics:
        """Build pipeline metrics from tracked data.

        Args:
            run_id: Pipeline run identifier.

        Returns:
            PipelineMetrics with computed throughput.
        """
        job = self._job_cache.get(run_id)
        if job is None:
            return PipelineMetrics(run_id=run_id, pipeline_name="unknown")

        elapsed = (datetime.now(timezone.utc) - job.started_at).total_seconds()
        throughput = job.rows_processed / elapsed if elapsed > 0 else 0.0

        return PipelineMetrics(
            run_id=run_id,
            pipeline_name=job.pipeline_name,
            batch_id=job.batch_id,
            total_execution_time_s=elapsed,
            rows_ingested=job.total_rows,
            rows_validated=max(0, job.total_rows - job.validation_errors),
            rows_rejected=job.rows_failed,
            rows_transformed=job.rows_processed,
            rows_loaded=job.rows_processed - job.rows_failed,
            validation_error_count=job.validation_errors,
            throughput_rows_per_sec=round(throughput, 2),
        )

    async def get_running_jobs(self) -> list[JobSnapshot]:
        """List all currently running jobs.

        Returns:
            List of running JobSnapshots.
        """
        return [j for j in self._job_cache.values() if j.status == JobStatus.RUNNING]

    async def get_job_status(self, run_id: str) -> JobSnapshot | None:
        """Get status of a specific job.

        Args:
            run_id: Pipeline run identifier.

        Returns:
            JobSnapshot if found, None otherwise.
        """
        return self._job_cache.get(run_id)

    async def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system resource metrics.

        Returns:
            SystemMetrics with CPU, memory, disk usage.
        """
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return SystemMetrics(
                cpu_percent=cpu,
                memory_used_mb=mem.used / (1024 * 1024),
                memory_total_mb=mem.total / (1024 * 1024),
                disk_used_gb=disk.used / (1024 * 1024 * 1024),
                active_connections=len(psutil.net_connections()),
                open_files=len(psutil.Process().open_files()),
            )
        except ImportError:
            return SystemMetrics()

    async def check_alerts(self, metrics: PipelineMetrics) -> list[str]:
        """Check metrics against alert thresholds.

        Args:
            metrics: Current pipeline metrics.

        Returns:
            List of alert messages (empty if all OK).
        """
        alerts: list[str] = []
        t = self.config.alert_thresholds

        if metrics.quality_score < t.get("quality_score_min", 80):
            alerts.append(
                f"Quality score {metrics.quality_score} below threshold {t['quality_score_min']}"
            )
        if metrics.throughput_rows_per_sec < t.get("throughput_min", 100):
            alerts.append(
                f"Throughput {metrics.throughput_rows_per_sec:.1f} rows/s below threshold"
            )

        return alerts

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _save_metrics(self, metrics: PipelineMetrics) -> None:
        """Persist pipeline metrics to database."""
        record = PipelineMetricsRecord(
            run_id=metrics.run_id,
            pipeline_name=metrics.pipeline_name,
            batch_id=metrics.batch_id,
            total_execution_time_s=metrics.total_execution_time_s,
            rows_ingested=metrics.rows_ingested,
            rows_validated=metrics.rows_validated,
            rows_rejected=metrics.rows_rejected,
            rows_transformed=metrics.rows_transformed,
            rows_loaded=metrics.rows_loaded,
            validation_error_count=metrics.validation_error_count,
            validation_warning_count=metrics.validation_warning_count,
            duplicate_count=metrics.duplicate_count,
            quality_score=metrics.quality_score,
            throughput_rows_per_sec=metrics.throughput_rows_per_sec,
            step_durations=metrics.step_durations,
        )
        self._session.add(record)
        await self._session.flush()

    async def _raise_alert(self, run_id: str, message: str) -> None:
        """Log and optionally notify about a pipeline failure."""
        # In production, this would send to Slack, email, PagerDuty, etc.
        pass
