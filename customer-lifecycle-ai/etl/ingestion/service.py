"""
ETL Ingestion Service - Core ingestion orchestration.

The IngestionService is the central orchestrator for data reception.
It receives Datasets from connectors, generates metadata, computes
checksums, stores raw data in the landing zone, persists metadata,
and emits events to trigger downstream validation.

No business logic — pure data reception and routing.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from etl.connectors.factory import create_connector
from etl.connectors.interfaces import Connector
from etl.ingestion.interfaces import (
    IngestionEventEmitter,
    IngestionRepository,
    IngestionServiceInterface,
    LandingZoneWriter,
)
from etl.schemas.connector_schemas import Dataset
from etl.schemas.ingestion_schemas import (
    IngestionBatch,
    IngestionEvent,
    IngestionRequest,
    IngestionResult,
    IngestionStatus,
)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class IngestionError(Exception):
    """Base exception for ingestion failures."""
    def __init__(self, message: str, batch_id: str | None = None) -> None:
        self.batch_id = batch_id
        super().__init__(message)


class ConnectorExtractionError(IngestionError):
    """Raised when the connector fails to extract data."""
    pass


class LandingZoneWriteError(IngestionError):
    """Raised when writing to the landing zone fails."""
    pass


class ChecksumMismatchError(IngestionError):
    """Raised when the computed checksum doesn't match expected."""
    pass


# ---------------------------------------------------------------------------
# Ingestion Service
# ---------------------------------------------------------------------------

