# Enterprise ETL Engine

## Overview

The ETL Engine provides end-to-end data pipeline capabilities for the Customer Lifecycle Prediction System. It ingests banking data from diverse source systems, validates and transforms it, and loads it into the tiered database architecture.

## Architecture

See [ETL Architecture Documentation](../docs/architecture/etl/README.md) for complete design details.

## Module Summary

| Module | Purpose |
|--------|---------|
| `connectors/` | Data source abstraction (database, API, files, streaming) |
| `ingestion/` | Data reception, batch ID generation, metadata capture |
| `landing/` | Immutable raw data storage (time-partitioned) |
| `validation/` | Modular validation (schema, business rules, dedup) |
| `transformation/` | Mapping, standardization, enrichment |
| `staging/` | Temporary validated data before production load |
| `loading/` | Ordered production database loading |
| `orchestration/` | DAG-based pipeline execution |
| `checkpoint/` | Resumable processing with state persistence |
| `monitoring/` | Real-time pipeline observability |
| `logging/` | Structured JSON logging (7 log streams) |
| `audit/` | Complete compliance audit trail |
| `config/` | Centralized configuration (env vars + YAML) |
| `pipelines/` | Assembled end-to-end ETL pipelines |
| `repositories/` | Data access layer (repository pattern) |
| `services/` | Business logic layer |
| `models/` | SQLAlchemy 2.0 ORM models |
| `schemas/` | Pydantic v2 data schemas |
| `utils/` | Helper utilities |

## Quick Start

```bash
# Run the ETL pipeline against the test dataset
python run_etl.py --csv scripts/etl_validation_customers.csv

# Dry run (validate only, no DB writes)
python run_etl.py --dry-run

# Force re-process an already-loaded file
python run_etl.py --csv data.csv --force

# Run the fixture regression test
pytest tests/test_validation_ground_truth.py -v

# Verify pipeline output against ground truth
python verify.py --verbose
```

## Production Features

| Feature | Description |
|---------|-------------|
| **Schema Drift Detection** | Fails loudly in strict mode on missing/reordered columns (configurable per `etl_config.yaml`) |
| **Idempotency Guard** | Detects duplicate loads by SHA-256 file hash in audit trail; `--force` to override |
| **Bulk Insert** | Batch inserts via `psycopg2.extras.execute_values` (5K-row chunks) — ~17K rows/s |
| **Structured Logging** | INFO/WARNING/ERROR levels with timestamps; UTF-8 output |
| **Invariant Checks** | Conservation, no silent skips, reason coverage, quality floor — run on every batch |
| **Immutable Audit** | `etl.etl_audit` — 24-column compliance trail, one record per batch, append-only |
| **Per-Row Rejections** | Every row in `customer_transactions_rejected` carries its specific failed rule ID(s) |
| **Constraint Rescue** | Rows failing DB constraints are rescued to rejected table, never silently dropped |

## Status

- **Phase 1:** Architecture scaffolding — COMPLETE
- **Phase 2a:** ETL engine production hardening — COMPLETE
- **Phase 2b:** API service implementation — IN PROGRESS
- **All 15 modules implemented** with 120+ unit/integration tests + fixture regression suite
- **All 15 modules implemented** with 120+ unit/integration tests

### Implementation Summary

| # | Module | Files | Tests | Status |
|---|--------|-------|-------|--------|
| 1 | Connectors | 7 | 20+ | ✅ |
| 2 | Ingestion | 4 | 20+ | ✅ |
| 3 | Landing Zone | 4 | 20+ | ✅ |
| 4 | Validation Engine | 6 | 25+ | ✅ |
| 5 | Transformation Engine | 5 | 18+ | ✅ |
| 6 | Staging Database | 3 | 14+ | ✅ |
| 7 | Production Loader | 3 | 14+ | ✅ |
| 8 | Orchestration Engine | 3 | 12+ | ✅ |
| 9 | Checkpoint Engine | 3 | 14+ | ✅ |
| 10 | Monitoring | 3 | 13+ | ✅ |
| 11 | Logging | 2 | 16+ | ✅ |
| 12 | Audit | 3 | 7+ | ✅ |
| 13 | Configuration | 2 | 4+ | ✅ |
| 14 | Pipeline Integration | 2 | 6+ | ✅ |
| 15 | Integration Tests | 1 | 10+ | ✅ |

**Total: 70+ source files, 17 ORM models, 12 schema modules, 120+ tests**
