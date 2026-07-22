# System Requirements Document — v2.0

## Customer Lifecycle Prediction System · 90-Day PoC · July 20, 2026

| Item | Description |
| --- | --- |
| Version | 2.0 — Detailed PoC requirements (supersedes v0.1) |
| Prepared by | Uniplexity AI |
| Client | Absa Bank Zambia |
| PoC Duration | 90 days (Month 1 complete, Month 2 in progress) |
| Hosting | Bank infrastructure — Ubuntu VMs, PostgreSQL 18, Docker Compose |
| Current Branch | poc-90day (reference architecture: architecture-target-full) |
| Purpose | Customer Lifecycle Prediction: churn prediction, CLV estimation, customer state classification, NBA recommendations |

---

## Contents

1. Executive Summary
2. Business & Technical Context
3. Solution Architecture — 3-Layer AI System
4. Component Specifications
    - 4.1 ETL Engine (Production-Hardened)
    - 4.2 Feature Engineering Service
    - 4.3 Customer State Service — Layer 1
    - 4.4 Prediction Service — Layer 2
    - 4.5 Decision Intelligence Service — Layer 3
    - 4.6 Frontend Dashboard (Vue 3)
    - 4.7 API Gateway
5. Data Requirements
6. Frontend Functional Requirements
7. Integration Requirements
8. Security, Compliance & Audit
9. Non-Functional Requirements
10. Sizing & Performance Assumptions
11. Deployment & Environments
12. Testing Strategy
13. Pilot Acceptance Criteria
14. Open Questions
15. Appendices

---

## 1. Executive Summary

This v2.0 System Requirements Document defines the detailed technical requirements for the 90-day Customer Lifecycle Prediction PoC at Absa Bank Zambia. The platform is a **3-layer AI system** that ingests banking transaction data, computes point-in-time customer features, classifies customers into behavioural states, predicts churn probability and customer lifetime value, and generates Next Best Action (NBA) recommendations for Relationship Managers.

**Month 1 (Data Foundation) is complete.** The ETL pipeline is production-hardened with 10 verified validation rules and a compliance-grade immutable audit trail. The Feature Engineering Service delivers 16 point-in-time customer features via FastAPI. The Vue 3 frontend requirements are fully specified.

**Month 2 (AI Services) is in progress.** The Customer State Service (Markov classification), Prediction Service (XGBoost churn/CLV), and Decision Intelligence Service (NBA rule engine) are next in the build queue.

The solution operates entirely within bank infrastructure — no cloud dependencies, no internet access required.

---

## 2. Business & Technical Context

| Area | Detail |
| --- | --- |
| Core Problem | Relationship Managers lack data-driven tools to identify at-risk customers, prioritise outreach, and make informed retention decisions. |
| PoC Scope | Customer Lifecycle Prediction: state classification (Active/At Risk/Dormant), churn probability, CLV estimation, NBA recommendations. |
| Users | Relationship Managers (primary), Branch Managers, Data Scientists, Operations. |
| Data Source | Customer transaction records from core banking system (CSV batch for PoC; PostgreSQL connectors available for production). |
| Deployment | Bank-owned Ubuntu VMs. Docker Compose for service orchestration. No Kubernetes. No cloud services. |
| Key Constraint | Air-gapped network — all npm/pip dependencies vendored. No public internet access from production. |
| Compliance | Bank of Zambia data residency. Every ML prediction must have SHAP explainability. Customer ID/Account ID plaintext storage flagged for at-rest encryption review. |

---

## 3. Solution Architecture — 3-Layer AI System

```
Absa Core Banking
       │
       ▼
  ETL Engine (CSV ingest, 10 validation rules, immutable audit)
       │
       ▼
  customer_transactions_clean (etl_clean PostgreSQL)
       │
       ▼
  Feature Engineering Service (16 point-in-time features per customer)
       │
       ▼
  customer_features (etl_clean PostgreSQL)
       │
  ┌────┴─────────────────┐
  ▼                      ▼
Layer 1                  Layer 2
Customer State Service   Prediction Service
(Markov Chain)           (XGBoost/LightGBM)
State: Active/At Risk/   Churn prob + CLV +
  Dormant/Churned        Health Score
  │                      │
  └────────┬─────────────┘
           ▼
       Layer 3
  Decision Intelligence Service
  (Rule Engine + NBA Generator)
           │
           ▼
  Vue 3 Dashboard (Relationship Managers)
```

### Service Topology

