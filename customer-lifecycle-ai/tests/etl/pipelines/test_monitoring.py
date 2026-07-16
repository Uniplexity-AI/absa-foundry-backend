"""
Unit tests for ETL Monitoring module.

Tests cover:
- Job registration and status tracking
- Progress updates and completion/failure marking
- Metrics collection and throughput calculation
- Alert threshold checks
- System metrics collection
- Configuration validation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from etl.monitoring.service import MonitoringService
from etl.schemas.monitoring_schemas import (
    JobSnapshot,
    JobStatus,
    MonitoringConfig,
    PipelineMetrics,
    SystemMetrics,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def monitoring_service(mock_session: AsyncMock) -> MonitoringService:
    return MonitoringService(mock_session)


# ---------------------------------------------------------------------------
# MonitoringConfig Tests
# ---------------------------------------------------------------------------

class TestMonitoringConfig:
    def test_defaults(self) -> None:
        config = MonitoringConfig()
        assert config.enabled is True
        assert config.collection_interval_seconds == 10.0
        assert config.track_system_metrics is True
        assert "quality_score_min" in config.alert_thresholds

    def test_disabled(self) -> None:
        config = MonitoringConfig(enabled=False)
        assert config.enabled is False


# ---------------------------------------------------------------------------
# Job Tracking Tests
# ---------------------------------------------------------------------------

class TestJobTracking:
    @pytest.mark.asyncio
    async def test_register_job(
        self, monitoring_service: MonitoringService
    ) -> None:
        await monitoring_service.register_job(
            run_id="run-001",
            pipeline_name="etl_full",
            batch_id="batch-001",
            total_rows=10000,
        )
        job = monitoring_service._job_cache.get("run-001")
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert job.total_rows == 10000

    @pytest.mark.asyncio
    async def test_update_progress(
        self, monitoring_service: MonitoringService
    ) -> None:
        await monitoring_service.register_job("run-002", "test", total_rows=1000)
        await monitoring_service.update_progress(
            "run-002", "validate", rows_processed=500, rows_failed=5
        )
        job = monitoring_service._job_cache["run-002"]
        assert job.current_step == "validate"
        assert job.progress_pct == 50.0
        assert job.rows_failed == 5

    @pytest.mark.asyncio
    async def test_mark_completed(
        self, monitoring_service: MonitoringService
    ) -> None:
        await monitoring_service.register_job("run-003", "test")
        await monitoring_service.mark_completed("run-003")
        assert "run-003" not in monitoring_service._job_cache

    @pytest.mark.asyncio
    async def test_mark_failed(
        self, monitoring_service: MonitoringService
    ) -> None:
        await monitoring_service.register_job("run-004", "test")
        await monitoring_service.mark_failed("run-004", "DB connection lost")
        assert "run-004" not in monitoring_service._job_cache

    @pytest.mark.asyncio
    async def test_get_running_jobs(
        self, monitoring_service: MonitoringService
    ) -> None:
        await monitoring_service.register_job("r1", "p1")
        await monitoring_service.register_job("r2", "p2")
        running = await monitoring_service.get_running_jobs()
        assert len(running) == 2

    @pytest.mark.asyncio
    async def test_disabled_skips_operations(
        self, mock_session: AsyncMock
    ) -> None:
        config = MonitoringConfig(enabled=False)
        service = MonitoringService(mock_session, config)
        await service.register_job("r", "p")
        assert len(service._job_cache) == 0


# ---------------------------------------------------------------------------
# Metrics Tests
# ---------------------------------------------------------------------------

class TestMetrics:
    @pytest.mark.asyncio
    async def test_collect_metrics(
        self, monitoring_service: MonitoringService
    ) -> None:
        await monitoring_service.register_job(
            "run-metrics", "test", total_rows=5000
        )
        await monitoring_service.update_progress(
            "run-metrics", "load", rows_processed=5000, rows_failed=50
        )
        metrics = await monitoring_service.collect_metrics("run-metrics")
        assert metrics.rows_ingested == 5000
        assert metrics.rows_loaded == 4950
        assert metrics.throughput_rows_per_sec > 0


# ---------------------------------------------------------------------------
# Alert Tests
# ---------------------------------------------------------------------------

class TestAlerts:
    @pytest.mark.asyncio
    async def test_quality_score_alert(
        self, monitoring_service: MonitoringService
    ) -> None:
        metrics = PipelineMetrics(
            run_id="r", pipeline_name="p",
            quality_score=50.0, throughput_rows_per_sec=500.0,
        )
        alerts = await monitoring_service.check_alerts(metrics)
        assert any("quality" in a.lower() for a in alerts)

    @pytest.mark.asyncio
    async def test_no_alerts_when_healthy(
        self, monitoring_service: MonitoringService
    ) -> None:
        metrics = PipelineMetrics(
            run_id="r", pipeline_name="p",
            quality_score=95.0, throughput_rows_per_sec=500.0,
        )
        alerts = await monitoring_service.check_alerts(metrics)
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# SystemMetrics Tests
# ---------------------------------------------------------------------------

class TestSystemMetrics:
    def test_memory_pct(self) -> None:
        metrics = SystemMetrics(memory_used_mb=4096, memory_total_mb=8192)
        assert metrics.memory_pct == 50.0

    def test_memory_pct_zero_total(self) -> None:
        metrics = SystemMetrics()
        assert metrics.memory_pct == 0.0
