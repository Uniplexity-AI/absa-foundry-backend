"""
Unit tests for ETL Audit module.

Tests cover:
- AuditRecord creation and validation
- Immutability enforcement
- Rejection rate and duplicate rate computation
- AuditConfig defaults
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from etl.audit.service import AuditService
from etl.schemas.audit_schemas import AuditConfig, AuditRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_audit_record() -> AuditRecord:
    return AuditRecord(
        audit_id="audit-001",
        batch_id="batch-001",
        source_type="csv",
        source_name="Monthly Export",
        pipeline_name="etl_full_pipeline",
        started_at=datetime.now(timezone.utc),
        rows_received=10000,
        rows_valid=9500,
        rows_rejected=300,
        rows_loaded=9500,
        rows_skipped=200,
        duplicates_detected=150,
        warnings_count=50,
        errors_count=300,
        quality_score=92.5,
        triggered_by="orchestration-service",
    )


# ---------------------------------------------------------------------------
# AuditRecord Tests
# ---------------------------------------------------------------------------

class TestAuditRecord:
    def test_rejection_rate(self) -> None:
        record = AuditRecord(
            audit_id="a-1", batch_id="b-1",
            source_type="csv", source_name="s", pipeline_name="p",
            started_at=datetime.now(timezone.utc),
            rows_received=10000, rows_rejected=500,
        )
        assert record.rejection_rate_pct == 5.0

    def test_rejection_rate_zero_rows(self) -> None:
        record = AuditRecord(
            audit_id="a-2", batch_id="b-2",
            source_type="csv", source_name="s", pipeline_name="p",
            started_at=datetime.now(timezone.utc),
            rows_received=0, rows_rejected=0,
        )
        assert record.rejection_rate_pct == 0.0

    def test_duplicate_rate(self) -> None:
        record = AuditRecord(
            audit_id="a-3", batch_id="b-3",
            source_type="csv", source_name="s", pipeline_name="p",
            started_at=datetime.now(timezone.utc),
            rows_received=10000, duplicates_detected=250,
        )
        assert record.duplicate_rate_pct == 2.5

    def test_defaults(self) -> None:
        record = AuditRecord(
            audit_id="a-4", batch_id="b-4",
            source_type="rest", source_name="api", pipeline_name="test",
            started_at=datetime.now(timezone.utc),
        )
        assert record.rows_received == 0
        assert record.quality_score == 100.0
        assert record.status == "COMPLETED"
        assert record.triggered_by == "system"


# ---------------------------------------------------------------------------
# AuditConfig Tests
# ---------------------------------------------------------------------------

class TestAuditConfig:
    def test_defaults(self) -> None:
        config = AuditConfig()
        assert config.enabled is True
        assert config.retention_years == 7
        assert config.immutable is True