| Service | Port | Framework | Status |
| --- | --- | --- | --- |
| API Gateway | 8080 | FastAPI | Scaffolded |
| ETL Engine | CLI | Python + psycopg2 | ✅ Production-hardened |
| Feature Engineering | 8002 | FastAPI | ✅ Implemented + tested |
| Customer State (L1) | 8003 | FastAPI | 📋 Next build |
| Prediction (L2) | 8004 | FastAPI | 📋 Scaffolded |
| Decision Intelligence (L3) | 8005 | FastAPI | 📋 Scaffolded |
| Model Management | 8006 | FastAPI | 📋 Scaffolded |
| Dashboard | 8007 | FastAPI | 📋 Scaffolded |

---

## 4. Component Specifications

### 4.1 ETL Engine — Production-Hardened

The data pipeline ingests CSV transaction data, validates against 10 configurable rules, transforms, and loads into `etl_clean.customer_transactions_clean` with a compliance-grade immutable audit trail.

#### Validation Rules (10/10 verified against ground truth)

| Rule ID | Category | Description | Ground Truth |
| --- | --- | --- | --- |
| DUP-001 | Duplicate | Exact duplicate detection (8-field composite key) | 350/350 |
| BUSINESS-CUR-001 | Currency | Reject unsupported currency codes | 50/50 |
| BUSINESS-CHN-001 | Channel | Reject invalid transaction channels | 50/50 |
| BUSINESS-DATE-001 | Date Format | Reject malformed dates | 50/50 |
| BUSINESS-DATE-002 | Future Date | Reject dates beyond max_future_date_days (365) | 50/50 |
| BUSINESS-AMT-001 | Amount | Reject amounts <= 0 | 50/50 |
| MANDATORY-CUSTOMER_ID | Mandatory | Reject null/empty customer_id | 50/50 |
| MANDATORY-ACCOUNT_ID | Mandatory | Reject null/empty account_id | 50/50 |
| MANDATORY-BRANCH_CODE | Mandatory | Reject null/empty branch_code | 50/50 |
| MANDATORY-AMOUNT | Mandatory | Reject null/empty amount | 50/50 |

#### Production Features

| Feature | Detail |
| --- | --- |
| Bulk Insert | psycopg2.extras.execute_values, 5K-row chunks, ~17,000 rows/s |
| Schema Drift Detection | Strict mode — fails loudly on missing/reordered columns (configurable) |
| Idempotency Guard | SHA-256 file hash in audit trail; --force flag to override |
| Structured Logging | INFO/WARNING/ERROR with timestamps, UTF-8 output |
| Invariant Checks | Conservation, no silent skips, reason coverage, quality floor |
| Per-Row Rejections | Every row in customer_transactions_rejected carries specific rule ID(s) |
| Constraint Rescue | Rows failing DB constraints rescued to rejected table (never silently dropped) |

#### Audit Trail

`etl.etl_audit` — 24-column immutable compliance table: audit_id, batch_id, source_type, source_name, pipeline_name, started_at, completed_at, duration_seconds, rows_received, rows_valid, rows_rejected, rows_loaded, rows_skipped, duplicates_detected, warnings_count, errors_count, quality_score, status, error_message, triggered_by, operator_id, tags (JSONB), extra (JSONB), created_at. Append-only, 7-year retention.

### 4.2 Feature Engineering Service

Point-in-time customer features computed from `customer_transactions_clean` using a single SQL aggregation pass per `as_of_date`.

#### Schema: customer_features

16 feature columns + id, customer_id, as_of_date, computed_at. Unique constraint on (customer_id, as_of_date). INSERT ... ON CONFLICT DO UPDATE for idempotent upsert.

#### Features (16 metrics per customer per date)

| Category | Features |
| --- | --- |
| Recency | days_since_last_txn, days_since_first_txn |
| Frequency | txn_count_30d, txn_count_90d, txn_count_180d |
| Monetary | total_amount_90d, avg_amount_90d, total_amount_180d, amount_growth_ratio |
| Diversity | distinct_channels_90d, distinct_txn_types_90d, dominant_channel |
| Volatility | amount_stddev_90d |
| Metadata | avg_days_between_txn |

#### Critical Guarantee: Point-in-Time Correctness

All features computed using only transactions where `transaction_date <= as_of_date`. No future data leakage. Uses `FILTER (WHERE ...)` clauses for windowed aggregation (30d/90d/180d) in a single SQL pass.

#### API Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | /features/compute-batch?as_of_date=YYYY-MM-DD | Compute for all customers |
| GET | /features/{customer_id}?as_of_date=YYYY-MM-DD | Fetch snapshot (404 if missing) |
| GET | /features/{customer_id}/latest | Latest snapshot for live scoring |

