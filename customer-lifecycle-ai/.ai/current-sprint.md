# Current Sprint — Phase 2: Foundation Implementation

**Sprint Status:** Planning
**Target:** Implement core infrastructure before ML logic

---

## Active Phase: Database & API Foundations

We are moving from scaffolding (Phase 1) to implementation (Phase 2).

## What's Done (Phase 1)

- [x] Complete project structure with 3-layer AI architecture
- [x] All 8 microservices scaffolded with Clean Architecture
- [x] Shared module with database, logging, exceptions, auth, ML utilities
- [x] Docker Compose for local development (PostgreSQL, Redis, all services)
- [x] Champion/challenger model registry structure
- [x] Feature Store subdirectories for all banking domains
- [x] Research notebook structure for experimentation
- [x] AI development guidance system (`.ai/`, `.github/`, `.cursor/`, `.claude/`)

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
