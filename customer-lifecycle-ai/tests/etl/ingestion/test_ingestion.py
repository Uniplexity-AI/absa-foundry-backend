"""
Unit tests for ETL Ingestion Framework.

Tests cover:
- IngestionService (full pipeline execution)
- Batch ID generation
- Checksum computation
- Ingestion lifecycle state machine
- Error handling and recovery
- Schema validation
- Repository operations (mocked)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pandas as pd
import pytest

from etl.ingestion.interfaces import (
    IngestionEventEmitter,
    IngestionRepository,
    LandingZoneWriter,
)
from etl.ingestion.service import (
    IngestionError,
    IngestionService,
    LandingZoneWriteError,
)
from etl.schemas.connector_schemas import (
    BatchMetadata,
    ConnectorConfig,
    Dataset,
    SourceType,
)
from etl.schemas.ingestion_schemas import (
    IngestionBatch,
    IngestionEvent,
    IngestionRequest,
    IngestionResult,
    IngestionStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Sample DataFrame representing banking transaction data."""
    return pd.DataFrame({
        "customer_id": ["C001", "C002", "C003"],
        "account_id": ["A001", "A002", "A003"],
        "transaction_date": ["2026-07-15", "2026-07-15", "2026-07-14"],
        "transaction_type": ["DEBIT", "CREDIT", "DEBIT"],
        "transaction_amount": [1500.00, 25000.00, 350.50],
        "currency": ["ZAR", "ZAR", "ZAR"],
    })


@pytest.fixture
def sample_dataset(sample_df: pd.DataFrame) -> Dataset:
    """Sample Dataset for ingestion testing."""
    return Dataset(
        data=sample_df,
        metadata=BatchMetadata(
            batch_id="pre-ingestion-batch",
            source_type=SourceType.CSV,
            source_name="Test Source",
        ),
        chunk_index=0,
    )


@pytest.fixture
def csv_config() -> ConnectorConfig:
    """Sample CSV connector config."""
    return ConnectorConfig(
        source_type=SourceType.CSV,
        source_name="Test CSV Source",
        file_path="/data/test.csv",
    )


