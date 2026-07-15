# CLAUDE.md — Customer Lifecycle Prediction System

## Before Any Code Changes

Read the `.ai/` directory in this order:

1. `.ai/README.md` — Entry point and quick rules
2. `.ai/project-context.md` — What we're building and banking constraints
3. `.ai/current-sprint.md` — Current phase and priorities
4. `.ai/architecture.md` — Complete 3-layer architecture
5. `.ai/coding-standards.md` — How code must be structured
6. `.ai/skills/<relevant-skill>.md` — Task-specific patterns

## Project Identity

Customer Lifecycle Prediction System — an enterprise AI platform for banking:
- Predicts customer churn, CLV, and health scores
- Recommends Next Best Actions (NBA) for Relationship Managers
- Deployed on Ubuntu servers with Docker Compose (no K8s)
- Internal banking deployment — air-gapped, no internet access

## Architecture at a Glance

```
Layer 1: customer-state-service     (Markov chain state tracking)
    ↓
Layer 2: prediction-service         (XGBoost/LightGBM churn + CLV + health score)
    ↓
Layer 3: decision-intelligence-service (rule engine + NBA recommendations)
    ↓
dashboard-service                    (RM-facing analytics)
```

Supporting: data-ingestion, feature-engineering, model-management, orchestration

## Non-Negotiable Rules

1. Clean Architecture: Routes → Services → Repositories → Database
2. Business logic ONLY in `app/services/service.py`
3. Data access ONLY in `app/repository/repository.py`
4. All config via `app/config/settings.py` (environment variables)
5. Pydantic v2 schemas, SQLAlchemy 2.0 models
6. Full type hints on all function signatures (Python 3.12+ syntax)
7. Module docstring + TODO in every file
8. Tests in `tests/unit/` for every new function

## Current Phase: Database & API Foundations

We are NOT implementing ML logic yet. Focus on:
1. SQLAlchemy ORM models
2. Pydantic v2 schemas
3. Repository pattern implementations
4. Service layer (thin for now)
5. FastAPI route definitions

## Project Root

`customer-lifecycle-ai/` — all paths relative to this directory.
