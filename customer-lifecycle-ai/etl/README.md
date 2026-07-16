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
# The ETL engine runs as part of the docker-compose orchestration
docker-compose up -d

# Trigger a pipeline run via the orchestration service API
curl -X POST http://localhost:8080/api/v1/etl/pipelines/run \
  -H "Content-Type: application/json" \
  -d '{"pipeline": "customer_data_ingestion", "source": "core_banking"}'
```

## Status

- **Phase 1:** Architecture scaffolding — COMPLETE
- **Phase 2:** Module implementation — COMPLETE
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
