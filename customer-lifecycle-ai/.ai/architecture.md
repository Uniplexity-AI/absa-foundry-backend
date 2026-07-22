# Architecture — 3-Layer AI System

> **Active branch:** `poc-90day` (lean subset) | **Reference:** `architecture-target-full` (complete)
> PoC removes: HMM engine, RL engine, Kafka/Debezium/REST/SOAP connectors, orchestration service.
> See [ARCHITECTURE.md](../ARCHITECTURE.md) for branch strategy and recovery commands.

## Data Ingestion Tier (IMPLEMENTED — 9 modules)

Before data reaches the ETL engine, a **Dynamic Extractor, Unifier & Validation Engine** handles multi-table extraction from fragmented source schemas.

```
┌──────────────────────────────────────────────────────────────┐
│           Dynamic Extractor & Unifier (Pre-Processor)        │
│  YAML Spec → Version Guard → Join Validator → Query Builder  │
│  → Streaming Extraction → Pydantic v2 Validation             │
│  → Business Rules Engine → DLQ (audit.rejected_records)      │
│  Output: unified, structurally-valid DataFrame               │
└────────────────────────────┬─────────────────────────────────┘
                             │ unified DataFrame
                             ▼
┌──────────────────────────────────────────────────────────────┐
│               ETL Engine (run_etl.py — existing)             │
│  Schema Drift → Business Validation → Transform → Load       │
│  Output: *_clean / *_rejected tables in etl_clean            │
└──────────────────────────────────────────────────────────────┘
```

**Implementation:** `etl/extraction/` (9 files) | Wired via `--extraction-spec` flag | 2 YAML specs in `etl/config/extraction_specs/`

### API Gateway (IMPLEMENTED — 17 auth files)

```
Gateway (:8080) → JWT Auth → RBAC → Rate Limit → API Key Auth → Logging
Routes: /auth/*, /admin/*, /internal/*
Auth: LDAP-ready, JWT + refresh tokens, 6 roles, Redis blacklist
```

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      API Gateway (8080)                      │
│          Auth / Rate Limiting / Centralized Logging          │
└──────────┬──────────┬──────────┬──────────┬─────────────────┘
           │          │          │          │
     ┌─────▼────┐┌───▼────┐┌───▼─────┐┌───▼──────┐
     │ Layer 1  ││Layer 2 ││ Layer 3  ││ Supporting│
     │Customer  ││Predict.││ Decision ││ Services  │
     │ State    ││Service ││ Intel.   ││           │
     │ Service  ││        ││ Service  ││           │
     └────┬─────┘└───┬────┘└────┬─────┘└───────────┘
          │          │          │
          │  customer│  health  │
          │  state   │  score   │
          │          │  churn   │
          └──────────► prob     │
                     │  CLV     │
                     └──────────►
```

## Layer 1 — Customer State Service (`customer-state-service`)

**Purpose:** Track customer behavioural state using Markov Chains.

**Data Flow:**
1. Ingests customer transaction/behaviour data from Feature Store
2. Computes Markov transition matrix from historical customer journeys
3. Classifies each customer into a state: `Active`, `At Risk`, `Dormant`
4. Publishes state labels and transition probabilities

**Key Modules:**
- `engines/markov/` — Transition matrix computation, stationary distribution
- `engines/hmm/` — Hidden Markov Model (FUTURE — not yet implemented)
- `services/behaviour_profiler.py` — State classification and pattern extraction

**DO NOT** put prediction logic here. This service only deals with state transitions.

## Layer 2 — Prediction Service (`prediction-service`)

**Purpose:** Unified prediction engine for churn, CLV, and health scoring.

**Data Flow:**
1. Receives customer state from Layer 1
2. Receives features from Feature Store
3. Runs churn prediction model (XGBoost or LightGBM, configured via env)
4. Runs CLV prediction model (XGBoost or LightGBM, configured via env)
5. Computes Health Score = weighted fusion of churn prob + CLV + behavioural state
6. Publishes predictions to Layer 3

**Model Selection:**
- `PREDICTION_MODEL_TYPE=xgboost` (or `lightgbm`) — controls which model framework is used
- Both XGBoost and LightGBM implementations must exist; config determines which runs

**Key Modules:**
- `models/xgboost/` — XGBoost churn and CLV model implementations
- `models/lightgbm/` — LightGBM churn and CLV model implementations
- `services/health_score.py` — Composite health score calculator
- `training/` — Model training and hyperparameter tuning pipelines
- `evaluation/` — AUC-ROC, precision-recall, calibration metrics
- `explainability/shap/` — SHAP value computation for every prediction

**Health Score Formula:**
```
Health Score = (churn_weight × (1 - churn_prob)) + (clv_weight × clv_percentile) + (behaviour_weight × state_score)
```
Weights configured via `HEALTH_SCORE_CHURN_WEIGHT`, `HEALTH_SCORE_CLV_WEIGHT`, `HEALTH_SCORE_BEHAVIOUR_WEIGHT`.

## Layer 3 — Decision Intelligence Service (`decision-intelligence-service`)

**Purpose:** Generate Next Best Action (NBA) recommendations.

**Data Flow:**
1. Receives health score, churn probability, and CLV from Layer 2
2. Evaluates business rules against customer profile
3. Generates ranked NBA recommendations
4. Publishes recommendations to Dashboard Service

**Key Modules:**
- `rule_engine/` — Business rule definitions and evaluation engine
- `nba/` — NBA generation, ranking, and prioritization
- `reinforcement_learning/` — RL-based optimization (FUTURE — not yet implemented)

**DO NOT** hardcode rules. Rules must be configurable and auditable.

## Supporting Services

| Service | Responsibility |
|---------|---------------|
| `data-ingestion-service` | Replaced by `etl/` engine — removed from PoC (available on `architecture-target-full`) |
| `feature-engineering-service` | Central Feature Store — computes and caches all ML features |
| `model-management-service` | Champion/challenger registry, versioning, drift monitoring |
| `dashboard-service` | Aggregates data for the RM dashboard frontend |
| `orchestration-service` | Schedules pipelines, coordinates multi-service workflows |

## Service Communication

- **Synchronous:** REST via API Gateway for real-time predictions
- **Asynchronous:** Database-polling or Redis pub/sub for batch workflows
- **Never:** Direct service-to-service calls bypassing the Gateway in production

## Database Per-Service Strategy

While this is a monorepo, each service owns its **logical schema**:
- `customer_data` — Data ingestion
- `features` — Feature store
- `customer_states` — Layer 1
- `predictions` — Layer 2
- `decisions` — Layer 3
- `model_registry` — Model management

Tables from one schema are **never written** by another service.
