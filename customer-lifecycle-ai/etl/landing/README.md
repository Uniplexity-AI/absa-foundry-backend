# ETL Landing Zone

## Overview

The Landing Zone provides immutable raw data storage for the ETL pipeline. All ingested data is written here first before any validation or transformation occurs. Files are write-once, read-many — never modified, never deleted (until archival).

## Architecture

```
┌──────────────────────────────────┐
│      IngestionService            │
│  (writes via LandingZoneWriter   │
│   protocol)                      │
└────────────┬─────────────────────┘
             │ write_chunk(dataset, batch_id, chunk_index)
             ▼
┌──────────────────────────────────┐
│   LocalLandingZoneWriter         │
│                                  │
│  1. Create directory structure   │
│  2. Write Parquet file           │
│  3. Compute SHA-256 checksum     │
│  4. Register in DB               │
│  5. Mark as LANDED               │
└────────┬───────────┬─────────────┘
         │           │
         ▼           ▼
┌─────────────┐ ┌──────────────┐
│  Filesystem │ │  Database    │
│  landing/   │ │  etl_landing │
│  YYYY/MM/DD │ │  _file       │
└──────┬──────┘ └──────────────┘
       │
       ▼ (read-only)
┌──────────────────────────────────┐
│   LocalLandingZoneReader         │
│  (used by validation,            │
│   transformation modules)        │
└──────────────────────────────────┘
```

## Directory Structure

```
/data/landing/
├── 2026/
│   ├── 07/
│   │   ├── 16/
│   │   │   ├── 20260716143022-a1b2c3d4/
│   │   │   │   ├── chunk_0000.parquet
│   │   │   │   ├── chunk_0001.parquet
│   │   │   │   └── chunk_0002.parquet
│   │   │   └── 20260716180000-e5f6g7h8/
│   │   │       └── chunk_0000.parquet
```

**Key properties:**
- **Immutable:** Files are never modified after write
- **Time-partitioned:** `YYYY/MM/DD/{batch_id}/` for efficient listing
- **Parquet by default:** Columnar, compressed (snappy), analytics-optimized
- **Checksummed:** Every file has SHA-256 for integrity verification
- **Database-tracked:** Every file registered in `etl.etl_landing_file`

## Usage

```python
from etl.landing import LocalLandingZoneWriter, LocalLandingZoneReader
from etl.schemas.landing_schemas import LandingZoneConfig

# Writer — used by IngestionService
config = LandingZoneConfig(base_path="/data/landing")
writer = LocalLandingZoneWriter(config=config)
path = await writer.write_chunk(dataset, batch_id="20260716-a1b2c3d4", chunk_index=0)

# Reader — used by Validation/Transformation
reader = LocalLandingZoneReader(config=config)
df = await reader.read_chunk(
    LandingPath.from_batch_id("20260716-a1b2c3d4"), chunk_index=0
)
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `base_path` | `/data/landing` | Root directory |
| `default_format` | `parquet` | File format |
| `compression` | `snappy` | Compression codec |
| `max_file_size_mb` | `256` | Max file size before split |
| `enable_checksum_verification` | `true` | Verify after write |
| `retention_days` | `2555` | ~7 year retention |

## Skills

### Adding a New Storage Backend

Implement the `LandingZoneWriter` protocol:

```python
class S3LandingZoneWriter:
    async def write_dataset(self, dataset, batch_id) -> str: ...
    async def write_chunk(self, dataset, batch_id, chunk_index) -> str: ...
```

Then inject into `IngestionService`:

```python
service = IngestionService(
    repository=repo,
    landing_zone=S3LandingZoneWriter(),
)
```