@pytest.fixture
def ingestion_request(csv_config: ConnectorConfig) -> IngestionRequest:
    """Sample ingestion request."""
    return IngestionRequest(
        connector_config=csv_config,
        pipeline_name="test_pipeline",
        trigger_type="manual",
        triggered_by="test_runner",
        tags={"env": "test"},
    )


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock ingestion repository."""
    return AsyncMock(spec=IngestionRepository)


@pytest.fixture
def mock_landing_zone() -> AsyncMock:
    """Mock landing zone writer."""
    return AsyncMock(spec=LandingZoneWriter)


@pytest.fixture
def mock_event_emitter() -> AsyncMock:
    """Mock event emitter."""
    return AsyncMock(spec=IngestionEventEmitter)


@pytest.fixture
def service(
    mock_repository: AsyncMock,
    mock_landing_zone: AsyncMock,
    mock_event_emitter: AsyncMock,
) -> IngestionService:
    """IngestionService with mocked dependencies."""
    return IngestionService(
        repository=mock_repository,
        landing_zone=mock_landing_zone,
        event_emitter=mock_event_emitter,
    )


# ---------------------------------------------------------------------------
# Batch ID Tests
# ---------------------------------------------------------------------------

class TestBatchIdGeneration:
    """Tests for batch ID generation."""

    def test_batch_id_format(self) -> None:
        """Test that batch ID follows the expected format."""
        batch_id = IngestionService._generate_batch_id()
        parts = batch_id.split("-")
        assert len(parts) == 2, f"Expected 2 parts, got {len(parts)}: {batch_id}"
        timestamp_part, uuid_part = parts
        assert len(timestamp_part) == 14, f"Timestamp part length: {len(timestamp_part)}"
        assert len(uuid_part) == 8, f"UUID part length: {len(uuid_part)}"

    def test_batch_ids_are_unique(self) -> None:
        """Test that generated batch IDs are unique."""
        ids = {IngestionService._generate_batch_id() for _ in range(100)}
        assert len(ids) == 100, "All 100 batch IDs must be unique"

    def test_batch_id_is_sortable(self) -> None:
        """Test that batch IDs sort chronologically."""
        id1 = IngestionService._generate_batch_id()
        import time
        time.sleep(0.01)
        id2 = IngestionService._generate_batch_id()
        assert id1 < id2, "Earlier batch ID should sort before later batch ID"


# ---------------------------------------------------------------------------
# Checksum Tests
# ---------------------------------------------------------------------------

class TestChecksumComputation:
    """Tests for data checksum computation."""

    def test_checksum_is_deterministic(self, sample_dataset: Dataset) -> None:
        """Test that checksum of same data is always the same."""
        cs1 = IngestionService._compute_checksum(sample_dataset)
        cs2 = IngestionService._compute_checksum(sample_dataset)
        assert cs1 == cs2
        assert len(cs1) == 64  # SHA-256 hex length

    def test_checksum_changes_with_data(self, sample_dataset: Dataset) -> None:
        """Test that different data produces different checksums."""
        cs1 = IngestionService._compute_checksum(sample_dataset)
        modified_df = sample_dataset.data.copy()
        modified_df.loc[0, "transaction_amount"] = 9999.99
        modified_dataset = Dataset(
            data=modified_df,
            metadata=sample_dataset.metadata,
        )
        cs2 = IngestionService._compute_checksum(modified_dataset)
        assert cs1 != cs2

    def test_aggregate_checksum(self) -> None:
        """Test aggregate checksum computation from chunk checksums."""
        checksums = ["a" * 64, "b" * 64, "c" * 64]
        agg = IngestionService._compute_aggregate_checksum(checksums)
        assert len(agg) == 64
        # Same checksums in different order should produce same aggregate
        agg2 = IngestionService._compute_aggregate_checksum(["c" * 64, "a" * 64, "b" * 64])
        assert agg == agg2

    def test_size_estimation(self, sample_dataset: Dataset) -> None:
        """Test dataset size estimation."""
        size = IngestionService._estimate_size_bytes(sample_dataset)
        assert size > 0, "Size estimate should be positive for non-empty DataFrame"

        empty_dataset = Dataset(
            data=pd.DataFrame(),
            metadata=sample_dataset.metadata,
        )
        size_empty = IngestionService._estimate_size_bytes(empty_dataset)
        assert size_empty == 0


# ---------------------------------------------------------------------------
# Ingestion Lifecycle Tests
# ---------------------------------------------------------------------------

class TestIngestionLifecycle:
    """Tests for the ingestion lifecycle state machine."""

    def test_batch_starts_received(self) -> None:
        """Test that a new batch starts in RECEIVED status."""
        batch = IngestionBatch(
            batch_id="test-001",
            pipeline_name="test",
            source_type=SourceType.CSV,
            source_name="Test",
        )
        assert batch.status == IngestionStatus.RECEIVED
        assert not batch.is_complete
        assert not batch.is_successful

    def test_batch_is_complete_after_validation_triggered(self) -> None:
        """Test that batch is considered complete after validation trigger."""
        batch = IngestionBatch(
            batch_id="test-002",
            pipeline_name="test",
            source_type=SourceType.CSV,
            source_name="Test",
            status=IngestionStatus.VALIDATION_TRIGGERED,
        )
        assert batch.is_complete
        assert batch.is_successful

    def test_batch_is_complete_after_failure(self) -> None:
        """Test that failed batch is considered complete."""
        batch = IngestionBatch(
            batch_id="test-003",
            pipeline_name="test",
            source_type=SourceType.CSV,
            source_name="Test",
            status=IngestionStatus.FAILED,
        )
        assert batch.is_complete
        assert not batch.is_successful

    def test_result_from_batch(self) -> None:
        """Test IngestionResult.from_batch conversion."""
        batch = IngestionBatch(
            batch_id="test-004",
            pipeline_name="test",
            source_type=SourceType.CSV,
            source_name="Test",
            status=IngestionStatus.VALIDATION_TRIGGERED,
            total_rows=1000,
            total_chunks=5,
        )
        result = IngestionResult.from_batch(batch)
        assert result.batch_id == batch.batch_id
        assert result.status == batch.status
        assert result.total_rows == 1000
        assert result.total_chunks == 5
        assert "validation" in result.next_steps


# ---------------------------------------------------------------------------
# IngestionService Tests
# ---------------------------------------------------------------------------

class TestIngestionService:
    """Tests for the IngestionService."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_extract(
        self,
        service: IngestionService,
        csv_config: ConnectorConfig,
    ) -> None:
        """Test that dry_run skips actual data extraction."""
        request = IngestionRequest(
            connector_config=csv_config,
            pipeline_name="test_pipeline",
            dry_run=True,
        )
        result = await service.ingest(request)
        assert result.status == IngestionStatus.VALIDATION_TRIGGERED
        assert result.total_rows == 0

    @pytest.mark.asyncio
    async def test_ingestion_success_flow(
        self,
        service: IngestionService,
        ingestion_request: IngestionRequest,
        mock_repository: AsyncMock,
        mock_landing_zone: AsyncMock,
        mock_event_emitter: AsyncMock,
        sample_dataset: Dataset,
    ) -> None:
        """Test the full successful ingestion flow."""
        mock_landing_zone.write_chunk.return_value = "/landing/2026/07/16/test.parquet"

        # Mock the connector to yield one dataset
        with patch(
            "etl.ingestion.service.create_connector"
        ) as mock_factory:
            mock_connector = AsyncMock()
            mock_connector.extract.return_value.__aiter__.return_value = [sample_dataset]
            mock_factory.return_value = mock_connector

            result = await service.ingest(ingestion_request)

        # Verify result
        assert result.status == IngestionStatus.VALIDATION_TRIGGERED
        assert result.total_rows == sample_dataset.row_count
        assert result.total_chunks == 1
        assert result.checksum_sha256 is not None
        assert result.landing_path is not None

        # Verify repository calls
        mock_repository.save_batch.assert_called_once()
        mock_repository.save_chunk.assert_called_once()
        assert mock_repository.update_batch_status.call_count >= 3

        # Verify landing zone call
        mock_landing_zone.write_chunk.assert_called_once()

        # Verify event emitted
        mock_event_emitter.emit_ingestion_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingestion_handles_connector_failure(
        self,
        service: IngestionService,
        ingestion_request: IngestionRequest,
        mock_repository: AsyncMock,
        mock_event_emitter: AsyncMock,
    ) -> None:
        """Test that connector failure is handled gracefully."""
        with patch(
            "etl.ingestion.service.create_connector"
        ) as mock_factory:
            mock_connector = AsyncMock()
            mock_connector.connect.side_effect = ConnectionError("Connection refused")
            mock_factory.return_value = mock_connector

            with pytest.raises(IngestionError, match="Connection refused"):
                await service.ingest(ingestion_request)

        # Failure event should be emitted
        mock_event_emitter.emit_ingestion_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingestion_handles_landing_zone_failure(
        self,
        service: IngestionService,
        ingestion_request: IngestionRequest,
        mock_landing_zone: AsyncMock,
        mock_event_emitter: AsyncMock,
        sample_dataset: Dataset,
    ) -> None:
        """Test that landing zone failure is handled gracefully."""
        mock_landing_zone.write_chunk.side_effect = IOError("Disk full")

        with patch(
            "etl.ingestion.service.create_connector"
        ) as mock_factory:
            mock_connector = AsyncMock()
            mock_connector.extract.return_value.__aiter__.return_value = [sample_dataset]
            mock_factory.return_value = mock_connector

            with pytest.raises(IngestionError, match="Disk full"):
                await service.ingest(ingestion_request)

        mock_event_emitter.emit_ingestion_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingestion_without_event_emitter(
        self,
        mock_repository: AsyncMock,
        mock_landing_zone: AsyncMock,
        ingestion_request: IngestionRequest,
        sample_dataset: Dataset,
    ) -> None:
        """Test that ingestion works without an event emitter."""
        service = IngestionService(
            repository=mock_repository,
            landing_zone=mock_landing_zone,
            event_emitter=None,
        )

        mock_landing_zone.write_chunk.return_value = "/landing/test.parquet"

        with patch(
            "etl.ingestion.service.create_connector"
        ) as mock_factory:
            mock_connector = AsyncMock()
            mock_connector.extract.return_value.__aiter__.return_value = [sample_dataset]
            mock_factory.return_value = mock_connector

            result = await service.ingest(ingestion_request)

        assert result.status == IngestionStatus.VALIDATION_TRIGGERED

    @pytest.mark.asyncio
    async def test_connector_is_disconnected_after_success(
        self,
        service: IngestionService,
        ingestion_request: IngestionRequest,
        mock_landing_zone: AsyncMock,
        sample_dataset: Dataset,
    ) -> None:
        """Test that connector is disconnected after successful ingestion."""
        mock_landing_zone.write_chunk.return_value = "/landing/test.parquet"

        with patch(
            "etl.ingestion.service.create_connector"
        ) as mock_factory:
            mock_connector = AsyncMock()
            mock_connector.extract.return_value.__aiter__.return_value = [sample_dataset]
            mock_factory.return_value = mock_connector

            await service.ingest(ingestion_request)

        mock_connector.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# Schema Validation Tests
