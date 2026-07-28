# Customer Lifecycle Prediction System — System Design Document

> **Version:** 0.3.0  
> **Last Updated:** 2026-07-24  
> **Architecture:** Python (orchestrator) + Go (execution engine)  
> **PoC Branch:** `poc-90day`  
> **Target Branch:** `architecture-target-full`

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Decision: Python + Go](#2-architecture-decision-python--go)
3. [Repository Structure](#3-repository-structure)
4. [API Gateway (Python / FastAPI)](#4-api-gateway-python--fastapi)
5. [Authentication & RBAC](#5-authentication--rbac)
6. [ETL Engine](#6-etl-engine)
7. [Go Execution Layer (Planned)](#7-go-execution-layer-planned)
8. [3-Layer AI Services](#8-3-layer-ai-services)
9. [Database Architecture](#9-database-architecture)
10. [Communication Patterns](#10-communication-patterns)
11. [Deployment](#11-deployment)
12. [Task Handoff Guide](#12-task-handoff-guide)

---

## 1. System Overview

### What It Does

An enterprise AI platform for Absa Bank Zambia that:

1. **Ingests** customer data from core banking, CRM, transactions
2. **Validates & transforms** via configurable ETL pipelines
3. **Predicts** customer churn, lifetime value, and health scores
4. **Recommends** Next Best Actions (NBA) for relationship managers
5. **Presents** actionable dashboards to branch staff

### High-Level Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    Vue 3 Dashboard (Frontend)                 │
│                    Port 5173 (dev) / Nginx (prod)             │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP/REST (JSON)
┌──────────────────────────▼───────────────────────────────────┐
│              FastAPI Gateway (Python 3.12)                    │
│              Port 8080                                        │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Auth     │ │ RBAC     │ │ Rate     │ │ ETL Dashboard │  │
│  │ LDAP/JWT │ │ 4 Roles  │ │ Limiter  │ │ API           │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼───────┐  ┌───────▼───────┐  ┌───────▼───────────────┐
│ AI Services   │  │ ETL Control   │  │ Go Runtime (Planned)   │
│ (Python)      │  │ (Python)      │  │ (High Performance)     │
│               │  │               │  │                        │
│ • State Svc   │  │ • YAML Parser │  │ • Extraction Engine    │
│ • Prediction  │  │ • Validator   │  │ • Bulk Loader          │
│ • Decision    │  │ • Transformer │  │ • Parallel Workers     │
│ • Feature Eng │  │ • Compiler    │  │ • Retry Manager        │
│               │  │ • Auditor     │  │ • File Processor       │
└───────────────┘  └───────────────┘  └────────────────────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              Data Layer                                      │
│                                                               │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ PostgreSQL 16  │  │ Redis (Cache)  │  │ File Storage  │  │
│  │ • etl_clean    │  │ • Rate limits  │  │ • CSV/Parquet │  │
│  │ • customer_    │  │ • Token black- │  │ • Extracts    │  │
│  │   lifecycle    │  │   list         │  │ • Archives    │  │
│  │ • iam          │  │ • Job queues   │  │              │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Decision: Python + Go

### Philosophy

> **Python is the brain. Go is the muscle.**

The gateway is an orchestration engine — it coordinates pipelines, enforces business rules, and manages auth. Python (FastAPI) excels at this. Moving it to Go would mean rebuilding mature logic without meaningful gain.

The performance gains come from moving the **data-intensive execution** to Go: reading/writing millions of rows, concurrent I/O, retry management, and parallel work distribution.

### What Stays in Python

| Component | Rationale |
|---|---|
| API Gateway (FastAPI) | Mature ecosystem, rich middleware, async support |
| Auth (LDAP/JWT/RBAC) | `ldap3`, `PyJWT` are Python-native |
| YAML Pipeline Parser | Business logic — easier to express in Python |
| Validation Rules Engine | Regex, lookup, custom rules |
| Business Rules Engine | `if age > 18`, `balance < loan_amount` |
| Transformation Engine | Data cleansing, standardization |
| AI Models (XGBoost/LightGBM) | `scikit-learn`, `xgboost`, `shap` |
| Feature Engineering | `pandas`, `numpy` |
| Audit Logging | Immutable records, compliance |

### What Moves to Go

| Component | Priority | Rationale |
|---|---|---|
| **Extraction Engine** | ⭐⭐⭐⭐⭐ | Millions of rows → goroutines per source, streaming |
| **Bulk Loader** | ⭐⭐⭐⭐⭐ | Worker pools, concurrent COPY/INSERT |
| **Parallel Workers** | ⭐⭐⭐⭐⭐ | One goroutine per data source (Core Banking, CRM, Loans, Cards...) |
| **Retry Manager** | ⭐⭐⭐⭐⭐ | Thousands of idle goroutines with near-zero overhead |
| **File Processor** | ⭐⭐⭐⭐⭐ | Stream CSV/Parquet/JSON/XML without loading into memory |
| Connection Pool Manager | ⭐⭐⭐⭐ | Efficient Postgres connection pooling |
| Incremental Load Processor | ⭐⭐⭐⭐ | Delta detection, watermark tracking |
| Scheduler Worker | ⭐⭐⭐ | Cron-like scheduling |
| Stream Processor | ⭐⭐⭐ | Stream records to Python as they arrive |

---

## 3. Repository Structure

```
customer-lifecycle-ai/
│
├── gateway/                        # FastAPI Gateway (Python)
│   ├── main.py                     # App factory, middleware chain
│   ├── dependencies.py             # Depends() callables (auth, RBAC, API key)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── middleware/
│   │   ├── auth.py                 # JWT validation
│   │   ├── rbac.py                 # Role-based access control
│   │   ├── api_key.py              # X-API-Key validation
│   │   ├── logging.py              # Request logging
│   │   └── rate_limit.py           # Redis sliding window
│   ├── routes/
│   │   ├── auth_routes.py          # /auth/*
│   │   ├── admin_routes.py         # /admin/*
│   │   ├── api_key_routes.py       # /admin/api-keys
│   │   └── etl_routes.py           # /api/etl/*
│   ├── services/
│   │   └── etl_service.py          # ETL dashboard business logic
│   └── schemas/
│       └── etl_schemas.py          # Pydantic v2 response models
│
├── etl/                            # ETL Engine (Python)
│   ├── pipelines/runner.py         # Pipeline registry + runner
│   ├── orchestration/service.py    # DAG-based execution engine
│   ├── extraction/                 # Dynamic extractor (9 files, YAML-driven)
│   ├── validation/                 # Schema drift, business rules
│   ├── transformation/             # Cleansing, standardization
│   ├── loading/                    # Bulk insert service
│   ├── ingestion/                  # CSV/DB connectors
│   ├── audit/                      # Immutable audit trail
│   ├── models/                     # SQLAlchemy ORM (10 models)
│   ├── schemas/                    # Pydantic v2 domain schemas (12 files)
│   ├── repositories/               # Data access layer
│   │   └── etl_repository.py       # ETL dashboard queries
│   ├── connectors/                 # DB connectors, CSV readers
│   └── config/                     # Extraction specs (YAML)
│
├── go-executor/                    # Go Execution Layer (PLANNED)
│   ├── cmd/
│   │   └── executor/main.go        # Entry point
│   ├── internal/
│   │   ├── extractor/              # DB extraction engine
│   │   ├── loader/                 # Bulk loading with worker pools
│   │   ├── worker/                 # Parallel execution engine
│   │   ├── retry/                  # Retry manager
│   │   ├── fileio/                 # CSV/Parquet/JSON/XML streaming
│   │   ├── pool/                   # Connection pool manager
│   │   └── grpc/                    # gRPC server (Python ↔ Go)
│   ├── go.mod
│   └── go.sum
│
├── services/                       # AI Services (Python)
│   ├── customer-state-service/     # Layer 1: Markov state tracking
│   ├── prediction-service/         # Layer 2: XGBoost/LightGBM
│   ├── decision-intelligence-service/ # Layer 3: NBA recommendations
│   ├── feature-engineering-service/   # Central feature store
│   ├── model-management-service/      # Champion/challenger registry
│   ├── dashboard-service/             # Analytics aggregation
│   └── orchestration-service/         # Workflow coordination
│
├── shared/                         # Shared Python libraries
│   ├── auth/                       # JWT, LDAP, RBAC, permissions
│   ├── config/                     # pydantic-settings
│   ├── database/                   # Async session factory, engines
│   └── exceptions/                 # Custom exceptions
│
├── models/                         # ML artifacts
│   ├── champion/                   # Production models
│   ├── challenger/                 # Models under evaluation
│   └── registry.json               # Model metadata
│
├── infrastructure/                 # Docker, Nginx, Postgres, Redis configs
├── database/                       # SQL migrations (IAM, ETL schemas)
├── docs/                           # Documentation
│   └── architecture/
│       └── gateway-reference.md    # Gateway deep-dive
├── scripts/                        # Seed data, evaluation
├── research/                       # Jupyter notebooks
├── run_etl.py                      # ETL CLI entry point
├── verify.py                       # Ground-truth verification
├── docker-compose.yml
└── requirements.txt
```

---

## 4. API Gateway (Python / FastAPI)

### Request Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│ 1. Logging Middleware                                   │
│    method, path, status, duration, caller, IP           │
├─────────────────────────────────────────────────────────┤
│ 2. CORS Middleware                                      │
│    allow_origins=["*"], credentials, methods, headers   │
├─────────────────────────────────────────────────────────┤
│ 3. RBAC Middleware (global)                             │
│    Checks roles against permissions matrix              │
│    Skips: /auth/*, /health, /docs                       │
│    Returns 403: {error, required_roles, user_roles}     │
├─────────────────────────────────────────────────────────┤
│ 4. Route Handler                                        │
│    Thin routes → Service → Repository → Database        │
│    Optional Depends(): auth, rate_limit, api_key        │
└─────────────────────────────────────────────────────────┘
```

### Route Map

| Prefix | Routes | Roles | Status |
|--------|--------|-------|--------|
| `/auth` | login, refresh, logout, me | Public (JWT for /me) | ✅ Done |
| `/admin` | users, roles | ADMIN | ⚠️ Read-only (CRUD stubs) |
| `/admin/api-keys` | create, list, revoke | ADMIN | ✅ Done |
| `/api/etl` | runs (dashboard) | ADMIN, OPERATIONS | ✅ Done |
| `/dashboard` | customers, recommendations, health-scores | ADMIN, RM | ❌ Not built |
| `/models` | registry, train, evaluate, deploy | ADMIN, DATA_SCIENTIST | ❌ Not built |
| `/monitoring` | health, metrics, pipelines | ADMIN, OPERATIONS | ❌ Not built |
| `/health` | health check | Public | ✅ Done |

### Layer Architecture (Every Route Follows This)

```
Route (THIN — one-line delegation)
  ↓ Depends(get_service)
Service (ALL business logic)
  ↓ Repository
Repository (ALL data access)
  ↓ SQLAlchemy / raw SQL
Database
```

---

## 5. Authentication & RBAC

### Login Flow

```
POST /auth/login { username, password }
  → Rate limit check (5 req / 15 min per IP)
  → Account lockout check (5 failures → 15-min lock)
  → Password policy validation (8+ chars, uppercase, digit)
  → LDAP/AD bind (or dev-mode bypass if LDAP disabled)
  → UserRepository.sync_user() → upsert into iam.users
  → SELECT roles FROM iam.user_roles → build UserContext
  → TokenService.create_access_token(roles=["RELATIONSHIP_MANAGER"])
  → TokenService.create_refresh_token()
  → AuthAudit log → iam.auth_audit
  → Response: { access_token, refresh_token, expires_in, token_type }
```

### 4 Roles

| Role | Access |
|---|---|
| **ADMIN** | Everything |
| **RELATIONSHIP_MANAGER** | `/dashboard/*` |
| **DATA_SCIENTIST** | `/models/*` |
| **OPERATIONS** | `/monitoring/*`, `/api/etl/**` |

### RBAC Enforcement

- JWT payload contains `roles: [...]`
- RBAC middleware checks `has_permission(user.roles, method, path)`
- `shared/auth/permissions.py` — 30 rules, wildcard support (`/api/etl/**`)
- 403 response: `{ "error": "Insufficient permissions", "required_roles": [...], "user_roles": [...] }`

### IAM Database Schema

```sql
iam.roles          (role_id, role_name, description, created_at)
iam.users          (user_id, username, email, display_name, department, branch_code, ...)
iam.user_roles     (user_id, role_id, granted_at, granted_by)  -- many-to-many
iam.api_keys       (key_id, key_hash, key_prefix, service_name, scopes, ...)
iam.refresh_tokens (token_id, user_id, token_hash, expires_at, revoked_at)
iam.auth_audit     (event_id, user_id, event_type, ip_address, success, ...)
```

---

## 6. ETL Engine

### Pipeline Phases

```
Phase 0: Dynamic Extraction (YAML-driven SQL)
  → Config models → Version guard → Join validator → Query builder
  → Streaming extraction → Pydantic v2 validation
  → Business rules engine → DLQ (audit.rejected_records)

Phase 1: EXTRACT (CSV connector or DB connector)
Phase 2: VALIDATE (schema drift, invariants, business rules)
Phase 3: TRANSFORM (cleansing, standardization, enrichment)
Phase 4: LOAD (bulk insert → etl_clean, rejected → audit.rejected_records)
Phase 5: AUDIT (immutable record → etl.etl_audit)
```

### Key Database Tables

| Table | Schema | Purpose |
|---|---|---|
| `etl_audit` | `etl` | Immutable audit trail — one record per batch |
| `etl_ingestion_batch` | `etl` | Batch metadata (source, status, checksum) |
| `etl_validation_run` | `etl` | Validation results per run |
| `etl_validation_error` | `etl` | Individual rejected records |
| `customers_clean` | `etl_clean` | Cleansed customer data |

### ETL Dashboard API

```
GET /api/etl/runs?page=1&limit=25&status=COMPLETED

Response:
{
  kpis:     { todays_runs, successful_runs, failed_runs, avg_quality, avg_duration, success_rate },
  status:   { current_status, last_successful_run, latest_quality, sla_threshold, last_failure },
  quality_trend: [{ label, value, rows, rejected, failed }],
  runs:     [{ runId, batchId, duration, rowsReceived, rowsValid, rowsLoaded, rowsRejected,
               qualityScore, qualityClass, status, statusClass }],
  total_runs, page, limit
}
```

Data source: `etl.etl_audit` in `etl_clean` (target DB). Uses raw SQL via `sqlalchemy.text()` because the ORM model has columns not present in the table (created by `run_etl.py` raw psycopg2).

---

## 7. Go Execution Layer (Planned)

### Architecture

```
┌──────────────────────────────────────────────┐
│              Python FastAPI Gateway           │
│              (Orchestrator)                   │
└──────────────────┬───────────────────────────┘
                   │ gRPC / Redis Queue
┌──────────────────▼───────────────────────────┐
│              Go Executor Service              │
│                                               │
│  ┌─────────────┐  ┌─────────────┐            │
│  │ Extractor   │  │ Bulk Loader │            │
│  │ (goroutines │  │ (worker     │            │
│  │  per source)│  │  pools)     │            │
│  └─────────────┘  └─────────────┘            │
│  ┌─────────────┐  ┌─────────────┐            │
│  │ Parallel    │  │ Retry       │            │
│  │ Workers     │  │ Manager     │            │
│  └─────────────┘  └─────────────┘            │
│  ┌─────────────┐  ┌─────────────┐            │
│  │ File        │  │ Connection  │            │
│  │ Processor   │  │ Pool Mgr    │            │
│  └─────────────┘  └─────────────┘            │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│              PostgreSQL / File Storage        │
└──────────────────────────────────────────────┘
```

### gRPC Service Definition (Proposed)

```protobuf
service Executor {
  // Start an extraction job
  rpc Extract(ExtractRequest) returns (stream ExtractRecord);

  // Bulk load records into target tables
  rpc BulkLoad(stream LoadRecord) returns (LoadResult);

  // Execute a parallel pipeline across multiple sources
  rpc ExecutePipeline(PipelineRequest) returns (stream PipelineProgress);

  // Health check
  rpc Health(HealthRequest) returns (HealthResponse);
}
```

### Communication Patterns

```
Python → Go (via gRPC):
  gateway → go-executor: Extract(sources=["CoreBanking","CRM","Loans"])
  go-executor → gateway: stream ExtractRecord

Python → Go (via Redis Queue):
  gateway publishes job → Redis "etl:jobs" queue
  go-executor worker picks up job → processes → publishes result → Redis "etl:results"
  gateway polls result → returns to frontend
```

---

## 8. 3-Layer AI Services

### Layer 1 — Customer State Service

**Purpose:** Track customer behavioural state using Markov Chains.

```
Input:  Transaction/behaviour data from Feature Store
Output: State labels: Active | At Risk | Dormant | Churned
        Transition probabilities
```

### Layer 2 — Prediction Service

**Purpose:** Churn probability, CLV, and composite health score.

```
Input:  Customer state (from Layer 1) + Features (from Feature Store)
Models: XGBoost or LightGBM (configurable)
Output: churn_probability, clv_prediction, health_score (0-100)

Health Score = (churn_weight × (1 - churn_prob))
             + (clv_weight × clv_percentile)
             + (behaviour_weight × state_score)
```

### Layer 3 — Decision Intelligence Service

**Purpose:** Generate ranked Next Best Action recommendations.

```
Input:  Health score, churn probability, CLV (from Layer 2)
Rules:  Configurable business rules engine
Output: Ranked NBA list with priority, impact, effort, confidence
```

---

## 9. Database Architecture

### Two PostgreSQL Instances

| Database | URL | Purpose |
|---|---|---|
| `customer_lifecycle` | `postgresql://clp_user:***@localhost:5432/customer_lifecycle` | Source: raw data, IAM, features |
| `etl_clean` | `postgresql://postgres:@localhost:5432/etl_clean` | Target: cleansed ETL output |

### Connection Strategy

```
Source DB (customer_lifecycle):
  - IAM schema (users, roles, API keys, audit)
  - Raw data tables
  - Feature store

Target DB (etl_clean):
  - Cleansed customer data
  - ETL audit trail
  - Validation results
```

### Key Schemas

| Schema | Database | Tables |
|---|---|---|
| `iam` | source | users, roles, user_roles, api_keys, refresh_tokens, auth_audit |
| `etl` | target | etl_audit, etl_ingestion_batch, etl_validation_run, etl_validation_error, etl_pipeline_run, etl_pipeline_metrics, etl_connector_registry, etl_batch_execution_log, etl_landing_file, etl_checkpoint |
| `etl_clean` | target | customers_clean, accounts_clean, transactions_clean |
| `features` | source | (future) customer features |
| `predictions` | source | (future) churn predictions, CLV |

---

## 10. Communication Patterns

### Current (Monolith)

All services run in-process. The gateway imports `etl.*` and `shared.*` directly.

### Future (Microservices)

```
Frontend ←→ Gateway (REST/JSON)
Gateway  ←→ Go Executor (gRPC)
Gateway  ←→ AI Services (REST or gRPC)
Services ←→ Redis (Pub/Sub for async jobs)
Services ←→ PostgreSQL (Direct for queries)
```

Redis is used for:
- JWT token blacklist
- Rate limiting (sliding window)
- Job queues (Go executor)
- Cache (feature store, frequent queries)

---

## 11. Deployment

### Development

```bash
# Gateway
cd customer-lifecycle-ai
uvicorn gateway.main:app --host 0.0.0.0 --port 8080 --reload

# Frontend
cd absa-foundry-frontend
npm run dev

# Redis (WSL)
sudo service redis-server start

# PostgreSQL (Docker)
docker-compose up -d postgres
```

### Production (Docker Compose)

```yaml
services:
  gateway:        # FastAPI on :8080
  frontend:       # Nginx serving Vue dist on :80
  postgres:       # PostgreSQL 16
  redis:          # Redis 7
  go-executor:    # Go binary (planned)
  nginx:          # Reverse proxy
```

---

## 12. Task Handoff Guide

### For a Developer New to the Gateway

**Read these in order:**

| # | Document | Location |
|---|---|---|
| 1 | Architecture (this doc) | `docs/architecture/system-design.md` |
| 2 | Gateway deep-dive | `docs/architecture/gateway-reference.md` |
| 3 | Coding standards | `.ai/coding-standards.md` |
| 4 | Current sprint | `.ai/current-sprint.md` |
| 5 | Project context | `.ai/project-context.md` |

**Key files to understand first:**

| File | Why |
|---|---|
| `gateway/main.py` | App factory, middleware chain, route mounting |
| `gateway/dependencies.py` | All `Depends()` callables |
| `shared/auth/permissions.py` | RBAC matrix |
| `shared/auth/models.py` | Pydantic models |
| `gateway/routes/auth_routes.py` | Example of a full route implementation |

**How to add a new route:**

1. Define Pydantic schemas in `gateway/schemas/`
2. Create service in `gateway/services/`
3. Create repository in `etl/repositories/`
4. Add route handler in `gateway/routes/` (thin, one-line delegation)
5. Add permission rule in `shared/auth/permissions.py`
6. Register router in `gateway/main.py`

**How to add a new role:**

1. Add to `database/iam/001_initial_schema.sql`
2. Add route rules in `shared/auth/permissions.py`
3. Update this document

### For a Developer Building the Go Executor

**Start with:**

| Component | Priority | Input → Output |
|---|---|---|
| Extraction Engine | 1 | `ExtractRequest{sources[]}` → `stream ExtractRecord` |
| Bulk Loader | 2 | `stream LoadRecord` → `LoadResult{rows_loaded, errors}` |
| Connection Pool Manager | 3 | Internal — manages `*sql.DB` pools per data source |
| Retry Manager | 4 | Internal — exponential backoff with configurable max retries |
| gRPC Server | 1 | Wraps all components, exposed on `:50051` |

**gRPC contract** (first pass):

```protobuf
service Executor {
  rpc Extract(ExtractRequest) returns (stream Record);
  rpc BulkLoad(stream Record) returns (LoadResult);
  rpc Health(google.protobuf.Empty) returns (HealthResponse);
}

message ExtractRequest {
  repeated string sources = 1;    // ["core_banking", "crm", "loans"]
  string query = 2;               // SQL or YAML pipeline spec
  int32 batch_size = 3;           // rows per chunk (default 10000)
}

message Record {
  string source = 1;
  bytes payload = 2;              // JSON-encoded row
  int64 sequence = 3;             // monotonic sequence number
}

message LoadResult {
  int64 rows_loaded = 1;
  int64 rows_failed = 2;
  repeated string errors = 3;
  double duration_seconds = 4;
}
```

### Immediate Priorities (Next Sprint)

| # | Task | Area | Effort |
|---|---|---|---|
| 1 | Complete user CRUD (POST/PUT/DELETE /admin/users) | Gateway | Small |
| 2 | Add `remove_role()` to UserRepository | Auth | Small |
| 3 | Create `/api/etl/runs/batch/{id}` detail endpoint | ETL | Medium |
| 4 | Build RM Dashboard routes | Gateway | Large |
| 5 | Go Extraction Engine (MVP) | Go Executor | Large |
| 6 | Wire rate limiter to Redis | Gateway | Small |
| 7 | Write gateway integration tests | Tests | Medium |
