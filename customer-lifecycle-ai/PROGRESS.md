# Absa Bank Zambia — PoC Progress Report

**Customer Lifecycle Prediction System** · July 29, 2026


## Executive Summary

The 90-day PoC has completed **Month 1 (Data Foundation)** and **Month 2 (AI Services — Layer 1)**. The ETL pipeline, Feature Engineering Service, and Customer State Service are all production-hardened with verified real-data validation. The project has pivoted from scaffolded stubs to running APIs on real customer data.

**Current milestone**: Layer 1 (Customer State Service) is live on port 8003 with real data verification. Layers 2 (Prediction) and 3 (Decision Intelligence) are the next build targets.


## 1. ETL Engine — Production Hardened

| Capability | Status |
|---|---|
| End-to-end pipeline (Extract → Validate → Transform → Load → Audit) | Done |
| Dynamic Extractor — 9 extraction specs, YAML-driven, 22 filter operators | Done |
| 9 clean tables populated from 15 source tables | Done |
| 10 validation rules verified against ground truth | Done — 800/800 dirty rows |
| Immutable audit trail (etl.etl_audit, 24 columns) | Done |
| Batch bulk insert (17,000 rows/second) | Done |
| Schema drift detection (dataset-aware per extraction spec) | Done |
| Idempotency guard (SHA-256 hash) | Done |
| Per-spec target table configuration (`target:` section in YAML) | Done |
| Transform overrides per spec (`transform.type_casts` + `standardization`) | Done |

### Extraction Specs (9 active)

| Spec | Source Tables | → Clean Table | Rows |
|------|-------------|---------------|------|
| `customer_profile_master.yaml` | `customers_core` ⟕ `demographics_hr` | `customers_clean` | 4,998 |
| `transaction_master.yaml` | `customer_transactions` | `customer_transactions_clean` | — |
| `transactions_batch1.yaml` | `transactions_core_batch1` | `customer_transactions_clean` | — |
| `transactions_batch2.yaml` | `transactions_core_batch2` | `customer_transactions_clean` | 90,871 |
| `account_summary.yaml` | `accounts_manual` | `accounts_clean` | 5,367 |
| `loan_summary.yaml` | `loans_los` | `loans_clean` | 279 |
| `card_summary.yaml` | `cards_page1` | `cards_clean` | 509 |
| `cards_page2.yaml` | `cards_page2` | `cards_clean` | 549 |
| `digital_engagement.yaml` | `digital_engagement` | `digital_engagement_clean` | 2,849 |


## 2. Feature Engineering Service — 56 Features Live

Point-in-time features across 7 domains + 4 product domains, computed from 5 clean tables.

### Feature Coverage

| Domain | Features | Customers | Source Table |
|--------|----------|-----------|-------------|
| **Phase 1** (transaction aggregates) | 16 | 4,998 | `customer_transactions_clean` |
| **Profile** (Domain 1) | 6 | 4,998 | `customers_clean` |
| **Behaviour** (Domain 2) | 10 | 4,998 | `customer_transactions_clean` |
| **Financial** (Domain 3) | 5 | 4,451 | `customer_transactions_clean` |
| **Channel** (Domain 4) | 5 | 2,758 | `customer_transactions_clean` |
| **Temporal** (Domain 7) | 3 | 2,758 | `customer_transactions_clean` |
| **Risk** (Domain 6) | 6 | 2,758 | `customer_transactions_clean` |
| **Relationship — Status** | 1 | 4,998 | `customers_clean` |
| **Relationship — Accounts** | 3 | 3,652 | `accounts_clean` |
| **Relationship — Loans** | 1 | 275 | `loans_clean` |
| **Cards** | 5 | 1,057 | `cards_clean` |
| **Digital Engagement** | 4 | 2,738 | `digital_engagement_clean` |

### Bug Fixes
- **Behaviour Generator**: Fixed `%(name)d` → `%(name)s` in psycopg2 parameter placeholders (was silently failing on ALL dates)
- **ID Mapping**: Created `customer_id_mapping` table (7,832 cross-references) to bridge different customer ID zero-padding formats between source tables and `customer_features`

### Verified Dates (3 PoC snapshots)
| Date | Total | Full 7-Generator Coverage |
|------|-------|--------------------------|
| 2026-07-27 | 4,998 | ✅ All 7 generators |
| 2026-07-22 | 4,998 | ✅ All 7 generators |
| 2026-07-17 | 4,998 | ✅ All 7 generators |