#### Test Coverage: 10/10 passing (~9s)

### 4.3 Customer State Service — Layer 1 (Next Build)

Classifies each customer into a discrete behavioural state using Markov Chain transition matrices from feature snapshots over time.

| Component | Detail |
| --- | --- |
| Engine | Markov Chain (transition matrix computation, stationary distribution) |
| States | Active, At Risk, Dormant, Churned |
| Input | customer_features snapshots (multiple as_of_date values per customer) |
| Output | Customer state label + transition probability per customer per as_of_date |
| HMM | Hidden Markov Model — deferred to post-PoC (preserved on architecture-target-full) |

### 4.4 Prediction Service — Layer 2 (Next Build)

Unified prediction engine for churn probability and CLV estimation.

| Model | Framework | Output |
| --- | --- | --- |
| Churn Model | XGBoost | Churn probability (0-1) |
| CLV Model | XGBoost | Estimated lifetime value (ZMW) |
| Health Score | Weighted fusion | Composite score (0-100) |

Health Score = churn_weight × (1 - churn_prob) + clv_weight × clv_percentile + behaviour_weight × state_score. Weights configurable via environment variables (default: 0.40 / 0.30 / 0.30).

### 4.5 Decision Intelligence Service — Layer 3 (Next Build)

Generates ranked NBA recommendations from customer state, churn probability, CLV, and feature values.

| Component | Detail |
| --- | --- |
| Rule Engine | Configurable business rules evaluating customer profile |
| NBA Generator | Ranked recommendations with impact/effort/confidence scoring |
| Action Logger | RM actions recorded with customer ID, action type, timestamp, NBA recommendation ID reference |
| RL Engine | Reinforcement learning — deferred to post-PoC (preserved on architecture-target-full) |

### 4.6 Frontend — Vue 3 Dashboard

#### Technology Stack

| Component | Choice |
| --- | --- |
| Framework | Vue 3 (Composition API) + TypeScript |
| Build Tool | Vite |
| State Management | Pinia |
| Router | Vue Router 4 |
| Charts | Chart.js via vue-chartjs (vendored, air-gapped) |
| Deployment | Nginx on Ubuntu, no CDN |

#### Screens (PoC Scope)

| Screen | Users | Key Features |
| --- | --- | --- |
| RM Dashboard | Relationship Managers | 4 KPI cards, priority alerts, searchable customer table, period selector |
| Customer Detail (360°) | Relationship Managers | Profile card, Health Score gauge, state timeline, feature importance chart, NBA recommendations with action logging |
| ETL Run History | Operations | Pipeline run table from etl.etl_audit, data quality time-series, system health |

Full frontend specifications in [FRONTEND-REQUIREMENTS.md](../FRONTEND-REQUIREMENTS.md) (50+ functional requirement IDs across 9 screens).

### 4.7 API Gateway

FastAPI gateway (port 8080) routing to all backend services. LDAP authentication, role-based access control, request logging.

---

## 5. Data Requirements

### Source Data

| Table | Database | Rows | Columns |
| --- | --- | --- | --- |
| customer_transactions | etl_validation | 70,472 | 10 (customer_id, account_id, branch_code, transaction_date, transaction_type, channel, currency, amount, data_issue) |

### Target Data (etl_clean)

| Table | Purpose | Current Volume |
| --- | --- | --- |
| customer_transactions_clean | Validated, transformed transactions | 69,672 rows |
| customer_transactions_rejected | Rows failing validation with per-row reasons | 800 rows |
| etl.etl_audit | Immutable compliance audit trail | 1 per batch |
| customer_features | Point-in-time feature snapshots | 5,000 per as_of_date |

### Data Refresh Cadence

- ETL pipeline: on-demand batch (CSV file drop) — 70K rows in ~50 seconds
- Feature computation: on-demand via API — 5,000 customers in ~35 seconds
- Daily batch schedule to be configured in Month 2

---

## 6. Frontend Functional Requirements (Summary)

### User Roles

| Role | Permissions |
| --- | --- |
| Relationship Manager | Own portfolio, customer drill-down, NBA view, action logging |
| Branch Manager | All branch customers, portfolio analytics, churn heatmap, team performance |
| Data Scientist | Model metrics, champion/challenger comparison, SHAP explanations, feature drift |
| Operations | ETL run history, data quality scores, audit logs, system health |

