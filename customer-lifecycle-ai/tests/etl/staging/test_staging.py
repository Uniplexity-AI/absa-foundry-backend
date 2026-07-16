"""
Unit tests for ETL Staging Database module.

Tests cover:
- StagingRepository: bulk insert, truncation, row counts
- StagingService: load operations, status checks, truncation
- Staging models: ORM column definitions
- Staging schemas: configuration validation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from etl.schemas.staging_schemas import (
    StagingConfig,
    StagingLoadRequest,
    StagingLoadResult,
    StagingLoadStatus,
    StagingTable,
)
from etl.staging.repository import StagingRepository
from etl.staging.service import StagingService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_customer_df() -> pd.DataFrame:
    """Sample customer DataFrame for staging."""
    return pd.DataFrame({
        "customer_id": ["C001", "C002", "C003"],
        "first_name": ["Alice", "Bob", "Charlie"],
        "last_name": ["Smith", "Jones", "Brown"],
        "date_of_birth": ["1990-01-15", "1985-06-20", "1978-03-10"],
        "customer_type": ["INDIVIDUAL", "INDIVIDUAL", "INDIVIDUAL"],
        "segment_code": ["MASS_MARKET", "AFFLUENT", "MASS_MARKET"],
        "is_active": [True, True, False],
    })


@pytest.fixture
def sample_transaction_df() -> pd.DataFrame:
    """Sample transaction DataFrame for staging."""
    return pd.DataFrame({
        "customer_id": ["C001", "C002", "C003"],
        "account_id": ["A001", "A002", "A003"],
        "transaction_date": ["2026-07-15", "2026-07-15", "2026-07-14"],
        "transaction_type": ["DEBIT", "CREDIT", "DEBIT"],
        "transaction_channel": ["ONLINE", "BRANCH", "ATM"],
        "transaction_amount": [1500.00, 25000.00, 350.50],
        "currency": ["ZAR", "ZAR", "ZAR"],
        "branch_code": ["BR001", "BR002", "BR001"],
    })


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock SQLAlchemy async session."""
    return AsyncMock()


@pytest.fixture
def staging_repo(mock_session: AsyncMock) -> StagingRepository:
    """StagingRepository with mocked session."""
    return StagingRepository(mock_session)


@pytest.fixture
def staging_service(staging_repo: StagingRepository) -> StagingService:
    """StagingService with mocked repository."""
    return StagingService(staging_repo)


# ---------------------------------------------------------------------------
# Staging Schemas Tests
# ---------------------------------------------------------------------------

class TestStagingSchemas:
    """Tests for staging schemas."""

    def test_config_defaults(self) -> None:
        """Test StagingConfig defaults."""
        config = StagingConfig()
        assert config.batch_size == 5000
        assert config.truncate_after_load is False
        assert config.schema_name == "staging"

    def test_load_request(self) -> None:
        """Test StagingLoadRequest creation."""
        req = StagingLoadRequest(
            batch_id="batch-001",
            table=StagingTable.CUSTOMER,
        )
        assert req.batch_id == "batch-001"
        assert req.table == StagingTable.CUSTOMER
        assert req.truncate_before_load is False

    def test_load_result_defaults(self) -> None:
        """Test StagingLoadResult defaults."""
        result = StagingLoadResult(
            batch_id="batch-001",
            table=StagingTable.TRANSACTION,
            status=StagingLoadStatus.LOADED,
        )
        assert result.rows_loaded == 0
        assert result.rows_skipped == 0
        assert result.status == StagingLoadStatus.LOADED


# ---------------------------------------------------------------------------
# StagingRepository Tests
# ---------------------------------------------------------------------------

class TestStagingRepository:
    """Tests for StagingRepository."""

    @pytest.mark.asyncio
    async def test_get_model_maps_correctly(self) -> None:
        """Test that StagingTable maps to correct ORM model."""
        from etl.models.staging_models import StgCustomer, StgTransaction
        assert StagingRepository._get_model(StagingTable.CUSTOMER) == StgCustomer
        assert StagingRepository._get_model(StagingTable.TRANSACTION) == StgTransaction

    @pytest.mark.asyncio
    async def test_bulk_insert_empty_returns_zero(
        self, staging_repo: StagingRepository
    ) -> None:
        """Test that bulk insert with empty records returns 0."""
        count = await staging_repo.bulk_insert(
            StagingTable.CUSTOMER, [], batch_id="test"
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_bulk_insert_df_empty_returns_zero(
        self, staging_repo: StagingRepository
    ) -> None:
        """Test that bulk_insert_df with empty DataFrame returns 0."""
        count = await staging_repo.bulk_insert_df(
            StagingTable.CUSTOMER, pd.DataFrame(), batch_id="test"
        )
        assert count == 0


# ---------------------------------------------------------------------------
# StagingService Tests
# ---------------------------------------------------------------------------

class TestStagingService:
    """Tests for StagingService."""

    @pytest.mark.asyncio
    async def test_load_customers(
        self,
        staging_service: StagingService,
        staging_repo: StagingRepository,
        sample_customer_df: pd.DataFrame,
    ) -> None:
        """Test loading customers into staging."""
        staging_repo.bulk_insert_df = AsyncMock(return_value=3)
        result = await staging_service.load_customers(
            sample_customer_df, batch_id="batch-001"
        )
        assert result.status == StagingLoadStatus.LOADED
        assert result.rows_loaded == 3
        assert result.table == StagingTable.CUSTOMER

    @pytest.mark.asyncio
    async def test_load_transactions(
        self,
        staging_service: StagingService,
        staging_repo: StagingRepository,
        sample_transaction_df: pd.DataFrame,
    ) -> None:
        """Test loading transactions into staging."""
        staging_repo.bulk_insert_df = AsyncMock(return_value=3)
        result = await staging_service.load_transactions(
            sample_transaction_df, batch_id="batch-002"
        )
        assert result.status == StagingLoadStatus.LOADED
        assert result.table == StagingTable.TRANSACTION

    @pytest.mark.asyncio
    async def test_load_empty_df(
        self,
        staging_service: StagingService,
        staging_repo: StagingRepository,
    ) -> None:
        """Test loading empty DataFrame returns empty result."""
        result = await staging_service.load_customers(
            pd.DataFrame(), batch_id="empty"
        )
        assert result.status == StagingLoadStatus.LOADED
        assert result.rows_loaded == 0

    @pytest.mark.asyncio
    async def test_load_handles_error(
        self,
        staging_service: StagingService,
        staging_repo: StagingRepository,
        sample_customer_df: pd.DataFrame,
    ) -> None:
        """Test that database errors are caught and reported."""
        staging_repo.bulk_insert_df = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )
        result = await staging_service.load_customers(
            sample_customer_df, batch_id="error-batch"
        )
        assert result.status == StagingLoadStatus.FAILED
        assert "DB connection lost" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_truncate_all(
        self,
        staging_service: StagingService,
        staging_repo: StagingRepository,
    ) -> None:
        """Test truncating all staging tables."""
        staging_repo.truncate_table = AsyncMock(return_value=100)
        results = await staging_service.truncate_all(batch_id="cleanup")
        assert len(results) == len(StagingTable)
        assert all(v == 100 for v in results.values())

    @pytest.mark.asyncio
    async def test_get_load_status(
        self,
        staging_service: StagingService,
        staging_repo: StagingRepository,
    ) -> None:
        """Test getting load status for a batch."""
        staging_repo.get_row_count = AsyncMock(return_value=500)
        status = await staging_service.get_load_status("batch-status")
        assert len(status) == len(StagingTable)
        assert all(v == 500 for v in status.values())
