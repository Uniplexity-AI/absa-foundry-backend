# Architecture Documentation

**Customer Lifecycle Prediction System**
**Date:** 2026-07-16
**Status:** Phase 2 Complete — ETL Engine Implemented

---

## 1. System Overview

The Customer Lifecycle Prediction System is an enterprise AI platform for banking customer lifecycle prediction, churn analysis, CLV estimation, and Next Best Action recommendations. It follows Domain-Driven Design, Clean Architecture, and Event-Driven Architecture principles.

### Component Architecture

| Layer | Component | Technology |
|-------|-----------|------------|
| Gateway | API Gateway | FastAPI, Nginx |
| ETL | ETL Engine | Python, SQLAlchemy, Pydantic v2 |
| AI | Behaviour, Prediction, Decision | XGBoost, LightGBM, Markov Chains |
| Infrastructure | Database, Cache, Proxy | PostgreSQL 16, Redis 7, Nginx |
| Operations | Monitoring, Logging, Audit | Structured JSON, Immutable Audit Trail |

---

## 2. ETL Engine

The ETL Engine provides end-to-end data pipeline capabilities: Extract → Ingest → Validate → Transform → Stage → Load → ML Triggers.

See [ETL Architecture Documentation](etl/README.md) for complete design details.

**Key Capabilities:**
- 12 data source connectors (PostgreSQL, SQL Server, Oracle, MySQL, CSV, Excel, JSON, XML, REST, SOAP, Core Banking, Kafka-future)
- 5-stage validation engine (Schema, Mandatory Fields, Business Rules, Duplicate Detection, Referential Integrity)
- 3-stage transformation pipeline (Field Mapping, Value Standardization, Data Enrichment)
- 4 staging tables (stg_customer, stg_account, stg_transaction, stg_branch)
- Production loader with UPSERT and topological dependency ordering
- DAG-based orchestration with 11-step default pipeline
- Resumable checkpoint engine
- 7-stream structured JSON logging
- Immutable audit trail (7-year retention)

---

## 3. AI Services

### Layer 1 — Behaviour Intelligence
Markov Chain based customer state engine.

### Layer 2 — Prediction Intelligence
XGBoost/LightGBM prediction engine with champion/challenger evaluation.

### Layer 3 — Decision Intelligence
Next Best Action recommendation system for Relationship Managers.

---

## 4. Database Tiered Architecture

Per [Database Design Specification v2.0](../database/database-design-specification-v2.md):

`raw → staging → clean → feature_store → behaviour → prediction → decision → warehouse → etl`

---

## 5. Design Principles

- **DDD:** Bounded contexts per module
- **Clean Architecture:** Dependencies point inward
- **Repository Pattern:** All data access through repositories
- **Dependency Injection:** Constructor-based
- **Immutable Raw Data:** Landing zone write-once
- **Configurable Everything:** Zero hardcoded values
- **SOLID:** Single responsibility, open for extension