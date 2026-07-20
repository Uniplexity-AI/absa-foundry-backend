# Absa Bank Zambia — PoC Progress Report

**Customer Lifecycle Prediction System** · July 17, 2026

---

## Executive Summary

The 90-day PoC is on track. **Month 1 (Data Foundation)** is complete: the ETL pipeline is production-hardened with verified validation, and the Feature Engineering Service is delivering point-in-time customer features. The project is structured with a clean branch strategy preserving the full target architecture for post-PoC rollout.

---

## 1. ETL Engine — Production Hardened

The data pipeline ingests, validates, transforms, and loads banking transaction data into a clean analytical database with a compliance-grade immutable audit trail.

| Capability | Status |
|---|---|
| End-to-end pipeline (Extract to Validate to Transform to Load to Audit) | Done |
| **10 validation rules** verified against ground truth | Done — 800/800 dirty rows correctly categorized |
| Immutable audit trail (etl.etl_audit, 24 columns) | Done |
| Per-row rejection reasons | Done |
| Batch bulk insert (17,000 rows/second) | Done |
| Schema drift detection (strict mode) | Done |
| Idempotency guard (SHA-256 hash) | Done |
| Structured logging (INFO/WARNING/ERROR with timestamps) | Done |
| Data-agnostic invariant checks | Done |
| PII compliance flag (BoZ data residency) | Done |

### Ground Truth Validation

| Metric | Value |
|---|---|
| Total input | 70,472 rows |
| Clean loaded | 69,672 rows |
| Rejected (validation) | 800 rows |
| Silently dropped | **0 rows** |
| Quality score | 94.3% |

### Run Commands

``bash
python run_etl.py                           # default fixture
python run_etl.py --csv data.csv --force    # custom input, force re-process
python run_etl.py --dry-run                 # validate only
pytest tests/test_validation_ground_truth.py -v   # fixture regression (6/6)
python verify.py --verbose                  # ground-truth comparison
``

---

## 2. Feature Engineering Service — Implemented

Point-in-time customer features computed from ETL output using a single SQL aggregation pass.

### API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /features/compute-batch?as_of_date=YYYY-MM-DD | Compute 16 features for all customers as-of a date |
| GET | /features/{customer_id}?as_of_date=YYYY-MM-DD | Fetch snapshot for a specific date (404 if missing) |
| GET | /features/{customer_id}/latest | Latest snapshot for live scoring |

### Features Delivered (16 metrics per customer per date)

| Category | Features |
|---|---|
| **Recency** | days_since_last_txn, days_since_first_txn |
| **Frequency** | txn_count_30d, txn_count_90d, txn_count_180d |
| **Monetary** | total_amount_90d, avg_amount_90d, total_amount_180d, amount_growth_ratio |
| **Diversity** | distinct_channels_90d, distinct_txn_types_90d, dominant_channel |
| **Volatility** | amount_stddev_90d |

### Critical Guarantee: Point-in-Time Correctness

All features are computed using **only transactions on or before as_of_date** — preventing data leakage in downstream ML training. The SQL query enforces WHERE transaction_date <= as_of_date for every computation.

### Run Commands

``bash
uvicorn main:app --port 8002
curl -X POST "http://localhost:8002/features/compute-batch?as_of_date=2026-07-17"
curl "http://localhost:8002/features/CUST00001?as_of_date=2026-07-17"
curl "http://localhost:8002/features/CUST00001/latest"
pytest services/feature-engineering-service/tests/ -v    # 10/10 tests
``

---

## 3. Testing — Regression Suites

| Suite | Tests | Runtime |
|---|---|---|
| ETL fixture regression | 6 assertions | ~25s |
| Feature engineering | 10 tests | ~9s |

### Test Coverage

**ETL:** Total rejected, total clean, per-category counts, conservation, no co-flagged rows, audit rows_skipped = 0.

**Feature Engineering:** Point-in-time correctness, upsert idempotency, division-by-zero guard, single-transaction customer, zero-history exclusion, non-existent snapshot, latest endpoint ordering.

---

## 4. Branch Strategy

  architecture-target-full   Frozen reference (full 8-service design)
  poc-90day                  Active PoC branch (lean subset)

The full target architecture (HMM, RL, Kafka/Debezium, REST/SOAP connectors, champion/challenger, hardened gateway middleware) is preserved on architecture-target-full. Everything removed is recoverable:

``bash
git checkout architecture-target-full -- path/to/module/
``

Full details in ARCHITECTURE.md.

---

## 5. Infrastructure Status

| Component | State |
|---|---|
| PostgreSQL 18 (etl_validation + etl_clean) | Running |
| ETL Engine (run_etl.py) | Production-hardened |
| Feature Engineering Service (port 8002) | Implemented + tested |
| Customer State Service (Layer 1) | Next build |
| Prediction Service (Layer 2) | Scaffolded |
| Decision Intelligence Service (Layer 3) | Scaffolded |
| Dashboard Service | Scaffolded |
| PII Compliance | Flagged for BoZ review |

---

## 6. Next Steps (Month 2 — AI Services)

1. **Customer State Service (Layer 1)** — Markov chain classification: Active / At Risk / Dormant states from customer_features snapshots
2. **Prediction Service (Layer 2)** — Churn probability + CLV estimation (XGBoost)
3. **Decision Intelligence Service (Layer 3)** — Rule engine + NBA recommendations for Relationship Managers
4. **Dashboard Service** — RM-facing analytics

---

## 7. Key Files

| File | Purpose |
|---|---|
| run_etl.py | ETL engine CLI entry point |
| verify.py | Ground-truth comparison tool |
| etl/ | ETL engine (15 modules) |
| services/feature-engineering-service/ | Feature computation + API |
| tests/test_validation_ground_truth.py | ETL canary regression (6 tests) |
| services/feature-engineering-service/tests/test_features.py | Feature regression (10 tests) |
| ARCHITECTURE.md | Branch strategy + recovery commands |
| README.md | Project overview + quick start |
| .ai/ | AI development guide, sprint status, coding standards |
