"""
ETL Ingestion Framework - Data reception and routing layer.

Responsibilities:
- Receive incoming data from connectors
- Generate unique, sortable Batch IDs
- Register source system metadata
- Calculate SHA-256 checksums for integrity
- Store raw data in the immutable landing zone
- Persist batch/chunk metadata in database
- Emit events to trigger downstream validation

No business logic — pure data reception and routing.
"""

from etl.ingestion.interfaces import (
    IngestionEventEmitter,
    IngestionRepository,
    IngestionServiceInterface,
    LandingZoneWriter,
)
from etl.ingestion.repository import IngestionRepository as SqlIngestionRepository
from etl.ingestion.service import (
    ChecksumMismatchError,
    ConnectorExtractionError,
    IngestionError,
    IngestionService,
    LandingZoneWriteError,
)

__all__ = [
    # Interfaces / Protocols
    "LandingZoneWriter",
    "IngestionRepository",
    "IngestionEventEmitter",
    "IngestionServiceInterface",
    # Service
    "IngestionService",
    # Repository
    "SqlIngestionRepository",
    # Exceptions
    "IngestionError",
    "ConnectorExtractionError",
    "LandingZoneWriteError",
    "ChecksumMismatchError",
]
