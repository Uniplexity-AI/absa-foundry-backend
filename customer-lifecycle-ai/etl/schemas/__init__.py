"""
ETL Schemas - Pydantic v2 schemas for ETL data structures.

Schemas for:
- Connector output (Dataset, Metadata, BatchInfo, ConnectorConfig)
- Ingestion (IngestionRequest, IngestionBatch, IngestionResult, IngestionEvent)
- Landing Zone (LandingPath, LandingFileRecord, LandingZoneConfig)
- Validation rules and results
- Transformation mappings
- Pipeline configuration
- Audit records
"""

from etl.schemas.connector_schemas import (
    BatchMetadata,
    ConnectionTestResult,
    ConnectorConfig,
    ConnectorCreateRequest,
    ConnectorInfo,
    Dataset,
    DatasetFormat,
    SourceType,
)
from etl.schemas.ingestion_schemas import (
    IngestionBatch,
    IngestionEvent,
    IngestionRequest,
    IngestionResult,
    IngestionStatus,
)
from etl.schemas.landing_schemas import (
    LandingFileFormat,
    LandingFileRecord,
    LandingFileStatus,
    LandingPath,
    LandingZoneConfig,
)
from etl.schemas.transformation_schemas import (
    DerivedFieldRule,
    EnrichmentRule,
    FieldMapping,
    StandardizationRule,
    TransformationConfig,
    TransformationReport,
    TransformType,
)

__all__ = [
    # Connector schemas
    "ConnectorConfig",
    "BatchMetadata",
    "Dataset",
    "DatasetFormat",
    "SourceType",
    "ConnectionTestResult",
    "ConnectorCreateRequest",
    "ConnectorInfo",
    # Ingestion schemas
    "IngestionRequest",
    "IngestionBatch",
    "IngestionResult",
    "IngestionStatus",
    "IngestionEvent",
    # Landing zone schemas
    "LandingPath",
    "LandingFileRecord",
    "LandingFileFormat",
    "LandingFileStatus",
    "LandingZoneConfig",
    # Transformation schemas
    "FieldMapping",
    "StandardizationRule",
    "DerivedFieldRule",
    "EnrichmentRule",
    "TransformationConfig",
    "TransformationReport",
    "TransformType",
]