### API Contract (Frontend ↔ Backend)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| /api/customers/{rm_id} | GET | List RM customers with latest features |
| /api/customers/{customer_id} | GET | Full customer detail (features + state + predictions) |
| /api/customers/{customer_id}/nba | GET | NBA recommendations |
| /api/customers/{customer_id}/actions | GET/POST | Action history / log new action |
| /api/etl/runs | GET | Pipeline run history |
| /api/auth/login | POST | LDAP authentication |
| /api/alerts/{user_id} | GET/PATCH | Priority alerts |

Full details in [FRONTEND-REQUIREMENTS.md](../FRONTEND-REQUIREMENTS.md).

---

## 7. Integration Requirements

| ID | Requirement | PoC Approach |
| --- | --- | --- |
| INT-001 | Data ingestion method | CSV file drop (PostgreSQL/SQL Server/Oracle/MySQL connectors on architecture-target-full) |
| INT-002 | Source system access | Direct database connection (etl_validation PostgreSQL) |
| INT-003 | Data refresh cadence | On-demand batch; daily schedule TBD for Month 2 |
| INT-004 | Error handling | Per-row savepoints, constraint rescue to rejected table, structured logging with stack traces |
| INT-005 | Data lineage | Full traceability: source CSV → batch_id → etl_audit → customer_transactions_clean → customer_features → predictions |

---

## 8. Security, Compliance & Audit

| ID | Requirement | PoC Status |
| --- | --- | --- |
| SEC-001 | Authentication | LDAP/SSO (specified for frontend + gateway) |
| SEC-002 | RBAC | 4 roles: RM, Branch Manager, Data Scientist, Operations |
| SEC-004 | Encryption in transit | HTTPS on internal bank network |
| SEC-005 | Encryption at rest | Flagged — customer_id/account_id plaintext needs BoZ review |
| SEC-006 | Audit logging | etl.etl_audit (24 columns, immutable, append-only) + frontend action audit log |
| SEC-007 | Sensitive data handling | Masked/synthetic test data only in non-production |
| SEC-008 | Retention | 7-year audit retention (configurable per etl_config.yaml) |
| SEC-009 | AI governance | All ML predictions logged with SHAP explanations; NBA recommendations advisory only |

---

## 9. Non-Functional Requirements

| ID | Area | Target |
| --- | --- | --- |
| NFR-001 | Availability | Align with Absa pilot application standards |
| NFR-002 | Performance | ETL: 70K rows in <60s. Features: 5K customers in <40s. Dashboard page load: <5s. |
| NFR-003 | Scalability | Bulk insert at 17K rows/s; design supports millions via batch chunking |
| NFR-004 | Maintainability | All rules config-driven (YAML + env vars). Single SQL query for all features. |
| NFR-005 | Usability | RM dashboard: core tasks with minimal training |
| NFR-006 | Observability | Structured logging at INFO/WARNING/ERROR. Audit trail per batch. |
| NFR-007 | Auditability | Every row traceable via batch_id FK. Immutable audit records. |
| NFR-008 | Portability | Docker Compose on Ubuntu VMs — adaptable to bank-approved hosting |

---

## 10. Sizing & Performance

| Area | Current (Verified) | Scaling Target |
| --- | --- | --- |
| Transaction rows per batch | 70,472 | 1M+ |
| Distinct customers | 5,000 | 100K+ |
| ETL throughput | 17,000 rows/s | Maintained with connection pooling |
| Feature computation | 5,000 customers / 35s | Linear with customer count |
| API response (single customer) | <1s | <3s at scale |
| Dashboard page load | Target <5s | <5s with cached features |
| Concurrent users | 1-10 | 50+ post-PoC |
| Database size | ~50MB (test data) | Partitioning strategy ready |

---

## 11. Deployment & Environments

| Environment | Detail |
| --- | --- |
| Development | Local Windows (current). Bank VM to be provisioned. |
| UAT | Bank-hosted UAT with masked/synthetic data |
| Production | Bank-hosted Production following Absa change/release process |
| DR | Bank-hosted DR aligned to Absa standards. RTO/RPO TBD. |

### Infrastructure Stack

| Component | Technology |
| --- | --- |
| Runtime | Python 3.10+ (target 3.12 for production) |
| Database | PostgreSQL 18 (etl_validation + etl_clean databases) |
| Cache | Redis 7 (optional, configured in docker-compose) |
| Orchestration | Docker Compose |
| Reverse Proxy | Nginx |
| Version Control | Git (GitHub: Uniplexity-AI/absa-foundry-backend) |

---

## 12. Testing Strategy

