"""
Unit tests for ETL Production Loader.

Tests cover:
- LoadStep dependency resolution (topological sort)
- LoadPipelineConfig defaults and validation
- LoadingService execution with mocked repositories
- LoadingRepository upsert/append strategies
- Circular dependency detection
- Staging truncation after success
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from etl.loading.repository import LoadingRepository
from etl.loading.service import LoadingService
from etl.schemas.loading_schemas import (
    LoadPipelineConfig,
    LoadPipelineResult,
    LoadStep,
    LoadStepResult,
    LoadStepStatus,
    LoadStrategy,
)
from etl.schemas.staging_schemas import StagingTable
from etl.staging.repository import StagingRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config() -> LoadPipelineConfig:
    """Default loading pipeline config."""
    return LoadPipelineConfig()


@pytest.fixture
def mock_load_repo() -> AsyncMock:
    """Mock LoadingRepository."""
    return AsyncMock(spec=LoadingRepository)


@pytest.fixture
def mock_staging_repo() -> AsyncMock:
    """Mock StagingRepository."""
    return AsyncMock(spec=StagingRepository)


@pytest.fixture
def loading_service(
    mock_load_repo: AsyncMock, mock_staging_repo: AsyncMock
) -> LoadingService:
    """LoadingService with mocked repositories."""
    return LoadingService(
        loading_repo=mock_load_repo,
        staging_repo=mock_staging_repo,
    )


# ---------------------------------------------------------------------------
# Topological Sort Tests
# ---------------------------------------------------------------------------

class TestDependencyResolution:
    """Tests for load step dependency resolution."""

    def test_linear_dependencies_resolve(self) -> None:
        """Test that linear dependency chain resolves correctly."""
        steps = [
            LoadStep(step_id="A", step_name="A", staging_table="a", target_table="a", target_schema="x"),
            LoadStep(step_id="B", step_name="B", staging_table="b", target_table="b", target_schema="x", depends_on=["A"]),
            LoadStep(step_id="C", step_name="C", staging_table="c", target_table="c", target_schema="x", depends_on=["B"]),
        ]
        ordered = LoadingService._resolve_order(steps)
        assert [s.step_id for s in ordered] == ["A", "B", "C"]

    def test_diamond_dependencies_resolve(self) -> None:
        """Test diamond dependency pattern."""
        steps = [
            LoadStep(step_id="A", step_name="A", staging_table="a", target_table="a", target_schema="x"),
            LoadStep(step_id="B", step_name="B", staging_table="b", target_table="b", target_schema="x", depends_on=["A"]),
            LoadStep(step_id="C", step_name="C", staging_table="c", target_table="c", target_schema="x", depends_on=["A"]),
            LoadStep(step_id="D", step_name="D", staging_table="d", target_table="d", target_schema="x", depends_on=["B", "C"]),
        ]
        ordered = LoadingService._resolve_order(steps)
        assert ordered[0].step_id == "A"
        assert ordered[3].step_id == "D"

    def test_no_dependencies_preserves_order(self) -> None:
        """Test steps with no dependencies keep input order."""
        steps = [
            LoadStep(step_id="X", step_name="X", staging_table="x", target_table="x", target_schema="s"),
            LoadStep(step_id="Y", step_name="Y", staging_table="y", target_table="y", target_schema="s"),
        ]
        ordered = LoadingService._resolve_order(steps)
        assert [s.step_id for s in ordered] == ["X", "Y"]

    def test_circular_dependency_raises(self) -> None:
        """Test that circular dependencies are detected."""
        steps = [
            LoadStep(step_id="A", step_name="A", staging_table="a", target_table="a", target_schema="x", depends_on=["B"]),
            LoadStep(step_id="B", step_name="B", staging_table="b", target_table="b", target_schema="x", depends_on=["A"]),
        ]
        with pytest.raises(ValueError, match="Circular dependency"):
            LoadingService._resolve_order(steps)


# ---------------------------------------------------------------------------
# LoadPipelineConfig Tests
# ---------------------------------------------------------------------------

class TestLoadPipelineConfig:
    """Tests for LoadPipelineConfig."""

    def test_default_steps_have_correct_order(self) -> None:
        """Test that default steps follow the required loading order."""
        config = LoadPipelineConfig()
        step_ids = [s.step_id for s in config.steps]
        assert "load_customers" in step_ids
        assert "load_accounts" in step_ids
        assert "load_branches" in step_ids
        assert "load_transactions" in step_ids

    def test_transactions_depend_on_customers(self) -> None:
        """Test that transaction loading depends on customers, accounts, branches."""
        config = LoadPipelineConfig()
        txn_step = next(s for s in config.steps if s.step_id == "load_transactions")
        assert "load_customers" in txn_step.depends_on
        assert "load_accounts" in txn_step.depends_on
        assert "load_branches" in txn_step.depends_on

    def test_config_defaults(self) -> None:
        """Test LoadPipelineConfig defaults."""
        config = LoadPipelineConfig()
        assert config.truncate_staging_on_success is True
        assert config.stop_on_failure is True
        assert config.batch_size == 5000


# ---------------------------------------------------------------------------
# LoadingService Tests
# ---------------------------------------------------------------------------

class TestLoadingService:
    """Tests for LoadingService."""

    @pytest.mark.asyncio
    async def test_execute_with_empty_staging(
        self,
        loading_service: LoadingService,
        mock_staging_repo: AsyncMock,
    ) -> None:
        """Test that empty staging results in skipped steps."""
        mock_staging_repo.get_row_count.return_value = 0

        result = await loading_service.execute(batch_id="empty-batch")

        assert result.status == LoadStepStatus.COMPLETED
        assert result.completed_steps == 0
        assert result.skipped_steps > 0

    @pytest.mark.asyncio
    async def test_execute_loads_successfully(
        self,
        loading_service: LoadingService,
        mock_staging_repo: AsyncMock,
        mock_load_repo: AsyncMock,
    ) -> None:
        """Test full successful load pipeline."""
        mock_staging_repo.get_row_count.return_value = 100
        mock_staging_repo.get_staging_customers.return_value = []
        mock_staging_repo.get_staging_accounts.return_value = []
        mock_staging_repo.get_staging_branches.return_value = []
        mock_staging_repo.get_staging_transactions.return_value = []
        mock_load_repo.upsert.return_value = (100, 20)
        mock_staging_repo.truncate_table.return_value = 100

        result = await loading_service.execute(batch_id="success-batch")

        assert result.status == LoadStepStatus.COMPLETED
        assert result.total_steps == 4

    @pytest.mark.asyncio
    async def test_staging_truncated_after_success(
        self,
        loading_service: LoadingService,
        mock_staging_repo: AsyncMock,
        mock_load_repo: AsyncMock,
    ) -> None:
        """Test that staging is truncated after successful load."""
        mock_staging_repo.get_row_count.return_value = 100
        mock_staging_repo.get_staging_customers.return_value = []
        mock_staging_repo.get_staging_accounts.return_value = []
        mock_staging_repo.get_staging_branches.return_value = []
        mock_staging_repo.get_staging_transactions.return_value = []
        mock_load_repo.upsert.return_value = (100, 0)

        result = await loading_service.execute(batch_id="truncate-test")

        assert result.staging_truncated is True
        # truncate_table should be called for each staging table
        assert mock_staging_repo.truncate_table.call_count >= 4

    @pytest.mark.asyncio
    async def test_stop_on_failure(
        self,
        loading_service: LoadingService,
        mock_staging_repo: AsyncMock,
    ) -> None:
        """Test that pipeline stops on first failure when configured."""
        mock_staging_repo.get_row_count.return_value = 100
        mock_staging_repo.get_staging_customers.side_effect = RuntimeError("DB down")

        result = await loading_service.execute(batch_id="fail-batch")

        assert result.status == LoadStepStatus.FAILED
        assert result.failed_steps >= 1

    @pytest.mark.asyncio
    async def test_result_has_timestamps(
        self,
        loading_service: LoadingService,
        mock_staging_repo: AsyncMock,
        mock_load_repo: AsyncMock,
    ) -> None:
        """Test that the result includes timing information."""
        mock_staging_repo.get_row_count.return_value = 100
        mock_staging_repo.get_staging_customers.return_value = []
        mock_staging_repo.get_staging_accounts.return_value = []
        mock_staging_repo.get_staging_branches.return_value = []
        mock_staging_repo.get_staging_transactions.return_value = []
        mock_load_repo.upsert.return_value = (100, 0)

        result = await loading_service.execute(batch_id="timing-test")

        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds is not None


# ---------------------------------------------------------------------------
# LoadPipelineResult Tests
# ---------------------------------------------------------------------------

class TestLoadPipelineResult:
    """Tests for LoadPipelineResult."""

    def test_result_defaults(self) -> None:
        """Test result default values."""
        result = LoadPipelineResult(batch_id="test", pipeline_name="test")
        assert result.status == LoadStepStatus.PENDING
        assert result.total_rows_loaded == 0
        assert result.is_successful is False

    def test_successful_result(self) -> None:
        """Test successful result detection."""
        result = LoadPipelineResult(
            batch_id="test",
            pipeline_name="test",
            status=LoadStepStatus.COMPLETED,
        )
        assert result.is_successful is True