# ---------------------------------------------------------------------------

class TestIngestionSchemas:
    """Tests for ingestion Pydantic schemas."""

    def test_ingestion_request_validation(self) -> None:
        """Test IngestionRequest schema validation."""
        config = ConnectorConfig(
            source_type=SourceType.CSV,
            source_name="Test",
            file_path="/tmp/test.csv",
        )
        request = IngestionRequest(connector_config=config)
        assert request.pipeline_name == "default"
        assert request.trigger_type == "manual"
        assert request.priority == 5

    def test_ingestion_batch_defaults(self) -> None:
        """Test IngestionBatch default values."""
        batch = IngestionBatch(
            batch_id="batch-test",
            pipeline_name="test",
            source_type=SourceType.CSV,
            source_name="Test",
        )
        assert batch.status == IngestionStatus.RECEIVED
        assert batch.total_rows == 0
        assert batch.total_chunks == 0
        assert batch.total_size_bytes == 0
        assert batch.received_at is not None

    def test_ingestion_event_creation(self) -> None:
        """Test IngestionEvent creation."""
        event = IngestionEvent(
            event_id="evt-001",
            batch_id="batch-001",
            pipeline_name="test",
            source_type=SourceType.CSV,
            source_name="Test",
            status=IngestionStatus.VALIDATION_TRIGGERED,
        )
        assert event.event_type == "ingestion.completed"
        assert event.producer == "etl-ingestion-service"
        assert event.occurred_at is not None

    def test_ingestion_result_warnings(self) -> None:
        """Test IngestionResult with warnings."""
        result = IngestionResult(
            batch_id="batch-warn",
            status=IngestionStatus.VALIDATION_TRIGGERED,
            pipeline_name="test",
            source_type=SourceType.CSV,
            source_name="Test",
            warnings=["Large number of null values detected"],
            received_at=datetime.now(timezone.utc),
        )
        assert len(result.warnings) == 1


# ---------------------------------------------------------------------------
# Landing Path Tests
# ---------------------------------------------------------------------------

class TestLandingPath:
    """Tests for landing zone path generation."""

    def test_landing_path_format(self) -> None:
        """Test landing path follows expected format."""
        path = IngestionService._build_landing_path("test-batch-001")
        assert path.startswith("landing/")
        parts = path.split("/")
        assert len(parts) == 5  # landing/YYYY/MM/DD/batch_id
        assert len(parts[1]) == 4  # Year
        assert len(parts[2]) == 2  # Month
        assert len(parts[3]) == 2  # Day
        assert parts[4] == "test-batch-001"
