# Current Sprint — PoC (90-Day)

**Sprint Status:** PoC — Month 2: AI Services (Layer 1 Complete, Layer 2 Next)
**Branch:** `poc-90day` (active) | Reference: `architecture-target-full` (frozen)
**Last Updated:** 2026-07-29


## Active Phase: AI Services — Layer 1 Complete

Customer State Service is live on port 8003 with real customer data. 15/15 state engine boundary tests, 6/6 Markov engine tests, 7 API endpoints, full data pipeline verified end-to-end. Next: Prediction Service (Layer 2).

### Completed Today (2026-07-29)

- [x] **Customer State Service** — 13 files implemented from scaffolded stubs
- [x] State Engine: 4-priority rule-based classifier, 15 boundary tests
- [x] Markov Engine: 4×4 transition matrix, steady-state, cold-start handling
- [x] State + Journey Repositories: psycopg2 sync, 3× DB retry
- [x] API: 7 endpoints (compute, get, timeline, portfolio, markov/matrix, markov/predict, health)
- [x] Gateway proxy: httpx forwarder with 502/504 handling
- [x] DDL: `customer_states` + `state_transitions` tables in etl_clean
- [x] Seed script: 4,998 customers × 3 dates = 14,994 states, 1,058 transitions
- [x] Verification: `verify_feature_to_state.py` — per-customer classification trace
- [x] **Behaviour Generator Bug Fix**: `%(name)d` → `%(name)s` in psycopg2 params
- [x] **4 Clean Tables Created**: `accounts_clean`, `loans_clean`, `cards_clean`, `digital_engagement_clean`
- [x] **ID Mapping**: `customer_id_mapping` table — 7,832 cross-references
- [x] **13 New Feature Columns**: All populated across 3 PoC dates
- [x] Design doc: `docs/architecture/customer-state-service.md` — 17 decisions
- [x] PROGRESS.md updated to reflect current state


## What's Done

### Data Layer
- [x] ETL engine end-to-end, 9 extraction specs, 22 filter operators
- [x] 9 clean tables in etl_clean across 15 source tables
- [x] Per-spec target table + transform configuration
- [x] Feature Engineering: 56 features, 7 domain generators, 3 verified dates

### Layer 1 — Customer State Service (NEW)
- [x] State classification: 4-priority rules, 15/15 boundary tests
- [x] Markov Chain: 4×4 matrix, steady-state, cold-start, 6/6 tests
- [x] API live on port 8003: 7 endpoints
- [x] Real data verified: 4,998 customers, portfolio breakdown, customer-level traces

### Infrastructure
- [x] PostgreSQL 18: etl_clean with all tables
- [x] ETL Engine: production-hardened
- [x] Feature Engineering Service: port 8002
- [x] Customer State Service: port 8003 (NEW)
- [x] API Gateway: port 8080 with auth + RBAC


## Next Up

1. **Prediction Service (Layer 2)** — XGBoost churn prob + Health Score → backfills customer_states.health_score
2. **Gateway: register customer_state routes** in main gateway router
3. **Frontend: Vue 3 RM Dashboard** — Customer Detail, State Timeline, Health Score gauge

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
