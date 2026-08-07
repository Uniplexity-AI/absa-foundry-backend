# Current Sprint — ABSA Customer Lifecycle Platform

**Status:** Demo-Ready — Backend + Frontend Wired End-to-End
**Date:** 2026-08-07
**Branch:** `main`

---

## Active Phase: Demo Preparation

All 5 backend services running. Frontend 6 pages wired to real data. 34/34 tests passing. ETL pipeline operational with 15,200 rows at 100% quality.

## Completed Today (2026-08-07)

### Decision Intelligence Service (Layer 3)
- [x] YAML config refactor — no hardcoded rules in ranking_engine.py or business_rules_engine.py
- [x] `config/ranking/ranking_rules.yaml` — all scoring weights and thresholds
- [x] `config/candidates/action_catalog.yaml` — action-to-category mappings
- [x] 34/34 tests passing across all engines
- [x] `pip install pyyaml pandas pyarrow asyncpg lightgbm` — all deps resolved

### Gateway — 15 API Routes
- [x] `/api/v1/customers/portfolio` + `/api/v1/customers` (list all) + `/{id}` + `/timeline`
- [x] `/api/v1/predictions/{id}/churn` + `/health` + `/markov-matrix`
- [x] `/api/v1/models`
- [x] `/api/etl/runs` — fixed asyncpg connection

### State Service — New Endpoint
- [x] `GET /states` — paginated list-all with LIMIT/OFFSET

### ETL Pipeline
- [x] 15,200 rows loaded, 14 audit records, 100% quality
- [x] `pip install pandas pyarrow asyncpg`

## Backend Services (all 5 running)

| Port | Service | Status |
|------|---------|--------|
| `:8080` | API Gateway | 15 routes |
| `:8002` | Feature Engineering | 22 features, 4,998 customers |
| `:8003` | Customer State | 4,998 classified |
| `:8004` | Prediction Service | Churn AUC 0.77 |
| `:8005` | Decision Intelligence | 9 engines, YAML-configured |

## Frontend (6 pages wired)

| Page | Route | Data |
|------|-------|------|
| Dashboard Home | `/dashboard/home` | Live KPIs + 500-row ledger |
| Portfolio | `/dashboard/portfolio` | Live KPIs |
| Customer Detail | `/dashboard/customer/:id` | State, health, churn, timeline, markov |
| Model Performance | `/dashboard/models` | AUC-ROC 76.7%, 2 models |
| ETL Pipeline | `/dashboard/etl-pipeline` | Health cards, quality chart, run table |
| ETL Run History | `/dashboard/etl-run-history` | Paginated audit trail |

## Known Gaps
- [ ] Branch Manager Dashboard not yet wired
- [ ] Customer names are synthetic "Customer 00001"
- [ ] Account number/tenure/RM show `...` placeholder
