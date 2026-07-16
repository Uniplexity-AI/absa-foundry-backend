"""
ETL Models - SQLAlchemy ORM models for ETL metadata tables.

Models for:
- etl_connector_registry: Registered data source connectors
- etl_batch_execution_log: Batch extraction history
- etl_ingestion_batch: Ingestion lifecycle tracking
- etl_ingestion_chunk: Per-chunk ingestion records
- etl_landing_file: Immutable landing zone file tracking
- etl_checkpoint: Pipeline checkpoint state
- etl_audit: Complete audit trail
- etl_validation_result: Per-record validation outcomes
- etl_pipeline_run: Pipeline execution history
"""

from etl.models.audit_models import AuditRecord
from etl.models.checkpoint_models import CheckpointRecord
from etl.models.connector_models import BatchExecutionLog, ConnectorRegistration
from etl.models.ingestion_models import IngestionBatchRecord, IngestionChunkRecord
from etl.models.landing_models import LandingFileRecord
from etl.models.monitoring_models import JobStatusRecord, PipelineMetricsRecord
from etl.models.orchestration_models import PipelineRunRecord
from etl.models.staging_models import StgAccount, StgBranch, StgCustomer, StgTransaction
from etl.models.validation_models import ValidationErrorRecord, ValidationRun

__all__ = [
    "AuditRecord",
    "CheckpointRecord",
    "ConnectorRegistration",
    "BatchExecutionLog",
    "IngestionBatchRecord",
    "IngestionChunkRecord",
    "LandingFileRecord",
    "JobStatusRecord",
    "PipelineMetricsRecord",
    "PipelineRunRecord",
    "StgCustomer",
    "StgAccount",
    "StgTransaction",
    "StgBranch",
    "ValidationRun",
    "ValidationErrorRecord",
]
