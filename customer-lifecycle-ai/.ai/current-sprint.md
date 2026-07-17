# Current Sprint — Phase 2: Foundation Implementation

**Sprint Status:** ETL Engine — Production Hardened ✅ | API Services — In Progress
**Target:** Implement core infrastructure before ML logic

---

## Active Phase: ETL Hardening Complete / Database & API Foundations

ETL engine is production-hardened and verified against ground truth. Focus shifting to API layer.

## What's Done (Phase 2a — ETL Engine)

- [x] ETL pipeline runs end-to-end (CSV → Extract → Validate → Transform → Load → Audit)
- [x] All 10 validation categories verified against ground truth (800/800 dirty rows, 69,672 clean)
- [x] Compliance-grade immutable audit trail (`etl.etl_audit`) with batch-level traceability
- [x] Per-row rejection reasons (each rejected row carries its specific failed rule IDs)
- [x] Production hardening: bulk inserts (17K rows/s), structured logging, idempotency guard
- [x] Schema drift detection (strict mode — fails loudly on missing/reordered columns)
- [x] Data-agnostic invariant checks (conservation, no silent skips, reason coverage, quality floor)
- [x] Fixture regression test (`pytest tests/test_validation_ground_truth.py` — 6/6 passing)
- [x] PII compliance flag (customer_id/account_id plaintext review note for BoZ data residency)

## What's Next (Phase 2)

### Priority 1: Database Models
1. Implement SQLAlchemy ORM models for each service
2. Set up Alembic for migrations
3. Create initial migration for all schemas:
   - `customer_data` — ingested customer records
   - `features` — feature store tables
   - `customer_states` — Markov state assignments
   - `predictions` — churn/CLV/health score predictions
   - `decisions` — NBA recommendations
   - `model_registry` — champion/challenger tracking

### Priority 2: API Endpoints
1. Implement CRUD routes for each service
2. Set up FastAPI dependency injection
3. Wire up service → repository → database flow
4. Add request/response validation with Pydantic v2
5. Implement health check endpoints

### Priority 3: Shared Infrastructure
1. Finalize `shared/database/session.py` with async session factory
2. Implement `shared/auth/authenticator.py` with JWT
3. Set up `shared/logging/logger.py` for structured JSON logging
4. Implement `shared/exceptions/` hierarchy

## What NOT to Implement Yet

- ❌ Markov chain transition matrices (Phase 3)
- ❌ XGBoost/LightGBM model training (Phase 3)
- ❌ SHAP explainability (Phase 3)
- ❌ NBA rule engine logic (Phase 4)
- ❌ Champion/challenger evaluation (Phase 4)
- ❌ RL-based optimization (Future)

## Current Focus for AI Agents

When asked to implement code right now, the response should be:

1. **Build database models first** — `app/models/models.py` for each service
2. **Then build schemas** — `app/schemas/schemas.py` (Pydantic v2)
3. **Then build repositories** — `app/repository/repository.py`
4. **Then build services** — `app/services/service.py` (thin, delegates to repos initially)
5. **Then build routes** — `app/api/routes.py`

Follow the order. Don't jump ahead.

## Next Sprint Preview (Phase 3)

- Markov chain implementation in customer-state-service
- XGBoost and LightGBM model training in prediction-service
- SHAP explainability integration
- Health score calculator
- Feature Store pipeline implementation