| Suite | Location | Tests | Runtime | Purpose |
| --- | --- | --- | --- | --- |
| ETL Fixture Regression | tests/test_validation_ground_truth.py | 6 assertions | ~25s | Canary for validation rule regressions |
| Feature Engineering | services/feature-engineering-service/tests/ | 10 tests | ~9s | Point-in-time correctness, idempotency, edge cases |
| Ground Truth Comparison | verify.py | 16 checks | ~1s | Source vs target DB count comparison |

Test data: `tests/fixtures/etl_validation_customers.csv` (70,472 rows) — immutable fixture, never changes. Feature tests use hand-crafted 9-transaction fixture with exact expected values.

---

## 13. Pilot Acceptance Criteria

| ID | Criterion | Status |
| --- | --- | --- |
| AC-001 | ETL pipeline ingests, validates, and loads transaction data | ✅ Done |
| AC-002 | All 10 validation rule categories verified against ground truth (800/800) | ✅ Done |
| AC-003 | Compliance-grade immutable audit trail (etl.etl_audit) operational | ✅ Done |
| AC-004 | Feature Engineering Service computes 16 point-in-time features per customer | ✅ Done |
| AC-005 | Customer State Service classifies customers (Active/At Risk/Dormant) | 📋 Month 2 |
| AC-006 | Prediction Service produces churn probability + CLV + Health Score | 📋 Month 2 |
| AC-007 | Decision Intelligence Service generates ranked NBA recommendations | 📋 Month 2 |
| AC-008 | Vue 3 RM dashboard with customer detail and NBA action logging | 📋 Month 2 |
| AC-009 | RBAC, LDAP auth, and audit logging validated end-to-end | 📋 Month 2 |
| AC-010 | Deployment follows Absa change/release process | ⏳ Pending bank env |

---

## 14. Open Questions

| ID | Question | Status |
| --- | --- | --- |
| Q-001 | Development environment — bank VM or Uniplexity environment? | Open |
| Q-002 | Docker Compose acceptable for PoC orchestration? | Proposed |
| Q-003 | PostgreSQL 18 approved for pilot application data? | In use |
| Q-004 | LDAP/SSO integration details and endpoints | Open |
| Q-005 | Production transaction data format, volume, and refresh cadence | Open |
| Q-006 | Data classification for customer_id/account_id — at-rest encryption required? | Flagged |
| Q-007 | Security review artefacts required before UAT deployment | Open |
| Q-008 | RTO/RPO targets for pilot DR | Open |
| Q-009 | Bank monitoring/logging tools for integration | Open |

---

## 15. Appendices

### Appendix A — Glossary

| Term | Definition |
| --- | --- |
| CLV | Customer Lifetime Value — predicted total future revenue from a customer |
| NBA | Next Best Action — ranked recommendation for the Relationship Manager |
| Health Score | Composite 0-100 score: weighted fusion of churn probability, CLV percentile, and behavioural state score |
| Markov Chain | Probabilistic state transition model used for customer behaviour classification |
| Point-in-Time | Feature computation using only data available as of a specific date — prevents future data leakage in ML training |
| Champion Model | Currently deployed production ML model |
| Challenger Model | Candidate model being evaluated against the champion |
| SHAP | SHapley Additive exPlanations — ML model explainability framework |
| BoZ | Bank of Zambia |
| PoC | Proof of Concept |

### Appendix B — Version History

| Version | Description | Status | Author | Date |
| --- | --- | --- | --- | --- |
| 0.1 | Initial SRD for Absa environment and tooling review | Draft | Uniplexity AI | 02 Jul 2026 |
| 2.0 | Detailed PoC requirements — 3-layer AI architecture, ETL engine, feature engineering, Vue 3 frontend | Final | Uniplexity AI | 20 Jul 2026 |

### Appendix C — Key Project Files

| File | Purpose |
| --- | --- |
| run_etl.py | ETL engine CLI entry point |
| verify.py | Ground-truth comparison tool |
| etl/ | ETL engine (15 modules, production-hardened) |
| services/feature-engineering-service/ | Feature computation + FastAPI |
| tests/test_validation_ground_truth.py | ETL canary regression (6 tests) |
| services/feature-engineering-service/tests/ | Feature regression (10 tests) |
| FRONTEND-REQUIREMENTS.md | Vue 3 frontend specifications (50+ FR-IDs) |
| PROGRESS.md | Implementation progress report |
| ARCHITECTURE.md | Branch strategy + recovery commands |
| .ai/ | AI development guide, sprint status, coding standards |
