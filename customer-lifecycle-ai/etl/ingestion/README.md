# ETL Ingestion Framework

## Overview

The Ingestion Framework is the data reception and routing layer of the ETL Engine. It receives Datasets from connectors, generates metadata, computes checksums, stores raw data in the landing zone, persists metadata, and emits events to trigger downstream validation.

**Key principle:** No business logic — pure data reception and routing.

## Architecture

```
┌──────────────┐
│  Connector   │  Extracts data from source
└──────┬───────┘
       │ Dataset (DataFrame + Metadata)
       ▼
┌──────────────────────────────────────────────┐
│            IngestionService                   │
│                                               │
│  1. Generate Batch ID                        │
│  2. Compute checksum per chunk               │
│  3. Write raw data → Landing Zone            │
│  4. Persist metadata → IngestionRepository   │
│  5. Emit event → IngestionEventEmitter       │
│                                               │
│  Dependencies (injected):                    │
│    • LandingZoneWriter (Protocol)            │
│    • IngestionRepository (Protocol)          │
│    • IngestionEventEmitter (Protocol)        │
└──────────┬──────────┬───────────┬────────────┘
           │          │           │
           ▼          ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌──────────┐
    │ Landing │ │   DB    │ │  Event   │
    │  Zone   │ │  Repo   │ │  Bus     │
    └─────────┘ └─────────┘ └──────────┘
```

## Ingestion Lifecycle

```
RECEIVED → CHECKSUMMED → LANDED → REGISTERED → VALIDATION_TRIGGERED
                                                       │
                                              (triggers validation engine)
```

Each status transition is recorded in the database with timestamps.

## Usage

```python
from etl.ingestion import IngestionService
from etl.schemas.ingestion_schemas import IngestionRequest
from etl.schemas.connector_schemas import ConnectorConfig, SourceType

# Configure ingestion
config = ConnectorConfig(
    source_type=SourceType.CSV,
    source_name="Monthly Transactions",
    file_path="/data/exports/transactions_202607.csv",
)

request = IngestionRequest(
    connector_config=config,
    pipeline_name="transaction_ingestion",
    trigger_type="scheduled",
    triggered_by="orchestration-service",
)

# Execute ingestion (dependencies injected)
service = IngestionService(
    repository=repo,
    landing_zone=landing_writer,
    event_emitter=event_bus,
)

result = await service.ingest(request)
print(f"Ingested {result.total_rows} rows in {result.duration_seconds:.2f}s")
print(f"Batch: {result.batch_id}")
print(f"Landing: {result.landing_path}")
```

## Batch ID Format

Batch IDs follow the pattern: `{YYYYMMDDHHMMSS}-{UUID8}`

Example: `20260716143022-a1b2c3d4`

This provides both chronological sorting and global uniqueness.

## Skills

### Adding a Custom Landing Zone Writer

Implement the `LandingZoneWriter` protocol:

```python
class S3LandingZoneWriter:
    async def write_dataset(self, dataset, batch_id) -> str:
        # Write to S3
        ...

    async def write_chunk(self, dataset, batch_id, chunk_index) -> str:
        # Write chunk to S3
        ...
```

## Examples

See `examples/` directory for complete usage examples.
