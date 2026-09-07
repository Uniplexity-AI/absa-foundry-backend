# CLAUDE.md — Customer Lifecycle Prediction System

## Before Any Code Changes

Read the `.ai/` and `graphify-out` directories in this order:

1. `.ai/README.md` — Entry point, quick rules, and Token Efficiency Protocol
2. `graphify-out/GRAPH_REPORT.md` — Codebase semantic graph (community groupings & files)
3. `.ai/project-context.md` — What we're building and banking constraints
4. `.ai/current-sprint.md` — Current phase and priorities
5. `.ai/architecture.md` — Complete 3-layer architecture
6. `.ai/coding-standards.md` — How code must be structured
7. `.ai/skills/<relevant-skill>.md` — Task-specific validated patterns

---

## Token Efficiency Navigation Protocol (MUST FOLLOW)

To drastically minimize LLM context token consumption and avoid context bloating:
* **Locate, Don't Scan**: Avoid scanning large directories or grepping entire folders. Open `graphify-out/GRAPH_REPORT.md` first to locate which semantic community and files contain the components or bridges (e.g. `BaseModel`, `ConnectorConfig`, `ExtractionConfigSpec`) you need.
* **Targeted Reads**: Never do full-file reads on files over 150 lines. Fetch the outline first, then request specific line ranges via `start_line` / `end_line`.
* **Zero Guessing / Inventing**: Refer directly to `.ai/skills/` for validated design templates.
* **Surgical Edits**: Provide minimal context line replacements in edits. Do not rewrite whole sections unnecessarily.

---

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
