# Current Sprint — PoC (90-Day)

**Sprint Status:** PoC — Month 1: Data Foundation
**Branch:** `poc-90day` (active) | Reference: `architecture-target-full` (frozen)
**Target:** Feature Engineering Service + minimal 3-Layer AI by month-end

---

## Active Phase: Feature Engineering (Month 1 — Data Foundation)

ETL engine is production-hardened. Focus shifting to the Feature Store and service layer.

## Branch Strategy

| Branch | Purpose |
|---|---|
| `poc-90day` | **Active** — lean subset for 90-day PoC delivery |
| `architecture-target-full` | **Frozen reference** — full 8-service design for post-PoC rollout |
| `mukoma` | Original development branch |

See [ARCHITECTURE.md](../ARCHITECTURE.md) for recovery commands.

## What's Done (PoC — ETL Engine)

- [x] ETL pipeline runs end-to-end (CSV → Extract → Validate → Transform → Load → Audit)
- [x] All 10 validation categories verified against ground truth (800/800 dirty rows, 69,672 clean)
- [x] Compliance-grade immutable audit trail (`etl.etl_audit`) with batch-level traceability
- [x] Per-row rejection reasons (each rejected row carries its specific failed rule IDs)
- [x] Production hardening: bulk inserts (17K rows/s), structured logging, idempotency guard
- [x] Schema drift detection (strict mode — fails loudly on missing/reordered columns)
- [x] Data-agnostic invariant checks (conservation, no silent skips, reason coverage, quality floor)
- [x] Fixture regression test (`pytest tests/test_validation_ground_truth.py` — 6/6 passing)
- [x] PII compliance flag (customer_id/account_id plaintext review note for BoZ data residency)
- [x] Branch strategy: full architecture frozen on `architecture-target-full`, PoC on `poc-90day`

## What's Next (Month 1 — Data Foundation)

### Priority: Feature Engineering Service
1. Implement real feature generation logic in `services/feature-engineering-service/`
2. Build feature pipelines for: customer profile, transactions, products, loans, cards, digital, behaviour, CLV
3. Wire Feature Store to ETL output (customer_transactions_clean)
4. Create feature metadata registry (feature names, types, lineage)

### Supporting: Minimal 3-Layer Services
1. Customer State Service — basic Markov engine (no HMM)
2. Prediction Service — single XGBoost model (no champion/challenger)
3. Decision Intelligence — rule engine only (no RL)

## What's Deferred (available on `architecture-target-full`)

- Hidden Markov Model (`services/customer-state-service/app/engines/hmm/`)
- Reinforcement Learning (`services/decision-intelligence-service/app/reinforcement_learning/`)
- Kafka/Debezium streaming connectors (`etl/connectors/streaming/`)
- REST/SOAP API connectors (`etl/connectors/api/`)
- Orchestration service (not yet implemented)
- Champion/challenger model evaluation
- Full auth/rate-limit/CORS gateway middleware
