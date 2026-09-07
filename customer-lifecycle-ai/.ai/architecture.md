# Architecture — ABSA Customer Lifecycle Platform

> **Active branch:** `poc-90day` (Phase 1 live)  
> **Status:** Demo-ready — 5 services, 6 pages wired, 34/34 tests  
> **Last updated:** 2026-08-07  
> **Reference:** `docs/architecture/decision-intelligence-platform-v3.md` (full design)

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   API Gateway (:8080)                        │
│      Auth / RBAC / Rate Limit / API Key / Logging            │
│      15 routes proxying to all backend services              │
└──────┬──────────┬──────────┬──────────┬─────────────────────┘
       │          │          │          │
 ┌─────▼────┐ ┌──▼─────┐ ┌─▼───────┐ ┌─▼──────────┐
 │ Layer 1  │ │Layer 2 │ │Layer 3  │ │ Supporting  │
 │ Customer │ │Predict.│ │Decision │ │ Services    │
 │ State    │ │Service │ │Intel.   │ │             │
 │ (:8003)  │ │(:8004) │ │(:8005)  │ │ (:8002)     │
 │          │ │        │ │         │ │ Features    │
 │ Markov   │ │XGBoost │ │9 engines│ │ ETL         │
 │ Chain    │ │Churn   │ │YAML cfg │ │ PostgreSQL  │
 └──────────┘ └────────┘ └─────────┘ └─────────────┘
```

---

## 2. Layer 1 — Customer State Service (:8003)

**Purpose:** Classify every customer into a discrete lifecycle state.

| Component | Description |
|-----------|-------------|
| State Engine | 4-priority rule-based classifier (Active → At Risk → Dormant → Churned) |
| Markov Engine | 4×4 transition probability matrix, steady-state analysis |
| Transition Analyzer | Detects state transitions between snapshots |
| Repository | psycopg2 sync, batch upsert, idempotent ON CONFLICT |

**API Endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/states/compute` | Classify all customers |
| GET | `/states/portfolio` | Aggregate state counts |
| GET | `/states` | Paginated list-all |
| GET | `/{customer_id}` | Single snapshot |
| GET | `/{customer_id}/timeline` | State history + transitions |
| GET | `/markov/matrix` | 4×4 transition matrix |
| GET | `/markov/predict/{id}` | Next-state prediction |

---

## 3. Layer 2 — Prediction Service (:8004)

**Purpose:** Score every customer with churn probability and health score.

| Component | Description |
|-----------|-------------|
| Churn Predictor | XGBoost model, AUC 0.7672, 65 training features |
| Health Scorer | Composite 0-100 from churn risk + CLV + behaviour |
| Model Registry | Champion/challenger tracking |

**API Endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/predict/batch` | Score all 4,998 customers (2.8s) |
| GET | `/predict/models` | Registered models with metrics |
| GET | `/{customer_id}/churn` | Churn probability (0-1) |
| GET | `/{customer_id}/health` | Health score breakdown |
| GET | `/{customer_id}` | Full prediction |

---

## 4. Layer 3 — Decision & Insight Intelligence Platform v3.0 (:8005)

The platform answers: *Why? What? Who? When? What next? What if?*

### 4.1 The Six Engines

```
┌─────────────────────────────────────────────────────────────────┐
│              DECISION & INSIGHT INTELLIGENCE PLATFORM            │
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  CHURN   │ │CUSTOMER  │ │ DECISION │ │RECOMMEND.│           │
│  │  INTEL   │ │  INTEL   │ │  ENGINE  │ │  ENGINE  │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       │             │            │            │                  │
│  ┌────┴─────────────┴────────────┴────────────┴────────┐       │
│  │               SHARED FOUNDATION                      │       │
│  │  Decision Context Builder | Policy & Rules (YAML)   │       │
│  │  Decision Memory (Audit + Feedback Loop)            │       │
│  └────────────────────────┬────────────────────────────┘       │
│                           │                                     │
│  ┌────────────────────────┴────────────────────────────┐       │
│  │            INSIGHT & EXPLANATION LAYER               │       │
│  │  FORECAST ENGINE | EXPLANATION ENGINE | INSIGHT ENG  │       │
│  └─────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

| Engine | Question | Phase 1 Status |
|--------|----------|---------------|
| **Churn Intelligence** | Why are customers leaving? | 🔨 Root cause, segment analysis |
| **Customer Intelligence** | What's happening to this customer? | ✅ Health trajectory, lifecycle stage, alerts |
| **Decision Engine** | What should the bank do? | ✅ NBA, ranking (LightGBM), strategy, routing, approval |
| **Recommendation Engine** | What product to offer? | 🔨 NBO, cross-sell, campaign mapping |
| **Forecast Engine** | What will happen? | 🔨 Churn forecast, revenue at risk |
| **Insight Engine** | What does this mean? | 🔜 LLM explanations (Phase 3) |