class IngestionService(IngestionServiceInterface):
    """Core ingestion service orchestrating the data reception pipeline.

    Flow:
        1. Create connector from config
        2. Connect to source
        3. Generate batch ID
        4. Extract data in chunks
        5. Compute checksums per chunk
        6. Write raw data to landing zone
        7. Persist metadata to database
        8. Emit completion event → triggers validation
        9. Disconnect connector

    Dependencies are injected via constructor for testability.
    """

    def __init__(
        self,
        repository: IngestionRepository,
        landing_zone: LandingZoneWriter,
        event_emitter: IngestionEventEmitter | None = None,
    ) -> None:
        """Initialize the ingestion service with its dependencies.

        Args:
            repository: Persistence layer for batch/chunk metadata.
            landing_zone: Writer for immutable raw storage.
            event_emitter: Optional event emitter for downstream triggers.
        """
        self._repository = repository
        self._landing_zone = landing_zone
        self._event_emitter = event_emitter

    async def ingest(self, request: IngestionRequest) -> IngestionResult:
        """Execute the full ingestion pipeline.

        Args:
            request: Configuration for the ingestion run.

        Returns:
            IngestionResult summarizing the ingestion outcome.

        Raises:
            IngestionError: If any step fails.
        """
        start_time = time.monotonic()
        batch_id = self._generate_batch_id()

        # Initialize batch metadata
        batch = IngestionBatch(
            batch_id=batch_id,
            pipeline_name=request.pipeline_name,
            source_type=request.connector_config.source_type,
            source_name=request.connector_config.source_name,
            status=IngestionStatus.RECEIVED,
            trigger_type=request.trigger_type,
            triggered_by=request.triggered_by,
            correlation_id=request.correlation_id,
            priority=request.priority,
            tags=request.tags,
        )

        if request.dry_run:
            batch.status = IngestionStatus.VALIDATION_TRIGGERED
            batch.completed_at = datetime.now(timezone.utc)
            batch.duration_seconds = time.monotonic() - start_time
            return IngestionResult.from_batch(batch)

        connector: Connector | None = None

        try:
            # Step 1: Create and connect connector
            connector = create_connector(request.connector_config)
            await connector.connect()

            # Step 2: Persist initial batch record
            await self._repository.save_batch(batch)

            # Step 3: Extract data in chunks, land each one
            checksums: list[str] = []
            chunk_index = 0
            total_rows = 0
            total_size = 0

            async for dataset in connector.extract():
                if request.max_rows and total_rows >= request.max_rows:
                    break

                # Compute chunk checksum
                chunk_checksum = self._compute_checksum(dataset)
                checksums.append(chunk_checksum)

                # Calculate chunk size (approx)
                chunk_size = self._estimate_size_bytes(dataset)

                # Write chunk to landing zone
                try:
                    chunk_path = await self._landing_zone.write_chunk(
                        dataset, batch_id, chunk_index
                    )
                except Exception as e:
                    raise LandingZoneWriteError(
                        f"Failed to write chunk {chunk_index} to landing zone: {e}",
                        batch_id=batch_id,
                    ) from e

                # Persist chunk metadata
                await self._repository.save_chunk(
                    batch_id=batch_id,
                    chunk_index=chunk_index,
                    row_count=dataset.row_count,
                    size_bytes=chunk_size,
                    checksum=chunk_checksum,
                    chunk_path=chunk_path,
                    column_names=dataset.column_names,
                    column_types=dataset.column_types,
                )

                total_rows += dataset.row_count
                total_size += chunk_size
                chunk_index += 1

            # Step 4: Compute aggregate checksum
            aggregate_checksum = self._compute_aggregate_checksum(checksums)

            # Step 5: Update batch with final state
            batch.total_rows = total_rows
            batch.total_chunks = chunk_index
            batch.total_size_bytes = total_size
            batch.checksum_sha256 = aggregate_checksum
            batch.landing_path = self._build_landing_path(batch_id)
            batch.status = IngestionStatus.LANDED
            batch.landed_at = datetime.now(timezone.utc)

            await self._repository.update_batch_status(
                batch_id=batch_id,
                status=IngestionStatus.LANDED.value,
                total_rows=total_rows,
                total_chunks=chunk_index,
                total_size_bytes=total_size,
                checksum_sha256=aggregate_checksum,
                landing_path=batch.landing_path,
                landed_at=batch.landed_at,
            )

            # Step 6: Register completion
            batch.status = IngestionStatus.REGISTERED
            batch.registered_at = datetime.now(timezone.utc)
            await self._repository.update_batch_status(
                batch_id=batch_id,
                status=IngestionStatus.REGISTERED.value,
                registered_at=batch.registered_at,
            )

            # Step 7: Emit completion event → triggers validation
            batch.status = IngestionStatus.VALIDATION_TRIGGERED
            batch.completed_at = datetime.now(timezone.utc)
            batch.duration_seconds = time.monotonic() - start_time

            await self._repository.update_batch_status(
                batch_id=batch_id,
                status=IngestionStatus.VALIDATION_TRIGGERED.value,
                completed_at=batch.completed_at,
                duration_seconds=batch.duration_seconds,
            )

            if self._event_emitter:
                await self._event_emitter.emit_ingestion_completed(batch)

            return IngestionResult.from_batch(batch)

        except Exception as e:
            # Record failure
            duration = time.monotonic() - start_time
            error_msg = str(e)
            batch.status = IngestionStatus.FAILED
            batch.completed_at = datetime.now(timezone.utc)
            batch.duration_seconds = duration
            batch.error_message = error_msg

            try:
                await self._repository.update_batch_status(
                    batch_id=batch_id,
                    status=IngestionStatus.FAILED.value,
                    completed_at=batch.completed_at,
                    duration_seconds=duration,
                    error_message=error_msg,
                )
            except Exception:
                pass  # Don't mask the original error

            if self._event_emitter:
                await self._event_emitter.emit_ingestion_failed(batch_id, error_msg)

            if isinstance(e, IngestionError):
                raise
            raise IngestionError(
                f"Ingestion failed for batch {batch_id}: {error_msg}",
                batch_id=batch_id,
            ) from e

        finally:
            if connector:
                try:
                    await connector.disconnect()
                except Exception:
                    pass  # Best-effort disconnect

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _generate_batch_id() -> str:
        """Generate a unique, sortable batch identifier.

        Format: {YYYYMMDDHHMMSS}-{UUID4}
        This provides both chronological sorting and global uniqueness.

        Returns:
            Batch ID string.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"{timestamp}-{short_uuid}"

    @staticmethod
    def _compute_checksum(dataset: Dataset) -> str:
        """Compute SHA-256 checksum of a dataset's data.

        Serializes the DataFrame to JSON (sorted keys for determinism)
        and computes SHA-256. For large datasets this runs in-memory;
        production may need a streaming approach.

        Args:
            dataset: The dataset to checksum.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        records = dataset.data.to_dict(orient="records")
        serialized = json.dumps(records, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _compute_aggregate_checksum(checksums: list[str]) -> str:
        """Compute an aggregate checksum from individual chunk checksums.

        Concatenates all chunk checksums and hashes the result.

        Args:
            checksums: List of hex-encoded SHA-256 digests.

        Returns:
            Aggregate hex-encoded SHA-256 digest.
        """
        combined = "".join(sorted(checksums))
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    @staticmethod
    def _estimate_size_bytes(dataset: Dataset) -> int:
        """Estimate the in-memory size of a dataset in bytes.

        Uses pandas memory_usage for a reasonable estimate.

        Args:
            dataset: The dataset to measure.

        Returns:
            Estimated size in bytes.
        """
        try:
            return int(dataset.data.memory_usage(deep=True).sum())
        except Exception:
            return 0

    @staticmethod
    def _build_landing_path(batch_id: str) -> str:
        """Build the landing zone path for a batch.

        Format: landing/YYYY/MM/DD/{batch_id}/

        Args:
            batch_id: The batch identifier.

        Returns:
            Relative landing zone path.
        """
        now = datetime.now(timezone.utc)
        return f"landing/{now.year:04d}/{now.month:02d}/{now.day:02d}/{batch_id}"
