"""
Example: Using the Ingestion Framework

Demonstrates how to configure and execute an ingestion pipeline
with various source types and dependency injection patterns.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from etl.ingestion.service import IngestionService
from etl.schemas.connector_schemas import ConnectorConfig, SourceType
from etl.schemas.ingestion_schemas import IngestionRequest


# ---------------------------------------------------------------------------
# Example 1: CSV File Ingestion
# ---------------------------------------------------------------------------

async def example_csv_ingestion():
    """Ingest data from a CSV file through the full ingestion pipeline."""
    from etl.ingestion.interfaces import (
        IngestionEventEmitter,
        IngestionRepository,
        LandingZoneWriter,
    )

    # In production, these would be real implementations
    repository: IngestionRepository = MagicMock()  # type: ignore[assignment]
    landing_zone: LandingZoneWriter = MagicMock()  # type: ignore[assignment]
    event_emitter: IngestionEventEmitter = MagicMock()  # type: ignore[assignment]

    service = IngestionService(
        repository=repository,
        landing_zone=landing_zone,
        event_emitter=event_emitter,
    )

    config = ConnectorConfig(
        source_type=SourceType.CSV,
        source_name="Monthly Transaction Export",
        file_path="/data/exports/transactions.csv",
    )

    request = IngestionRequest(
        connector_config=config,
        pipeline_name="transaction_ingestion",
        trigger_type="scheduled",
        triggered_by="orchestration-service",
        tags={"department": "finance", "frequency": "monthly"},
    )

    result = await service.ingest(request)
    print(f"Batch: {result.batch_id}")
    print(f"Status: {result.status.value}")
    print(f"Rows: {result.total_rows}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Next steps: {result.next_steps}")


# ---------------------------------------------------------------------------
# Example 2: Database Ingestion with Dry Run
# ---------------------------------------------------------------------------

async def example_dry_run():
    """Validate ingestion configuration without actually ingesting data."""
    repository = MagicMock()  # type: ignore[assignment]
    landing_zone = MagicMock()  # type: ignore[assignment]

    service = IngestionService(
        repository=repository,
        landing_zone=landing_zone,
    )

    config = ConnectorConfig(
        source_type=SourceType.POSTGRESQL,
        source_name="Core Banking DB",
        host="localhost",
        port=5432,
        database="core_banking",
        username="etl_user",
        password="secret",
        table_name="public.transactions",
    )

    request = IngestionRequest(
        connector_config=config,
        pipeline_name="core_banking_ingestion",
        dry_run=True,  # Validate only
    )

    result = await service.ingest(request)
    print(f"Dry run completed for {result.source_name}")
    print(f"Status: {result.status.value}")


# ---------------------------------------------------------------------------
# Example 3: Batch ID Generation
# ---------------------------------------------------------------------------

def example_batch_id_format():
    """Demonstrate batch ID generation format."""
    batch_id = IngestionService._generate_batch_id()
    print(f"Generated batch ID: {batch_id}")
    # Example: 20260716143022-a1b2c3d4
    # Format: {YYYYMMDDHHMMSS}-{UUID8}

    parts = batch_id.split("-")
    timestamp_part = parts[0]
    uuid_part = parts[1]

    assert len(timestamp_part) == 14, "Timestamp part must be 14 digits (YYYYMMDDHHMMSS)"
    assert len(uuid_part) == 8, "UUID part must be 8 hex characters"

    year = int(timestamp_part[0:4])
    month = int(timestamp_part[4:6])
    day = int(timestamp_part[6:8])

    print(f"  Date: {year}-{month:02d}-{day:02d}")
    print(f"  UUID fragment: {uuid_part}")


# ---------------------------------------------------------------------------
# Example 4: Error Handling
# ---------------------------------------------------------------------------

async def example_error_handling():
    """Demonstrate graceful error handling during ingestion."""
    from etl.ingestion.service import IngestionError

    repository = AsyncMock()
    landing_zone = AsyncMock()
    event_emitter = AsyncMock()

    # Simulate landing zone failure
    landing_zone.write_chunk.side_effect = IOError("Disk full")

    service = IngestionService(
        repository=repository,
        landing_zone=landing_zone,
        event_emitter=event_emitter,
    )

    config = ConnectorConfig(
        source_type=SourceType.CSV,
        source_name="Test",
        file_path="/tmp/test.csv",
    )

    request = IngestionRequest(
        connector_config=config,
        pipeline_name="test_pipeline",
    )

    try:
        await service.ingest(request)
    except IngestionError as e:
        print(f"Ingestion failed as expected: {e}")
        print(f"Batch ID: {e.batch_id}")
        # Failure event should have been emitted
        event_emitter.emit_ingestion_failed.assert_called_once()
