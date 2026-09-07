"""
Unit tests for ETL Checkpoint Engine.

Tests cover:
- Checkpoint save and load
- Resume from checkpoint
- Progress percentage
- Max retry enforcement
- CheckpointConfig validation
- Mark completed
- Save interval triggers
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from etl.checkpoint.service import CheckpointService
from etl.schemas.checkpoint_schemas import (
    Checkpoint,
    CheckpointConfig,
    CheckpointStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock SQLAlchemy async session."""
    return AsyncMock()


@pytest.fixture
def checkpoint_service(mock_session: AsyncMock) -> CheckpointService:
    """CheckpointService with mocked session."""
    return CheckpointService(mock_session)


# ---------------------------------------------------------------------------
# Checkpoint Schema Tests
# ---------------------------------------------------------------------------

class TestCheckpointSchema:
    """Tests for Checkpoint Pydantic schema."""

    def test_progress_pct(self) -> None:
        """Test progress percentage calculation."""
        cp = Checkpoint(
            checkpoint_id="cp-001",
            batch_id="b-001",
            pipeline_name="test",
            current_step="validate",
            current_record_index=500,
            total_records=1000,
        )
        assert cp.progress_pct == 50.0

    def test_progress_complete(self) -> None:
        """Test progress at 100%."""
        cp = Checkpoint(
            checkpoint_id="cp-002",
            batch_id="b-001",
            pipeline_name="test",
            current_step="validate",
            current_record_index=1000,
            total_records=1000,
        )
        assert cp.progress_pct == 100.0

    def test_progress_zero_total(self) -> None:
        """Test progress when total is 0."""
        cp = Checkpoint(
            checkpoint_id="cp-003",
            batch_id="b-001",
            pipeline_name="test",
            current_step="empty",
            current_record_index=0,
            total_records=0,
        )
        assert cp.progress_pct == 100.0

    def test_is_resumable(self) -> None:
        """Test resumable status detection."""
        cp = Checkpoint(
            checkpoint_id="cp-004",
            batch_id="b-001",
            pipeline_name="test",
            current_step="step",
            status=CheckpointStatus.IN_PROGRESS,
        )
        assert cp.is_resumable is True

        cp.status = CheckpointStatus.FAILED
        assert cp.is_resumable is True

        cp.status = CheckpointStatus.COMPLETED
        assert cp.is_resumable is False


# ---------------------------------------------------------------------------
# CheckpointConfig Tests
# ---------------------------------------------------------------------------

class TestCheckpointConfig:
    """Tests for CheckpointConfig."""

    def test_defaults(self) -> None:
        """Test configuration defaults."""
        config = CheckpointConfig()
        assert config.enabled is True
        assert config.save_interval_records == 1000
        assert config.save_interval_seconds == 30.0
        assert config.max_retries_per_checkpoint == 3
        assert config.backend == "database"

    def test_disabled(self) -> None:
        """Test disabled configuration."""
        config = CheckpointConfig(enabled=False)
        assert config.enabled is False


# ---------------------------------------------------------------------------
# CheckpointService Tests
# ---------------------------------------------------------------------------

class TestCheckpointService:
    """Tests for CheckpointService."""

    @pytest.mark.asyncio
    async def test_save_new_checkpoint(
        self, checkpoint_service: CheckpointService
    ) -> None:
        """Test saving a new checkpoint."""
        checkpoint = await checkpoint_service.save(
            batch_id="batch-001",
            pipeline_name="test_pipeline",
            current_step="validate",
            current_record_index=500,
            total_records=10000,
        )
        assert checkpoint.batch_id == "batch-001"
        assert checkpoint.current_step == "validate"
        assert checkpoint.current_record_index == 500
        assert checkpoint.status == CheckpointStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_save_with_error(
        self, checkpoint_service: CheckpointService
    ) -> None:
        """Test saving a checkpoint after an error."""
        checkpoint = await checkpoint_service.save(
            batch_id="batch-fail",
            pipeline_name="test",
            current_step="transform",
            current_record_index=200,
            total_records=1000,
            error_message="Connection timeout",
        )
        assert checkpoint.status == CheckpointStatus.FAILED
        assert checkpoint.error_message == "Connection timeout"

    @pytest.mark.asyncio
    async def test_should_save_by_records(
        self, checkpoint_service: CheckpointService
    ) -> None:
        """Test that should_save_checkpoint triggers by record count."""
        checkpoint_service.config.save_interval_records = 500
        assert checkpoint_service.should_save_checkpoint(500) is True
        assert checkpoint_service.should_save_checkpoint(499) is False

    @pytest.mark.asyncio
    async def test_should_save_by_time(
        self, checkpoint_service: CheckpointService
    ) -> None:
        """Test that should_save triggers by time."""
        import time
        checkpoint_service.config.save_interval_seconds = 0.01
        checkpoint_service._last_save_time = 0  # Force time-based trigger
        assert await checkpoint_service.should_save_checkpoint(0) is True

    @pytest.mark.asyncio
    async def test_disabled_returns_dummy(
        self, mock_session: AsyncMock
    ) -> None:
        """Test that disabled checkpoints return dummy values."""
        config = CheckpointConfig(enabled=False)
        service = CheckpointService(mock_session, config)
        checkpoint = await service.save(
            batch_id="b", pipeline_name="p", current_step="s",
            current_record_index=0, total_records=100,
        )
        assert checkpoint.checkpoint_id == "disabled"

    @pytest.mark.asyncio
    async def test_disabled_save_interval(
        self, mock_session: AsyncMock
    ) -> None:
        """Test should_save_checkpoint returns False when disabled."""
        config = CheckpointConfig(enabled=False)
        service = CheckpointService(mock_session, config)
        assert await service.should_save_checkpoint(10000) is False

    @pytest.mark.asyncio
    async def test_mark_completed(
        self, checkpoint_service: CheckpointService
    ) -> None:
        """Test marking a checkpoint as completed."""
        await checkpoint_service.mark_completed("batch-001", "validate")
        # Verify the update was executed
        checkpoint_service._session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_save_with_metadata(
        self, checkpoint_service: CheckpointService
    ) -> None:
        """Test saving checkpoint with step-specific metadata."""
        checkpoint = await checkpoint_service.save(
            batch_id="batch-meta",
            pipeline_name="test",
            current_step="enrich",
            current_record_index=750,
            total_records=5000,
            metadata={"last_customer_id": "C12345", "branch_code": "BR001"},
        )
        assert checkpoint.metadata["last_customer_id"] == "C12345"
        assert checkpoint.metadata["branch_code"] == "BR001"