### 4.2 Decision Engine — 9 Sub-Engines (Implemented)

| # | Engine | Purpose |
|---|--------|---------|
| 1 | Eligibility Engine | YAML rules: AML, KYC, age, credit risk, complaints |
| 2 | Business Rules Engine | YAML banking logic: VIP escalation, retention priority |
| 3 | Action Generator | 25 actions across 5 categories (YAML catalog) |
| 4 | Ranking Engine (heuristic) | YAML-configurable scoring weights + thresholds |
| 5 | Ranking Engine (LightGBM) | ML model: 19 features, MAE 0.0015 |
| 6 | Strategy Layer | Balanced / Retention First / Revenue First |
| 7 | Optimization Engine | Multi-objective scoring |
| 8 | Routing Engine | RM vs Digital vs Marketing channel selection |
| 9 | Approval Workflow | Auto-execute vs human approval |
| — | Composer | Assembles final DecisionPackage |

### 4.3 YAML-Driven Configuration

All business logic is in YAML — no hardcoded rules:

| Config File | Purpose |
|-------------|---------|
| `ranking/ranking_rules.yaml` | Scoring weights, thresholds per category |
| `candidates/action_catalog.yaml` | 25 actions → 5 categories |
| `policies/banking_rules.yaml` | 8 business rules (VIP, churned, dormant, etc.) |
| `eligibility/eligibility_rules.yaml` | KYC, AML, age, credit risk checks |

---

## 5. Feature Engineering Service (:8002)

**Purpose:** Central feature store — 22 features per customer across 4,998 customers.

| Domain | Features |
|--------|----------|
| Transaction Behaviour | txn_count_30d/90d, total_amount_90d, days_since_last_txn |
| Customer Profile | age_years, customer_tenure_days, customer_segment |
| Product Holdings | product counts, has_salary_credit |
| Engagement | engagement_score, digital_channel_usage |

---

## 6. API Gateway (:8080)

15 routes registered:

| Prefix | Proxied To | Routes |
|--------|-----------|--------|
| `/auth/*` | Gateway internal | Login, refresh, logout |
| `/admin/*` | Gateway internal | Users, roles, API keys |
| `/api/v1/customers/*` | State :8003 | Portfolio, list, detail, timeline |
| `/api/v1/predictions/*` | Prediction :8004 + State :8003 | Churn, health, markov-matrix |
| `/api/v1/models` | Prediction :8004 | Model registry |
| `/api/etl/*` | PostgreSQL | ETL dashboard |
| `/features/*` | Feature :8002 | Compute batch, snapshots |

---

## 7. ETL Pipeline

```
Raw Data (PostgreSQL)
  → Dynamic Extractor (YAML spec → SQL → Parquet)
    → Validate (schema + business rules)
      → Transform (standardize + enrich)
        → Load (customers_clean, accounts_clean, etc.)
          → Audit (etl.etl_audit with quality scores)
```

- 11 extraction specs in `etl/config/extraction_specs/`
- 15,200 rows loaded on latest run
- 14 audit records with quality scores
- 100% quality on latest run

---

## 8. Architecture Decision Records

| # | Decision | Rationale |
|---|----------|-----------|
| ADR-001 | Six engines, one platform, shared foundation | DecisionContext built once, consumed by all |
| ADR-002 | Churn Intelligence is portfolio-level | Per-customer churn is Prediction Service (L2) |
| ADR-003 | Decision routing by stakeholder | Not every decision needs human intervention |
| ADR-004 | Forecast separate from predictions | Enables scenario modeling |
| ADR-005 | LLM explains, never decides | Deterministic engines produce decisions |
| ADR-006 | YAML for all rules/catalogs/strategies | Audit-friendly, hot-reloadable |
| ADR-007 | Decision Memory for closed-loop | Every decision → execution → outcome tracked |
| ADR-008 | Single DecisionContext shared across engines | No engine queries upstream individually |

---

## 9. Phase 1 Delivery (Current)

| Engine | Capabilities | Status |
|--------|-------------|--------|
| Foundation | Decision Context Builder, Policy Engine, Eligibility Engine, Decision Memory | ✅ |
| Decision Engine | Action Gen, Heuristic Ranking, LightGBM, Strategy, Routing, Approval | ✅ |
| Customer Intelligence | Health Trajectory, Lifecycle Stage, Behavioural Alerts | ✅ |
| Recommendation Engine | Product Propensity (heuristic), Cross-sell Logic | 🔨 |
| Churn Intelligence | Root Cause (aggregate SHAP), Segment Deterioration | 🔨 |
| Forecast Engine | Churn Forecast, Revenue at Risk | 🔨 |
| Insight Engine | Reason Code Generator | 🔜 Phase 3 |