## 3. Customer State Service (Layer 1) — Live on Port 8003

### Capability Summary

| Component | Status | Tests |
|-----------|--------|-------|
| **State Engine** — 4-priority rule-based classifier | ✅ Live | 15/15 boundary + priority tests |
| **Markov Engine** — 4×4 transition matrix + steady-state | ✅ Live | 6/6 (absorbing, cold-start, predict) |
| **State Repository** — psycopg2 sync, batch upsert, 3× DB retry | ✅ Live | — |
| **Journey Repository** — transition tracking | ✅ Live | — |
| **Transition Analyzer** — trigger reason attribution | ✅ Live | — |
| **Journey Analyzer** — milestone detection + path analysis | ✅ Live | — |
| **API** — 7 endpoints (compute, get, timeline, portfolio, markov/matrix, markov/predict, health) | ✅ Live | — |
| **Gateway Proxy** — httpx forwarder with 502/504 handling | ✅ Live | — |
| **Verification Script** — feature→state traceability per customer | ✅ Live | — |

### Classification Rules (15/15 verified)

| Priority | State | Rules |
|----------|-------|-------|
| 1 | CHURNED | Account closed OR inactive > 365d |
| 2 | DORMANT | Inactive > 90d OR zero txns OR engagement < 10 |
| 3 | AT_RISK | Inactive ≥ 30d OR dormant indicator OR engagement < 20 |
| 4 | ACTIVE | Default |

### Live Portfolio (2026-07-27)
| State | Count | % |
|-------|-------|---|
| DORMANT | 2,417 | 48.4% |
| AT_RISK | 2,291 | 45.8% |
| CHURNED | 290 | 5.8% |

### API Endpoints
```
POST   /states/compute?as_of_date=YYYY-MM-DD    # Classify all customers
GET    /states/{customer_id}?as_of_date=         # State snapshot
GET    /states/{customer_id}/timeline             # Full history
GET    /states/portfolio?as_of_date=              # Aggregate counts
GET    /states/markov/matrix?as_of_date=          # Transition probability matrix
GET    /states/markov/predict/{customer_id}       # Next-state prediction
GET    /health                                     # Service health
```

### Markov Matrix (Live — 2026-07-27)
```
          TO→   ACTIVE  AT_RISK  DORMANT  CHURNED
ACTIVE          0.00    1.00     0.00     0.00
AT_RISK         0.00    0.00     0.82     0.18
DORMANT         0.00    0.00     0.00     1.00
CHURNED         0.00    0.00     0.00     1.00   ← absorbing
```


## 4. Infrastructure Status

| Component | State | Port |
|-----------|-------|------|
| PostgreSQL 18 (etl_clean) | Running | 5432 |
| ETL Engine (run_etl.py) | Production-hardened | — |
| Feature Engineering Service | Implemented + tested | 8002 |
| Customer State Service (Layer 1) | **Live + verified** | 8003 |
| Prediction Service (Layer 2) | Next build | 8004 |
| Decision Intelligence Service (Layer 3) | Scaffolded | 8005 |
| API Gateway | Auth + RBAC complete | 8080 |
| Dashboard Service | Scaffolded | — |


## 5. Next Steps (Month 2 — AI Services)

1. **Prediction Service (Layer 2)** — XGBoost churn probability + CLV prediction + Health Score (0-100). Backfills `customer_states.health_score` column.
2. **Decision Intelligence Service (Layer 3)** — Rule engine + NBA recommendations
3. **Frontend (Vue 3)** — RM Dashboard, Customer Detail, State Timeline
4. **Dashboard Service** — Aggregate analytics for branch managers


## 6. Key Files

| File | Purpose |
|------|---------|
| `run_etl.py` | ETL engine CLI entry point |
| `_run_generators.py` | Feature generator runner (accepts `--as-of-date`) |
| `scripts/seed_states.py` | Initial state computation |
| `scripts/verify_feature_to_state.py` | Feature→State traceability |
| `etl/config/extraction_specs/` | 9 YAML extraction specs |
| `services/feature-engineering-service/` | 56 features, 7 domain generators |
| `services/customer-state-service/` | 13 files, 15+6 tests, live API |
| `database/state_engine/001_customer_states.sql` | State DDL |
| `database/feature_store/002_add_product_engagement_features.sql` | Feature column migration |
| `database/state_engine/customer_id_mapping` | ID cross-reference table |
| `docs/architecture/customer-state-service.md` | Full design doc (17 decisions)
