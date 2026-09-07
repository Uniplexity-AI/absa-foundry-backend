---
name: absa-customer-lifecycle
description: "ABSA Bank Zambia — Customer Lifecycle Prediction System. ETL engine, Dynamic Extractor, authentication gateway, and feature engineering for AI-driven churn prediction, CLV, and Next Best Action recommendations. Use when working on any part of this codebase: ETL pipelines, extraction specs, auth middleware, gateway routes, IAM database, or feature engineering."
---

# ABSA Customer Lifecycle Prediction System

Enterprise-grade AI platform for banking customer lifecycle prediction, churn analysis, CLV, and NBA recommendations. Deployed on-premise (air-gapped Ubuntu servers). Python 3.12+ / FastAPI / PostgreSQL 16 / Redis 7 / Vue 3 frontend.

## Project Root

```
absa-foundry-backend/customer-lifecycle-ai/
```

All commands are run from this directory.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│              Dynamic Extractor (Pre-Processor)            │
│  YAML Spec → Join Validator → Query Builder              │
│  → Streaming → Pydantic v2 Validation → Business Rules    │
│  → DLQ (audit.rejected_records)                          │
└───────────────────────┬──────────────────────────────────┘
                        │ unified DataFrame
                        ▼
┌──────────────────────────────────────────────────────────┐
│              ETL Engine (run_etl.py)                      │
│  Schema Drift → Validate → Transform → Load              │
│  Output: *_clean / *_rejected in etl_clean               │
└───────────────────────┬──────────────────────────────────┘
                        │ clean data
                        ▼
┌──────────────────────────────────────────────────────────┐
│         API Gateway (:8080) — Auth / RBAC / Logging       │
│  /auth/*  /admin/*  /internal/*                           │
│  LDAP → JWT → RBAC → Rate Limit → API Key                │
└──────────────────────────────────────────────────────────┘
```

## Databases

| Database | Role | Tables |
|---|---|---|
| `etl_validation` | Source (raw data) | `raw_customers`, `raw_transactions`, `raw_interactions`, `customer_transactions` |
| `etl_clean` | Target (clean data) | `customers_clean`, `customers_rejected`, `etl.etl_audit` |
| `etl_validation` | IAM (auth) | `iam.users`, `iam.roles`, `iam.user_roles`, `iam.service_accounts`, `iam.api_keys`, `iam.refresh_tokens`, `iam.auth_audit` |

Connection: `postgresql://postgres:wamulehi@localhost:5432/etl_validation` (source) and `postgresql://postgres:wamulehi@localhost:5432/etl_clean` (target).

## Key Commands

```powershell
# ETL — single table extraction
python run_etl.py --source-table raw_customers --force
python run_etl.py --source-table raw_transactions --force

# ETL — Dynamic Extractor (YAML-driven)
python run_etl.py --extraction-spec etl/config/extraction_specs/customer_360.yaml --force
python run_etl.py --extraction-spec etl/config/extraction_specs/customer_360_multi.yaml --force

# Dry run (validate, no DB writes)
python run_etl.py --extraction-spec etl/config/extraction_specs/customer_360.yaml --dry-run

# Gateway
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8080 --reload --reload-dir gateway --reload-dir shared --reload-dir etl

# IAM seed (admin user + service accounts)
python scripts/seed_iam.py

# Auth test
curl -X POST http://localhost:8080/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"Admin123!"}'
```

## What's Built

### ETL Engine (`run_etl.py`)
- Config-driven via `etl/config/etl_config.yaml` — same engine handles any source table
- 4-phase pipeline: Extract → Validate → Transform → Load
- Schema drift detection (strict mode), idempotency guard, invariant checks
- Bulk inserts: 16,000+ rows/s via psycopg2 `execute_values`
- `target` section in config drives table names and column lists — zero code changes to switch pipelines
- Standby transaction pipeline preserved (commented) in config

### Dynamic Extractor (`etl/extraction/` — 9 files)
- `config_models.py` — 20+ Pydantic v2 models for YAML spec validation
- `query_builder.py` — Dynamic SQLAlchemy: 22 filter operators, multi-column JOINs, aggregations, calculated fields, incremental watermark
- `join_validator.py` — 8 pre-query checks (table exists, alias unique, no cross-joins, no cycles)
- `schema_factory.py` — Runtime Pydantic v2 model generation from YAML validation rules
- `business_rules.py` — AST-based safe expression evaluator (no eval/exec), supports tuples, lists, comparisons
- `streaming.py` — Server-side cursor streaming, constant memory
- `executor.py` — Full pipeline orchestrator, YAML → DLQ + valid DataFrame
- `version_guard.py` — Engine/spec compatibility
- Wired into `run_etl.py` via `--extraction-spec` flag as Phase 0

### Extraction Specs (`etl/config/extraction_specs/`)
- `customer_360.yaml` — Single-table: 9 fields from raw_customers, regex + 4 business rules
- `customer_360_multi.yaml` — 3-table JOIN (customers + transactions + interactions), 5 aggregations, 2 calculated fields
- **YAML gotcha:** The key `on` (as in `on:`) is a YAML boolean — must be quoted as `"on":`

### Authentication (Phases 1-3 — `shared/auth/` + `gateway/`)
- **Phase 1:** LDAP/AD authenticator, JWT service (create/verify/refresh/blacklist), RBAC (30 rules, 6 roles), API key service, auth middleware, routes
- **Phase 2:** Service accounts, API key CRUD, seed script
- **Phase 3:** Rate limiting (Redis sliding window), account lockout (5 attempts → 15 min), password policy, audit trail (iam.auth_audit), LDAP TLS
- Gateway: 14 routes, request logging middleware, CORS, health check
- Admin credentials: `admin` / `Admin123!` (dev mode — any password-passing-policy works)

### Documentation
- `docs/architecture/etl/dynamic-extractor-spec.md` — 18-section spec
- `docs/architecture/security/authentication-flow.md` — 15-section auth flow
- `docs/ml/feature-engineering-design-v1.md` — 48 features across 8 groups
- `AUTH-INTEGRATION.md` (frontend repo) — Vue 3 + Pinia + Axios integration

## Key Config Files

| File | Purpose |
|---|---|
| `etl/config/etl_config.yaml` | Active pipeline config — schema, validation, transformation, target tables |
| `etl/config/extraction_specs/*.yaml` | Dynamic Extractor specs — single-table and multi-table |
| `.env` | Database credentials, JWT secret, Redis URL, LDAP settings |

## Conventions

- Python 3.12+ syntax (`str | None`, not `Optional[str]`)
- Pydantic v2 for all data validation
- Google-style docstrings
- psycopg2 for sync DB access (ETL, auth repo)
- SQLAlchemy 2.0 for Dynamic Extractor (reflection, query building)
- FastAPI for all services
- Pinia for frontend state management
- Vue 3 Composition API + TypeScript for frontend

## Known Issues

1. Multi-table extraction: Pydantic Decimal → float coercion bug (query runs, data flows, validation rejects — `aggregation` fields need `object | None` type in schema_factory)
2. `ldap3` package not installed — LDAP auth falls back to dev mode
3. Feature Engineering Service: scaffold exists, no feature computation logic yet

## Related Repos

- Frontend: `absa-foundry-frontend` (Vue 3 + Vite + Tailwind)
- Frontend auth guide: `AUTH-INTEGRATION.md` in that repo
