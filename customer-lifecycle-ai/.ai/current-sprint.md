# Current Sprint — PoC (90-Day)

**Sprint Status:** PoC — Month 1: Data Foundation (Near Complete)
**Branch:** `poc-90day` (active) | Reference: `architecture-target-full` (frozen)
**Target:** Stakeholder demo-ready with ETL + Dynamic Extractor + Auth + Gateway

---

## Active Phase: Demo Preparation

ETL engine, Dynamic Extractor, and Auth system are production-hardened. Focus: stakeholder demo, then Feature Store + service layer.

## Branch Strategy

| Branch | Purpose |
|---|---|
| `poc-90day` | **Active** — lean subset for 90-day PoC delivery |
| `architecture-target-full` | **Frozen reference** — full 8-service design for post-PoC rollout |
| `mukoma` | Original development branch |

See [ARCHITECTURE.md](../ARCHITECTURE.md) for recovery commands.

## What's Done

### ETL Engine
- [x] ETL pipeline end-to-end (Extract → Validate → Transform → Load → Audit)
- [x] Config-driven `target` section — same engine runs customers, transactions, or interactions
- [x] Schema drift detection (strict mode), invariant checks, idempotency guard
- [x] Bulk inserts: 16,000+ rows/s, 100% quality on 15,200-row customer dataset
- [x] `customers_clean` in etl_clean database (15,200 rows from raw_customers)
- [x] Source DB has 4 tables: raw_customers, raw_transactions, raw_interactions, customer_transactions

### Dynamic Extractor (9 files, fully implemented)
- [x] `etl/extraction/` — config_models, query_builder, join_validator, schema_factory, business_rules, streaming, executor, version_guard
- [x] 22 filter operators, multi-column JOINs, aggregations (SUM/COUNT/AVG/MIN/MAX), calculated fields
- [x] Wired into `run_etl.py` via `--extraction-spec` flag as Phase 0
- [x] `customer_360.yaml` — Single-table: 15,200 rows, 100% quality, 2s runtime
- [x] `customer_360_multi.yaml` — 3-table JOIN (customers + transactions + interactions) with 5 aggregations + 2 calculated fields

### Authentication (Phases 1-3 Complete — 17 files)
- [x] LDAP/AD authenticator, JWT service (create/verify/refresh/blacklist)
- [x] RBAC matrix: 30 rules across 6 roles (Admin, RM, Branch Manager, Data Scientist, Operations, Service Account)
- [x] API key service: `clp_sk_*` format, SHA-256 hashing, scoped access
- [x] Rate limiting: Redis sliding window, 3 default rules
- [x] Account lockout: 5 failed attempts → 15-minute lock, exponential backoff
- [x] Password policy: 8+ chars, uppercase, digit
- [x] Audit trail: PostgreSQL `iam.auth_audit` — every login/logout/refresh persisted
- [x] Gateway: 14 routes, logging middleware, CORS, health check
- [x] IAM schema: 7 tables, 6 seeded roles
- [x] `seed_iam.py`: admin user (admin/Admin123!) with ADMIN role + 4 service account API keys

### Documentation
- [x] `docs/architecture/etl/dynamic-extractor-spec.md` — 18 sections
- [x] `docs/architecture/security/authentication-flow.md` — 15 sections
- [x] `AUTH-INTEGRATION.md` — Frontend guide (Pinia store, Axios interceptor, router guard, login view)
- [x] Demo runbook: 5-act stakeholder walkthrough

### Frontend
- [x] `api.js` updated: JWT login, refresh interceptor, auto-redirect on 401
- [x] Tailscale-connected: gateway accessible to remote frontend dev

## Known Issues
- [ ] Multi-table extraction: Pydantic Decimal → float coercion (data flows, validation rejects)
- [ ] Refresh token `expires_at` uses PostgreSQL function, not Python datetime (non-blocking)
- [ ] Feature Engineering Service not yet implemented
- [ ] 3-Layer AI services not yet implemented

## What's Next
1. Fix multi-table extraction Decimal coercion
2. Feature Engineering Service
3. Customer State Service (Markov engine)
4. Prediction Service (XGBoost churn/CLV)

## What's Deferred (available on `architecture-target-full`)
- Hidden Markov Model, Reinforcement Learning
- Kafka/Debezium/REST/SOAP connectors
- Orchestration service
- Champion/challenger model evaluation
